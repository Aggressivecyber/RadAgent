#!/usr/bin/env python3
"""RadAgent 器件截面画布 · 本地服务(可选)

启动后浏览器打开 http://127.0.0.1:8765 ,即可:
1. 左上「选择 Job」下拉自动列出 simulation_workspace 里所有产出过
   ``03_model_ir/g4_model_ir.json`` 的 job —— 这就是 agent 对器件的理解。
2. 在画布上人工修正(拖位置/改尺寸/换材料/加删层)。
3. 点「回写到 Job」把修正后的 model_ir 写回该 job 的
   ``04_human_confirmation/g4_model_ir.json``,供 human_confirmation 阶段读取。

纯前端模式下(直接双击 index.html)只能拖文件 + 下载,不能浏览/回写 job。
"""

from __future__ import annotations

import json
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
WORKSPACE = Path(__file__).resolve().parent.parent / "simulation_workspace"

# 用于回写确认目录(画布修正后的 IR 落在这里)
def job_dir(job_id: str) -> Path | None:
    candidate = WORKSPACE / "jobs" / job_id
    return candidate if candidate.is_dir() else None


def list_jobs() -> list[dict]:
    jobs_root = WORKSPACE / "jobs"
    if not jobs_root.is_dir():
        return []
    out: list[dict] = []
    for d in sorted(jobs_root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        ir = d / "03_model_ir" / "g4_model_ir.json"
        if not ir.is_file():
            continue
        try:
            data = json.loads(ir.read_text())
        except Exception:
            continue
        out.append({
            "job_id": d.name,
            "target_system": data.get("target_system", ""),
            "n_components": len(data.get("components", [])),
            "path": str(ir.relative_to(WORKSPACE.parent)),
        })
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 安静点
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            try:
                self._send(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(404, b"index.html missing", "text/plain")
            return

        # 本地静态资源(仅 device_canvas 目录内的文件,禁止路径穿越)
        if path.startswith("/") and "/" not in path[1:]:
            fp = ROOT / path[1:]
            if fp.is_file():
                ctype = "application/javascript" if fp.suffix == ".js" else (
                    "application/json" if fp.suffix == ".json" else "application/octet-stream")
                self._send(200, fp.read_bytes(), ctype)
                return

        if path == "/api/jobs":
            self._send(200, json.dumps(list_jobs()).encode(), "application/json")
            return

        if path == "/api/job":
            qs = parse_qs(parsed.query)
            job_id = qs.get("id", [""])[0]
            if not job_id or not re.fullmatch(r"[A-Za-z0-9_.\-]+", job_id):
                self._send(400, b"bad job id", "text/plain")
                return
            jd = job_dir(job_id)
            if not jd:
                self._send(404, b"job not found", "text/plain")
                return
            ir = jd / "03_model_ir" / "g4_model_ir.json"
            if not ir.is_file():
                self._send(404, b"no model_ir", "text/plain")
                return
            self._send(200, ir.read_bytes(), "application/json")
            return

        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/save":
            self._send(404, b"not found", "text/plain")
            return
        qs = parse_qs(parsed.query)
        job_id = qs.get("id", [""])[0]
        if not job_id or not re.fullmatch(r"[A-Za-z0-9_.\-]+", job_id):
            self._send(400, b"bad job id", "text/plain")
            return
        jd = job_dir(job_id)
        if not jd:
            self._send(404, b"job not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw)
        except Exception as exc:
            self._send(400, f"bad json: {exc}".encode(), "text/plain")
            return

        # 写入 human_confirmation 目录,保留 03_ 原始 IR 不动(便于追溯)
        conf_dir = jd / "04_human_confirmation"
        conf_dir.mkdir(parents=True, exist_ok=True)
        out_path = conf_dir / "g4_model_ir.json"
        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        self._send(200, json.dumps({"ok": True, "written_to": str(out_path)}).encode())


def main() -> None:
    host, port = "127.0.0.1", 8765
    srv = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"[device_canvas] serving on {url}")
    print(f"[device_canvas] workspace: {WORKSPACE}")
    print(f"[device_canvas] found {len(list_jobs())} job(s) with model_ir")
    print("[device_canvas] Ctrl+C to stop")
    # 尽力自动开浏览器
    try:
        import webbrowser
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[device_canvas] stopped")


if __name__ == "__main__":
    main()
