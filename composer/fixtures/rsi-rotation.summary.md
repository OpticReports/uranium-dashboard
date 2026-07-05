# RSI rotation symphony — logic tree

- Symphony ID: `rhZ9oDAUvN26v5Ra5qql`
- Name: Simons KMLM switcher (single pops) | BT 4/13/22 = A.R. 466% / D.D. 22% V2 (Buy Copy)
- Captured: 2026-07-05 (read-only baseline, Step D)
- Source: `GET /api/v0.1/symphonies/{id}/score` (Composer REST API — the MCP
  endpoint at ai.composer.trade was offline; see CHANGELOG)
- Raw definition: [`rsi-rotation.raw.json`](rsi-rotation.raw.json) (volatile
  `price`/`dollar_volume` fields stripped)

Notation: `RSI(10d) of QQQE` = 10-day relative strength index of QQQE.
Conditions evaluate top to bottom; the first matching branch wins.
Rebalance is threshold-based (corridor width 0.1), checked daily.

> **Note:** this symphony contains **no SPY 200-day moving-average gate** —
> every condition in the tree is a 10-day RSI test (the SPY gate is
> `RSI(10d) of SPY > 80`). If a 200d-MA-gated variant exists, it is a
> different symphony/version than the one currently saved under this ID.

## Structure at a glance

1. **Overbought scan → volatility pop:** eleven RSI(10d) > ~79–80 checks
   (QQQE, VTV, VOX, TECL, VOOG, VOOV, XLP@75, TQQQ, XLY, FAS, SPY) — any hit
   holds **UVXY**.
2. **Oversold scan → buy-the-dip ("Combined Pop Bot"):** TQQQ<30 → TECL,
   SOXL<30 → SOXL, SPXL<30 → SPXL, LABU<25 → LABU.
3. **Default — KMLM switcher:** if RSI(10d) XLK > RSI(10d) KMLM (risk-on),
   hold the bottom-2-RSI of {TECL, SOXL, SVIX}; otherwise (risk-off) hold the
   top-1-RSI of {SQQQ, TLT}.

## Full tree

**Simons KMLM switcher (single pops)| BT 4/13/22 = A.R. 466% / D.D. 22% V2 (Buy Copy)**  
rebalance: none, corridor width: 0.1

- group: "KMLM switcher (single pops)| BT 4/13/22 = A.R. 466% / D.D. 22%"
  - **if** RSI(10d) of QQQE > 79:
    - hold **UVXY** (ProShares Ultra VIX Short-Term Futures ETF)
  - **else**:
    - **if** RSI(10d) of VTV > 79:
      - hold **UVXY** (ProShares Ultra VIX Short-Term Futures ETF)
    - **else**:
      - **if** RSI(10d) of VOX > 79:
        - hold **UVXY** (ProShares Ultra VIX Short-Term Futures ETF)
      - **else**:
        - **if** RSI(10d) of TECL > 79:
          - hold **UVXY** (ProShares Ultra VIX Short-Term Futures ETF)
        - **else**:
          - **if** RSI(10d) of VOOG > 79:
            - hold **UVXY** (ProShares Ultra VIX Short-Term Futures ETF)
          - **else**:
            - **if** RSI(10d) of VOOV > 79:
              - hold **UVXY** (ProShares Ultra VIX Short-Term Futures ETF)
            - **else**:
              - **if** RSI(10d) of XLP > 75:
                - hold **UVXY** (ProShares Ultra VIX Short-Term Futures ETF)
              - **else**:
                - **if** RSI(10d) of TQQQ > 79:
                  - hold **UVXY** (ProShares Ultra VIX Short-Term Futures ETF)
                - **else**:
                  - **if** RSI(10d) of XLY > 80:
                    - hold **UVXY** (ProShares Ultra VIX Short-Term Futures ETF)
                  - **else**:
                    - **if** RSI(10d) of FAS > 80:
                      - hold **UVXY** (ProShares Ultra VIX Short-Term Futures ETF)
                    - **else**:
                      - **if** RSI(10d) of SPY > 80:
                        - hold **UVXY** (ProShares Ultra VIX Short-Term Futures ETF)
                      - **else**:
                        - group: "Combined Pop Bot"
                          - **if** RSI(10d) of TQQQ < 30:
                            - hold **TECL** (Direxion Daily Technology Bull 3x Shares)
                          - **else**:
                            - **if** RSI(10d) of SOXL < 30:
                              - hold **SOXL** (Direxion Daily Semiconductor Bull 3x Shares)
                            - **else**:
                              - **if** RSI(10d) of SPXL < 30:
                                - hold **SPXL** (Direxion Daily S&P 500 Bull 3x Shares)
                              - **else**:
                                - **if** RSI(10d) of LABU < 25:
                                  - hold **LABU** (Direxion Daily S&P Biotech Bull 3X Shares)
                                - **else**:
                                  - group: "KMLM switcher: TECL, SVIX, or L/S Rotator | BT 4/13/22 = AR 164% / DD 22.2%"
                                    - **if** RSI(10d) of XLK > RSI(10d) of KMLM:
                                      - filter — pick bottom 2 by RSI(10d) of each candidate, from:
                                        - hold **TECL** (Direxion Daily Technology Bull 3x Shares)
                                        - hold **SOXL** (Direxion Daily Semiconductor Bull 3x Shares)
                                        - hold **SVIX** (-1x Short VIX Futures ETF)
                                    - **else**:
                                      - filter — pick top 1 by RSI(10d) of each candidate, from:
                                        - hold **SQQQ** (ProShares UltraPro Short QQQ)
                                        - hold **TLT** (iShares 20+ Year Treasury Bond ETF)
