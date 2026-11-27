"""Eternal Memories · 通用智能体桥接器（零第三方依赖）.

让任意智能体使用长期记忆：
  MCP 智能体      -> 直接用 mcp_server.py（em_* 工具）
  无 MCP 的智能体 -> 用本文件的 prompt / json 子命令，或 REST API
  本地程序        -> 直接 import EternalMemory

用法示例：
  python bridge.py recall "项目交付 关键节点"
  python bridge.py json "项目交付 关键节点" -k 5
  python bridge.py remember "客户偏好周三回访" --title "回访偏好"
  python bridge.py prompt doubao
  python bridge.py serve
  python bridge.py capture --user "问题" --assistant "回答" --source doubao
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from eternal_memory import EternalMemory

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = os.environ.get("EM_DATA_DIR") or str(HERE / "data")

SYSTEM_PROMPT = """你拥有跨会话长期记忆。回答前先检索记忆，把与问题相关的历史结论、用户偏好、在办事项作为已知事实纳入回答；若记忆与当前表述冲突，以用户当前表述为准。不要编造记忆中不存在的事实。"""

PLATFORM_TIPS = {
    "generic": "把下面的记忆块和你的问题一起粘贴给任意智能体即可。",
    "doubao": "豆包网页版/客户端没有插件接口：先执行 `python bridge.py recall \"你的问题\"`，把输出整段复制进豆包对话框。",
    "deepseek": "DeepSeek 网页版同上；若用 API，直接运行 examples/deepseek_client.py，脚本会自动注入记忆。",
    "coze": "扣子/Coze 可用 HTTP 节点调用本地 REST：POST http://127.0.0.1:8765/api/recall 。",
}


def _engine(data_dir: str | None) -> EternalMemory:
    return EternalMemory(data_dir or DEFAULT_DATA)


def _format_prompt(query: str, result: dict[str, Any]) -> str:
    items = result.get("items") or []
    lines = ["【Eternal Memories · 已召回的相关记忆】"]
    if not items:
        lines.append("（暂无相关记忆）")
    for i, item in enumerate(items, 1):
        title = item.get("title") or "未命名"
        content = (item.get("content") or "").replace("\n", " ")[:240]
        arms = "/".join(item.get("arms") or [])
        lines.append(f"{i}. {title} 〔命中臂: {arms}〕\n   {content}")
    pack = (result.get("context_pack") or "").strip()
    if pack:
        lines.append("【可直接注入的上下文】\n" + pack[:1200])
    lines.append("【请回答以下问题】\n" + query)
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(prog="bridge", description="Eternal Memories 通用智能体桥接器")
    p.add_argument("--data-dir", default=None, help="记忆库目录，默认项目内 data/")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("recall", help="输出可粘贴给任意智能体的增强提示词")
    q.add_argument("query")
    q.add_argument("-k", "--top-k", type=int, default=6)

    q = sub.add_parser("json", help="输出召回结果 JSON（程序化接入）")
    q.add_argument("query")
    q.add_argument("-k", "--top-k", type=int, default=6)
    q.add_argument("--arms", nargs="*", help="仅使用指定臂")

    q = sub.add_parser("remember", help="写入一条记忆")
    q.add_argument("content")
    q.add_argument("--title", default="")
    q.add_argument("--type", default="semantic")
    q.add_argument("--tags", default="")
    q.add_argument("--source", default="bridge")

    q = sub.add_parser("import", help="导入本地文件或整个目录为记忆点")
    q.add_argument("path")
    q.add_argument("--source", default="bridge")
    q.add_argument("--max-files", type=int, default=200)
    q.add_argument("--no-recursive", action="store_true")

    q = sub.add_parser("capture", help="把一轮对话或会话目录自动沉淀为记忆")
    q.add_argument("--text", default=None, help="对话文本；不传则从 stdin 读取")
    q.add_argument("--user", default="")
    q.add_argument("--assistant", default="")
    q.add_argument("--path", default=None, help="会话文件/目录，批量沉淀")
    q.add_argument("--since", default="today", help="起始日期，传 all 不过滤")
    q.add_argument("--source", default="bridge:capture")

    q = sub.add_parser("prompt", help="输出可放入智能体 system prompt 的指令")
    q.add_argument("platform", nargs="?", default="generic",
                   choices=sorted(PLATFORM_TIPS.keys()))

    sub.add_parser("stats", help="记忆库统计")
    sub.add_parser("serve", help="启动 REST API + 星云面板（默认 127.0.0.1:8765）")

    args = p.parse_args()

    if args.cmd == "serve":
        os.environ["EM_DATA_DIR"] = args.data_dir or DEFAULT_DATA
        import web_server
        web_server.main()
        return 0

    g = _engine(args.data_dir)
    try:
        if args.cmd == "recall":
            result = g.recall(args.query, top_k=args.top_k, trace=False)
            print(_format_prompt(args.query, result))
        elif args.cmd == "json":
            kwargs: dict[str, Any] = {"top_k": args.top_k, "trace": False}
            if args.arms:
                kwargs["arms"] = args.arms
            print(json.dumps(g.recall(args.query, **kwargs), ensure_ascii=False, indent=2))
        elif args.cmd == "remember":
            tags = [t for t in args.tags.split(",") if t.strip()]
            mid, is_new = g.remember(args.content, args.title, args.type, tags, args.source)
            print(json.dumps({"id": mid, "new": is_new}, ensure_ascii=False))
        elif args.cmd == "import":
            p = Path(args.path)
            if p.is_dir():
                result = g.import_folder(p, recursive=not args.no_recursive,
                                         max_files=args.max_files, source=args.source)
            else:
                result = g.import_file(p, args.source)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.cmd == "capture":
            from capture_common import (
                extract_turns, normalize_since, parse_text_block, remember_turn, today,
            )
            source = args.source
            if args.path:
                since = normalize_since(args.since)
                p = Path(args.path)
                files = [p] if p.is_file() else [
                    f for f in sorted(p.rglob("*"))
                    if f.is_file() and f.suffix.lower() in (".jsonl", ".json", ".txt")
                ]
                summary = {"files": len(files), "remembered": 0, "duplicates": 0, "skipped": 0}
                for f in files:
                    for turn in extract_turns(str(f), since=since):
                        outcome = remember_turn(g, turn, source=source)
                        key = "skipped" if outcome.get("skipped") else ("created" if outcome.get("created") else "duplicate")
                        summary[{"skipped": "skipped", "created": "remembered", "duplicate": "duplicates"}[key]] += 1
                print(json.dumps(summary, ensure_ascii=False, indent=2))
            else:
                raw = args.text if args.text is not None else sys.stdin.read()
                turn = parse_text_block(raw)
                if args.user:
                    turn["user"] = args.user
                if args.assistant:
                    turn["assistant"] = args.assistant
                turn["date"] = today()
                print(json.dumps(remember_turn(g, turn, source=source), ensure_ascii=False, indent=2))
        elif args.cmd == "prompt":
            print(SYSTEM_PROMPT)
            print("\n【平台提示】" + PLATFORM_TIPS[args.platform])
        elif args.cmd == "stats":
            print(json.dumps(g.stats(), ensure_ascii=False, indent=2))
    finally:
        g.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
