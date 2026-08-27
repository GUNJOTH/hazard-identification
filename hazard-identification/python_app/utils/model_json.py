"""模型 JSON 输出解析。"""

from __future__ import annotations

import json
import re
from typing import Any


def parse_model_json(content: Any) -> dict[str, Any]:
    if isinstance(content, list):
        content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    if not isinstance(content, str):
        return {"parse_error": "模型返回内容不是文本", "raw_content": content}
    cleaned = re.sub(r"^```json\s*", "", content.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {"raw_content": parsed}
    except json.JSONDecodeError:
        return {"parse_error": "模型未返回合法 JSON", "raw_content": content}
