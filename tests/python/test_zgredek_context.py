"""Contract tests for the Zgredek context packet v0.1.

Positive: a packet is prepared, approved, hashed, validated and lets
repository-fact-load run.

Negative: a missing, tampered, mission-mismatched, repository-mismatched,
branch-mismatched, unapproved or unevaluable packet **refuses** execution.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from hydra_control.server import create_server  # noqa: E402
from hydra_control.service import MissionService  # noqa: E402
from hydra_control.zgredek import (  # noqa: E402
    PACKET_SCHEMA_VERSION,
    ContextPacket,
    DeterministicZgredek,
    canonical_sha256,
)


class PacketPreparationCase(unittest.TestCase):
    def setUp(self) -> None:
        self.zgredek = DeterministicZgredek(REPO_ROOT)
        self.packet = self.zgredek.prepare(
            mission_id="m-1",
            repository="fixture://hydra-safe-demo",
            base_branch="main",
            now="2026-08-03T00:00:00.000Z",
        )

    def test_packet_carries_every_required_section(self) -> None:
        data = self.packet.to_dict()
        for key in (
            "repositoryInstructions",
            "architectureLocks",
            "acceptedDecisions",
            "ownership",
            "forbiddenDrift",
            "requiredEvidence",
            "sha256",
        ):
            with self.subTest(key=key):
                self.assertIn(key, data)
                self.assertTrue(data[key], f"{key} is empty")

    def test_schema_version_is_stable(self) -> None:
        self.assertEqual(self.packet.schema_version, PACKET_SCHEMA_VERSION)
        self.assertEqual(PACKET_SCHEMA_VERSION, "zgredek-context-packet/0.1")

    def test_sha256_covers_the_payload_and_is_reproducible(self) -> None:
        self.assertEqual(self.packet.sha256, canonical_sha256(self.packet.payload()))
        again = self.zgredek.prepare(
            mission_id="m-1",
            repository="fixture://hydra-safe-demo",
            base_branch="main",
            now="2026-08-03T00:00:00.000Z",
        )
        self.assertEqual(again.sha256, self.packet.sha256)

    def test_sha256_changes_when_the_binding_changes(self) -> None:
        other = self.zgredek.prepare(
            mission_id="m-2",
            repository="fixture://hydra-safe-demo",
            base_branch="main",
            now="2026-08-03T00:00:00.000Z",
        )
        self.assertNotEqual(other.sha256, self.packet.sha256)

    def test_real_repository_locks_and_decisions_are_discovered(self) -> None:
        lock_paths = {lock["path"] for lock in self.packet.architecture_locks}
        self.assertIn("docs/ARCHITECTURE_LOCK_v0.1.md", lock_paths)
        self.assertIn("docs/MINION_CONTROL_PLANE_ARCHITECTURE_LOCK_v0.1.md", lock_paths)
        decision_ids = {d["id"] for d in self.packet.accepted_decisions}
        self.assertIn("D-001", decision_ids)
        for decision in self.packet.accepted_decisions:
            self.assertTrue(decision["title"])

    def test_absent_instruction_files_are_reported_not_hidden(self) -> None:
        by_path = {i["path"]: i for i in self.packet.repository_instructions}
        self.assertTrue(by_path["SOUL.md"]["present"])
        # No CLAUDE.md exists in this repository; that must be visible.
        self.assertFalse(by_path["CLAUDE.md"]["present"])
        self.assertEqual(by_path["CLAUDE.md"]["sha256"], "")

    def test_ownership_is_unknown_without_codeowners(self) -> None:
        ownership = self.packet.ownership
        self.assertEqual(ownership["rootAuthority"], "OSA")
        self.assertEqual(ownership["status"], "UNKNOWN")
        self.assertEqual(ownership["perPath"], [])

    def test_forbidden_drift_entries_cite_a_source(self) -> None:
        for entry in self.packet.forbidden_drift:
            self.assertTrue(entry["statement"])
            self.assertTrue(entry["source"])

    def test_drift_report_passes_against_an_unchanged_repository(self) -> None:
        report = self.zgredek.drift_report(self.packet)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["findings"], [])

    def test_drift_is_detected_when_a_recorded_lock_changes(self) -> None:
        tampered = ContextPacket.from_dict(
            {
                **self.packet.to_dict(),
                "architectureLocks": [
                    {**self.packet.architecture_locks[0], "sha256": "0" * 64}
                ],
            }
        )
        report = self.zgredek.drift_report(tampered)
        self.assertEqual(report["status"], "DRIFT")
        self.assertEqual(report["findings"][0]["kind"], "CHANGED")

    def test_drift_is_unknown_when_there_is_nothing_to_compare(self) -> None:
        empty = ContextPacket.from_dict(
            {**self.packet.to_dict(), "architectureLocks": [], "repositoryInstructions": []}
        )
        self.assertEqual(self.zgredek.drift_report(empty)["status"], "UNKNOWN")

    def test_reader_refuses_to_escape_the_repository_root(self) -> None:
        self.assertIsNone(self.zgredek._read("../../etc/passwd"))


class PacketVerificationCase(unittest.TestCase):
    """Every way a packet can be unusable must be reported, not tolerated."""

    def setUp(self) -> None:
        self.zgredek = DeterministicZgredek(REPO_ROOT)
        self.packet = self.zgredek.prepare(
            mission_id="m-1",
            repository="fixture://hydra-safe-demo",
            base_branch="main",
            now="2026-08-03T00:00:00.000Z",
        )
        self.binding = {
            "mission_id": "m-1",
            "repository": "fixture://hydra-safe-demo",
            "base_branch": "main",
        }

    def test_untouched_packet_verifies(self) -> None:
        self.assertEqual(self.zgredek.verify(self.packet, **self.binding), [])

    def _mutate(self, **changes) -> ContextPacket:
        return ContextPacket.from_dict({**self.packet.to_dict(), **changes})

    def test_tampered_content_breaks_the_hash(self) -> None:
        # Change a statement without recomputing the hash.
        tampered = self._mutate(acceptedDecisions=[{"id": "D-999", "title": "fake", "statement": "x"}])
        reasons = self.zgredek.verify(tampered, **self.binding)
        self.assertTrue(any("SHA-256" in r for r in reasons))

    def test_mission_mismatch_is_refused(self) -> None:
        reasons = self.zgredek.verify(self.packet, **{**self.binding, "mission_id": "m-other"})
        self.assertTrue(any("innej misji" in r for r in reasons))

    def test_repository_mismatch_is_refused(self) -> None:
        reasons = self.zgredek.verify(self.packet, **{**self.binding, "repository": "fixture://other"})
        self.assertTrue(any("innego repozytorium" in r for r in reasons))

    def test_base_branch_mismatch_is_refused(self) -> None:
        reasons = self.zgredek.verify(self.packet, **{**self.binding, "base_branch": "develop"})
        self.assertTrue(any("innego brancha" in r for r in reasons))

    def test_unapproved_packet_is_refused(self) -> None:
        unapproved = self._mutate(approvedBy="", approvedAt="")
        unapproved = ContextPacket.from_dict(
            {**unapproved.to_dict(), "sha256": canonical_sha256(unapproved.payload())}
        )
        reasons = self.zgredek.verify(unapproved, **self.binding)
        self.assertTrue(any("zatwierdzony" in r for r in reasons))

    def test_unsupported_schema_version_is_refused(self) -> None:
        stale = self._mutate(schemaVersion="zgredek-context-packet/0.0")
        reasons = self.zgredek.verify(stale, **self.binding)
        self.assertTrue(any("wersja packetu" in r for r in reasons))

    def test_missing_hash_is_refused(self) -> None:
        reasons = self.zgredek.verify(self._mutate(sha256=""), **self.binding)
        self.assertTrue(any("SHA-256" in r for r in reasons))

    def test_packet_without_locks_is_refused(self) -> None:
        empty = self._mutate(architectureLocks=[])
        empty = ContextPacket.from_dict(
            {**empty.to_dict(), "sha256": canonical_sha256(empty.payload())}
        )
        reasons = self.zgredek.verify(empty, **self.binding)
        self.assertTrue(any("locka" in r for r in reasons))


class ContextGateCase(unittest.TestCase):
    """repository-fact-load must refuse without a usable packet."""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.service = MissionService.local(self._dir.name)
        self.service.seed_registries()

    def tearDown(self) -> None:
        self.service.store.close()
        self._dir.cleanup()

    def _mission(self) -> str:
        return self.service.create_mission(
            {"title": "Ctx", "request": "Add a helper", "requiredTests": ["test_app.py"]}
        )["mission_id"]

    def test_packet_is_prepared_at_intake(self) -> None:
        report = self.service.context_packet(self._mission())
        self.assertTrue(report["available"])
        self.assertTrue(report["valid"])
        self.assertEqual(report["drift"]["status"], "PASS")
        self.assertEqual(len(report["packet"]["sha256"]), 64)

    def test_preparation_appends_an_apr_event(self) -> None:
        mission_id = self._mission()
        types = [e["event_type"] for e in self.service.events(mission_id)]
        self.assertIn("CONTEXT_PACKET_PREPARED", types)

    def test_valid_packet_lets_fact_load_run(self) -> None:
        mission_id = self._mission()
        self.service.start(mission_id, asynchronous=False)
        mission = self.service.store.get_mission(mission_id)
        node = next(n for n in mission["nodes"] if n["node_id"] == "repository-fact-load")
        self.assertEqual(node["state"], "PASSED")
        types = [e["event_type"] for e in self.service.events(mission_id)]
        self.assertIn("CONTEXT_PACKET_VALIDATED", types)

    def test_missing_packet_refuses_fact_load(self) -> None:
        mission_id = self._mission()
        self.service.store.conn.execute(
            "DELETE FROM control_context_packets WHERE mission_id = ?", (mission_id,)
        )
        self.service.store.conn.commit()

        self.service.start(mission_id, asynchronous=False)

        mission = self.service.store.get_mission(mission_id)
        self.assertEqual(mission["state"], "BLOCKED")
        node = next(n for n in mission["nodes"] if n["node_id"] == "repository-fact-load")
        self.assertEqual(node["state"], "BLOCKED")
        self.assertIn("brak context packetu", mission["failure_reason"])
        # The worker must never have been dispatched.
        self.assertEqual(node["attempt"], 0)

    def test_tampered_packet_refuses_fact_load(self) -> None:
        mission_id = self._mission()
        stored = self.service.store.context_packet(mission_id)
        stored["acceptedDecisions"] = [{"id": "D-999", "title": "injected", "statement": "x"}]
        self.service.store.save_context_packet(mission_id, stored)

        self.service.start(mission_id, asynchronous=False)

        mission = self.service.store.get_mission(mission_id)
        self.assertEqual(mission["state"], "BLOCKED")
        self.assertIn("SHA-256", mission["failure_reason"])

    def test_invalid_packet_never_reports_a_reassuring_drift_verdict(self) -> None:
        mission_id = self._mission()
        stored = self.service.store.context_packet(mission_id)
        stored["acceptedDecisions"] = [{"id": "D-999", "title": "injected", "statement": "x"}]
        self.service.store.save_context_packet(mission_id, stored)

        report = self.service.context_packet(mission_id)
        self.assertFalse(report["valid"])
        # The locks themselves are untouched, so a naive check would say PASS.
        self.assertEqual(report["drift"]["status"], "UNKNOWN")

    def test_mission_mismatched_packet_refuses_fact_load(self) -> None:
        mission_id = self._mission()
        stored = self.service.store.context_packet(mission_id)
        stored["missionId"] = "00000000-0000-4000-8000-000000000000"
        self.service.store.save_context_packet(mission_id, stored)

        self.service.start(mission_id, asynchronous=False)

        mission = self.service.store.get_mission(mission_id)
        self.assertEqual(mission["state"], "BLOCKED")
        self.assertIn("innej misji", mission["failure_reason"])

    def test_refusal_appends_an_apr_event_with_a_verdict(self) -> None:
        mission_id = self._mission()
        self.service.store.conn.execute(
            "DELETE FROM control_context_packets WHERE mission_id = ?", (mission_id,)
        )
        self.service.store.conn.commit()
        self.service.start(mission_id, asynchronous=False)

        events = [
            e for e in self.service.events(mission_id)
            if e["event_type"] == "CONTEXT_PACKET_VALIDATED"
        ]
        self.assertTrue(events)
        self.assertEqual(events[-1]["next_state"], "REFUSED")
        self.assertEqual(events[-1]["actor"], "zgredek-local-contract-v0.1")

    def test_context_events_keep_the_chain_verifiable(self) -> None:
        mission_id = self._mission()
        self.service.start(mission_id, asynchronous=False)
        ok, detail = self.service.store.verify_event_chain(mission_id)
        self.assertTrue(ok, detail)

    def test_refused_mission_can_recover_after_the_packet_is_restored(self) -> None:
        mission_id = self._mission()
        good = self.service.store.context_packet(mission_id)
        self.service.store.conn.execute(
            "DELETE FROM control_context_packets WHERE mission_id = ?", (mission_id,)
        )
        self.service.store.conn.commit()
        self.service.start(mission_id, asynchronous=False)
        self.assertEqual(self.service.store.get_mission(mission_id)["state"], "BLOCKED")

        # Zgredek re-approves; the mission resumes without losing its ledger.
        self.service.store.save_context_packet(mission_id, good)
        self.service.retry(mission_id, "repository-fact-load", "OSA", asynchronous=False)

        mission = self.service.store.get_mission(mission_id)
        node = next(n for n in mission["nodes"] if n["node_id"] == "repository-fact-load")
        self.assertEqual(node["state"], "PASSED")


class ContextPacketApiCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._dir = tempfile.TemporaryDirectory()
        cls.service = MissionService.local(cls._dir.name)
        cls.service.seed_registries()
        cls.server = create_server(cls.service, port=0, web_root=REPO_ROOT / "web")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.mission_id = cls.service.create_mission(
            {"title": "Api", "request": "Add a helper"}
        )["mission_id"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.service.store.close()
        cls._dir.cleanup()

    def test_endpoint_returns_the_packet_with_verdict_and_drift(self) -> None:
        with urlopen(f"{self.base}/api/context-packet/{self.mission_id}", timeout=10) as r:
            self.assertEqual(r.status, 200)
            payload = json.load(r)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["drift"]["status"], "PASS")
        packet = payload["packet"]
        self.assertEqual(packet["schemaVersion"], "zgredek-context-packet/0.1")
        self.assertEqual(packet["missionId"], self.mission_id)
        self.assertEqual(len(packet["sha256"]), 64)
        for key in (
            "repositoryInstructions",
            "architectureLocks",
            "acceptedDecisions",
            "ownership",
            "forbiddenDrift",
            "requiredEvidence",
        ):
            self.assertIn(key, packet)

    def test_unknown_mission_is_a_404(self) -> None:
        with self.assertRaises(Exception) as caught:
            urlopen(f"{self.base}/api/context-packet/00000000-0000-4000-8000-000000000000", timeout=10)
        self.assertEqual(getattr(caught.exception, "code", None), 404)

    def test_packet_response_carries_no_host_paths(self) -> None:
        with urlopen(f"{self.base}/api/context-packet/{self.mission_id}", timeout=10) as r:
            raw = r.read().decode("utf-8")
        for needle in ("/home/", "/root/", "/tmp/"):
            self.assertNotIn(needle, raw)


if __name__ == "__main__":
    unittest.main()
