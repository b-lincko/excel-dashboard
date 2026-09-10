# Linkco MR — production image (same topology as deploy/nginx.conf):
#   browser -> nginx :8000 (public) -> uvicorn 127.0.0.1:8001 (loopback)
# nginx serves the built frontend and proxies /api; the backend is never
# exposed. file.xlsx, data/ and backups/ are mounted at runtime (see
# docker-compose.yml) — nothing stateful is baked into the image.
FROM node:20-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Build, then pre-compress for nginx gzip_static (served as .gz directly).
RUN npm run build \
    && cd dist \
    && find . -type f \( -name '*.js' -o -name '*.css' -o -name '*.html' -o -name '*.svg' \) -exec gzip -9k {} \;

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WOMS_HOST=127.0.0.1 \
    WOMS_PORT=8001

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx curl \
    && rm -rf /var/lib/apt/lists/* \
    && nginx -v

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --prefer-binary -r /app/backend/requirements.txt

COPY backend /app/backend
COPY --from=frontend /src/dist /app/frontend/dist
COPY deploy/nginx-docker.conf /app/deploy/nginx-docker.conf
COPY deploy/mime.types /app/deploy/mime.types
COPY deploy/proxy_params.conf /app/deploy/proxy_params.conf
COPY deploy/maintenance.json /app/deploy/maintenance.json
COPY deploy/docker-entrypoint.sh /app/deploy/docker-entrypoint.sh
RUN chmod +x /app/deploy/docker-entrypoint.sh && mkdir -p /app/data/logs

WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

ENTRYPOINT ["/app/deploy/docker-entrypoint.sh"]
