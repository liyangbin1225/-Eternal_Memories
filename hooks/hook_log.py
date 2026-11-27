"""钩子可观测性：异常写入 data/hook.log，静默失败但可排障。"""
from __future__ import annotations

import os
import sys
from datetime import datetime


def log_failure(hook: str, exc: BaseException) -> None:
    try:
        data_dir = os.environ.get("EM_DATA_DIR") or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
        )
        os.makedirs(data_dir, exist_ok=True)
        line = "[%s] %s: %s: %s\n" % (
            datetime.now().astimezone().isoformat(timespec="seconds"),
            hook, type(exc).__name__, exc,
        )
        with open(os.path.join(data_dir, "hook.log"), "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:  # noqa: BLE001 - 日志失败绝不影响主流程
        pass
    print("em %s skipped: %s" % (hook, exc), file=sys.stderr)
