# Pre-registration: a rules-exact synthetic of the KMLM fund, and the switcher study on its long history (2026-11-20)

Written before any synthetic series was built or compared with the fund (a scouting pass is fetching
the index's published rules and one rough first-pass fit; its numbers are disclosed below when known and
count as seen). Frozen at the commit that adds this file. Standing rule: CLAUDE.md "SYNTHETIC HISTORY
BEFORE SHORT SAMPLES" (owner, 2026-11-20: "ok go ahead and build").

## What is built
A daily total-return series for the KFA Mount Lucas Managed Futures Index Strategy ETF (KMLM, first close
2020-12-02) before it existed, by applying its index's PUBLISHED rules to the underlying futures markets
(or, where a futures history cannot be had, to spot plus carry), less the fund's fee, plus collateral
interest. The other legs of the switcher come from the repo's long panel (`research/longrun/long_panel.py`),
each re-validated here.

## What may and may not be fitted
- Rules come from the published methodology. Where it is silent, the choice is made from the documents'
  own wording or common index practice BEFORE any comparison with the fund, and is listed.
- No parameter is searched to improve the fit to the fund. ONE scalar may be calibrated: the exposure
  (index-to-fund scale), on the FIRST HALF of the overlap only (2020-12-02 to 2023-11-30).
- Every fidelity bar below is read on the SECOND HALF (2023-12-01 to the last settled close), which the
  calibration never saw. First-half numbers are reported beside them.

## Fidelity bars (the synthetic against the real fund; set now)
F1 daily-return correlation >= 0.90 (the current stand-in RYMFX: 0.55).
F2 the switch reads the same way: RSI(10) of XLK > RSI(10) of the synthetic agrees with the real fund on
   >= 95% of sessions (RYMFX: about 84%).
F3 annualised volatility within 15% of the fund's; annual return within 3 points of the fund's.
F4 the whole symphony run on the synthetic in place of the fund holds what the real-fund run holds on
   >= 95% of sessions, and its total log growth is within 10% of the real-fund run's (the repo's proxy
   flags gave 9-23x where the real flag gave 61x: this is the bar that matters).
F5 the 74-variant surface of addendum 57 recomputed with the synthetic flag ranks the variants as the
   real flag does: Spearman rank correlation of the variants' growth differences >= 0.80.
Also reported, not gating: agreement before 2020 with any published history of the index itself.

## What each outcome licenses
- ALL FIVE PASS: the synthetic years count as evidence. The 74 variants of addendum 57 are judged again
  on the long history by the same five conditions (family-wise p < 0.10 and so on), with one addition: a
  variant must also not be behind the live rule on the real-fund years. Reported in two parts: years
  where every leg is a REPLICATION (its underlying market traded), and earlier years where a leg is a
  MODEL of a market that did not exist (VIX futures before 2004-03): the modelled stretch is shown but
  cannot carry a verdict alone.
- F1-F3 pass but F4 or F5 fails: the synthetic tracks the fund but not the rule built on it. The long
  history stays "shape only", as in addendum 57, and the report says which bar failed and why.
- F1 or F2 fails: no faithful synthetic from the data reachable here. Report what data would fix it.

## Honesty box
A synthetic is the rule set and the data, not the fund: fees, roll timing, collateral yield and tracking
differences are approximations, and a fit on five years does not prove the same fidelity in 1995. Markets
that did not trade cannot be replicated, only modelled. Nothing here is a forecast. Any change to a live
symphony remains the owner's decision, on both brokers, with the logic book updated.
