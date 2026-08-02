FROM python:3.11-slim
WORKDIR /app
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir fastapi==0.115.5 "uvicorn[standard]==0.32.1" pydantic==2.10.3 httpx==0.28.1
COPY backend/app ./app
COPY backend/tests ./tests
ENV EWM_DATA_DIR=/data
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
