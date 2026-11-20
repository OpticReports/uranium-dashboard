"""Gate tests for the symphony logic book (composer/symphonies/, scripts/symphony_book.py).

  B1  the book on disk is exactly what the script writes from the approved trees and the why files
      (so an approved logic change cannot be committed without regenerating it)
  B2  every approved version of every engine is named in that engine's why file
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

    def test_b2_every_approved_version_is_named_in_its_why_file(self):
        for eng, cfg in manifest()["engines"].items():
            with open(os.path.join(sb.WHY, f"{eng}.md"), encoding="utf-8") as f:
                why = f.read()
            for era in cfg["eras"]:
                self.assertIn(era["version"][:8], why, f"{eng}: why file does not explain {era['version']}")

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
        self.assertIn("75%: [KMLM switcher]", km)
        self.assertIn("25%: [VIX sleeve]", km)
        self.assertIn("IF RSI(XLK, 10d) > RSI(KMLM, 10d):", km)
        self.assertEqual(km.count("IF RSI(UVXY, 14d) > 70:"), 9)
        _, _, sl = text_of(current("SLEEVE"), blocks=False)
        self.assertIn("IF RSI(IEF, 8d) < RSI(PSQ, 45d):", sl)
        self.assertIn("IF return of HYG over 1d > 1.75%:", sl)
        self.assertIn("BOXX", sl)
        self.assertNotIn("BIL", sl)

    def test_b6_unknown_logic_is_refused(self):
        base = {"step": "root", "children": [{"step": "if", "children": [
            {"step": "if-child", "lhs-fn": "relative-strength-index", "lhs-fn-params": {"window": 10},
             "lhs-val": "SPY", "comparator": "gt", "rhs-val": "80", "rhs-fixed-value?": True,
             "children": [{"step": "asset", "ticker": "AAA"}]},
            {"step": "if-child", "is-else-condition?": True, "children": [{"step": "asset", "ticker": "BBB"}]}]}]}
        self.assertEqual(sb.Outline(base).render()[0], ["IF RSI(SPY, 10d) > 80:", "  AAA", "ELSE:", "  BBB"])
        import copy
        for path, value in ((("lhs-fn",), "some-new-indicator"), (("comparator",), "between")):
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


if __name__ == "__main__":
    unittest.main()
