"""文本、枚举和时间工具。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from ..config import YES_NO


def as_text(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def nullable_text(value: Any) -> str | None:
    text = as_text(value)
    return text or None


def unique_texts(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        if isinstance(item, dict):
            if item.get("text") is not None:
                text = str(item.get("text") or "").strip()
            elif item.get("risk") is not None or item.get("impact") is not None:
                parts = []
                risk = str(item.get("risk") or "").strip()
                impact = str(item.get("impact") or "").strip()
                if risk:
                    parts.append(risk)
                if impact:
                    parts.append(impact)
                text = "；".join(parts)
            else:
                parts = []
                for key in ("description", "summary", "reason", "value"):
                    value_text = str(item.get(key) or "").strip()
                    if value_text and value_text not in parts:
                        parts.append(value_text)
                text = "；".join(parts)
        else:
            text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def limit_text(value: Any, length: int) -> str | None:
    text = nullable_text(value)
    return text[:length] if text else None


def exact_option(value: Any, options: tuple[str, ...]) -> str | None:
    text = nullable_text(value)
    if not text:
        return None
    for option in options:
        if text == option or option in text:
            return option
    return None


def yes_no(value: Any) -> str | None:
    return exact_option(value, YES_NO)


def valid_date(value: Any) -> str | None:
    text = nullable_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
