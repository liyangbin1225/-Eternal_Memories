"""Eternal Memories - 命令行入口."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eternal_memory import EternalMemory


def _out(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    p = argparse.ArgumentParser(prog="em", description="永恒记忆系统 Eternal Memories")
    p.add_argument("--data-dir", default=None, help="数据目录，默认项目内 data/")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="初始化记忆库")

    q = sub.add_parser("recall", help="六臂召回")
    q.add_argument("query")
    q.add_argument("-k", "--top-k", type=int, default=8)
    q.add_argument("--arms", nargs="*", help="仅使用指定臂")
    q.add_argument("--compact", action="store_true")

    q = sub.add_parser("remember", help="写入记忆")
    q.add_argument("content")
    q.add_argument("--title", default="")
    q.add_argument("--type", default="semantic")
    q.add_argument("--tags", default="")
    q.add_argument("--source", default="cli")
    q.add_argument("--importance", type=float, default=0.5)
    q.add_argument("--pinned", action="store_true")

    q = sub.add_parser("link", help="建立关系")
    q.add_argument("src")
    q.add_argument("dst")
    q.add_argument("--kind", default="semantic")
    q.add_argument("--evidence", default="inferred")
    q.add_argument("--confidence", type=float, default=0.6)

    q = sub.add_parser("import", help="导入数据（文件或目录自动识别）")
    q.add_argument("path", nargs="?", default="")
    q.add_argument("--kind", choices=["auto", "markdown", "jsonl", "nebula", "workbuddy"], default="auto")
    q.add_argument("--source", default="")
    q.add_argument("--days", type=int, default=180)
    q.add_argument("--workspace", default="")
    q.add_argument("--max-files", type=int, default=200, help="目录导入最多处理文件数")
    q.add_argument("--no-recursive", action="store_true", help="目录导入不递归子目录")

    sub.add_parser("stats", help="统计概览")
    sub.add_parser("graph", help="导出星图数据 JSON")
    sub.add_parser("conflicts", help="列出可疑矛盾")
    sub.add_parser("profile", help="用户画像记忆")

    q = sub.add_parser("consolidate", help="记忆巩固")
    q.add_argument("--decay-days", type=float, default=90)

    q = sub.add_parser("export", help="导出备份")
    q.add_argument("--format", choices=["json", "markdown"], default="json")
    q.add_argument("--path", default="")

    q = sub.add_parser("backup", help="备份数据库")
    q.add_argument("--out-dir", default="")

    sub.add_parser("serve", help="启动 REST + 星云面板")
    sub.add_parser("mcp", help="启动 MCP stdio 服务")

    args = p.parse_args()

    if args.cmd == "mcp":
        import mcp_server

        mcp_server.main()
        return
    if args.cmd == "serve":
        import web_server

        web_server.main()
        return

    g = EternalMemory(args.data_dir)
    try:
        if args.cmd == "init":
            _out({"ok": True, "data_dir": str(g.data_dir), "db": str(g.db_path)})
        elif args.cmd == "recall":
            res = g.recall(args.query, top_k=args.top_k, arms=args.arms)
            if args.compact:
                _out(
                    {
                        "arms": res["arm_counts"],
                        "items": [
                            {"id": i["id"], "title": i["title"], "score": i["score"], "arms": i["arms"]}
                            for i in res["items"]
                        ],
                    }
                )
            else:
                _out(res)
        elif args.cmd == "remember":
            mid, created = g.remember(
                args.content,
                args.title,
                args.type,
                args.tags,
                args.source,
                importance=args.importance,
                pinned=args.pinned,
            )
            _out({"id": mid, "created": created})
        elif args.cmd == "link":
            _out({"edge_id": g.link(args.src, args.dst, args.kind, args.evidence, args.confidence)})
        elif args.cmd == "import":
            if args.path and Path(args.path).is_dir() and args.kind == "auto":
                _out(g.import_folder(args.path, recursive=not args.no_recursive,
                                     max_files=args.max_files, source=args.source or None))
            elif args.kind == "workbuddy":
                home_cfg = Path.home() / ".workbuddy"
                profiles = sorted(p for p in home_cfg.glob("user-*") if (p / "MEMORY.md").exists())
                _out(
                    g.import_workbuddy(
                        str(profiles[-1]) if profiles else str(home_cfg),
                        args.workspace or str(Path.cwd()),
                        args.days,
                    )
                )
            elif args.kind == "nebula":
                _out(g.import_nebula_export(args.path))
            elif args.kind == "jsonl":
                _out(g.import_jsonl(args.path))
            elif args.kind in ("auto", "file"):
                _out(g.import_file(args.path, args.source or None))
            else:
                _out(g.import_markdown(args.path, args.source or None))
        elif args.cmd == "stats":
            _out(g.stats())
        elif args.cmd == "graph":
            _out(g.graph_data())
        elif args.cmd == "conflicts":
            _out({"items": g.find_conflicts()})
        elif args.cmd == "profile":
            _out(g.profile())
        elif args.cmd == "consolidate":
            _out(g.consolidate(args.decay_days))
        elif args.cmd == "export":
            if args.format == "markdown":
                _out({"path": g.export_markdown(args.path or (g.data_dir / "vault"))})
            else:
                _out(g.export_json(args.path or None))
        elif args.cmd == "backup":
            _out({"path": g.backup(args.out_dir or None)})
    finally:
        g.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
