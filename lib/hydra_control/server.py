"""Loopback JSON API and static command-center server."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from hermes.config import state_dir as hermes_state_dir

from .models import ControlPlaneError, NotFoundError, ValidationError
from .service import MissionService


MAX_BODY_BYTES = 64 * 1024
MISSION_ID = r"(?P<mission>[0-9a-f-]{36})"
NODE_ID = r"(?P<node>[a-z0-9-]{1,80})"


class HydraHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        service: MissionService,
        web_root: Path,
    ) -> None:
        self.service = service
        self.web_root = web_root.resolve(strict=True)
        super().__init__(server_address, HydraRequestHandler)


class HydraRequestHandler(BaseHTTPRequestHandler):
    server: HydraHTTPServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP interface
        try:
            path = urlparse(self.path).path
            if path == "/api/health":
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "service": "hydra-minion-control-plane",
                        "backends": len(self.server.service.backends()),
                    },
                )
                return
            if path == "/api/backends":
                self._json(HTTPStatus.OK, {"backends": self.server.service.backends()})
                return
            if path == "/api/missions":
                self._json(HTTPStatus.OK, {"missions": self.server.service.list_missions()})
                return
            match = re.fullmatch(rf"/api/missions/{MISSION_ID}", path)
            if match:
                self._json(HTTPStatus.OK, self.server.service.mission(match["mission"]))
                return
            for suffix, getter in (
                ("events", self.server.service.events),
                ("logs", self.server.service.logs),
                ("artifacts", self.server.service.artifacts),
                ("evidence", self.server.service.evidence),
            ):
                match = re.fullmatch(rf"/api/missions/{MISSION_ID}/{suffix}", path)
                if match:
                    value = getter(match["mission"])
                    self._json(
                        HTTPStatus.OK,
                        value if suffix == "evidence" else {suffix: value},
                    )
                    return
            match = re.fullmatch(r"/api/artifacts/(?P<artifact>[0-9a-f-]{36})/content", path)
            if match:
                data = self.server.service.artifact_bytes(match["artifact"])
                self._bytes(HTTPStatus.OK, data, "application/octet-stream")
                return
            self._static(path)
        except Exception as error:
            self._error(error)

    def do_POST(self) -> None:  # noqa: N802 - stdlib HTTP interface
        try:
            path = urlparse(self.path).path
            actor = self.headers.get("X-Hydra-Actor", "OSA")
            if path == "/api/missions":
                payload = self._body()
                self._json(
                    HTTPStatus.CREATED,
                    self.server.service.create_mission(payload, actor),
                )
                return
            match = re.fullmatch(rf"/api/missions/{MISSION_ID}/start", path)
            if match:
                self._empty_body_only()
                self._json(
                    HTTPStatus.ACCEPTED,
                    self.server.service.start(match["mission"], actor),
                )
                return
            match = re.fullmatch(rf"/api/missions/{MISSION_ID}/approvals", path)
            if match:
                payload = self._body()
                if set(payload) != {"gate"}:
                    raise ValidationError("approval body must contain only 'gate'")
                self._json(
                    HTTPStatus.ACCEPTED,
                    self.server.service.approve(
                        match["mission"], gate=payload.get("gate"), actor=actor
                    ),
                )
                return
            match = re.fullmatch(
                rf"/api/missions/{MISSION_ID}/nodes/{NODE_ID}/retry", path
            )
            if match:
                self._empty_body_only()
                self._json(
                    HTTPStatus.ACCEPTED,
                    self.server.service.retry(match["mission"], match["node"], actor),
                )
                return
            match = re.fullmatch(rf"/api/missions/{MISSION_ID}/cancel", path)
            if match:
                self._empty_body_only()
                self._json(
                    HTTPStatus.OK,
                    self.server.service.cancel(match["mission"], actor),
                )
                return
            raise NotFoundError(f"unknown endpoint: {path}")
        except Exception as error:
            self._error(error)

    def _body(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            raise ValidationError("Content-Type must be application/json")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValidationError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ValidationError("invalid Content-Length") from error
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValidationError(f"request body must be 1-{MAX_BODY_BYTES} bytes")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationError("request body is not valid UTF-8 JSON") from error
        if not isinstance(payload, dict):
            raise ValidationError("request body must be a JSON object")
        return payload

    def _empty_body_only(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length:
            raise ValidationError("this endpoint does not accept a request body")

    def _static(self, path: str) -> None:
        relative = "index.html" if path in ("", "/") else unquote(path.lstrip("/"))
        if relative not in {"index.html", "app.js", "styles.css"}:
            raise NotFoundError(f"unknown path: {path}")
        candidate = (self.server.web_root / relative).resolve(strict=True)
        try:
            candidate.relative_to(self.server.web_root)
        except ValueError as error:
            raise NotFoundError("static path is outside the command-center root") from error
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self._bytes(HTTPStatus.OK, candidate.read_bytes(), content_type)

    def _error(self, error: Exception) -> None:
        if isinstance(error, ControlPlaneError):
            self._json(
                error.status,
                {"error": {"code": error.code, "message": str(error)}},
            )
            return
        self._json(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "unexpected control-plane failure; inspect local server logs",
                }
            },
        )

    def _json(self, status: int, payload: Any) -> None:
        data = (json.dumps(payload, sort_keys=True, default=str) + "\n").encode("utf-8")
        self._bytes(status, data, "application/json; charset=utf-8")

    def _bytes(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(int(status))
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        print(f"hydra-http {self.address_string()} {format % args}")


def create_server(
    service: MissionService,
    host: str = "127.0.0.1",
    port: int = 8787,
    web_root: str | Path | None = None,
) -> HydraHTTPServer:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValidationError("the initial control plane may bind only to loopback")
    root = Path(web_root) if web_root else Path(__file__).resolve().parents[2] / "web"
    return HydraHTTPServer((host, port), service, root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hydra Minion control-plane server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--state-dir", default=str(hermes_state_dir()))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = MissionService.local(args.state_dir)
    recovered = service.recover(asynchronous=True)
    server = create_server(service, args.host, args.port)
    print(
        f"Hydra Minion control plane listening on http://{args.host}:{server.server_port} "
        f"state={Path(args.state_dir).resolve()} recovered={len(recovered)}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
