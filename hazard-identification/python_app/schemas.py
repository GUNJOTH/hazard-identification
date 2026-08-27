"""HTTP 接口的请求与响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


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
    regions: list[DetailRegionResponse]


class DetailLawEvidence(BaseModel):
    title: str
    article: str | None
    articleContent: str | None = None
    excerpt: str
    violationReason: str | None = None
    aiSummary: str | None = None


class DetailRuleEvidence(BaseModel):
    title: str
    riskLevelText: str | None
    excerpt: str
    aiSummary: str | None = None


class DetailEvidenceResponse(BaseModel):
    laws: list[DetailLawEvidence]
    rules: list[DetailRuleEvidence]


class DetailBasicResponse(BaseModel):
    reportNo: str | None
    createdAt: str
    source: str | None
    model: str | None
    analyst: str | None
    analyzedAt: str | None


class DetailMediaResponse(BaseModel):
    imageBasis: str | None
    images: list[DetailImageResponse]


class DetailFindingRiskBadge(BaseModel):
    text: str | None


class DetailFindingResponse(BaseModel):
    description: str
    reason: str | None
    location: str | None
    riskBadge: DetailFindingRiskBadge
    confidenceText: str | None
    basisText: str | None


class DetailSuggestionDeadline(BaseModel):
    isUrgent: bool
    text: str


class DetailSuggestionResponse(BaseModel):
    impacts: list[str]
    actions: list[str]
    deadline: DetailSuggestionDeadline


class HazardDetailResponse(BaseModel):
    basic: DetailBasicResponse
    media: DetailMediaResponse
    evidence: DetailEvidenceResponse
    findings: list[DetailFindingResponse]
    suggestion: DetailSuggestionResponse


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
    evidence_summary: dict[str, list[dict[str, Any]]] = {}
