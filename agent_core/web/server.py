from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from agent_core.app import RadAgentAppService
from agent_core.web.api import (
    build_command_catalog,
    build_home_summary,
    dispatch_web_command,
    to_jsonable,
)

ApiHandler = Callable[[str, str, bytes], tuple[int, dict[str, Any]]]
ServiceProvider = Callable[[], Any]


def _read_json(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object.")
    return data


def _create_api_handler(get_service: ServiceProvider) -> ApiHandler:
    """Create a framework-free API handler for unit tests and HTTP serving."""

    def handle(method: str, target: str, body: bytes) -> tuple[int, dict[str, Any]]:
        parsed = urlparse(target)
        query = parse_qs(parsed.query)
        path = parsed.path.rstrip("/") or "/"

        try:
            match method.upper(), path:
                case "GET", "/api/commands":
                    return HTTPStatus.OK, {"commands": build_command_catalog()}
                case "GET", "/api/home":
                    service = get_service()
                    return HTTPStatus.OK, {"home": build_home_summary(service)}
                case "GET", "/api/startup":
                    service = get_service()
                    return HTTPStatus.OK, {"startup": to_jsonable(service.get_startup_status())}
                case "GET", "/api/status":
                    service = get_service()
                    return HTTPStatus.OK, {"status": to_jsonable(service.get_status())}
                case "GET", "/api/events":
                    service = get_service()
                    limit = int(query.get("limit", ["80"])[0])
                    return HTTPStatus.OK, {"events": to_jsonable(service.recent_events(limit))}
                case "GET", "/api/visualization":
                    service = get_service()
                    job_id = str(query.get("job_id", [""])[0]).strip() or None
                    return HTTPStatus.OK, {
                        "visualization": to_jsonable(service.get_visualization_payload(job_id))
                    }
                case "GET", "/api/artifacts":
                    service = get_service()
                    job_id = str(query.get("job_id", [""])[0]).strip() or None
                    return HTTPStatus.OK, {"artifacts": to_jsonable(service.list_artifacts(job_id))}
                case "POST", "/api/command":
                    service = get_service()
                    payload = _read_json(body)
                    text = str(payload.get("text", "")).strip()
                    if not text:
                        return HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Missing command text."}
                    result = asyncio.run(dispatch_web_command(service, text))
                    return HTTPStatus.OK, result
                case "POST", "/api/job":
                    service = get_service()
                    payload = _read_json(body)
                    job_id = str(payload.get("job_id", "")).strip()
                    if not job_id:
                        return HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Missing job id."}
                    job = service.get_job(job_id)
                    if job is None:
                        return HTTPStatus.NOT_FOUND, {"ok": False, "error": f"Job not found: {job_id}"}
                    return HTTPStatus.OK, {"job": to_jsonable(job)}
                case "POST", "/api/artifact":
                    service = get_service()
                    payload = _read_json(body)
                    path = str(payload.get("path", "")).strip()
                    if not path:
                        return HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Missing artifact path."}
                    max_chars = int(payload.get("max_chars", 200_000))
                    artifact = service.read_artifact(path, max_chars=max_chars)
                    return HTTPStatus.OK, {"artifact": to_jsonable(artifact)}
                case "POST", "/api/model":
                    service = get_service()
                    payload = _read_json(body)
                    allowed_keys = {
                        "base_url",
                        "api_key",
                        "api_key_env",
                        "lite_model",
                        "pro_model",
                        "max_model",
                        "lite_timeout_s",
                        "pro_timeout_s",
                        "max_timeout_s",
                        "lite_max_tokens",
                        "pro_max_tokens",
                        "max_max_tokens",
                        "lite_context_window_tokens",
                        "pro_context_window_tokens",
                        "max_context_window_tokens",
                        "agentic_repair_max_turns",
                        "agentic_repair_history_chars",
                    }
                    update = {key: value for key, value in payload.items() if key in allowed_keys}
                    model = service.update_model_config(update)
                    return HTTPStatus.OK, {"model": to_jsonable(model)}
                case _:
                    return HTTPStatus.NOT_FOUND, {"ok": False, "error": f"Unknown API path: {path}"}
        except (json.JSONDecodeError, ValueError) as exc:
            return HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)}

    return handle


def create_api_handler(service: Any) -> ApiHandler:
    return _create_api_handler(lambda: service)


class RadAgentWebHandler(BaseHTTPRequestHandler):
    api_handler: ApiHandler
    static_root: Path

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._send_api_response("GET")
            return
        self._send_static_response()

    def do_POST(self) -> None:
        self._send_api_response("POST")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_api_response(self, method: str) -> None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else b""
        status, payload = self.api_handler(method, self.path, body)
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_static_response(self) -> None:
        root = self.static_root.resolve()
        parsed = urlparse(self.path)
        relative = parsed.path.lstrip("/") or "index.html"
        candidate = (root / relative).resolve()
        if not str(candidate).startswith(str(root)) or not candidate.is_file():
            candidate = root / "index.html"
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Frontend build not found.")
            return
        raw = candidate.read_bytes()
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def build_server(
    *,
    host: str,
    port: int,
    static_root: Path,
    env_path: Path | None = None,
    service: Any | None = None,
) -> HTTPServer:
    active_service = service

    def get_service() -> Any:
        nonlocal active_service
        if active_service is None:
            active_service = RadAgentAppService(execution_mode="strict", env_path=env_path)
        return active_service

    api_handler = _create_api_handler(get_service)

    class Handler(RadAgentWebHandler):
        pass

    Handler.api_handler = staticmethod(api_handler)
    Handler.static_root = static_root
    return HTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the RadAgent web workbench server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--static-root",
        type=Path,
        default=Path("web_workbench/dist"),
        help="Path to the built Vite frontend.",
    )
    parser.add_argument(
        "--env-path",
        type=Path,
        default=None,
        help="Project env file for editable model settings.",
    )
    args = parser.parse_args(argv)

    server = build_server(
        host=args.host,
        port=args.port,
        static_root=args.static_root,
        env_path=args.env_path,
    )
    print(f"RadAgent web workbench listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
