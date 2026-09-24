#!/usr/bin/env python3
"""Minimal HTTP bridge for Hydra cockpit vertical slice v1."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from hermes.vertical_slice import ControlPlaneService  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    server_version = "HydraControlAPI/1.0"

    @property
    def service(self) -> ControlPlaneService:
        return self.server.service  # type: ignore[attr-defined]

    def _origin(self) -> str:
        return os.environ.get("HYDRA_UI_ORIGIN", "http://localhost:3000")

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", self._origin())
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, {})

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/healthz":
            self._send(200, {"status": "ok", "service": "hydra-control-api"})
            return
        if path == "/api/v1/snapshot":
            self._send(200, self.service.snapshot())
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/v1/missions":
                payload = self._json_body()
                result = self.service.create_mission(str(payload.get("title", "")))
                self._send(201, result)
                return
            if path == "/api/v1/run-next":
                self._send(200, self.service.run_next())
                return
            self._send(404, {"error": "not_found"})
        except LookupError as error:
            self._send(409, {"error": str(error)})
        except (ValueError, json.JSONDecodeError) as error:
            self._send(400, {"error": str(error)})
        except Exception as error:
            self._send(500, {"error": type(error).__name__, "detail": str(error)})

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[hydra-api] " + (fmt % args) + "\n")


def main() -> int:
    host = os.environ.get("HYDRA_API_HOST", "127.0.0.1")
    port = int(os.environ.get("HYDRA_API_PORT", "8787"))
    server = HTTPServer((host, port), Handler)
    server.service = ControlPlaneService()  # type: ignore[attr-defined]
    print("Hydra control API listening on http://" + host + ":" + str(port))
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
