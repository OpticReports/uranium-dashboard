"""Infer what live HG actually held on days its return does not match the model.

Why: the account view de-levers the LIVE return using the model's holdings.  On days where live
held something else (Composer decides at ~15:50 ET on 15:50 prices; the model decides on the
close, so a condition near its threshold can flip either way), the model's leverage contribution
is the wrong one to subtract.  HG holds a single asset almost every day, so the live holding can
be identified from the live return.

Rule per return day d1 (decision d0 = prior session), HG only:
  - deposit / withdrawal day (raw-series flow > $100): keep the model holding (flagged 'flow');
  - |live - model| <= 0.25%: model holding confirmed ('model');
  - else the candidates are the model holding decided one session EARLIER (live did not switch:
    'lag') and one session LATER (live switched a session early: 'lead'); take the best if it is
    within 0.50% of live AND at most half the model's error;
  - otherwise unresolved ('open'): keep the model holding, and report the swing in the leverage
    contribution if live had instead held an unlevered asset (bound used for the range).
KMLM / SLEEVE / HARV hold multi-asset mixes and track their models at 0.97-0.99 daily
correlation; they keep the model holdings.  Output: LEV_DATA/hg_inferred.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lev_study as S   # noqa: E402

TOL_MATCH, TOL_ALT = 0.0025, 0.0050


def main():
    B = json.load(open(f'{S.D}/backtests.json'))
    live = json.load(open(f'{S.D}/live_symphonies.json'))
    p = live['HG']
    dates = [S.epoch_ms_to_iso(ms) for ms in p['epoch_ms']]
    da = dict(zip(dates, p['deposit_adjusted_series']))
    raw = dict(zip(dates, p['series']))

    def hold(d):
        return B[S.version_for('HG', d)]['holdings'][d]

    def port(h, d1):
        return sum(w * S.R(t)[d1] for t, w in h.items())

    def contrib(h, d1):
        return sum(w * (S.R(t)[d1] - S.r1x(t, d1, 'real')) for t, w in h.items())

    rows, counts = {}, {}
    for d1 in S.YTD:
        i = S.DAYS.index(d1)
        d0, dm1 = S.DAYS[i - 1], S.DAYS[i - 2]
        if d0 not in da or d1 not in da:
            continue
        rl = da[d1] / da[d0] - 1
        flow = raw[d1] - raw[d0] * (1 + rl)
        hm = hold(d0)
        em = abs(rl - port(hm, d1))
        cls, hi = 'model', hm
        if abs(flow) > 100:
            cls = 'flow'
        elif em > TOL_MATCH:
            cands = {'lag': hold(dm1)}
            if d1 <= S.YTD1 and d1 in B[S.version_for('HG', d1)]['holdings']:
                cands['lead'] = hold(d1)
            best = min(cands, key=lambda k: abs(rl - port(cands[k], d1)))
            eb = abs(rl - port(cands[best], d1))
            if eb <= TOL_ALT and eb <= em / 2 and cands[best] != hm:
                cls, hi = best, cands[best]
            else:
                cls = 'open'
        counts[cls] = counts.get(cls, 0) + 1
        rows[d1] = {'class': cls, 'live': round(rl, 5), 'model_hold': hm, 'model_ret': round(port(hm, d1), 5),
                    'inferred_hold': hi, 'inferred_ret': round(port(hi, d1), 5),
                    'c_model': round(contrib(hm, d1), 5), 'c_inferred': round(contrib(hi, d1), 5),
                    # open days: swing if live had held an unlevered asset instead (c = 0)
                    'c_if_unlevered': 0.0}
    json.dump({'counts': counts, 'rows': rows}, open(f'{S.D}/hg_inferred.json', 'w'), indent=1)
    print('HG live-holding classes over YTD:', counts)
    for d1, r in rows.items():
        if r['class'] in ('lag', 'lead', 'open'):
            print(f"  {d1} {r['class']:4s} live {r['live']:+.2%} | model {r['model_hold']} {r['model_ret']:+.2%} c {r['c_model']:+.2%}"
                  f" | inferred {r['inferred_hold']} {r['inferred_ret']:+.2%} c {r['c_inferred']:+.2%}")


if __name__ == '__main__':
    main()
