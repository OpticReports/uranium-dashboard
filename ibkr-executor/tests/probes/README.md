# Adversarial-review probes (the record, not the suite)

These files are the counter-agent probe suites written against the
blend3070 executor across the review rounds that produced N1/N2, R1/R2, N3,
X1–X4/Y1, Z1/Z2/y2, ZF-1..ZF-9 and MF2-1..MF2-5. They are committed as the **audit record** of what
was attacked and what landed — the thing a later reviewer needs in order to
tell a probe that got HARDER from one that got quietly softened.

Why they are here at all: the Z1 counter-review (finding **Z-M**) could only
audit one rewritten probe by disassembling its stale `__pycache__` bytecode,
and a second probe's pre-commit text was **unrecoverable** because the probes
lived only in a scratch directory and were never versioned. Probes are
load-bearing gates in this workflow; an unversioned gate is not a gate.

## They are NOT part of the pytest run

`pytest` does not collect them: they are named `attack_*.py` (the default
`python_files` patterns are `test_*.py` / `*_test.py`), and
`pyproject.toml` additionally sets `norecursedirs = ["probes"]`. They are
standalone scripts with their own PASS/FAIL printer — a FAIL is a **landed
attack**, which is the opposite of the pytest convention, so collecting them
would invert the meaning of a red run.

Run them by hand from `ibkr-executor/`:

```
python tests/probes/attack_z1.py
```

Each prints its result on the last line. Six of the eight end with
`N/M probes passed; landed attacks: [...]`; `attack_reround.py` and
`attack_r1r2.py` end with `N/M probes passed; failures: [...]` — same
meaning, older wording, and left as written per rule 1 below.

`attack_mf2.py` drives its service-level scenarios out to subprocesses
(`probes/mf2/scen.py`, one scenario per process because they mutate module
globals), so that directory travels with it. `probes/mf2/flake_repro.py`
and `probes/mf2/linger.py` are the two deterministic reproductions behind
the MF-1 gate's flake ruling; they run the OLD body of that test on
purpose, as the record of what was measured, and are NOT gates.

## Rules for touching them

1. **Do not "clean them up."** Their current text IS the record. Formatting,
   renaming and de-duplication all destroy the diff a reviewer needs.
2. **Any edit to a probe must be justified in the commit message**, naming
   the check that changed and why the new assertion attacks the contract at
   least as hard as the old one. A contract that legitimately changed is a
   reason to make a probe HARDER, never weaker.
3. A probe that legitimately encodes an OLD contract stays in the file with
   its result explained in the round's summary, rather than being deleted.

## Standing results at the time of this commit

The MF-1/MF-2/MF-3 round (the whole-branch counter-review's three
MATERIALs) changed no probe file: all seven were re-run from
`ibkr-executor/` at the marks below, before and after the fixes, and every
one landed on its documented mark. The reviewer's own re-attack suite for
that round (`scratchpad/attack_final.py`, 29 checks) went 28/29 -> 29/29,
the one flip being `F4g` — the MF-3 defect it found.

The MF-A/MF-B/MF-C round (the counter-review OF that round: the false
kill-switch bound, the stand-in flag that cleared in one cycle, and the
NEW harm where a stand-in row's fabricated identity cancelled a real
working stop) again changed no probe file. All seven were re-run from
`ibkr-executor/` before and after, every one on its documented mark, and
`scratchpad/attack_final.py` stayed 29/29.

The MF2 round (the counter-review OF the MF-A/MF-B/MF-C round: the ladder
half of the kill switch — a `/kill` that made an uncapped gateway call on
the API thread, a deferred halt that never reached disk, a queued kill that
outlived `/resume`, and a `ladder: "closed"` when nothing closed) changed no
existing probe file either. All seven were re-run before and after, every
one on its documented mark, `scratchpad/attack_final.py` stayed 29/29, and
the round's own suite is landed below as `attack_mf2.py`.

