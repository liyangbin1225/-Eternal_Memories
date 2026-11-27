"""会话沉淀公共逻辑：提取问答轮次、脱敏、幂等写入。

被 hooks/capture_hook.py、auto_capture.py、web_server.py、bridge.py 共用。
兼容 WorkBuddy transcript、Claude Code JSONL 及纯文本对话格式。
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any, Iterable

# 强敏感词：整轮跳过；正则类：脱敏替换后仍沉淀，不因局部敏感信息丢失整条经验。
SENSITIVE = ("薪资", "佣金比例", "身份证号", "密码", "口令", "api key", "secret", "access token")
# 顺序敏感：先长后短，避免 18 位身份证被 11 位手机号正则从中间截断误脱敏。
REDACT = (
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[身份证]"),
    (re.compile(r"(?<!\d)\d{16,19}(?!\d)"), "[卡号]"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机号]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[邮箱]"),
)
SYSTEM_TAGS = re.compile(r"<(system-reminder|task-notification|command-name|user-context)[\s\S]*?</\1>", re.I)
USER_MIN = 4
ASSISTANT_MIN = 30


def clean(text: str) -> str:
    """去除系统标签与敏感信息，压缩空白。"""
    text = SYSTEM_TAGS.sub("", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    for pattern, repl in REDACT:
        text = pattern.sub(repl, text)
    return text


def _text_of(obj: dict[str, Any]) -> str:
    """兼容 str / [{text}] / [{content}] / Claude Code message.content 结构。"""
    content = obj.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str):
                    parts.append(value)
        return " ".join(parts)
    return ""


def _role_of(obj: dict[str, Any]) -> str:
    role = obj.get("role")
    if role in ("user", "assistant"):
        return str(role)
    msg = obj.get("message")
    if isinstance(msg, dict) and msg.get("role") in ("user", "assistant"):
        return str(msg["role"])
    return ""


def _date_of(obj: dict[str, Any]) -> str:
    value = obj.get("timestamp") or obj.get("created_at") or obj.get("ts")
    if value is None:
        return ""
    try:
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > 1e11 else value
            return datetime.fromtimestamp(seconds, timezone.utc).date().isoformat()
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text).date().isoformat()
    except (ValueError, TypeError, OSError, OverflowError):
        return ""


def extract_turns(path: str, since: str | None = None) -> list[dict[str, str]]:
    """从 JSONL 会话文件提取完整问答轮次。

    since 为 YYYY-MM-DD；为空表示不过滤。返回每项含 user/assistant/date。
    """
    turns: list[dict[str, str]] = []
    pending: tuple[str, str] = ("", "")
    with open(path, encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(obj, dict):
                continue
            role = _role_of(obj)
            if not role:
                continue
            text = clean(_text_of(obj))
            if not text:
                continue
            day = _date_of(obj)
            if role == "user":
                pending = (text, day)
            elif role == "assistant" and pending[0]:
                user_text, user_day = pending
                turns.append({"user": user_text, "assistant": text, "date": user_day or day})
                pending = ("", "")
    if since:
        return [t for t in turns if not t["date"] or t["date"] >= since]
    return turns


def parse_text_block(text: str) -> dict[str, str]:
    """解析【用户】/【助手】或 User:/Assistant: 格式的纯文本对话。"""
    text = (text or "").strip()
    patterns = (
        (r"【用户】\s*([\s\S]*?)\s*【助手】\s*([\s\S]*)",),
        (r"(?im)^user\s*[:：]\s*([\s\S]*?)^\s*assistant\s*[:：]\s*([\s\S]*)",),
    )
    for group in patterns:
        for pattern in group:
            match = re.search(pattern, text)
            if match:
                return {"user": clean(match.group(1)), "assistant": clean(match.group(2)), "date": ""}
    return {"user": "", "assistant": clean(text), "date": ""}


def is_valuable(turn: dict[str, str]) -> bool:
    """过滤纯命令、过短轮次与强敏感内容。"""
    user = turn.get("user", "")
    assistant = turn.get("assistant", "")
    merged = (user + "\n" + assistant).lower()
    return (
        len(user) >= USER_MIN
        and len(assistant) >= ASSISTANT_MIN
        and not any(word in merged for word in SENSITIVE)
    )


def build_content(turn: dict[str, str]) -> str:
    return "【用户】%s\n【助手】%s" % (turn.get("user", "")[:700], turn.get("assistant", "")[:1100])


def remember_turn(em: Any, turn: dict[str, str], source: str = "auto-capture", importance: float = 0.55) -> dict[str, Any]:
    """将一轮对话写入记忆；统一脱敏，不合规时返回 skipped，不抛异常。"""
    safe = dict(turn)
    safe["user"] = clean(safe.get("user", ""))
    safe["assistant"] = clean(safe.get("assistant", ""))
    if not is_valuable(safe):
        return {"skipped": True, "reason": "short_or_sensitive"}
    content = build_content(safe)
    mid, created = em.remember(
        content=content,
        title=safe.get("user", "")[:52],
        memory_type="episodic",
        tags=["会话沉淀", "auto"],
        source=source,
        importance=importance,
    )
    return {"skipped": False, "id": mid, "created": created}


def today() -> str:
    return date.today().isoformat()


def normalize_since(value: str | None) -> str | None:
    """统一 since 参数：today -> 今天日期，all/空 -> 不过滤。"""
    if not value:
        return None
    if value == "all":
        return None
    if value == "today":
        return today()
    return value
