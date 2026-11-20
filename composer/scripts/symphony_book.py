#!/usr/bin/env python3
"""The symphony logic book: each live symphony's approved logic in plain English, why it is built
that way, and how it has changed (composer/symphonies/).

Sources, and nothing else (no network, no Composer call):
  fixtures/approved/manifest.json   the approved versions of each engine, by era
  fixtures/approved/<tree>.json     the logic tree of each approved version (GET /symphonies/{id}/score)
  symphonies/why/<ENGINE>.md        hand-written: purpose, the reason for each block, each change
  symphonies/tree-pins.json         the logic fingerprint of every approved tree (shadow_runner.tree_sha1)

Output, one file per engine plus an index, all GENERATED (never edited by hand):
  symphonies/<ENGINE>.md   identity, the why text, the current logic as an outline, the blocks it
                           repeats, the funds it can hold, and every approved version with a line
                           diff of the outline against the version before it
  symphonies/README.md     the index and the rule for keeping it current

Keeping it current is tested, not remembered: tests/test_symphony_book.py fails when these files are
not what this script would write, when an approved version has no entry of its own in its engine's
why file, when an approved tree's logic no longer matches its pinned fingerprint (a tree edited in
place), when a fund a live tree can hold has no description here, or when the outline loses a
condition, a ranked pick or a fund of the tree. The repo has no CI and no commit hook: the tests
fail, nothing blocks the commit. What the tests cannot see: whether the hand-written why text
(weights, status, numbers) is still true. An UNAPPROVED change on Composer is caught elsewhere: the
shadow runner's LOGIC DRIFT alert.

Only logic the shadow runner's evaluator has been validated on is described (shadow_runner.validate):
anything else is refused, never paraphrased.

Usage: symphony_book.py            write the book
       symphony_book.py --check    exit 1 and name the files that are stale; write nothing
"""
import argparse
import difflib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shadow_runner as sr  # noqa: E402  (validate, tree_sha1: the evaluator's own reading of a tree)
ROOT = os.path.normpath(os.path.join(HERE, ".."))
APPROVED = os.path.join(ROOT, "fixtures", "approved")
BOOK = os.path.join(ROOT, "symphonies")
WHY = os.path.join(BOOK, "why")
PINS = os.path.join(BOOK, "tree-pins.json")
WHY_MIN = 60                 # characters an approved version's own entry in the why file must run to
BLOCK_MIN_LINES = 3          # a named group repeated at least twice and this long is printed once

FN = {"relative-strength-index": "RSI", "moving-average-price": "moving-average price",
      "current-price": "price", "cumulative-return": "return", "standard-deviation-return": "volatility of returns"}
CMP = {"gt": ">", "lt": "<"}

# What each fund is, written here: Composer's own labels in the trees are not used (the saved HARV and
# KMLM trees label ZVOL with UVXY's name, which inverts it). A fund a live tree can hold needs a row.
FUNDS = {
    "ANGL": "fallen-angel high-yield bonds", "BIL": "1-3 month Treasury bills",
    "BOXX": "box spreads: T-bill-like return paid as price gain", "BSV": "short-term bonds",
    "KIE": "insurance stocks", "LABD": "-3x biotech", "LABU": "3x biotech", "LQD": "investment-grade corporate bonds",
    "PULS": "ultra-short bonds (cash-like)", "QLD": "2x Nasdaq-100", "SMH": "semiconductor stocks",
    "SOXL": "3x semiconductors", "SOXS": "-3x semiconductors", "SPAB": "US aggregate bonds",
    "SPXL": "3x S&P 500", "SQQQ": "-3x Nasdaq-100", "SSO": "2x S&P 500",
    "SVIX": "-1x short-term VIX futures (short volatility)", "SVXY": "-0.5x short-term VIX futures (short volatility)",
    "TECL": "3x technology", "TLT": "20+ year Treasuries", "TMF": "3x 20+ year Treasuries",
    "TMV": "-3x 20+ year Treasuries", "TNA": "3x Russell 2000", "TQQQ": "3x Nasdaq-100", "UDOW": "3x Dow 30",
    "UGL": "2x gold", "UPRO": "3x S&P 500", "USD": "2x semiconductors",
    "UVXY": "1.5x short-term VIX futures (long volatility)", "VBF": "closed-end investment-grade bond fund",
    "VCIT": "intermediate corporate bonds", "VIXM": "mid-term VIX futures (long volatility)",
    "VIXY": "short-term VIX futures (long volatility)", "VXZ": "mid-term VIX futures note (long volatility)",
    "ZVOL": "about -1x mid-term VIX futures (short volatility); pays a large monthly distribution",
}


