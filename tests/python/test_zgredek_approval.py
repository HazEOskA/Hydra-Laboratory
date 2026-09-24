"""Zgredek manual approval v0.2.

A prepared packet is PENDING_APPROVAL and unusable. An authorized human
authority accepts one exact content hash; Zgredek may never accept its own
output; any later edit to the content breaks the approval automatically.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from hydra_control.models import (  # noqa: E402
    AuthorizationError,
    ConflictError,
    NotFoundError,
)
from hydra_control.server import create_server  # noqa: E402
from hydra_control.service import MissionService  # noqa: E402
from hydra_control.zgredek import (  # noqa: E402
    ADAPTER_ID,
    STATUS_APPROVED,
    STATUS_PENDING,
)


class ApprovalContractCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.service = MissionService.local(self._dir.name)
        self.service.seed_registries()
        self.mission_id = self.service.create_mission(
            {"title": "Approval", "request": "Add a helper", "requiredTests": ["test_app.py"]}
        )["mission_id"]

    def tearDown(self) -> None:
        self.service.store.close()
        self._dir.cleanup()

    def sha(self) -> str:
        return self.service.store.context_packet(self.mission_id)["sha256"]

    def approve(self, actor: str = "OSA", sha: str | None = None):
        return self.service.approve_context_packet(
            self.mission_id, actor=actor, packet_sha256=sha if sha is not None else self.sha()
        )

    def fact_node(self) -> dict:
        mission = self.service.store.get_mission(self.mission_id)
        return next(n for n in mission["nodes"] if n["node_id"] == "repository-fact-load")

    # -- 1. a fresh packet awaits approval ----------------------------

    def test_prepared_packet_is_pending_approval(self) -> None:
        report = self.service.context_packet(self.mission_id)
        self.assertTrue(report["valid"])
        self.assertEqual(report["approval"]["status"], STATUS_PENDING)
        self.assertFalse(report["approval"]["approved"])
        self.assertEqual(report["packet"]["approvedBy"], "")
        self.assertEqual(report["packet"]["approvedPacketSha256"], "")

    def test_zgredek_does_not_approve_its_own_packet_at_preparation(self) -> None:
        packet = self.service.store.context_packet(self.mission_id)
        self.assertNotEqual(packet.get("approvedBy"), ADAPTER_ID)
        self.assertEqual(packet["status"], STATUS_PENDING)

    # -- 2. no approval blocks the node before attempt 1 --------------

    def test_missing_approval_blocks_fact_load_before_first_attempt(self) -> None:
        self.service.start(self.mission_id, asynchronous=False)
        mission = self.service.store.get_mission(self.mission_id)
        node = self.fact_node()
        self.assertEqual(mission["state"], "BLOCKED")
        self.assertEqual(node["state"], "BLOCKED")
        self.assertEqual(node["attempt"], 0)
        self.assertIn("PENDING_APPROVAL", mission["failure_reason"])
        artifacts = [
            a for a in self.service.artifacts(self.mission_id)
            if a["node_id"] == "repository-fact-load"
        ]
        self.assertEqual(artifacts, [])

    # -- 3. OSA approves a valid packet -------------------------------

    def test_osa_approves_a_valid_packet(self) -> None:
        sha = self.sha()
        result = self.approve()
        self.assertTrue(result["approved"])
        self.assertFalse(result["idempotent"])
        self.assertEqual(result["approvedBy"], "OSA")
        self.assertEqual(result["approvedPacketSha256"], sha)

        report = self.service.context_packet(self.mission_id)
        self.assertEqual(report["approval"]["status"], STATUS_APPROVED)
        self.assertTrue(report["approval"]["approved"])
        self.assertTrue(report["approval"]["approvedAt"])

    def test_approval_appends_an_apr_event(self) -> None:
        self.approve()
        events = [
            e for e in self.service.events(self.mission_id)
            if e["event_type"] == "CONTEXT_PACKET_APPROVED"
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["actor"], "OSA")
        self.assertEqual(events[0]["next_state"], "APPROVED")

    def test_reapproving_the_same_sha_is_idempotent(self) -> None:
        first = self.approve()
        second = self.approve()
        self.assertTrue(second["approved"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(second["approvedAt"], first["approvedAt"])
        events = [
            e for e in self.service.events(self.mission_id)
            if e["event_type"] == "CONTEXT_PACKET_APPROVED"
        ]
        self.assertEqual(len(events), 1, "idempotent approval must not duplicate the ledger entry")

    # -- 4. an unauthorized actor is rejected -------------------------

    def test_unauthorized_actor_is_rejected(self) -> None:
        with self.assertRaises(AuthorizationError) as caught:
            self.approve(actor="randomdev")
        self.assertIn("nie jest autoryzowany", str(caught.exception))
        self.assertEqual(
            self.service.context_packet(self.mission_id)["approval"]["status"], STATUS_PENDING
        )

    def test_zgredek_cannot_approve_its_own_packet(self) -> None:
        with self.assertRaises(AuthorizationError) as caught:
            self.approve(actor=ADAPTER_ID)
        self.assertIn("nie może zatwierdzać własnego packetu", str(caught.exception))

    def test_an_explicitly_authorized_actor_may_approve(self) -> None:
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"HYDRA_CONTEXT_APPROVERS": "OSA-DEPUTY"}):
            result = self.approve(actor="OSA-DEPUTY")
        self.assertTrue(result["approved"])

    def test_a_forged_approval_in_storage_is_not_honoured(self) -> None:
        # Writing an approval directly, bypassing the endpoint, must not work:
        # the recorded approver is still checked against the allowlist.
        stored = self.service.store.context_packet(self.mission_id)
        stored.update(
            status=STATUS_APPROVED,
            approvedBy="intruder",
            approvedAt="2026-08-03T00:00:00.000Z",
            approvedPacketSha256=stored["sha256"],
        )
        self.service.store.save_context_packet(self.mission_id, stored)
        report = self.service.context_packet(self.mission_id)
        self.assertFalse(report["approval"]["approved"])
        self.assertTrue(any("nie jest autoryzowany" in r for r in report["approval"]["reasons"]))

    def test_a_self_approval_written_directly_is_not_honoured(self) -> None:
        stored = self.service.store.context_packet(self.mission_id)
        stored.update(
            status=STATUS_APPROVED,
            approvedBy=ADAPTER_ID,
            approvedAt="2026-08-03T00:00:00.000Z",
            approvedPacketSha256=stored["sha256"],
        )
        self.service.store.save_context_packet(self.mission_id, stored)
        report = self.service.context_packet(self.mission_id)
        self.assertFalse(report["approval"]["approved"])
        self.assertTrue(
            any("własnego packetu" in r for r in report["approval"]["reasons"])
        )

    # -- 5. tampering after approval invalidates it -------------------

    def test_tampering_after_approval_invalidates_the_approval(self) -> None:
        self.approve()
        self.assertTrue(self.service.context_packet(self.mission_id)["approval"]["approved"])

        stored = self.service.store.context_packet(self.mission_id)
        stored["acceptedDecisions"] = [{"id": "D-999", "title": "injected", "statement": "x"}]
        self.service.store.save_context_packet(self.mission_id, stored)

        report = self.service.context_packet(self.mission_id)
        self.assertFalse(report["valid"])
        self.assertFalse(report["approval"]["approved"])

        self.service.start(self.mission_id, asynchronous=False)
        self.assertEqual(self.service.store.get_mission(self.mission_id)["state"], "BLOCKED")
        self.assertEqual(self.fact_node()["attempt"], 0)

    def test_content_edit_with_recomputed_hash_still_breaks_the_approval(self) -> None:
        """The subtle case: a tamperer who also fixes the hash.

        The approval pins the hash it was granted for, so a recomputed hash no
        longer matches it and the approval falls away on its own.
        """
        from hydra_control.zgredek import ContextPacket, canonical_sha256

        self.approve()
        stored = self.service.store.context_packet(self.mission_id)
        stored["acceptedDecisions"] = [{"id": "D-999", "title": "injected", "statement": "x"}]
        stored["sha256"] = canonical_sha256(ContextPacket.from_dict(stored).payload())
        self.service.store.save_context_packet(self.mission_id, stored)

        report = self.service.context_packet(self.mission_id)
        self.assertTrue(report["valid"], "content hash was recomputed, so content verifies")
        self.assertFalse(report["approval"]["approved"], "but the approval no longer matches")
        self.assertTrue(any("innego SHA-256" in r for r in report["approval"]["reasons"]))

    # -- 6. approving a different SHA does not pass -------------------

    def test_approving_a_different_sha_is_refused(self) -> None:
        with self.assertRaises(ConflictError) as caught:
            self.approve(sha="0" * 64)
        self.assertIn("dokładny SHA-256", str(caught.exception))
        self.assertEqual(
            self.service.context_packet(self.mission_id)["approval"]["status"], STATUS_PENDING
        )

    def test_approving_a_tampered_packet_is_refused(self) -> None:
        stored = self.service.store.context_packet(self.mission_id)
        stored["acceptedDecisions"] = [{"id": "D-999", "title": "injected", "statement": "x"}]
        self.service.store.save_context_packet(self.mission_id, stored)
        with self.assertRaises(ConflictError) as caught:
            self.approve(sha=stored["sha256"])
        self.assertIn("nieważnego packetu", str(caught.exception))

    def test_approving_a_missing_packet_is_refused(self) -> None:
        self.service.store.conn.execute(
            "DELETE FROM control_context_packets WHERE mission_id = ?", (self.mission_id,)
        )
        self.service.store.conn.commit()
        with self.assertRaises(NotFoundError):
            self.service.approve_context_packet(
                self.mission_id, actor="OSA", packet_sha256="0" * 64
            )

    # -- 7. retry after approval runs repository-fact-load ------------

    def test_retry_after_approval_runs_fact_load(self) -> None:
        self.service.start(self.mission_id, asynchronous=False)
        self.assertEqual(self.fact_node()["state"], "BLOCKED")

        self.approve()
        self.service.retry(self.mission_id, "repository-fact-load", "OSA", asynchronous=False)

        node = self.fact_node()
        self.assertEqual(node["state"], "PASSED")
        self.assertGreaterEqual(node["attempt"], 1)

    def test_approval_before_start_lets_the_mission_proceed(self) -> None:
        self.approve()
        self.service.start(self.mission_id, asynchronous=False)
        self.assertEqual(self.fact_node()["state"], "PASSED")
        self.assertEqual(
            self.service.store.get_mission(self.mission_id)["state"],
            "AWAITING_ARCHITECTURE_APPROVAL",
        )

    # -- 8. the ledger chain still verifies ---------------------------

    def test_ledger_chain_verifies_across_prepare_approve_and_validate(self) -> None:
        self.approve()
        self.service.start(self.mission_id, asynchronous=False)
        ok, detail = self.service.store.verify_event_chain(self.mission_id)
        self.assertTrue(ok, detail)
        types = [e["event_type"] for e in self.service.events(self.mission_id)]
        for expected in (
            "CONTEXT_PACKET_PREPARED",
            "CONTEXT_PACKET_APPROVED",
            "CONTEXT_PACKET_VALIDATED",
        ):
            self.assertIn(expected, types)

    def test_context_events_remain_append_only(self) -> None:
        self.approve()
        with self.assertRaises(Exception):
            self.service.store.conn.execute(
                "UPDATE control_events SET actor = 'forged' WHERE event_type = ?",
                ("CONTEXT_PACKET_APPROVED",),
            )

    # -- 9. rollback stays additive -----------------------------------

    def test_approval_adds_no_schema_migration(self) -> None:
        """Approval lives inside the stored packet JSON.

        Nothing about v0.2 requires a new table or column, so reverting the code
        needs no database change at all.
        """
        self.approve()
        self.assertEqual(self.service.store.schema_versions(), [1, 2, 3])

    def test_pipeline_shape_and_state_machine_are_unchanged(self) -> None:
        mission = self.service.store.get_mission(self.mission_id)
        node_ids = [n["node_id"] for n in mission["nodes"]]
        self.assertEqual(len(node_ids), 14)
        self.assertEqual(node_ids[0], "mission-intake")
        self.assertEqual(node_ids[1], "repository-fact-load")
        self.assertEqual(node_ids[-1], "draft-pull-request")


class ApprovalApiCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._dir = tempfile.TemporaryDirectory()
        cls.service = MissionService.local(cls._dir.name)
        cls.service.seed_registries()
        cls.server = create_server(cls.service, port=0, web_root=REPO_ROOT / "web")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.service.store.close()
        cls._dir.cleanup()

    def _mission(self) -> str:
        return self.service.create_mission(
            {"title": "ApiApproval", "request": "Add a helper"}
        )["mission_id"]

    def _post(self, mission_id: str, body: dict, actor: str = "OSA"):
        request = Request(
            f"{self.base}/api/context-packet/{mission_id}/approve",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Hydra-Actor": actor},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            return response.status, json.load(response)

    def test_endpoint_approves_and_reports_status(self) -> None:
        mission_id = self._mission()
        sha = self.service.store.context_packet(mission_id)["sha256"]
        status, payload = self._post(mission_id, {"packetSha256": sha})
        self.assertEqual(status, 200)
        self.assertTrue(payload["approved"])

        with urlopen(f"{self.base}/api/context-packet/{mission_id}", timeout=10) as r:
            report = json.load(r)
        self.assertEqual(report["approval"]["status"], STATUS_APPROVED)
        self.assertTrue(report["approval"]["approved"])

    def test_endpoint_rejects_an_unauthorized_actor_with_403(self) -> None:
        mission_id = self._mission()
        sha = self.service.store.context_packet(mission_id)["sha256"]
        with self.assertRaises(HTTPError) as caught:
            self._post(mission_id, {"packetSha256": sha}, actor="randomdev")
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()

    def test_endpoint_rejects_a_wrong_sha_with_409(self) -> None:
        mission_id = self._mission()
        with self.assertRaises(HTTPError) as caught:
            self._post(mission_id, {"packetSha256": "0" * 64})
        self.assertEqual(caught.exception.code, 409)
        caught.exception.close()

    def test_endpoint_rejects_unknown_body_fields(self) -> None:
        mission_id = self._mission()
        sha = self.service.store.context_packet(mission_id)["sha256"]
        with self.assertRaises(HTTPError) as caught:
            self._post(mission_id, {"packetSha256": sha, "force": True})
        self.assertEqual(caught.exception.code, 422)
        caught.exception.close()

    def test_endpoint_rejects_an_unknown_mission_with_404(self) -> None:
        with self.assertRaises(HTTPError) as caught:
            self._post("00000000-0000-4000-8000-000000000000", {"packetSha256": "0" * 64})
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()

    def test_approval_response_carries_no_credential_material(self) -> None:
        mission_id = self._mission()
        sha = self.service.store.context_packet(mission_id)["sha256"]
        _, payload = self._post(mission_id, {"packetSha256": sha})
        raw = json.dumps(payload)
        for needle in ("Authorization", "api_key", "API_KEY", "token"):
            self.assertNotIn(needle, raw)


if __name__ == "__main__":
    unittest.main()
