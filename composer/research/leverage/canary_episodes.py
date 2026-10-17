"""Episode accounting for the canary add-ons that beat the 200d gate (counter-agent F1): for each
contiguous stretch where 'signal & 200d' differs from the 200d alone, the log-wealth gain vs the 200d,
plus the running lead.  Output appended to LEVGATE_DATA/canary_gates.json under 'episodes'."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levgate as lg        # noqa: E402
import canary_gates as cg   # noqa: E402


def main():
    P, P1, runs = lg.engine_runs('B')
    days, h = runs['HG']
    F = cg.build(P, days)
    G = lg.leg_sets('HG', sorted({t for d in h for t in h[d] if t in lg.LEG}))['trend']
    run = lambda lam: lg.gate_run(days, h, P, P1, lam, G, lg.COST['HG'])[0]   # noqa: E731
    t200 = F['T200 SPY>200d (reference)']
    r200 = run(t200)
    out = {}
    for key in ('CAPE<35', 'CAPE<30', 'MX25 margin excess growth<25pp (canary cell)', 'EMA100 SPY>EMA100'):
        lam = {d: min(F[key].get(d, 1.0), t200.get(d, 1.0)) for d in days}
        r = run(lam)
        eps, cur, lead, peak_lead = [], None, 0.0, (0.0, None)
        for i, d in enumerate(days[1:], 1):
            g = math.log(1 + r[d]) - math.log(1 + r200[d])
            lead += g
            if lead > peak_lead[0]:
                peak_lead = (lead, d)
            differs = lam.get(days[i - 1], 1.0) != t200.get(days[i - 1], 1.0)
            if differs:
                if cur is None:
                    cur = {'from': d, 'to': d, 'gain': 0.0, 'sessions': 0}
                cur['to'] = d
                cur['sessions'] += 1
                cur['gain'] += g
            elif cur is not None:
                cur['gain'] += g          # the switch-back day carries the re-entry trade
                eps.append(cur)
                cur = None
        if cur:
            eps.append(cur)
        # merge stretches separated by < 63 sessions into episodes
        merged = []
        for e in eps:
            if merged and days.index(e['from']) - days.index(merged[-1]['to']) < 63:
                m = merged[-1]
                m['to'], m['sessions'], m['gain'] = e['to'], m['sessions'] + e['sessions'], m['gain'] + e['gain']
            else:
                merged.append(dict(e))
        out[key] = {'episodes': [{**e, 'gain': round(e['gain'], 3)} for e in merged], 'total_log_gain': round(lead, 3),
                    'peak_lead': [round(peak_lead[0], 3), peak_lead[1]]}
        print(f"\n{key}: total log gain vs 200d {lead:+.3f} (peak {peak_lead[0]:+.3f} on {peak_lead[1]})")
        for e in merged:
            print(f"   {e['from']} .. {e['to']}  {e['sessions']:4d} sessions de-levered vs 200d  gain {e['gain']:+.3f} ({math.exp(e['gain']) - 1:+.1%})")
    J = json.load(open(os.path.join(lg.OUT, 'canary_gates.json')))
    J['episodes'] = out
    json.dump(J, open(os.path.join(lg.OUT, 'canary_gates.json'), 'w'))


if __name__ == '__main__':
    main()
