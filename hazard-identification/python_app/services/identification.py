"""隐患单草稿生成与图片识别创建流程。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Request

from ..api.request_parsing import parse_request
from ..config import DISCOVERY_SOURCES
from ..repositories.records import save_result, save_upload
from ..schemas import ImageReference
from ..utils.evidence import clean_evidence
from ..utils.geometry import normalize_regions
from ..utils.text import exact_option, limit_text, now_iso, nullable_text, unique_texts, valid_date, yes_no
from .knowledge import flatten_evidence, infer_category, infer_type, knowledge_level, retrieve_hazard_rules
from .pipeline import ensure_pipeline_config
from .vision import analyze_images


def build_manual_review_items(
    *,
    category: str | None,
    hazard_type: str | None,
    level: str | None,
    equipment_name: str | None,
    special_equipment: str | None,
    deadline: str | None,
    executor: str | None,
    department: str | None,
) -> list[str]:
    items = []
    if not category:
        items.append("隐患类别无法由图片可靠确认，需要人工选择")
    if not hazard_type:
        items.append("隐患类型无法由图片可靠确认，需要人工选择")
    if not level:
        items.append("隐患等级未命中明确规则，需要人工确认一般隐患或重大隐患")
    if not equipment_name:
        items.append("设备或对象名称无法由图片完全确认")
    if special_equipment is None:
        items.append("是否涉及特种设备无法由图片确认")
    if not deadline:
        items.append("整改时限需要依据业务规则确认")
    if not executor:
        items.append("整改执行人需要由业务系统或责任人信息补充")
    if not department:
        items.append("整改执行部门需要由组织或设备归属信息补充")
    return items


def build_hazard_draft(
    *,
    created_at: str,
    image_refs: list[ImageReference],
    vision: dict[str, Any],
    knowledge: dict[str, Any],
    context: dict[str, str],
) -> dict[str, Any]:
    analysis = vision.get("analysis", {})
    description = limit_text(analysis.get("hazard_description"), 500)
    category = infer_category(analysis)
    hazard_type = infer_type(analysis)
    level, level_source = knowledge_level(knowledge)
    equipment_name = nullable_text(analysis.get("equipment_name"))
    location = nullable_text(analysis.get("location")) or nullable_text(context.get("inspection_location"))
    special_equipment = yes_no(context.get("special_equipment_involved")) or yes_no(analysis.get("special_equipment_involved"))
    discovery_source = exact_option(context.get("discovery_source"), DISCOVERY_SOURCES) or "隐患排查"
    inspection_date = valid_date(context.get("inspection_date")) or created_at[:10]
    deadline = valid_date(context.get("rectification_deadline"))
    executor = nullable_text(context.get("rectification_executor"))
    department = nullable_text(context.get("rectification_department"))
    key_hazard = yes_no(context.get("key_hazard"))
    group_statistics = yes_no(context.get("group_statistics"))
    suggested_actions = unique_texts(analysis.get("suggested_actions") or analysis.get("suggested_action"))
    requirement = limit_text(context.get("rectification_requirement"), 3000) or ("；".join(suggested_actions) or None)
    review_items = build_manual_review_items(
        category=category,
        hazard_type=hazard_type,
        level=level,
        equipment_name=equipment_name,
        special_equipment=special_equipment,
        deadline=deadline,
        executor=executor,
        department=department,
    )
    return {
        "description": description,
        "category": category,
        "type": hazard_type,
        "level": level,
        "level_source": level_source,
        "discovery_source": discovery_source,
        "rectification_deadline": deadline,
        "rectification_executor": executor,
        "rectification_department": department,
        "special_equipment_involved": special_equipment,
        "key_hazard": key_hazard,
        "group_statistics": group_statistics,
        "rectification_requirement": requirement,
        "discovery_time": created_at,
        "equipment_name": equipment_name,
        "equipment_review_required": equipment_name is None,
        "location": location,
        "hazard_images": [item.model_dump() for item in image_refs],
        "inspection": {
            "inspector": nullable_text(context.get("inspector")),
            "inspection_date": inspection_date,
            "inspection_location": location,
        },
        "remediation": {
            "status": "待整改",
            "completed_at": None,
            "reviewer": None,
            "review_date": None,
            "conclusion": None,
        },
        "extension": {
            "requested": "否",
            "reason": None,
            "new_deadline": None,
            "approval_status": None,
        },
        "observations": unique_texts(analysis.get("observations")),
        "suggested_actions": suggested_actions,
        "evidence": flatten_evidence(knowledge),
        "manual_review_required": bool(review_items),
        "manual_review_items": review_items,
    }


def public_images(record_id: str, count: int) -> list[dict[str, Any]]:
    return [
        {"index": index, "url": f"/api/v1/hazard-identifications/{record_id}/images/{index}"}
        for index in range(count)
    ]


def public_result(result: dict[str, Any]) -> dict[str, Any]:
    images = public_images(result["id"], len(result["images"]))
    draft = dict(result["hazard_draft"])
    draft["evidence"] = clean_evidence(draft.get("evidence"))
    draft["hazard_images"] = images
    regions = normalize_regions((result.get("vision") or {}).get("analysis", {}).get("regions"), len(images))
    return {
        "id": result["id"],
        "status": "identified",
        "created_at": result["created_at"],
        "client_request_id": result.get("client_request_id"),
        "model": result["vision"]["model"],
        "confidence": result["vision"]["analysis"].get("confidence"),
        "image_count": len(images),
        "images": images,
        "regions": regions,
        "hazard_info": draft,
    }


async def create_identification(request: Request) -> dict[str, Any]:
    ensure_pipeline_config()
    uploads, context = await parse_request(request)
    record_id = str(uuid4())
    created_at = now_iso()
    metadata: list[dict[str, Any]] = []
    image_paths: list[Path] = []
    for index, upload in enumerate(uploads):
        item, path = await save_upload(upload, record_id, index)
        metadata.append(item)
        image_paths.append(path)
    vision = await analyze_images(image_paths)
    knowledge = await retrieve_hazard_rules(vision["analysis"])
    image_refs = [ImageReference(index=index, url=f"/api/v1/hazard-identifications/{record_id}/images/{index}") for index in range(len(image_paths))]
    draft = build_hazard_draft(
        created_at=created_at,
        image_refs=image_refs,
        vision=vision,
        knowledge=knowledge,
        context={**context, "inspector": context.get("inspector") or request.headers.get("X-User-Name", "")},
    )
    result = {
        "id": record_id,
        "created_at": created_at,
        "client_request_id": nullable_text(context.get("client_request_id")),
        "images": metadata,
        "vision": vision,
        "knowledge": knowledge,
        "hazard_draft": draft,
    }
    await save_result(record_id, result)
    return public_result(result)
