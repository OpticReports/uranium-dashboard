"""Infer what live HG actually held on days its return does not match the model.

Why: the account view de-levers the LIVE return using the model's holdings.  On days where live
held something else (Composer decides at ~15:50 ET on 15:50 prices; the model decides on the
close, so a condition near its threshold can flip either way), the model's leverage contribution
is the wrong one to subtract.  HG holds a single asset almost every day, so the live holding can
be identified from the live return.

Rule per return day d1 (decision d0 = prior session), HG only; tolerances are relative on big days
(max(25 bp, 6% of the model's move), counter-agent 2026-10-16):
  - deposit / withdrawal day (raw-series flow > $100): keep the model holding ('flow'; the day's
    deposit-adjusted return mixes the deposit's intraday fill in, so it cannot identify the holding);
  - |live - model| within tolerance: model holding confirmed ('model');
  - else the model holdings decided one session EARLIER ('lag') or LATER ('lead'): accepted within
    2x tolerance and at most half the model's error;
  - else any single leaf of HG's trees: accepted if it fits within 10 bp AND the runner-up is at least
    25 bp away ('leaf', unambiguous); otherwise 'open': keep the model holding and record the
    best-fitting leaf (best_hold) so the study can show the range it spans.
KMLM / SLEEVE / HARV hold multi-asset mixes; they keep the model holdings.  Output: LEV_DATA/hg_inferred.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lev_study as S   # noqa: E402

TOL_MIN, TOL_REL, TOL_LEAF, TOL_GAP = 0.0025, 0.06, 0.0010, 0.0025


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

    VT = json.load(open(f'{S.D}/version_trees.json'))
    leaves = sorted({t for v in VT['HG'] for t in v['leaves']})
    rows, counts = {}, {}
    for d1 in S.YTD:
        i = S.DAYS.index(d1)
        d0, dm1 = S.DAYS[i - 1], S.DAYS[i - 2]
        if d0 not in da or d1 not in da:
            continue
        rl = da[d1] / da[d0] - 1
        flow = raw[d1] - raw[d0] * (1 + rl)
        hm = hold(d0)
        pm = port(hm, d1)
        em = abs(rl - pm)
        tol = max(TOL_MIN, TOL_REL * abs(pm))
        fits = sorted(((abs(rl - S.R(t)[d1]), t) for t in leaves if d1 in S.R(t)), key=lambda x: x[0])
        best_hold = {fits[0][1]: 1.0} if fits else None
        cls, hi = 'model', hm
        if abs(flow) > 100:
            cls = 'flow'
        elif em > tol:
            cands = {'lag': hold(dm1)}
            if d1 in B[S.version_for('HG', d1)]['holdings']:
                cands['lead'] = hold(d1)
            best = min(cands, key=lambda k: abs(rl - port(cands[k], d1)))
            eb = abs(rl - port(cands[best], d1))
            alt_ok = eb <= 2 * tol and eb <= em / 2 and cands[best] != hm
            leaf_ok = bool(fits) and fits[0][0] <= TOL_LEAF and (len(fits) < 2 or fits[1][0] - fits[0][0] >= TOL_GAP)
            if leaf_ok and (not alt_ok or fits[0][0] < eb):
                cls, hi = 'leaf', best_hold
            elif alt_ok:
                cls, hi = best, cands[best]
            else:
                cls = 'open'
        counts[cls] = counts.get(cls, 0) + 1
        rows[d1] = {'class': cls, 'live': round(rl, 5), 'model_hold': hm, 'model_ret': round(pm, 5),
                    'inferred_hold': hi, 'inferred_ret': round(port(hi, d1), 5),
                    'c_model': round(contrib(hm, d1), 5), 'c_inferred': round(contrib(hi, d1), 5),
                    'best_hold': best_hold, 'best_err': round(fits[0][0], 5) if fits else None,
                    'runner_up_err': round(fits[1][0], 5) if len(fits) > 1 else None, 'tol': round(tol, 5)}
    json.dump({'counts': counts, 'rows': rows}, open(f'{S.D}/hg_inferred.json', 'w'), indent=1)
    print('HG live-holding classes over YTD:', counts)
    for d1, r in rows.items():
        if r['class'] in ('lag', 'lead', 'leaf', 'open'):
            print(f"  {d1} {r['class']:4s} live {r['live']:+.2%} | model {r['model_hold']} {r['model_ret']:+.2%} c {r['c_model']:+.2%}"
                  f" | used {r['inferred_hold']} c {r['c_inferred']:+.2%} | best leaf {r['best_hold']} err {r['best_err']:.2%} next {r['runner_up_err']:.2%}")


if __name__ == '__main__':
    main()
