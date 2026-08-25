#!/usr/bin/env bash
# ibkr-executor entrypoint. Gateway only starts when credentials exist;
# the service itself always comes up (OFFLINE mode without creds).
#
# The gateway is SUPERVISED. It used to be started as `"$GW" &` and never
# looked at again: uvicorn is PID 1, so a gateway that crashed, was
# OOM-killed, or gave up after a failed login stayed dead until a human
# redeployed — while /health kept answering 200 (it reports the API, not the
# gateway) so Render never restarted the container either. The executor's
# reconnect-with-backoff then retried forever against a process that no
# longer existed. That is the difference between a 3-minute daily restart and
# the 30+ minute outage on 2026-08-24.
set -u
cd /opt/executor

RESTART_LOG="${IBGW_RESTART_LOG:-/opt/executor/data/gateway_restarts.jsonl}"
BACKOFF_MIN_S="${IBGW_BACKOFF_MIN_S:-5}"
BACKOFF_MAX_S="${IBGW_BACKOFF_MAX_S:-300}"
# a gateway that stayed up this long counts as healthy -> reset the backoff
HEALTHY_S="${IBGW_HEALTHY_S:-300}"

log_restart() {   # $1=reason $2=exit_code $3=uptime_s $4=next_delay_s
  mkdir -p "$(dirname "$RESTART_LOG")" 2>/dev/null || return 0
  printf '{"ts":%s,"reason":"%s","exit_code":%s,"uptime_s":%s,"next_delay_s":%s}\n' \
    "$(date +%s)" "$1" "$2" "$3" "$4" >> "$RESTART_LOG" 2>/dev/null || true
}

supervise_gateway() {
  local gw="$1" delay="$BACKOFF_MIN_S"
  while :; do
    local started ec uptime
    started=$(date +%s)
    "$gw"
    ec=$?
    uptime=$(( $(date +%s) - started ))
    # SIGTERM/SIGINT during container shutdown: exit, do not resurrect
    if [ "$ec" -eq 143 ] || [ "$ec" -eq 130 ]; then
      echo "gateway exited on signal ($ec) — not restarting (shutdown)"
      return 0
    fi
    if [ "$uptime" -ge "$HEALTHY_S" ]; then
      delay="$BACKOFF_MIN_S"      # it had been running fine; treat as fresh
    fi
    echo "WARN: IB gateway exited (code $ec) after ${uptime}s — restarting in ${delay}s"
    log_restart "exited" "$ec" "$uptime" "$delay"
    sleep "$delay"
    delay=$(( delay * 2 ))
    [ "$delay" -gt "$BACKOFF_MAX_S" ] && delay="$BACKOFF_MAX_S"
  done
}

if [ -n "${TWS_USERID:-}" ] && [ -n "${TWS_PASSWORD:-}" ]; then
  GW="${IBGW_ENTRYPOINT:-/home/ibgateway/scripts/run.sh}"
  if [ -x "$GW" ]; then
    echo "starting IB gateway (${TRADING_MODE:-paper}) under supervision"
    supervise_gateway "$GW" &
    GW_SUP_PID=$!
    # stop supervising before the container dies, so shutdown does not race
    # a restart (the loop would otherwise resurrect the gateway mid-teardown)
    trap 'kill "$GW_SUP_PID" 2>/dev/null || true' TERM INT
  else
    echo "WARN: gateway entrypoint $GW missing; continuing without gateway"
  fi
else
  echo "no TWS credentials -> OFFLINE mode, gateway not started"
fi

exec ./venv/bin/uvicorn app.service:app --host 0.0.0.0 --port "${PORT:-8000}"
