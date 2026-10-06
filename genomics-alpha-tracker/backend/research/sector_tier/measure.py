"""Sector-tier measurements, stage 4: Tier 1 point in time vs the shipped baseline.

Pre-registration: docs/DESIGN_SECTOR_TIER.md (rev 3, amendments 1-7). Every
choice below is the one recorded there; this file adds none. Inputs:

  population.json, moves.json  (stage 1: FMP)
  ctgov.json                   (stage 2: CT.gov current records + record history)
  labels.json                  (stage 3: two blind labellers + adjudicator)
  prod_export.json             (optional: production `security` + `universe_candidate`)
  the FMP cache (bars, caps, full profile descriptions) and git history of
  config/watchlist.yaml (the core on each day)

The pipeline runs with rule (b)'s strict own-trial titles; the pre-registered
title check (amendment 7) then decides whether a second run with the funnel's
title behaviour is the one the verdict comes from. Both runs are written to
results.json; the charts show the run the verdict comes from.

    cd genomics-alpha-tracker/backend && python -m research.sector_tier.measure
"""
from __future__ import annotations

import bisect
import json
import math
import random
import subprocess
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import yaml

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent.parent
REPO = BACKEND.parent.parent
sys.path.insert(0, str(BACKEND))

from app.ingestion import discovery as D  # noqa: E402
from research.sector_tier import build_ctgov as C  # noqa: E402
from research.sector_tier import build_population as P  # noqa: E402

OUT = HERE / "results.json"
CHARTS = HERE / "charts"
WIN0, WIN1 = P.WINDOW
WARM = date(2025, 8, 1)
PIT_FROM = date.fromisoformat(C.PIT_FROM)
TODAY = date(2026, 10, 5)
LIVE_FROM = date(2026, 9, 8)
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
    return date.fromisoformat(str(s)[:10]) if s else None


def wilson(k: int, n: int, z: float = Z90) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


# --- the core on each day -----------------------------------------------------------

def _git_versions() -> list[tuple[date, list[SimpleNamespace]]]:
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
    return out


def load_export() -> dict:
    path = HERE / "prod_export.json"
    return json.loads(path.read_text()) if path.exists() else {}


class Core:
    """Git versions of the watchlist, plus production additions each dated by
    its own created_at (never back-dated into an earlier version)."""

    def __init__(self, export: dict):
        self.hist = _git_versions()
        self.dates = [h[0] for h in self.hist]
        git_syms = {e.symbol for _, ents in self.hist for e in ents}
        self.promoted = {str(r["symbol"]).upper() for r in export.get("universe_candidate", [])
                         if r.get("status") == "promoted"}
        self.adds: list[tuple[date, SimpleNamespace]] = []
        for r in export.get("security", []):
            when = d(str(r.get("created_at") or ""))
            sym = str(r.get("symbol") or "").upper()
            if not when or not sym or not r.get("active", True) or sym in git_syms:
                continue
            sub = r.get("subsector")
            sub = json.loads(sub) if isinstance(sub, str) and sub.startswith("[") else (sub or [])
            self.adds.append((when, SimpleNamespace(symbol=sym, name=r.get("name", ""), subsector=sub,
                                                    active=True, ctgov_names=[])))
        self.adds.sort(key=lambda x: x[0])
        self.add_dates = [a[0] for a in self.adds]
        self._partner_cache: dict[tuple[int, int], set[str]] = {}

    def _key(self, t: date) -> tuple[int, int]:
        return bisect.bisect_right(self.dates, t) - 1, bisect.bisect_right(self.add_dates, t)

    def entries(self, t: date) -> list[SimpleNamespace]:
        i, k = self._key(t)
        return self.hist[i][1] + [a[1] for a in self.adds[:k]]

    def symbols(self, t: date) -> set[str]:
        return {e.symbol for e in self.entries(t)}

    def partners(self, t: date) -> set[str]:
        key = self._key(t)
        if key not in self._partner_cache:
            # Tier 2's hand-curated names only: discovery promotions never seed partners.
            self._partner_cache[key] = D.universe_partner_names(self.entries(t), MODALITIES, self.promoted)
        return self._partner_cache[key]


# --- prices, caps, listing --------------------------------------------------------

