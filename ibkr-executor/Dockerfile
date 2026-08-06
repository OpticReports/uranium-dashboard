# IB Gateway (gnzsnz image: gateway + IBC auto-login, reads TWS_USERID /
# TWS_PASSWORD / TRADING_MODE) with the executor's FastAPI loop alongside.
# OFFLINE mode (no credentials) skips the gateway entirely and boots green.
FROM ghcr.io/gnzsnz/ib-gateway:stable

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/executor
COPY requirements.txt .
RUN python3 -m venv venv && ./venv/bin/pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY start.sh .
RUN chmod +x start.sh

ENV PORT=8000
CMD ["/opt/executor/start.sh"]
