# Tokenized Microcap Screener — backend-only image (server-rendered status
# page, no frontend build). Pattern-matches the catalyst-options-engine stage.
FROM python:3.11-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# SQLite + lane cache persist under ./data (Render mounts a disk at /app/data).
RUN mkdir -p data/cache

ENV PORT=8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
