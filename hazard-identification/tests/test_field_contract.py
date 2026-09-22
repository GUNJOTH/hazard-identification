"""响应字段、前端读取与接口文档的一致性契约测试。

本次评审的回归根因是「后端字段改名，前端与文档没跟上」。
这类问题靠人工检查容易漏，这里把前端源码实际读取的字段名与后端响应模型
做机械比对，让"改名漏改前端"在测试阶段暴露，而不是等详情页显示"待确认"。
"""

from __future__ import annotations

import re
from pathlib import Path

from python_app.schemas import DetailBasicResponse, HazardListItem

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_JS = PROJECT_ROOT / "test" / "frontend" / "analysis.js"
ANALYSIS_HTML = PROJECT_ROOT / "test" / "frontend" / "analysis.html"
API_DOC = PROJECT_ROOT / "API.md"

BASIC_FIELD_PATTERN = re.compile(r"\bbasic\.([A-Za-z_][A-Za-z0-9_]*)")


def basic_fields_read_by_frontend() -> set[str]:
    """解析 analysis.js 中所有 `basic.xxx` 形式的字段读取。"""
    return set(BASIC_FIELD_PATTERN.findall(ANALYSIS_JS.read_text(encoding="utf-8")))


def test_frontend_only_reads_fields_declared_by_backend() -> None:
    """前端读取的每个 basic 字段都必须由后端响应模型声明。"""
    used = basic_fields_read_by_frontend()
    assert used, "未能从 analysis.js 解析出 basic 字段读取，解析逻辑或前端结构已变化"

    declared = set(DetailBasicResponse.model_fields)
    undeclared = used - declared
    assert not undeclared, (
        f"前端读取了后端未声明的 basic 字段：{sorted(undeclared)}；"
        "后端改名后必须同步前端，否则详情页会回落到占位文案"
    )


def test_frontend_reads_canonical_category_and_type() -> None:
    """前端应读取规范字段名 category/type，而不是只依赖兼容别名。"""
    used = basic_fields_read_by_frontend()
    missing = {"category", "type"} - used
    assert not missing, f"前端仍未读取规范字段：{sorted(missing)}"


def test_detail_schema_exposes_hazard_code_and_compat_aliases() -> None:
    """响应模型必须同时声明编码字段与兼容别名，避免被序列化时过滤。"""
    fields = set(DetailBasicResponse.model_fields)
    required = {"CM_PL_PJO_LINECODE", "category", "type", "model", "analyst", "analyzedAt"}
    assert required <= fields, f"DetailBasicResponse 缺少字段：{sorted(required - fields)}"


def test_list_item_schema_exposes_hazard_code() -> None:
    """列表项同样返回编码字段。"""
    assert "CM_PL_PJO_LINECODE" in HazardListItem.model_fields


def test_frontend_element_ids_exist_in_html() -> None:
    """analysis.js 里 $('id') 引用的元素必须在 analysis.html 中存在。

    前端字段改名往往连带元素 id 一起改，最容易出现改一处漏一处。
    """
    js = ANALYSIS_JS.read_text(encoding="utf-8")
    html = ANALYSIS_HTML.read_text(encoding="utf-8")

    referenced = set(re.findall(r"\$\('([A-Za-z_][A-Za-z0-9_]*)'\)", js))
    available = set(re.findall(r'id="([A-Za-z_][A-Za-z0-9_]*)"', html))
    missing = referenced - available

    assert not missing, f"analysis.js 引用了 analysis.html 中不存在的元素 id：{sorted(missing)}"


def test_api_doc_documents_detail_basic_fields() -> None:
    """接口文档需覆盖本次新增/改名的字段，防止实现与文档再次脱节。"""
    doc = API_DOC.read_text(encoding="utf-8")

    for token in ("CM_PL_PJO_LINECODE", "basic.category", "basic.type", "basic.CM_PL_PJO_LINECODE"):
        assert token in doc, f"API.md 未记录 {token}"