class BookError(Exception):
    """a tree this renderer cannot describe exactly: better no book than a wrong one"""


def kids(n):
    return n.get("children") or []


def _window(n, side):
    p = n.get(f"{side}-fn-params") or {}
    w = p.get("window", n.get(f"{side}-window-days"))
    return int(w) if w not in (None, "") else None


def measure(fn, ticker, w):
    """'RSI(SPY, 10d)', 'price of SPY', 'return of TQQQ over 1d'"""
    if fn not in FN:
        raise BookError(f"unknown function {fn!r}")
    if fn == "current-price":
        return f"price of {ticker}"
    if w is None:
        raise BookError(f"{fn} of {ticker} has no window")
    if fn == "relative-strength-index":
        return f"RSI({ticker}, {w}d)"
    if fn == "cumulative-return":
        return f"return of {ticker} over {w}d"
    return f"{w}d {FN[fn]} of {ticker}"


def condition(c):
    """one if-child's test as text"""
    lhs = measure(c["lhs-fn"], c["lhs-val"], _window(c, "lhs"))
    cmp_ = CMP.get(c.get("comparator"))
    if cmp_ is None:
        raise BookError(f"unknown comparator {c.get('comparator')!r}")
    if not c.get("rhs-fixed-value?"):
        if not c.get("rhs-fn"):
            raise BookError(f"{lhs} is compared with a ticker without a function")
        rhs = measure(c["rhs-fn"], c["rhs-val"], _window(c, "rhs"))
    else:
        rhs = str(c["rhs-val"])
        if c["lhs-fn"] in ("cumulative-return", "standard-deviation-return"):
            rhs += "%"
    return f"{lhs} {cmp_} {rhs}"


def weight_of(node):
    """a child's weight as its parent reads it (shadow_runner.weight_of); None when it has none"""
    w = node.get("weight")
    if isinstance(w, dict):
        return float(w["num"]) / float(w.get("den", 100))
    return None


def shares(children):
    """the children's shares of a fixed-weight split, as text: each weight over the siblings' total,
    which is how Composer and the shadow runner read them (a weight is read nowhere else)"""
    ws = [weight_of(c) for c in children]
    if any(w is None for w in ws) or not sum(ws) > 0:
        raise BookError("a fixed-weight split whose children do not all carry a weight")
    out = []
    for w in ws:
        x = 100.0 * w / sum(ws)
        out.append(f"{x:.0f}%" if abs(x - round(x)) < 1e-6 else f"{x:.2f}%")
    return out


def sort_text(n):
    fn = n.get("sort-by-fn")
    if fn not in FN:
        raise BookError(f"unknown sort function {fn!r}")
    p = n.get("sort-by-fn-params") or {}
    w = p.get("window", n.get("sort-by-window-days"))
    name = {"relative-strength-index": "RSI", "cumulative-return": "return"}.get(fn, FN[fn])
    return f"{w}d {name}" if w not in (None, "") else name


