#!/usr/bin/env python3
"""Read-only health check of the live Hyperliquid book: btc-executor, carry-executor
and btc-paper-engine. Sends nothing to any venue. Used by the 6-hourly monitoring
routine; prints one block and a final ISSUES line.

    python3 btc-executor/ops/monitor.py
"""
import calendar
import json
import os
import time
import urllib.request

ADDR = "0xAb533E69e77881D89D0357166851C9653bC551e2"
INFO = "https://api.hyperliquid.xyz/info"
T1_SINCE_MS = calendar.timegm((2026, 9, 21, 0, 0, 0)) * 1000   # tripwire T1 window start
T1_LIMIT = -3750.0
HW_FLOOR = 101835.27              # high water seen by 2026-11-10 18:25Z (fallback if the state file is lost)
HW_SINCE_MS = 1794322184000       # 2026-11-10 14:49:44Z, the redeposit
CARRY_OPEN_MS = 1794322731000     # 2026-11-10 14:58:51Z, the carry re-open
KEY_WARN_DAYS = 14                # warn this long before an approved trading key expires
NEWS_KINDS = {"cap_clamp", "exposure_over_cap", "kelly_over_cap",
              "size_mult_fallback", "size_mult_invalid"}


def get(url, body=None, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(
                url, data=json.dumps(body).encode() if body else None,
                headers={"Content-Type": "application/json", "User-Agent": "monitor/1"})
            with urllib.request.urlopen(req, timeout=40) as r:
                out = json.loads(r.read())
            if out is not None:
                return out
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {str(e)[:60]}"
        else:
            last = "null body"
        time.sleep(2)
    return {"_err": last}


def info(body):
    return get(INFO, body)


# The portfolio series coarsen as they age (94-min points, then 217-min), so an
# old intraday peak can drop out of them; the high water is kept here so it
# only ratchets up. Lost on a container replacement, then HW_FLOOR applies.
STATE = os.path.expanduser("~/.cache/hl_monitor_state.json")


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def save_state(st):
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        with open(STATE, "w") as f:
            json.dump(st, f)
    except Exception as e:  # noqa: BLE001
        print(f"(state not saved: {e})")


def fills_since(start_ms):
    out, start = [], start_ms
    while True:
        page = info({"type": "userFillsByTime", "user": ADDR, "startTime": start})
        if not isinstance(page, list):
            return out, page
        out += page
        if len(page) < 2000:
            return out, None
        start = page[-1]["time"] + 1


issues = []
now = time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime())
print("monitor", now)

b = get("https://btc-executor.onrender.com/pulse")
if "_err" in b:
    issues.append(f"btc-executor /pulse unreachable ({b['_err']})")
else:
    legs = {k: (v["in_position"], v["stop_placed"], v["stop_mode"], v["engine_halted"])
            for k, v in b["legs"].items()}
    print("BTC-EXEC", {k: b.get(k) for k in ("build", "ready", "halted", "dry_run",
                                              "red_kinds_24h", "ramp_v4_met",
                                              "equity_counts_spot_tokens", "agent_days_left",
                                              "last_target_age_s")}, "legs", legs)
    if b.get("halted"):
        issues.append(f"T2 btc-executor halted {b['halted']}")
    hit = NEWS_KINDS & set(b.get("red_kinds_24h") or {})
    if hit:
        issues.append(f"T3/T5 btc red kinds {sorted(hit)}")
    if b.get("red_kinds_24h"):
        issues.append(f"btc red kinds present {b['red_kinds_24h']} (new ones are news)")
    if not b.get("equity_counts_spot_tokens"):
        issues.append("btc equity_counts_spot_tokens is not true")
    if (b.get("agent_days_left") or 99) < KEY_WARN_DAYS:
        issues.append(f"btc agent key expires in {b.get('agent_days_left')} days")

c = get("https://carry-executor.onrender.com/pulse")
if "_err" in c:
    issues.append(f"carry-executor /pulse unreachable ({c['_err']})")
