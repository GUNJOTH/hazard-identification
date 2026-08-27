"""识别区域的归一化坐标处理。"""

from __future__ import annotations

import math
from typing import Any

from .text import limit_text


def unit_coordinate(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(max(0.0, min(1.0, number)), 6)


def normalize_bbox(value: Any) -> list[float] | None:
    if isinstance(value, dict):
        if all(key in value for key in ("x1", "y1", "x2", "y2")):
            value = [value.get("x1"), value.get("y1"), value.get("x2"), value.get("y2")]
        elif all(key in value for key in ("x", "y", "width", "height")):
            x = unit_coordinate(value.get("x"))
            y = unit_coordinate(value.get("y"))
            width = unit_coordinate(value.get("width"))
            height = unit_coordinate(value.get("height"))
            if None in {x, y, width, height}:
                return None
            value = [x, y, (x or 0) + (width or 0), (y or 0) + (height or 0)]
    if not isinstance(value, list) or len(value) != 4:
        return None
    coordinates = [unit_coordinate(item) for item in value]
    if any(item is None for item in coordinates):
        return None
    x1, y1, x2, y2 = coordinates
    assert x1 is not None and y1 is not None and x2 is not None and y2 is not None
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def normalize_polygon(value: Any) -> list[list[float]]:
    if not isinstance(value, list):
        return []
    polygon: list[list[float]] = []
    for point in value[:20]:
        if not isinstance(point, list) or len(point) < 2:
            continue
        x = unit_coordinate(point[0])
        y = unit_coordinate(point[1])
        if x is not None and y is not None:
            polygon.append([x, y])
    return polygon if len(polygon) >= 3 else []


def normalize_regions(value: Any, image_count: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    regions: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            image_index = int(item.get("image_index", 0))
        except (TypeError, ValueError):
            continue
        if image_index < 0 or image_index >= image_count:
            continue
        bbox = normalize_bbox(item.get("bbox"))
        if bbox is None:
            continue
        confidence = unit_coordinate(item.get("confidence"))
        label = limit_text(item.get("label"), 100) or "隐患区域"
        regions.append({
            "image_index": image_index,
            "label": label,
            "confidence": confidence,
            "coordinate_system": "normalized_0_1",
            "bbox": bbox,
            "polygon": normalize_polygon(item.get("polygon")),
            "description": limit_text(item.get("description"), 500),
        })
    return regions
