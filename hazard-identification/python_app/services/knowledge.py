"""隐患知识库检索、分类推断与规则定级。"""

from __future__ import annotations

import re
from typing import Any

import httpx

from ..config import CONFIG, HAZARD_CATEGORIES, HAZARD_TYPES, PROJECT_DIR
from ..errors import UpstreamError
from ..utils.text import as_text, exact_option
from .http_client import request_json


HEAT_SAFETY_KEYWORDS = (
    "热力", "供热", "热源", "热网", "锅炉", "蒸汽", "热水", "管道", "阀门",
    "换热", "泵站", "热力站", "补偿器", "管沟", "压力管道",
)

INFRASTRUCTURE_SAFETY_KEYWORDS = (
    "墙体", "墙壁", "墙面", "天花板", "楼梯", "楼板", "地面", "公共区域",
    "受潮", "渗水", "渗漏", "水渍", "锈水", "剥落", "起皮", "裂缝", "积水",
    "湿滑", "警示牌", "扶手", "通道",
)


def build_knowledge_query(analysis: dict[str, Any]) -> str:
    return "；".join([
        f"隐患描述：{as_text(analysis.get('hazard_description'))}",
        f"隐患类别：{as_text(analysis.get('hazard_category'))}",
        f"隐患类型：{as_text(analysis.get('hazard_type'))}",
        f"设备对象：{as_text(analysis.get('equipment_name'))}",
        f"可见现象：{as_text(analysis.get('observations'))}",
        "依据召回：热力安全法规、国家标准、行业标准、供热单位隐患参考目录、条款和整改要求",
    ])


def compact_records(payload: Any) -> list[dict[str, Any]]:
    records = payload.get("records", []) if isinstance(payload, dict) else []
    compacted = []
    for record in records[:8]:
        segment = record.get("segment", {}) if isinstance(record, dict) else {}
        document = segment.get("document", {}) if isinstance(segment, dict) else {}
        document_name = document.get("name")
        if "演示" in str(document_name or ""):
            continue
        compacted.append({
            "score": record.get("score"),
            "document": document_name,
            "content": (segment.get("content") or "")[:1800],
            "segment_id": segment.get("id"),
        })
    return compacted


def is_heat_context(analysis: dict[str, Any]) -> bool:
    context_text = " ".join([
        as_text(analysis.get("hazard_description")),
        as_text(analysis.get("hazard_category")),
        as_text(analysis.get("hazard_type")),
        as_text(analysis.get("equipment_name")),
        as_text(analysis.get("observations")),
    ])
    return any(keyword in context_text for keyword in HEAT_SAFETY_KEYWORDS)


def is_infrastructure_safety_context(analysis: dict[str, Any]) -> bool:
    context_text = " ".join([
        as_text(analysis.get("hazard_description")),
        as_text(analysis.get("hazard_category")),
        as_text(analysis.get("hazard_type")),
        as_text(analysis.get("equipment_name")),
        as_text(analysis.get("location")),
        as_text(analysis.get("observations")),
    ])
    return any(keyword in context_text for keyword in INFRASTRUCTURE_SAFETY_KEYWORDS)


def local_heat_safety_evidence() -> list[dict[str, Any]]:
    path = PROJECT_DIR / "knowledge-base" / "05_热力安全法规与标准依据.md"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [{
        "score": 0.6,
        "document": path.name,
        "content": content[:1800],
        "segment_id": "local-05-heat-safety-legal-basis",
    }]


def local_infrastructure_safety_evidence() -> list[dict[str, Any]]:
    path = PROJECT_DIR / "knowledge-base" / "08_建筑与公共区域安全法规依据.md"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [{
        "score": 0.65,
        "document": path.name,
        "content": content[:3600],
        "segment_id": "local-08-building-public-safety-basis",
    }]