else:
    print("CARRY", {k: c.get(k) for k in ("build", "dry_run", "enabled", "on", "halted",
                                           "spot_qty", "perp_qty", "hedge_gap_usd",
                                           "guard_until", "red_kinds_24h")},
          "signal", c.get("signal"))
    if c.get("halted"):
        issues.append(f"T2 carry halted {c['halted']}")
    if c.get("dry_run"):
        issues.append("C6 carry dry_run is true")
    if not c.get("on"):
        issues.append("C1 carry is not on")
    if (c.get("hedge_gap_usd") or 0) > 50:
        issues.append(f"C2 carry hedge gap ${c['hedge_gap_usd']}")
    if c.get("red_kinds_24h"):
        issues.append(f"C3 carry red kinds {c['red_kinds_24h']}")

s = get("https://btc-paper-engine.onrender.com/status")
if "_err" in s:
    issues.append(f"engine /status unreachable ({s['_err']})")
else:
    books = {}
    for name in ("S3", "S4"):
        bk = (s.get("books") or {}).get(name) or {}
        pos = bk.get("position") or {}
        books[name] = (bk.get("state"), bk.get("halted"), pos.get("entry_price"), pos.get("trail"))
        if bk.get("halted"):
            issues.append(f"engine book {name} halted")
    print("ENGINE", books, "vol_size", s.get("vol_size"),
          "degraded", s.get("degraded"), "data_halt", s.get("data_halt"))
    if (s.get("vol_size") or {}).get("basis") != "vol_target":
        issues.append(f"engine vol_size basis {(s.get('vol_size') or {}).get('basis')}")
    if s.get("degraded") or s.get("data_halt"):
        issues.append("engine degraded or data_halt")
ev = get("https://btc-paper-engine.onrender.com/events")
items = ev if isinstance(ev, list) else (ev.get("events") or [])
if isinstance(ev, dict) and "_err" in ev:
    issues.append(f"engine /events unreadable ({ev['_err']})")
# Last 24 h only: a bad event shows on up to four 6-hourly runs, then ages out.
since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 86400))
bad = [(e.get("ts"), e.get("event")) for e in items
       if e.get("event") in ("bar_gap", "bar_stuck", "degraded")
       and str(e.get("ts", "")) >= since]
if bad:
    issues.append(f"engine events in the last 24h {bad[:3]}")
fd = get("https://btc-paper-engine.onrender.com/funding")
gate = ((fd.get("venues") or {}).get("HL_ETH") or {}) if isinstance(fd, dict) else {}
print("GATE HL_ETH", {k: gate.get(k) for k in ("armed", "mean_ann_pct", "coverage")})

mids = info({"type": "allMids"})
eth_mid = float(mids.get("ETH", 0) or 0)
ueth_mid = float(mids.get("@151", 0) or 0)
cs = info({"type": "clearinghouseState", "user": ADDR})
pos = {r["position"]["coin"]: r["position"] for r in (cs.get("assetPositions") or [])}
btc = float((pos.get("BTC") or {}).get("szi") or 0)
eth = pos.get("ETH") or {}
eth_szi = float(eth.get("szi") or 0)
print("VENUE BTC", btc, "entry", (pos.get("BTC") or {}).get("entryPx"),
      "| ETH", eth_szi, "entry", eth.get("entryPx"), "liq", eth.get("liquidationPx"),
      "| mids BTC", mids.get("BTC"), "ETH", eth_mid, "@151", ueth_mid)
oo = info({"type": "frontendOpenOrders", "user": ADDR})
btc_stops = [o for o in (oo if isinstance(oo, list) else [])
             if o.get("coin") == "BTC" and o.get("isTrigger")]
print("BTC STOPS", [(o["side"], o["sz"], o.get("triggerPx"), o.get("reduceOnly")) for o in btc_stops])
stop_sum = sum(float(o["sz"]) for o in btc_stops if o.get("reduceOnly"))
if abs(stop_sum - abs(btc)) > 1e-6:
    issues.append(f"BTC stop sizes {stop_sum} != |BTC net| {abs(btc)} (news outside a fresh fill's unbooked window)")
if b.get("legs") and btc != 0 and not any(v[0] for v in legs.values()):
    issues.append(f"venue holds {btc} BTC but no leg is booked")

