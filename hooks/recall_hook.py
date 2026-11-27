"""WorkBuddy UserPromptSubmit hook：提交提问前自动六臂召回并注入上下文。

输入：WorkBuddy 传入的 JSON（含 prompt）
输出：{"continue":true,"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"..."}}
原则：任何异常都静默放行，绝不阻塞对话；调试信息只写 stderr。
"""

from __future__ import annotations

import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
DATA_DIR = os.environ.get("EM_DATA_DIR") or os.path.join(BASE, "data")
MAX_ITEMS = 5
MAX_CHARS = 260
EMPTY = {
    "continue": True,
    "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ""},
}


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    prompt = str(data.get("prompt") or "").strip()

    context = ""
    # 跳过命令、极短输入与明显的系统占位内容，避免无意义召回
    if len(prompt) >= 3 and not prompt.startswith("/") and "<system-reminder" not in prompt:
        try:
            from eternal_memory import EternalMemory

            em = EternalMemory(DATA_DIR)
            result = em.recall(prompt, top_k=MAX_ITEMS, min_score=0.001, trace=False)
            blocks = []
            for i, item in enumerate(result.get("items", [])[:MAX_ITEMS], 1):
                body = re.sub(r"\s+", " ", str(item.get("content") or ""))[:MAX_CHARS]
                title = str(item.get("title") or "未命名")[:60]
                blocks.append(
                    "[%d] 《%s》(%s｜%s)\n%s"
                    % (i, title, item.get("memory_type") or "semantic", item.get("source") or "", body)
                )
            if blocks:
                context = (
                    "【Eternal Memories 自动召回 · 六臂融合】\n"
                    + "\n".join(blocks)
                    + "\n【以上为历史记忆线索；与用户本轮最新表述冲突时，以本轮表述为准】"
                )
        except Exception as exc:  # noqa: BLE001
            try:
                from hook_log import log_failure
                log_failure("recall", exc)
            except Exception:
                print("em recall hook skipped: %s" % exc, file=sys.stderr)

    print(json.dumps(
        {"continue": True, "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit", "additionalContext": context}},
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print("em recall hook fatal: %s" % exc, file=sys.stderr)
        print(json.dumps(EMPTY, ensure_ascii=False))
        sys.exit(0)
