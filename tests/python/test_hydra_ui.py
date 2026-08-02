"""Contract tests for the static Hydra command-center vertical slice."""

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

from hydra_control.server import create_server  # noqa: E402
from hydra_control.service import MissionService  # noqa: E402


EXPECTED_NAVIGATION = [
    "Dashboard",
    "Policies AI",
    "Michael Angelo",
    "Missions",
    "Agent Fleet",
    "Repositories",
    "Sandboxes",
    "Approvals",
    "APR Evidence",
    "Artifacts",
    "Infrastructure",
    "Audit Log",
    "Settings",
]


class HydraCommandCenterCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._state = tempfile.TemporaryDirectory()
        cls.service = MissionService.local(cls._state.name)
        cls.server = create_server(cls.service, port=0, web_root=REPO_ROOT / "web")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.service.store.close()
        cls._state.cleanup()

    def get(self, path: str) -> tuple[int, bytes, object]:
        with urlopen(f"{self.base_url}{path}", timeout=5) as response:
            return response.status, response.read(), response.headers

    def test_shell_and_local_assets_are_served_with_security_headers(self) -> None:
        status, body, headers = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"HYDRA Hermes Lab", body)
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])

        status, body, headers = self.get("/assets/brand/hydra-wordmark.webp")
        self.assertEqual(status, 200)
        self.assertGreater(len(body), 1_000)
        self.assertEqual(headers.get_content_type(), "image/webp")

    def test_static_handler_rejects_missing_and_traversal_assets(self) -> None:
        for path in (
            "/assets/illustrations/missing.webp",
            "/assets/%2e%2e/%2e%2e/docs/ui-references/hydra-dashboard-reference.png",
            "/docs/HYDRA_UI_DESIGN_LOCK_v0.1.md",
        ):
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                self.get(path)
            self.assertEqual(caught.exception.code, 404)
            caught.exception.close()

    def test_navigation_order_and_honest_runtime_states_are_locked(self) -> None:
        source = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
        positions = [source.index(f'"{label}"') for label in EXPECTED_NAVIGATION]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('route: "michael-angelo"', source)
        self.assertIn("NOT CONNECTED", source)
        self.assertIn("UNKNOWN", source)
        self.assertIn("Drift Guard", source)
        self.assertNotIn("innerHTML", source)

    def test_real_api_contract_drives_mission_inventory(self) -> None:
        payload = json.dumps(
            {
                "title": "UI contract mission",
                "request": "Validate that the command center reads the durable API.",
            }
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/missions",
            data=payload,
            headers={"Content-Type": "application/json", "X-Hydra-Actor": "UI-Test"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            created = json.load(response)
        self.assertEqual(response.status, 201)

        status, body, _ = self.get("/api/missions")
        missions = json.loads(body)["missions"]
        self.assertEqual(status, 200)
        self.assertIn(created["mission_id"], {item["mission_id"] for item in missions})
        self.assertEqual(created["state"], "DRAFT")

    def test_emergency_stop_requires_native_confirmation(self) -> None:
        html = (REPO_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        source = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('<dialog id="emergency-dialog"', html)
        self.assertIn("showModal()", source)
        self.assertIn('/cancel`, { method: "POST"', source)

    def test_mission_intake_uses_a_real_submit_control(self) -> None:
        source = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('type: options.type || "button"', source)
        self.assertIn('ariaLabel: "Compile local mission", type: "submit"', source)


if __name__ == "__main__":
    unittest.main()
