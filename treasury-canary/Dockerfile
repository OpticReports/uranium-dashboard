# Single-service image: build the React/TS SPA, then serve it from FastAPI (one
# origin, no CORS). Mirrors the genomics app's deploy pattern.
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
# Served at research.optic.capital/canary via the genomics-app reverse proxy:
# asset base "/canary/" (vite.config default) + API calls under "/canary".
ENV VITE_API_BASE="/canary"
RUN npm run build

FROM python:3.11-slim AS app
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY backend/pyproject.toml ./
RUN pip install --upgrade pip && pip install \
    "fastapi==0.115.5" "uvicorn[standard]==0.32.1" "pydantic==2.10.3" \
    "pydantic-settings==2.6.1" "sqlalchemy==2.0.36" "httpx==0.28.1" \
    "apscheduler==3.11.0" "python-dateutil==2.9.0.post0" \
    "numpy==2.2.6" "hmmlearn==0.3.3" "openpyxl==3.1.5"
COPY backend/ ./
COPY --from=frontend /fe/dist ./frontend_dist
ENV FRONTEND_DIST=/app/frontend_dist
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
