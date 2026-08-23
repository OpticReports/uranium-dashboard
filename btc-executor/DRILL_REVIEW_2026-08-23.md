# Counter-agent review — drill variants + stopfill redesign (6baf5cd)

**Target:** `claude/genomics-tracker-goals-8eleq3` @ 6baf5cd, files
`app/mirror.py`, `app/config.py`, `RAMP_V4.md`, `tests/test_executor_gates.py`.
Baseline `origin/main`. Governing law: `EXECUTOR.md`, `RAMP_V4.md`.

> **REVIEWER INDEPENDENCE — READ THIS FIRST.** I am the **same model family as
> the author**. No cross-family reviewer was reachable for this pass. Per the
> CROSS-FAMILY REVIEW convention (Casey, 2026-08-22) this is **weaker evidence
> than an independent-family review**: I share the author's training and
> therefore the author's blind spots, and a reviewer that does not think to
> check what the author did not think to check is not the independent check the
> verdict log implies. This is a live-money change and it BINDS (it credits the
> coverage rows that authorize scaling). Treat the verdict below as a finder's
> report, not as the independent sign-off the ramp rules ask for.

---

## VERDICT: **REJECT**

Not because the redesign is wrong — the below-market stop is correct and the
differential proves the `cycle`/`stopfill` refactor is behaviour-preserving.
Reject because **two independent defects put evidence the venue never gave into
the counters that authorize scaling real money**, and **one lets a drill leave a
live order resting on Coinbase while reporting `ok=true`**. One of them is
enshrined in a new test as intended behaviour, so this needs a code + test +
spec change and a re-review, not a merge-on-trust.

Blocking list is B1–B4. B5–B9 are binding corrections that may ride along.

---

## What I verified as CORRECT

| author's claim | verdict | how |
|---|---|---|
| (4) `cycle`/`stopfill` behaviour otherwise UNCHANGED | **CONFIRMED** | 12-scenario differential vs `origin/main` (base, cancel-race, stop-rejects, stop-fires, exit-swallowed, mid-raises × cycle/stopfill): `ok`, coverage dict, order tape and end position **identical in all 12**, modulo the trigger price |
| (b) the `ok` refactor is equivalent | **CONFIRMED** | Same differential + direct probes: repair-fires ⇒ `ok=False`, no coverage; `repair_error` ⇒ `ok=False`, no coverage. `steps["auto_repair"]` is only ever a non-zero float, so `is not None` is a faithful stand-in for the old inline `ok = False`. **The `ok=True`-when-unproven cases below come from the NEW paths' return values, not from the refactor.** |
| (c) sign/price math | **CORRECT, all four** | BUY/rest → `mid(1−bps)`; SELL/rest → `mid(1+bps)`; BUY/cross → `mid(1+bps)`; SELL/cross → `mid(1−bps)`. Every combination lands on the intended side. |
| (f) preconditions & size bound | **CORRECT** | `_drill_refusal()` and `q = self._min_contract()` run in `_drill_locked` **before** any kind dispatch — halted / leg-not-flat / venue-not-flat / daily budget / cooldown all inherit unchanged. No parameter reaches `q`. (But see **B4** — a *race* can double the size even though no parameter can.) |
| (g) auto-drill cannot schedule the new kinds | **CORRECT** | `_needed_auto_drill()` returns only `"cycle"` or `None`. Mutating it to return `"limit_buy"` is caught. |
| (1) Coinbase STOP_DOWN rationale | **SOUND** | `cb.py:280` hard-maps SELL → `STOP_DIRECTION_STOP_DOWN`. An above-market trigger on a STOP_DOWN is preview-rejected; the old drill was dead on arrival and could never earn `stop_filled`. Moving below market is the right fix. |
| (5) drill entries do not credit organic rows | **CORRECT** | `RAMP_V4_REQUIRED` (main.py:209) contains neither `drill_limit_entry` nor `drill_chase`; the organic `chase` row is never appended. Mutating `drill_chase`→`chase` is caught. |

