"""AI 流水线公共配置校验。"""

from fastapi import HTTPException

from ..config import CONFIG


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
