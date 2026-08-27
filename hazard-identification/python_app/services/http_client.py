"""上游服务 HTTP 调用与错误转换。"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import CONFIG
from ..errors import UpstreamError


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
