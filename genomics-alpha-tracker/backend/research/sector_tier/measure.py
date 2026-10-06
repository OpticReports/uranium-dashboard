"""Sector-tier measurements, stage 4: Tier 1 point in time vs the shipped baseline.

Pre-registration: docs/DESIGN_SECTOR_TIER.md (rev 3, amendments 1-7). Every
choice below is the one recorded there; this file adds none. Inputs:

  population.json, moves.json  (stage 1: FMP)
  ctgov.json                   (stage 2: CT.gov current records + record history)
  labels.json                  (stage 3: two blind labellers + adjudicator)
  the FMP cache (bars, caps, full profile descriptions) and git history of
  config/watchlist.yaml (the core on each day)

Outputs results.json and the charts in research/sector_tier/charts/.

    cd genomics-alpha-tracker/backend && python -m research.sector_tier.measure
"""
from __future__ import annotations

import bisect
import json
import math
import random
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import yaml

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent.parent
REPO = BACKEND.parent.parent
sys.path.insert(0, str(BACKEND))

from app.ingestion import discovery as D  # noqa: E402
from research.sector_tier import build_population as P  # noqa: E402

OUT = HERE / "results.json"
CHARTS = HERE / "charts"
WIN0, WIN1 = P.WINDOW
WARM = date(2025, 8, 1)
TODAY = date(2026, 10, 5)
ACTIVE = {"RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"}
LAB_INDUSTRY = "Biotechnology: Laboratory Analytical Instruments"
CAP_MIN = 300e6
MOVER_MIN = 0.10
ROTATION = 10
HORIZON = 240
PAGE = 50
TOP_N = 25
CAT_DAYS = 30
SEED = 20261005
Z90 = 1.6448536269514722
WATCHLIST = "genomics-alpha-tracker/backend/config/watchlist.yaml"
MODALITIES = D._DEFAULTS["partner_modalities"]


def d(s: str | None) -> date | None:
    return date.fromisoformat(s[:10]) if s else None


def wilson(k: int, n: int, z: float = Z90) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


# --- the core on each day (git history of watchlist.yaml) -----------------------

def core_history() -> list[tuple[date, list[SimpleNamespace]]]:
    log = subprocess.run(["git", "-C", str(REPO), "log", "--reverse", "--format=%H %cI", "--", WATCHLIST],
                         capture_output=True, text=True, check=True).stdout.split("\n")
    out: list[tuple[date, list[SimpleNamespace]]] = []
    for line in filter(None, log):
        sha, when = line.split()
        text = subprocess.run(["git", "-C", str(REPO), "show", f"{sha}:{WATCHLIST}"],
                              capture_output=True, text=True, check=True).stdout
        entries = [SimpleNamespace(symbol=e["symbol"].upper(), name=e.get("name", ""),
                                   subsector=e.get("subsector") or [], active=bool(e.get("active", True)),
                                   ctgov_names=e.get("ctgov_names") or [])
                   for e in (yaml.safe_load(text) or {}).get("universe", [])]
        out.append((date.fromisoformat(when[:10]), [e for e in entries if e.active]))
    # Amendment 7: the first committed list stood from the start of the window.
    out[0] = (date.min, out[0][1])
    prod = HERE / "prod_export.json"
    if prod.exists():  # production adds (UI / discovery), dated by created_at
        rows = json.loads(prod.read_text()).get("security", [])
        for r in rows:
            when = d(str(r.get("created_at") or ""))
            if not when or not r.get("active", True):
                continue
            ns = SimpleNamespace(symbol=r["symbol"].upper(), name=r.get("name", ""),
                                 subsector=json.loads(r["subsector"]) if isinstance(r.get("subsector"), str) else (r.get("subsector") or []),
                                 active=True, ctgov_names=[])
            for i, (eff, ents) in enumerate(out):
                if eff >= when or (i + 1 == len(out) or out[i + 1][0] > when):
                    if ns.symbol not in {e.symbol for e in ents}:
                        ents.append(ns)
    return out


