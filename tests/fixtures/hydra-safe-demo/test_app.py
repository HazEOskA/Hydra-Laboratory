"""Targeted fixture tests, including a real deterministic fail-once path."""

from pathlib import Path
import unittest

import app


class AppTest(unittest.TestCase):
    def test_greeting(self) -> None:
        self.assertEqual(app.greet("Hydra"), "Hello, Hydra!")

    def test_mission_result(self) -> None:
        marker = Path(".hydra-fail-once")
        if marker.exists():
            marker.unlink()
            self.fail("deterministic fail-once marker exercised")
        self.assertEqual(
            app.mission_summary(),
            "Hydra mission executed with commit-bound evidence.",
        )


if __name__ == "__main__":
    unittest.main()