---

## BLOCKING FINDINGS

### B1 — A drill can leave a LIVE ORDER RESTING on the venue and still report `ok=true` — SEVERITY: HIGH (a)

`_drill_repair` verifies **only `venue.position()`**. It never checks whether the
drill's own orders reached a terminal state. `CoinbaseVenue.cancel()` swallows
every exception (`cb.py:295–301`, `logger.warning` and return), so a failed
cancel is **completely invisible** to the drill.

Executed repro (`cancel()` is a silent no-op on the venue):

| kind | drill reports | left resting at Coinbase |
|---|---|---|
| `limit_buy` | `ok=True`, `venue_flat_end=True`, credits `drill_limit_entry` + `drill_chase` | post-only **BUY LIMIT @ mid−5bp** |
| `stopfill` | `ok=False` (pages) | **SELL STOP @ mid−10bp** |
| `cycle` | `ok=True`, credits `drill_cycle` + `stop_placed` | **SELL STOP @ mid−100bp** |

Consequences: the resting `stopfill` stop is 10bp below market and **will fire
within minutes**, opening a naked 1-contract SHORT with no stop and no ledger
entry. Nothing cleans it up — `step()` only manages ledger-known cloids and
`cancel_all()` runs only on halt/kill. It surfaces, eventually, as a
`position_drift` RED. The `limit_buy` case is worse in one respect: the drill
says **`ok=True` and takes the coverage credit** while the order is still live.

The `cycle` variant is pre-existing on `origin/main`, but the `stopfill` and
`limit_*` variants are **newly reachable** — on main the stopfill stop was always
preview-rejected, so there was never a resting order to fail to cancel.