class Core:
    def __init__(self):
        self.hist = core_history()
        self.dates = [h[0] for h in self.hist]
        self._partner_cache: dict[int, set[str]] = {}

    def _idx(self, t: date) -> int:
        return bisect.bisect_right(self.dates, t) - 1

    def symbols(self, t: date) -> set[str]:
        return {e.symbol for e in self.hist[self._idx(t)][1]}

    def partners(self, t: date) -> set[str]:
        i = self._idx(t)
        if i not in self._partner_cache:
            self._partner_cache[i] = D.universe_partner_names(self.hist[i][1], MODALITIES)
        return self._partner_cache[i]


# --- prices, caps, listing --------------------------------------------------------

class Series:
    def __init__(self, sym: str):
        bars = json.loads((P.CACHE / "fmp" / "bars" / f"{sym}.json").read_text()) if \
            (P.CACHE / "fmp" / "bars" / f"{sym}.json").exists() else []
        bars = sorted((b for b in bars or [] if b.get("adjClose")), key=lambda b: b["date"])
        self.bdates = [d(b["date"]) for b in bars]
        self.close = [float(b["adjClose"]) for b in bars]
        self.dvol = [float(b["adjClose"]) * float(b.get("volume") or 0) for b in bars]
        caps = json.loads((P.CACHE / "fmp" / "mcap" / f"{sym}.json").read_text()) if \
            (P.CACHE / "fmp" / "mcap" / f"{sym}.json").exists() else []
        caps = sorted((c for c in caps or [] if c.get("marketCap")), key=lambda c: c["date"])
        self.cdates = [d(c["date"]) for c in caps]
        self.caps = [float(c["marketCap"]) for c in caps]

    def cap(self, t: date) -> float | None:
        i = bisect.bisect_right(self.cdates, t) - 1
        if i < 0 or (t - self.cdates[i]).days > 7:   # no stale cap for a name gone quiet
            return None
        return self.caps[i]

    def first_bar(self) -> date | None:
        return self.bdates[0] if self.bdates else None

    def dollar_vol_20(self, t: date) -> float:
        i = bisect.bisect_right(self.bdates, t)
        w = self.dvol[max(0, i - 20):i]
        return sum(w) / len(w) if w else 0.0


# --- CT.gov point in time -----------------------------------------------------------

