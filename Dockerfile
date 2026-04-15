FROM python:3.12-slim

WORKDIR /app

# 系统依赖
# 系统依赖（精简版 — Chromium 相关库不再需要，改用 Jina Reader API）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 不预装 Chromium — 使用 Jina Reader API 替代（免费、无需本地浏览器、支持 JS 渲染）
# 本地开发如需 Playwright: PLAYWRIGHT_ENABLED=1 + python3 -m patchright install chromium
# RUN python3 -m patchright install chromium

COPY . .

# 创建数据目录
RUN mkdir -p .crabres/memory .crabres/skills .crabres/crawl .crabres/notifications /data/workspace



CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]
