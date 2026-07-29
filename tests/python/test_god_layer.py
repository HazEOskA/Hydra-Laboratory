"""Offline proof for the Hermes God-Layer control plane.

No network, no sandbox, no host: every guarantee below is exercised against
temporary stores so the suite runs in CI and on a workstation.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from hermes import redact as redact_module  # noqa: E402
from hermes import soul as soul_module  # noqa: E402
from hermes.ledger import ChainError, Ledger, TransitionError, allowed  # noqa: E402
from hermes.permissions import (  # noqa: E402
    PermissionClassifier,
    PermissionLevel,
    ToolDisabledError,
    UnknownToolError,
    dispatch_plan,
    escalate,
    idempotency_key,
)
from hermes.queue import DuplicateTaskError, TaskQueue, backoff_seconds  # noqa: E402
from hermes.revenue import (  # noqa: E402
    Lead,
    RevenueLedger,
    generate_audit,
    generate_outreach_draft,
    score_lead,
)
from hermes.router import HealthTable, ModelRouter, ProviderHealth  # noqa: E402


class TempStoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)


# -- permission engine ----------------------------------------------------


class TestPermissions(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = PermissionClassifier()

    def test_green_action_dispatches_without_approval(self) -> None:
        decision = self.classifier.classify("git", "commit")
        self.assertIs(decision.permission, PermissionLevel.GREEN)
        self.assertFalse(decision.requires_approval)
        self.assertFalse(decision.audit_required)
        self.assertEqual(dispatch_plan(decision), "DISPATCH")

    def test_routine_diagnostics_stay_green(self) -> None:
        """SOUL.md forbids turning routine work into approval gates."""
        for tool, action in [
            ("shell", "inspect"),
            ("shell", "test"),
            ("docker", "ps"),
            ("docker", "logs"),
            ("database", "read"),
            ("filesystem", "backup"),
            ("browser", "smoke_test"),
            ("research", "search"),
            ("email", "draft"),
            ("git", "diff"),
        ]:
            with self.subTest(tool=tool, action=action):
                self.assertIs(
                    self.classifier.classify(tool, action).permission, PermissionLevel.GREEN
                )

    def test_yellow_action_audits_and_dispatches(self) -> None:
        decision = self.classifier.classify("git", "push", rollback_available=True)
        self.assertIs(decision.permission, PermissionLevel.YELLOW)
        self.assertFalse(decision.requires_approval)
        self.assertTrue(decision.audit_required)
        self.assertEqual(dispatch_plan(decision), "CHECKPOINT_AUDIT_DISPATCH")

    def test_yellow_without_rollback_is_flagged_in_reason(self) -> None:
        decision = self.classifier.classify("docker", "restart")
        self.assertIs(decision.permission, PermissionLevel.YELLOW)
        self.assertIn("rollback", decision.reason)

    def test_red_action_requires_approval(self) -> None:
        decision = self.classifier.classify("email", "send")
        self.assertIs(decision.permission, PermissionLevel.RED)
        self.assertTrue(decision.requires_approval)
        self.assertEqual(dispatch_plan(decision), "REQUEST_APPROVAL_BLOCK_TASK")

    def test_split_verb_tools_resolve_both_levels(self) -> None:
        self.assertIs(
            self.classifier.classify("deployment", "preview").permission, PermissionLevel.YELLOW
        )
        self.assertIs(
            self.classifier.classify("deployment", "production").permission, PermissionLevel.RED
        )
        self.assertIs(
            self.classifier.classify("crypto", "analysis").permission, PermissionLevel.GREEN
        )
        self.assertIs(
            self.classifier.classify("crypto", "transaction").permission, PermissionLevel.RED
        )

    def test_red_pattern_escalates_a_green_tool(self) -> None:
        """A GREEN tool must not be a smuggling route for a RED action."""
        decision = self.classifier.classify(
            "shell", "run", {"cmd": "drop production database"}
        )
        self.assertIs(decision.permission, PermissionLevel.RED)
        self.assertEqual(decision.matched_rule, "red.destructive_delete")

    def test_red_patterns_cover_the_soul_list(self) -> None:
        cases = [
            ("research", "search", {"intent": "send outreach to external prospect"}),
            ("filesystem", "write", {"intent": "publish public social post"}),
            ("shell", "run", {"cmd": "wire transfer_funds to account"}),
            ("shell", "run", {"cmd": "rotate secret credential"}),
            ("shell", "run", {"cmd": "disable backup schedule"}),
            ("shell", "run", {"cmd": "bypass authentication"}),
            ("shell", "run", {"cmd": "impersonate the client company"}),
        ]
        for tool, action, payload in cases:
            with self.subTest(payload=payload):
                self.assertIs(
                    self.classifier.classify(tool, action, payload).permission,
                    PermissionLevel.RED,
                )

    def test_disabled_tool_is_refused_not_downgraded(self) -> None:
        with self.assertRaises(ToolDisabledError):
            self.classifier.classify("payments", "charge")

    def test_unknown_tool_is_refused(self) -> None:
        with self.assertRaises(UnknownToolError):
            self.classifier.classify("nonexistent", "do")

    def test_unclassified_action_on_split_tool_defaults_red(self) -> None:
        decision = self.classifier.classify("deployment", "wildcard_action")
        self.assertIs(decision.permission, PermissionLevel.RED)

    def test_idempotency_key_is_stable_and_payload_sensitive(self) -> None:
        first = idempotency_key("git", "push", {"branch": "main"})
        second = idempotency_key("git", "push", {"branch": "main"})
        third = idempotency_key("git", "push", {"branch": "other"})
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

    def test_escalate_takes_the_strictest(self) -> None:
        self.assertIs(
            escalate(PermissionLevel.GREEN, PermissionLevel.RED, PermissionLevel.YELLOW),
            PermissionLevel.RED,
        )

    def test_every_enabled_tool_declares_a_health_check(self) -> None:
        for tool in self.classifier.enabled_tools():
            with self.subTest(tool=tool):
                self.assertTrue(self.classifier.tool_spec(tool).get("health_check"))


# -- constitution ---------------------------------------------------------


class TestSoul(unittest.TestCase):
    def test_constitution_loads_and_verifies(self) -> None:
        soul = soul_module.load()
        self.assertTrue(soul.loaded)
        ok, missing = soul_module.verify(soul)
        self.assertTrue(ok, f"missing sections: {missing}")
        self.assertEqual(len(soul.sha256), 64)

    def test_preamble_always_carries_the_permission_model(self) -> None:
        soul = soul_module.load()
        for budget in (6000, 2500, 1200):
            with self.subTest(budget=budget):
                text = soul_module.preamble(soul, max_chars=budget)
                self.assertIn("Permission Model", text)
                self.assertIn(soul.sha256[:16], text)

    def test_missing_constitution_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            soul_module.load("/nonexistent/SOUL.md")

    def test_tampered_constitution_fails_structure_check(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as handle:
            handle.write("# SOUL.md\n\n## Identity\n\nI am Hermes.\n")
            path = handle.name
        self.addCleanup(os.unlink, path)
        ok, missing = soul_module.verify(soul_module.load(path))
        self.assertFalse(ok)
        self.assertIn("### RED — OSA Approval Required", missing)


# -- mission state machine and ledger -------------------------------------


class TestLedger(TempStoreCase):
    def setUp(self) -> None:
        super().setUp()
        self.ledger = Ledger(self.tmp / "missions.db")
        self.addCleanup(self.ledger.close)

    def _advance_to_running(self, mission: str = "m-1") -> str:
        self.ledger.create_mission(mission, "test mission")
        for state in ("INTAKE_VALIDATED", "PLANNED", "QUEUED", "DISPATCHED", "RUNNING"):
            self.ledger.transition(mission, state, reason=f"to {state}")
        return mission

    def test_running_cannot_jump_to_completed(self) -> None:
        mission = self._advance_to_running()
        self.assertFalse(allowed("RUNNING", "COMPLETED"))
        with self.assertRaises(TransitionError):
            self.ledger.transition(mission, "COMPLETED", evidence_refs=["evidence://x"])

    def test_completion_requires_validation_and_evidence(self) -> None:
        mission = self._advance_to_running()
        self.ledger.transition(mission, "VALIDATING", reason="validating")
        with self.assertRaises(TransitionError):
            self.ledger.transition(mission, "COMPLETED", reason="no evidence")
        self.ledger.transition(
            mission, "COMPLETED", reason="validated", evidence_refs=["evidence://run/1"]
        )
        self.assertEqual(self.ledger.mission_state(mission), "COMPLETED")

    def test_invalid_transition_is_refused(self) -> None:
        self.ledger.create_mission("m-2")
        with self.assertRaises(TransitionError):
            self.ledger.transition("m-2", "RUNNING")

    def test_chain_verifies_and_detects_tampering(self) -> None:
        mission = self._advance_to_running("m-3")
        self.ledger.transition(mission, "VALIDATING")
        self.ledger.transition(mission, "COMPLETED", evidence_refs=["evidence://ok"])
        ok, detail = self.ledger.verify_chain()
        self.assertTrue(ok, detail)

        # Tampering must be detected even if it bypasses the application layer.
        self.ledger.close()
        raw = sqlite3.connect(str(self.tmp / "missions.db"))
        raw.execute("DROP TRIGGER events_no_update")
        raw.execute("UPDATE events SET reason = 'rewritten' WHERE seq = 2")
        raw.commit()
        raw.close()
        reopened = Ledger(self.tmp / "missions.db")
        self.addCleanup(reopened.close)
        ok, detail = reopened.verify_chain()
        self.assertFalse(ok)
        self.assertIn("hash mismatch", detail)

    def test_ledger_is_append_only(self) -> None:
        self.ledger.create_mission("m-4")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.conn.execute("UPDATE events SET actor = 'x'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.conn.execute("DELETE FROM events")

    def test_audit_entries_do_not_move_state(self) -> None:
        self.ledger.create_mission("m-5")
        self.ledger.record("m-5", actor="hermes", reason="YELLOW: pushed branch")
        self.assertEqual(self.ledger.mission_state("m-5"), "CREATED")
        self.assertTrue(self.ledger.verify_chain()[0])


# -- durable queue --------------------------------------------------------


class TestQueue(TempStoreCase):
    def setUp(self) -> None:
        super().setUp()
        self.db = self.tmp / "queue.db"
        self.queue = TaskQueue(self.db, max_active=1)
        self.addCleanup(self.queue.close)

    def test_claim_complete_roundtrip(self) -> None:
        self.queue.enqueue("t1", "m1", "shell.inspect")
        task = self.queue.claim("worker-a")
        self.assertIsNotNone(task)
        assert task is not None
        self.assertEqual(task.status, "RUNNING")
        self.assertEqual(task.attempt, 1)
        self.queue.start_validation("t1")
        self.queue.complete("t1", ["evidence://t1"])
        stored = self.queue.get("t1")
        assert stored is not None
        self.assertEqual(stored.status, "COMPLETED")

    def test_completion_requires_evidence(self) -> None:
        self.queue.enqueue("t-eve", "m1", "shell.inspect")
        self.queue.claim("worker-a")
        with self.assertRaises(ValueError):
            self.queue.complete("t-eve", [])

    def test_concurrency_cap_is_enforced(self) -> None:
        self.queue.enqueue("t1", "m1", "shell.inspect")
        self.queue.enqueue("t2", "m1", "shell.inspect")
        self.assertIsNotNone(self.queue.claim("worker-a"))
        self.assertIsNone(self.queue.claim("worker-b"))

    def test_duplicate_idempotency_key_is_rejected(self) -> None:
        self.queue.enqueue("t1", "m1", "git.push", idempotency_key="same")
        with self.assertRaises(DuplicateTaskError):
            self.queue.enqueue("t2", "m1", "git.push", idempotency_key="same")

    def test_retry_uses_exponential_backoff_then_dead_letters(self) -> None:
        self.assertEqual(backoff_seconds(1), 30)
        self.assertEqual(backoff_seconds(2), 60)
        self.assertEqual(backoff_seconds(3), 120)
        self.queue.enqueue("t1", "m1", "shell.flaky", max_attempts=2)
        self.queue.claim("worker-a")
        requeued = self.queue.fail("t1", "boom")
        assert requeued is not None
        self.assertEqual(requeued.status, "QUEUED")
        self.assertEqual(requeued.last_error, "boom")
        # Backoff pushes it into the future, so it is not immediately claimable.
        self.assertIsNone(self.queue.claim("worker-a"))
        self.queue.conn.execute(
            "UPDATE tasks SET scheduled_at = '2000-01-01T00:00:00Z' WHERE task_id = 't1'"
        )
        self.queue.claim("worker-a")
        dead = self.queue.fail("t1", "boom again")
        assert dead is not None
        self.assertEqual(dead.status, "DEAD_LETTER")
        self.assertEqual([task.task_id for task in self.queue.dead_letters()], ["t1"])

    def test_dependencies_gate_dispatch(self) -> None:
        self.queue.enqueue("parent", "m1", "shell.inspect")
        self.queue.enqueue("child", "m1", "shell.inspect", depends_on=["parent"])
        first = self.queue.claim("worker-a")
        assert first is not None
        self.assertEqual(first.task_id, "parent")
        self.queue.start_validation("parent")
        self.queue.complete("parent", ["evidence://parent"])
        second = self.queue.claim("worker-a")
        assert second is not None
        self.assertEqual(second.task_id, "child")

    def test_red_task_waits_and_blocks_only_itself(self) -> None:
        self.queue.enqueue("red", "m1", "email.send", permission="RED", priority=1)
        self.queue.enqueue("green", "m1", "shell.inspect", permission="GREEN", priority=10)
        claimed = self.queue.claim("worker-a")
        assert claimed is not None
        self.assertEqual(claimed.task_id, "green", "a RED task must not freeze GREEN work")
        red = self.queue.get("red")
        assert red is not None
        self.assertEqual(red.status, "WAITING_FOR_APPROVAL")

    def test_approval_is_scoped_and_expiring(self) -> None:
        self.queue.enqueue("red", "m1", "email.send", permission="RED")
        expires = datetime.now(timezone.utc) + timedelta(minutes=30)
        approved = self.queue.approve("red", "OSA", expires_at=expires)
        assert approved is not None
        self.assertEqual(approved.status, "QUEUED")
        approval = approved.payload["approval"]
        self.assertEqual(approval["approver"], "OSA")
        self.assertEqual(approval["scope"]["task_id"], "red")
        self.assertIsNotNone(approval["expires_at"])

    def test_expired_approval_is_refused(self) -> None:
        self.queue.enqueue("red", "m1", "email.send", permission="RED")
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        with self.assertRaises(ValueError):
            self.queue.approve("red", "OSA", expires_at=past)

    def test_approving_a_non_pending_task_is_refused(self) -> None:
        self.queue.enqueue("green", "m1", "shell.inspect")
        with self.assertRaises(ValueError):
            self.queue.approve("green", "OSA")

    def test_stale_worker_lease_is_recovered(self) -> None:
        self.queue.enqueue("t1", "m1", "shell.inspect")
        self.queue.claim("worker-a")
        self.queue.conn.execute(
            "UPDATE tasks SET lease_expires_at = '2000-01-01T00:00:00Z',"
            " heartbeat_at = '2000-01-01T00:00:00Z' WHERE task_id = 't1'"
        )
        recovered = self.queue.recover_stale()
        self.assertEqual(recovered, ["t1"])
        task = self.queue.get("t1")
        assert task is not None
        self.assertEqual(task.status, "QUEUED")

    def test_fresh_heartbeat_protects_a_running_task(self) -> None:
        self.queue.enqueue("t1", "m1", "shell.inspect")
        self.queue.claim("worker-a")
        self.queue.conn.execute(
            "UPDATE tasks SET lease_expires_at = '2000-01-01T00:00:00Z' WHERE task_id = 't1'"
        )
        self.queue.heartbeat("t1", "worker-a")
        self.queue.conn.execute(
            "UPDATE tasks SET lease_expires_at = '2000-01-01T00:00:00Z' WHERE task_id = 't1'"
        )
        self.assertEqual(self.queue.recover_stale(), [])

    def test_state_survives_restart(self) -> None:
        self.queue.enqueue("t1", "m1", "shell.inspect")
        self.queue.enqueue("t2", "m1", "shell.inspect")
        self.queue.claim("worker-a")
        self.queue.close()

        reopened = TaskQueue(self.db, max_active=1)
        self.addCleanup(reopened.close)
        counts = reopened.stats()
        self.assertEqual(counts["QUEUED"], 1)
        self.assertEqual(counts["RUNNING"], 1)
        task = reopened.get("t1")
        assert task is not None
        self.assertEqual(task.attempt, 1)

    def test_cancel_and_replay(self) -> None:
        self.queue.enqueue("t1", "m1", "shell.inspect")
        self.queue.cancel("t1", "operator stopped it")
        cancelled = self.queue.get("t1")
        assert cancelled is not None
        self.assertEqual(cancelled.status, "CANCELLED")
        replayed = self.queue.replay("t1", "t1-replay")
        self.assertEqual(replayed.status, "QUEUED")
        self.assertNotEqual(replayed.idempotency_key, cancelled.idempotency_key)

    def test_queue_lag_reports_a_stalled_queue(self) -> None:
        self.queue.enqueue("t1", "m1", "shell.inspect")
        self.queue.conn.execute(
            "UPDATE tasks SET scheduled_at = '2000-01-01T00:00:00Z' WHERE task_id = 't1'"
        )
        self.assertGreater(self.queue.queue_lag_seconds(), 0)


# -- model router ---------------------------------------------------------


class TestRouter(TempStoreCase):
    def setUp(self) -> None:
        super().setUp()
        self.health = HealthTable(self.tmp / "model-health.json")

    def _router(self) -> ModelRouter:
        return ModelRouter(health=self.health)

    def test_preferred_model_is_selected_when_healthy(self) -> None:
        self.health.set(
            ProviderHealth("nvidia-router", "router-default", "HEALTHY",
                           supported_capabilities=["text", "reasoning", "code", "tools"])
        )
        decision = self._router().select("CODE_GENERATION", required_capabilities=["code"])
        self.assertEqual(decision.selected, "router-default")
        self.assertEqual(decision.status, "ROUTED")

    def test_fallback_when_preferred_is_down(self) -> None:
        self.health.set(ProviderHealth("nvidia-router", "router-default", "DOWN"))
        self.health.set(
            ProviderHealth("nvidia-router", "router-reasoning", "HEALTHY",
                           supported_capabilities=["text", "reasoning", "code"])
        )
        decision = self._router().select("CODE_GENERATION", required_capabilities=["code"])
        self.assertEqual(decision.selected, "router-reasoning")
        self.assertIn("router-default", decision.rejected)
        self.assertEqual(decision.rejected["router-default"], "provider health is DOWN")

    def test_degraded_provider_is_used_but_flagged(self) -> None:
        self.health.set(
            ProviderHealth("nvidia-router", "router-fast", "DEGRADED",
                           supported_capabilities=["text", "classification"])
        )
        decision = self._router().select("FAST_CLASSIFICATION")
        self.assertEqual(decision.selected, "router-fast")
        self.assertEqual(decision.status, "DEGRADED")

    def test_capability_gap_blocks_instead_of_substituting(self) -> None:
        """The important one: never hand vision work to a text-only model."""
        self.health.set(ProviderHealth("nvidia-router", "router-vision", "DOWN"))
        decision = self._router().select("VISION", required_capabilities=["vision"])
        self.assertTrue(decision.blocked)
        self.assertIsNone(decision.selected)
        self.assertIn("blocked rather than routed", decision.reason)

    def test_local_fallback_never_receives_code_work(self) -> None:
        for model in ("router-default", "router-reasoning"):
            self.health.set(ProviderHealth("nvidia-router", model, "DOWN"))
        decision = self._router().select("CODE_GENERATION", required_capabilities=["code"])
        self.assertTrue(decision.blocked)

    def test_context_window_is_respected(self) -> None:
        self.health.set(
            ProviderHealth("nvidia-router", "router-fast", "HEALTHY",
                           supported_capabilities=["text", "classification"])
        )
        self.health.set(
            ProviderHealth("nvidia-router", "router-default", "HEALTHY",
                           supported_capabilities=["text", "classification"])
        )
        decision = self._router().select("FAST_CLASSIFICATION", context_tokens=64000)
        self.assertEqual(decision.selected, "router-default")
        self.assertIn("exceeds window", decision.rejected["router-fast"])

    def test_private_task_requires_a_local_model(self) -> None:
        self.health.set(
            ProviderHealth("local", "local-fallback", "HEALTHY",
                           supported_capabilities=["text", "classification"])
        )
        decision = self._router().select("LOCAL_PRIVATE", private=True)
        self.assertEqual(decision.selected, "local-fallback")

    def test_health_table_persists(self) -> None:
        self.health.set(ProviderHealth("nvidia-router", "router-default", "DEGRADED"))
        self.health.save()
        reloaded = HealthTable(self.tmp / "model-health.json")
        self.assertEqual(reloaded.status_of("router-default"), "DEGRADED")

    def test_unknown_model_defaults_to_down(self) -> None:
        self.assertEqual(self.health.status_of("router-default"), "DOWN")


# -- redaction ------------------------------------------------------------


class TestRedaction(unittest.TestCase):
    def test_credential_shapes_are_redacted(self) -> None:
        sample = (
            "key=nvapi-AAAABBBBCCCCDDDD token: ghp_0123456789abcdefghij "  # noqa: E501 secret-scan: synthetic fixture
            "authorization: Bearer abcdefghijklmnop"
        )
        cleaned = redact_module.redact(sample)
        self.assertNotIn("nvapi-AAAA", cleaned)
        self.assertNotIn("ghp_0123456789", cleaned)
        self.assertIn("REDACTED", cleaned)

    def test_mask_uses_the_required_format(self) -> None:
        self.assertEqual(redact_module.mask("abcdefghijklmnopqrstuvwxyz"), "abcd...wxyz")
        self.assertEqual(redact_module.mask("short"), "*****")
        self.assertEqual(redact_module.mask(""), "")

    def test_excerpt_is_bounded_and_clean(self) -> None:
        text = "line one\n\tline two   " + ("x" * 500)
        result = redact_module.excerpt(text, limit=64)
        self.assertLessEqual(len(result), 64)
        self.assertNotIn("\n", result)


# -- revenue --------------------------------------------------------------


class TestRevenue(TempStoreCase):
    def setUp(self) -> None:
        super().setUp()
        self.ledger = RevenueLedger(self.tmp / "revenue-ledger.db")
        self.addCleanup(self.ledger.close)

    @staticmethod
    def _lead() -> Lead:
        return Lead(
            lead_id="lead-test-1",
            company="Testowa Firma Sp. z o.o.",
            contact_name="Test Contact",
            email="contact@example.invalid",
            website="https://example.invalid",
            industry="logistics",
            problem="manual order handling across three systems",
            team_size="10-49",
            current_tools=["excel", "email"],
            urgency="high",
            consent=True,
            source="synthetic-test",
        )

    def test_scoring_is_deterministic_and_bounded(self) -> None:
        lead = self._lead()
        self.assertEqual(score_lead(lead), score_lead(lead))
        self.assertLessEqual(score_lead(lead), 100)
        self.assertGreater(score_lead(lead), 0)

    def test_estimates_never_land_in_realised_revenue(self) -> None:
        result = self.ledger.add_lead(self._lead())
        self.ledger.add_opportunity(
            "opp-1", "lead-test-1", "synthetic-test", result["estimated_value"], 0.3,
            "call", ["evidence://audit/1"],
        )
        totals = self.ledger.totals()
        self.assertGreater(totals["estimated_value"], 0)
        self.assertGreater(totals["pipeline_value"], 0)
        self.assertEqual(totals["contracted_value"], 0.0)
        self.assertEqual(totals["invoiced_value"], 0.0)
        self.assertEqual(totals["received_value"], 0.0, "forecast must never appear as cash")

    def test_send_states_require_scoped_approval(self) -> None:
        self.ledger.add_lead(self._lead())
        with self.assertRaises(PermissionError):
            self.ledger.set_state("lead-test-1", "sent")
        with self.assertRaises(PermissionError):
            self.ledger.set_state("lead-test-1", "approved_to_send")
        self.ledger.set_state("lead-test-1", "sent", approval_ref="approval://osa/1")

    def test_outreach_row_requires_an_approval_reference(self) -> None:
        self.ledger.add_lead(self._lead())
        self.ledger.add_draft("draft-1", "lead-test-1", "outreach", "subject", "body")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.record_outreach("evt-1", "lead-test-1", "draft-1", "email", "", "")

    def test_audit_and_draft_are_generated_from_stored_facts(self) -> None:
        lead = self._lead()
        score = score_lead(lead)
        audit = generate_audit(lead, score, ["three systems, no shared order state"])
        self.assertIn(lead.company, audit)
        self.assertIn("forecasts, not commitments", audit)
        subject, body = generate_outreach_draft(lead, f"Opportunity score: {score}/100")
        self.assertIn(lead.company, subject)
        self.assertIn("DRAFT — not sent", body)

    def test_full_revenue_workflow_sends_nothing(self) -> None:
        """§22 revenue workflow test, synthetic data only."""
        lead = self._lead()
        result = self.ledger.add_lead(lead)
        score = result["score"]
        self.ledger.add_audit(
            "audit-1", lead.lead_id, "TRACK_1", generate_audit(lead, score, ["finding"]), score
        )
        self.ledger.set_state(lead.lead_id, "audit_ready")
        subject, body = generate_outreach_draft(lead, "summary")
        self.ledger.add_draft("draft-1", lead.lead_id, "outreach", subject, body)
        self.ledger.set_state(lead.lead_id, "draft_ready")
        due = self.ledger.schedule_followup("fu-1", lead.lead_id, 4)

        counts = self.ledger.counts()
        self.assertEqual(counts["leads"], 1)
        self.assertEqual(counts["audits"], 1)
        self.assertEqual(counts["drafts"], 1)
        self.assertEqual(counts["drafts_sent"], 0, "no draft may be marked sent")
        self.assertTrue(due)

        sent_rows = self.ledger.conn.execute(
            "SELECT COUNT(*) AS n FROM outreach_events"
        ).fetchone()["n"]
        self.assertEqual(sent_rows, 0, "no outreach event may exist without approval")
        stored = self.ledger.get_lead(lead.lead_id)
        assert stored is not None
        self.assertEqual(stored["state"], "draft_ready")


# -- integration ----------------------------------------------------------


class TestMissionIntegration(TempStoreCase):
    """Mission intake through to evidenced completion, across all components."""

    def setUp(self) -> None:
        super().setUp()
        self.ledger = Ledger(self.tmp / "missions.db")
        self.queue = TaskQueue(self.tmp / "queue.db", max_active=1)
        self.classifier = PermissionClassifier()
        self.addCleanup(self.ledger.close)
        self.addCleanup(self.queue.close)

    def test_green_mission_runs_end_to_end_with_evidence(self) -> None:
        mission = "m-green"
        self.ledger.create_mission(mission, "inspect the runtime")
        self.ledger.transition(mission, "INTAKE_VALIDATED", reason="intake ok")
        self.ledger.transition(mission, "PLANNED", reason="one task planned")

        decision = self.classifier.classify("shell", "inspect", {"target": "docker ps"})
        self.assertIs(decision.permission, PermissionLevel.GREEN)
        self.queue.enqueue(
            "t-green", mission, "shell.inspect", permission=str(decision.permission),
            idempotency_key=decision.idempotency_key,
        )
        self.ledger.transition(mission, "QUEUED", reason="task queued", task_id="t-green")

        task = self.queue.claim("worker-a")
        assert task is not None
        self.ledger.transition(mission, "DISPATCHED", task_id=task.task_id)
        self.ledger.transition(mission, "RUNNING", task_id=task.task_id)

        self.queue.start_validation(task.task_id)
        self.ledger.transition(mission, "VALIDATING", reason="checking output")
        self.queue.complete(task.task_id, ["evidence://runtime-inventory"])
        self.ledger.transition(
            mission, "COMPLETED", reason="validated", task_id=task.task_id,
            evidence_refs=["evidence://runtime-inventory"],
        )

        self.assertEqual(self.ledger.mission_state(mission), "COMPLETED")
        ok, detail = self.ledger.verify_chain()
        self.assertTrue(ok, detail)

    def test_red_task_blocks_and_resumes_only_its_own_scope(self) -> None:
        mission = "m-red"
        self.ledger.create_mission(mission, "outreach mission")
        self.ledger.transition(mission, "INTAKE_VALIDATED")
        self.ledger.transition(mission, "PLANNED")

        red = self.classifier.classify("email", "send", {"to": "prospect@example.invalid"})
        green = self.classifier.classify("email", "draft", {"lead": "lead-1"})
        self.assertIs(red.permission, PermissionLevel.RED)
        self.assertIs(green.permission, PermissionLevel.GREEN)

        self.queue.enqueue("t-red", mission, "email.send", permission="RED", priority=1,
                           idempotency_key=red.idempotency_key)
        self.queue.enqueue("t-draft", mission, "email.draft", permission="GREEN", priority=5,
                           idempotency_key=green.idempotency_key)
        self.ledger.transition(mission, "WAITING_FOR_APPROVAL", reason="send requires OSA")

        # The GREEN task still runs while the RED one waits.
        claimed = self.queue.claim("worker-a")
        assert claimed is not None
        self.assertEqual(claimed.task_id, "t-draft")
        self.queue.start_validation("t-draft")
        self.queue.complete("t-draft", ["evidence://draft/1"])

        blocked = self.queue.get("t-red")
        assert blocked is not None
        self.assertEqual(blocked.status, "WAITING_FOR_APPROVAL")

        # Scoped, expiring approval releases exactly one task.
        expires = datetime.now(timezone.utc) + timedelta(minutes=15)
        approved = self.queue.approve("t-red", "OSA", expires_at=expires)
        assert approved is not None
        self.assertEqual(approved.payload["approval"]["scope"]["task_id"], "t-red")
        self.ledger.record(
            mission, actor="OSA", reason="approved scoped send", task_id="t-red",
            evidence_refs=["approval://osa/t-red"],
        )
        self.ledger.transition(mission, "QUEUED", reason="approval granted")
        self.assertTrue(self.ledger.verify_chain()[0])

    def test_queue_and_ledger_survive_a_restart_together(self) -> None:
        mission = "m-restart"
        self.ledger.create_mission(mission)
        self.queue.enqueue("t-a", mission, "shell.inspect")
        self.queue.enqueue("t-b", mission, "shell.inspect")
        self.queue.claim("worker-a")
        self.queue.close()
        self.ledger.close()

        queue = TaskQueue(self.tmp / "queue.db", max_active=1)
        ledger = Ledger(self.tmp / "missions.db")
        self.addCleanup(queue.close)
        self.addCleanup(ledger.close)

        queue.conn.execute(
            "UPDATE tasks SET lease_expires_at = '2000-01-01T00:00:00Z',"
            " heartbeat_at = '2000-01-01T00:00:00Z' WHERE task_id = 't-a'"
        )
        self.assertEqual(queue.recover_stale(), ["t-a"])
        self.assertEqual(queue.stats()["QUEUED"], 2)
        self.assertEqual(ledger.mission_state(mission), "CREATED")
        self.assertTrue(ledger.verify_chain()[0])


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
