from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from hermes.vertical_slice import ControlPlaneService


class TestHydraVerticalSlice(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "worker"
        self.old_state = os.environ.get("HERMES_WORKER_STATE_DIR")
        os.environ["HERMES_WORKER_STATE_DIR"] = str(self.state)
        self.addCleanup(self._restore_env)
        self.service = ControlPlaneService(self.state)

    def _restore_env(self) -> None:
        if self.old_state is None:
            os.environ.pop("HERMES_WORKER_STATE_DIR", None)
        else:
            os.environ["HERMES_WORKER_STATE_DIR"] = self.old_state

    def test_mission_runs_michael_worker_pinokio_evidence_end_to_end(self) -> None:
        created = self.service.create_mission("Sprawdź integralność Hydra Control Plane")
        mission_id = created["mission_id"]
        task_id = created["task_id"]

        snapshot = created["snapshot"]
        mission = next(item for item in snapshot["missions"] if item["mission_id"] == mission_id)
        self.assertEqual(mission["state"], "QUEUED")
        self.assertEqual(created["permission"], "GREEN")

        result = self.service.run_next()
        self.assertEqual(result["executed"]["mission_id"], mission_id)
        self.assertEqual(result["executed"]["task_id"], task_id)
        self.assertEqual(result["executed"]["worker"], "michael-angelo")
        self.assertEqual(result["executed"]["verifier"], "Pinokio")

        evidence_file = Path(result["executed"]["evidence_file"])
        self.assertTrue(evidence_file.is_file())
        self.assertIn("sha256=", result["executed"]["evidence_ref"])

        snapshot = result["snapshot"]
        mission = next(item for item in snapshot["missions"] if item["mission_id"] == mission_id)
        task = next(item for item in snapshot["tasks"] if item["task_id"] == task_id)
        self.assertEqual(mission["state"], "COMPLETED")
        self.assertEqual(task["status"], "COMPLETED")
        self.assertTrue(snapshot["chain"]["ok"])

        actors = [
            event["actor"]
            for event in snapshot["events"]
            if event["mission_id"] == mission_id
        ]
        self.assertIn("Michael Angelo", actors)
        self.assertIn("Pinokio", actors)

    def test_empty_title_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.create_mission("   ")

    def test_run_next_without_task_is_blocked(self) -> None:
        with self.assertRaises(LookupError):
            self.service.run_next()


if __name__ == "__main__":
    unittest.main(verbosity=2)
