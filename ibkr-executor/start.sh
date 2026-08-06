#!/usr/bin/env bash
# ibkr-executor entrypoint. Gateway only starts when credentials exist;
# the service itself always comes up (OFFLINE mode without creds).
set -u
cd /opt/executor

if [ -n "${TWS_USERID:-}" ] && [ -n "${TWS_PASSWORD:-}" ]; then
  GW="${IBGW_ENTRYPOINT:-/home/ibgateway/scripts/run.sh}"
  if [ -x "$GW" ]; then
    echo "starting IB gateway (${TRADING_MODE:-paper})"
    "$GW" &
  else
    echo "WARN: gateway entrypoint $GW missing; continuing without gateway"
  fi
else
  echo "no TWS credentials -> OFFLINE mode, gateway not started"
fi

exec ./venv/bin/uvicorn app.service:app --host 0.0.0.0 --port "${PORT:-8000}"
