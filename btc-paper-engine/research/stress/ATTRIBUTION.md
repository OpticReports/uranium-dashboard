# ATTRIBUTION - where the crash damage came from (K 0.75, offset 0, headline funding)

Source: `python3 attribution.py` -> `attribution.json` (re-runs the headline runs with the harness's
new per-bar per-leg MTM; reproduces results.json to the cent; every decomposition closes to <= $0.01).
Basis: mark-to-market; 12m = balance at day 365 (exactness on the bar's CLOSE: 2008 / 1999 are the
exact day-365 close; COVID is the bar opening on day 365, closing 4h after it, `12m*`). "Pullback" =
S3 leg, "trend" = S4 leg; P&L per leg is net of its own fees and BTC
perp funding; carry = the ETH sleeve (BitMEX XBTUSD proxy funding). Start 100,000 = BTC book 70,000 +
carry 30,000.

## COVID-like (BTC -56% in 32 days, then +355% at 12m) - 12m 115,987 (+15,987), maxDD -21.0%

| mechanism | 12m $ | in the maxDD window $ | detail |
|---|---|---|---|
| (a) pullback, before S3 halt | **-15,359** | -9,691 | 8 trades: 6 STOP-outs -18,035 (2 longs in the first drop -4,011; 4 shorts stopped by V-rallies -14,024, the 11-12 short alone -5,577 at size_mult 0.50), 2 SIGNAL wins +2,676 |
| (a) pullback, after S3 halt (11-30, margin -1,016, knife-edge) | 0 | 0 | 25 engine trades dropped; **forgone +12,207** (no-halt counterfactual 12m 128,193, maxDD -16.1%): the halt cost the 2020H2 recovery |
| (b) trend | **+27,169** | -15,289 | 6 winners +50,349 (crash short 10-08..11-12 +11,386 after a 6,859 trail give-back from its 11-08 MTM peak; recovery longs +17,366 and +11,807); 19 stop-outs after reversals -27,602; in the DD window 13 of 17 closed trades lost; longest losing streak 5 trades -5,782 (01-02..03-03) was followed by a +4,698 long |
| (c) daily-loss halt | 0 | 0 | never fired; rail 59% used (closest 6,116 of 15,000 on 11-12 20:00, worst intrabar day -8,884) |
| (d) drawdown halt | 0 | 0 | never fired; rail 90% used (closest 3,051 of 30,000 on 05-27 20:00) |
| (e) carry sleeve | **+4,176** | +1,230 | funding +4,376, fees -200, 4 flips, on 63% of bars, worst dip 0 |
| (f) fees / BTC funding | -993 / -2,820 | -531 / -913 | fees pullback 404 trend 589; funding pullback -547 trend -2,273 (inside the leg figures above) |
| **total** | **+15,987** | **-23,749** (112,972 on 11-08 -> 89,223 on 05-27) | |

Earned: trend +54,636 on its winners (the crash short, then the two recovery longs); pullback only
+2,676. The DD trough is six months after the crash low: the crash itself was survived with the
trend short; the drawdown was made by the pullback's short stop-outs in the V (Nov) and then the
trend's 13 whipsaw losses in the Dec-May chop while the pullback leg was halted.

## 2008-like (BTC -74% over 7 months, -73% at 12m) - 12m* 125,924 (+25,924), maxDD -8.2%

| mechanism | 12m $ | in the maxDD window $ | detail |
|---|---|---|---|
| (a) pullback (no S3 halt) | **+11,389** | -4,806 | 42 trades: 25 SIGNAL wins +54,847 (18 shorts +40,042), 17 STOP-outs -43,458 (7 longs -18,364, 9 shorts -24,737, 1 seam re-mirror -357); the DD window's 3 stop-outs are the Aug-Sep 2027 ones at size_mult 1.00 |
| (b) trend | **+14,352** | -6,276 | 10 winners +31,757 (three crash shorts +8,306 / +6,821 / +6,056), 16 stop-outs -20,066; crash phase +18,856, after the low -7,165; give-back on the first short 2,455 |
| (c) daily-loss halt | 0 | 0 | never fired; rail 34% used (closest 9,974 on 2027-08-07) |
| (d) drawdown halt | 0 | 0 | never fired; rail 44% used |
| (e) carry sleeve | +183 | 0 | gate ON only 10% of bars (XBTUSD funding negative through the bleed); 1 flip |
| (f) fees / BTC funding | -2,794 / -482 | -456 / -79 | fees pullback 2,200 (84 fills) trend 595; funding pullback -167 trend -315 |
| **total** | **+25,924** | **-11,082** (135,342 on 08-05 -> 124,260 on 09-11) | |

Earned: both legs; the trend's crash shorts and the pullback's 18 winning shorts in the bear. The
slow bleed is the engine's home ground: nothing here needs a guard.

