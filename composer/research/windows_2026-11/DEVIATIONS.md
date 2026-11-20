# Deviations from PREREG.md (each recorded before the affected number was computed, unless it says otherwise)

1. **G4 reads "fail" for HG on one fund and is accepted.** BIL shows 10 consecutive unchanged adjusted
   closes to 2015-10-19: a T-bill fund at a zero rate, not stale data. No other series trips it. Recorded
   after the gate ran, before any variant was simulated.
2. **The sleeve tree has 15 return-ranked picks, not the 16 the first tree dump suggested** (one of the 16
   filters ranks by volatility and is not varied). The cell list is unchanged.
