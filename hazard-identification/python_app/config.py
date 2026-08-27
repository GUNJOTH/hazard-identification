"""应用配置、运行目录和固定枚举。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


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
DISCOVERY_SOURCES = ("安全检查", "巡检", "缺陷", "隐患排查", "图片上传识别")
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


load_dotenv_file(PROJECT_DIR / ".env")
CONFIG = load_config()