class Series:
    def __init__(self, sym: str):
        bp, cp = P.CACHE / "fmp" / "bars" / f"{sym}.json", P.CACHE / "fmp" / "mcap" / f"{sym}.json"
        bars = json.loads(bp.read_text()) if bp.exists() else []
        bars = sorted((b for b in bars or [] if b.get("adjClose")), key=lambda b: b["date"])
        self.bdates = [d(b["date"]) for b in bars]
        self.close = [float(b["adjClose"]) for b in bars]
        self.dvol = [float(b["adjClose"]) * float(b.get("volume") or 0) for b in bars]
        caps = json.loads(cp.read_text()) if cp.exists() else []
        caps = sorted((c for c in caps or [] if c.get("marketCap")), key=lambda c: c["date"])
        self.cdates = [d(c["date"]) for c in caps]
        self.caps = [float(c["marketCap"]) for c in caps]

    def cap(self, t: date) -> float | None:
        """Amendment 7: FMP's cap on the latest date on or before t (listing is checked separately)."""
        i = bisect.bisect_right(self.cdates, t) - 1
        return self.caps[i] if i >= 0 else None

    def first_bar(self) -> date | None:
        return self.bdates[0] if self.bdates else None

    def dollar_vol_20(self, t: date) -> float:
        i = bisect.bisect_right(self.bdates, t)
        w = self.dvol[max(0, i - 20):i]
        return sum(w) / len(w) if w else 0.0


# --- CT.gov point in time -----------------------------------------------------------

class Trials:
    """A name's studies, each shown as CT.gov showed it on a given day."""

    def __init__(self, entry: dict, pit: dict, lag: int):
        self.rows = entry.get("studies") or []
        self.timelines: dict[str, tuple] = {}
        self.no_timeline = Counter()          # PIT-relevant studies standing in with the current record
        for r in self.rows:
            h = pit.get(r["nct"])
            if not h or not h.get("versions") or not h.get("status_list"):
                if C.needs_pit(r):
                    self.no_timeline["missing" if not h else "empty"] += 1
                continue
            # date-only stable sorts: the lists arrive in version order, so the last
            # version of a date stands (counter-agent DA-3)
            vs = sorted(((d(x["from"]), x["pcd"], x["phases"], x.get("status")) for x in h["versions"] if x.get("from")),
                        key=lambda x: x[0])
            st = []
            for x in sorted((x for x in h["status_list"] if x.get("from")), key=lambda x: x["from"]):
                stt = x.get("status")
                if not stt:   # list entry without a status: the fetched version in force says it
                    k = bisect.bisect_right([v[0] for v in vs], d(x["from"])) - 1
                    stt = vs[k][3] if k >= 0 else None
                st.append((d(x["from"]), stt))
            # visible from version date + L; the version in force on PIT_FROM was public before the span
            sv = [(x[0] if x[0] <= PIT_FROM else x[0] + timedelta(days=lag)) for x in st]
            vv = [(x[0] if x[0] <= PIT_FROM else x[0] + timedelta(days=lag)) for x in vs]
            self.timelines[r["nct"]] = (sv, st, vv, vs)

    def state(self, r: dict, t: date):
        """(status, pcd_raw, phases) as shown on day t, or None if not shown yet."""
        fp = d(r.get("first_post"))
        if fp and fp > t:
            return None
        tl = self.timelines.get(r["nct"])
        if tl is None:
            return r["status"], r["pcd"], r["phases"]
        sv, st, vv, vs = tl
        i, j = bisect.bisect_right(sv, t) - 1, bisect.bisect_right(vv, t) - 1
        if i < 0 or j < 0:
            return None
        return st[i][1], vs[j][1], vs[j][2] or r["phases"]

    def page(self, t: date) -> list[tuple[date, dict, list]]:
        """The funnel's CT.gov page on day t: active, PCD on or after t, 50 nearest."""
        out = []
        for r in self.rows:
            s = self.state(r, t)
            if not s or s[0] not in ACTIVE:
                continue
            pcd = D._parse_loose_date(s[1])
            if pcd is None or pcd < t:
                continue
            out.append((pcd, r, s[2]))
        out.sort(key=lambda x: x[0])
        return out[:PAGE]

    def funnel_lane(self, name: str, t: date, partners: set[str], cleaned: str) -> bool:
        """The shipped catalyst lane's decision for this name on day t."""
        returned = self.page(t)
        if not returned:
            return False
        p3 = [pcd for pcd, _, ph in returned if "PHASE3" in "/".join(ph)]
        if p3 and (min(p3) - t).days <= HORIZON:
            return True
        if not any(("PHASE3" in "/".join(ph) or "PHASE2" in "/".join(ph)) for _, _, ph in returned):
            return False
        own = [r for _, r, _ in returned if r.get("own_p23")]
        partner_strs = [p for r in own for p in r.get("partners") or []]
        tags = set(D.genomics_tags_for([name] + [r["title"][:120] for _, r, _ in returned] + partner_strs))
        if any(r.get("genetic") for r in own):
            tags.add("gene-therapy")
        if D.genomics_partner_hits(partner_strs, partners, cleaned):
            tags.add("genomics-partner")
        return bool(tags)

    def rule_b(self, t: date, partners: set[str], cleaned: str, title_mode: str = "own") -> list[str]:
        """Rule (b) evidence on day t: own interventional phase 2/3 trials first
        posted by t (current-record titles, interventions, sponsors). With
        title_mode='funnel' the title half reads the funnel's page instead."""
        own = [r for r in self.rows if r.get("own_p23") and (r.get("first_post") or "9999") <= t.isoformat()]
        why = []
        if any(r.get("genetic") for r in own):
            why.append("genetic-intervention")
        titles = [r["title"] for r in own] if title_mode == "own" else [r["title"][:120] for _, r, _ in self.page(t)]
        tt = D.genomics_tags_for(titles)
        if tt:
            why.append("title:" + ",".join(tt))
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
    assert lag < (WIN0 - WARM).days, f"posting lag {lag}d swallows the warm-up"
    return lag, {"n": len(gaps), "p50": q(0.5), "p95": q(0.95), "max": gaps[-1], "min": gaps[0],
                 "share_negative": sum(g < 0 for g in gaps) / len(gaps)}


