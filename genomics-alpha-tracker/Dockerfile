# Single-service image: builds the React frontend, then serves it from the
# FastAPI backend (one URL, no CORS). Used by render.yaml and any single-container
# host. For local dev with hot-reload use docker-compose.yml instead.

# --- 1. Build the frontend (same-origin API: VITE_API_BASE="") ---
# VITE_BASE="/genomics/" because the SPA is served under /genomics/
# (research.optic.capital/genomics); API calls stay at the root paths.
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
ENV VITE_API_BASE=""
ENV VITE_BASE="/genomics/"
RUN npm run build

# --- 2. Backend + bundled frontend ---
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend /fe/dist ./static

# FastAPI serves the SPA from ./static and persists SQLite + cache under ./data.
ENV FRONTEND_DIST=/app/static
RUN mkdir -p data/cache

# Hosts inject $PORT; default to 8000 locally.
ENV PORT=8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
