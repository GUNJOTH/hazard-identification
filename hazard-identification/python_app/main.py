"""FastAPI 应用装配入口。"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.hazards import router as hazard_router
from .config import CONFIG, DEMO_FRONTEND_DIR


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


app.include_router(hazard_router)
