"""DeepSeek / OpenAI 兼容 API 的读写双向自动记忆示例（仅标准库）。

流程：本地召回 -> 注入 system -> 请求模型 -> 自动沉淀本轮问答。
设置 DEEPSEEK_API_KEY 后运行：
  python examples/auto_memory_client.py "项目交付计划怎么安排？"

只要把本文件的 _ask() 换成你的智能体调用，即可给任意 API 智能体加上自动记忆。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from capture_common import remember_turn, today  # noqa: E402
from eternal_memory import EternalMemory  # noqa: E402

API_URL = os.environ.get("EM_API_URL", "https://api.deepseek.com/chat/completions")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MODEL = os.environ.get("EM_API_MODEL", "deepseek-chat")


def _ask(question: str, context_pack: str) -> str:
    """调用 OpenAI 兼容 chat/completions；无 key 时返回演示文本。"""
    if not API_KEY:
        return "（演示模式：未设置 DEEPSEEK_API_KEY，这里是占位回答。）"
    import urllib.request

    system = (
        "你是用户的长期记忆助手。以下是从本地记忆库召回的相关事实，请作为已知信息：\n"
        + (context_pack or "（暂无相关记忆）")
    )
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=payload,
        headers={"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python examples/auto_memory_client.py \"你的问题\"")
        return 1
    question = sys.argv[1]
    data_dir = os.environ.get("EM_DATA_DIR") or str(ROOT / "data")
    em = EternalMemory(data_dir)
    try:
        recalled = em.recall(question, top_k=5, trace=False)
        context = recalled.get("context_pack") or ""
        print("【召回】命中 %d 条记忆" % len(recalled.get("items") or []))
        answer = _ask(question, context)
        print("\n【回答】\n" + answer)
        turn = {"user": question, "assistant": answer, "date": today()}
        outcome = remember_turn(em, turn, source="deepseek-api:auto")
        print("\n【沉淀】" + json.dumps(outcome, ensure_ascii=False))
        return 0
    finally:
        em.close()


if __name__ == "__main__":
    raise SystemExit(main())
