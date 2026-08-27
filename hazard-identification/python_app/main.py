from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.datastructures import UploadFile as StarletteUploadFile


PROJECT_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = Path(os.getenv("HAZARD_RUNTIME_DIR", PROJECT_DIR / "runtime"))
UPLOAD_DIR = RUNTIME_DIR / "uploads"
RESULT_DIR = RUNTIME_DIR / "results"
DEMO_FRONTEND_DIR = PROJECT_DIR / "test" / "frontend"
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", 10 * 1024 * 1024))
MAX_IMAGE_COUNT = int(os.getenv("MAX_IMAGE_COUNT", 8))
ALLOWED_MIME_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

HAZARD_CATEGORIES = ("电气设备", "消防设施", "二违", "基础设施", "生产设备", "管理问题")
HAZARD_TYPES = (
    "人身安全隐患",
    "设备设施事故隐患",
    "安全管理隐患",
    "电力安全事故隐患",
    "大坝安全隐患",
    "其他事故隐患",
)
HAZARD_LEVELS = ("一般隐患", "重大隐患")
DISCOVERY_SOURCES = ("安全检查", "巡检", "缺陷", "隐患排查")
YES_NO = ("是", "否")


@dataclass(frozen=True)
class Config:
    vision_base_url: str
    vision_model: str
    vision_api_key: str
    dify_base_url: str
    dify_api_key: str
    hazard_rules_dataset_id: str
    api_auth_token: str
    cors_origin: str
    upstream_trust_env: bool


class ImageReference(BaseModel):
    index: int
    url: str


class HazardRegionResponse(BaseModel):
    image_index: int
    label: str
    confidence: float | None
    coordinate_system: str
    bbox: list[float]
    polygon: list[list[float]]
    description: str | None


class InspectionInfo(BaseModel):
    inspector: str | None
    inspection_date: str
    inspection_location: str | None


class RemediationInfo(BaseModel):
    status: str
    completed_at: str | None
    reviewer: str | None
    review_date: str | None
    conclusion: str | None


class ExtensionInfo(BaseModel):
    requested: str
    reason: str | None
    new_deadline: str | None
    approval_status: str | None


class HazardDraftResponse(BaseModel):
    description: str | None
    category: str | None
    type: str | None
    level: str | None
    level_source: str
    discovery_source: str
    rectification_deadline: str | None
    rectification_executor: str | None
    rectification_department: str | None
    special_equipment_involved: str | None
    key_hazard: str | None
    group_statistics: str | None
    rectification_requirement: str | None
    discovery_time: str
    equipment_name: str | None
    equipment_review_required: bool
    location: str | None
    hazard_images: list[ImageReference]
    inspection: InspectionInfo
    remediation: RemediationInfo
    extension: ExtensionInfo
    observations: list[str]
    suggested_actions: list[str]
    evidence: list[dict[str, Any]]
    manual_review_required: bool
    manual_review_items: list[str]


class HazardIdentificationResponse(BaseModel):
    id: str
    status: str
    created_at: str
    client_request_id: str | None
    model: str
    confidence: float | None
    image_count: int
    images: list[ImageReference]
    regions: list[HazardRegionResponse]
    hazard_info: HazardDraftResponse


class DetailAnalyzer(BaseModel):
    type: str
    name: str


class DetailBbox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class DetailRegionResponse(BaseModel):
    id: str
    label: str
    kind: str | None
    bbox: DetailBbox | None
    confidence: float | None


class DetailImageResponse(BaseModel):
    index: int
    url: str
    thumbnail_url: str | None
    regions: list[DetailRegionResponse]


class DetailFindingResponse(BaseModel):
    description: str
    reason: str | None
    location: str | None
    risk_level: str | None
    confidence: float | None
    basis: list[str]


class DetailResponseDeadline(BaseModel):
    urgency: str | None
    text: str


class DetailLawEvidence(BaseModel):
    title: str
    article: str | None
    excerpt: str
    source_url: str | None


