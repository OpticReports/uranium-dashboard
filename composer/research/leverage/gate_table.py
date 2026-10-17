"""Comparison table for the proposed HG 200-day leverage gate (add. 42 candidate), from the ratified gate-lab
output (LEVGATE_DATA/levgate.json) plus operational stats (time below the 200d, switches per year, live era,
2026 YTD).  Writes results/hg-200d-gate-comparison-2026-10-17.md and prints it."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levgate as lg   # noqa: E402

V = [('As built (trend baskets always 3x)', 'A0 always levered (as built)', 'as built'),
     ('200d gate, trend baskets to 1x below', 'T200 SPY>200d [trend only]', 'T200 SPY>200d [trend only] -> HG only'),
     ('200d gate, trend baskets to half 1x / half cash', 'T200 SPY>200d -> half 1x half cash [trend only]', 'T200 SPY>200d -> half 1x half cash [trend only] -> HG only'),
     ('200d gate, trend baskets to cash (add. 40 B1)', 'T200 SPY>200d -> cash [trend only]', 'T200 SPY>200d -> cash [trend only] -> HG only'),
     ('200d gate on every leveraged long, 1x below', 'T200 SPY>200d', 'T200 SPY>200d -> HG only'),
     ('Trend baskets always 1x (reference)', 'A1 never levered [trend only]', 'A1 never levered [trend only] -> HG only')]


def pct(x, sign=True):
    return '' if x is None else (f'{x * 100:+.1f}%' if sign else f'{x * 100:.1f}%')


def switches(P, days):
    spy, ma = P['SPY'], lg.ma_series(P['SPY'], 200)
    st = [spy[d] > ma[d] for d in days if d in ma]
    flips = sum(1 for a, b in zip(st, st[1:]) if a != b)
    below = sum(1 for s in st if not s) / len(st)
    return flips / (len(st) / 252), below, (spy[days[-1]] / ma[days[-1]] - 1)


def main():
    J = json.load(open(os.path.join(lg.OUT, 'levgate.json')))
    B, A = J['panels']['B']['HG'], J['panels']['A']['HG']
    book = J['book_A']['rows']
    lines = ['# HG 200-day leverage gate: comparison (2026-10-17)', '',
             'Same signals and trades; below the SPY 200-day average the five trend baskets (TQQQ, UPRO, UDOW, SSO, TNA) '
             'are held at 1x, half 1x / half cash, or cash. Dip-buys stay at 3x. Costed at HG\'s measured slippage including '
             'the switches. Source: levgate.json (add. 42, counter-agent reviewed).', '']
    lines += ['## 1990-2026 (proxy panel, out of sample for HG\'s rules)', '',
              '| Variant | CAGR | Sharpe | Sortino | Max DD | Worst year | Sharpe gap vs as built (90%) | P(beats as built) |',
              '|---|---|---|---|---|---|---|---|']
    for lab, k, _ in V:
        r = B['rows'][k]
        m = r['full']
        n = r.get('nulls')
        gap = f"{n['sharpe_gap_ci90'][0]:+.2f} to {n['sharpe_gap_ci90'][1]:+.2f}" if n else ''
        lines.append(f"| {lab} | {pct(m['cagr'])} | {m['sharpe']:.2f} | {m['sortino']:.2f} | {pct(m['maxdd'], False)} | {pct(m['worst_year'])} | {gap} | {n['p_gap_gt0']:.2f} |" if n else
                     f"| {lab} | {pct(m['cagr'])} | {m['sharpe']:.2f} | {m['sortino']:.2f} | {pct(m['maxdd'], False)} | {pct(m['worst_year'])} | | |")
    W = ['2000-02 bear', '2007-09 bear', '2009-19', '2020-26']
    lines += ['', '## By regime, 1990-2026 panel (CAGR per year / max DD in the window)', '',
              '| Variant | ' + ' | '.join(W) + ' |', '|---|' + '---|' * len(W)]
    for lab, k, _ in V:
        w = B['rows'][k]['windows']
        lines.append(f'| {lab} | ' + ' | '.join(f"{pct(w[x]['cagr'])} / {pct(w[x]['maxdd'], False)}" for x in W) + ' |')
    lines += ['', '## 2015-2026 real tickers (in sample), live era and 2026 YTD', '',
              '| Variant | CAGR 2015-26 | Sharpe | Max DD | Live era 2023-04 on: CAGR / Sharpe / DD | 2026 YTD (to 10-07) |',
              '|---|---|---|---|---|---|']
    for lab, k, _ in V:
        m = A['rows'][k]['full']
        s = A['series_keep'].get(k)
        live = ytd = ''
        if s:
            ds = sorted(s)
            le = lg.gs.metrics(s, ['x'] + ds, '2023-04-19')
            yt = lg.gs.metrics(s, ['x'] + ds, '2026-01-02')
            live = f"{pct(le['cagr'])} / {le['sharpe']:.2f} / {pct(le['maxdd'], False)}"
            ytd = pct(yt['cum'] - 1)
        lines.append(f"| {lab} | {pct(m['cagr'])} | {m['sharpe']:.2f} | {pct(m['maxdd'], False)} | {live} | {ytd} |")
    lines += ['', '## Book level, 2015-2026 (29/29/27/15, drift, 40% cap; gate on HG only)', '',
              '| Variant | Book CAGR | Sharpe | Sortino | Max DD | Worst year |', '|---|---|---|---|---|---|']
    for lab, _, bk in V:
        m = book.get(bk)
        if m:
            lines.append(f"| {lab} | {pct(m['cagr'])} | {m['sharpe']:.2f} | {m['sortino']:.2f} | {pct(m['maxdd'], False)} | {pct(m['worst_year'])} |")
    # full metric set per period (owner request: Sharpe, Sortino, max DD for every period)
    V4 = V[:4]
    hdr = '| Variant | CAGR | Vol | Sharpe | Sortino | Calmar | Max DD | Worst year | Longest underwater |'
    sep = '|---|---|---|---|---|---|---|---|---|'

    def row(lab, m):
        cal = f"{m['calmar']:.2f}" if m.get('calmar') is not None else ''
        tuw = f"{m['tuw_days'] / 21:.0f} mo" if m.get('tuw_days') is not None else ''
        return (f"| {lab} | {pct(m['cagr'])} | {pct(m['vol'], False)} | {m['sharpe']:.2f} | {m['sortino']:.2f} | {cal} | "
                f"{pct(m['maxdd'], False)} | {pct(m['worst_year'])} | {tuw} |")
    lines += ['', '## Full metrics by period', '']
    periods = [('1990-2026, full history', lambda k: B['rows'][k]['full'])]
    for w in ('1990-99', '2000-02 bear', '2003-07', '2007-09 bear', '2009-19', '2020-26'):
        periods.append((f'{w} (1990-2026 panel)', lambda k, w=w: B['rows'][k]['windows'][w]))
    periods.append(('2015-2026, real tickers (in sample)', lambda k: A['rows'][k]['full']))

    def live(k):
        s_ = A['series_keep'][k]
        ds = sorted(s_)
        return lg.gs.metrics(s_, ['x'] + ds, '2023-04-19')
    periods.append(('Live era, 2023-04-19 to 2026-10-07', live))
    for title, get in periods:
        lines += [f'### {title}', '', hdr, sep] + [row(lab, get(k)) for lab, k, _ in V4] + ['']
    lines += ['### Book 2015-2026 (29/29/27/15, 40% cap; gate on HG only)', '', hdr, sep]
    lines += [row(lab, book[bk]) for lab, _, bk in V4 if bk in book] + ['']
    PB, _, rb = lg.engine_runs('B')
    PA, _, ra = lg.engine_runs('A')
    sb, bb, _ = switches(PB, rb['HG'][0])
    sa, ba, now = switches(PA, ra['HG'][0])
    lines += ['', '## Operation', '',
              f'- SPY below its 200-day: {bb * 100:.0f}% of sessions 1990-2026, {ba * 100:.0f}% in 2015-2026.',
              f'- Gate flips (above/below the 200-day): {sb:.1f} per year 1990-2026, {sa:.1f} per year 2015-2026; each flip is one extra trade on the trend leg held that day.',
              f'- Today ({ra["HG"][0][-1]}): SPY {now * 100:+.1f}% vs its 200-day, so the gate is open and HG would hold exactly what it holds now.',
              '- Composer can express it as one condition (SPY price above SPY 200-day moving average of price) in front of each trend basket.']
    out = '\n'.join(lines) + '\n'
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'results', 'hg-200d-gate-comparison-2026-10-17.md')
    open(path, 'w').write(out)
    print(out)


if __name__ == '__main__':
    main()
