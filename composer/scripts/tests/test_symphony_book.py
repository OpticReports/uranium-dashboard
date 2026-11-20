"""Gate tests for the symphony logic book (composer/symphonies/, scripts/symphony_book.py).

  B1  the book on disk is exactly what the script writes from the approved trees and the why files
  B2  every approved version of every engine has an entry of its own in that engine's why file (a
      bullet starting - **`<id8>`** with real text): a bare mention elsewhere does not count
  B7  an approved tree's logic is pinned: edited in place (no new era), the book is refused; so is a
      tree the evaluator is not validated on, and a held fund with no description
  B8  a change of the rebalance rule between two versions shows in the version diff
  B3  the outline loses nothing: every condition, ranked pick and fund of each approved tree is in it,
      with and without repeated blocks folded
  B4  fixed-weight splits read as Composer reads them: each weight over its siblings' total, and a
      weight on a node whose parent is not a fixed-weight split is ignored
  B5  pinned facts of the live trees (a renderer that garbles them fails here, not in a report)
  B6  a tree the renderer does not understand is refused, never described approximately

Run: python3 -m unittest composer.scripts.tests.test_symphony_book -v
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import symphony_book as sb  # noqa: E402


def manifest():
    return sb.load(os.path.join(sb.APPROVED, "manifest.json"))


def trees():
    for eng, cfg in manifest()["engines"].items():
        for era in cfg["eras"]:
            yield eng, era, sb.load(os.path.join(sb.APPROVED, era["tree"]))


def current(eng):
    cfg = manifest()["engines"][eng]
    return sb.load(os.path.join(sb.APPROVED, cfg["eras"][-1]["tree"]))


def text_of(tree, blocks):
    main, defs = sb.Outline(tree, blocks=blocks).render()
    return main, defs, "\n".join(main + [x for _, body in defs for x in body])


class Current(unittest.TestCase):
    def test_b1_book_on_disk_is_what_the_script_writes(self):
        pages = sb.build()
        self.assertEqual(len(pages), 1 + len(manifest()["engines"]))
        for path, text in pages.items():
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), text, f"{os.path.relpath(path, sb.ROOT)} is stale: run "
                                                 f"python3 composer/scripts/symphony_book.py")
        self.assertEqual(sb.main(["--check"]), 0)

    def test_b2_every_approved_version_has_its_own_entry_in_its_why_file(self):
        for eng, cfg in manifest()["engines"].items():
            with open(os.path.join(sb.WHY, f"{eng}.md"), encoding="utf-8") as f:
                why = f.read()
            for era in cfg["eras"]:
                entry = sb.why_entry(why, era["version"])
                self.assertIsNotNone(entry, f"{eng}: no entry for {era['version']}")
                self.assertTrue(sb.says_something(entry), f"{eng}: the entry for {era['version']} says nothing")

    def test_b2_a_mention_is_not_an_entry(self):
        long = "a reason with enough words in it to count as one for the version"
        why = ("## What it is for\n\n- **`EEEEeeee`** " + long + "\n\n"
               "## What changed, and why\n\n- **`AAAAaaaa`** (live from 2026-01-01): the first version, with "
               "enough words to count as a reason for it.\n  A second line that belongs to it; it also names "
               "`BBBBbbbb` in passing.\n- **`CCCCcccc`**: x\n- **`FFFFffff`** " + " ." * 60 + "\n"
               "- **`GGGGgggg`**\n\nAn unrelated paragraph, " + long + ".\n"
               "<!-- DDDDdddd -->\n<!--\n- **`HHHHhhhh`** " + long + "\n-->\n"
               "```\n- **`IIIIiiii`** " + long + "\n```\n\n## Later\n\n- **`JJJJjjjj`** " + long + "\n")
        ok = lambda v: sb.says_something(sb.why_entry(why, v + "XXXX"))                  # noqa: E731
        self.assertIn("A second line that belongs to it", sb.why_entry(why, "AAAAaaaaXXXX"))
        self.assertTrue(ok("AAAAaaaa"))
        for v, what in (("BBBBbbbb", "a mention in passing"), ("CCCCcccc", "one letter"),
                        ("DDDDdddd", "a comment"), ("EEEEeeee", "a bullet in another section"),
                        ("FFFFffff", "dots"), ("GGGGgggg", "an empty bullet before an unrelated paragraph"),
                        ("HHHHhhhh", "a bullet inside a comment"), ("IIIIiiii", "a bullet inside a code fence"),
                        ("JJJJjjjj", "a bullet in a later section")):
            self.assertFalse(ok(v), what)
        self.assertIsNone(sb.why_entry("no such section\n- **`AAAAaaaa`** " + long, "AAAAaaaaXXXX"))

    def test_b2_a_new_era_without_its_reason_is_refused(self):
        real = sb.load

        def fake(path):
            d = real(path)
            if path.endswith("manifest.json"):
                d["engines"]["HG"]["eras"].append(dict(d["engines"]["HG"]["eras"][-1], version="ZZZZnewversion0000000"))
            return d
        sb.load = fake
        try:
            with self.assertRaises(sb.BookError) as cm:
                sb.build()
        finally:
            sb.load = real
        self.assertIn("ZZZZnewv", str(cm.exception))


class Pinned(unittest.TestCase):
    def _with(self, change):
        """build() with one loaded file changed in memory: change(path, data) -> data"""
        real = sb.load

        def fake(path):
            return change(path, real(path))
        sb.load = fake
        try:
            with self.assertRaises(sb.BookError) as cm:
                sb.build()
        finally:
            sb.load = real
        return str(cm.exception)

    def test_b7_every_approved_tree_has_its_pinned_fingerprint(self):
        pins = sb.load(sb.PINS)
        files = sorted(era["tree"] for cfg in manifest()["engines"].values() for era in cfg["eras"])
        self.assertEqual(sorted(pins), files)
        for f in files:
            self.assertEqual(sb.sr.tree_sha1(sb.load(os.path.join(sb.APPROVED, f))), pins[f], f)

    def test_b7_a_tree_edited_in_place_is_refused(self):
        for name, find, new in (("sleeve-yHJkdePZ.json", "-6", "-5"), ("kmlm-MVfHI8Og.json", "25", "28"),
                                ("hg-6jq2MZNf.json", "30", "28")):
            def change(path, d, name=name, find=find, new=new):
                if not path.endswith(name):
                    return d
                hit = []

                def walk(n):
                    if not hit and n.get("step") == "if-child" and str(n.get("rhs-val")) == find:
                        n["rhs-val"] = new
                        hit.append(1)
                    for c in n.get("children") or []:
                        walk(c)
                walk(d)
                self.assertTrue(hit, name)
                return d
            msg = self._with(change)
            self.assertIn(name, msg)
            self.assertIn("never edited in place", msg)

    def test_b7_a_rebalance_edit_in_place_is_refused(self):
        def change(path, d):
            if path.endswith("sleeve-yHJkdePZ.json"):
                d["rebalance"] = "none"
                d["rebalance-corridor-width"] = 0.1
            return d
        self.assertIn("never edited in place", self._with(change))

    def test_b7_unvalidated_logic_and_undescribed_funds_are_refused(self):
        def gte(path, d):
            if path.endswith("hg-2oyXahw1.json"):
                def walk(n):
                    if n.get("comparator") == "gt":
                        n["comparator"] = "gte"
                    for c in n.get("children") or []:
                        walk(c)
                walk(d)
            return d
        self.assertIn("not validated", self._with(gte))
        real = dict(sb.FUNDS)
        try:
            del sb.FUNDS["BOXX"]
            with self.assertRaises(sb.BookError) as cm:
                sb.build()
        finally:
            sb.FUNDS.clear()
            sb.FUNDS.update(real)
        self.assertIn("BOXX", str(cm.exception))

    def test_b7_zvol_is_described_as_short_volatility(self):
        for eng in ("HARV", "KMLM"):
            with open(os.path.join(sb.BOOK, f"{eng}.md"), encoding="utf-8") as f:
                page = f.read()
            row = [x for x in page.split("\n") if x.startswith("| ZVOL |")]
            self.assertEqual(len(row), 1)
            self.assertIn("short volatility", row[0])
            self.assertNotIn("Ultra VIX Short-Term", page)

    def test_b8_a_rebalance_change_shows_in_the_version_diff(self):
        cfg = {"symphony": "x", "corridor": 0.1, "eras": [
            {"version": "A" * 20, "from": "2026-01-01", "created_at": "t", "tree": "sleeve-yHJkdePZ.json", "note": "n"},
            {"version": "B" * 20, "from": "2026-02-01", "created_at": "t", "tree": "sleeve-yHJkdePZ.json", "note": "n"}]}
        real = sb.load
        seen = []

        def fake(path):
            d = real(path)
            seen.append(1)
            if len(seen) == 2:                       # the second era's tree: threshold in place of daily
                d["rebalance"], d["rebalance-corridor-width"] = "none", 0.1
            return d
        sb.load = fake
        try:
            page = sb.engine_page("X", cfg, "why")
        finally:
            sb.load = real
        self.assertIn("-rebalance: daily", page)
        self.assertIn("+rebalance: threshold", page)
        self.assertNotIn("Logic identical", page)

    def test_b8_the_corridor_printed_is_the_trees_and_the_manifest_must_agree(self):
        era = lambda v, f: {"version": v * 20, "from": f, "created_at": "t", "tree": "kmlm-MVfHI8Og.json",  # noqa: E731
                            "note": "n"}
        real = sb.load
        seen = []

        def fake(path):
            d = real(path)
            seen.append(1)
            if len(seen) == 2:
                d["rebalance-corridor-width"] = 0.2
            return d
        sb.load = fake
        try:
            page = sb.engine_page("X", {"symphony": "x", "eras": [era("A", "2026-01-01"), era("B", "2026-02-01")]}, "why")
        finally:
            sb.load = real
        self.assertIn("more than 20 percentage points", page.split("## Approved versions")[0])
        self.assertIn("-rebalance: threshold: trades only when a holding is more than 10 percentage", page)
        self.assertNotIn("Logic identical", page)
        with self.assertRaises(sb.BookError):
            sb.engine_page("X", {"symphony": "x", "corridor": 0.25, "eras": [era("A", "2026-01-01")]}, "why")

    def test_b9_a_pick_of_more_than_there_are_is_refused_and_the_index_table_is_whole(self):
        fl = {"step": "filter", "select-fn": "bottom", "select-n": "2", "sort-by-fn": "cumulative-return",
              "sort-by-fn-params": {"window": 1}, "children": [{"step": "asset", "ticker": "AAA"}]}
        with self.assertRaises(sb.BookError):
            sb.Outline({"step": "root", "children": [fl]}).render()
        with open(os.path.join(sb.BOOK, "README.md"), encoding="utf-8") as f:
            rows = [x for x in f.read().split("\n") if x.startswith("| [")]
        self.assertEqual(len(rows), len(manifest()["engines"]))
        for x in rows:
            self.assertEqual(len(re.split(r"(?<!\\)\|", x)), 7, x)        # 5 cells: 6 bars, 7 pieces


class Faithful(unittest.TestCase):
    def test_b3_no_condition_pick_or_fund_is_lost(self):
        n = 0
        for eng, era, tree in trees():
            tests, filters, tickers, _ = sb.census(tree)
            main, _, _ = text_of(tree, blocks=False)
            full = "\n".join(main)
            self.assertEqual(len(re.findall(r"\bIF ", full)), tests, f"{eng} {era['version']}: conditions")
            self.assertEqual(len(re.findall(r"\bthe (?:top|bottom) \d+ by ", full)), filters,
                             f"{eng} {era['version']}: ranked picks")
            words = set(re.findall(r"[A-Z][A-Z0-9.]*", re.sub(r"\[[^\]]*\]", "", full)))
            self.assertTrue(set(tickers) <= words, f"{eng}: funds missing {set(tickers) - words}")
            _, _, folded = text_of(tree, blocks=True)
            self.assertTrue(set(tickers) <= set(re.findall(r"[A-Z][A-Z0-9.]*", folded)))
            n += 1
        self.assertGreaterEqual(n, 7)

    def test_b3_folding_blocks_changes_no_line_of_logic(self):
        """unfolding every 'block [name]' reference gives back the unfolded outline"""
        for eng, era, tree in trees():
            main, defs, _ = text_of(tree, blocks=True)
            body = dict(defs)

            def unfold(lines):
                out = []
                for x in lines:
                    m = re.match(r"^(\s*)((?:\d+(?:\.\d+)?%: |- )?)block \[(.+)\]$", x)
                    if not m:
                        out.append(x)
                        continue
                    pad = m.group(1) + " " * len(m.group(2))
                    name = m.group(3)
                    inner = unfold(body[name])
                    title = re.sub(r" \(variant \d+\)$", "", name)
                    out.append(m.group(1) + m.group(2) + f"[{title}]")
                    out += [pad + "  " + y for y in inner]
                return out
            self.assertEqual(unfold(main), sb.Outline(tree, blocks=False).render()[0], f"{eng} {era['version']}")

    def test_b4_fixed_weights_are_shares_of_the_siblings_total(self):
        kid = lambda t, w: {"step": "asset", "ticker": t, "weight": w}                      # noqa: E731
        tree = {"step": "root", "children": [{"step": "wt-cash-specified", "children": [
            kid("AAA", {"num": "30", "den": 100}), kid("BBB", {"num": 10, "den": 100})]}]}
        self.assertEqual(sb.Outline(tree).render()[0], ["split by fixed weights:", "  75%: AAA", "  25%: BBB"])
        tree = {"step": "root", "children": [{"step": "wt-cash-equal", "children": [
            kid("AAA", {"num": "0", "den": 100})]}]}
        self.assertEqual(sb.Outline(tree).render()[0], ["AAA"])
        with self.assertRaises(sb.BookError):
            sb.Outline({"step": "root", "children": [{"step": "wt-cash-specified", "children": [
                kid("AAA", None), kid("BBB", {"num": 1, "den": 2})]}]}).render()

    def test_b5_pinned_facts_of_the_live_trees(self):
        hg = "\n".join(sb.Outline(current("HG")).render()[0])
        self.assertEqual(hg.count("IF price of SPY > 200d moving-average price of SPY:"), 2)
        self.assertIn("IF RSI(TQQQ, 10d) > 80:\n    the bottom 1 by 10d RSI of UVXY, VIXY, VIXM", hg)
        _, _, harv = text_of(current("HARV"), blocks=False)
        self.assertEqual(re.findall(r"(\d+)%: IF RSI\(SPY, (\d+)d\) < 25:", harv),
                         [("36", "2"), ("16", "3"), ("8", "4"), ("8", "5"), ("8", "6"), ("8", "7"), ("8", "8"),
                          ("4", "9"), ("4", "10")])
        self.assertEqual(harv.count("IF RSI(UVXY, 14d) > 70:"), 9)
        self.assertNotIn("HYG", harv)
        _, _, km = text_of(current("KMLM"), blocks=False)
        self.assertIn("75%: [KMLM switcher]\n         [KMLM switcher (single pops)", km)
        self.assertIn("25%: [VIX sleeve]", km)
        self.assertIn("IF RSI(XLK, 10d) > RSI(KMLM, 10d):", km)
        self.assertEqual(km.count("IF RSI(UVXY, 14d) > 70:"), 9)
        _, _, sl = text_of(current("SLEEVE"), blocks=False)
        self.assertIn("IF RSI(IEF, 8d) < RSI(PSQ, 45d):", sl)
        self.assertIn("IF return of HYG over 1d > 1.75%:", sl)
        self.assertIn("BOXX", sl)
        self.assertNotIn("BIL", sl)
        self.assertIn("both of these, half each (the bottom 2 by 20d volatility of returns, of 2: nothing is ever "
                      "dropped):", sl)
        self.assertIn("UVXY (the bottom 1 by 1d return, of 1: nothing is ever dropped)", sl)

    def test_b6_unknown_logic_is_refused(self):
        base = {"step": "root", "children": [{"step": "if", "children": [
            {"step": "if-child", "lhs-fn": "relative-strength-index", "lhs-fn-params": {"window": 10},
             "lhs-val": "SPY", "comparator": "gt", "rhs-val": "80", "rhs-fixed-value?": True,
             "children": [{"step": "asset", "ticker": "AAA"}]},
            {"step": "if-child", "is-else-condition?": True, "children": [{"step": "asset", "ticker": "BBB"}]}]}]}
        self.assertEqual(sb.Outline(base).render()[0], ["IF RSI(SPY, 10d) > 80:", "  AAA", "ELSE:", "  BBB"])
        import copy
        for path, value in ((("lhs-fn",), "some-new-indicator"), (("comparator",), "between"),
                            (("comparator",), "gte"), (("lhs-fn",), "max-drawdown")):
            t = copy.deepcopy(base)
            t["children"][0]["children"][0][path[0]] = value
            with self.assertRaises(sb.BookError):
                sb.Outline(t).render()
        t = copy.deepcopy(base)
        t["children"][0]["step"] = "some-new-step"
        with self.assertRaises(sb.BookError):
            sb.Outline(t).render()
        t = copy.deepcopy(base)
        t["children"][0]["children"].append(copy.deepcopy(t["children"][0]["children"][0]))
        with self.assertRaises(sb.BookError):
            sb.Outline(t).render()
        t = copy.deepcopy(base)                       # a branch holding two things at full weight each
        t["children"][0]["children"][0]["children"].append({"step": "asset", "ticker": "CCC"})
        with self.assertRaises(sb.BookError):
            sb.Outline(t).render()
        t = copy.deepcopy(base)                       # compared with a ticker, no function named
        t["children"][0]["children"][0].update({"rhs-fixed-value?": False, "rhs-val": "QQQ"})
        with self.assertRaises(sb.BookError):
            sb.Outline(t).render()


if __name__ == "__main__":
    unittest.main()
