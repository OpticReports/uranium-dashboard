# Catalyst Options Engine — backend-only image (no frontend build: the status
# page is server-rendered HTML). Pattern-matches the genomics backend stage.
FROM python:3.11-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# SQLite + lane cache persist under ./data (Render mounts a disk at /app/data).
RUN mkdir -p data/cache

# Hosts inject $PORT; default to 8000 locally.
ENV PORT=8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