## 1999/2000-like (BTC -84% over 12 months, no recovery) - 12m* 116,600 (+16,600), maxDD -13.6%

| mechanism | 12m $ | in the maxDD window $ | detail |
|---|---|---|---|
| (a) pullback, before S3 halt | **-16,618** | -9,491 | 7 trades: 5 STOP-outs -19,871 (2 longs on days 1-2 -7,964 at size_mult 1.00; 3 shorts stopped by bear rallies -11,907 at 0.50), 2 wins +3,253 |
| (a) pullback, after S3 halt (12-08, margin -3,416, firm) | 0 | 0 | 30 engine trades dropped; **saved 11,160** (no-halt counterfactual 12m 105,439, maxDD -17.4%): the leg kept losing in the grind |
| (b) trend | **+30,577** | -5,536 | 12 winners +30,383 + open short +15,124 (entered 09-05, the final capitulation), 12 stop-outs -14,930; give-back on the 10-30..12-01 short 3,432; pays -5,411 of funding (shorts held through -31.6%/yr stamps, longs through +27.8%/yr) |
| (c) daily-loss halt | 0 | 0 | never fired; rail 47% used (closest 7,949 on 2026-10-26, worst intrabar day -7,051) |
| (d) drawdown halt | 0 | 0 | never fired; rail 59% used |
| (e) carry sleeve | **+2,641** | +1,093 | funding +2,944, fees -303, 9 flips, on 39% of bars; worst dip -19 |
| (f) fees / BTC funding | -897 / -5,008 | -239 / +981 | fees pullback 342 trend 555; funding pullback +403 trend -5,411 |
| **total** | **+16,600** | **-13,934** (102,382 on 10-21 -> 88,448 on 12-27) | |

Earned: trend shorts (+45,507 on winners incl. the open one); the pullback earned +3,253 on two
trades and lost on five.

## Ranking across the three paths (what to attack)

1. **Pullback stop-outs in the crash regime.** -18,035 (COVID) / -19,871 (1999) / -4,806 in the 2008
   DD window; the leading item of every maxDD window (-9.7k of -23.7k, -9.5k of -13.9k, -4.8k of
   -11.1k). The live vol target lags: it reads 1.00 on days 1-2 of each crash (sigma_now is a 30-day
   window) when the first longs are stopped for -3k to -4.6k each, and bottoms at its 0.50 floor
   while the 4h ATR is 4-6x its normal level (the 11-12 COVID short lost 14% of notional inside one
   day). Second feature: the stops cluster - 2 to 3 consecutive STOP exits within days, every one
   at the same regime (COVID 10-07/10-08, 11-25/11-26; 1999 10-08 x2, 12-04/12-06; 2008 10-07/10-08,
   03-04/03-05, 08-07/08-08).
2. **Trend stop-outs after reversals.** -27,602 (COVID, 19 trades) / -20,066 (2008) / -14,930 (1999),
   incl. the trail give-back on the crash short (6.9k / 2.5k / 3.4k). Not a candidate: the trend
   leg is the net earner on all three paths (+27.2k / +14.4k / +30.6k) and its winners follow its
   losing streaks (COVID: the 5-trade -5.8k streak was followed by +4.7k; the +17.4k and +11.8k
   recovery longs came out of the chop). A damper or brake on its re-entries halves the winners
   that pay for the streaks; the trail give-back is the 5-ATR trail's price for riding the crash.
3. **BTC perp funding** -2.8k / -0.5k / -5.0k, mostly the trend leg (funding follows the trend, so
   it pays on both sides). Not a logic change; a venue cost.
4. **S3 paper-book halt**: +/-12k with the sign set by the path (cost 12.2k in COVID, saved 11.2k in
   1999), a 0.9%-of-peak knife-edge in COVID and the open P1 key input (seam). Cannot be settled on
   these paths (REVIEW.md) - not a candidate.
5. **Carry sleeve**: a contributor on every path (+4.2k / +0.2k / +2.6k; worst dip -19). A faster
   disarm would only cut income here - not a candidate.
6. **Executor halts**: none fired in 83 runs (daily rail <= 64%, drawdown rail <= 90%). A crash-mode
   re-arm rule or a drawdown auto-resume cannot change any number on these paths - not a candidate.
7. Fees -1.0k / -2.8k / -0.9k.

Honesty: three spliced paths, in-sample for the trend leg on COVID and 1999 (fit window 2013-21),
quasi-OOS on 2008; the pullback (fitted 2024-26) is OOS on all three. The ranking above was read off
these paths after the fact; the candidates in CANDIDATES.md are therefore selected in-sample and
their parameters are fixed from the leg's own statistics on real history, not from the outcomes.
