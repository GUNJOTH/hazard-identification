"""隐患识别 API 路由与编排逻辑。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ..config import (
    CONFIG,
    HAZARD_CATEGORIES,
    HAZARD_LEVELS,
    HAZARD_TYPES,
    PROJECT_DIR,
    RESULT_DIR,
    RUNTIME_DIR,
    YES_NO,
)
from ..errors import UpstreamError
from ..schemas import (
    DetailBbox,
    HazardContentAnalysisResponse,
    HazardDetailResponse,
    HazardIdentificationResponse,
    HazardListResponse,
    ImageReference,
)
from ..repositories.records import load_persisted_result, save_result
from ..services.detail_view import public_detail_result as build_public_detail_result
from ..services.http_client import request_json
from ..services.identification import build_hazard_draft, create_identification, public_images
from ..services.knowledge import flatten_evidence, retrieve_hazard_rules
from ..services.pipeline import ensure_pipeline_config
from ..services.vision import request_vision_completion
from ..utils.evidence import clean_evidence
from ..utils.geometry import normalize_regions, unit_coordinate
from ..utils.images import image_mime_type
from ..utils.model_json import parse_model_json
from ..utils.text import as_text, limit_text, now_iso, nullable_text, unique_texts, valid_date


router = APIRouter()


REGION_BACKFILL_LOCKS: dict[str, asyncio.Lock] = {}


def region_backfill_lock(record_id: str) -> asyncio.Lock:
    return REGION_BACKFILL_LOCKS.setdefault(record_id, asyncio.Lock())


def evidence_kind_label(item: dict[str, Any]) -> str:
    document = str(item.get("document") or "")
    if document.startswith("05_热力安全"):
        return "法规/标准依据"
    if document.startswith("08_建筑与公共区域"):
        return "法规/标准依据"
    if document.startswith("06_供热单位隐患识别与分级规则"):
        return "企业规则"
    if document.startswith("07_热力设备图像识别词典"):
        return "图像识别词典"
    return "其他依据"


def content_analysis_prompt(draft: dict[str, Any], *, include_regions: bool = False) -> str:
    evidence = clean_evidence(draft.get("evidence"))
    evidence_text = "\n".join(
        f"[依据{index}] [{evidence_kind_label(item)}] {item.get('document') or '隐患规则库'}：{item.get('content') or ''}"
        for index, item in enumerate(evidence[:6], start=1)
    ) or "- 暂无知识库片段"
    region_instruction = (
        "由于当前记录没有区域坐标，请同时根据图片补充 regions；每个元素必须包含 image_index、label、confidence、bbox、polygon、description。"
        " bbox 使用 [x1,y1,x2,y2]，polygon 使用 [[x,y],...]，坐标归一化到 0 到 1；无法可靠定位时返回空数组。"
        if include_regions
        else "当前记录已有区域坐标，不要输出像素坐标或假设精确的框选区域。"
    )
    region_fields = "regions: 隐患区域数组；" if include_regions else ""
    return f"""
你是工业现场隐患复核分析助手。请根据下面一条隐患识别结果和随后附带的原始图片证据进行分析。
不要修改隐患类别、隐患类型、隐患等级等原始字段；只输出分析结论、风险判断和建议。
无法从内容确认的事实必须明确写“待现场核实”，不得编造设备编码、责任人或事故后果。
请结合原始图片重新核对隐患现象，并用自然语言说明重点隐患在图片中的大致位置。{region_instruction}
请返回严格 JSON，不要 Markdown，字段必须包括：
summary: 一句话分析结论；
focus_hint: 重点观察位置，例如“第一张图片中部偏下的立柱根部”，无法确认时写待现场核实；
risk_assessment: 风险判断，说明主要风险和判断依据；
impact: 可能影响，无法确认时写待现场核实；
root_cause: 可能原因，无法确认时写待现场核实；
key_findings: 关键发现数组；
findings: 多模态识别结果数组，每项包含 description、reason、location、risk_level、confidence、basis；
risk_impacts: 风险影响数组；
recommended_actions: 建议措施数组；
response_deadline: 建议整改时限对象，包含 urgency（urgent/normal）和 text；无法判断时为 null；
evidence_summary: 对上面编号知识库依据的 AI 归纳对象，包含 laws 和 rules 两个数组；每项包含 evidence_index、summary、violation_reason。laws 只能引用标记为“法规/标准依据”的编号，rules 只能引用标记为“企业规则”的编号，标记为“图像识别词典”的依据不得放入 laws 或 rules。不得按相关程度重排编号。summary 只能根据对应编号的原文归纳，不能编造原文没有的法规条款；如果没有明确条款号或原文，必须说明“当前依据为检查要点/适用说明，未提供明确条款原文”。
 manual_review_items: 需要人工复核的事项数组；
 confidence: 0 到 1 的分析置信度。
 {region_fields}

