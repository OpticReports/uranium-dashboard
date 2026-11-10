"""Scoring machinery for SPEC v1 of studies/distress-signals.md (section 0).

Time is an integer month index m = 12*year + (month - 1). A series is a list
of Period(ref, release, on) in its own frequency, one entry per period with
no gaps: `release` is the month the value was first published (onsets are
dated there), `on` is True / False, or None when the value is masked or not
computable. The same functions score the observed series and every rotation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


def M(y: int, m: int = 1) -> int:
    return 12 * y + m - 1


def mstr(i: int) -> str:
    return f"{i // 12}-{i % 12 + 1:02d}"


# NBER business-cycle peaks and troughs; 2020-02 is exogenous (never led)
PEAKS = [(M(1969, 12), M(1970, 11)), (M(1973, 11), M(1975, 3)), (M(1980, 1), M(1980, 7)),
         (M(1981, 7), M(1982, 11)), (M(1990, 7), M(1991, 3)), (M(2001, 3), M(2001, 11)),
         (M(2007, 12), M(2009, 6)), (M(2020, 2), M(2020, 4))]
EXOGENOUS = frozenset({M(2020, 2)})
RUN_MONTH = M(2026, 10)
T_N = RUN_MONTH - 12          # last month the absence of a peak counts as known


@dataclass(frozen=True)
class Period:
    ref: int                  # reference period (series' own frequency, consecutive)
    release: int              # month index of first publication
    on: bool | None           # None = masked / not computable


def onsets(series: list[Period], quiet: int, reset_on_mask: bool = True,
           lo: int = 0, hi: int | None = None) -> list[int]:
    """Indices of onsets: the first ON period after >= `quiet` consecutive
    observed OFF periods. A spell ON at the first computable period is
    left-censored; with reset_on_mask a masked block restarts the count, so a
    spell ON right after a mask is left-censored too (SPEC v1). Only onsets
    with index in [lo, hi] are returned; earlier periods still set the count."""
    hi = len(series) - 1 if hi is None else hi
    out, off = [], 0
    for i, p in enumerate(series[:hi + 1]):
        if p.on is None:
            if reset_on_mask:
                off = 0
            continue
        if p.on:
            if off >= quiet and i >= lo:
                out.append(i)
            off = 0
        else:
            off += 1
    return out


def classify(o: int, L: int, t_n: int = T_N, peaks=PEAKS, exogenous=EXOGENOUS,
             exo_policy: str = "false") -> tuple[str, int | None]:
    """(label, peak) for an onset released in month o. The onset belongs to
    the earliest peak whose trough is >= o, if o is inside [p - L, trough];
    an onset before p - L is a FALSE ALARM (no peak within L months). With no
    later peak, FALSE if o + L <= t_n, else PENDING."""
    for p, tau in peaks:
        if o <= tau:
            if o < p - L:
                return "FALSE", None
            lab = "LEAD" if o <= p - 1 else ("COINCIDENT" if o <= p + 3 else "LATE")
            if p in exogenous:
                return ("FALSE" if lab == "LEAD" and exo_policy == "false" else "NEUTRAL"), p
            return lab, p
    return ("FALSE" if o + L <= t_n else "PENDING"), None


def scored_peaks(series: list[Period], L: int, panel: bool = False,
                 peaks=PEAKS, exogenous=EXOGENOUS, lo: int = 0, hi: int | None = None) -> list[int]:
    """Non-exogenous peaks p with a computable, unmasked value at every period
    released in [p - L - 12, p - 1] (and [p, p + 3] for PANEL), the window
    fully covered by the series' scoring range [lo, hi]."""
    hi = len(series) - 1 if hi is None else hi
    sub = series[:hi + 1]
    comp = [s.release for s in sub if s.on is not None]
    if not comp:
        return []
    first_rel, last_rel = comp[0], sub[-1].release
    out = []
    for p, _ in peaks:
        if p in exogenous:
            continue
        a, b = p - L - 12, (p + 3 if panel else p - 1)
        if first_rel > a or last_rel < b:
            continue
        win = [s.on for s in sub if a <= s.release <= b]
        if win and all(v is not None for v in win):
            # the classification window must lie inside the scoring range
            if series[lo].release <= p - L:
                out.append(p)
    return out


def lit_through(series: list[Period], p: int, L: int) -> bool:  # noqa: D103
    before = [s.on for s in series if s.release < p - L and s.on is not None]
    win = [s.on for s in series if p - L <= s.release <= p + 3 and s.on is not None]
    return bool(before) and before[-1] and bool(win) and all(win)


