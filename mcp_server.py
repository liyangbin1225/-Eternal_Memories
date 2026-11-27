"""Eternal Memories - MCP stdio server（零第三方依赖，手写 JSON-RPC 2.0）."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from eternal_memory import ARMS, EternalMemory

VERSION = "1.0.0"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "em_health",
        "description": "检查记忆引擎状态、数据目录与统计概览。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "em_recall",
        "description": "动手前先召回：六臂融合检索个人记忆，返回命中、分臂分数与可直接使用的上下文包。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "自然语言查询"},
                "top_k": {"type": "integer", "default": 8, "minimum": 1, "maximum": 40},
                "arms": {"type": "array", "items": {"type": "string", "enum": list(ARMS)}, "description": "只启用指定召回臂"},
                "compact": {"type": "boolean", "default": False, "description": "只返回精简字段，节省 token"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "em_remember",
        "description": "写入一条长期记忆。同 source+content 幂等，重复写入不产生新记录。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "title": {"type": "string", "default": ""},
                "memory_type": {"type": "string", "enum": ["semantic", "episodic", "procedural", "preference", "fact", "identity"], "default": "semantic"},
                "tags": {"type": "array", "items": {"type": "string"}, "default": []},
                "source": {"type": "string", "default": "mcp"},
                "importance": {"type": "number", "default": 0.5},
                "pinned": {"type": "boolean", "default": False},
            },
            "required": ["content"],
        },
    },
    {
        "name": "em_capture_turn",
        "description": "自动沉淀一轮客户端对话（用户问题 + 智能体回答），统一脱敏与敏感过滤，供豆包/DeepSeek 桌面端每轮结束调用。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user": {"type": "string", "description": "用户本轮问题"},
                "assistant": {"type": "string", "description": "智能体本轮回答"},
                "source": {"type": "string", "default": "desktop:mcp"},
            },
            "required": ["user", "assistant"],
        },
    },
    {
        "name": "em_link",
        "description": "连接两条记忆，支持 temporal/entity/causal/semantic 四类关系与来源证据标记。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "src": {"type": "string"},
                "dst": {"type": "string"},
                "kind": {"type": "string", "enum": ["temporal", "entity", "causal", "semantic"], "default": "semantic"},
                "evidence": {"type": "string", "enum": ["extracted", "inferred", "ambiguous"], "default": "inferred"},
                "confidence": {"type": "number", "default": 0.6},
                "note": {"type": "string", "default": ""},
            },
            "required": ["src", "dst"],
        },
    },
    {
        "name": "em_import_workbuddy",
        "description": "只读导入 WorkBuddy 用户 MEMORY.md、工作区记忆日志与外部记忆导出包。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "profile_dir": {"type": "string", "description": "WorkBuddy profile 目录，默认自动探测"},
                "workspace_dir": {"type": "string", "description": "工作区根目录，默认当前工作目录"},
                "days": {"type": "integer", "default": 180},
            },
        },
    },
    {
        "name": "em_import_file",
        "description": "导入本地文件：auto 按扩展名识别 md/txt/html/eml/json/jsonl。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "kind": {"type": "string", "enum": ["auto", "markdown", "jsonl", "nebula"], "default": "auto"},
                "source": {"type": "string", "default": ""},
            },
            "required": ["path"],
        },
    },
    {
        "name": "em_import_folder",
        "description": "批量把本地目录内文件变成记忆点：自动识别 md/txt/html/eml/json/jsonl，跳过隐藏与噪声目录，内容哈希幂等。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "本地目录绝对路径"},
                "recursive": {"type": "boolean", "default": True},
                "max_files": {"type": "integer", "default": 200},
                "source": {"type": "string", "default": ""},
            },
            "required": ["path"],
        },
    },
    {
        "name": "em_consolidate",
        "description": "执行记忆巩固：重要度衰减、访问提升、过期归档、共享标签自动建边。",
        "inputSchema": {
            "type": "object",
            "properties": {"decay_days": {"type": "number", "default": 90}},
        },
    },
    {
        "name": "em_conflicts",
        "description": "列出可疑矛盾记忆（同主题肯定/否定共现），只报告不删除。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "em_stats",
        "description": "返回记忆总数、边分布、证据分布、召回次数等统计。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "em_graph",
        "description": "返回星图渲染所需的节点与边数据。",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 300}},
        },
    },
    {
        "name": "em_profile",
        "description": "返回用户画像类与置顶类记忆，便于快速加载长期偏好。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "em_export",
        "description": "导出全量 JSON 备份或可被 iwe 索引的 Markdown 双链库。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["json", "markdown"], "default": "json"},
                "path": {"type": "string", "description": "输出路径；JSON 可省略（直接返回数据）"},
            },
            "required": ["format"],
        },
    },
    {
        "name": "em_backup",
        "description": "备份 SQLite 数据库到指定目录，返回备份文件路径。",
        "inputSchema": {
            "type": "object",
            "properties": {"out_dir": {"type": "string", "default": ""}},
        },
    },
]


def _default_profile_dir() -> str:
    home = Path.home()
    candidates = sorted(p for p in (home / ".workbuddy").glob("user-*") if (p / "MEMORY.md").exists())
    return str(candidates[-1]) if candidates else str(home / ".workbuddy")


class Server:
    def __init__(self, data_dir: str | None = None):
        self.em = EternalMemory(data_dir or os.environ.get("EM_DATA_DIR"))

    def handle(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}
        if mid is None:
            return None
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "protocolVersion": params.get("protocolVersion") or "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "eternal-memories", "version": VERSION},
                },
            }
        if method == "ping":
            return {"jsonrpc": "2.0", "id": mid, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            try:
                result = self.call(name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                        "isError": False,
                    },
                }
            except Exception as exc:  # noqa: BLE001 - MCP 边界必须转成 isError
                return {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {
                        "content": [{"type": "text", "text": f"ERROR: {type(exc).__name__}: {exc}"}],
                        "isError": True,
                    },
                }
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Unknown method: {method}"}}

    def call(self, name: str, args: dict[str, Any]) -> Any:
        g = self.em
        if name == "em_health":
            return {"ok": True, "version": VERSION, "data_dir": str(g.data_dir), "stats": g.stats()}
        if name == "em_recall":
            res = g.recall(
                args["query"],
                top_k=int(args.get("top_k", 8)),
                arms=args.get("arms"),
            )
            if args.get("compact"):
                return {
                    "query": res["query"],
                    "arms": res["arms"],
                    "arm_counts": res["arm_counts"],
                    "items": [
                        {"id": i["id"], "title": i["title"], "content": i["content"][:300], "score": i["score"], "arms": i["arms"]}
                        for i in res["items"]
                    ],
                }
            return res
        if name == "em_remember":
            mid, created = g.remember(
                content=args["content"],
                title=args.get("title", ""),
                memory_type=args.get("memory_type", "semantic"),
                tags=args.get("tags", []),
                source=args.get("source", "mcp"),
                importance=float(args.get("importance", 0.5)),
                pinned=bool(args.get("pinned", False)),
            )
            return {"id": mid, "created": created}
        if name == "em_capture_turn":
            from capture_common import remember_turn, today
            return remember_turn(
                g,
                {
                    "user": str(args.get("user") or ""),
                    "assistant": str(args.get("assistant") or ""),
                    "date": today(),
                },
                source=str(args.get("source") or "desktop:mcp"),
            )
        if name == "em_link":
            return {"edge_id": g.link(args["src"], args["dst"], args.get("kind", "semantic"), args.get("evidence", "inferred"), float(args.get("confidence", 0.6)), args.get("note", ""))}
        if name == "em_import_workbuddy":
            return g.import_workbuddy(
                profile_dir=args.get("profile_dir") or _default_profile_dir(),
                workspace_dir=args.get("workspace_dir") or os.getcwd(),
                days=int(args.get("days", 180)),
            )
        if name == "em_import_file":
            kind = args.get("kind", "auto")
            path = args["path"]
            if kind == "auto":
                return g.import_file(path, source=args.get("source") or None)
            if kind == "nebula":
                return g.import_nebula_export(path)
            if kind == "jsonl":
                return g.import_jsonl(path)
            return g.import_markdown(path, source=args.get("source") or None)
        if name == "em_import_folder":
            return g.import_folder(
                args["path"], recursive=bool(args.get("recursive", True)),
                max_files=int(args.get("max_files", 200)), source=args.get("source") or None,
            )
        if name == "em_consolidate":
            return g.consolidate(float(args.get("decay_days", 90)))
        if name == "em_conflicts":
            conflicts = g.find_conflicts()
            return {"count": len(conflicts), "items": conflicts}
        if name == "em_stats":
            return g.stats()
        if name == "em_graph":
            return g.graph_data(int(args.get("limit", 300)))
        if name == "em_profile":
            return g.profile()
        if name == "em_export":
            fmt = args.get("format", "json")
            path = args.get("path")
            if fmt == "markdown":
                return {"path": g.export_markdown(path or (g.data_dir / "vault"))}
            return g.export_json(path)
        if name == "em_backup":
            return {"path": g.backup(args.get("out_dir") or None)}
        raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    server = Server()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):  # 合法 JSON 标量/数组不是合法 JSON-RPC 消息，直接跳过
            continue
        try:
            resp = server.handle(msg)
        except Exception as exc:  # noqa: BLE001 - 任何方法异常都转成 JSON-RPC error，保证 stdio 循环不中断
            resp = {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "error": {"code": -32603, "message": f"{type(exc).__name__}: {exc}"},
            }
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