def weekdays(a: date, b: date):
    t = a
    while t <= b:
        if t.weekday() < 5:
            yield t
        t += timedelta(days=1)


# --- shared world: data, baseline replay -----------------------------------------------

class World:
    def __init__(self):
        self.pop = {p["symbol"]: p for p in json.loads(P.OUT_POP.read_text())}
        moves = json.loads(P.OUT_MOVES.read_text())
        # price vs cap disagree by > 50%: an adjustment break, not a move (stage 1 flag)
        self.artifacts = [m for m in moves if m.get("flag_artifact")]
        self.moves = [m for m in moves if not m.get("flag_artifact")]
        # M&A hand check (two blind reviewers + adjudicator) overrides stage 1's
        # automatic flag on every move it covers (all genomics-labelled moves).
        review_path = HERE / "ma_review.json"
        self.ma_review = json.loads(review_path.read_text()) if review_path.exists() else {}
        self.ma_overrides = []
        for m in self.moves:
            r = self.ma_review.get(f"{m['symbol']}|{m['date']}")
            if r and r.get("ma") is not None:
                if bool(r["ma"]) != bool(m["flag_ma"]):
                    self.ma_overrides.append((m["symbol"], m["date"], m["flag_ma"], r["ma"]))
                m["flag_ma_auto"], m["flag_ma"] = m["flag_ma"], bool(r["ma"])
        ctg_all = json.loads((HERE / "ctgov.json").read_text())
        self.ctg_counters = ctg_all.get("counters", {})
        labels = json.loads((HERE / "labels.json").read_text())
        ctg, pit = ctg_all["names"], ctg_all["pit"]
        self.lag, self.lag_stats = posting_lag(pit, ctg)
        print(f"posting lag L = {self.lag}d {self.lag_stats}", flush=True)
        self.export = load_export()
        census = {r["symbol"]: r for r in P.census_today()}
        delisted = {r["symbol"]: r for r in P.delisted_in_window()}
        self.census = census
        self.core = Core(self.export)
        self.series = {s: Series(s) for s in self.pop}
        self.names = {s: (census.get(s) or {}).get("screener_name") or (delisted.get(s) or {}).get("screener_name")
                      or self.pop[s]["name"] for s in self.pop}
        self.cleaned = {s: D.clean_company_name(n) for s, n in self.names.items()}
        self.trials = {s: Trials(ctg[s], pit, self.lag) for s in self.pop if s in ctg and "error" not in ctg[s]}
        self.no_ctgov = sorted(s for s in self.pop if s in ctg and "error" in ctg[s])
        self.ctg_dropped_by_cap = sum(e.get("n_pit_dropped_by_cap", 0) for e in ctg.values())
        self.eligible = set(ctg)                       # stage 2's eligible set = the labelled set
        self.labels = labels
        self.lab = {s: (labels.get(s) or {}).get("genomics") for s in self.pop}
        self.cell_therapy = {s for s, v in labels.items() if v.get("genomics") and any(
            (x or {}).get("modality") == "cell-therapy" and (x or {}).get("genomics")
            for x in (v.get("a"), v.get("b"), v.get("adj")))}
        missing = sorted(s for s in self.eligible if self.lab.get(s) is None)
        if missing:
            raise SystemExit(f"INVALID: {len(missing)} eligible names have no label: {missing[:20]}")

        # rule (a) and (c) are static
        self.rule_a = {s: bool(D.genomics_tags_for([self.names[s]])) for s in self.pop}
        self.rule_c_why = {}
        for s in self.pop:
            prof_path = P.CACHE / "fmp" / "profile" / f"{s}.json"
            prof = (json.loads(prof_path.read_text()) or [None])[0] if prof_path.exists() else None
            desc = (prof or {}).get("description") or ""
            ind = (census.get(s) or {}).get("screener_industry") or ""
            self.rule_c_why[s] = (["industry"] if ind == LAB_INDUSTRY else []) + \
                                 [f"desc:{t}" for t in D.genomics_tags_for([desc])]
        self.mondays = [t for t in (WARM + timedelta(days=i) for i in range((TODAY - WARM).days + 1))
                        if t.weekday() == 0]
        self._replay()

    def listed(self, s: str, t: date) -> bool:
        fb = self.series[s].first_bar()
        dd = d(self.pop[s].get("delisted_date"))
        return fb is not None and fb <= t and (dd is None or t < dd)

    def _replay(self, start: date = WARM) -> None:
        """Amendment 6: the shipped funnel's two lanes on every weekday from the warm-up."""
        queued: dict[str, tuple[date, str]] = {}
        for s, ser in self.series.items():
            for i in range(1, len(ser.bdates)):
                t = ser.bdates[i]
                if t < start or t > WIN1:
                    continue
                r = ser.close[i] / ser.close[i - 1] - 1.0
                cap = ser.cap(ser.bdates[i - 1])
                if abs(r) >= MOVER_MIN and cap is not None and cap >= CAP_MIN and s not in self.core.symbols(t):
                    queued[s] = (t, "mover")
                    break
        self.n_cat_checks = 0
        for t in weekdays(start, WIN1):
            bucket = t.toordinal() % ROTATION
            core_t = self.core.symbols(t)
            partners = self.core.partners(t)
            for s in self.pop:
                if s in core_t or (s in queued and queued[s][0] <= t) or s not in self.trials:
                    continue
                if D.rotation_bucket(s, ROTATION) != bucket or not self.listed(s, t):
                    continue
                cap = self.series[s].cap(t)
                if cap is None or cap < CAP_MIN:
                    continue
                self.n_cat_checks += 1
                if self.trials[s].funnel_lane(self.names[s], t, partners, self.cleaned[s]):
                    queued[s] = (t, "catalyst")
        self.queued = queued

    def baseline_visible(self, s: str, p: date) -> bool:
        return s in self.core.symbols(p) or (s in self.queued and self.queued[s][0] <= p)

    def cross_check(self) -> dict | None:
        """Amendment 6: the replay vs the live queue, 2026-09-08 to 2026-09-30 (export
        only). The live funnel started that day with an EMPTY queue, so the check
        replays from an empty queue too."""
        cands = self.export.get("universe_candidate")
        if not cands:
            return None
        saved = self.queued
        self._replay(start=LIVE_FROM)
        cold, self.queued = self.queued, saved
        live = {str(r["symbol"]).upper(): d(str(r.get("first_seen"))) for r in cands if r.get("first_seen")}
        live = {s: t for s, t in live.items() if t and LIVE_FROM <= t <= WIN1}
        rep = {s: v[0] for s, v in cold.items()}
        both = set(live) & set(rep)
        return {"live_new_in_span": len(live), "replay_new_in_span": len(rep), "both": len(both),
                "live_only": sorted(set(live) - set(rep)), "live_only_outside_population": sorted(set(live) - set(self.pop)),
                "replay_only": sorted(set(rep) - set(live)),
                "date_offsets_days": sorted((rep[s] - live[s]).days for s in both)}