async def retrieve_hazard_rules(analysis: dict[str, Any]) -> dict[str, Any]:
    query = build_knowledge_query(analysis)
    queries = [query]
    heat_context = is_heat_context(analysis)
    if heat_context:
        queries.append(
            "热力安全法规 标准 条款 供热单位 隐患参考目录；"
            f"相关对象：{query}；法律法规依据和整改要求"
        )
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for candidate_query in queries:
        try:
            payload = await request_json(
                f"{CONFIG.dify_base_url}/datasets/{CONFIG.hazard_rules_dataset_id}/retrieve",
                method="POST",
                headers={
                    "Authorization": f"Bearer {CONFIG.dify_api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                body={"query": candidate_query},
                timeout=45,
            )
            records.extend(compact_records(payload))
        except (UpstreamError, httpx.HTTPError) as error:
            errors.append(str(error))
    if heat_context and not any(
        str(record.get("document") or "").startswith("05_热力安全")
        for record in records
    ):
        records.extend(local_heat_safety_evidence())
    infrastructure_context = is_infrastructure_safety_context(analysis)
    if infrastructure_context and not any(
        str(record.get("document") or "").startswith("08_建筑与公共区域")
        for record in records
    ):
        records.extend(local_infrastructure_safety_evidence())
    unique_records = []
    seen = set()
    for record in records:
        key = (record.get("segment_id"), record.get("document"), record.get("content"))
        if key in seen:
            continue
        seen.add(key)
        unique_records.append(record)
    result = {"query": "；".join(queries), "records": unique_records[:12]}
    if errors and not unique_records:
        result["error"] = "；".join(errors)
    return result


def infer_category(analysis: dict[str, Any]) -> str | None:
    candidate = exact_option(analysis.get("hazard_category"), HAZARD_CATEGORIES)
    if candidate:
        return candidate
    text = " ".join([
        as_text(analysis.get("hazard_description")),
        as_text(analysis.get("equipment_name")),
        as_text(analysis.get("observations")),
    ])
    keyword_map = (
        (("电缆", "配电", "开关", "变压器", "带电", "电气"), "电气设备"),
        (("灭火器", "消火栓", "消防泵", "喷淋", "火灾报警"), "消防设施"),
        (("墙面", "楼梯", "楼板", "基础", "地面", "立柱", "护栏", "平台"), "基础设施"),
        (("泵", "阀门", "管道", "设备", "机组", "锅炉", "风机"), "生产设备"),
        (("违章", "违规", "未戴", "未按规定"), "二违"),
        (("台账", "制度", "标识管理", "责任不清"), "管理问题"),
    )
    for keywords, category in keyword_map:
        if any(keyword in text for keyword in keywords):
            return category
    return None


def infer_type(analysis: dict[str, Any]) -> str | None:
    candidate = exact_option(analysis.get("hazard_type"), HAZARD_TYPES)
    if candidate:
        return candidate
    text = " ".join([
        as_text(analysis.get("hazard_description")),
        as_text(analysis.get("equipment_name")),
        as_text(analysis.get("observations")),
    ])
    keyword_map = (
        (("带电", "电缆", "配电柜", "绝缘", "接地"), "电力安全事故隐患"),
        (("坠落", "护栏缺失", "洞口", "尖锐", "夹伤", "人员"), "人身安全隐患"),
        (("管理", "制度", "台账", "标识缺失"), "安全管理隐患"),
        (("大坝", "坝体", "水库"), "大坝安全隐患"),
        (("设备", "管道", "阀门", "泵", "腐蚀", "渗漏", "破损"), "设备设施事故隐患"),
    )
    for keywords, hazard_type in keyword_map:
        if any(keyword in text for keyword in keywords):
            return hazard_type
    return None


def knowledge_level(knowledge: dict[str, Any]) -> tuple[str | None, str]:
    pattern = re.compile(r"(?:规则结论|隐患等级|判定等级|等级)\s*[：:]\s*(重大隐患|一般隐患)")
    records = sorted(knowledge.get("records", []), key=lambda item: -(float(item.get("score") or 0)))
    for record in records:
        match = pattern.search(str(record.get("content") or ""))
        if match:
            return match.group(1), "knowledge_rule"
    return None, "human_review"


def flatten_evidence(knowledge: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "document": record.get("document"),
            "score": record.get("score"),
            "content": record.get("content"),
            "segment_id": record.get("segment_id"),
        }
        for record in knowledge.get("records", [])
    ]