Related, same function: `cycle`'s `steps["stop_cancelled"] = st2["status"] !=
"FILLED"` is **True for a stop that is still OPEN**. The step name asserts
something the check does not test.

**Required fix.** In `_drill_repair`, after flattening, resolve every `{base}-*`
cloid and refuse `ok` unless each is terminal. `venue.cancel_all()` is safe to
call here *specifically because* `_drill_refusal()` guarantees no leg holds an
`entry_cloid`/`stop_cloid` — there is nothing else of ours on the book. Record
the outcome in `steps` so a stranded order pages instead of passing.

### B2 — `post_only_cross` is credited off evidence the drill did not produce, and then DOUBLE-COUNTED — SEVERITY: HIGH (e) — *this is the highest-severity class named in the brief*

```python
crossed = bool(getattr(self.venue, "post_only_crosses", None))
```

`post_only_crosses` is a **cumulative list on the venue adapter**
(`cb.py:48`, appended at `cb.py:253`) drained only by
`_report_post_only_crosses()` inside `step()`. So "non-empty" means *some cross
has happened since the last step tick* — not *this drill's order crossed*.

Executed repro — venue pre-loaded with one **organic** cross (`P-organic-E`),
drill's own limit never rejected:

```
drill ok: True   post_only_rejected: True
coverage after drill:                {'drill_chase': 1, 'post_only_cross': 1}
venue.post_only_crosses still:       ['P-organic-E']      <-- not consumed
coverage after next step()'s drain:  {'drill_chase': 1, 'post_only_cross': 2}
```

Two distinct defects in one line:

1. **False attribution.** A cross caused by an unrelated organic order credits
   the drill. RAMP_V4 says the row is "Credited ONLY when the venue actually
   records the rejection: us intending to cross proves nothing, the venue
   refusing does." The code cannot tell the difference.
2. **Double count.** The drill credits `_cov("post_only_cross")` without
   clearing the list; `step()`'s drainer credits the *same cloid* again on the
   next tick. One real cross ⇒ **two** increments on a gate-authorizing counter
   that RAMP_V4 states is "incremented inside the real code paths — never by
   hand."

**The new test bakes this in as correct.**
`test_gate_post_only_cross_credits_only_on_venue_rejection` sets
`venue.post_only_crosses = {"D-x-E"}` — a cloid belonging to *no order in the
test* — and asserts the drill credits the row. The test named for this property
is the artifact that certifies the bug.

**Required fix.** Snapshot `list(venue.post_only_crosses)` before `place_limit`;
credit only if a NEW entry appears **whose cloid is `f"{base}-E"`**; then remove
that entry so `_report_post_only_crosses` cannot re-credit it. Rewrite the test
to prove the negative case (a stale foreign cross must NOT credit).

### B3 — At shipped defaults the stopfill drill fails ~90% of the time and RED-pages on every failure — SEVERITY: HIGH (d)

`DRILL_STOPFILL_BPS=10.0`, `DRILL_STOPFILL_POLL=30` ⇒ the drill needs BTC to
trade **10bp down within 60 s**. First-passage probability for driftless GBM,
P(min ≤ −a) = 2Φ(−a/σ_T):

| ann. vol | σ over 60s | P(fire) @10bp/60s | @3bp/60s | @10bp/300s |
|---|---|---|---|---|
| 35% | 4.8bp | **3.8%** | 53% | 35% |
| 45% | 6.2bp | **10.7%** | 63% | 47% |
| 60% | 8.3bp | **22.7%** | 72% | 59% |

So at ordinary BTC vol roughly **90% of stopfill drills time out**. Each timeout:

- emits a **RED `drill` event** ("UNVERIFIED - check venue") → Telegram page;
- pushes `/pulse.red_events_24h > 0`, which latches the **btc-paper-engine
  watchdog's `red_events` condition** (`watchdog.py:196`, fires on `reds > 0`)
  and re-pages every `WATCHDOG_COOLDOWN_S` until a clean 24h. With daily
  drilling that condition **never clears**;
- burns 1 of the 6 `DRILL_MAX_PER_DAY` slots shared with `cycle` and the limit
  kinds, plus a real market round-trip (~$1–2).

Expected yield at defaults: **~0.3–0.6 successes/day against ~5.5 RED pages/day.**
EXECUTOR.md cites the 2026-08-17 storm ("35 identical REDs in ~12 minutes —
never again") as settled law; this ships a slower version of it.

**Required fix.** Default `DRILL_STOPFILL_BPS ≈ 3.0` (still ~2× the measured
1.54bp spread and ~33 ticks on a $1 price increment) and/or raise
`DRILL_STOPFILL_POLL`. Additionally: a stopfill that merely times out is an
expected outcome, not a fault — it should log **WARN**, and reserve RED for a
drill that could not be flattened or verified.

### B4 — A fill-beats-cancel race in the limit path doubles the drill size, leaves no record, and reports `ok=true` — SEVERITY: MEDIUM-HIGH (a/f)

`_drill_limit_path` cancels the unfilled limit and then places a market chase for
the **full `q`** without re-reading the position. If the limit filled in the
cancel window, both fills land. Executed repro:

```
tape: LIMIT BUY 0.01 -E | CANCEL(too late) | MARKET BUY 0.01 -C | MARKET SELL 0.02 -X
ok: True   coverage: {'drill_chase': 1, 'drill_limit_entry': 1}
steps: (nothing recording that 2 contracts were held)
```

The intended-exit flatten absorbs it, so `auto_repair` never fires, so **no RED,
no `ok=False`, no trace in `steps`**. RAMP_V4's hard bound — "size is ALWAYS
exactly one venue contract; no parameter can raise it" — holds for parameters
but not for the venue. Fix: read `position()` after the cancel and chase only the
residual, and record `steps["actual_qty"]` so a doubling is visible.

The **same race in the redesigned `stopfill` fallback** is the bug the 2026-08-15
referee already ruled on. `cycle` got the guard (`if steps["stop_cancelled"]:`);
`stopfill` did not — it cancels and unconditionally sells `q`. Executed repro
confirms it opens a **SHORT**, which the repair tail then buys back (`ok=False`,
RED). Bounded and detected, ~0.5% of drills (a ~2.2 s unobserved window in a 60 s
poll × ~10% fire probability), so ~1 in 200 — but the redesign converted a dead
branch into a live one, and worse: **in that case the stop genuinely fired, so
the `stop_filled` row was legitimately earned and the code throws it away, pages
RED, and opens an unwanted short instead.** Re-read `position()` after the
cancel: if flat, the stop filled — credit the row.

---

## BINDING CORRECTIONS (non-blocking)

**B5 — `DRILL_LIMIT_BPS=5.0` does not rest "inside the spread"; it rests behind
the book.** EXECUTOR.md's own measurement is a **1.54bp** spread (half-spread
0.77bp) with 50 contracts at level 1. A BUY at mid−5bp sits ~4.2bp **behind the
best bid**, outside the spread, behind the whole level-1 queue. Consequences: the
maker fill essentially never happens (P(touch) 14–39% in 30 s, and touching ≠
filling from the back of a 50-contract queue), so **every limit drill degenerates
to place → cancel → market chase**. Set the default to ~0.5bp to actually rest
inside the measured spread, or rename the parameter and stop claiming "inside".

**B6 — the limit drill does not run the organic pullback path it claims to.** An
organic pullback fill goes on to place the protective ATR stop (`_maintain_stop`).
The drill flattens instead. So the drill proves *placement + cancel + chase*, and
— per B5 — in practice not even the maker fill. RAMP_V4's "routes the same venue
calls an organic pullback entry makes" and the honesty table's "fill handling ✅
proven" both overclaim.

**B7 — `drill_limit_entry` is credited even when the venue REJECTS the limit.**
Executed: a venue that rejects the post-only order outright still yields
`ok=True` and `drill_limit_entry: 1`. Not gate-bearing **today**, but RAMP_V4
explicitly flags promoting these rows to `entry_long`/`entry_short` as the
pending question — this is a live landmine for that follow-up. Gate the credit on
the limit having actually been accepted.

**B8 — the position-holding window grew 5×, and a SIGTERM inside it strands the
position.** `except Exception` does not catch `SystemExit`/`KeyboardInterrupt`, so
a Render redeploy during the now-60 s stopfill poll (or the 30 s limit poll) skips
both the fallback flatten and the repair tail. Nothing auto-flattens a stray
position at boot — `_check_drift` pages but does not close. Recommend a persisted
`drill_open` marker written before the entry and reconciled in `__init__`.

**B9 — the five new drill vars are absent from the `config_change` snapshot**
(`_check_mode_change`, mirror.py:757). They set live order prices. A dashboard
fat-finger on `DRILL_CROSS_BPS` changes real order behaviour with no page.

---

## TESTS (h)

All 124 pass. The 11 new tests are real (each fails against `origin/main`), but
**mutation testing found 4 of 11 weakenings survive them**:

| mutation | new tests | full suite |
|---|---|---|
| M1 trigger back ABOVE market | **caught** | caught |
| M2 flip BUY/SELL sign | **caught** | caught |
| M4 credit the ORGANIC `chase` row | **caught** | caught |
| M6 auto-drill schedules `limit_buy` | **caught** | caught |
| M10 new kinds skip the flat precondition | **caught** | caught |
| M5 delete the intended flatten | caught (incidentally, by the post-only-cross test) | caught |
| **M3 credit `post_only_cross` unconditionally** | **SURVIVES** | caught elsewhere |
| **M7 drop `post_only=True` on the drill limit** | **SURVIVES** | caught only by `test_gate_no_blueprint_managed_trading_vars`, an unrelated source-text gate — i.e. coincidentally |
| **M8 delete the stopfill cancel+flatten fallback** | **SURVIVES** | SURVIVES |
| **M9 repair no longer forces `ok=False`** | **SURVIVES** | caught elsewhere |
| **M11 drill size ×3** | **SURVIVES** | caught elsewhere |

The three that matter:

- **M7.** `test_gate_limit_drill_uses_post_only_not_market` is named for the
  single most important claim of the whole change — that the drill runs the
  **maker** path — and does not test it. Root cause: `_drill_exec` builds a
  `DryRunVenue`, which ignores `post_only`; `FakeVenue` (which has
  `assert post_only, "pullback entries must be maker"`) is not used for drills.
- **M8.** `test_gate_stopfill_unfilled_still_flattens` asserts
  `venue.position() == 0.0` — which the **repair tail** satisfies with the
  fallback deleted. It verifies the backstop, not the fallback. Assert the `-X`
  order exists and that no `-R` repair order was needed.
- **M9.** The single highest-stakes line of the `ok` refactor is not covered by
  any of the 11 new tests.

Also: `test_gate_stopfill_trigger_is_below_market`'s lower bound
(`trig > mid*0.99`) would pass a 99bp trigger; it does not test "close enough to
fire" in any meaningful sense. And **no test exercises the stopfill FILLED path
at all** — `covs.extend(("stop_filled", "drill_stopfill"))` and its `return True`
are reached only by an existing monkeypatched test, not by the new ones.

**Does `poll = 1` in the test `Cfg` hide a production-only bug?** Not directly —
the loop body is budget-independent. But it hides everything *timing*: the
fill-beats-cancel windows of B4, the 60 s SIGTERM exposure of B8, and the ~90 %
timeout rate of B3 are all invisible at a 1-iteration budget. The budget choice
is defensible; the missing coverage is the race, not the count.

---

## SPEC (i) — RAMP_V4.md does NOT accurately describe the code

| RAMP_V4.md says | reality |
|---|---|
| stopfill "fires on the next **downtick**" | needs a **10bp** adverse move — ~100× a tick, ~4–11% probability in the 60 s budget (B3) |
| limit drills rest "**INSIDE the spread**" | 5bp default vs a 1.54bp measured spread ⇒ ~4bp **behind the best bid** (B5) |
| "routes the same venue calls an organic pullback entry makes" | no protective stop is placed on fill; the maker fill itself is not reached in practice (B6) |
| post_only_cross "Credited **ONLY** when the venue actually records the rejection" | credited whenever the venue's cumulative list is non-empty for *any* reason, and double-counted (B2) |
| "size is ALWAYS exactly one venue contract; no parameter can raise it" | true of parameters; a race raises it to two, silently (B4) |
| "AUTO-REPAIR tail (all kinds, all exception paths)" | covers **position** only; never checks resting **orders** (B1), and does not cover `SystemExit` (B8) |
| undocumented | `post_only_cross` is always a **BUY** cross. The organic row it stands in for is a basis-driven **SELL** rejection. Side-symmetric at the venue, but the doc should say so. |

**Is the execution-half vs decision-half honesty section accurate and sufficient?**
The *framing* is right and the `PENDING CROSS-FAMILY REVIEW` hold is the correct
call — the author declining to rule on their own promotion question is exactly
the discipline the repo asks for, and `drill_limit_entry` being recorded
separately from `entry_long`/`entry_short` is the right mechanism. But the table
**overclaims within its own left column**: "venue interaction, fill handling,
chase ✅ proven" is not earned when the maker fill almost never occurs and no
stop is placed on it. Add a third row — *maker fill + stop-on-fill: ❌ not
exercised* — and the section becomes accurate.

Editorial: the sentence "Trend organic entries (market path) count toward entry
coverage; pullback entries prove the limit/post-only path." is stapled to the end
of the AUTO-REPAIR bullet, where it does not belong.

---

## Re-review scope

B1, B2, B4 are code + test changes; B3 is a constant; the spec rows follow. When
they land, the differential harness and mutation set used here should be re-run,
and **the cross-family reviewer this change is already waiting on for the
entry-row promotion question should review B2 as well** — attributing coverage
evidence is precisely the judgment a same-family reviewer is weakest at.