# --- one run of the measurements (title mode for rule (b)) ------------------------------

def run(W: World, title_mode: str) -> dict:
    pop, series, trials, core, mondays = W.pop, W.series, W.trials, W.core, W.mondays
    hits_ab: dict[date, set[str]] = {}
    hits_abc: dict[date, set[str]] = {}
    why_b: dict[tuple[str, date], list[str]] = {}
    for w in mondays:
        partners = core.partners(w)
        ab, abc = set(), set()
        for s in pop:
            if not W.listed(s, w):
                continue
            cap = series[s].cap(w)
            if cap is None or cap < CAP_MIN:
                continue
            b = trials[s].rule_b(w, partners, W.cleaned[s], title_mode) if s in trials else []
            if b:
                why_b[(s, w)] = b
            if W.rule_a[s] or b:
                ab.add(s)
            if W.rule_a[s] or b or W.rule_c_why[s]:
                abc.add(s)
        hits_ab[w], hits_abc[w] = ab, abc

    def members(hits: dict[date, set[str]], i: int) -> set[str]:
        out = set().union(*(hits[x] for x in mondays[max(0, i - 3):i + 1]))
        return {s for s in out if W.listed(s, mondays[i])}

    mem_ab = {w: members(hits_ab, i) for i, w in enumerate(mondays)}
    mem_abc = {w: members(hits_abc, i) for i, w in enumerate(mondays)}

    def eval_day(p: date) -> date:
        return mondays[bisect.bisect_right(mondays, p) - 1]

    screen_cache: dict[tuple[str, date], dict[str, tuple[int, int | None]]] = {}

    def screen(kind: str, p: date) -> dict[str, tuple[int, int | None]]:
        """{symbol: (rank, days_to_catalyst)} for the Sector screen on day p (frozen sort)."""
        key = (kind, p)
        if key not in screen_cache:
            w = eval_day(p)
            rows = []
            for s in (mem_ab if kind == "ab" else mem_abc)[w]:
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
    rows = []
    for m in W.moves:
        s, p = m["symbol"], d(m["prior_date"])
        sa, ra, ka = surfaced("ab", s, p)
        sc_, rc, kc = surfaced("abc", s, p)
        w = eval_day(p)
        vis = W.baseline_visible(s, p)
        rows.append({**m, "genomics": W.lab.get(s), "baseline_visible": vis,
                     "baseline_via": ("core" if s in core.symbols(p) else W.queued[s][1]) if vis else None,
                     "queued_on": W.queued[s][0].isoformat() if s in W.queued else None,
                     "tier1_ab": s in mem_ab[w], "tier1_abc": s in mem_abc[w],
                     "surfaced_ab": sa, "rank_ab": ra, "days_ab": ka,
                     "surfaced_abc": sc_, "rank_abc": rc, "days_abc": kc,
                     "rule_a": W.rule_a.get(s), "rule_b_why": why_b.get((s, w)), "rule_c_why": W.rule_c_why.get(s),
                     "pit_no_timeline": dict(trials[s].no_timeline) if s in trials else None})
    unlabelled = sorted({r["symbol"] for r in rows if r["genomics"] is None})
    if unlabelled:
        raise SystemExit(f"INVALID: movers without a label: {unlabelled[:20]}")
    prim = [r for r in rows if not r["flag_ma"]]
    g = [r for r in prim if r["genomics"]]
    g_inv = [r for r in g if not r["baseline_visible"]]
    for r in g_inv:
        r["c_only"] = r["tier1_abc"] and not r["tier1_ab"]
    denom = [r for r in g_inv if not r["c_only"]]
    k1 = sum(r["surfaced_ab"] for r in denom)
    k_c = sum(r["surfaced_abc"] for r in g_inv)
    k_any = sum(r["surfaced_ab"] or r["surfaced_abc"] for r in g_inv)

    # enrichment, by distinct names
    win_mondays = [w for w in mondays if WIN0 - timedelta(days=6) <= w <= WIN1]
    eligible_census = {s for s in pop if any(c >= CAP_MIN and WIN0 <= t <= WIN1 and W.listed(s, t)
                                             for t, c in zip(series[s].cdates, series[s].caps))}
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

    # ---- measurement 2 (today's classification, all rules) ----
    core_today = core.symbols(TODAY)
    t1_today = mem_abc[TODAY]
    non_core_t1 = sorted(t1_today - core_today)
    census_today_elig = sorted(s for s in pop if pop[s]["source"] != "delisted" and W.listed(s, TODAY)
                               and (series[s].cap(TODAY) or 0) >= CAP_MIN)
    not_t1 = sorted(set(census_today_elig) - t1_today)
    prec_sample = random.Random(SEED).sample(non_core_t1, min(50, len(non_core_t1)))
    miss_sample = random.Random(SEED).sample(not_t1, min(50, len(not_t1)))
    for s in prec_sample + miss_sample + non_core_t1 + not_t1:
        if W.lab.get(s) is None:
            raise SystemExit(f"INVALID: M2 frame name without a label: {s}")
    prec_k = sum(W.lab[s] for s in prec_sample)
    miss_k = sum(W.lab[s] for s in miss_sample)
    m2 = {
        "tier1_today": len(t1_today), "tier1_today_non_core": len(non_core_t1),
        "census_today_eligible": len(census_today_elig), "not_tier1": len(not_t1),
        "precision_sample": {"n": len(prec_sample), "genomics": prec_k,
                             "share": prec_k / len(prec_sample) if prec_sample else None,
                             "wilson90": wilson(prec_k, len(prec_sample)),
                             "not_genomics": sorted(s for s in prec_sample if not W.lab[s])},
        "misses_sample": {"n": len(miss_sample), "genomics": miss_k,
                          "share": miss_k / len(miss_sample) if miss_sample else None,
                          "wilson90": wilson(miss_k, len(miss_sample)),
                          "genomics_names": sorted(s for s in miss_sample if W.lab[s])},
        "full_population": {
            "precision": sum(W.lab[s] for s in non_core_t1) / len(non_core_t1) if non_core_t1 else None,
            "misses": sum(W.lab[s] for s in not_t1) / len(not_t1) if not_t1 else None,
            "missed_genomics_names": sorted(s for s in not_t1 if W.lab[s]),
            "tier1_non_genomics": sorted(s for s in non_core_t1 if not W.lab[s])},
        "samples": {"precision": prec_sample, "misses": miss_sample},
        "tier1_today_names": sorted(t1_today),
    }

    # ---- measurement 4 ----
    def known_miss(s: str, p: date) -> dict:
        w = eval_day(p)
        sa, ra, ka = surfaced("ab", s, p)
        sc_, rc, kc = surfaced("abc", s, p)
        return {"symbol": s, "day_before": p.isoformat(), "evaluation": w.isoformat(),
                "cap": series[s].cap(p), "rule_a": W.rule_a.get(s), "rule_b": why_b.get((s, w)) or [],
                "rule_c": W.rule_c_why.get(s), "in_tier1_ab": s in mem_ab[w], "in_tier1_abc": s in mem_abc[w],
                "rank_ab": ra, "days_to_catalyst_ab": ka, "surfaced_ab": sa,
                "rank_abc": rc, "days_to_catalyst_abc": kc, "surfaced_abc": sc_,
                "core": s in core.symbols(p), "baseline_visible": W.baseline_visible(s, p),
                "queued_on": W.queued[s][0].isoformat() if s in W.queued else None}

    m4 = []
    if "MRNA" in pop:
        m4.append(known_miss("MRNA", date(2026, 8, 18)))
    if "VRTX" in series and series["VRTX"].bdates:
        ser = series["VRTX"]
        best = max((abs(ser.close[i] / ser.close[i - 1] - 1), ser.bdates[i - 1], ser.bdates[i])
                   for i in range(1, len(ser.bdates)) if WIN0 <= ser.bdates[i] <= WIN1)
        m4.append({**known_miss("VRTX", best[1]), "largest_move": round(best[0], 4), "move_day": best[2].isoformat()})

    # ---- decision rule (frozen); the floor applies to the primary denominator ----
    share = k1 / len(denom) if denom else None
    m1_pass = len(denom) >= 15 and share is not None and share >= 0.5 and (enr_ab["ratio"] or 0) > 2
    ps, ms = m2["precision_sample"]["share"], m2["misses_sample"]["share"]
    m2_pass = ps is not None and ps >= 0.8 and ms is not None and ms <= 0.10
    verdict = ("INCONCLUSIVE" if len(denom) < 15 else
               "BUILD (measurement 3: quota taken as met, amendment 2)" if (m1_pass and m2_pass) else "DO NOT BUILD")

    sizes = [{"monday": w.isoformat(), "ab": len(mem_ab[w]), "abc": len(mem_abc[w]),
              "baseline": len(core.symbols(w) | {s for s, v in W.queued.items() if v[0] <= w})} for w in mondays]
    return {
        "title_mode": title_mode,
        "m1": {"genomics_moves": len(g), "genomics_moves_baseline_visible": len(g) - len(g_inv),
               "invisible_to_baseline": len(g_inv), "rule_c_only_removed": len(g_inv) - len(denom),
               "denominator": len(denom), "surfaced": k1, "share": share, "wilson90": wilson(k1, len(denom)),
               "with_rule_c_lookahead": {"n": len(g_inv), "surfaced": k_c, "share": k_c / len(g_inv) if g_inv else None,
                                         "wilson90": wilson(k_c, len(g_inv))},
               "per_move_union_bound": {"n": len(g_inv), "surfaced": k_any,
                                        "share": k_any / len(g_inv) if g_inv else None},
               "enrichment_ab": enr_ab, "enrichment_with_rule_c_lookahead": enr_abc,
               "ma_moves": sum(1 for r in rows if r["flag_ma"]),
               "ma_moves_genomics": sum(1 for r in rows if r["flag_ma"] and r["genomics"])},
        "m2": m2, "m4": m4,
        "decision": {"m1_pass": m1_pass, "m2_pass": m2_pass, "verdict": verdict,
                     "floor_counts": {"primary_denominator": len(denom), "all_invisible": len(g_inv)}},
        "sizes_by_week": sizes,
        "moves": rows,
        "_why_b_today": {s: why_b.get((s, TODAY)) for s in t1_today},
    }


