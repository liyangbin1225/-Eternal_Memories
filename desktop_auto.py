"""桌面客户端自动记忆探测器：豆包 / DeepSeek 客户端会话发现与增量沉淀。

两类全自动通路：
  1. 客户端支持 MCP（豆包自定义连接器、DeepSeek Harness 等）
     -> 挂载 mcp_server.py，并在客户端「技能/人设」中写入自动沉淀指令，
        每轮结束由模型调用 em_capture_turn，直接全自动。
  2. 客户端把会话存成 SQLite / JSON / JSONL（多数开源 DeepSeek 桌面端）
     -> 本脚本 detect 找到会话文件，watch 增量扫描并沉淀，无需人工干预。

豆包官方桌面端把会话写在 Chromium IndexedDB（LevelDB + Snappy + V8 序列化），
标准库无法可靠解析；detect 会明确提示走 MCP 通路，不做假解析。

用法：
  python desktop_auto.py detect
  python desktop_auto.py once --source deepseek-desktop
  python desktop_auto.py watch --interval 60 --source deepseek-desktop
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from capture_common import clean, is_valuable, normalize_since, remember_turn, today
from eternal_memory import EternalMemory

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = os.environ.get("EM_DATA_DIR") or str(HERE / "data")
STATE_NAME = "desktop_state.json"
SCAN_EXT = {".db", ".sqlite", ".sqlite3", ".json", ".jsonl", ".txt"}


def candidate_roots() -> dict[str, list[Path]]:
    """按平台约定列出豆包 / DeepSeek 客户端可能的用户数据目录。"""
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA") or (home / ".local" / "share"))
    appdata = Path(os.environ.get("APPDATA") or (home / ".config"))
    return {
        "doubao": [
            local / "Doubao" / "User Data",
            appdata / "Doubao",
            home / ".config" / "Doubao",
        ],
        "deepseek": [
            appdata / "DeepSeek",
            appdata / "DeepSeek-Coder",
            local / "DeepSeek",
            home / ".deepseek",
            home / ".dsh",
            home / ".config" / "DeepSeek",
        ],
    }


def _leveldb_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [
        p for p in root.rglob("*.indexeddb.leveldb")
        if "IndexedDB" in p.parts
    ]


def _scannable_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    files: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in SCAN_EXT:
            continue
        if any(part.startswith(".") or part in ("Cache", "Code Cache", "GPUCache") for part in p.parts):
            continue
        try:
            if p.stat().st_size > 200_000_000:
                continue
        except OSError:
            continue
        files.append(p)
    return files[:200]


def detect() -> dict[str, Any]:
    report: dict[str, Any] = {"detected_at": today(), "platforms": {}, "recommendation": ""}
    for name, roots in candidate_roots().items():
        items = []
        for root in roots:
            if not root.exists():
                continue
            levels = _leveldb_dirs(root)
            files = _scannable_files(root)
            items.append({
                "root": str(root),
                "leveldb": [str(p) for p in levels],
                "scannable": [str(p) for p in files],
                "mode": "mcp" if levels and not files else ("file" if files else "empty"),
            })
        report["platforms"][name] = items
    all_mcp = any(
        item["mode"] == "mcp"
        for items in report["platforms"].values() for item in items
    )
    all_file = any(
        item["mode"] == "file"
        for items in report["platforms"].values() for item in items
    )
    if all_file:
        report["recommendation"] = "发现可解析的会话文件，运行 desktop_auto.py watch 即可全自动沉淀。"
    elif all_mcp:
        report["recommendation"] = (
            "客户端会话存于 Chromium IndexedDB（LevelDB/Snappy/V8），标准库无法可靠解析。"
            "请挂载 mcp_server.py 并在客户端技能/人设中写入自动沉淀指令，见 configs/doubao-mcp.md。"
        )
    else:
        report["recommendation"] = "未发现本地会话数据，请检查客户端是否已登录并产生对话，或使用 MCP 通路。"
    return report


def _sqlite_turns(path: Path) -> list[dict[str, str]]:
    """只读打开 SQLite，识别含 role/content 的表并配对问答。"""
    turns: list[dict[str, str]] = []
    uri = "file:%s?mode=ro" % path.as_posix().replace("?", "%3f")
    conn = sqlite3.connect(uri, uri=True)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            cols = [r[1] for r in conn.execute('PRAGMA table_info("%s")' % table.replace('"', ""))]
            if "role" not in cols or "content" not in cols:
                continue
            try:
                rows = conn.execute(
                    'SELECT rowid, role, content FROM "%s" ORDER BY rowid' % table.replace('"', "")
                ).fetchall()
            except sqlite3.Error:
                continue
            pending = ""
            for _rid, role, content in rows:
                if role not in ("user", "assistant"):
                    continue
                text = clean(str(content or ""))
                if not text:
                    continue
                if role == "user":
                    pending = text
                elif pending:
                    turns.append({"user": pending, "assistant": text, "date": ""})
                    pending = ""
            if turns:
                break
    finally:
        conn.close()
    return turns


def _json_turns(path: Path) -> list[dict[str, str]]:
    """兼容 [{"role":"user","content":"..."}] 与单条 JSONL 之外的数组格式。"""
    if path.suffix.lower() == ".jsonl":
        from capture_common import extract_turns
        return extract_turns(str(path))
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    turns: list[dict[str, str]] = []
    pending = ""
    for item in data:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in ("user", "assistant"):
            continue
        text = clean(str(item.get("content") or ""))
        if not text:
            continue
        if role == "user":
            pending = text
        elif pending:
            turns.append({"user": pending, "assistant": text, "date": ""})
            pending = ""
    return turns


def scan(roots: Iterable[Path], em: EternalMemory, state: dict[str, Any], source: str) -> dict[str, Any]:
    summary: dict[str, Any] = {"files": 0, "remembered": 0, "duplicates": 0, "skipped": 0, "errors": []}
    for root in roots:
        for file in _scannable_files(root):
            key = str(file)
            try:
                ext = file.suffix.lower()
                if ext in (".db", ".sqlite", ".sqlite3"):
                    turns = _sqlite_turns(file)
                else:
                    turns = _json_turns(file)
                if not turns:
                    continue
                summary["files"] += 1
                processed = int((state.get(key) or {}).get("processed", 0) or 0)
                if len(turns) < processed:
                    processed = 0
                for turn in turns[processed:]:
                    if not is_valuable(turn):
                        summary["skipped"] += 1
                        continue
                    outcome = remember_turn(em, turn, source=source)
                    if outcome.get("skipped"):
                        summary["skipped"] += 1
                    elif outcome.get("created"):
                        summary["remembered"] += 1
                    else:
                        summary["duplicates"] += 1
                state[key] = {"processed": len(turns)}
            except Exception as exc:  # noqa: BLE001 - 单文件失败不阻断
                summary["errors"].append({"path": key, "error": f"{type(exc).__name__}: {exc}"})
    return summary


def _state_path(data_dir: str) -> Path:
    return Path(data_dir) / STATE_NAME


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(prog="desktop_auto", description="豆包/DeepSeek 桌面客户端自动记忆")
    p.add_argument("--data-dir", default=DEFAULT_DATA)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("detect", help="探测本机客户端会话存储并给出接入建议")
    q = sub.add_parser("once", help="扫描一次可解析的客户端会话文件")
    q.add_argument("--source", default="desktop:auto")
    q = sub.add_parser("watch", help="常驻增量扫描可解析的客户端会话文件")
    q.add_argument("--source", default="desktop:auto")
    q.add_argument("--interval", type=int, default=60)
    args = p.parse_args()

    if args.cmd == "detect":
        print(json.dumps(detect(), ensure_ascii=False, indent=2))
        return 0

    state_path = _state_path(args.data_dir)
    em = EternalMemory(args.data_dir)
    try:
        files_roots = [
            root for items in detect()["platforms"].values()
            for item in items for root in [Path(item["root"])]
        ]
        while True:
            state = _load_state(state_path)
            result = scan(files_roots, em, state, args.source)
            _save_state(state_path, state)
            print(json.dumps(result, ensure_ascii=False))
            sys.stdout.flush()
            if args.cmd == "once":
                break
            time.sleep(max(1, args.interval))
        return 0
    except KeyboardInterrupt:
        print("stopped")
        return 0
    finally:
        em.close()


if __name__ == "__main__":
    raise SystemExit(main())
