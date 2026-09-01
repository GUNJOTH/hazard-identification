# 隐患识别后端 —— Docker 镜像
# 构建：docker compose build（或 docker build -t hazard-identification:latest .）
# 运行：见 docker-compose.yml 与 DEPLOY_DOCKER.md

FROM python:3.12-slim

# 时区（日志与时间显示用）
ENV TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    HAZARD_RUNTIME_DIR=/app/data

WORKDIR /app

# 1) 先拷贝依赖清单，利用 Docker 层缓存
COPY pyproject.toml uv.lock ./

# 2) 安装 uv 并按 uv.lock 锁定版本安装生产依赖（不安装项目本体，package=false）
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --no-install-project \
    && pip install --no-cache-dir tzdata

# 3) 拷贝全部源码（含 test/frontend 演示前端、test/multi-angle 演示图片、knowledge-base）
COPY . .

# 4) 以非 root 用户运行：创建应用用户和数据目录
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8787

# 使用项目内 .venv 启动，--no-sync 避免每次启动都检查依赖
CMD ["uv", "run", "--no-sync", "uvicorn", "python_app.main:app", "--host", "0.0.0.0", "--port", "8787"]