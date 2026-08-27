"""API3 五区块详情视图组装。"""

from __future__ import annotations

import re
from typing import Any

from ..schemas import DetailBbox
from ..utils.evidence import clean_evidence
from ..utils.geometry import normalize_regions, unit_coordinate
from ..utils.text import as_text, limit_text, nullable_text, unique_texts, valid_date


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
        if document.startswith("05_热力安全"):
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
    return {"high": "高", "medium": "中", "low": "低"}.get(str(value or "").strip().lower())


def detail_public_confidence(value: Any) -> str | None:
    confidence = unit_coordinate(value)
    return f"{confidence:.2f}" if confidence is not None else None


def detail_public_basis_text(value: Any) -> str | None:
    labels = {
        "image_feature": "图像特征", "image_features": "图像特征", "图像特征": "图像特征",
        "law": "法规", "laws": "法规", "法规": "法规",
        "rule": "规则", "rules": "规则", "规则": "规则",
        "knowledge": "知识库", "知识库": "知识库",
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
        "laws": [{
            "title": item["title"], "article": item.get("article"), "articleContent": item.get("article_content"),
            "excerpt": item["excerpt"], "violationReason": item.get("violation_reason"), "aiSummary": item.get("ai_summary"),
        } for item in evidence.get("laws", [])],
        "rules": [{
            "title": item.get("name") or item.get("code") or "企业隐患规则", "riskLevelText": item.get("risk_level"),
            "excerpt": item["excerpt"], "aiSummary": item.get("ai_summary"),
        } for item in evidence.get("rules", [])],
    }


def detail_public_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "description": item["description"], "reason": item.get("reason"), "location": item.get("location"),
        "riskBadge": {"text": detail_public_risk_text(item.get("risk_level"))},
        "confidenceText": detail_public_confidence(item.get("confidence")), "basisText": detail_public_basis_text(item.get("basis")),
    } for item in findings]


def detail_public_deadline(value: Any, draft: dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        text = limit_text(value.get("text"), 500)
        urgency = str(value.get("urgency") or "").strip().lower()
        if text:
            return {"isUrgent": bool(value.get("isUrgent") is True or urgency == "urgent"), "text": text}
    deadline = valid_date(draft.get("rectification_deadline"))
    if deadline:
        return {"isUrgent": draft.get("level") == "重大隐患", "text": f"建议在 {deadline} 前完成整改并复核"}
    return {"isUrgent": False, "text": "建议结合现场风险评估确定整改时限"}


def public_detail_result(result: dict[str, Any]) -> dict[str, Any]:
    draft = dict(result.get("hazard_draft") or {})
    content_analysis = dict(result.get("content_analysis") or {})
    image_count = len(result.get("images") or [])
    regions = normalize_regions((result.get("vision") or {}).get("analysis", {}).get("regions"), image_count)
    context_text = " ".join([
        as_text(draft.get("description")), as_text(draft.get("category")), as_text(draft.get("type")),
        as_text(draft.get("equipment_name")), as_text(draft.get("location")),
        " ".join(unique_texts(draft.get("observations"))), as_text(content_analysis.get("summary")),
        " ".join(unique_texts(content_analysis.get("key_findings"))),
        " ".join(as_text(item.get("description")) + " " + as_text(item.get("reason"))
                 for item in (content_analysis.get("findings") or []) if isinstance(item, dict)),
    ])
    evidence = detail_evidence(draft.get("evidence") or content_analysis.get("evidence"), context_text, content_analysis.get("evidence_summary"))
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
        "basic": {"reportNo": result.get("report_no"), "createdAt": result.get("created_at") or "",
                  "source": draft.get("discovery_source"), "model": draft.get("category"),
                  "analyst": draft.get("type"), "analyzedAt": content_analysis.get("analyzed_at")},
        "media": {"imageBasis": image_basis, "images": detail_images(str(result["id"]), image_count, regions)},
        "evidence": detail_public_evidence(evidence),
        "findings": detail_public_findings(findings),
        "suggestion": {"impacts": impacts, "actions": actions,
                       "deadline": detail_public_deadline(content_analysis.get("response_deadline"), draft)},
    }