| probe | result | note |
|---|---|---|
| `attack_reround.py` | 9/9 | |
| `attack_r1r2.py` | 7/7 | |
| `attack_n3guard.py` | 10/10 | |
| `attack_n1n2.py` | 14/14 | |
| `attack_x1x4.py` | 39/40 | `X-B[consequence]` lands BY DESIGN — its author withdrew it (a bounded liquidation at a chosen price beats unbounded naked downside); do not code to it |
| `attack_zfinal.py` | 41/43 | The whole-branch review's suite, committed byte-identical to the file its author ran. Two land and BOTH are by design. `ZF-A9c` is a recorded SCOPE statement, not a defect: outside a flagged cell reconcile never reads `held`, so the invariant is "cover <= held **in cells where `held` was verified this cycle**" — identical at main, and closing it is a new periodic-sweep feature. `ZF-G4` ASSERTS the ZF-2 defect (pass 4 adopting an already-FILLED order as working protection, `stop_missing=False` with nothing resting): it PASSED while the defect existed and now FAILS because `_ensure_stop` refuses a non-`working` duplicate — its own detail line shows the corrected end state (`stop_missing=True`, `naked=True`). It is left exactly as written, per rule 3 above. `ZF-D3` needs `ZF_MAIN_WORKTREE=<a worktree at e750abd>` to mean anything; without it the subprocess re-imports HEAD and reports a false PASS. The rollback it measures is unfixable from this side — see the deploy note in the executor README (ZF-3). |
| `attack_z1.py` | 20/21 | `Z-1b` lands and is left landing on purpose: it directly contradicts `Z-1`, the hand-derived allocation table in the same file. `Z-1` pins `held > book` to `{1:2,2:2,3:1}`; `Z-1b` demands every allocation be `<= that position's own qty`. Both cannot hold. `held > book` is unreachable from the only call site (it enters on `held < book_qty`) and every result is capped at `min(alloc, qty)` before it can reach the venue, so the cell is a documentation defect, not a live one — and preserving the reviewer's verified table was judged worth more than silencing a probe about an unreachable input. `Z-1c` (negative/zero qty) WAS fixed. |
| `attack_mf2.py` | 55/57 | The MF2 round's suite (57 checks), committed byte-identical to the file its author ran, with its drivers in `probes/mf2/`. It was **48/57 at 499aed1** (landed: `A3`, `A4`, `A5`, `A6`, `A8`, `A9`, `B5`, `B6`, `C2`) and is **55/57** here: `A3`/`A4`/`A5`/`A8`/`A9` were closed on the merits by MF2-1/MF2-2/MF2-3/MF2-4 (`/kill` makes no venue call at all now, the halt is journalled to `<STATE_PATH>.kill`, `/resume` cancels a queued kill, and the reply/alert report what actually happened) and `B5`/`B6` by mf2-9/mf2-10. Note that `A9` was PRE-EXISTING at main, not this round's harm; it closed as a side effect of MF2-1. Two still land and BOTH are by design. `A6` asks that a book halted mid-cycle place NO further order in the cycle already in flight: the intent loop breaks on a halt now (MF2-5), so the four measured venue BUYs became ONE — and that one is the order whose `place_stock_order` call the probe itself is blocked INSIDE when the kill lands. Nothing in this process can withdraw a call already made to the venue, so the check cannot reach zero as it is constructed; it is a residual of the probe's shape, not an open finding. `C2` is the accepted ZF-3 one-way rollback door in its MF-C form: an older build loads a `stand_in_rows` book without crashing and then runs reconcile pass 1b on the INVENTED symbol, deleting the row while the venue still holds the shares and the real GTC stop still rests there (`ROWS_AFTER [] | VENUE 5 | STOP working`). The fix would have to live in the build being rolled AWAY from, so it is unreachable from this side — named in the executor README's deploy note. Running it: `python tests/probes/attack_mf2.py` from `ibkr-executor/`; `C1`/`C2` additionally need a git worktree of `9b33081` at `tests/probes/base9b` (without one, `C1` lands as SKIPPED and `C2` never runs), and `A9` compares against that same worktree. |