class Trials:
    """A name's studies, with each relevant study's record as CT.gov showed it."""

    def __init__(self, entry: dict, pit: dict, lag: int):
        self.rows = entry.get("studies") or []
        self.timelines: dict[str, tuple] = {}
        self.fallbacks = 0
        for r in self.rows:
            h = pit.get(r["nct"])
            if not h:
                continue
            if not h.get("versions") or not h.get("status_list"):
                self.fallbacks += 1      # history unreadable: the current record stands in
                continue
            st = [(d(x["from"]) + timedelta(days=lag), x["status"]) for x in h["status_list"] if x.get("from")]
            vs = [(d(x["from"]) + timedelta(days=lag), x["pcd"], x["phases"]) for x in h["versions"] if x.get("from")]
            st.sort(key=lambda x: x[0])
            vs.sort(key=lambda x: x[0])
            self.timelines[r["nct"]] = ([x[0] for x in st], st, [x[0] for x in vs], vs)

    def state(self, r: dict, t: date):
        """(status, pcd_raw, phases) as shown on day t, or None if not shown yet."""
        fp = d(r.get("first_post"))
        if fp and fp > t:
            return None
        tl = self.timelines.get(r["nct"])
        if tl is None:
            return r["status"], r["pcd"], r["phases"]
        sd, st, vd, vs = tl
        i, j = bisect.bisect_right(sd, t) - 1, bisect.bisect_right(vd, t) - 1
        if i < 0 or j < 0:
            return None
        return st[i][1], vs[j][1], vs[j][2] or r["phases"]

    def funnel_lane(self, name: str, t: date, partners: set[str], cleaned: str) -> bool:
        """The shipped catalyst lane's decision for this name on day t."""
        returned = []
        for r in self.rows:
            s = self.state(r, t)
            if not s or s[0] not in ACTIVE:
                continue
            pcd = D._parse_loose_date(s[1])
            if pcd is None or pcd < t:
                continue
            returned.append((pcd, r, s[2]))
        returned.sort(key=lambda x: x[0])
        returned = returned[:PAGE]
        if not returned:
            return False
        p3 = [pcd for pcd, _, ph in returned if "PHASE3" in "/".join(ph)]
        near_p3 = bool(p3) and (min(p3) - t).days <= HORIZON
        if near_p3:
            return True
        active_p23 = any(("PHASE3" in "/".join(ph) or "PHASE2" in "/".join(ph)) for _, _, ph in returned)
        if not active_p23:
            return False
        own = [r for _, r, _ in returned if r.get("own_p23")]
        partner_strs = [p for r in own for p in r.get("partners") or []]
        tags = set(D.genomics_tags_for([name] + [r["title"][:120] for _, r, _ in returned] + partner_strs))
        if any(r.get("genetic") for r in own):
            tags.add("gene-therapy")
        if D.genomics_partner_hits(partner_strs, partners, cleaned):
            tags.add("genomics-partner")
        return bool(tags)

    def rule_b(self, t: date, partners: set[str], cleaned: str) -> list[str]:
        """Rule (b) evidence on day t: own interventional phase 2/3 trials first
        posted by t; current-record titles, interventions and sponsors."""
        own = [r for r in self.rows if r.get("own_p23") and (r.get("first_post") or "9999") <= t.isoformat()]
        why = []
        if any(r.get("genetic") for r in own):
            why.append("genetic-intervention")
        if D.genomics_tags_for([r["title"] for r in own]):
            why.append("title:" + ",".join(D.genomics_tags_for([r["title"] for r in own])))
        hits = D.genomics_partner_hits([p for r in own for p in r.get("partners") or []], partners, cleaned)
        if hits:
            why.append("partner:" + ",".join(hits))
        return why

    def days_to_catalyst(self, w: date, p: date) -> int | None:
        best = None
        for r in self.rows:
            if not r.get("own_p23"):
                continue
            s = self.state(r, w)
            if not s or s[0] not in ACTIVE:
                continue
            pcd = D._parse_loose_date(s[1])
            if pcd is None or pcd < p:
                continue
            k = (pcd - p).days
            best = k if best is None else min(best, k)
        return best


def posting_lag(pit: dict, ctg: dict) -> tuple[int, dict]:
    first_post = {r["nct"]: r.get("first_post") for e in ctg.values() for r in e.get("studies") or []}
    gaps = sorted((d(first_post[n]) - d(h["v0_date"])).days for n, h in pit.items()
                  if h.get("v0_date") and first_post.get(n))
    if not gaps:
        return 0, {"n": 0}
    q = lambda f: gaps[min(len(gaps) - 1, int(f * len(gaps)))]  # noqa: E731
    lag = max(0, q(0.95))
    return lag, {"n": len(gaps), "p50": q(0.5), "p95": q(0.95), "max": gaps[-1], "min": gaps[0],
                 "share_negative": sum(g < 0 for g in gaps) / len(gaps)}


# --- the measurement ------------------------------------------------------------------

def weekdays(a: date, b: date):
    t = a
    while t <= b:
        if t.weekday() < 5:
            yield t
        t += timedelta(days=1)


