"""本地图片与 JSON 隐患记录存储。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from ..config import RESULT_DIR, UPLOAD_DIR


async def save_upload(
    upload: tuple[str, str, bytes, str],
    record_id: str,
    index: int,
) -> tuple[dict[str, Any], Path]:
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


async def load_persisted_result(record_id: str) -> dict[str, Any] | None:
    path = RESULT_DIR / f"{record_id}.json"
    if not path.exists():
        return None
    return json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