def title_check(W: World, strict: dict) -> dict:
    """Amendment 7: fires if a misses-sample name labelled genomics with modality
    cell therapy would be caught by the funnel's title behaviour on 2026-10-05."""
    partners = W.core.partners(TODAY)
    out = []
    for s in strict["m2"]["misses_sample"]["genomics_names"]:
        if s not in W.cell_therapy or s not in W.trials:
            continue
        why = W.trials[s].rule_b(TODAY, partners, W.cleaned[s], "funnel")
        out.append({"symbol": s, "funnel_title_rule_b": why, "caught": any(x.startswith("title:") for x in why)})
    return {"cell_therapy_misses": out, "fires": any(x["caught"] for x in out)}


def main() -> None:
    W = World()
    strict = run(W, "own")
    check = title_check(W, strict)
    final = run(W, "funnel") if check["fires"] else strict
    res = {
        "inputs": {"population": len(W.pop), "eligible_labelled": len(W.eligible), "moves_all": len(W.moves),
                   "moves_ma_flagged": sum(m["flag_ma"] for m in W.moves),
                   "ma_hand_check_overrides": W.ma_overrides, "ma_hand_checked": len(W.ma_review),
                   "artifacts_excluded": [(m["symbol"], m["date"], m["ret"], m.get("price_cap_mismatch")) for m in W.artifacts],
                   "no_ctgov": W.no_ctgov, "posting_lag_days": W.lag, "posting_lag_stats": W.lag_stats,
                   "core_versions": [(t.isoformat() if t != date.min else "window start", len(e)) for t, e in W.core.hist],
                   "prod_export_used": bool(W.export), "prod_adds": [(t.isoformat(), a.symbol) for t, a in W.core.adds],
                   "live_queue_cross_check": W.cross_check(),
                   "funnel_catalyst_checks": W.n_cat_checks,
                   "queued_by_lane": dict(Counter(v[1] for v in W.queued.values())),
                   "ctgov_counters": W.ctg_counters, "ctgov_studies_dropped_by_cap": W.ctg_dropped_by_cap,
                   "pit_relevant_without_timeline": dict(sum((t.no_timeline for t in W.trials.values()), Counter()))},
        "title_check": check,
        "verdict_from": final["title_mode"],
        "strict": {k: v for k, v in strict.items() if k != "_why_b_today"},
        **({"funnel_titles": {k: v for k, v in final.items() if k != "_why_b_today"}} if check["fires"] else {}),
    }
    OUT.write_text(json.dumps(res, indent=1, default=str))
    charts(final)
    show = {k: final[k] for k in ("m1", "decision")}
    print(json.dumps({"inputs": res["inputs"], "title_check": check, "verdict_from": final["title_mode"], **show},
                     indent=1, default=str)[:8000])
    print("M2", json.dumps({k: v for k, v in final["m2"].items() if k not in ("samples", "tier1_today_names")}, default=str)[:3000])
    print("M4", json.dumps(final["m4"], default=str))