sp = info({"type": "spotClearinghouseState", "user": ADDR})
bal = {x["coin"]: float(x["total"]) for x in (sp.get("balances") or [])}
print("SPOT USDC", bal.get("USDC"), "UETH", bal.get("UETH"))
if eth_szi and eth_mid:
    gap = abs(bal.get("UETH", 0) - abs(eth_szi)) * eth_mid
    print(f"C2 hedge gap ${gap:.2f} | C5 depeg {ueth_mid / eth_mid - 1:+.5f}")
    if gap > 50:
        issues.append(f"C2 venue hedge gap ${gap:.2f}")
    if abs(ueth_mid / eth_mid - 1) > 0.01:
        issues.append(f"C5 UETH depeg {ueth_mid / eth_mid - 1:+.4f}")
    liq = float(eth.get("liquidationPx") or 0)
    if liq and eth_mid >= 0.6 * liq:
        issues.append(f"C4 ETH {eth_mid} within 40% of liquidation {liq}")
    print(f"C4 liq/mid {liq / eth_mid:.2f}" if liq else "C4 liq n/a")

pf = info({"type": "portfolio", "user": ADDR})
series = dict(pf) if isinstance(pf, list) else {}
day = (series.get("day") or {}).get("accountValueHistory") or []
equity = float(day[-1][1]) if day else float("nan")
pts = [float(v) for k in ("day", "week", "month", "allTime")
       for t, v in ((series.get(k) or {}).get("accountValueHistory") or []) if t >= HW_SINCE_MS]
st = load_state()
hw = max([HW_FLOOR, float(st.get("hw", 0))] + pts)
st["hw"] = hw
save_state(st)
if equity != equity:
    issues.append(f"portfolio equity unreadable ({pf.get('_err') if isinstance(pf, dict) else 'empty day series'})")
print(f"T4 equity {equity:,.2f} | HW {hw:,.2f} | trip {0.9 * hw:,.2f}")
if equity <= 0.9 * hw:
    issues.append(f"T4 equity {equity:,.2f} <= trip {0.9 * hw:,.2f}")

fl, err = fills_since(T1_SINCE_MS)
btc_f = [f for f in fl if f["coin"] == "BTC"]
t1 = sum(float(f["closedPnl"]) - float(f["fee"]) for f in btc_f)
new = [f for f in btc_f if f["time"] >= HW_SINCE_MS]
print(f"T1 BTC realized net since 2026-09-21 {t1:+,.2f} over {len(btc_f)} fills; since the restart: "
      f"{[(time.strftime('%m-%d %H:%M', time.gmtime(f['time'] / 1000)), f['dir'], f['sz'], f['px']) for f in new][-4:]}"
      + (f" (fills read failed: {err})" if err else ""))
if t1 <= T1_LIMIT:
    issues.append(f"T1 BTC realized {t1:,.2f} <= {T1_LIMIT:,.0f}")
fu = info({"type": "userFunding", "user": ADDR, "startTime": CARRY_OPEN_MS})
fund = sum(float(x["delta"]["usdc"]) for x in (fu if isinstance(fu, list) else [])
           if x.get("delta", {}).get("coin") == "ETH")
print(f"ETH funding since the 2026-11-10 carry open ${fund:,.2f}")

# Every approved agent key on the account (btc-executor's and carry-executor's are
# separate). Carry's /pulse does not report its expiry, so read it from the venue.
ag = info({"type": "extraAgents", "user": ADDR})
if isinstance(ag, list):
    now_ms = time.time() * 1000
    keys = [(a.get("name"), a.get("address", ""), ((a.get("validUntil") or 0) - now_ms) / 86400000)
            for a in ag]
    print("KEYS", [(n, f"{ad[:6]}..{ad[-4:]}", f"{d:.0f}d") for n, ad, d in keys])
    if not keys:
        issues.append("no approved agent key on the account: neither executor can trade")
    for n, ad, d in keys:
        if d < KEY_WARN_DAYS:
            issues.append(f"agent key {n} ({ad[:6]}..{ad[-4:]}) expires in {d:.1f} days")
else:
    issues.append(f"agent key list unreadable ({ag.get('_err') if isinstance(ag, dict) else ag})")

print("ISSUES:", "; ".join(issues) if issues else "none")
