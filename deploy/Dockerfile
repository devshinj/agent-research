# ── Stage 1: Python 패키지 빌드 ──
FROM python:3.12-slim AS py-builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir uv \
    && uv pip install --system --no-cache-dir .

# ── Stage 2: React 프론트엔드 빌드 ──
FROM node:22-slim AS web-builder

WORKDIR /app/frontend

COPY src/ui/frontend/package.json src/ui/frontend/package-lock.json* ./
RUN npm ci --ignore-scripts

COPY src/ui/frontend/ ./

ARG VITE_API_URL
ARG VITE_WS_URL

RUN npm run build

# ── Stage 3: Nginx (프론트엔드 + 리버스 프록시) ──
FROM nginx:alpine AS web

RUN rm /etc/nginx/conf.d/default.conf
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=web-builder /app/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

# ── Stage 4: FastAPI 런타임 ──
FROM python:3.12-slim AS app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=py-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=py-builder /usr/local/bin /usr/local/bin

RUN groupadd --gid 1001 appuser \
    && useradd --uid 1001 --gid appuser --no-create-home appuser

COPY src/ ./src/
COPY config/ ./config/

RUN mkdir -p data/models && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["python", "-m", "src.main"]
