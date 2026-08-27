"""视觉模型调用、图片识别与区域坐标处理。"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any

from ..config import CONFIG, HAZARD_CATEGORIES, HAZARD_TYPES
from ..errors import UpstreamError
from ..utils.geometry import normalize_regions
from ..utils.images import image_mime_type
from ..utils.model_json import parse_model_json
from .http_client import request_json


def extraction_prompt(image_count: int) -> str:
    category_text = "、".join(HAZARD_CATEGORIES)
    type_text = "、".join(HAZARD_TYPES)
    return f"""
你是工业现场隐患识别助手。输入的 {image_count} 张图片属于同一处隐患的不同角度，只生成一条隐患记录。
只依据图片可见事实，不臆测设备编码、责任人、责任部门、整改期限、是否集团统计和法定重大隐患结论。
隐患类别只能从以下值中选择：{category_text}；无法确定时为 null。
隐患类型只能从以下值中选择：{type_text}；无法确定时为 null。
请返回严格 JSON，不要 Markdown，字段必须包括：
hazard_description: 隐患描述，最多 500 字；
hazard_category: 隐患类别枚举值或 null；
hazard_type: 隐患类型枚举值或 null；
location: 图片能确认的检查地点或区域，无法确认时为 null；
equipment_name: 图片能辨识的设备或对象通用名称，无法确认时为 null；
special_equipment_involved: 仅在图片有明确证据时返回“是”或“否”，否则为 null；
observations: 合并去重的可见现象数组；
suggested_actions: 整改建议数组；
confidence: 0 到 1 的整体识别置信度。
regions: 隐患区域数组。每个元素必须包含 image_index（从 0 开始）、label、confidence、bbox、polygon、description；
bbox 使用 [x1,y1,x2,y2]，polygon 使用 [[x,y], ...]，坐标原点为图片左上角，所有坐标必须归一化到 0 到 1；
只标注图片中可以看见的主要隐患区域，无法可靠定位时返回空数组；同一处隐患的不同图片分别填写对应的 image_index。
不要输出 hazard_level，隐患等级必须由知识库规则生成。
""".strip()


async def request_vision_completion(messages: list[dict[str, Any]], *, max_tokens: int = 1200) -> dict[str, Any]:
    request_body = {
        "model": CONFIG.vision_model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    last_error: UpstreamError | None = None
    for attempt in range(3):
        try:
            payload = await request_json(
                f"{CONFIG.vision_base_url}/chat/completions",
                method="POST",
                headers={
                    "Authorization": f"Bearer {CONFIG.vision_api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                body=request_body,
                timeout=60,
            )
            break
        except UpstreamError as error:
            last_error = error
            if not error.retryable or attempt == 2:
                raise
            await asyncio.sleep(1.5 * (attempt + 1))
    else:
        raise last_error or UpstreamError("视觉模型请求失败")
    content = payload.get("choices", [{}])[0].get("message", {}).get("content") if isinstance(payload, dict) else None
    if not content:
        raise UpstreamError("视觉模型没有返回 message.content")
    return {
        "model": payload.get("model", CONFIG.vision_model),
        "analysis": parse_model_json(content),
    }


async def analyze_images(image_paths: list[Path]) -> dict[str, Any]:
    contents: list[dict[str, Any]] = [{"type": "text", "text": extraction_prompt(len(image_paths))}]
    for index, image_path in enumerate(image_paths):
        image = await asyncio.to_thread(image_path.read_bytes)
        contents.append({"type": "text", "text": f"当前图片 image_index={index}"})
        contents.append({
            "type": "image_url",
            "image_url": {"url": f"data:{image_mime_type(image_path)};base64,{base64.b64encode(image).decode()}"},
        })
    result = await request_vision_completion([{"role": "user", "content": contents}])
    result["analysis"]["regions"] = normalize_regions(result["analysis"].get("regions"), len(image_paths))
    return {**result, "image_count": len(image_paths)}