class DetailRuleEvidence(BaseModel):
    code: str | None
    name: str | None
    excerpt: str
    risk_level: str | None
    source_url: str | None


class DetailEvidenceResponse(BaseModel):
    laws: list[DetailLawEvidence]
    rules: list[DetailRuleEvidence]


class DetailAnalysisResponse(BaseModel):
    summary: str | None
    confidence: float | None
    findings: list[DetailFindingResponse]
    risk_impacts: list[str]
    recommended_actions: list[str]
    response_deadline: DetailResponseDeadline | None
    evidence: DetailEvidenceResponse


class HazardDetailResponse(BaseModel):
    id: str
    report_no: str | None
    status: str
    created_at: str
    discovery_time: str
    model: str | None
    analyzed_at: str | None
    analyzer: DetailAnalyzer
    description: str | None
    category: str | None
    type: str | None
    level: str | None
    level_source: str | None
    discovery_source: str | None
    location: str | None
    equipment_name: str | None
    image_count: int
    thumbnail_url: str | None
    manual_review_required: bool
    rectification_deadline: str | None
    identification_basis: str | None
    images: list[DetailImageResponse]
    analysis: DetailAnalysisResponse


class HazardListItem(BaseModel):
    id: str
    status: str
    created_at: str
    discovery_time: str
    description: str | None
    category: str | None
    type: str | None
    level: str | None
    discovery_source: str
    rectification_deadline: str | None
    location: str | None
    equipment_name: str | None
    image_count: int
    thumbnail_url: str | None
    manual_review_required: bool


class HazardListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[HazardListItem]


class HazardContentAnalysisResponse(BaseModel):
    id: str
    status: str
    analyzed_at: str
    model: str
    confidence: float | None
    summary: str
    focus_hint: str
    risk_assessment: str
    impact: str
    root_cause: str
    key_findings: list[str]
    recommended_actions: list[str]
    manual_review_required: bool
    manual_review_items: list[str]
    evidence: list[dict[str, Any]]
    regions: list[HazardRegionResponse] = []
    findings: list[dict[str, Any]] = []
    risk_impacts: list[str] = []
    response_deadline: dict[str, Any] | None = None


def load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key.strip()):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


load_dotenv_file(PROJECT_DIR / ".env")


def env_url(name: str, default: str) -> str:
    return os.getenv(name, default).rstrip("/")


def load_config() -> Config:
    return Config(
        vision_base_url=env_url("VISION_BASE_URL", "https://www.ai.atyou.cn/v1"),
        vision_model=os.getenv("VISION_MODEL", "deepseek-v4-flash-vision-exp"),
        vision_api_key=os.getenv("VISION_API_KEY", ""),
        dify_base_url=env_url("DIFY_BASE_URL", "http://172.20.1.81/v1"),
        dify_api_key=os.getenv("DIFY_API_KEY", ""),
        hazard_rules_dataset_id=os.getenv("DIFY_HAZARD_RULES_DATASET_ID", ""),
        api_auth_token=os.getenv("API_AUTH_TOKEN", ""),
        cors_origin=os.getenv("CORS_ORIGIN", "*"),
        upstream_trust_env=os.getenv("UPSTREAM_TRUST_ENV", "false").strip().lower() in {"1", "true", "yes", "on"},
    )


CONFIG = load_config()


class UpstreamError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


async def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 90,
) -> Any:
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=CONFIG.upstream_trust_env) as client:
            response = await client.request(method, url, headers=headers, json=body)
    except httpx.HTTPError as error:
        raise UpstreamError(f"{method} {url} 网络请求失败: {error}", retryable=True) from error
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    if not response.is_success:
        detail = None
        if isinstance(payload, dict):
            error_value = payload.get("error")
            detail = error_value.get("message") if isinstance(error_value, dict) else None
            detail = detail or payload.get("message") or payload.get("detail")
        raise UpstreamError(
            f"{method} {url} 返回 HTTP {response.status_code}: {detail or response.text[:500]}",
            status_code=response.status_code,
            retryable=response.status_code == 408 or response.status_code == 429 or response.status_code >= 500,
        )
    return payload


