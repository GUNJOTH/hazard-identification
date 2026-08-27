"""隐患图片识别请求的解析与校验。"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile
from starlette.datastructures import UploadFile as StarletteUploadFile

from ..config import ALLOWED_MIME_TYPES, MAX_IMAGE_BYTES, MAX_IMAGE_COUNT
from ..utils.images import sniff_image_mime_type


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
