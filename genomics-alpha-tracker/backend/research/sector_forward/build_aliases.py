"""Forward test, setup step 1: the CT.gov sponsor alias table for the genomics universe.

Why: the shipped clean_company_name() turns listing names into CT.gov sponsor
queries that find nothing for a third of the genomics names ("CRISPR
Therapeutics AG Common Shares", "uniQure N V", "Silence Therapeutics Plc
American Depository Share"), and sponsors register under other names
("Autolus Limited", "ModernaTX, Inc."). A ranking by trial dates is blind to
those names. This builds, per genomics-labelled name:

  core      the listing name with listing boilerplate, legal suffixes and
            single-letter tokens removed ("uniQure", "CRISPR Therapeutics");
  queries   the core, plus its first token when distinctive (4+ letters);
  aliases   every lead-sponsor / collaborator string in those results whose
            tokens are (a) the core, (b) the core followed by anything, or
            (c) the core's first token followed only by legal suffixes
            ("Autolus Limited"); plus the core watchlist's registered
            ctgov_names (MRNA -> ModernaTX);
  rejected  the most frequent other sponsor strings, for the alias review.

A study is the company's OWN when its lead sponsor or a collaborator is one
of its aliases. The table is reviewed (two blind reviewers) and frozen
before the forward test starts; it is an input, never re-derived mid-test.

    cd genomics-alpha-tracker/backend && python -m research.sector_forward.build_aliases
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent.parent
sys.path.insert(0, str(BACKEND))

from app.config import watchlist_config  # noqa: E402
from research.sector_tier import build_ctgov as C  # noqa: E402
from research.sector_tier import build_population as P  # noqa: E402
from research.sector_tier.measure import load_ctgov  # noqa: E402

OUT = HERE / "aliases.json"
LEGAL = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "llc", "plc", "sa",
         "nv", "ag", "se", "gmbh", "bv", "ab", "as", "asa", "oy", "oyj", "spa", "srl", "kk", "pty", "lp",
         "holdings", "holding", "group", "the"}
_PHRASES = ("american depositary shares", "american depository shares", "american depositary share",
            "american depository share", "depositary shares", "depository shares", "common stock",
            "common shares", "ordinary shares", "ordinary share", "class a", "class b", "sponsored adr", " adr",
            " ads ", "each representing")


def toks(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def sponsor_core(name: str) -> str:
    low = " " + (name or "").lower() + " "
    cut = min([low.find(p) for p in _PHRASES if p in low] or [len(low)])
    words = toks(low[:cut])
    while words and (words[-1] in LEGAL or len(words[-1]) == 1):
        words.pop()
    return " ".join(words)


def is_alias(sponsor: str, core: list[str]) -> bool:
    st = toks(sponsor)
    while st and st[-1] in LEGAL:
        st.pop()
    if not st or not core:
        return False
    if st[:len(core)] == core:
        return True
    return st[0] == core[0] and len(st) >= 1 and all(t in LEGAL for t in st[1:]) and len(core[0]) >= 4


def sponsors_of(study: dict) -> list[str]:
    sc = ((study.get("protocolSection") or {}).get("sponsorCollaboratorsModule") or {})
    return [x for x in [(sc.get("leadSponsor") or {}).get("name")] + [c.get("name") for c in sc.get("collaborators") or []] if x]


def main() -> None:
    labels = json.loads((BACKEND / "research" / "sector_tier" / "labels.json").read_text())
    ctg = load_ctgov()["names"]
    pop = {p["symbol"]: p for p in json.loads(P.OUT_POP.read_text())}
    census = {r["symbol"]: r for r in P.census_today()}
    registered = {e["symbol"]: e.get("ctgov_names") or [] for e in watchlist_config().get("universe", [])}
    out = {}
    for sym in sorted(s for s, v in labels.items() if v["genomics"] and s in ctg):
        listing = (census.get(sym) or {}).get("screener_name") or pop[sym]["name"]
        core = sponsor_core(listing)
        ct = toks(core)
        queries = [core] + ([ct[0]] if ct and len(ct[0]) >= 4 and ct[0] != core else [])
        queries += [q for q in registered.get(sym, []) if q not in queries]
        seen: Counter = Counter()
        for q in queries:
            for st in C.search_name(q):
                for sp in sponsors_of(st):
                    seen[sp] += 1
        aliases = sorted({sp for sp in seen if is_alias(sp, ct)} | set(registered.get(sym, [])))
        out[sym] = {"listing": listing, "core": core, "queries": queries, "aliases": aliases,
                    "alias_study_counts": {a: seen.get(a, 0) for a in aliases},
                    "rejected_top": [x for x, _ in seen.most_common(40) if x not in aliases][:12],
                    "old_query": ctg[sym].get("query")}
        print(f"{sym:6} core={core!r:32} aliases={aliases[:4]}", flush=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"{len(out)} names; {sum(1 for v in out.values() if not v['aliases'])} with no alias found")


if __name__ == "__main__":
    main()