def ensure_pipeline_config() -> None:
    missing = []
    if not CONFIG.vision_api_key:
        missing.append("VISION_API_KEY")
    if not CONFIG.dify_api_key:
        missing.append("DIFY_API_KEY")
    if not CONFIG.hazard_rules_dataset_id:
        missing.append("DIFY_HAZARD_RULES_DATASET_ID")
    if missing:
        raise HTTPException(status_code=503, detail=f"缺少服务配置: {', '.join(missing)}")


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


def image_mime_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def sniff_image_mime_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


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


REGION_BACKFILL_LOCKS: dict[str, asyncio.Lock] = {}


def region_backfill_lock(record_id: str) -> asyncio.Lock:
    return REGION_BACKFILL_LOCKS.setdefault(record_id, asyncio.Lock())


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


HEAT_SAFETY_KEYWORDS = (
    "热力", "供热", "热源", "热网", "锅炉", "蒸汽", "热水", "管道", "阀门",
    "换热", "泵站", "热力站", "补偿器", "管沟", "压力管道",
)


def is_heat_context(analysis: dict[str, Any]) -> bool:
    context_text = " ".join([
        as_text(analysis.get("hazard_description")),
        as_text(analysis.get("hazard_category")),
        as_text(analysis.get("hazard_type")),
        as_text(analysis.get("equipment_name")),
        as_text(analysis.get("observations")),
    ])
    return any(keyword in context_text for keyword in HEAT_SAFETY_KEYWORDS)


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


