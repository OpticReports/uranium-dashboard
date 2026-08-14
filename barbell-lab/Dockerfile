FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    BARBELL_ROOT=/app \
    BARBELL_DATA_DIR=/app/data

COPY pyproject.toml ./
COPY src ./src
COPY config ./config
# frozen edge-monitor baseline fixture (registration reads ROOT/research/...)
COPY research/fixtures/s5_backtest_daily.json ./research/fixtures/
RUN pip install --no-cache-dir .

# data/ is a mounted persistent disk on Render (sqlite + parquet + reports)
RUN mkdir -p /app/data

EXPOSE 10000
CMD ["sh", "-c", "uvicorn barbell.web.app:app --host 0.0.0.0 --port ${PORT:-10000}"]
