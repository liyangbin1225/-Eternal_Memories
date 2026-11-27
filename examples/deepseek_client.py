"""DeepSeek API 示例：调用前自动注入 Eternal Memories 记忆（零第三方依赖）.

用法：
    set DEEPSEEK_API_KEY=sk-xxx          (Windows)
    export DEEPSEEK_API_KEY=sk-xxx       (macOS/Linux)
    python examples/deepseek_client.py "项目交付计划怎么安排？"

说明：脚本先在本地召回相关记忆，再作为 system 消息注入 DeepSeek 请求。
记忆数据永不上传，只有召回后的文本随提问发给模型服务商。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eternal_memory import EternalMemory  # noqa: E402

API = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
SYSTEM = (
    "你拥有跨会话长期记忆。回答前优先依据注入的记忆事实；"
    "若记忆与用户当前表述冲突，以当前表述为准；不要编造未提供的信息。"
)


def recall_block(query: str, top_k: int = 5) -> str:
    g = EternalMemory(os.environ.get("EM_DATA_DIR") or str(ROOT / "data"))
    try:
        r = g.recall(query, top_k=top_k, trace=False)
    finally:
        g.close()
    lines = []
    for i, item in enumerate(r.get("items") or [], 1):
        lines.append("[%d] 《%s》\n%s" % (i, item.get("title", ""), (item.get("content") or "")[:300]))
    return "\n".join(lines) or "（无相关记忆）"


def ask(query: str) -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("请先设置环境变量 DEEPSEEK_API_KEY")
    memory = recall_block(query)
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM + "\n\n【长期记忆】\n" + memory},
            {"role": "user", "content": query},
        ],
        "stream": False,
    }
    req = Request(
        API,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST",
    )
    with urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "帮我梳理当前在办事项"
    print(ask(q))