def content_analysis_prompt(draft: dict[str, Any], *, include_regions: bool = False) -> str:
    evidence = draft.get("evidence") or []
    evidence_text = "\n".join(
        f"- {item.get('document') or '隐患规则库'}：{item.get('content') or ''}"
        for item in evidence[:6]
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
""".strip()


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
    result = await request_vision_completion([{"role": "user", "content": contents}], max_tokens=1600)
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
        "manual_review_required": bool(manual_items),
        "manual_review_items": manual_items,
        "evidence": draft.get("evidence") or [],
        "regions": regions,
    }


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


async def save_upload(upload: tuple[str, str, bytes, str], record_id: str, index: int) -> tuple[dict[str, Any], Path]:
    filename, mime_type, data, extension = upload
    await asyncio.to_thread(UPLOAD_DIR.mkdir, parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / f"{record_id}-{index + 1}{extension}"
    await asyncio.to_thread(file_path.write_bytes, data)
    metadata = {
        "filename": filename,
        "mime_type": mime_type,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "path": str(file_path),
    }
    return metadata, file_path


async def save_result(record_id: str, result: dict[str, Any]) -> None:
    await asyncio.to_thread(RESULT_DIR.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(
        (RESULT_DIR / f"{record_id}.json").write_text,
        json.dumps(result, ensure_ascii=False, indent=2),
        "utf-8",
    )


async def load_result(record_id: str) -> dict[str, Any]:
    try:
        UUID(record_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="识别记录 ID 格式错误") from error
    path = RESULT_DIR / f"{record_id}.json"
    if path.exists():
        return json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
    record = seed_records().get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="识别记录不存在")
    return record


async def normalize_upload(upload: UploadFile) -> tuple[str, str, bytes, str]:
    mime_type = (upload.content_type or mimetypes.guess_type(upload.filename or "")[0] or "").lower().split(";")[0].strip()
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="仅支持 JPG、PNG、WEBP 图片")
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="图片文件为空")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"图片超过大小限制（{MAX_IMAGE_BYTES} 字节）")
    return Path(upload.filename or "upload").name, mime_type, data, ALLOWED_MIME_TYPES[mime_type]


async def parse_request(request: Request) -> tuple[list[tuple[str, str, bytes, str]], dict[str, str]]:
    content_type = (request.headers.get("content-type") or "").lower()
    fields: dict[str, str] = {}
    uploads: list[tuple[str, str, bytes, str]] = []
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        for key, value in form.multi_items():
            if key in {"images", "image"} and isinstance(value, StarletteUploadFile):
                uploads.append(await normalize_upload(value))
            elif key not in {"images", "image"}:
                fields[key] = str(value or "").strip()
    elif content_type.startswith("application/json"):
        try:
            payload = await request.json()
        except json.JSONDecodeError as error:
            raise HTTPException(status_code=400, detail="JSON 请求体格式错误") from error
        raw_images = payload.get("images") or payload.get("image_base64")
        if isinstance(raw_images, str):
            raw_images = [raw_images]
        if not isinstance(raw_images, list) or not raw_images:
            raise HTTPException(status_code=400, detail="JSON 请求缺少 images 或 image_base64")
        for index, raw in enumerate(raw_images):
            if not isinstance(raw, str):
                raise HTTPException(status_code=400, detail=f"第 {index + 1} 张图片格式错误")
            match = re.match(r"data:(image/(?:jpeg|png|webp));base64,(.+)", raw, flags=re.IGNORECASE | re.DOTALL)
            if not match:
                raise HTTPException(status_code=400, detail=f"第 {index + 1} 张图片必须是 data URL")
            mime_type, encoded = match.groups()
            try:
                data = base64.b64decode(encoded, validate=True)
            except ValueError as error:
                raise HTTPException(status_code=400, detail=f"第 {index + 1} 张图片 base64 格式错误") from error
            if len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail=f"第 {index + 1} 张图片超过大小限制")
            uploads.append((f"image-{index + 1}", mime_type.lower(), data, ALLOWED_MIME_TYPES[mime_type.lower()]))
        for key, value in payload.items():
            if key not in {"images", "image_base64"} and value is not None:
                fields[key] = str(value).strip()
    elif content_type.startswith("image/") or content_type == "application/octet-stream":
        data = await request.body()
        mime_type = content_type if content_type in ALLOWED_MIME_TYPES else sniff_image_mime_type(data)
        if not mime_type:
            raise HTTPException(status_code=415, detail="原始图片请求无法识别格式，仅支持 JPG、PNG、WEBP")
        if not data:
            raise HTTPException(status_code=400, detail="图片文件为空")
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail=f"图片超过大小限制（{MAX_IMAGE_BYTES} 字节）")
        uploads.append(("upload", mime_type, data, ALLOWED_MIME_TYPES[mime_type]))
    else:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的 Content-Type: {content_type or '未提供'}；请使用 multipart/form-data、application/json 或直接发送图片",
        )
    if not uploads:
        raise HTTPException(status_code=400, detail="缺少 images 文件字段")
    if len(uploads) > MAX_IMAGE_COUNT:
        raise HTTPException(status_code=400, detail=f"单次最多上传 {MAX_IMAGE_COUNT} 张图片")
    return uploads, fields


def public_images(record_id: str, count: int) -> list[dict[str, Any]]:
    return [
        {"index": index, "url": f"/api/v1/hazard-identifications/{record_id}/images/{index}"}
        for index in range(count)
    ]


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
            description="金属立柱根部存在大面积锈蚀，局部保护层脱落并出现破损。",
            category="基础设施",
            hazard_type="设备设施事故隐患",
            location="室外设备区域",
            equipment_name="金属立柱",
            actions=["安排专业人员检查腐蚀范围", "完成除锈、防腐及破损部位修复"],
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
        "00000000-0000-4000-8000-000000000003": seed_record(
            record_id="00000000-0000-4000-8000-000000000003",
            created_at="2026-08-25T03:00:00Z",
            image_indexes=(0, 1),
            description="楼梯间墙面及构件存在受潮、锈蚀和表面破损，通行区域维护状况较差。",
            category="基础设施",
            hazard_type="人身安全隐患",
            location="楼梯间及相邻管道区域",
            equipment_name="楼梯及墙面构件",
            actions=["设置现场警示并排查受潮原因", "修复墙面和构件破损，保持通道安全"],
        ),
        "00000000-0000-4000-8000-000000000004": seed_record(
            record_id="00000000-0000-4000-8000-000000000004",
            created_at="2026-08-25T03:45:00Z",
            image_indexes=(0,),
            description="金属支撑构件根部腐蚀严重并伴随明显截面破损，存在承载能力下降风险。",
            category="基础设施",
            hazard_type="设备设施事故隐患",
            location="设备基础区域",
            equipment_name="金属支撑构件",
            actions=["立即设置隔离和警示", "由专业人员复核承载状态并制定加固或更换方案"],
            level="重大隐患",
            review_items=["需人工复核设备名称、腐蚀深度及重大隐患等级"],
        ),
        "00000000-0000-4000-8000-000000000005": seed_record(
            record_id="00000000-0000-4000-8000-000000000005",
            created_at="2026-08-25T04:30:00Z",
            image_indexes=(0, 1),
            description="同一处设施从多个角度可见构件锈蚀、墙面锈水和局部破损，需开展联合排查。",
            category="生产设备",
            hazard_type="设备设施事故隐患",
            location="设备间及相邻墙体",
            equipment_name="管道、阀门及墙体构件",
            actions=["结合两张图片核对隐患范围", "排查渗漏源并完成防腐、修复和复验"],
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
            "thumbnail_url": f"/api/v1/hazard-identifications/{record_id}/images/{index}?w=128",
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


def detail_evidence(items: Any) -> dict[str, list[dict[str, Any]]]:
    laws: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []
    for item in clean_evidence(items):
        document = str(item.get("document") or "")
        content = str(item.get("content") or "")
        if not content:
            continue
        if document.startswith("05_热力安全"):
            matches = list(re.finditer(r"###\s+(HS-[A-Z0-9-]+)\s+(.+?)(?=\n|$)", content))
            if matches:
                for match in matches:
                    start = match.end()
                    section = content[start:]
                    laws.append({
                        "title": match.group(2).strip(),
                        "article": re.search(r"第[一二三四五六七八九十百0-9]+条", section).group(0)
                        if re.search(r"第[一二三四五六七八九十百0-9]+条", section) else None,
                        "excerpt": evidence_excerpt(section),
                        "source_url": evidence_source_url(section),
                    })
            else:
                laws.append({
                    "title": "热力安全法规与标准依据",
                    "article": None,
                    "excerpt": evidence_excerpt(content),
                    "source_url": evidence_source_url(content),
                })
            continue
        if document.startswith("06_供热单位隐患识别与分级规则"):
            code_match = re.search(r"\bR-[A-Z0-9-]+\b", content)
            first_line = next((line.strip() for line in content.splitlines() if line.strip()), "供热单位隐患识别与分级规则")
            name = re.sub(r"^R-[A-Z0-9-]+\s*", "", first_line).strip() or first_line
            rules.append({
                "code": code_match.group(0) if code_match else None,
                "name": name,
                "excerpt": evidence_excerpt(content),
                "risk_level": "高风险" if "重大隐患" in content else "一般风险" if "一般隐患" in content else None,
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


def public_detail_result(result: dict[str, Any]) -> dict[str, Any]:
    draft = dict(result.get("hazard_draft") or {})
    content_analysis = dict(result.get("content_analysis") or {})
    image_count = len(result.get("images") or [])
    regions = normalize_regions(
        (result.get("vision") or {}).get("analysis", {}).get("regions"),
        image_count,
    )
    evidence = detail_evidence(draft.get("evidence") or content_analysis.get("evidence"))
    analysis = {
        "summary": limit_text(content_analysis.get("summary"), 1000) or draft.get("description"),
        "confidence": unit_coordinate(content_analysis.get("confidence")) or unit_coordinate(
            (result.get("vision") or {}).get("analysis", {}).get("confidence")
        ),
        "findings": detail_findings(content_analysis, draft, evidence),
        "risk_impacts": unique_texts(content_analysis.get("risk_impacts")),
        "recommended_actions": unique_texts(content_analysis.get("recommended_actions"))
        or unique_texts(draft.get("suggested_actions")),
        "response_deadline": content_analysis.get("response_deadline")
        if isinstance(content_analysis.get("response_deadline"), dict) else None,
        "evidence": evidence,
    }
    if not analysis["risk_impacts"]:
        impact = nullable_text(content_analysis.get("impact"))
        if impact and impact != "待现场核实":
            analysis["risk_impacts"] = [impact]
    if analysis["response_deadline"] is None and draft.get("rectification_deadline"):
        urgency = "urgent" if draft.get("level") == "重大隐患" else "normal"
        analysis["response_deadline"] = {
            "urgency": urgency,
            "text": f"建议在 {draft['rectification_deadline']} 前完成整改并复核",
        }
    return {
        "id": result["id"],
        "report_no": result.get("report_no"),
        "status": "identified",
        "created_at": result.get("created_at") or "",
        "discovery_time": draft.get("discovery_time") or result.get("created_at") or "",
        "model": content_analysis.get("model") or (result.get("vision") or {}).get("model"),
        "analyzed_at": content_analysis.get("analyzed_at"),
        "analyzer": {"type": "system", "name": "系统自动分析"},
        "description": draft.get("description"),
        "category": draft.get("category"),
        "type": draft.get("type"),
        "level": draft.get("level"),
        "level_source": draft.get("level_source"),
        "discovery_source": draft.get("discovery_source"),
        "location": draft.get("location"),
        "equipment_name": draft.get("equipment_name"),
        "image_count": image_count,
        "thumbnail_url": f"/api/v1/hazard-identifications/{result['id']}/images/0" if image_count else None,
        "manual_review_required": bool(draft.get("manual_review_required") or content_analysis.get("manual_review_required")),
        "rectification_deadline": draft.get("rectification_deadline"),
        "identification_basis": "；".join(unique_texts(draft.get("observations"))) or draft.get("description"),
        "images": detail_images(str(result["id"]), image_count, regions),
        "analysis": analysis,
    }


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


app = FastAPI(
    title="隐患识别后端 API",
    version="1.0.0",
    description="多模态图片隐患识别、知识库判定、隐患内容分析和处理建议。",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in CONFIG.cors_origin.split(",") if item.strip()] or ["*"],
    allow_credentials=CONFIG.cors_origin != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

if DEMO_FRONTEND_DIR.exists():
    app.mount("/demo", StaticFiles(directory=DEMO_FRONTEND_DIR, html=True), name="standalone-frontend")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if CONFIG.api_auth_token and request.url.path not in {"/api/v1/health", "/docs", "/openapi.json", "/redoc"}:
        if request.headers.get("Authorization") != f"Bearer {CONFIG.api_auth_token}":
            raise HTTPException(status_code=401, detail="缺少或无效的 API 认证令牌")
    return await call_next(request)


@app.get("/api/v1/health", tags=["system"], summary="健康检查")
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


@app.get(
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


@app.post(
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


@app.post(
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


@app.get(
    "/api/v1/hazard-identifications/{record_id}",
    tags=["hazard-identifications"],
    summary="获取隐患识别记录详情",
    description="返回详情报告页所需的基础信息、图像区域、法规/规则依据和 AI 分析结果；首次访问时自动生成并缓存分析。",
    response_model=HazardDetailResponse,
)
async def get_hazard_identification(record_id: str) -> dict[str, Any]:
    await analyze_hazard_identification(record_id)
    return public_detail_result(await load_result(record_id))


@app.get("/api/v1/hazard-identifications/{record_id}/images/{index}", tags=["hazard-identifications"], summary="获取隐患图片")
async def get_hazard_image(record_id: str, index: int) -> FileResponse:
    result = await load_result(record_id)
    if index < 0 or index >= len(result["images"]):
        raise HTTPException(status_code=404, detail="图片序号不存在")
    path = Path(result["images"][index]["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="图片文件不存在")
    return FileResponse(path, media_type=result["images"][index]["mime_type"])
