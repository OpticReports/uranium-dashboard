"""Attribute every BTC stop order in a historicalOrders dump to the executor's
_maintain_stop id format  f"{leg[0].upper()}-{entry_ts}-S{int(trigger)}-{stop_n}"
(app/mirror.py:4055, unchanged since the HL adapter landed, f10a61f8) by
brute force over hour-aligned entry_ts, leg T/P, int(trigger) in tpx-1..tpx+1
and stop_n 1..N. Orders that match nothing are reported as UNMATCHED (the
drill's ids are f"D-{time.time_ns()}-S" - not invertible, identified by shape).

Usage: python3 -I attribute_cloids.py <hl_history.json>
"""
import json, sys, hashlib, collections, datetime as dt

def ts(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

d = json.load(open(sys.argv[1]))
by = collections.defaultdict(list)
for e in d:
    o = e['order']
    if o['coin'] == 'BTC' and o['orderType'] == 'Stop Market':
        by[o['oid']].append(e)
orders = []
for oid, recs in by.items():
    recs.sort(key=lambda e: e['statusTimestamp'])
    o = recs[0]['order']
    orders.append(dict(oid=oid, placed=o['timestamp'], tpx=int(float(o['triggerPx'])),
                       cloid=o['cloid'], sz=o['origSz'], final=recs[-1]['status'],
                       life=(recs[-1]['statusTimestamp'] - o['timestamp']) / 1000.0))
orders.sort(key=lambda r: r['placed'])
want = {o['cloid'][2:]: o for o in orders}
NMAX = 400
found = {}
known_entry = set()          # (leg, entry_ts) already matched: try these first

def try_one(o, legs_ts):
    for leg, ets in legs_ts:
        for trig in (o['tpx'] - 1, o['tpx'], o['tpx'] + 1):
            pre = hashlib.sha256(f"{leg}-{ets}-S{trig}-".encode())
            for n in range(1, NMAX + 1):
                h = pre.copy(); h.update(str(n).encode())
                hx = h.hexdigest()[:32]
                if hx == o['cloid'][2:]:
                    return f"{leg}-{ets}-S{trig}-{n}"
    return None

for o in orders:
    s = try_one(o, sorted(known_entry))
    if s is None:
        end = o['placed'] // 1000
        start = end - 70 * 86400
        cands = [(leg, t) for t in range(end - end % 3600, start, -3600) for leg in ('T', 'P')]
        s = try_one(o, cands)
    if s:
        leg, ets = s.split('-')[0], int(s.split('-')[1])
        known_entry.add((leg, ets))
    found[o['oid']] = s
    flag = 'QUICK' if (o['final'] == 'canceled' and o['life'] < 5) else ''
    print(f"{ts(o['placed'])}  {o['final']:<19} life={o['life']:>11.3f}s tpx={o['tpx']} sz={o['sz']:<8} "
          f"{o['cloid'][:12]}..  {s or 'UNMATCHED (not a T-/P- stop id)'} {flag}", flush=True)