class Outline:
    """renders one tree. blocks=True prints a repeated named group once and refers to it by name"""

    def __init__(self, tree, blocks=True):
        self.tree, self.use_blocks = tree, blocks
        self.counts, self.names, self.defs = {}, {}, []
        if blocks:
            self._count(tree)

    def _count(self, n):
        if n.get("step") == "group" and n.get("name"):
            body = tuple(self._body(n, plain=True))
            if len(body) >= BLOCK_MIN_LINES:
                self.counts[(n["name"], body)] = self.counts.get((n["name"], body), 0) + 1
        for c in kids(n):
            self._count(c)

    def _label(self, key):
        """the block's printed name: the group's name, numbered when two different bodies share it"""
        if key not in self.names:
            same = [k for k in self.names if k[0] == key[0]]
            self.names[key] = key[0] if not same else f"{key[0]} (variant {len(same) + 1})"
            self.defs.append(key)
        return self.names[key]

    def _body(self, n, plain=False):
        """the single child of a root, group or branch (the evaluator gives each of several its full
        weight, which no outline line could say: refused)"""
        if len(kids(n)) != 1:
            raise BookError(f"a {n.get('step')} with {len(kids(n))} children")
        return self.lines(kids(n)[0], plain=plain)

    def lines(self, n, plain=False, prefix=""):
        """the node as outline lines (two spaces per level); prefix is its share in a weighted split"""
        step = n.get("step")
        if step == "asset":
            return [prefix + n["ticker"]]
        if step in ("root", "wt-cash-equal", "wt-cash-specified"):
            ch = kids(n)
            if step == "root" or len(ch) == 1:
                if step == "wt-cash-specified":
                    shares(ch)                          # a lone child must still carry a weight above 0
                out = self._body(n, plain)
                return self._prefixed(out, prefix)
            if step == "wt-cash-specified":
                out = [prefix + "split by fixed weights:"]
                for c, p in zip(ch, shares(ch)):
                    out += ["  " + x for x in self.lines(c, plain, prefix=p + ": ")]
                return out
            if all(c.get("step") == "asset" for c in ch):
                return [prefix + f"equal weights of {', '.join(c['ticker'] for c in ch)}"]
            out = [prefix + f"split equally across {len(ch)}:"]
            for c in ch:
                out += ["  " + x for x in self._prefixed(self.lines(c, plain), "- ")]
            return out
        if step == "group":
            name = n.get("name") or "group"
            body = self._body(n, plain=True if plain else False)
            key = (name, tuple(self._body(n, plain=True)))
            if self.use_blocks and not plain and self.counts.get(key, 0) >= 2:
                return [prefix + f"block [{self._label(key)}]"]
            return self._prefixed([f"[{name}]"] + ["  " + x for x in body], prefix)
        if step == "if":
            return self._prefixed(self._if(n, plain), prefix)
        if step == "filter":
            ch = kids(n)
            if n.get("select-fn") not in ("top", "bottom"):
                raise BookError(f"unknown select {n.get('select-fn')!r}")
            k = int(n.get("select-n"))
            pick = f"the {n.get('select-fn')} {k} by {sort_text(n)}"
            names = all(c.get("step") == "asset" for c in ch)
            if k >= len(ch):                           # a pick that can never drop a candidate
                note = f"({pick}, of {len(ch)}: nothing is ever dropped)"
                if names:
                    held = ch[0]["ticker"] if len(ch) == 1 else f"equal weights of {', '.join(c['ticker'] for c in ch)}"
                    return [prefix + f"{held} {note}"]
                out = [prefix + ("both of these, half each" if len(ch) == 2 else f"all {len(ch)} of these, equal shares")
                       + f" {note}:"]
            elif names:
                return [prefix + f"{pick} of {', '.join(c['ticker'] for c in ch)}"]
            else:
                out = [prefix + f"{pick} of these {len(ch)} (each ranked on its own branch's return series):"]
            for c in ch:
                out += ["  " + x for x in self._prefixed(self.lines(c, plain), "- ")]
            return out
        raise BookError(f"unknown step {step!r}")

    @staticmethod
    def _prefixed(lines, prefix):
        if not prefix or not lines:
            return lines
        pad = " " * len(prefix)
        return [prefix + lines[0]] + [pad + x for x in lines[1:]]

    def _if(self, n, plain):
        ch = kids(n)
        tests = [c for c in ch if not c.get("is-else-condition?")]
        elses = [c for c in ch if c.get("is-else-condition?")]
        if len(tests) != 1 or len(elses) > 1 or any(c.get("step") != "if-child" for c in ch):
            raise BookError("an if without exactly one test and at most one else")
        out = [f"IF {condition(tests[0])}:"] + ["  " + x for x in self._body(tests[0], plain)]
        if elses:
            nxt = self._lone_if(elses[0])
            if nxt is not None:                       # else-if chains stay at one depth
                sub = self._if(nxt, plain)
                out += ["ELSE " + sub[0]] + sub[1:]
            else:
                out += ["ELSE:"] + ["  " + x for x in self._body(elses[0], plain)]
        return out

    @staticmethod
    def _lone_if(else_child):
        """the if this else branch consists of, through unnamed single-child wrappers; else None"""
        n = else_child
        while True:
            ch = kids(n)
            if len(ch) != 1:
                return None
            n = ch[0]
            if n.get("step") == "if":
                return n
            if n.get("step") not in ("wt-cash-equal", "wt-cash-specified"):
                return None

    def render(self):
        """(the outline's lines, [(block name, its lines)])"""
        main = self.lines(self.tree)
        blocks, i = [], 0
        while i < len(self.defs):                       # a block's body may name further blocks
            key = self.defs[i]
            node = self._find(self.tree, key)
            blocks.append((self.names[key], self._body(node)))
            i += 1
        return main, blocks

    def _find(self, n, key):
        if n.get("step") == "group" and n.get("name") == key[0] and tuple(self._body(n, plain=True)) == key[1]:
            return n
        for c in kids(n):
            hit = self._find(c, key)
            if hit is not None:
                return hit
        return None