def main() -> None:
    pop = {p["symbol"]: p for p in json.loads(P.OUT_POP.read_text())}
    moves = json.loads(P.OUT_MOVES.read_text())
    ctg_all = json.loads((HERE / "ctgov.json").read_text())
    labels = json.loads((HERE / "labels.json").read_text())
    ctg, pit = ctg_all["names"], ctg_all["pit"]
    lag, lag_stats = posting_lag(pit, ctg)
    print(f"posting lag L = {lag}d {lag_stats}", flush=True)

    census = {r["symbol"]: r for r in P.census_today()}
    delisted = {r["symbol"]: r for r in P.delisted_in_window()}
    core = Core()
    series = {s: Series(s) for s in pop}
    names = {s: (census.get(s) or {}).get("screener_name") or (delisted.get(s) or {}).get("screener_name") or pop[s]["name"]
             for s in pop}
    cleaned = {s: D.clean_company_name(n) for s, n in names.items()}
    trials = {s: Trials(ctg[s], pit, lag) for s in pop if s in ctg and "error" not in ctg[s]}
    no_ctgov = sorted(s for s in pop if s in ctg and "error" in ctg[s])

    def listed(s: str, t: date) -> bool:
        fb = series[s].first_bar()
        dd = d(pop[s].get("delisted_date"))
        return fb is not None and fb <= t and (dd is None or t < dd)

    from collections import Counter

    # ---- funnel replay: movers lane (trading days) + catalyst lane (weekdays) ----
    queued: dict[str, tuple[date, str]] = {}
    for s, ser in series.items():
        for i in range(1, len(ser.bdates)):
            t = ser.bdates[i]
            if t < WARM or t > WIN1 or s in queued and queued[s][0] <= t:
                continue
            r = ser.close[i] / ser.close[i - 1] - 1.0
            cap = ser.cap(ser.bdates[i - 1])
            if abs(r) >= MOVER_MIN and cap is not None and cap >= CAP_MIN and s not in core.symbols(t):
                queued[s] = (t, "mover")
                break
    n_cat_checks = 0
    for t in weekdays(WARM, WIN1):
        bucket = t.toordinal() % ROTATION
        core_t = core.symbols(t)
        partners = core.partners(t)
        for s in pop:
            if s in core_t or (s in queued and queued[s][0] <= t) or s not in trials:
                continue
            if D.rotation_bucket(s, ROTATION) != bucket or not listed(s, t):
                continue
            cap = series[s].cap(t)
            if cap is None or cap < CAP_MIN:
                continue
            n_cat_checks += 1
            if trials[s].funnel_lane(names[s], t, partners, cleaned[s]):
                queued[s] = (t, "catalyst")

    def baseline_visible(s: str, p: date) -> bool:
        return s in core.symbols(p) or (s in queued and queued[s][0] <= p)

    # ---- Tier 1, weekly (Mondays) from the warm-up through today ----
    mondays = [t for t in (WARM + timedelta(days=i) for i in range((TODAY - WARM).days + 1)) if t.weekday() == 0]
    rule_a = {s: bool(D.genomics_tags_for([names[s]])) for s in pop}
    rule_c, rule_c_why = {}, {}
    for s in pop:
        prof_path = P.CACHE / "fmp" / "profile" / f"{s}.json"
        prof = (json.loads(prof_path.read_text()) or [None])[0] if prof_path.exists() else None
        desc = (prof or {}).get("description") or ""
        ind = (census.get(s) or {}).get("screener_industry") or ""
        why = (["industry"] if ind == LAB_INDUSTRY else []) + [f"desc:{t}" for t in D.genomics_tags_for([desc])]
        rule_c[s], rule_c_why[s] = bool(why), why
    hits_ab: dict[date, set[str]] = {}
    hits_abc: dict[date, set[str]] = {}
    why_b: dict[tuple[str, date], list[str]] = {}
    for w in mondays:
        partners = core.partners(w)
        ab, abc = set(), set()
        for s in pop:
            if not listed(s, w):
                continue
            cap = series[s].cap(w)
            if cap is None or cap < CAP_MIN:
                continue
            b = trials[s].rule_b(w, partners, cleaned[s]) if s in trials else []
            if b:
                why_b[(s, w)] = b
            if rule_a[s] or b:
                ab.add(s)
            if rule_a[s] or b or rule_c[s]:
                abc.add(s)
        hits_ab[w], hits_abc[w] = ab, abc

    def members(hits: dict[date, set[str]], w: date) -> set[str]:
        i = mondays.index(w)
        out = set().union(*(hits[x] for x in mondays[max(0, i - 3):i + 1]))
        return {s for s in out if listed(s, w)}

    mem_ab = {w: members(hits_ab, w) for w in mondays}
    mem_abc = {w: members(hits_abc, w) for w in mondays}

    def eval_day(p: date) -> date:
        return mondays[bisect.bisect_right(mondays, p) - 1]

    screen_cache: dict[tuple[str, date], dict[str, tuple[int, int | None]]] = {}

    def screen(kind: str, p: date) -> dict[str, tuple[int, int | None]]:
        """{symbol: (rank, days_to_catalyst)} for the Sector screen on day p."""
        key = (kind, p)
        if key not in screen_cache:
            w = eval_day(p)
            mem = (mem_ab if kind == "ab" else mem_abc)[w]
            rows = []
            for s in mem:
                k = trials[s].days_to_catalyst(w, p) if s in trials else None
                rows.append((k is None, k if k is not None else 0, -series[s].dollar_vol_20(p), s, k))
            rows.sort()
            screen_cache[key] = {r[3]: (i + 1, r[4]) for i, r in enumerate(rows)}
        return screen_cache[key]

    def surfaced(kind: str, s: str, p: date) -> tuple[bool, int | None, int | None]:
        sc = screen(kind, p)
        if s not in sc:
            return False, None, None
        rank, k = sc[s]
        return (rank <= TOP_N or (k is not None and k <= CAT_DAYS)), rank, k

    # ---- measurement 1 ----
    lab = {s: (labels.get(s) or {}).get("genomics") for s in pop}
    unlabelled_movers = sorted({m["symbol"] for m in moves if lab.get(m["symbol"]) is None})
    rows = []
    for m in moves:
        s, p = m["symbol"], d(m["prior_date"])
        if p < WARM:
            continue
        sa, ra, ka = surfaced("ab", s, p)
        sc_, rc, kc = surfaced("abc", s, p)
        w = eval_day(p)
        rows.append({**m, "genomics": lab.get(s), "baseline_visible": baseline_visible(s, p),
                     "baseline_via": ("core" if s in core.symbols(p) else queued[s][1]) if baseline_visible(s, p) else None,
                     "queued_on": queued[s][0].isoformat() if s in queued else None,
                     "tier1_ab": s in mem_ab[w], "tier1_abc": s in mem_abc[w],
                     "surfaced_ab": sa, "rank_ab": ra, "days_ab": ka,
                     "surfaced_abc": sc_, "rank_abc": rc, "days_abc": kc,
                     "rule_b_why": why_b.get((s, w)), "rule_c_why": rule_c_why.get(s)})
    prim = [r for r in rows if not r["flag_ma"]]
    g = [r for r in prim if r["genomics"]]
    g_inv = [r for r in g if not r["baseline_visible"]]
    c_only = [r for r in g_inv if r["tier1_abc"] and not r["tier1_ab"]]
    denom = [r for r in g_inv if r not in c_only]
    k1 = sum(r["surfaced_ab"] for r in denom)
    k_up = sum(r["surfaced_abc"] for r in g_inv)
    lo, hi = wilson(k1, len(denom))
    lo_u, hi_u = wilson(k_up, len(g_inv))

    # enrichment, by distinct names
    win_mondays = [w for w in mondays if WIN0 - timedelta(days=6) <= w <= WIN1]
    eligible_census = {s for s in pop if any(
        (c := series[s].cap(t)) is not None and c >= CAP_MIN for t in series[s].cdates if WIN0 <= t <= WIN1)}
    g_movers = {r["symbol"] for r in prim if r["genomics"]}

    def enrichment(kind: str) -> dict:
        mem = mem_ab if kind == "ab" else mem_abc
        ever = set().union(*(mem[w] for w in win_mondays))
        num = {r["symbol"] for r in prim if r["genomics"] and r[f"tier1_{kind}"]}
        a = len(num) / len(ever) if ever else 0.0
        b = len(g_movers) / len(eligible_census) if eligible_census else 0.0
        return {"tier1_names_ever": len(ever), "genomics_movers_in_tier1": len(num),
                "census_eligible": len(eligible_census), "genomics_movers_census": len(g_movers),
                "ratio": (a / b) if b else None}

    enr_ab, enr_abc = enrichment("ab"), enrichment("abc")

    # ---- measurement 2 (today's classification) ----
    w_today = TODAY
    core_today = core.symbols(TODAY)
    t1_today = mem_abc[w_today]
    non_core_t1 = sorted(t1_today - core_today)
    census_today_elig = sorted(s for s in pop if pop[s]["source"] != "delisted" and listed(s, TODAY)
                               and (series[s].cap(TODAY) or 0) >= CAP_MIN)
    not_t1 = sorted(set(census_today_elig) - t1_today)
    rng = random.Random(SEED)
    prec_sample = rng.sample(non_core_t1, min(50, len(non_core_t1)))
    rng = random.Random(SEED)
    miss_sample = rng.sample(not_t1, min(50, len(not_t1)))
    prec_k = sum(bool(lab.get(s)) for s in prec_sample)
    miss_k = sum(bool(lab.get(s)) for s in miss_sample)
    m2 = {
        "tier1_today": len(t1_today), "tier1_today_non_core": len(non_core_t1),
        "census_today_eligible": len(census_today_elig), "not_tier1": len(not_t1),
        "precision_sample": {"n": len(prec_sample), "genomics": prec_k, "share": prec_k / len(prec_sample) if prec_sample else None,
                             "wilson90": wilson(prec_k, len(prec_sample)),
                             "not_genomics": sorted(s for s in prec_sample if not lab.get(s))},
        "misses_sample": {"n": len(miss_sample), "genomics": miss_k, "share": miss_k / len(miss_sample) if miss_sample else None,
                          "wilson90": wilson(miss_k, len(miss_sample)),
                          "genomics_names": sorted(s for s in miss_sample if lab.get(s))},
        "full_population": {
            "precision": sum(bool(lab.get(s)) for s in non_core_t1) / len(non_core_t1) if non_core_t1 else None,
            "misses": sum(bool(lab.get(s)) for s in not_t1) / len(not_t1) if not_t1 else None,
            "missed_genomics_names": sorted(s for s in not_t1 if lab.get(s)),
            "tier1_non_genomics": sorted(s for s in non_core_t1 if lab.get(s) is False)},
        "samples": {"precision": prec_sample, "misses": miss_sample},
    }

    # ---- measurement 4 ----
    def known_miss(s: str, p: date) -> dict:
        w = eval_day(p)
        sa, ra, ka = surfaced("ab", s, p)
        sc_, rc, kc = surfaced("abc", s, p)
        return {"symbol": s, "day_before": p.isoformat(), "evaluation": w.isoformat(),
                "cap": series[s].cap(p), "rule_a": rule_a.get(s), "rule_b": why_b.get((s, w)) or [],
                "rule_c": rule_c_why.get(s), "in_tier1_ab": s in mem_ab[w], "in_tier1_abc": s in mem_abc[w],
                "rank_ab": ra, "days_to_catalyst_ab": ka, "surfaced_ab": sa,
                "rank_abc": rc, "days_to_catalyst_abc": kc, "surfaced_abc": sc_,
                "core": s in core.symbols(p), "baseline_visible": baseline_visible(s, p)}

    m4 = []
    if "MRNA" in pop:
        m4.append(known_miss("MRNA", date(2026, 8, 18)))
    if "VRTX" in series and series["VRTX"].bdates:
        ser = series["VRTX"]
        best = max((abs(ser.close[i] / ser.close[i - 1] - 1), ser.bdates[i - 1], ser.bdates[i])
                   for i in range(1, len(ser.bdates)) if WIN0 <= ser.bdates[i] <= WIN1)
        m4.append({**known_miss("VRTX", best[1]), "largest_move": round(best[0], 4), "move_day": best[2].isoformat()})

    # ---- decision rule (frozen) ----
    share = k1 / len(denom) if denom else None
    m1_pass = len(denom) >= 15 and share is not None and share >= 0.5 and (enr_ab["ratio"] or 0) > 2
    m2_pass = (m2["precision_sample"]["share"] or 0) >= 0.8 and (m2["misses_sample"]["share"] if m2["misses_sample"]["share"] is not None else 1) <= 0.10
    if len(denom) < 15:
        verdict = "INCONCLUSIVE"
    elif m1_pass and m2_pass:
        verdict = "BUILD (subject to measurement 3)"
    else:
        verdict = "DO NOT BUILD"

    res = {
        "inputs": {"population": len(pop), "moves_all": len(moves), "moves_ma_flagged": sum(m["flag_ma"] for m in moves),
                   "labelled": sum(v is not None for v in lab.values()), "unlabelled_movers": unlabelled_movers,
                   "no_ctgov": no_ctgov, "posting_lag_days": lag, "posting_lag_stats": lag_stats,
                   "core_versions": [(t.isoformat() if t != date.min else "window start", len(e)) for t, e in core.hist],
                   "prod_export_used": (HERE / "prod_export.json").exists(),
                   "funnel_catalyst_checks": n_cat_checks,
                   "queued_by_lane": dict(Counter(v[1] for v in queued.values())),
                   "pit_fallback_to_current": sum(t.fallbacks for t in trials.values())},
        "m1": {"genomics_moves": len(g), "genomics_moves_baseline_visible": len(g) - len(g_inv),
               "invisible_to_baseline": len(g_inv), "rule_c_only_removed": len(c_only),
               "denominator": len(denom), "surfaced": k1, "share": share, "wilson90": (lo, hi),
               "upper_bound_with_rule_c": {"n": len(g_inv), "surfaced": k_up,
                                           "share": k_up / len(g_inv) if g_inv else None, "wilson90": (lo_u, hi_u)},
               "enrichment_ab": enr_ab, "enrichment_abc_upper": enr_abc,
               "ma_moves_genomics": sum(1 for r in rows if r["flag_ma"] and r["genomics"])},
        "m2": m2, "m4": m4,
        "decision": {"m1_pass": m1_pass, "m2_pass": m2_pass, "verdict": verdict,
                     "m3": "quota half met on Casey's statement (amendment 2); see m3.json for the dry run"},
        "tier1_size_by_week": [{"monday": w.isoformat(), "ab": len(mem_ab[w]), "abc": len(mem_abc[w])} for w in mondays],
        "baseline_visible_by_week": [{"monday": w.isoformat(),
                                      "core": len(core.symbols(w)),
                                      "queued": sum(1 for v in queued.values() if v[0] <= w)} for w in mondays],
        "moves": rows,
    }
    OUT.write_text(json.dumps(res, indent=1, default=str))
    charts(res)
    print(json.dumps({k: res[k] for k in ("inputs", "m1", "decision")}, indent=1, default=str)[:6000])
    print("M2", json.dumps({k: v for k, v in m2.items() if k != "samples"}, default=str)[:3000])
    print("M4", json.dumps(m4, default=str))