def charts(res: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    CHARTS.mkdir(exist_ok=True)
    tag = "" if res["title_mode"] == "own" else " (rule (b) titles: funnel behaviour)"

    # 1. every measured genomics move, by what saw it
    rows = [r for r in res["moves"] if not r["flag_ma"] and r["genomics"]]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    groups = [("baseline already saw it", lambda r: r["baseline_visible"], "#9aa4b1", "o"),
              ("unseen by baseline, Tier 1 surfaced", lambda r: not r["baseline_visible"] and not r.get("c_only") and r["surfaced_ab"], "#1a9850", "^"),
              ("unseen by baseline, Tier 1 missed", lambda r: not r["baseline_visible"] and not r.get("c_only") and not r["surfaced_ab"], "#d73027", "x"),
              ("rule (c) only: excluded (look-ahead)", lambda r: not r["baseline_visible"] and r.get("c_only"), "#fdae61", "s")]
    for lab_, f, col, mk in groups:
        sel = [r for r in rows if f(r)]
        ax.scatter([date.fromisoformat(r["date"]) for r in sel], [100 * r["ret"] for r in sel],
                   s=24, c=col, marker=mk, label=f"{lab_} ({len(sel)})", alpha=0.85)
    ax.axhline(0, color="#555", lw=0.6)
    ax.set_ylabel("one-day move, %")
    ax.set_title("Genomics-labelled 20% moves, 2025-10 to 2026-09 (M&A days excluded)" + tag)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(CHARTS / "m1_moves.png", dpi=130)
    plt.close(fig)

    # 2. from moves to Tier 1's recall
    m1 = res["m1"]
    stages = [("measured moves\n(no M&A)", sum(1 for r in res["moves"] if not r["flag_ma"])),
              ("genomics-\nlabelled", m1["genomics_moves"]), ("unseen by\nbaseline", m1["invisible_to_baseline"]),
              ("primary\ndenominator", m1["denominator"]), ("Tier 1\nsurfaced", m1["surfaced"])]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar([s[0] for s in stages], [s[1] for s in stages], color=["#9aa4b1", "#4575b4", "#fdae61", "#f46d43", "#1a9850"])
    for i, s in enumerate(stages):
        ax.text(i, s[1], str(s[1]), ha="center", va="bottom")
    ax.axhline(15, color="#d73027", ls="--", lw=1)
    ax.text(len(stages) - 0.5, 15, " floor: 15", color="#d73027", va="bottom", ha="right", fontsize=8)
    ax.set_title("Measurement 1: from moves to Tier 1's recall" + tag)
    fig.tight_layout()
    fig.savefig(CHARTS / "m1_funnel.png", dpi=130)
    plt.close(fig)

    # 3. what each side was watching
    sz = res["sizes_by_week"]
    xs = [date.fromisoformat(x["monday"]) for x in sz]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(xs, [x["ab"] for x in sz], label="Tier 1, rules a+b", color="#1a9850")
    ax.plot(xs, [x["abc"] for x in sz], label="Tier 1, rules a+b+c (c = look-ahead)", color="#1a9850", ls="--")
    ax.plot(xs, [x["baseline"] for x in sz], label="baseline: core + funnel queue (distinct names)", color="#4575b4")
    ax.axvline(WIN0, color="#888", lw=0.8)
    ax.set_ylabel("names")
    ax.set_title("What each side was watching, week by week (window starts at the grey line)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(CHARTS / "sizes.png", dpi=130)
    plt.close(fig)

    # 4. measurement 2 against the gates
    m2 = res["m2"]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for i, (key, gate, better) in enumerate([("precision_sample", 0.8, "at or above"), ("misses_sample", 0.10, "at or below")]):
        x = m2[key]
        if x["share"] is None:
            continue
        lo, hi = x["wilson90"]
        ax.errorbar([i], [x["share"]], yerr=[[max(0.0, x["share"] - lo)], [max(0.0, hi - x["share"])]],
                    fmt="o", capsize=6, color="#4575b4")
        ax.hlines(gate, i - 0.3, i + 0.3, colors="#d73027", linestyles="--")
        ax.text(i + 0.32, gate, f"gate: {better}", color="#d73027", fontsize=8, va="center")
        ax.text(i, x["share"], f"  {x['genomics']}/{x['n']}", va="bottom")
    ax.set_xticks([0, 1], ["precision\n(non-core Tier 1)", "misses\n(census not in Tier 1)"])
    ax.set_ylim(0, 1.05)
    ax.set_title("Measurement 2: random-50 samples, Wilson 90%" + tag)
    fig.tight_layout()
    fig.savefig(CHARTS / "m2.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