def census(tree):
    """what the tree holds, counted on the tree itself: (tests, filters, sorted tickers, nodes)"""
    tests = filters = nodes = 0
    tickers = set()
    stack = [tree]
    while stack:
        n = stack.pop()
        nodes += 1
        s = n.get("step")
        tests += s == "if-child" and not n.get("is-else-condition?")
        filters += s == "filter"
        if s == "asset":
            tickers.add(n["ticker"])
        stack += kids(n)
    return tests, filters, sorted(tickers), nodes


def why_entry(why, version):
    """the text of the version's own entry in a why file (a bullet starting - **`<first 8>`**, up to
    the next bullet or heading), or None"""
    key = f"- **`{version[:8]}`**"
    lines, out = why.split("\n"), None
    for x in lines:
        if x.startswith(key):
            out = [x[len(key):]]
        elif out is not None:
            if x.startswith(("- ", "#")):
                break
            out.append(x)
    return None if out is None else " ".join(" ".join(out).split())


def check_pins(manifest):
    """raises BookError unless every approved tree is one the evaluator is validated on, every fund it
    can hold is described, and its logic fingerprint is the pinned one. The pins are never rewritten
    here: a tree edited in place is refused, and a new tree's pin is added by hand with its era"""
    try:
        pins = load(PINS)
    except FileNotFoundError:
        raise BookError("symphonies/tree-pins.json is missing") from None
    for eng, cfg in manifest["engines"].items():
        for era in cfg["eras"]:
            tree = load(os.path.join(APPROVED, era["tree"]))
            try:
                sr.validate(tree)
            except sr.Unsupported as e:
                raise BookError(f"{era['tree']}: logic the evaluator is not validated on ({e})") from None
            got = sr.tree_sha1(tree)
            want = pins.get(era["tree"])
            if want is None:
                raise BookError(f"{era['tree']} has no pin in symphonies/tree-pins.json: add \"{era['tree']}\": "
                                f"\"{got}\" with its era")
            if got != want:
                raise BookError(f"{era['tree']} no longer has the logic that was approved (fingerprint {got[:12]}, "
                                f"pinned {want[:12]}): an approved tree is never edited in place; a logic change "
                                f"is a new tree file and a new era")
            missing = [t for t in census(tree)[2] if t not in FUNDS]
            if missing:
                raise BookError(f"{era['tree']} can hold {', '.join(missing)}: describe them in symphony_book.FUNDS")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rebalance_text(tree, cfg):
    r = tree.get("rebalance")
    if r == "daily":
        return "daily (~15:50 ET)"
    if r == "none":
        c = cfg.get("corridor", tree.get("rebalance-corridor-width"))
        return (f"threshold: trades only when a holding is more than {100 * float(c):.0f} percentage points of the "
                f"symphony's own value from its target weight (absolute reading, inferred from Composer's "
                f"backtests: results.md addendum 48); the signals are still read every session")
    return str(r)


