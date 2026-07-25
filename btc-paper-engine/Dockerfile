# Single-service image: build the React SPA, then serve it from FastAPI.
# Mirrors the canary's deploy pattern (one origin, no CORS).
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
# Served at research.optic.capital/btc via the genomics reverse proxy.
ENV VITE_API_BASE="/btc"
RUN npm run build

FROM python:3.11-slim AS app
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY backend/pyproject.toml ./
RUN pip install --upgrade pip && pip install \
    "fastapi==0.115.5" "uvicorn[standard]==0.32.1" "pydantic==2.10.3" \
    "pydantic-settings==2.6.1" "sqlalchemy==2.0.36" "httpx==0.28.1" \
    "pyyaml==6.0.2"
COPY backend/ ./
COPY --from=frontend /fe/dist ./frontend_dist
ENV FRONTEND_DIST=/app/frontend_dist
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
