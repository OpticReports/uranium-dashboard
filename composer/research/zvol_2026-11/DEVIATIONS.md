# Deviations from PREREG.md (logged as they arose)

1. Haircut lens. PREREG says the switcher's daily return is "multiplied down" with "volatility and drawdown
   shape kept"; those two cannot both hold. Implemented as a constant daily log-return shift (volatility
   kept, mean cut). The KMLM symphony gets the same shift on its switcher share only.
2. The switcher's backtest CAGR quoted in PREREG (+538%/yr) is its 2022-04+ window; over the matched real
   era (2023-04-20+) it is +295%/yr. The haircut targets (its live pace +63.8%/yr, and half) are unchanged.
3. Q2 placebo: every circular shift from 20 to n-20 sessions (859 in the real era; about 1,000 evenly
   spaced on longer paths) instead of 5,000 random ones; the full set is the stronger test.
4. Q2 "timing out of sample" and Q3 run on a 2006-07..2026-11 path the pre-registration called the
   "long history (Q5 path)": the exact rule simulated on real funds where they exist and on calibrated
   proxies before (sim.py header). The simulator reproduces Composer's HARV weights on 899 of 899
   real-era sessions.
5. Q5 sample starts 2008-01-02 (first VIX6M print), not the start of the futures archive.
6. Q6 R2 (carry gate) was not run: the only predictor that passed the Q5 bar is SPY RSI(2), the rule's
   own trigger. This is the pre-registered branch.
7. Q4 live window: the pure switcher's returns in books B, C and D are the model's on those dates (no
   live pure-switcher account exists); all other engines are live.
8. Added, EXPLORATORY and labelled so: a volatility-matched book (q7_extra.py a), the rolling one-year
   return of the rule (b), and the dollars going ex-distribution on 2026-11-18 (c).
9. The live symphony series runs to 2026-11-17; Composer's symphony-stats on 2026-11-18 (intraday, an
   ex-distribution day for ZVOL) is quoted only as "what the app shows today".
