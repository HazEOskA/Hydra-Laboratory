"""Contract tests for the minimal Hydra World true-loop boundary."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from hydra_control.world import HydraWorldAdapter, WorldPort  # noqa: E402
from hydra_world import KERNEL_ID, WorldKernel, WorldObservation  # noqa: E402


class WorldKernelCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.kernel = WorldKernel(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_roundtrip_is_hash_bound(self) -> None:
        observation = self.kernel.record(
            WorldObservation(
                source="test.probe",
                kind="metric",
                payload={"cpu": 0.12},
                recorded_at=1_800_000_000.0,
            )
        )
        self.assertEqual(len(observation.sha256), 64)
        self.assertTrue(observation.hash_valid())

        snapshot = self.kernel.snapshot()
        self.assertEqual(snapshot.kernel_id, KERNEL_ID)
        self.assertEqual(snapshot.observation_count, 1)
        self.assertEqual(len(snapshot.sha256), 64)

        recent = self.kernel.recent(limit=10)
        self.assertEqual(recent, [observation])

    def test_snapshot_keeps_latest_health_per_source(self) -> None:
        self.kernel.record_health(
            "test.host",
            "degraded",
            {"reason": "warmup"},
            recorded_at=100.0,
        )
        latest = self.kernel.record_health(
            "test.host",
            "ok",
            {"uptime": 3600},
            recorded_at=200.0,
        )

        snapshot = self.kernel.snapshot()
        self.assertEqual(snapshot.observation_count, 2)
        self.assertEqual(snapshot.health["test.host"]["payload"]["status"], "ok")
        self.assertEqual(snapshot.health["test.host"]["sha256"], latest.sha256)

    def test_input_bounds_are_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            self.kernel.record(
                WorldObservation(
                    source="../escape",
                    kind="metric",
                    payload={},
                    recorded_at=1.0,
                )
            )
        with self.assertRaises(ValueError):
            self.kernel.recent(limit=0)
        with self.assertRaises(ValueError):
            self.kernel.recent(limit=501)

    def test_tampered_storage_is_refused(self) -> None:
        self.kernel.record(
            WorldObservation(
                source="test.probe",
                kind="event",
                payload={"value": 1},
                recorded_at=10.0,
            )
        )
        with sqlite3.connect(self.kernel.db_path) as conn:
            conn.execute(
                "UPDATE observations SET payload_json = ?",
                ('{"value":2}',),
            )
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.kernel.recent(limit=1)


class LaboratoryWorldGlueCase(unittest.TestCase):
    def test_laboratory_world_laboratory_roundtrip_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = HydraWorldAdapter(tmp)
            self.assertIsInstance(adapter, WorldPort)

            written = adapter.observe(
                source="hydra.health",
                kind="event",
                payload={"missionCount": 3},
                recorded_at=1_800_000_001.0,
            )
            self.assertEqual(len(written["sha256"]), 64)

            # Reconstructing the adapter proves the loop is durable, not in-memory.
            reopened = HydraWorldAdapter(tmp)
            snapshot = reopened.snapshot()
            self.assertEqual(snapshot["observationCount"], 1)
            self.assertEqual(snapshot["kernelId"], KERNEL_ID)
            self.assertEqual(
                reopened.recent(limit=1, source="hydra.health")[0]["payload"],
                {"missionCount": 3},
            )

            # World state is physically separate from Laboratory's missions.db.
            self.assertEqual(reopened.kernel.db_path, Path(tmp).resolve() / "world" / "world.db")
            self.assertNotEqual(reopened.kernel.db_path, Path(tmp).resolve() / "missions.db")

    def test_adapter_exposes_no_control_plane_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = HydraWorldAdapter(tmp)
            for forbidden in (
                "dispatch",
                "approve",
                "execute",
                "enqueue",
                "deploy",
                "create_mission",
            ):
                self.assertFalse(hasattr(adapter, forbidden), forbidden)


if __name__ == "__main__":
    unittest.main()
