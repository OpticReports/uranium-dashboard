"""Build the HG 200-day gate draft (add. 42/44 candidate): the live HG tree with each of its two trend-basket
filters (top-1 RSI of TQQQ/UPRO/UDOW/SSO/TNA) wrapped in one condition, SPY price above its 200-day moving
average -> the basket as before, else -> BIL.  Dip-buys, the long-vol branch and the existing BIL defaults
are untouched; every original node keeps its id.  Reads the live tree (read-only GET) or a saved copy;
writes the draft tree and a diff summary to the scratch dir.  Nothing is saved to Composer here; the save was
  scripts/composer-api.py create -f <out> --name "<NAME>" --hashtag "#hg200ddraft"
-> symphony hZ6NSYPMQi3N0otU6lY6, version NyvFccHtb3Bc1mikyuNk (2026-10-18, uninvested).

usage: build_gate_draft.py [--from FILE] [--out FILE]"""
import argparse
import copy
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'scripts'))
import composerlib as cl   # noqa: E402

HG = 'mbkiXcuNDjueXpiox5Av'
TREND = {'TQQQ', 'UPRO', 'UDOW', 'SSO', 'TNA'}
SCRATCH = '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/draft'
NAME = 'HG + SPY 200d gate (cash below) | DRAFT, do not invest'
DESC = ('Draft for review, not for capital. The live HG (version bP4mvRy6) with one condition in front of each '
        'trend basket: SPY price above its 200-day moving average -> the basket; else -> BIL. Dip-buys unchanged. '
        'Research: results.md addenda 40, 42, 44.')


def gate_node(inner, gid):
    """if (SPY current-price gt SPY 200d MA) -> inner (existing wt-cash-equal); else -> BIL.
    Mirrors the shape of HG's own TQQQ-vs-20d condition (nodes 6179bf64 / 6b57f3b5 / 9f015dee)."""
    ids = {k: str(uuid.UUID(int=gid * 16 + i, version=4)) for i, k in enumerate(['outer', 'if', 'cond', 'else', 'cash_w', 'bil'])}
    return {'id': ids['outer'], 'step': 'wt-cash-equal', 'children': [
        {'id': ids['if'], 'step': 'if', 'children': [
            {'id': ids['cond'], 'step': 'if-child', 'is-else-condition?': False,
             'lhs-fn': 'current-price', 'lhs-val': 'SPY', 'comparator': 'gt',
             'rhs-fn': 'moving-average-price', 'rhs-val': 'SPY', 'rhs-fn-params': {'window': 200},
             'children': [inner]},
            {'id': ids['else'], 'step': 'if-child', 'is-else-condition?': True, 'children': [
                {'id': ids['cash_w'], 'step': 'wt-cash-equal', 'children': [
                    {'id': ids['bil'], 'step': 'asset', 'ticker': 'BIL'}]}]}]}]}


def is_trend_filter(n):
    return n.get('step') == 'filter' and {c.get('ticker') for c in n.get('children', [])} == TREND


def build(live):
    tree = copy.deepcopy(live)
    wrapped = []

    def walk(n, parent):
        for i, c in enumerate(list(n.get('children', []))):
            if c.get('step') == 'wt-cash-equal' and len(c.get('children', [])) == 1 and is_trend_filter(c['children'][0]):
                n['children'][i] = gate_node(c, len(wrapped) + 1)
                wrapped.append((parent_label(n), c['children'][0]['id']))
            else:
                walk(c, n)
    walk(tree, None)
    tree['name'] = NAME
    tree['description'] = DESC
    tree['id'] = str(uuid.uuid4())   # POST /symphonies rejects a root without an id (HTTP 400); Composer re-keys it
    return tree, wrapped


def parent_label(n):
    return f"{n.get('step')} {n['id'][:8]}"


def tickers(n, acc=None):
    acc = set() if acc is None else acc
    if n.get('step') == 'asset':
        acc.add(n['ticker'])
    for c in n.get('children', []):
        tickers(c, acc)
    return acc


def count(n):
    return 1 + sum(count(c) for c in n.get('children', []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='src', help='saved live score JSON (default: fetch the live tree)')
    ap.add_argument('--out', default=os.path.join(SCRATCH, 'hg_gate_draft_tree.json'))
    a = ap.parse_args()
    live = json.load(open(a.src)) if a.src else cl.get(f'/symphonies/{HG}/score')
    assert live.get('id') == HG and live.get('step') == 'root', 'unexpected live tree'
    tree, wrapped = build(live)
    assert len(wrapped) == 2, wrapped
    # the five trend tickers must appear only inside the two wrapped filters
    assert count(tree) == count(live) + 2 * 6, (count(tree), count(live))
    assert tickers(tree) == tickers(live), (tickers(tree) ^ tickers(live))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(tree, open(a.out, 'w'), indent=1)
    json.dump(live, open(os.path.join(os.path.dirname(a.out), 'hg_live_tree_at_build.json'), 'w'), indent=1)
    print('live nodes', count(live), '-> draft nodes', count(tree), '(+12: two gates of six nodes each)')
    for where, fid in wrapped:
        print(f'  wrapped trend filter {fid[:8]} under {where}')
    print('wrote', a.out)


if __name__ == '__main__':
    main()
