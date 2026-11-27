"""WorkBuddy Stop hook：每轮结束后从会话记录提取最后一轮问答，沉淀到 EternalMemory。

输入：WorkBuddy 传入的 JSON（含 transcript_path）
输出：{"continue":true}
原则：只写业务记忆，跳过敏感信息与系统标签；异常静默放行，绝不阻塞收尾。
提取与脱敏逻辑复用 capture_common，与其他智能体的自动沉淀保持一致。
"""
from __future__ import annotations

import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
DATA_DIR = os.environ.get("EM_DATA_DIR") or os.path.join(BASE, "data")
OK = {"continue": True}


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    path = str(data.get("transcript_path") or "")
    if path and os.path.isfile(path):
        try:
            from capture_common import extract_turns, remember_turn

            turns = extract_turns(path)
            if turns:
                result = remember_turn(_engine(), turns[-1], source="workbuddy:hook")
                if result.get("skipped"):
                    pass  # 纯命令、过短轮次或敏感内容：静默跳过
        except Exception as exc:  # noqa: BLE001
            try:
                from hook_log import log_failure
                log_failure("capture", exc)
            except Exception:
                print("em capture hook skipped: %s" % exc, file=sys.stderr)

    print(json.dumps(OK, ensure_ascii=False))
    return 0


def _engine():
    from eternal_memory import EternalMemory
    return EternalMemory(DATA_DIR)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print("em capture hook fatal: %s" % exc, file=sys.stderr)
        print(json.dumps(OK, ensure_ascii=False))
        sys.exit(0)