def engine_page(eng, cfg, why_text):
    eras = cfg["eras"]
    trees = [load(os.path.join(APPROVED, e["tree"])) for e in eras]
    cur, tree = eras[-1], trees[-1]
    main, blocks = Outline(tree).render()
    tests, filters, tickers, nodes = census(tree)
    out = [f"# {eng}: {' '.join(tree.get('name', eng).split())}", "",
           "> GENERATED by `scripts/symphony_book.py` from `fixtures/approved/` and `symphonies/why/"
           f"{eng}.md`. Do not edit this file: change those and re-run the script.", "",
           "| | |", "|---|---|",
           f"| Symphony id | `{cfg['symphony']}` |",
           f"| Approved version | `{cur['version']}`, in force from the {cur['from']} session |",
           f"| Rebalance | {rebalance_text(tree, cfg)} |",
           f"| Size of the logic | {tests} conditions, {filters} ranked picks, {len(tickers)} funds, {nodes} nodes |",
           f"| Approved versions on file | {len(eras)} |", "",
           why_text.strip(), "",
           f"## The logic, as approved (version `{cur['version'][:8]}`)", "",
           "Within each IF / ELSE IF / ELSE chain the first true test is taken; each part of a split is "
           "decided separately and held at its share. `Nd` is N trading days. RSI is Wilder's. Decided on "
           "prices a few minutes before the close (measured about 15:51-15:54 ET, results.md addendum 50; "
           "Composer does not publish the time).", "", "```"]
    out += main + ["```", ""]
    if blocks:
        out += ["### Blocks used more than once", ""]
        for name, body in blocks:
            out += [f"**[{name}]**", "", "```"] + body + ["```", ""]
    out += ["## Funds it can hold", "",
            "Descriptions are this repo's, not Composer's labels.", "", "| Ticker | What it is |", "|---|---|"]
    out += [f"| {t} | {FUNDS[t]} |" for t in tickers] + [""]
    out += ["## Approved versions", "",
            "Each entry is an approved era in the manifest. The diff under it is that version's rebalance "
            "rule and outline against the one before (`-` removed, `+` added).", ""]
    prev = None
    for era, t in zip(eras, trees):
        full = [f"rebalance: {rebalance_text(t, cfg)}"] + Outline(t, blocks=False).render()[0]
        out += [f"### `{era['version']}`: from the {era['from']} session", "",
                f"- Created {era['created_at']} (ET). Tree: `fixtures/approved/{era['tree']}`.",
                f"- {era['note']}", ""]
        if prev is None:
            out += ["First approved version on file.", ""]
        else:
            d = [x for x in difflib.unified_diff(prev, full, lineterm="", n=1)][2:]
            out += (["```diff"] + d + ["```", ""]) if d else ["Logic identical to the version before.", ""]
        prev = full
    return "\n".join(out).rstrip("\n") + "\n"