def charts(res: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    CHARTS.mkdir(exist_ok=True)

    # 1. every measured genomics move: visible to the baseline, surfaced only by Tier 1, or missed by both
    rows = [r for r in res["moves"] if not r["flag_ma"] and r["genomics"]]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    groups = [("baseline already saw it", lambda r: r["baseline_visible"], "#9aa4b1", "o"),
              ("unseen by baseline, Tier 1 surfaced (a+b)", lambda r: not r["baseline_visible"] and r["surfaced_ab"], "#1a9850", "^"),
              ("unseen by baseline, Tier 1 missed", lambda r: not r["baseline_visible"] and not r["surfaced_ab"], "#d73027", "x")]
    for lab_, f, col, mk in groups:
        sel = [r for r in rows if f(r)]
        ax.scatter([date.fromisoformat(r["date"]) for r in sel], [100 * r["ret"] for r in sel],
                   s=22, c=col, marker=mk, label=f"{lab_} ({len(sel)})", alpha=0.85)
    ax.axhline(0, color="#555", lw=0.6)
    ax.set_ylabel("one-day move, %")
    ax.set_title("Genomics-labelled 20% moves, 2025-10 to 2026-09 (M&A days excluded)")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(CHARTS / "m1_moves.png", dpi=130)
    plt.close(fig)

    # 2. the funnel: all moves -> genomics -> unseen -> surfaced
    m1 = res["m1"]
    stages = [("measured moves\n(no M&A)", sum(1 for r in res["moves"] if not r["flag_ma"])),
              ("genomics-\nlabelled", m1["genomics_moves"]), ("unseen by\nbaseline", m1["invisible_to_baseline"]),
              ("primary\ndenominator", m1["denominator"]), ("Tier 1\nsurfaced", m1["surfaced"])]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar([s[0] for s in stages], [s[1] for s in stages], color=["#9aa4b1", "#4575b4", "#fdae61", "#f46d43", "#1a9850"])
    for i, s in enumerate(stages):
        ax.text(i, s[1], str(s[1]), ha="center", va="bottom")
    ax.axhline(15, color="#d73027", ls="--", lw=1)
    ax.text(len(stages) - 0.5, 15, " 15 = floor", color="#d73027", va="bottom", ha="right", fontsize=8)
    ax.set_title("Measurement 1: from moves to Tier 1's recall")
    fig.tight_layout()
    fig.savefig(CHARTS / "m1_funnel.png", dpi=130)
    plt.close(fig)

    # 3. sizes over time: Tier 1 vs what the baseline could see
    tb = res["tier1_size_by_week"]
    bv = res["baseline_visible_by_week"]
    xs = [date.fromisoformat(x["monday"]) for x in tb]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(xs, [x["ab"] for x in tb], label="Tier 1, rules a+b", color="#1a9850")
    ax.plot(xs, [x["abc"] for x in tb], label="Tier 1, rules a+b+c (look-ahead)", color="#1a9850", ls="--")
    ax.plot(xs, [x["core"] + x["queued"] for x in bv], label="baseline: core + funnel queue", color="#4575b4")
    ax.axvline(WIN0, color="#888", lw=0.8)
    ax.set_ylabel("names")
    ax.set_title("What each side was watching, week by week (window starts at the grey line)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(CHARTS / "sizes.png", dpi=130)
    plt.close(fig)

    # 4. measurement 2 with Wilson intervals against the gates
    m2 = res["m2"]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for i, (key, gate, better) in enumerate([("precision_sample", 0.8, "above"), ("misses_sample", 0.10, "below")]):
        x = m2[key]
        if x["share"] is None:
            continue
        lo, hi = x["wilson90"]
        ax.errorbar([i], [x["share"]], yerr=[[x["share"] - lo], [hi - x["share"]]], fmt="o", capsize=6, color="#4575b4")
        ax.hlines(gate, i - 0.3, i + 0.3, colors="#d73027", linestyles="--")
        ax.text(i + 0.32, gate, f"gate ({better})", color="#d73027", fontsize=8, va="center")
        ax.text(i, x["share"], f"  {x['genomics']}/{x['n']}", va="bottom")
    ax.set_xticks([0, 1], ["precision\n(non-core Tier 1)", "misses\n(census not in Tier 1)"])
    ax.set_ylim(0, 1.05)
    ax.set_title("Measurement 2: random-50 samples, Wilson 90%")
    fig.tight_layout()
    fig.savefig(CHARTS / "m2.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
