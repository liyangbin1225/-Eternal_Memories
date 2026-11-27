"""跨智能体会话自动沉淀器：把当天会话记录变成记忆点。

支持三类智能体：
  有本地会话文件的（WorkBuddy / Claude Code / Cursor 导出的 JSONL）-> once / watch
  能发 HTTP 的（扣子 / Dify / n8n / 自研 Agent）                -> web_server /api/capture
  无插件无文件但能复制文本的（豆包 / DeepSeek 网页版）          -> text 子命令

示例：
  python auto_capture.py once "D:\\会话记录" --since today
  python auto_capture.py watch "D:\\会话记录" --interval 60
  echo "【用户】xxx【助手】yyy" | python auto_capture.py text --source doubao
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from capture_common import extract_turns, normalize_since, parse_text_block, remember_turn, today
from eternal_memory import EternalMemory

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = os.environ.get("EM_DATA_DIR") or str(HERE / "data")
EXTENSIONS = {".jsonl", ".json", ".txt"}
DEFAULT_STATE_NAME = "capture_state.json"


def _engine(data_dir: str) -> EternalMemory:
    return EternalMemory(data_dir)


def _state_path(data_dir: str, override: str | None) -> Path:
    return Path(override) if override else Path(data_dir) / DEFAULT_STATE_NAME


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


def _targets(path: str) -> list[Path]:
    p = Path(path)
    if p.is_file():
        return [p]
    if not p.is_dir():
        return []
    return [item for item in sorted(p.rglob("*")) if item.is_file() and item.suffix.lower() in EXTENSIONS]


def scan(
    path: str,
    em: EternalMemory,
    state: dict[str, Any],
    since: str | None = None,
    source: str = "auto-capture",
) -> dict[str, Any]:
    """扫描会话文件，只沉淀上次之后新增的完整轮次。"""
    result: dict[str, Any] = {
        "scanned_files": 0, "turns_seen": 0, "remembered": 0,
        "duplicates": 0, "skipped": 0, "errors": [],
    }
    for file in _targets(path):
        key = str(file)
        try:
            stat = file.stat()
            previous = state.get(key) or {}
            turns = extract_turns(key, since=since)
            result["scanned_files"] += 1
            result["turns_seen"] += len(turns)
            processed = int(previous.get("processed", 0) or 0)
            if float(previous.get("size", 0)) > stat.st_size or len(turns) < processed:
                processed = 0  # 文件被重写或轮次减少：从头重新对齐，靠幂等去重兜底
            for turn in turns[processed:]:
                outcome = remember_turn(em, turn, source=source)
                if outcome.get("skipped"):
                    result["skipped"] += 1
                elif outcome.get("created"):
                    result["remembered"] += 1
                else:
                    result["duplicates"] += 1
            state[key] = {"size": stat.st_size, "mtime": stat.st_mtime, "processed": len(turns)}
        except Exception as exc:  # noqa: BLE001 - 单文件失败不阻断整批
            result["errors"].append({"path": key, "error": f"{type(exc).__name__}: {exc}"})
    return result


def run_once(args: argparse.Namespace, em: EternalMemory, state_path: Path) -> dict[str, Any]:
    state = _load_state(state_path)
    result = scan(args.path, em, state, since=args.since, source=args.source)
    if args.since == today() and not _targets(args.path):
        result["errors"].append({"path": args.path, "error": "no session files found"})
    _save_state(state_path, state)
    return result


def run_text(args: argparse.Namespace, em: EternalMemory) -> dict[str, Any]:
    raw = args.text
    if raw is None:
        raw = sys.stdin.read()
    turn = parse_text_block(raw)
    if args.user:
        turn["user"] = args.user
    if args.assistant:
        turn["assistant"] = args.assistant
    turn["date"] = today()
    outcome = remember_turn(em, turn, source=args.source)
    return {"turn": {"user": turn["user"][:120]}, **outcome}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="auto_capture", description="跨智能体会话自动沉淀器")
    p.add_argument("--data-dir", default=DEFAULT_DATA, help="记忆库目录，默认项目内 data/")
    p.add_argument("--state", default=None, help="扫描进度状态文件，默认 data/capture_state.json")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("once", help="扫描一次会话目录，沉淀当天新增轮次")
    q.add_argument("path", help="会话文件目录或单个 JSONL 文件")
    q.add_argument("--since", default="today", help="起始日期 YYYY-MM-DD；传 all 表示不过滤")
    q.add_argument("--source", default="auto-capture")

    q = sub.add_parser("watch", help="常驻监听会话目录，按间隔增量沉淀")
    q.add_argument("path")
    q.add_argument("--interval", type=int, default=60, help="轮询秒数，默认 60")
    q.add_argument("--since", default="today")
    q.add_argument("--source", default="auto-capture")

    q = sub.add_parser("text", help="把一轮对话文本沉淀为记忆")
    q.add_argument("--text", default=None, help="对话文本；不传则从 stdin 读取")
    q.add_argument("--user", default="")
    q.add_argument("--assistant", default="")
    q.add_argument("--source", default="auto-capture")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if hasattr(args, "since"):
        args.since = normalize_since(args.since)
    state_path = _state_path(args.data_dir, args.state)
    em = _engine(args.data_dir)
    try:
        if args.cmd == "text":
            print(json.dumps(run_text(args, em), ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "watch":
            print("watching %s every %ss (Ctrl+C to stop)" % (args.path, args.interval))
            try:
                while True:
                    state = _load_state(state_path)
                    result = scan(args.path, em, state, since=args.since, source=args.source)
                    _save_state(state_path, state)
                    print(json.dumps(result, ensure_ascii=False))
                    if result["remembered"] or result["duplicates"] or result["errors"]:
                        sys.stdout.flush()
                    time.sleep(max(1, args.interval))
            except KeyboardInterrupt:
                print("stopped")
                return 0
        print(json.dumps(run_once(args, em, state_path), ensure_ascii=False, indent=2))
        return 0
    finally:
        em.close()


if __name__ == "__main__":
    raise SystemExit(main())
