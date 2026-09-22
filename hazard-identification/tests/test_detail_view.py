"""详情视图字段与隐患编码的回归测试。

覆盖代码评审提出的两个风险点：

1. ``basic`` 字段改名（model/analyst → category/type）必须保留兼容别名，
   否则已发版前端与外部集成方读取旧字段时会拿到 null，详情页出现稳定回归；
2. ``CM_PL_PJO_LINECODE`` 只能取记录顶层登记的台账值：既不按记录 ID 或描述
   文本反查猜测，也不采用 ``hazard_draft`` / ``content_analysis`` 等模型产物中
   的同名字段，避免业务主数据被模型输出覆盖。
"""

from __future__ import annotations

import pytest

from python_app.services.detail_view import public_detail_result, record_hazard_code
from python_app.services.identification import hazard_code_from_context


def make_record(**overrides: object) -> dict:
    """构造一份最小可用的记录，字段对齐 runtime/results 落盘结构。"""
    record: dict = {
        "id": "11111111-1111-4111-8111-111111111111",
        "created_at": "2026-08-26T08:00:00Z",
        "report_no": None,
        "images": [],
        "vision": {"analysis": {}},
        "hazard_draft": {
            "description": "电缆外皮破损露出内部导线",
            "category": "生产设备",
            "type": "设备设施事故隐患",
            "discovery_source": "图片上传识别",
            "equipment_name": "电缆",
            "location": "配电间",
            "observations": ["电缆外皮破损"],
        },
        "content_analysis": {
            "analyzed_at": "2026-08-26T08:02:11Z",
            "summary": "电缆外皮破损",
            "findings": [{"description": "电缆外皮破损露出内部导线"}],
        },
    }
    record.update(overrides)
    return record


def test_basic_keeps_canonical_fields_and_compat_aliases() -> None:
    """category/type 与兼容别名 model/analyst 同时存在且取值一致。"""
    basic = public_detail_result(make_record())["basic"]

    assert basic["category"] == "生产设备"
    assert basic["type"] == "设备设施事故隐患"
    # 已发版前端读的是旧字段名，缺失即回归
    assert basic["model"] == basic["category"]
    assert basic["analyst"] == basic["type"]


def test_hazard_code_is_read_from_record() -> None:
    """编码随记录保存时，详情与列表都应原样读出。"""
    record = make_record(hazard_code="CE20260831.003")

    assert record_hazard_code(record) == "CE20260831.003"
    assert public_detail_result(record)["basic"]["CM_PL_PJO_LINECODE"] == "CE20260831.003"


@pytest.mark.parametrize("container", ["hazard_draft", "content_analysis"])
@pytest.mark.parametrize("field", ["hazard_code", "CM_PL_PJO_LINECODE"])
def test_hazard_code_is_ignored_outside_record_top_level(container: str, field: str) -> None:
    """模型产物层出现的同名字段必须忽略，不得当作官方台账编码返回。

    content_analysis 是 AI 分析结果、hazard_draft 同样是模型输出：二者出现
    hazard_code 属于模型幻觉或历史迁移残留，一旦采信就会让业务主数据被模型结果覆盖。
    """
    record = make_record()
    record[container][field] = "CE20260901.003"

    assert record_hazard_code(record) is None
    assert public_detail_result(record)["basic"]["CM_PL_PJO_LINECODE"] is None


def test_record_top_level_code_wins_over_model_output() -> None:
    """台账登记值优先，模型产物中的同名字段不得覆盖它。"""
    record = make_record(hazard_code="CE20260831.003")
    record["hazard_draft"]["hazard_code"] = "MODEL-OUTPUT"
    record["content_analysis"]["CM_PL_PJO_LINECODE"] = "MODEL-OUTPUT"

    assert record_hazard_code(record) == "CE20260831.003"
    assert public_detail_result(record)["basic"]["CM_PL_PJO_LINECODE"] == "CE20260831.003"


def test_hazard_code_missing_returns_none_instead_of_guessing() -> None:
    """记录未登记编码时必须返回 None，不能凭描述或 ID 猜一个出来。"""
    record = make_record()

    assert record_hazard_code(record) is None
    assert public_detail_result(record)["basic"]["CM_PL_PJO_LINECODE"] is None


@pytest.mark.parametrize(
    ("record_id", "description", "legacy_code"),
    [
        ("3d7c9a58-8cd7-4a58-b674-cb9f2a616609", "电缆外皮破损露出内部导线", "CE20260831.003"),
        ("f47ab829-c749-463b-961a-e558cf06fec1", "管道法兰连接处存在泄漏痕迹", "CE20260901.003"),
        ("7c8ee1b4-5c0f-4bf8-ace1-395b8f600413", "电气柜周边积水", "CE20260901.004"),
        ("00000000-0000-4000-8000-000000000001", "右侧墙面及天花板存在锈迹和水渍", "CE20260831.006"),
        ("00000000-0000-4000-8000-000000000002", "管道及阀门连接部位锈蚀", "CE20260831.004"),
    ],
)
def test_removed_hardcoded_pairs_are_not_reintroduced(
    record_id: str, description: str, legacy_code: str
) -> None:
    """历史硬编码映射（记录 ID / 描述文本 → 编码）必须彻底失效。

    这些键值当初是为了让演示数据显示编码而写死的，代价是记录一旦变更就会
    显示错误编码。此处把它们固化成断言：即使 ID 与描述完全复现，也不得再返回。
    """
    record = make_record(id=record_id)
    record["hazard_draft"]["description"] = description
    record["content_analysis"]["findings"] = [{"description": description}]

    assert record_hazard_code(record) is None


def test_suggestion_and_findings_sections_still_render() -> None:
    """改动编码读取逻辑后，其余区块结构不受影响。"""
    detail = public_detail_result(make_record())

    assert set(detail) == {"basic", "media", "evidence", "findings", "suggestion"}
    assert set(detail["media"]) == {"imageBasis", "images"}
    assert set(detail["suggestion"]) == {"impacts", "actions", "deadline"}


@pytest.mark.parametrize("field", ["hazard_code", "CM_PL_PJO_LINECODE", "cm_pl_pjo_linecode"])
def test_hazard_code_is_accepted_from_create_request(field: str) -> None:
    """创建隐患单时携带的编码按原值保存（兼容三种字段写法）。"""
    assert hazard_code_from_context({field: "CE20260831.003"}) == "CE20260831.003"


def test_hazard_code_absent_from_create_request_stays_empty() -> None:
    """请求未携带编码时不生成占位值，避免凭空造出一个台账编码。"""
    assert hazard_code_from_context({}) is None
    assert hazard_code_from_context({"hazard_code": "   "}) is None