def index_page(manifest):
    out = ["# The symphony logic book", "",
           "> GENERATED by `scripts/symphony_book.py`. Do not edit: run the script.", "",
           "What each live symphony does, why, and how it has changed. One page per engine.", "",
           "| Engine | Symphony | Approved version | Since | Versions on file |", "|---|---|---|---|---|"]
    for eng, cfg in manifest["engines"].items():
        cur = cfg["eras"][-1]
        name = " ".join(load(os.path.join(APPROVED, cur["tree"])).get("name", eng).split())
        out.append(f"| [{eng}]({eng}.md) | {name} | `{cur['version'][:8]}` | {cur['from']} | {len(cfg['eras'])} |")
    out += ["", "## How it stays current", "",
            "- The logic on each page is rendered from the approved tree, so it cannot differ from what the",
            "  shadow runner and the IBKR mirror run.",
            "- Approving a logic change: save the new tree as a NEW file in `fixtures/approved/` (an approved",
            "  tree is never edited in place), add its era to `manifest.json` and its fingerprint to",
            "  `symphonies/tree-pins.json`, write what changed and why as a bullet starting",
            "  ``- **`<first 8 of the id>`**`` in `symphonies/why/<ENGINE>.md`, describe any new fund in",
            "  `symphony_book.FUNDS`, run `python3 composer/scripts/symphony_book.py`, and commit all of it",
            "  with the CHANGELOG entry. Also refresh the shadow runner's frozen fixture",
            "  (`tests/test_shadow_runner.py` S4 pins the current version of each engine).",
            "- `tests/test_symphony_book.py` fails until that is done. The repo has no CI or commit hook, so",
            "  a failing test is a signal, not a lock.",
            "- A change made on Composer without that is caught daily: the shadow runner's LOGIC DRIFT alert.",
            "- The why files are hand-written and cite the study behind each choice (`results/results.md`",
            "  addenda, `CHANGELOG.md`). Numbers in them are in-sample records, not forecasts. No test can",
            "  tell whether that text (weights, status, live numbers) is still true: it is re-read whenever",
            "  POLICY or an engine's status changes.", ""]
    return "\n".join(out)


def build():
    """{path: text} of every file of the book"""
    manifest = load(os.path.join(APPROVED, "manifest.json"))
    check_pins(manifest)
    pages = {os.path.join(BOOK, "README.md"): index_page(manifest)}
    for eng, cfg in manifest["engines"].items():
        path = os.path.join(WHY, f"{eng}.md")
        try:
            with open(path, encoding="utf-8") as f:
                why = f.read()
        except FileNotFoundError:
            raise BookError(f"symphonies/why/{eng}.md is missing: every engine needs its reasons on file") from None
        missing = [e["version"][:8] for e in cfg["eras"] if len(why_entry(why, e["version"]) or "") < WHY_MIN]
        if missing:
            raise BookError(f"symphonies/why/{eng}.md has no entry of its own for the approved version(s) "
                            f"{', '.join(missing)}: under \"What changed, and why\" write a bullet starting "
                            f"- **`<first 8 of the id>`** saying what changed and why")
        pages[os.path.join(BOOK, f"{eng}.md")] = engine_page(eng, cfg, why)
    return pages


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true")
    a = p.parse_args(argv)
    try:
        pages = build()
    except BookError as e:
        print(f"SYMPHONY BOOK REFUSED: {e}")
        return 1
    stale = []
    for path, text in pages.items():
        try:
            with open(path, encoding="utf-8") as f:
                same = f.read() == text
        except FileNotFoundError:
            same = False
        if not same:
            stale.append(os.path.relpath(path, ROOT))
            if not a.check:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
    if a.check and stale:
        print("SYMPHONY BOOK STALE: " + ", ".join(stale) + " - run python3 composer/scripts/symphony_book.py")
        return 1
    print(("symphony book current" if not stale else "symphony book written: " + ", ".join(stale))
          + f" ({len(pages)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
