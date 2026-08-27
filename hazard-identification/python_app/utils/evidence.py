"""知识库证据的通用清洗。"""

from __future__ import annotations

from typing import Any


def clean_evidence(items: Any) -> list[dict[str, Any]]:
    return [
        item for item in (items or [])
        if isinstance(item, dict) and "演示" not in str(item.get("document") or "")
    ]
