"""Paired block bootstrap of Sharpe/Sortino(actual) - Sharpe/Sortino(no leverage) on the account's
198 YTD sessions (10-day blocks, 4,000 resamples, seed 7).  Both series are resampled on the SAME
days, so the interval is for the gap, not for either level."""
import json, math, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lev_study as S


def sh(x, f):
    ex = [a - b for a, b in zip(x, f)]; n = len(ex); mu = sum(ex) / n
    sd = math.sqrt(sum((e - mu) ** 2 for e in ex) / (n - 1)); dn = math.sqrt(sum(min(e, 0) ** 2 for e in ex) / n)
    return mu / sd * math.sqrt(252), mu / dn * math.sqrt(252)


def main():
    J = json.load(open(f'{S.D}/lev_study.json'))
    ds = J['series']['dates']
    ca = J['series']['acct_actual']; cu = J['series']['acct_unlev']
    ra = [ca[0] - 1] + [ca[i] / ca[i - 1] - 1 for i in range(1, len(ca))]
    ru = [cu[0] - 1] + [cu[i] / cu[i - 1] - 1 for i in range(1, len(cu))]
    rf = [S.RF[d] for d in ds]
    n, B, L = len(ds), 4000, 10
    rng = random.Random(7)
    d_sh, d_so, s_a, s_u = [], [], [], []
    for _ in range(B):
        idx = []
        while len(idx) < n:
            s0 = rng.randrange(0, n - L + 1); idx.extend(range(s0, s0 + L))
        idx = idx[:n]
        a = sh([ra[i] for i in idx], [rf[i] for i in idx]); u = sh([ru[i] for i in idx], [rf[i] for i in idx])
        d_sh.append(a[0] - u[0]); d_so.append(a[1] - u[1]); s_a.append(a[0]); s_u.append(u[0])
    q = lambda v, p: sorted(v)[int(p * (len(v) - 1))]
    pa, pu = sh(ra, rf), sh(ru, rf)
    out = {'sharpe_actual': round(pa[0], 3), 'sharpe_unlev': round(pu[0], 3),
           'sharpe_gap': round(pa[0] - pu[0], 3), 'sharpe_gap_ci90': [round(q(d_sh, .05), 3), round(q(d_sh, .95), 3)],
           'p_sharpe_gap_gt0': round(sum(1 for x in d_sh if x > 0) / B, 3),
           'sortino_gap': round(pa[1] - pu[1], 3), 'sortino_gap_ci90': [round(q(d_so, .05), 3), round(q(d_so, .95), 3)],
           'p_sortino_gap_gt0': round(sum(1 for x in d_so if x > 0) / B, 3),
           'sharpe_actual_ci90': [round(q(s_a, .05), 2), round(q(s_a, .95), 2)], 'sharpe_unlev_ci90': [round(q(s_u, .05), 2), round(q(s_u, .95), 2)]}
    json.dump(out, open(f'{S.D}/sharpe_boot.json', 'w'), indent=1)
    print(out)


if __name__ == '__main__':
    main()
