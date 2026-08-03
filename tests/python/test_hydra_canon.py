"""Contract tests for the canonical Hydra control-plane surfaces.

Covers the registries, the durable queue and scheduler, budget enforcement,
worker-adapter refusal, and the completion gates that a mission must satisfy
before it may reach COMPLETED.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from hydra_control import adapters  # noqa: E402
from hydra_control.models import (  # noqa: E402
    BackendError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from hydra_control.scheduler import MissionScheduler  # noqa: E402
from hydra_control.server import create_server  # noqa: E402
from hydra_control.service import MissionService  # noqa: E402
from hydra_control.store import ControlPlaneStore  # noqa: E402


class StoreRegistryCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.store = ControlPlaneStore(self._dir.name)

    def tearDown(self) -> None:
        self.store.close()
        self._dir.cleanup()

    def test_schema_migrations_are_applied_additively(self) -> None:
        self.assertEqual(self.store.schema_versions(), [1, 2, 3])

    def test_project_and_repository_registry_roundtrip(self) -> None:
        self.store.upsert_project(key="ma", name="Michael Angelo", permission="GREEN")
        self.store.upsert_repository(
            project_key="ma", slug="demo", uri="fixture://demo", executable=True
        )
        repositories = self.store.repositories()
        self.assertEqual(len(repositories), 1)
        self.assertTrue(repositories[0]["executable"])
        self.assertEqual(repositories[0]["project_key"], "ma")

    def test_upsert_is_idempotent(self) -> None:
        for _ in range(3):
            self.store.upsert_project(key="ma", name="Michael Angelo")
        self.assertEqual(len(self.store.projects()), 1)

    def test_repository_requires_a_known_project(self) -> None:
        with self.assertRaises(NotFoundError):
            self.store.upsert_repository(project_key="ghost", slug="x", uri="fixture://x")

    def test_budget_enforces_its_limit(self) -> None:
        self.store.set_budget("global", 1.0)
        self.store.charge_budget("global", 0.75, reason="a")
        with self.assertRaises(ConflictError):
            self.store.charge_budget("global", 0.5, reason="b")
        # The refused charge must not have been recorded.
        self.assertAlmostEqual(self.store.budget("global")["spent_amount"], 0.75)
        self.assertEqual(len(self.store.budget_entries("global")), 1)

    def test_queue_leases_by_priority_then_age(self) -> None:
        self.store.enqueue("mission-low", priority=200)
        self.store.enqueue("mission-high", priority=1)
        leased = self.store.lease_next()
        self.assertEqual(leased["mission_id"], "mission-high")
        self.assertEqual(leased["status"], "LEASED")
        self.assertEqual(leased["attempts"], 1)

    def test_leased_entries_return_to_waiting_on_recovery(self) -> None:
        self.store.enqueue("mission-a")
        self.store.lease_next()
        self.assertEqual(self.store.queue_entry("mission-a")["status"], "LEASED")
        requeued = self.store.requeue_leased()
        self.assertEqual(requeued, ["mission-a"])
        self.assertEqual(self.store.queue_entry("mission-a")["status"], "WAITING")

    def test_empty_queue_leases_nothing(self) -> None:
        self.assertIsNone(self.store.lease_next())


class WorkerAdapterCase(unittest.TestCase):
    def test_every_declared_worker_reports_a_status(self) -> None:
        described = adapters.describe_workers()
        ids = {worker["workerId"] for worker in described}
        self.assertEqual(
            ids,
            {"deterministic-local", "codex", "openhands", "claude-worker", "generic-minion"},
        )
        for worker in described:
            self.assertIn(worker["availability"], {adapters.AVAILABLE, adapters.UNAVAILABLE})
            self.assertTrue(worker["reason"])

    def test_local_worker_is_available_and_auto_resolves_to_it(self) -> None:
        self.assertEqual(adapters.resolve_worker("AUTO"), "deterministic-local")

    def test_requesting_an_unavailable_worker_is_refused_not_substituted(self) -> None:
        with self.assertRaises(BackendError) as caught:
            adapters.resolve_worker("openhands")
        self.assertIn("UNAVAILABLE", str(caught.exception))

    def test_unknown_worker_is_rejected(self) -> None:
        with self.assertRaises(BackendError):
            adapters.resolve_worker("does-not-exist")

    def test_unavailable_backend_refuses_every_operation(self) -> None:
        backend = adapters.UnavailableBackend(adapters.REGISTRY_BY_ID["codex"])
        for call in (
            lambda: backend.create_session(None),
            lambda: backend.execute_task(None),
            lambda: backend.get_status("s"),
            lambda: backend.cancel("s"),
            lambda: backend.collect_artifacts("s"),
        ):
            with self.subTest(call=call), self.assertRaises(BackendError):
                call()

    def test_generic_minion_slot_is_never_available(self) -> None:
        availability, _ = adapters.REGISTRY_BY_ID["generic-minion"].status()
        self.assertEqual(availability, adapters.UNAVAILABLE)

    def test_a_failing_probe_degrades_to_unavailable(self) -> None:
        def boom() -> tuple[str, str]:
            raise RuntimeError("probe exploded")

        adapter = adapters.WorkerAdapter(
            worker_id="x", name="X", kind="test", capabilities=(), probe=boom
        )
        availability, reason = adapter.status()
        self.assertEqual(availability, adapters.UNAVAILABLE)
        self.assertIn("probe failed", reason)

    def test_service_probe_reads_the_environment(self) -> None:
        probe = adapters._probe_service("HYDRA_TEST_URL", "Test")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HYDRA_TEST_URL", None)
            self.assertEqual(probe()[0], adapters.UNAVAILABLE)
        with mock.patch.dict(os.environ, {"HYDRA_TEST_URL": "http://x"}):
            self.assertEqual(probe()[0], adapters.AVAILABLE)


class MissionIntakeCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.service = MissionService.local(self._dir.name)
        self.service.seed_registries()

    def tearDown(self) -> None:
        self.service.store.close()
        self._dir.cleanup()

    def test_canonical_intake_is_recorded_on_the_manifest(self) -> None:
        mission = self.service.create_mission(
            {
                "title": "Canon",
                "request": "Add a helper",
                "baseBranch": "main",
                "acceptanceCriteria": ["kryterium jeden"],
                "requiredTests": ["test_app.py"],
                "riskLevel": "HIGH",
                "budgetLimit": 2.5,
                "worker": "AUTO",
                "timeoutSeconds": 600,
                "blueprint": "standard-coding-mission",
            }
        )
        manifest = mission["manifest"]
        self.assertEqual(manifest["base_branch"], "main")
        self.assertEqual(manifest["acceptance_criteria"], ["kryterium jeden"])
        self.assertEqual(manifest["required_tests"], ["test_app.py"])
        self.assertEqual(manifest["budget_limit"], 2.5)
        self.assertEqual(manifest["timeout_seconds"], 600)
        self.assertEqual(mission["risk_level"], "HIGH")

    def test_risk_override_can_raise_but_never_lower(self) -> None:
        mission = self.service.create_mission(
            {
                "title": "Deploy",
                # The request text alone classifies as HIGH.
                "request": "deploy to production",
                "riskLevel": "LOW",
            }
        )
        self.assertEqual(mission["risk_level"], "HIGH")

    def test_creating_a_mission_enqueues_it(self) -> None:
        mission = self.service.create_mission({"title": "Q", "request": "Add a helper"})
        entry = self.service.store.queue_entry(mission["mission_id"])
        self.assertEqual(entry["status"], "WAITING")

    def test_unknown_fields_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.create_mission({"title": "x", "request": "y", "nope": 1})

    def test_unavailable_worker_fails_intake(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            self.service.create_mission(
                {"title": "x", "request": "y", "worker": "openhands"}
            )
        self.assertIn("UNAVAILABLE", str(caught.exception))

    def test_intake_bounds_are_enforced(self) -> None:
        cases = [
            {"timeoutSeconds": 5},
            {"timeoutSeconds": 99999},
            {"budgetLimit": -1},
            {"priority": 0},
            {"baseBranch": "../etc/passwd"},
            {"blueprint": "arbitrary"},
            {"riskLevel": "SEVERE"},
            {"acceptanceCriteria": "not-a-list"},
            {"requiredTests": [""]},
        ]
        for extra in cases:
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                self.service.create_mission({"title": "x", "request": "y", **extra})

    def test_registry_snapshot_reports_all_surfaces(self) -> None:
        snapshot = self.service.registry_snapshot()
        keys = {project["key"] for project in snapshot["projects"]}
        self.assertEqual(keys, {"michael-angelo", "genkit-lab", "windows-rtx", "web3-lab"})
        web3 = next(p for p in snapshot["projects"] if p["key"] == "web3-lab")
        self.assertEqual(web3["permission"], "RED")

    def test_seeding_twice_does_not_duplicate(self) -> None:
        self.service.seed_registries()
        self.assertEqual(len(self.service.registry_snapshot()["projects"]), 4)

    def test_model_routing_reports_unavailable_rather_than_substituting(self) -> None:
        route = self.service.route_model("coding")
        self.assertEqual(route["status"], "UNAVAILABLE")
        self.assertIsNone(route["selected"])
        self.assertIn("claude-opus-4", route["candidates"])

    def test_health_reports_the_local_zgredek_adapter(self) -> None:
        health = self.service.health()
        self.assertTrue(health["zgredek"]["connected"])
        self.assertEqual(health["zgredek"]["contextPacket"], "ACTIVE")
        self.assertEqual(health["zgredek"]["adapter"], "zgredek-local-contract-v0.1")
        # The separate Zgredek product is still not claimed.
        self.assertIn("UNKNOWN", health["zgredek"]["reason"])
        self.assertEqual(health["schemaVersions"], [1, 2, 3])


class SchedulerCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.service = MissionService.local(self._dir.name)
        self.service.seed_registries()
        self.scheduler = MissionScheduler(self.service, interval=0.05)

    def tearDown(self) -> None:
        self.scheduler.stop()
        self.service.store.close()
        self._dir.cleanup()

    def test_tick_dispatches_a_waiting_mission(self) -> None:
        mission = self.service.create_mission({"title": "Sched", "request": "Add a helper"})
        dispatched = self.scheduler.tick()
        self.assertEqual(dispatched, 1)
        self.service.wait(mission["mission_id"], timeout=60)
        state = self.service.store.get_mission(mission["mission_id"])["state"]
        # Without an architecture approval the pipeline parks on the gate.
        self.assertEqual(state, "AWAITING_ARCHITECTURE_APPROVAL")

    def test_tick_on_an_empty_queue_dispatches_nothing(self) -> None:
        self.assertEqual(self.scheduler.tick(), 0)

    def test_recover_requeues_orphaned_leases(self) -> None:
        self.service.create_mission({"title": "Orphan", "request": "Add a helper"})
        self.service.store.lease_next()
        self.assertEqual(len(self.scheduler.recover()), 1)

    def test_status_reports_the_pump_state(self) -> None:
        status = self.scheduler.status()
        self.assertFalse(status["running"])
        self.assertEqual(status["maxConcurrent"], 2)


class CompletionGateCase(unittest.TestCase):
    """A mission must not reach COMPLETED without full, commit-bound evidence."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._dir = tempfile.TemporaryDirectory()
        cls.service = MissionService.local(cls._dir.name)
        cls.service.seed_registries()
        cls.mission = cls.service.create_mission(
            {
                "title": "Gate",
                "request": "Add a deterministic helper",
                "acceptanceCriteria": ["deterministyczny wynik"],
                "requiredTests": ["test_app.py"],
            }
        )
        cls.mission_id = cls.mission["mission_id"]
        cls.service.start(cls.mission_id, asynchronous=False)
        cls.service.approve(cls.mission_id, gate="architecture", actor="OSA", asynchronous=False)
        cls.service.approve(cls.mission_id, gate="human", actor="OSA", asynchronous=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.service.store.close()
        cls._dir.cleanup()

    def test_mission_completed_through_validating(self) -> None:
        mission = self.service.store.get_mission(self.mission_id)
        self.assertEqual(mission["state"], "COMPLETED")
        node_states = {node["node_id"]: node["state"] for node in mission["nodes"]}
        for required in ("targeted-tests", "runtime-verification", "apr-evidence"):
            self.assertEqual(node_states[required], "PASSED")

    def test_evidence_bundle_carries_every_required_section(self) -> None:
        evidence = self.service.evidence(self.mission_id)
        self.assertTrue(evidence["valid"], evidence.get("invalidReasons"))
        bundle = evidence["bundle"]
        self.assertEqual(bundle["schemaVersion"], "1.1")
        self.assertTrue(bundle["changedFiles"])
        self.assertTrue(bundle["gitDiff"])
        self.assertTrue(bundle["rollbackPlan"]["verified"])
        self.assertEqual(bundle["rollbackPlan"]["baseCommit"], bundle["baseCommit"])
        self.assertTrue(all(c["status"] == "PASS" for c in bundle["acceptanceCriteria"]))
        self.assertTrue(all(t["status"] == "PASS" for t in bundle["requiredTests"]))

    def test_evidence_is_invalidated_when_the_rollback_plan_is_missing(self) -> None:
        bundle = json.loads(json.dumps(self.service.store.evidence(self.mission_id)))
        bundle.pop("rollbackPlan")
        self.service.store.save_evidence(self.mission_id, bundle)
        try:
            evidence = self.service.evidence(self.mission_id)
            self.assertFalse(evidence["valid"])
            self.assertIn("no verified rollback plan", evidence["invalidReasons"])
        finally:
            self.service.store.save_evidence(
                self.mission_id, self.service._build_evidence(
                    self.mission_id,
                    {
                        "changedFiles": ["app.py"],
                        "currentCommit": self.service.store.get_mission(self.mission_id)["result_commit"],
                    },
                )
            )

    def test_evidence_is_invalidated_when_no_diff_was_recorded(self) -> None:
        original = self.service.store.evidence(self.mission_id)
        tampered = json.loads(json.dumps(original))
        tampered["changedFiles"] = []
        self.service.store.save_evidence(self.mission_id, tampered)
        try:
            evidence = self.service.evidence(self.mission_id)
            self.assertFalse(evidence["valid"])
            self.assertIn("no git diff recorded for this mission", evidence["invalidReasons"])
        finally:
            self.service.store.save_evidence(self.mission_id, original)

    def test_rollback_manifest_and_pull_request_are_available(self) -> None:
        rollback = self.service.rollback_manifest(self.mission_id)
        self.assertTrue(rollback["available"])
        self.assertTrue(rollback["rollbackPlan"]["steps"])

        pr = self.service.pull_request(self.mission_id)
        self.assertTrue(pr["available"])
        # No branch is pushed and no GitHub API is called.
        self.assertEqual(pr["status"], "LOCAL_DESCRIPTOR")
        self.assertEqual(pr["productionMerge"], "RED")

    def test_budget_ledger_recorded_measured_compute(self) -> None:
        entries = self.service.store.budget_entries("global")
        self.assertTrue(entries)
        self.assertTrue(all(entry["amount"] > 0 for entry in entries))
        self.assertTrue(any(entry["reason"].startswith("compute:") for entry in entries))

    def test_sandbox_is_reported_per_mission(self) -> None:
        sandboxes = self.service.sandboxes()
        entry = next(s for s in sandboxes if s["missionId"] == self.mission_id)
        self.assertTrue(entry["isolated"])
        self.assertFalse(entry["network"])
        self.assertFalse(entry["productionCredentials"])


class CanonicalApiCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._dir = tempfile.TemporaryDirectory()
        cls.service = MissionService.local(cls._dir.name)
        cls.service.seed_registries()
        cls.scheduler = MissionScheduler(cls.service, interval=0.05)
        cls.server = create_server(
            cls.service, port=0, web_root=REPO_ROOT / "web", scheduler=cls.scheduler
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.scheduler.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.service.store.close()
        cls._dir.cleanup()

    def get(self, path: str):
        with urlopen(f"{self.base}{path}", timeout=10) as response:
            return response.status, json.load(response)

    def test_every_canonical_endpoint_answers(self) -> None:
        for path, key in (
            ("/api/health/full", "status"),
            ("/api/projects", "projects"),
            ("/api/repositories", "repositories"),
            ("/api/workers", "workers"),
            ("/api/models", "models"),
            ("/api/budgets", "budgets"),
            ("/api/queue", "queue"),
            ("/api/sandboxes", "sandboxes"),
            ("/api/registry", "projects"),
            ("/api/approvals", "approvals"),
        ):
            with self.subTest(path=path):
                status, payload = self.get(path)
                self.assertEqual(status, 200)
                self.assertIn(key, payload)

    def test_queue_endpoint_exposes_scheduler_state(self) -> None:
        _, payload = self.get("/api/queue")
        self.assertIn("maxConcurrent", payload["scheduler"])

    def test_workers_endpoint_reports_unavailable_workers_honestly(self) -> None:
        _, payload = self.get("/api/workers")
        unavailable = [w for w in payload["workers"] if w["availability"] == "UNAVAILABLE"]
        self.assertGreaterEqual(len(unavailable), 3)
        for worker in unavailable:
            self.assertTrue(worker["reason"])

    def test_mission_intake_rejects_a_non_fixture_repository(self) -> None:
        payload = json.dumps(
            {"title": "Escape", "request": "x", "repository": "/etc/passwd"}
        ).encode("utf-8")
        request = Request(
            f"{self.base}/api/missions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(Exception) as caught:
            urlopen(request, timeout=10)
        self.assertEqual(getattr(caught.exception, "code", None), 422)


if __name__ == "__main__":
    unittest.main()
