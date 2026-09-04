"""Contract tests for the Hydra -> OSA Execution Force RuntimeV2 adapter."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from hydra_control.models import (  # noqa: E402
    BackendError,
    CreateSessionInput,
    ExecuteTaskInput,
)
from hydra_control.osa_execution_force import (  # noqa: E402
    OsaExecutionForceBackend,
    RuntimeV2HttpTransport,
)
from hydra_control.service import MissionService  # noqa: E402
from hydra_control.store import ControlPlaneStore  # noqa: E402


BASE_SHA = "a" * 40
RESULT_SHA = "b" * 40
PACKET_SHA = "c" * 64
RUNTIME_ID = "runtime-mission-1"
EXECUTION_ID = "runtime-execution-1"


class FakeTransport:
    def __init__(self, snapshot: dict) -> None:
        self.snapshot = snapshot
        self.calls: list[tuple[str, str, dict | None, str]] = []

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        correlation_id: str = "",
    ) -> dict:
        self.calls.append((method, path, payload, correlation_id))
        if path == "/health":
            return {"status": "ok"}
        return self.snapshot


class SequencedTransport(FakeTransport):
    def __init__(self, snapshots: list[dict]) -> None:
        super().__init__(snapshots[-1])
        self.snapshots = iter(snapshots)

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        correlation_id: str = "",
    ) -> dict:
        self.calls.append((method, path, payload, correlation_id))
        if path == "/health":
            return {"status": "ok"}
        return next(self.snapshots)


def _event(state: str = "COMPLETED") -> dict:
    body = {
        "mission_id": RUNTIME_ID,
        "execution_id": EXECUTION_ID,
        "sequence": 1,
        "event_type": "MISSION_COMPLETED",
        "state": state,
        "payload": {"outcome": state},
        "previous_hash": "0" * 64,
        "created_at": "2026-09-02T00:00:00+00:00",
    }
    return {
        **body,
        "created_at": "2026-09-02T00:00:00Z",
        "event_hash": hashlib.sha256(
            json.dumps(
                body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }


def _completed_snapshot(*, authority: str = "MECHANICALLY_VERIFIED") -> dict:
    return {
        "state": "COMPLETED",
        "mission_version": 3,
        "resolution": {
            "selected_starting_skills": ["backend.platform-engineering"],
            "routing_action": "INVOKE",
            "abstain": False,
        },
        "events": [_event()],
        "evidence": [
            {
                "evidence_id": "evidence-diff",
                "mission_id": RUNTIME_ID,
                "execution_id": EXECUTION_ID,
                "fact_key": "backend.platform-engineering.host_action.git_diff_scope",
                "authority": authority,
                "artifact": "inline://git-diff-scope",
                "artifact_sha256": "d" * 64,
                "command": "git diff --name-only aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa..HEAD",
                "exit_code": 0,
                "executor_identity": "fixture-worker",
                "verification_details": {
                    "output": {
                        "passed": True,
                        "claim_matches_reality": True,
                        "scope_confined": True,
                        "actual_changed_files": ["src/app.py"],
                    }
                },
            },
            {
                "evidence_id": "evidence-tests",
                "mission_id": RUNTIME_ID,
                "execution_id": EXECUTION_ID,
                "fact_key": "backend.platform-engineering.host_action.tests_pass",
                "authority": authority,
                "artifact": "inline://tests",
                "artifact_sha256": "e" * 64,
                "command": "pytest tests/test_app.py -q",
                "exit_code": 0,
                "executor_identity": "fixture-worker",
                "verification_details": {"output": {"status": "PASS"}},
            },
        ],
        "completion_checks": {"tests": True, "git_diff": True},
        "context": {
            "mission_id": RUNTIME_ID,
            "execution_id": EXECUTION_ID,
            "host_action_ledger": {
                "host-action-1": {
                    "host_identity": "fixture-worker",
                    "source_commit_before": BASE_SHA,
                    "source_commit_after": RESULT_SHA,
                    "commands_run": [
                        "pytest tests/test_app.py -q"
                    ],
                }
            },
            "required_checks": {"tests": "PASS", "git_diff": "PASS"},
        },
    }


def _blocked_snapshot() -> dict:
    return {
        "state": "HOST_ACTION_REQUIRED",
        "mission_version": 1,
        "events": [],
        "evidence": [],
        "completion_checks": {},
        "context": {
            "mission_id": RUNTIME_ID,
            "execution_id": EXECUTION_ID,
            "pending_host_action": {
                "action_id": "host-action-1",
                "operation": "repository_change",
            },
        },
    }


def _manifest(mission_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "mission_id": mission_id,
        "title": "Bounded fixture change",
        "request": "Change src/app.py and run its test",
        "repository": "github://HazEOskA/osa-agent-e2e-fixture",
        "branch": f"hydra/mission-{mission_id[:8]}",
        "risk_level": "MEDIUM",
        "execution_backend": "osa-execution-force",
        "acceptance_criteria": ["helper returns the expected value"],
        "base_commit": BASE_SHA,
        "allowed_scope": ["src/app.py"],
        "test_command": ["pytest", "tests/test_app.py", "-q"],
        "timeout_seconds": 900,
        "budget_limit": 2.0,
        "environment": "development",
        "hydra_context": {
            "packetSha256": PACKET_SHA,
            "status": "APPROVED",
            "approvedBy": "OSA",
            "approvedPacketSha256": PACKET_SHA,
        },
    }


class OsaExecutionForceAdapterCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.mission_id = str(uuid.uuid4())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _backend(self, snapshot: dict) -> tuple[OsaExecutionForceBackend, FakeTransport]:
        transport = FakeTransport(snapshot)
        backend = OsaExecutionForceBackend(transport, self.tmp.name)
        backend.create_session(
            CreateSessionInput(
                mission_id=self.mission_id,
                repository="github://HazEOskA/osa-agent-e2e-fixture",
                branch=f"hydra/mission-{self.mission_id[:8]}",
            )
        )
        return backend, transport

    def _input(self) -> ExecuteTaskInput:
        return ExecuteTaskInput(
            session_id=self.mission_id,
            mission_id=self.mission_id,
            node_id="agent-execution",
            attempt=1,
            manifest=_manifest(self.mission_id),
            base_commit=BASE_SHA,
        )

    def test_environment_configuration_refuses_missing_credentials(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HYDRA_OSA_EXECUTION_FORCE_URL", None)
            os.environ.pop("OSA_ACTIONS_API_KEY", None)
            with self.assertRaises(BackendError) as caught:
                OsaExecutionForceBackend.from_environment(self.tmp.name)
        self.assertIn("UNAVAILABLE", str(caught.exception))

    @mock.patch.dict(
        os.environ,
        {"HYDRA_OSA_EXECUTION_FORCE_URL": "https://runtime.example"},
        clear=False,
    )
    def test_missing_key_allows_state_open_but_refuses_dispatch(self) -> None:
        os.environ.pop("OSA_ACTIONS_API_KEY", None)
        backend = OsaExecutionForceBackend.from_environment(self.tmp.name)
        self.assertIsInstance(backend.transport, RuntimeV2HttpTransport)
        self.assertEqual(backend.availability()[0], "UNAVAILABLE")
        with self.assertRaisesRegex(BackendError, "execution is UNAVAILABLE"):
            backend.create_session(
                CreateSessionInput(
                    mission_id=self.mission_id,
                    repository="github://HazEOskA/osa-agent-e2e-fixture",
                    branch="main",
                )
            )

    def test_run_uses_the_official_v2_schema_and_preserves_correlation(self) -> None:
        backend, transport = self._backend(_blocked_snapshot())
        result = backend.execute_task(self._input())
        self.assertFalse(result.success)
        self.assertEqual(result.metadata["hydraDisposition"], "BLOCKED")
        self.assertEqual(result.metadata["runtimeMissionId"], RUNTIME_ID)
        run = next(call for call in transport.calls if call[1] == "/api/v2/missions/run")
        payload = run[2]
        self.assertEqual(run[3], self.mission_id)
        self.assertEqual(
            set(payload),
            {"task", "goal", "context", "environment", "requested_operation", "approvals"},
        )
        self.assertEqual(payload["context"]["commit_sha"], BASE_SHA)
        self.assertEqual(
            payload["context"]["repository"],
            "HazEOskA/osa-agent-e2e-fixture",
        )
        self.assertEqual(payload["context"]["budget"]["maximum_cost"], 2.0)
        self.assertEqual(
            payload["context"]["known_facts"]["hydra.mission_id"], self.mission_id
        )
        self.assertEqual(
            payload["context"]["known_facts"][
                "backend.platform-engineering.allowed_scope"
            ],
            ["src/app.py"],
        )
        self.assertEqual(result.metadata["hostActionRequest"]["action_id"], "host-action-1")
        worker = next(
            call
            for call in transport.calls
            if call[1] == f"/api/v2/missions/{RUNTIME_ID}/execute-host-action"
        )
        self.assertEqual(
            worker[2],
            {
                "expected_action_id": "host-action-1",
                "expected_mission_version": 1,
                "expected_execution_id": EXECUTION_ID,
            },
        )
        self.assertEqual(worker[3], self.mission_id)

    def test_host_worker_boundary_can_return_verified_completion(self) -> None:
        transport = SequencedTransport([_blocked_snapshot(), _completed_snapshot()])
        backend = OsaExecutionForceBackend(transport, self.tmp.name)
        backend.create_session(
            CreateSessionInput(
                mission_id=self.mission_id,
                repository="github://HazEOskA/osa-agent-e2e-fixture",
                branch=f"hydra/mission-{self.mission_id[:8]}",
            )
        )

        result = backend.execute_task(self._input())

        self.assertTrue(result.success)
        self.assertEqual(result.metadata["runtimeMissionId"], RUNTIME_ID)
        self.assertEqual(result.metadata["baseCommit"], BASE_SHA)
        self.assertEqual(result.metadata["resultCommit"], RESULT_SHA)
        paths = [path for _, path, _, _ in transport.calls]
        self.assertEqual(paths[1:], [
            "/api/v2/missions/run",
            f"/api/v2/missions/{RUNTIME_ID}/execute-host-action",
        ])

    def test_host_worker_boundary_refuses_incomplete_identity(self) -> None:
        snapshot = _blocked_snapshot()
        snapshot["mission_version"] = True
        backend, _ = self._backend(snapshot)
        result = backend.execute_task(self._input())
        self.assertFalse(result.success)
        self.assertIn("identity is incomplete", result.metadata["detail"])

    def test_host_worker_boundary_refuses_missing_action(self) -> None:
        snapshot = _blocked_snapshot()
        snapshot["context"]["pending_host_action"] = None
        backend, _ = self._backend(snapshot)
        result = backend.execute_task(self._input())
        self.assertFalse(result.success)
        self.assertIn("no bound action_id", result.metadata["detail"])

    def test_host_worker_boundary_refuses_correlation_drift(self) -> None:
        drifted = _completed_snapshot()
        drifted["context"] = dict(drifted["context"], mission_id="runtime-drift")
        transport = SequencedTransport([_blocked_snapshot(), drifted])
        backend = OsaExecutionForceBackend(transport, self.tmp.name)
        backend.create_session(
            CreateSessionInput(
                mission_id=self.mission_id,
                repository="github://HazEOskA/osa-agent-e2e-fixture",
                branch="main",
            )
        )
        result = backend.execute_task(self._input())
        self.assertFalse(result.success)
        self.assertIn("correlation changed", result.metadata["detail"])

    def test_repository_translation_rejects_invalid_github_identifier(self) -> None:
        with self.assertRaisesRegex(BackendError, "invalid github"):
            OsaExecutionForceBackend._runtime_repository("github://owner/repo/extra")
        self.assertEqual(
            OsaExecutionForceBackend._runtime_repository("https://github.com/owner/repo"),
            "https://github.com/owner/repo",
        )

    def test_claimed_evidence_cannot_complete(self) -> None:
        backend, _ = self._backend(_completed_snapshot(authority="CLAIMED"))
        result = backend.execute_task(self._input())
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "RUNTIME_V2_VERIFICATION_FAILED")
        self.assertIn("mechanical evidence", result.metadata["detail"])

    def test_completed_requires_and_returns_mechanical_proof(self) -> None:
        backend, _ = self._backend(_completed_snapshot())
        result = backend.execute_task(self._input())
        self.assertTrue(result.success)
        self.assertEqual(result.metadata["baseCommit"], BASE_SHA)
        self.assertEqual(result.metadata["resultCommit"], RESULT_SHA)
        self.assertEqual(result.metadata["changedFiles"], ["src/app.py"])
        self.assertEqual(
            result.metadata["resolvedSkills"], ["backend.platform-engineering"]
        )
        self.assertTrue(result.metadata["eventChainVerified"])
        self.assertEqual(result.commands[0].exit_code, 0)
        self.assertEqual(
            result.metadata["mechanicalEvidenceIds"],
            ["evidence-diff", "evidence-tests"],
        )

    def test_tampered_runtime_event_chain_is_refused(self) -> None:
        snapshot = _completed_snapshot()
        snapshot["events"][0]["event_hash"] = "0" * 64
        backend, _ = self._backend(snapshot)
        result = backend.execute_task(self._input())
        self.assertFalse(result.success)
        self.assertIn("event hash mismatch", result.metadata["detail"])

    def test_unknown_required_check_is_refused(self) -> None:
        snapshot = _completed_snapshot()
        snapshot["completion_checks"]["security"] = False
        backend, _ = self._backend(snapshot)
        result = backend.execute_task(self._input())
        self.assertFalse(result.success)
        self.assertIn("failed or UNKNOWN required check", result.metadata["detail"])

    def test_cancel_is_explicitly_unsupported_not_faked(self) -> None:
        backend, _ = self._backend(_blocked_snapshot())
        with self.assertRaises(BackendError) as caught:
            backend.cancel(self.mission_id)
        self.assertIn("UNSUPPORTED", str(caught.exception))

    def test_runtime_correlation_survives_adapter_reconstruction(self) -> None:
        backend, transport = self._backend(_blocked_snapshot())
        backend.execute_task(self._input())
        recovered = OsaExecutionForceBackend(transport, self.tmp.name)
        recovered.create_session(
            CreateSessionInput(
                mission_id=self.mission_id,
                repository="github://HazEOskA/osa-agent-e2e-fixture",
                branch=f"hydra/mission-{self.mission_id[:8]}",
            )
        )
        recovered.execute_task(self._input())
        paths = [path for _, path, _, _ in transport.calls]
        self.assertEqual(paths.count("/api/v2/missions/run"), 1)
        self.assertIn(f"/api/v2/missions/{RUNTIME_ID}", paths)


class OsaExecutionForceServiceCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ControlPlaneStore(self.tmp.name)
        self.transport = FakeTransport(_blocked_snapshot())
        self.backend = OsaExecutionForceBackend(
            self.transport, self.store.artifact_root
        )
        self.service = MissionService(self.store, self.backend)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    @mock.patch.dict(
        os.environ,
        {
            "HYDRA_OSA_EXECUTION_FORCE_URL": "https://runtime.example",
            "OSA_ACTIONS_API_KEY": "test-token",
        },
    )
    def test_host_action_request_maps_to_hydra_blocked_without_local_fallback(self) -> None:
        mission = self.service.create_mission(
            {
                "title": "Fixture change",
                "request": "Change src/app.py",
                "repository": "github://HazEOskA/osa-agent-e2e-fixture",
                "baseCommit": BASE_SHA,
                "allowedScope": ["src/app.py"],
                "testCommand": ["pytest", "tests/test_app.py", "-q"],
                "backend": "osa-execution-force",
                "worker": "AUTO",
            }
        )
        self.assertEqual(mission["backend"], "osa-execution-force")
        self.assertEqual(mission["base_commit"], BASE_SHA)
        self.assertNotIn(
            "sandbox-provisioning",
            {node["node_id"] for node in mission["nodes"]},
        )
        packet = self.service.context_packet(mission["mission_id"])["packet"]
        self.service.approve_context_packet(
            mission["mission_id"], actor="OSA", packet_sha256=packet["sha256"]
        )
        paused = self.service.start(
            mission["mission_id"], actor="OSA", asynchronous=False
        )
        self.assertEqual(paused["state"], "AWAITING_ARCHITECTURE_APPROVAL")
        result = self.service.approve(
            mission["mission_id"],
            gate="architecture",
            actor="OSA",
            asynchronous=False,
        )["mission"]
        self.assertEqual(result["state"], "BLOCKED")
        agent = next(node for node in result["nodes"] if node["node_id"] == "agent-execution")
        self.assertEqual(agent["state"], "BLOCKED")
        self.assertNotEqual(result["state"], "COMPLETED")
        run_calls = [call for call in self.transport.calls if call[1] == "/api/v2/missions/run"]
        self.assertEqual(len(run_calls), 1)

    @mock.patch.dict(
        os.environ,
        {
            "HYDRA_OSA_EXECUTION_FORCE_URL": "https://runtime.example",
            "OSA_ACTIONS_API_KEY": "test-token",
        },
    )
    def test_verified_runtime_result_can_reach_hydra_completion_gates(self) -> None:
        self.transport.snapshot = _completed_snapshot()
        mission = self.service.create_mission(
            {
                "title": "Fixture change",
                "request": "Change src/app.py",
                "repository": "github://HazEOskA/osa-agent-e2e-fixture",
                "baseCommit": BASE_SHA,
                "allowedScope": ["src/app.py"],
                "testCommand": ["pytest", "tests/test_app.py", "-q"],
                "backend": "osa-execution-force",
                "acceptanceCriteria": ["helper returns the expected value"],
                "requiredTests": ["tests/test_app.py"],
            }
        )
        packet = self.service.context_packet(mission["mission_id"])["packet"]
        self.service.approve_context_packet(
            mission["mission_id"], actor="OSA", packet_sha256=packet["sha256"]
        )
        self.service.start(mission["mission_id"], actor="OSA", asynchronous=False)
        after_architecture = self.service.approve(
            mission["mission_id"],
            gate="architecture",
            actor="OSA",
            asynchronous=False,
        )["mission"]
        self.assertEqual(after_architecture["state"], "AWAITING_HUMAN_APPROVAL")
        completed = self.service.approve(
            mission["mission_id"],
            gate="human",
            actor="OSA",
            asynchronous=False,
        )["mission"]
        self.assertEqual(completed["state"], "COMPLETED")
        evidence = self.service.evidence(mission["mission_id"])
        self.assertTrue(evidence["valid"])
        self.assertEqual(evidence["bundle"]["runtimeV2MissionId"], RUNTIME_ID)
        self.assertEqual(evidence["bundle"]["runtimeV2ExecutionId"], EXECUTION_ID)
        self.assertEqual(evidence["bundle"]["executionWorker"], "fixture-worker")

    @mock.patch.dict(os.environ, {}, clear=False)
    def test_explicit_unavailable_worker_is_rejected_at_intake(self) -> None:
        os.environ.pop("HYDRA_OSA_EXECUTION_FORCE_URL", None)
        os.environ.pop("OSA_ACTIONS_API_KEY", None)
        with self.assertRaisesRegex(Exception, "UNAVAILABLE"):
            self.service.create_mission(
                {
                    "title": "Fixture change",
                    "request": "Change src/app.py",
                    "repository": "github://HazEOskA/osa-agent-e2e-fixture",
                    "baseCommit": BASE_SHA,
                    "allowedScope": ["src/app.py"],
                    "testCommand": ["pytest"],
                    "backend": "osa-execution-force",
                    "worker": "osa-execution-force",
                }
            )

    @mock.patch.dict(
        os.environ,
        {
            "HYDRA_EXECUTION_BACKEND": "osa-execution-force",
            "HYDRA_OSA_EXECUTION_FORCE_URL": "https://runtime.example",
            "OSA_ACTIONS_API_KEY": "test-token",
        },
        clear=False,
    )
    def test_context_approval_persists_without_runtime_key(self) -> None:
        mission = self.service.create_mission(
            {
                "title": "Fixture change",
                "request": "Change src/app.py",
                "repository": "github://HazEOskA/osa-agent-e2e-fixture",
                "baseCommit": BASE_SHA,
                "allowedScope": ["src/app.py"],
                "testCommand": ["pytest", "-q"],
                "backend": "osa-execution-force",
            }
        )
        packet = self.service.context_packet(mission["mission_id"])["packet"]
        os.environ.pop("OSA_ACTIONS_API_KEY", None)

        reopened = MissionService.configured(self.tmp.name)
        try:
            approval = reopened.approve_context_packet(
                mission["mission_id"],
                actor="OSA",
                packet_sha256=packet["sha256"],
            )
            self.assertTrue(approval["approved"])
            self.assertTrue(
                reopened.context_packet(mission["mission_id"])["approval"]["approved"]
            )
            with self.assertRaisesRegex(BackendError, "execution is UNAVAILABLE"):
                reopened.start(mission["mission_id"], actor="OSA", asynchronous=False)
        finally:
            reopened.store.close()


if __name__ == "__main__":
    unittest.main()
