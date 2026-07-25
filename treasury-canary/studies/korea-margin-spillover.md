# Korean margin deleveraging → US equities: spillover study (NEGATIVE result)

**Question** (2026-07): Korean retail leverage is blowing up (record ₩38.6T
margin balance in June 2026 → ₩32.75T by late July; 1.2M accounts margin-called,
~360k liquidated; KOSPI −9.99% Jun 23, −9% Jul 13). On big Korean deleveraging
days, US stocks seem to sell off. Is Korean margin data a usable leading input
for US exposure — worth a canary tile?

**Data**: KOFIA daily credit balance (신용잔고, via the Naver Finance mirror —
KOFIA's own portal WAF-blocks server-side clients), 1,780 trading days
2019-04..2026-07; SPY and SOXX full OHLC (FMP); KOSPI (^KS11). Same-date
pairing = "Korea's session closed before the US opened that calendar day."
Script preserved beside this file's session notes; re-run needs only those
four inputs.

## Results

**Test 1 — same-date US response.** Event = daily Korean margin balance drop
≤ −0.8% (n=175; p05 of the distribution) or ≤ −1.2% (n=94). SPY open gap on
event days: mean −0.03% (baseline +0.04%), median +0.11%, 41% negative —
indistinguishable from noise. Close-to-close: mean +0.01%. SOXX: same story
(gap −0.01% vs baseline +0.11% — a whisker, not a signal). The fat left tail
(worst −10.4%) is COVID-March days, i.e. common shocks.

**Test 2 — independence.** Prior-day US return on Korean-delev days is flat
(mean −0.03%) — Korean delev days are NOT merely echoes of US selloffs, so the
test is fair. Restricting to "non-echo" events (prior US day > −0.5%):
SPY same-day mean −0.14% to −0.31% but median +0.09% to +0.16%, 44-49%
negative — the negative mean is a handful of common-shock tail days, not a
distributional shift. Same-day KOSPI on those events is itself flat (−0.02%),
confirming the balance drop mostly *records* selling that already happened.

**Test 3 — state-dependence and tradeability.** Unwind-regime vs normal-regime
splits flip sign between thresholds (n=13 in one cell) — no stable pattern.
The tradeable version (act at D+2, after KOFIA's ~T+2 publication): SPY
+0.13%, SOXX +0.31% — if anything, mild mean-reversion AGAINST the signal.

**Lead-lag (full sample, n=1,779).** dK(D) vs SPY: r = **+0.062** with the
PRIOR US session (US leads Korea), +0.012 same-date, +0.026 next-day, −0.012
at the tradeable lag. The causality arrow points from the US to Korea.

**The 2026 episode itself** (12 delev days ≥0.8%, Jun-Jul): US closed down 6,
up 6, mean −0.17%. The days that formed the impression (Jun 23: dK −1.1%, SPY
−1.45%; Jun 10) sit next to Jul 10 (dK −2.86%, the second-worst Korean day of
the whole sample — SPY **+0.43%**).

## Why the intuition fails as a signal

1. **T+2 embedding**: the balance series drops ~2 days after the forced selling
   (settlement), so by publication the information is stale twice over.
2. **Common factor, not causation**: KOSPI leverage IS the AI/semis trade
   (Samsung/SK Hynix ≈ the NVDA complex) held with more leverage by a more
   fragile base. Korean blowups and US selloffs share a cause; the co-movement
   is same-trade-different-timezone and is priced by the US open.
3. **Size**: Korean retail's US flows ($2-3B/mo, concentrated in SOXL/TQQQ)
   are real but rounding-error vs US volume outside the overnight session.

## Verdict

**Do not add a Korea-leverage tile as a signal** — every version tested carries
zero or negative incremental information for US equities. The observed
"Korean deleveraging day → US selloff" pattern is the shared AI-complex shock,
which the canary already watches directly (semis via cross-asset, US leverage
via the FINRA margin gauges — the slow, validated version of the same
risk-appetite cycle Korea expresses fast and loud). If Korea is wanted on the
dashboard at all, it belongs as *context* (a news-tier line), not as an input.

Falsifiable revisit: if a future episode shows Korean margin data moving
BEFORE US semis for 5+ consecutive events (not after, as in every episode
here), re-run this study with intraday data.
