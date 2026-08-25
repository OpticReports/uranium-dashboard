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

RESTART_LOG="${IBGW_RESTART_LOG:-/app/data/gateway_restarts.jsonl}"
BACKOFF_MIN_S="${IBGW_BACKOFF_MIN_S:-5}"
BACKOFF_MAX_S="${IBGW_BACKOFF_MAX_S:-300}"
# a gateway that stayed up this long counts as healthy -> reset the backoff
HEALTHY_S="${IBGW_HEALTHY_S:-300}"
# consecutive short-lived starts before the breaker opens. A permanently
# unstartable gateway (bad credentials) would otherwise attempt ~250-290
# IBKR LOGINS PER DAY forever: IBKR locks accounts on repeated failures and
# each LIVE attempt can fire a 2FA push, so unbounded retry could turn a
# 30-minute outage into a locked brokerage account (counter-agent 2026-08-24).
MAX_CONSEC_FAIL="${IBGW_MAX_CONSEC_FAIL:-8}"
LOG_MAX_LINES="${IBGW_LOG_MAX_LINES:-2000}"

# Validate BEFORE use: a non-numeric value tripped `set -u` inside the
# arithmetic and killed the supervisor silently (supervision off, /health
# still 200); a negative one made `delay` diverge negative, giving ~63
# gateway launches per SECOND - a JVM fork bomb on a trading container.
for _v in BACKOFF_MIN_S BACKOFF_MAX_S HEALTHY_S MAX_CONSEC_FAIL LOG_MAX_LINES; do
  _val="${!_v}"
  case "$_val" in
    ''|*[!0-9]*) echo "FATAL: IBGW_${_v}='$_val' is not a positive integer" >&2
                 exit 1;;
  esac
  if [ "$_val" -lt 1 ]; then
    echo "FATAL: IBGW_${_v} must be >= 1 (got $_val)" >&2; exit 1
  fi
done
if [ "$BACKOFF_MAX_S" -lt "$BACKOFF_MIN_S" ]; then
  echo "FATAL: IBGW_BACKOFF_MAX_S < IBGW_BACKOFF_MIN_S" >&2; exit 1
fi

log_restart() {   # $1=reason $2=exit_code $3=uptime_s $4=next_delay_s
  mkdir -p "$(dirname "$RESTART_LOG")" 2>/dev/null || return 0
  printf '{"ts":%s,"reason":"%s","exit_code":%s,"uptime_s":%s,"next_delay_s":%s}\n' \
    "$(date +%s)" "$1" "$2" "$3" "$4" >> "$RESTART_LOG" 2>/dev/null || true
  # rotate: unbounded growth put ~10 MB/yr on a 1 GB disk and made every
  # /health probe read the whole file
  local n
  n=$(wc -l < "$RESTART_LOG" 2>/dev/null || echo 0)
  if [ "${n:-0}" -gt "$(( LOG_MAX_LINES * 2 ))" ]; then
    tail -n "$LOG_MAX_LINES" "$RESTART_LOG" > "${RESTART_LOG}.tmp" 2>/dev/null \
      && mv "${RESTART_LOG}.tmp" "$RESTART_LOG" 2>/dev/null || true
  fi
}

cleanup_gateway_leftovers() {
  # The gnzsnz run.sh cleans up (stop_ibc kills IBC/Xvfb/x11vnc/socat) ONLY
  # on SIGINT/SIGTERM, which the supervisor never sends - a non-signal exit
  # leaves those helpers alive. Each restart then stacked a fresh X server,
  # VNC and socat on top of the survivors, on a 2GB instance shared with the
  # JVM (counter-agent 2026-08-24, residual). Kill the stack and free the
  # display lock so every start is from a clean slate. Best-effort: pkill
  # may be absent or matches may be gone; never abort the restart over it.
  pkill -f 'ibcstart' 2>/dev/null || true
  pkill -f 'ibgateway'  2>/dev/null || true
  pkill Xvfb   2>/dev/null || true
  pkill x11vnc 2>/dev/null || true
  pkill socat  2>/dev/null || true
  rm -f /tmp/.X1-lock 2>/dev/null || true
  sleep 1
}

supervise_gateway() {
  local gw="$1" delay="$BACKOFF_MIN_S" consec=0 first=1
  while :; do
    local started ec uptime
    if [ "$first" -eq 1 ]; then
      first=0
    elif declare -F cleanup_gateway_leftovers >/dev/null; then
      # declare-guard: the test harness extracts supervise_gateway alone,
      # and a bare call there would be command-not-found noise (and pkill
      # in a test environment must never run)
      cleanup_gateway_leftovers
    fi
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
      consec=0
    else
      consec=$(( consec + 1 ))
    fi
    if [ "$consec" -ge "$MAX_CONSEC_FAIL" ]; then
      echo "FATAL: IB gateway failed $consec consecutive times without staying"\
           "up ${HEALTHY_S}s — circuit breaker OPEN, not restarting again."\
           "This is almost always credentials or config; retrying would keep"\
           "hammering IBKR logins." >&2
      log_restart "circuit_open" "$ec" "$uptime" 0
      return 1
    fi
    echo "WARN: IB gateway exited (code $ec) after ${uptime}s — restarting in ${delay}s"
    log_restart "exited" "$ec" "$uptime" "$delay"
    sleep "$delay"
    delay=$(( delay * 2 ))
    [ "$delay" -gt "$BACKOFF_MAX_S" ] && delay="$BACKOFF_MAX_S"
    [ "$delay" -lt "$BACKOFF_MIN_S" ] && delay="$BACKOFF_MIN_S"
  done
}

if [ -n "${TWS_USERID:-}" ] && [ -n "${TWS_PASSWORD:-}" ]; then
  GW="${IBGW_ENTRYPOINT:-/home/ibgateway/scripts/run.sh}"
  if [ -x "$GW" ]; then
    echo "starting IB gateway (${TRADING_MODE:-paper}) under supervision"
    supervise_gateway "$GW" &
    GW_SUP_PID=$!
    # NOTE (counter-agent 2026-08-24): no trap here. `exec` below replaces
    # this shell and DISCARDS every trap, so a TERM handler installed here
    # would be dead code - and a test that greps for it would pass while it
    # is provably inert. Docker signals PID 1 only, so on a normal stop the
    # container dies with uvicorn and the supervisor goes with it. The
    # 143/130 exit-code guard inside the loop still covers the case where
    # the gateway itself is signalled directly.
  else
    echo "WARN: gateway entrypoint $GW missing; continuing without gateway"
  fi
else
  echo "no TWS credentials -> OFFLINE mode, gateway not started"
fi

exec ./venv/bin/uvicorn app.service:app --host 0.0.0.0 --port "${PORT:-8000}"