隐患单内容：
- 隐患描述：{draft.get('description') or '待补充'}
- 隐患类别：{draft.get('category') or '待确认'}
- 隐患类型：{draft.get('type') or '待确认'}
- 隐患等级：{draft.get('level') or '待确认'}
- 发现来源：{draft.get('discovery_source') or '隐患排查'}
- 整改时限：{draft.get('rectification_deadline') or '待确认'}
- 设备名称：{draft.get('equipment_name') or '待现场确认'}
- 位置：{draft.get('location') or '待现场确认'}
- 可见现象：{as_text(draft.get('observations')) or '待补充'}
- 已有整改建议：{as_text(draft.get('suggested_actions')) or '待生成'}

知识库依据：
{evidence_text}

法规与规则归纳要求：
请对与当前图片隐患最相关的法规和企业规则分别归纳，说明依据解决什么风险、当前识别结果为什么与它相关。法规依据必须区分“明确条款原文”和“检查要点/适用说明”；不能把知识库中的召回说明改写成法律条款，也不能凭空生成条款号。若没有法规/标准依据或企业规则的明确匹配项，对应数组返回空数组。
""".strip()


def normalize_evidence_summary(value: Any) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {"laws": [], "rules": []}
    if not isinstance(value, dict):
        return result
    for kind in result:
        items = value.get(kind)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_index = item.get("evidence_index", item.get("evidenceIndex"))
            try:
                evidence_index = int(raw_index)
            except (TypeError, ValueError):
                continue
            if evidence_index < 1 or evidence_index > 6:
                continue
            summary = limit_text(item.get("summary"), 1200)
            reason = limit_text(item.get("violation_reason", item.get("violationReason")), 1200)
            if not summary and not reason:
                continue
            result[kind].append({
                "evidence_index": evidence_index,
                "summary": summary,
                "violation_reason": reason,
            })
    return result


async def analyze_hazard_content(record: dict[str, Any], *, include_regions: bool = False) -> dict[str, Any]:
    ensure_pipeline_config()
    draft = record.get("hazard_draft") or {}
    contents: list[dict[str, Any]] = [{
        "type": "text",
        "text": content_analysis_prompt(draft, include_regions=include_regions),
    }]
    for item in record.get("images") or []:
        image_path = Path(item.get("path") or "")
        if not image_path.exists():
            continue
        image = await asyncio.to_thread(image_path.read_bytes)
        contents.append({
            "type": "image_url",
            "image_url": {"url": f"data:{image_mime_type(image_path)};base64,{base64.b64encode(image).decode()}"},
        })
    result = await request_vision_completion([{"role": "user", "content": contents}], max_tokens=2200)
    analysis = result.get("analysis") or {}
    manual_items = unique_texts((draft.get("manual_review_items") or []) + (analysis.get("manual_review_items") or []))
    regions = normalize_regions(
        analysis.get("regions"),
        len(record.get("images") or []),
    ) if include_regions else []
    return {
        "id": record["id"],
        "status": "analyzed",
        "analyzed_at": now_iso(),
        "model": result["model"],
        "confidence": analysis.get("confidence"),
        "summary": limit_text(analysis.get("summary"), 1000) or draft.get("description") or "待补充分析结论",
        "focus_hint": limit_text(analysis.get("focus_hint"), 500) or "待现场核实",
        "risk_assessment": limit_text(analysis.get("risk_assessment"), 2000) or "待现场复核风险影响",
        "impact": limit_text(analysis.get("impact"), 1000) or "待现场核实",
        "root_cause": limit_text(analysis.get("root_cause"), 1000) or "待现场核实",
        "key_findings": unique_texts(analysis.get("key_findings")),
        "findings": analysis.get("findings") if isinstance(analysis.get("findings"), list) else [],
        "risk_impacts": unique_texts(analysis.get("risk_impacts")),
        "recommended_actions": unique_texts(analysis.get("recommended_actions")) or unique_texts(draft.get("suggested_actions")),
        "response_deadline": analysis.get("response_deadline") if isinstance(analysis.get("response_deadline"), dict) else None,
        "evidence_summary": normalize_evidence_summary(analysis.get("evidence_summary")),
        "manual_review_required": bool(manual_items),
        "manual_review_items": manual_items,
        "evidence": draft.get("evidence") or [],
        "regions": regions,
    }


async def load_result(record_id: str) -> dict[str, Any]:
    try:
        UUID(record_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="识别记录 ID 格式错误") from error
    persisted = await load_persisted_result(record_id)
    if persisted is not None:
        return persisted
    record = seed_records().get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="识别记录不存在")
    return record


SEED_IMAGE_PATHS = (
    PROJECT_DIR / "test" / "multi-angle" / "hazard_sample_002_01.png",
    PROJECT_DIR / "test" / "multi-angle" / "hazard_sample_002_02.png",
)


def seed_image_metadata(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {
        "filename": path.name,
        "mime_type": image_mime_type(path),
        "size": size,
        "sha256": None,
        "path": str(path),
    }


def seed_record(
    *,
    record_id: str,
    created_at: str,
    image_indexes: tuple[int, ...],
    description: str,
    category: str,
    hazard_type: str,
    location: str,
    equipment_name: str,
    actions: list[str],
    level: str = "一般隐患",
    review_items: list[str] | None = None,
) -> dict[str, Any]:
    image_paths = [SEED_IMAGE_PATHS[index] for index in image_indexes]
    analysis = {
        "hazard_description": description,
        "hazard_category": category,
        "hazard_type": hazard_type,
        "location": location,
        "equipment_name": equipment_name,
        "special_equipment_involved": "否",
        "observations": [description],
        "suggested_actions": actions,
        "confidence": 0.86 if level == "一般隐患" else 0.72,
    }
    knowledge = {
        "query": f"隐患描述：{description}；隐患类别：{category}；隐患类型：{hazard_type}",
        "records": [{
            "score": 0.94 if level == "一般隐患" else 0.89,
            "document": "03_一般隐患规则.md" if level == "一般隐患" else "02_重大隐患规则.md",
            "content": (
                f"规则结论：{level}\n"
                "判定依据：根据现场可见现象、影响范围和是否存在立即失稳或重大事故风险综合判断。"
            ),
            "segment_id": f"seed-{record_id}",
        }],
    }
    image_refs = [
        ImageReference(
            index=position,
            url=f"/api/v1/hazard-identifications/{record_id}/images/{position}",
        )
        for position, _ in enumerate(image_indexes)
    ]
    draft = build_hazard_draft(
        created_at=created_at,
        image_refs=image_refs,
        vision={"analysis": analysis},
        knowledge=knowledge,
        context={
            "discovery_source": "隐患排查",
            "inspection_date": created_at[:10],
            "inspection_location": location,
            "rectification_deadline": "2026-09-02",
            "rectification_requirement": "；".join(actions),
            "special_equipment_involved": "否",
            "key_hazard": "否",
            "group_statistics": "否",
            "inspector": "管理员",
        },
    )
    if review_items:
        draft["equipment_review_required"] = True
        draft["manual_review_required"] = True
        draft["manual_review_items"] = review_items
    return {
        "id": record_id,
        "created_at": created_at,
        "client_request_id": None,
        "images": [seed_image_metadata(path) for path in image_paths],
        "vision": {"model": CONFIG.vision_model, "analysis": analysis},
        "knowledge": knowledge,
        "hazard_draft": draft,
    }


def seed_records() -> dict[str, dict[str, Any]]:
    return {
        "00000000-0000-4000-8000-000000000001": seed_record(
            record_id="00000000-0000-4000-8000-000000000001",
            created_at="2026-08-25T01:30:00Z",
            image_indexes=(0,),
            description="墙体墙壁局部出现受潮、锈水和表层剥落，墙面保护层破损，需及时排查渗漏原因并修复。",
            category="基础设施",
            hazard_type="设备设施事故隐患",
            location="室外墙体区域",
            equipment_name="墙体墙壁",
            actions=["安排专业人员检查墙体受潮和破损范围", "完成墙面修复、防水及表层防护"],
        ),
        "00000000-0000-4000-8000-000000000002": seed_record(
            record_id="00000000-0000-4000-8000-000000000002",
            created_at="2026-08-25T02:15:00Z",
            image_indexes=(1,),
            description="管道、阀门及连接部位可见锈蚀，墙面存在锈水痕迹和局部剥落。",
            category="生产设备",
            hazard_type="设备设施事故隐患",
            location="地下管道间",
            equipment_name="管道及阀门组",
            actions=["检查管道和阀门密封状态", "处理锈蚀并消除渗漏，恢复墙面防护"],
        ),
    }


def records_for_list() -> list[dict[str, Any]]:
    records = seed_records()
    if RESULT_DIR.exists():
        for path in RESULT_DIR.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            record_id = str(record.get("id") or path.stem)
            if record_id:
                records[record_id] = record
    return sorted(records.values(), key=lambda record: str(record.get("created_at") or ""), reverse=True)


def list_item_from_record(record: dict[str, Any]) -> dict[str, Any]:
    draft = record.get("hazard_draft") or {}
    images = public_images(str(record["id"]), len(record.get("images") or []))
    return {
        "id": str(record["id"]),
        "status": "identified",
        "created_at": record.get("created_at") or "",
        "discovery_time": draft.get("discovery_time") or record.get("created_at") or "",
        "description": draft.get("description"),
        "category": draft.get("category"),
        "type": draft.get("type"),
        "level": draft.get("level"),
        "discovery_source": draft.get("discovery_source") or "隐患排查",
        "rectification_deadline": draft.get("rectification_deadline"),
        "location": draft.get("location"),
        "equipment_name": draft.get("equipment_name"),
        "image_count": len(images),
        "thumbnail_url": images[0]["url"] if images else None,
        "manual_review_required": bool(draft.get("manual_review_required")),
    }


def clean_evidence(items: Any) -> list[dict[str, Any]]:
    return [
        item for item in (items or [])
        if isinstance(item, dict) and "演示" not in str(item.get("document") or "")
    ]


def detail_region_kind(label: str) -> str:
    if any(keyword in label for keyword in ("锈蚀", "腐蚀", "渗漏", "锈水")):
        return "corrosion"
    if any(keyword in label for keyword in ("裂纹", "开裂", "破裂")):
        return "crack"
    if any(keyword in label for keyword in ("磨损", "破损", "剥落")):
        return "wear"
    if "隐患部位" in label or "区域" in label:
        return "hazard_area"
    return "other"


def detail_bbox(value: Any) -> DetailBbox | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    x1, y1, x2, y2 = value
    return DetailBbox(x=x1, y=y1, width=round(x2 - x1, 6), height=round(y2 - y1, 6))


def detail_images(record_id: str, image_count: int, regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {index: [] for index in range(image_count)}
    for index, region in enumerate(regions, start=1):
        image_index = int(region["image_index"])
        bbox = detail_bbox(region.get("bbox"))
        grouped[image_index].append({
            "id": f"r{image_index}-{index}",
            "label": region["label"],
            "kind": detail_region_kind(region["label"]),
            "bbox": bbox,
            "confidence": region.get("confidence"),
        })
    return [
        {
            "index": index,
            "url": f"/api/v1/hazard-identifications/{record_id}/images/{index}",
            "regions": grouped[index],
        }
        for index in range(image_count)
    ]


def evidence_source_url(content: str) -> str | None:
    match = re.search(r"https?://[^\s)`】]+", content)
    return match.group(0).rstrip("`.,;，。") if match else None


def evidence_excerpt(content: str, length: int = 700) -> str:
    text = re.sub(r"https?://[^\s)`】]+", "", content)
    text = re.sub(r"[`#]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:length] or "待补充依据摘要"


def heat_safety_law_sections(content: str) -> list[dict[str, str | None]]:
    text = str(content or "").replace("\r\n", "\n")
    matches = list(re.finditer(
        r"(?m)^(?:###\s+)?(?P<code>HS-[A-Z0-9-]+)\s+(?P<title>.+?)\s*$",
        text,
    ))
    sections: list[dict[str, str | None]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        next_heading = re.search(r"(?m)^##\s+", text[match.end():end])
        if next_heading:
            end = match.end() + next_heading.start()
        body = text[match.end():end].strip()
        title = match.group("title").strip()
        article_match = re.search(r"第[一二三四五六七八九十百0-9]+条", body)
        sections.append({
            "code": match.group("code"),
            "title": title,
            "article": article_match.group(0) if article_match else None,
            "body": body,
        })
    return sections


def law_requirement_excerpt(content: str) -> str:
    preferred_prefixes = (
        "检索要点", "可检索要点", "核心定义", "管理要求", "可直接召回",
        "重点条款", "识别用途", "重大风险提示", "判定边界", "适用范围",
        "现场参考目录", "重要更新", "状态说明",
    )
    lines: list[str] = []
    for raw_line in str(content or "").splitlines():
        line = re.sub(r"^\s*[-*]\s*", "", raw_line).strip()
        if not line or line.startswith(("来源：", "发布来源：", "规程文本：", "层级：")):
            continue
        if line.startswith(preferred_prefixes):
            lines.append(line)
    if not lines:
        for raw_line in str(content or "").splitlines():
            line = re.sub(r"^\s*[-*]\s*", "", raw_line).strip()
            if line and not line.startswith(("来源：", "发布来源：", "规程文本：", "层级：")):
                lines.append(line)
    return evidence_excerpt("；".join(lines[:4]))


def law_article_content(content: str) -> str | None:
    labels = ("条款原文", "条文原文", "原文", "条文内容", "规定内容")
    for raw_line in str(content or "").splitlines():
        line = re.sub(r"^\s*[-*]\s*", "", raw_line).strip()
        for label in labels:
            if line.startswith(f"{label}：") or line.startswith(f"{label}:"):
                value = line.split("：", 1)[1] if "：" in line else line.split(":", 1)[1]
                return evidence_excerpt(value)
    return None


def evidence_violation_reason(excerpt: str, context_text: str) -> str:
    keywords = (
        "锈蚀", "腐蚀", "渗漏", "漏水", "漏汽", "锈水", "保温", "积水",
        "标识", "支架", "裂纹", "剥落", "管道", "阀门", "墙面", "防护", "警示",
    )
    matched = [keyword for keyword in keywords if keyword in excerpt and keyword in context_text]
    if matched:
        matched_text = "、".join(matched[:3])
        return (
            f"当前识别结果包含“{matched_text}”等可见现象，与该依据中的检查要求相关；"
            "照片只能证明外观现象，是否构成违反条款仍需结合现场资料和专业人员复核。"
        )
    return "该依据与当前热力安全场景相关；照片只能证明可见现象，是否构成违反条款需结合现场资料和专业人员复核。"


def detail_evidence(
    items: Any,
    context_text: str = "",
    ai_summary: Any = None,
) -> dict[str, list[dict[str, Any]]]:
    laws: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []
    cleaned_items = clean_evidence(items)
    normalized_ai = normalize_evidence_summary(ai_summary)
    law_ai = {item["evidence_index"]: item for item in normalized_ai["laws"]}
    rule_ai = {item["evidence_index"]: item for item in normalized_ai["rules"]}
    for evidence_index, item in enumerate(cleaned_items, start=1):
        document = str(item.get("document") or "")
        content = str(item.get("content") or "")
        if not content:
            continue
        if document.startswith("05_热力安全") or document.startswith("08_建筑与公共区域"):
            sections = heat_safety_law_sections(content)
            for section in sections:
                body = str(section.get("body") or "")
                if body:
                    excerpt = law_requirement_excerpt(body)
                    ai_item = law_ai.get(evidence_index) or {}
                    laws.append({
                        "title": str(section.get("title") or "热力安全法规与标准"),
                        "article": section.get("article"),
                        "article_content": law_article_content(body),
                        "excerpt": excerpt,
                        "violation_reason": (
                            ai_item.get("violation_reason")
                            or evidence_violation_reason(excerpt, context_text)
                        ),
                        "ai_summary": ai_item.get("summary"),
                        "source_url": evidence_source_url(body),
                    })
            continue
        if document.startswith("06_供热单位隐患识别与分级规则"):
            code_match = re.search(r"\bR-[A-Z0-9-]+\b", content)
            first_line = next((line.strip() for line in content.splitlines() if line.strip()), "供热单位隐患识别与分级规则")
            name = re.sub(r"^R-[A-Z0-9-]+\s*", "", first_line).strip() or first_line
            ai_item = rule_ai.get(evidence_index) or {}
            rules.append({
                "code": code_match.group(0) if code_match else None,
                "name": name,
                "excerpt": evidence_excerpt(content),
                "risk_level": "高风险" if "重大隐患" in content else "一般风险" if "一般隐患" in content else None,
                "ai_summary": ai_item.get("summary"),
                "source_url": evidence_source_url(content),
            })
    def unique(values: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for value in values:
            key = tuple(value.get(item) for item in keys)
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result
    return {
        "laws": unique(laws, ("title", "article", "source_url"))[:12],
        "rules": unique(rules, ("code", "name"))[:12],
    }


def detail_risk_level(value: Any, fallback: str | None) -> str | None:
    text = str(value or "").lower()
    if text in {"high", "medium", "low"}:
        return text
    if "高" in text or "重大" in text:
        return "high"
    if "中" in text or "一般" in text:
        return "medium"
    if fallback == "重大隐患":
        return "high"
    if fallback == "一般隐患":
        return "medium"
    return None


def detail_findings(
    analysis: dict[str, Any],
    draft: dict[str, Any],
    evidence: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    basis = ["image_feature"]
    if evidence["laws"]:
        basis.append("law")
    if evidence["rules"]:
        basis.append("rule")
    raw_findings = analysis.get("findings")
    if not isinstance(raw_findings, list) or not raw_findings:
        raw_findings = [{"description": item} for item in unique_texts(analysis.get("key_findings"))]
    if not raw_findings and draft.get("description"):
        raw_findings = [{"description": draft["description"]}]
    result: list[dict[str, Any]] = []
    for item in raw_findings:
        if isinstance(item, str):
            item = {"description": item}
        if not isinstance(item, dict):
            continue
        description = limit_text(item.get("description"), 1000)
        if not description:
            continue
        result.append({
            "description": description,
            "reason": limit_text(item.get("reason"), 500) or "检测依据：图像特征识别",
            "location": nullable_text(item.get("location")) or nullable_text(draft.get("location")),
            "risk_level": detail_risk_level(item.get("risk_level"), draft.get("level")),
            "confidence": unit_coordinate(item.get("confidence")) or unit_coordinate(analysis.get("confidence")),
            "basis": unique_texts(item.get("basis")) or basis,
        })
    return result


def detail_public_risk_text(value: Any) -> str | None:
    return {
        "high": "高",
        "medium": "中",
        "low": "低",
    }.get(str(value or "").strip().lower())


def detail_public_confidence(value: Any) -> str | None:
    confidence = unit_coordinate(value)
    return f"{confidence:.2f}" if confidence is not None else None


def detail_public_basis_text(value: Any) -> str | None:
    labels = {
        "image_feature": "图像特征",
        "image_features": "图像特征",
        "图像特征": "图像特征",
        "law": "法规",
        "laws": "法规",
        "法规": "法规",
        "rule": "规则",
        "rules": "规则",
        "规则": "规则",
        "knowledge": "知识库",
        "知识库": "知识库",
    }
    values = value if isinstance(value, list) else []
    result: list[str] = []
    for item in values:
        text = labels.get(str(item).strip(), str(item).strip())
        if text and text not in result:
            result.append(text)
    return "、".join(result) or None


def detail_public_evidence(evidence: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "laws": [
            {
                "title": item["title"],
                "article": item.get("article"),
                "articleContent": item.get("article_content"),
                "excerpt": item["excerpt"],
                "violationReason": item.get("violation_reason"),
                "aiSummary": item.get("ai_summary"),
            }
            for item in evidence.get("laws", [])
        ],
        "rules": [
            {
                "title": item.get("name") or item.get("code") or "企业隐患规则",
                "riskLevelText": item.get("risk_level"),
                "excerpt": item["excerpt"],
                "aiSummary": item.get("ai_summary"),
            }
            for item in evidence.get("rules", [])
        ],
    }


def detail_public_findings(
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "description": item["description"],
            "reason": item.get("reason"),
            "location": item.get("location"),
            "riskBadge": {"text": detail_public_risk_text(item.get("risk_level"))},
            "confidenceText": detail_public_confidence(item.get("confidence")),
            "basisText": detail_public_basis_text(item.get("basis")),
        }
        for item in findings
    ]


def detail_public_deadline(
    value: Any,
    draft: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(value, dict):
        text = limit_text(value.get("text"), 500)
        urgency = str(value.get("urgency") or "").strip().lower()
        if text:
            return {
                "isUrgent": bool(value.get("isUrgent") is True or urgency == "urgent"),
                "text": text,
            }
    deadline = valid_date(draft.get("rectification_deadline"))
    if deadline:
        return {
            "isUrgent": draft.get("level") == "重大隐患",
            "text": f"建议在 {deadline} 前完成整改并复核",
        }
    return {
        "isUrgent": False,
        "text": "建议结合现场风险评估确定整改时限",
    }


def public_detail_result(result: dict[str, Any]) -> dict[str, Any]:
    draft = dict(result.get("hazard_draft") or {})
    content_analysis = dict(result.get("content_analysis") or {})
    image_count = len(result.get("images") or [])
    regions = normalize_regions(
        (result.get("vision") or {}).get("analysis", {}).get("regions"),
        image_count,
    )
    context_text = " ".join([
        as_text(draft.get("description")),
        as_text(draft.get("category")),
        as_text(draft.get("type")),
        as_text(draft.get("equipment_name")),
        as_text(draft.get("location")),
        " ".join(unique_texts(draft.get("observations"))),
        as_text(content_analysis.get("summary")),
        " ".join(unique_texts(content_analysis.get("key_findings"))),
        " ".join(
            as_text(item.get("description")) + " " + as_text(item.get("reason"))
            for item in (content_analysis.get("findings") or [])
            if isinstance(item, dict)
        ),
    ])
    evidence = detail_evidence(
        draft.get("evidence") or content_analysis.get("evidence"),
        context_text,
        content_analysis.get("evidence_summary"),
    )
    findings = detail_findings(content_analysis, draft, evidence)
    impacts = unique_texts(content_analysis.get("risk_impacts"))
    if not impacts:
        impact = nullable_text(content_analysis.get("impact"))
        if impact and impact != "待现场核实":
            impacts = [impact]
    actions = unique_texts(content_analysis.get("recommended_actions")) or unique_texts(draft.get("suggested_actions"))
    image_basis = "；".join(unique_texts(draft.get("observations")))
    if not image_basis:
        image_basis = limit_text(content_analysis.get("summary"), 1000) or draft.get("description")
    return {
        "basic": {
            "reportNo": result.get("report_no"),
            "createdAt": result.get("created_at") or "",
            "source": draft.get("discovery_source"),
            "model": draft.get("category"),
            "analyst": draft.get("type"),
            "analyzedAt": content_analysis.get("analyzed_at"),
        },
        "media": {
            "imageBasis": image_basis,
            "images": detail_images(str(result["id"]), image_count, regions),
        },
        "evidence": detail_public_evidence(evidence),
        "findings": detail_public_findings(findings),
        "suggestion": {
            "impacts": impacts,
            "actions": actions,
            "deadline": detail_public_deadline(content_analysis.get("response_deadline"), draft),
        },
    }


@router.get("/api/v1/health", tags=["system"], summary="健康检查")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "hazard-identification-python",
        "version": "1.0.0",
        "pipeline": "vision -> hazard knowledge retrieval -> hazard content analysis",
        "config": {
            "vision_model_configured": bool(CONFIG.vision_api_key),
            "dify_configured": bool(CONFIG.dify_api_key and CONFIG.hazard_rules_dataset_id),
        },
    }


@router.get(
    "/api/v1/hazard-identifications",
    tags=["hazard-identifications"],
    summary="分页获取隐患识别记录列表",
    response_model=HazardListResponse,
)
async def list_hazard_identifications(
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    normalized_keyword = (keyword or "").strip().lower()
    records = records_for_list()
    if normalized_keyword:
        records = [
            record
            for record in records
            if normalized_keyword in " ".join([
                str(record.get("id") or ""),
                str((record.get("hazard_draft") or {}).get("description") or ""),
                str((record.get("hazard_draft") or {}).get("category") or ""),
                str((record.get("hazard_draft") or {}).get("type") or ""),
                str((record.get("hazard_draft") or {}).get("location") or ""),
                str((record.get("hazard_draft") or {}).get("equipment_name") or ""),
            ]).lower()
        ]
    total = len(records)
    start = (page - 1) * page_size
    items = [list_item_from_record(record) for record in records[start:start + page_size]]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post(
    "/api/v1/hazard-identifications",
    tags=["hazard-identifications"],
    summary="创建隐患识别记录",
    description="同一次请求中的多张图片视为同一处隐患的不同角度，只生成一条隐患识别结果。",
    response_model=HazardIdentificationResponse,
)
async def create_hazard_identification(request: Request) -> dict[str, Any]:
    try:
        return await create_identification(request)
    except HTTPException:
        raise
    except (UpstreamError, httpx.HTTPError) as error:
        raise HTTPException(status_code=502, detail=f"视觉模型调用失败，可重试：{error}") from error


@router.post(
    "/api/v1/hazard-identifications/{record_id}/analysis",
    tags=["hazard-identifications"],
    summary="根据隐患单内容执行 AI 分析",
    response_model=HazardContentAnalysisResponse,
)
async def analyze_hazard_identification(record_id: str) -> dict[str, Any]:
    try:
        async with region_backfill_lock(record_id):
            result = await load_result(record_id)
            images = result.get("images") or []
            draft = dict(result.get("hazard_draft") or {})
            original_evidence = draft.get("evidence") or []
            existing_evidence = clean_evidence(original_evidence)
            if existing_evidence != original_evidence:
                draft["evidence"] = existing_evidence
                result["hazard_draft"] = draft
                await save_result(record_id, result)
            has_heat_safety_evidence = any(
                str(item.get("document") or "").startswith("05_热力安全")
                for item in existing_evidence
                if isinstance(item, dict)
            )
            if (
                not has_heat_safety_evidence
                and CONFIG.dify_api_key
                and CONFIG.hazard_rules_dataset_id
            ):
                refreshed_knowledge = await retrieve_hazard_rules({
                    "hazard_description": draft.get("description"),
                    "hazard_category": draft.get("category"),
                    "hazard_type": draft.get("type"),
                    "equipment_name": draft.get("equipment_name"),
                    "observations": draft.get("observations"),
                })
                refreshed_evidence = flatten_evidence(refreshed_knowledge)
                if refreshed_evidence:
                    merged_evidence = list(existing_evidence)
                    seen_evidence = {
                        (item.get("document"), item.get("segment_id"), item.get("content"))
                        for item in merged_evidence
                        if isinstance(item, dict)
                    }
                    for item in refreshed_evidence:
                        key = (item.get("document"), item.get("segment_id"), item.get("content"))
                        if key not in seen_evidence:
                            seen_evidence.add(key)
                            merged_evidence.append(item)
                    result["knowledge"] = {
                        **refreshed_knowledge,
                        "records": merged_evidence,
                    }
                    draft["evidence"] = merged_evidence
                    result["hazard_draft"] = draft
                    await save_result(record_id, result)
            regions = normalize_regions(
                (result.get("vision") or {}).get("analysis", {}).get("regions"),
                len(images),
            )
            cached = result.get("content_analysis")
            if isinstance(cached, dict) and regions:
                cached = dict(cached)
                cached["regions"] = regions
                cached["evidence"] = draft.get("evidence") or cached.get("evidence") or []
                return cached

            analysis = await analyze_hazard_content(result, include_regions=not regions)
            new_regions = normalize_regions(analysis.get("regions"), len(images)) or regions
            analysis["regions"] = new_regions
            if new_regions:
                vision = dict(result.get("vision") or {})
                vision_analysis = dict(vision.get("analysis") or {})
                vision_analysis["regions"] = new_regions
                vision["analysis"] = vision_analysis
                result["vision"] = vision
            result["content_analysis"] = analysis
            await save_result(record_id, result)
            return analysis
    except HTTPException:
        raise
    except (UpstreamError, httpx.HTTPError) as error:
        raise HTTPException(status_code=502, detail=f"隐患内容 AI 分析失败，可重试：{error}") from error


@router.get(
    "/api/v1/hazard-identifications/{record_id}",
    tags=["hazard-identifications"],
    summary="获取隐患识别记录详情（v3）",
    description="返回 basic、media、evidence、findings、suggestion 五个前端直接渲染的区块；首次访问时自动生成并缓存分析。",
    response_model=HazardDetailResponse,
)
async def get_hazard_identification(record_id: str) -> dict[str, Any]:
    await analyze_hazard_identification(record_id)
    return build_public_detail_result(await load_result(record_id))


@router.get("/api/v1/hazard-identifications/{record_id}/images/{index}", tags=["hazard-identifications"], summary="获取隐患图片")
async def get_hazard_image(record_id: str, index: int) -> FileResponse:
    result = await load_result(record_id)
    if index < 0 or index >= len(result["images"]):
        raise HTTPException(status_code=404, detail="图片序号不存在")
    path = Path(result["images"][index]["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="图片文件不存在")
    return FileResponse(path, media_type=result["images"][index]["mime_type"])
