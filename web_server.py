"""Eternal Memories - 本地 REST API + 星云面板服务（仅标准库）."""

from __future__ import annotations

import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from eternal_memory import EternalMemory

HERE = Path(__file__).resolve().parent
DATA_DIR = os.environ.get("EM_DATA_DIR")
_ENGINE: EternalMemory | None = None
# 安全：仅允许本机来源的跨域请求，防止恶意网页读取本地记忆；静态资源仅放行面板必需后缀。
ALLOWED_ORIGINS = {"http://127.0.0.1:8765", "http://localhost:8765"}
STATIC_EXT = {".css", ".js", ".png", ".jpg", ".svg", ".ico", ".woff", ".woff2"}


def _em() -> EternalMemory:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = EternalMemory(DATA_DIR)
    return _ENGINE


class Handler(BaseHTTPRequestHandler):
    server_version = "EternalMemories/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.environ.get("EM_VERBOSE"):
            super().log_message(fmt, *args)

    def _send(self, status: int, payload: Any, content_type: str = "application/json; charset=utf-8") -> None:
        if isinstance(payload, bytes):
            body = payload  # 静态资源原始字节，直接写出，不转字符串字面量
        elif isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        elif isinstance(payload, str):
            body = payload.encode("utf-8")
        else:
            body = str(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._send(204, "")

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in ("127.0.0.1", "localhost", "::1")

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if not self._host_ok():
            return self._send(403, {"error": "forbidden host"})
        try:
            if path in ("/", "/index.html", "/dashboard.html"):
                f = HERE / "dashboard.html"
                if not f.exists():
                    return self._send(404, {"error": "dashboard.html not found"})
                return self._send(200, f.read_text(encoding="utf-8"), "text/html; charset=utf-8")
            g = _em()
            if path == "/api/health":
                return self._send(200, {"ok": True, "data_dir": str(g.data_dir), **g.stats()})
            if path == "/api/graph":
                return self._send(200, g.graph_data())
            if path == "/api/stats":
                return self._send(200, g.stats())
            if path == "/api/conflicts":
                return self._send(200, {"items": g.find_conflicts()})
            if path == "/api/profile":
                return self._send(200, g.profile())
            if path == "/api/export":
                return self._send(200, g.export_json())
            if path == "/api/memories":
                rows = [
                    dict(r, tags=json.loads(r["tags"] or "[]"))
                    for r in g._conn.execute("SELECT * FROM memories WHERE archived=0 ORDER BY updated_at DESC LIMIT 300")
                ]
                return self._send(200, {"items": rows})
            if path.startswith("/api/memory/"):
                mid = path.split("/")[-1]
                row = g.get(mid)
                return self._send(200, row or {"error": "not found"})
            if path.startswith("/static/"):
                name = Path(path.split("/")[-1]).name  # 归一化，阻断路径穿越
                if Path(name).suffix.lower() not in STATIC_EXT:
                    return self._send(404, {"error": "not found"})
                f = HERE / name
                if f.exists() and f.is_file():
                    ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
                    return self._send(200, f.read_bytes(), ctype)
            return self._send(404, {"error": "not found"})
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not self._host_ok():
            return self._send(403, {"error": "forbidden host"})
        body = self._body()
        try:
            g = _em()
            if path == "/api/recall":
                return self._send(
                    200,
                    g.recall(
                        body.get("query", ""),
                        top_k=int(body.get("top_k", 8)),
                        arms=body.get("arms"),
                    ),
                )
            if path == "/api/remember":
                mid, created = g.remember(
                    content=body.get("content", ""),
                    title=body.get("title", ""),
                    memory_type=body.get("memory_type", "semantic"),
                    tags=body.get("tags", []),
                    source=body.get("source", "dashboard"),
                    importance=float(body.get("importance", 0.5)),
                    pinned=bool(body.get("pinned", False)),
                )
                return self._send(200, {"id": mid, "created": created})
            if path == "/api/link":
                return self._send(200, {"edge_id": g.link(body["src"], body["dst"], body.get("kind", "semantic"), body.get("evidence", "inferred"), float(body.get("confidence", 0.6)), body.get("note", ""))})
            if path == "/api/capture":
                from capture_common import (
                    extract_turns, normalize_since, parse_text_block, remember_turn, today,
                )
                source = str(body.get("source") or "rest:capture")
                target = str(body.get("path") or "")
                if target:
                    since = normalize_since(body.get("since") or today())
                    is_file = os.path.isfile(target)
                    files = [target] if is_file else [
                        str(p) for p in sorted(Path(target).rglob("*"))
                        if p.is_file() and p.suffix.lower() in (".jsonl", ".json", ".txt")
                    ][:int(body.get("max_files", 200))]
                    seen = remembered = duplicates = skipped = 0
                    errors: list[dict[str, str]] = []
                    for item in files:
                        try:
                            for turn in extract_turns(item, since=since):
                                seen += 1
                                outcome = remember_turn(g, turn, source=source)
                                if outcome.get("skipped"):
                                    skipped += 1
                                elif outcome.get("created"):
                                    remembered += 1
                                else:
                                    duplicates += 1
                        except Exception as exc:  # noqa: BLE001
                            errors.append({"path": item, "error": f"{type(exc).__name__}: {exc}"})
                    return self._send(200, {
                        "scanned_files": len(files), "turns_seen": seen,
                        "remembered": remembered, "duplicates": duplicates,
                        "skipped": skipped, "errors": errors,
                    })
                if body.get("user") or body.get("assistant"):
                    turn = {
                        "user": str(body.get("user") or ""),
                        "assistant": str(body.get("assistant") or ""),
                        "date": today(),
                    }
                elif body.get("text"):
                    turn = parse_text_block(str(body["text"]))
                else:
                    return self._send(400, {"error": "need user/assistant, text or path"})
                return self._send(200, remember_turn(g, turn, source=source))
            if path == "/api/import":
                kind = body.get("kind", "markdown")
                if kind == "workbuddy":
                    return self._send(200, g.import_workbuddy(body.get("profile_dir"), body.get("workspace_dir"), int(body.get("days", 180))))
                if kind == "nebula":
                    return self._send(200, g.import_nebula_export(body["path"]))
                if kind == "jsonl":
                    return self._send(200, g.import_jsonl(body["path"]))
                if kind == "folder":
                    return self._send(200, g.import_folder(
                        body["path"], recursive=bool(body.get("recursive", True)),
                        max_files=int(body.get("max_files", 200)), source=body.get("source"),
                    ))
                if kind in ("auto", "file"):
                    p = body["path"]
                    if os.path.isdir(p):
                        return self._send(200, g.import_folder(
                            p, recursive=bool(body.get("recursive", True)),
                            max_files=int(body.get("max_files", 200)), source=body.get("source"),
                        ))
                    return self._send(200, g.import_file(p, body.get("source")))
                return self._send(200, g.import_markdown(body["path"], body.get("source")))
            if path == "/api/consolidate":
                return self._send(200, g.consolidate(float(body.get("decay_days", 90))))
            if path == "/api/backup":
                return self._send(200, {"path": g.backup(body.get("out_dir"))})
            if path == "/api/archive":
                return self._send(200, {"ok": g.archive(body["id"])})
            if path == "/api/pin":
                return self._send(200, {"ok": g.pin(body["id"], bool(body.get("pinned", True)))})
            if path == "/api/forget":
                return self._send(200, {"ok": g.forget(body["id"])})
            return self._send(404, {"error": "not found"})
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})


def main() -> None:
    host = os.environ.get("EM_HOST", "127.0.0.1")
    port = int(os.environ.get("EM_PORT", "8765"))
    _em()
    server = ThreadingHTTPServer((host, port), Handler)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(f"Eternal Memories dashboard: http://{host}:{port}/")
    print(f"Data dir: {_em().data_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