def score(series: list[Period], L: int, quiet: int, scored: list[int], *,
          t_n: int = T_N, reset_on_mask: bool = True, exo_policy: str = "false",
          lo: int = 0, hi: int | None = None, discount=None,
          peaks=PEAKS, exogenous=EXOGENOUS) -> dict:
    """Classify every onset in [lo, hi] and grade each scored peak.
    discount(i) -> True drops a LEAD (e.g. Q-H single-month attribution)."""
    idx = onsets(series, quiet, reset_on_mask, lo, hi)
    per_onset, false_alarms, pending, neutral, unscored, discounted = [], [], [], [], [], []
    by_peak: dict[int, dict[str, list[int]]] = {}
    for i in idx:
        o = series[i].release
        lab, p = classify(o, L, t_n, peaks=peaks, exogenous=exogenous, exo_policy=exo_policy)
        rec = {"i": i, "release": mstr(o), "class": lab, "peak": mstr(p) if p is not None else None}
        if lab == "FALSE":
            nxt = next((pk for pk, tau in peaks if o <= tau), None)
            rec["early"] = nxt is not None and nxt - L - 6 <= o <= nxt - L - 1
            false_alarms.append(i)
        elif lab == "PENDING":
            pending.append(i)
        elif lab == "NEUTRAL":
            neutral.append(i)
        elif p not in scored:
            unscored.append(i)
            rec["unscored_peak"] = True
        elif lab == "LEAD" and discount is not None and discount(i):
            discounted.append(i)
            rec["discounted"] = True
        else:
            by_peak.setdefault(p, {}).setdefault(lab, []).append(i)
        per_onset.append(rec)
    peaks_out = []
    for p in scored:
        d = by_peak.get(p, {})
        if d.get("LEAD"):
            i = d["LEAD"][0]
            peaks_out.append({"peak": mstr(p), "outcome": "LEAD", "onset": mstr(series[i].release),
                              "lead_months": p - series[i].release})
        elif lit_through(series[:(len(series) if hi is None else hi + 1)], p, L):
            peaks_out.append({"peak": mstr(p), "outcome": "LIT-THROUGH"})
        elif d.get("COINCIDENT"):
            peaks_out.append({"peak": mstr(p), "outcome": "COINCIDENT",
                              "onset": mstr(series[d["COINCIDENT"][0]].release)})
        elif d.get("LATE"):
            peaks_out.append({"peak": mstr(p), "outcome": "LATE",
                              "onset": mstr(series[d["LATE"][0]].release)})
        else:
            peaks_out.append({"peak": mstr(p), "outcome": "MISS"})
    return {"per_peak": peaks_out, "onsets": per_onset,
            "n_lead": sum(1 for x in peaks_out if x["outcome"] == "LEAD"),
            "n_false": len(false_alarms), "n_pending": len(pending),
            "false_alarms": [mstr(series[i].release) for i in false_alarms],
            "pending": [mstr(series[i].release) for i in pending]}


def years_scored(series: list[Period], L: int, per_year: int, t_n: int = T_N,
                 lo: int = 0, hi: int | None = None) -> float:
    """Unmasked, non-PENDING computable periods, in years (FA-rate denominator)."""
    hi = len(series) - 1 if hi is None else hi
    last_trough = PEAKS[-1][1]
    n = sum(1 for s in series[lo:hi + 1]
            if s.on is not None and (s.release <= last_trough or s.release + L <= t_n))
    return n / per_year


def size_test(series: list[Period], L: int, quiet: int, scored: list[int], q: int, *,
              lo: int = 0, hi: int | None = None, **kw) -> dict:
    """Rotate the ON/OFF values circularly among the computable slots in
    [lo, hi] by k = q .. |O| - q; everything else fixed. Statistic (LEADs at
    scored peaks, false alarms); p = (1 + #{L_k >= L, F_k <= F}) / (1 + R)."""
    hi = len(series) - 1 if hi is None else hi
    obs = score(series, L, quiet, scored, lo=lo, hi=hi, **{k: v for k, v in kw.items() if k != "discount"},
                discount=kw.get("discount"))
    slots = [i for i in range(lo, hi + 1) if series[i].on is not None]
    vals = [series[i].on for i in slots]
    n = len(vals)
    better = R = 0
    kw2 = {k: v for k, v in kw.items() if k != "discount"}
    for k in range(q, n - q + 1):
        rv = vals[-k:] + vals[:-k]
        new = list(series)
        for i, v in zip(slots, rv):
            new[i] = replace(series[i], on=v)
        sc = score(new, L, quiet, scored, lo=lo, hi=hi, **kw2)
        R += 1
        if sc["n_lead"] >= obs["n_lead"] and sc["n_false"] <= obs["n_false"]:
            better += 1
    return {"p": (1 + better) / (1 + R) if R else None, "R": R, "at_least_as_good": better,
            "min_p": 1 / (1 + R) if R else None,
            "observed": {"leads": obs["n_lead"], "false": obs["n_false"]}}


def holm(pvals: dict[str, float | None]) -> dict[str, float | None]:
    """Holm step-down adjusted p-values (None stays None)."""
    items = sorted((p, k) for k, p in pvals.items() if p is not None)
    m, out, run = len(items), {k: None for k in pvals}, 0.0
    for j, (p, k) in enumerate(items):
        run = max(run, min(1.0, (m - j) * p))
        out[k] = run
    return out
