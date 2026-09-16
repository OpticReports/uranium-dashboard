# BLOCK event — results (spec v1, run 2026-09-15)

Inputs: frozen `panel.csv` (1946-01..2026-08), `events.json`. Oil = FRED WTISPLC monthly spot (D1/D2/D3), WPU0561 PPI crude as the pre-1983 companion. Curve = GS10−TB3MS (`spread_gs`). Resolved month for horizon h: t + h ≤ 2025-08. Common NBER window: ON months 1953-04..last resolved; onsets 1953-08..2020-03 (11). Base rate = share of resolved USREC=0 months in the window with an onset in t+1..t+h.

## 1. Instrument agreement (reported BEFORE any result)

### 1(i) D1 grade: monthly-mean `oil_12m_pct` vs deployed point construction `wti_daily_252_pct`, month-ends 1987-01..2026-08

- months compared: 476; 3-level grade agreement 92.4%; ON/OFF (ON = RED) agreement **96.4%** (disagreements: 10 live-RED/panel-not, 7 panel-RED/live-not).
- Verdict: ≥ 90% → the monthly-mean construction STANDS for the overlap (spec §4 D1 clause not triggered).

Live-RED / panel-not-RED months:

| month | daily 252-obs % | grade | monthly-mean 12m % | grade |
|---|---|---|---|---|
| 1987-03 | 65.8 | red | 45.1 | yellow |
| 1987-06 | 53.9 | red | 48.7 | yellow |
| 1989-09 | 55.1 | red | 35.4 | yellow |
| 2000-08 | 50.9 | red | 46.8 | yellow |
| 2000-10 | 51.5 | red | 46.1 | yellow |
| 2005-03 | 55.3 | red | 47.7 | yellow |
| 2005-06 | 59.1 | red | 48.0 | yellow |
| 2005-08 | 62.2 | red | 44.6 | yellow |
| 2007-10 | 61.2 | red | 46.4 | yellow |
| 2007-12 | 57.7 | red | 47.9 | yellow |

Panel-RED / live-not-RED months:

| month | daily 252-obs % | grade | monthly-mean 12m % | grade |
|---|---|---|---|---|
| 1990-11 | 42.2 | yellow | 63.0 | red |
| 2002-12 | 48.1 | yellow | 52.2 | red |
| 2007-11 | 40.7 | yellow | 59.4 | red |
| 2018-07 | 39.2 | yellow | 52.2 | red |
| 2021-11 | 45.1 | yellow | 93.3 | red |
| 2022-06 | 47.3 | yellow | 60.9 | red |
| 2026-05 | 45.0 | yellow | 64.3 | red |

All 3-level grade disagreements (36 months): 1987-03 (live red/panel yellow), 1987-06 (live red/panel yellow), 1987-08 (live benign/panel yellow), 1989-06 (live yellow/panel benign), 1989-07 (live benign/panel yellow), 1989-08 (live yellow/panel benign), 1989-09 (live red/panel yellow), 1989-12 (live benign/panel yellow), 1990-11 (live yellow/panel red), 1991-05 (live yellow/panel benign), 1994-12 (live yellow/panel benign), 2000-08 (live red/panel yellow), 2000-10 (live red/panel yellow), 2002-09 (live yellow/panel benign), 2002-10 (live benign/panel yellow), 2002-12 (live yellow/panel red), 2003-03 (live benign/panel yellow), 2005-03 (live red/panel yellow), 2005-05 (live yellow/panel benign), 2005-06 (live red/panel yellow), 2005-08 (live red/panel yellow), 2006-02 (live benign/panel yellow), 2007-10 (live red/panel yellow), 2007-11 (live yellow/panel red), 2007-12 (live red/panel yellow), 2011-07 (live benign/panel yellow), 2017-04 (live benign/panel yellow), 2017-11 (live yellow/panel benign), 2018-07 (live yellow/panel red), 2018-10 (live benign/panel yellow), 2019-12 (live yellow/panel benign), 2021-02 (live yellow/panel benign), 2021-11 (live yellow/panel red), 2022-06 (live yellow/panel red), 2026-05 (live yellow/panel red), 2026-07 (live yellow/panel benign)

### 1(ii) Curve flat: `curve_flat_gs6m` (monthly, GS10−TB3MS) vs `curve_flat_daily183` (deployed daily rule), 1982-01..2026-08

- months compared: 536; agreement **91.0%**; disagreements 48 (48 daily-flat/monthly-not, 0 monthly-flat/daily-not).
- Named disagreement months: 1982-02 (daily flat only), 1982-03 (daily flat only), 1982-04 (daily flat only), 1982-05 (daily flat only), 1982-06 (daily flat only), 1982-07 (daily flat only), 1982-08 (daily flat only), 1982-09 (daily flat only), 1989-02 (daily flat only), 1989-03 (daily flat only), 1989-04 (daily flat only), 1989-05 (daily flat only), 1990-06 (daily flat only), 1995-12 (daily flat only), 1996-01 (daily flat only), 1996-02 (daily flat only), 1996-03 (daily flat only), 1996-04 (daily flat only), 1996-05 (daily flat only), 1998-01 (daily flat only), 1998-02 (daily flat only), 1998-03 (daily flat only), 1998-04 (daily flat only), 1998-05 (daily flat only), 1998-06 (daily flat only), 1998-07 (daily flat only), 1998-08 (daily flat only), 1999-03 (daily flat only), 1999-04 (daily flat only), 1999-05 (daily flat only), 1999-06 (daily flat only), 1999-07 (daily flat only), 2000-03 (daily flat only), 2000-04 (daily flat only), 2000-05 (daily flat only), 2000-06 (daily flat only), 2001-08 (daily flat only), 2008-01 (daily flat only), 2008-02 (daily flat only), 2018-12 (daily flat only), 2019-01 (daily flat only), 2019-02 (daily flat only), 2020-08 (daily flat only), 2022-07 (daily flat only), 2022-08 (daily flat only), 2022-09 (daily flat only), 2022-10 (daily flat only), 2026-04 (daily flat only)

### 1(iii) Flat condition (6-month min < 0.25) on `spread_cmt` (T10Y3M, CMT) vs `spread_gs` (GS10−TB3MS), 1982-06..2026-08

- months compared: 531; agreement 97.0%; **16 disagreement months** (16 CMT-flat only, 0 GS-flat only).
- Named: 1982-06 (CMT flat only), 1982-07 (CMT flat only), 1989-03 (CMT flat only), 1989-04 (CMT flat only), 1989-05 (CMT flat only), 1999-03 (CMT flat only), 1999-04 (CMT flat only), 1999-05 (CMT flat only), 2000-04 (CMT flat only), 2000-05 (CMT flat only), 2000-06 (CMT flat only), 2019-02 (CMT flat only), 2022-08 (CMT flat only), 2022-09 (CMT flat only), 2022-10 (CMT flat only), 2026-04 (CMT flat only)
- The spec's data audit counted 17; this recount on the frozen panel (6-month min requires 6 CMT months, so 1982-01..05 are not comparable) finds 16. Every disagreement is CMT-flat-only, consistent with CMT − (GS10−TB3MS) averaging −0.12pp. 2026-04 is one of them: the CMT basis and the deployed daily rule (§1(ii)) both read the curve as flat in 2026-04; the fit basis `spread_gs` does not.

## 2. Expected episode lists (pre-outcome record; §4 episode rule)

Rule: ON months; consecutive ON months separated by ≤ 6 OFF months form one episode; membership = USREC_t = 0 months (in-recession ON months are listed in the span but excluded from n and from every numerator/denominator). `start` = first ON month with USREC=0; `raw span` includes in-recession ON months; peak = max reading over the whole span.

### D1-RED — `oil_12m_pct` ≥ 50 (primary); series starts 1947-01

| start (USREC=0) | end (USREC=0) | n ON (USREC=0) | raw span (all ON) | n ON (all) | peak | peak month | regime |
|---|---|---|---|---|---|---|---|
| 1948-01 | 1948-03 | 3 | 1948-01..1948-03 | 3 | 58.6 | 1948-01 | R0 |
| — | — | 0 | 1974-01..1974-12 | 12 | 184.0 | 1974-01 | R0 |
| 1979-08 | 1980-01 | 6 | 1979-08..1980-07 | 12 | 149.2 | 1980-04 | R0 |
| 1987-07 | 1987-07 | 1 | 1987-07..1987-07 | 1 | 84.5 | 1987-07 | R1 |
| — | — | 0 | 1990-09..1990-11 | 3 | 78.8 | 1990-10 | R1 |
| 1999-08 | 2000-06 | 10 | 1999-08..2000-06 | 10 | 144.4 | 2000-02 | R1 |
| 2002-12 | 2003-02 | 3 | 2002-12..2003-02 | 3 | 73.0 | 2003-02 | R1 |
| 2004-09 | 2004-11 | 3 | 2004-09..2004-11 | 3 | 75.2 | 2004-10 | R1 |
| 2007-11 | 2007-11 | 1 | 2007-11..2008-08 | 9 | 98.5 | 2008-06 | R1 |
| 2009-12 | 2010-04 | 5 | 2009-12..2010-04 | 5 | 95.1 | 2010-02 | R2 |
| 2017-01 | 2017-02 | 2 | 2017-01..2017-02 | 2 | 76.4 | 2017-02 | R2 |
| 2018-06 | 2018-07 | 2 | 2018-06..2018-07 | 2 | 52.2 | 2018-07 | R2 |
| 2021-03 | 2022-06 | 16 | 2021-03..2022-06 | 16 | 272.9 | 2021-04 | R3 |
| 2026-04 | 2026-05 | 2 | 2026-04..2026-05 | 2 | 64.3 | 2026-05 | R3 |

### D1-YELLOW — `oil_12m_pct` ≥ 25 (secondary); series starts 1947-01

| start (USREC=0) | end (USREC=0) | n ON (USREC=0) | raw span (all ON) | n ON (all) | peak | peak month | regime |
|---|---|---|---|---|---|---|---|
| 1947-01 | 1948-10 | 19 | 1947-01..1948-10 | 19 | 58.6 | 1948-01 | R0 |
| — | — | 0 | 1974-01..1974-12 | 12 | 184.0 | 1974-01 | R0 |
| 1979-06 | 1980-09 | 10 | 1979-06..1980-09 | 16 | 149.2 | 1980-04 | R0 |
| 1987-03 | 1987-10 | 8 | 1987-03..1987-10 | 8 | 84.5 | 1987-07 | R1 |
| 1989-07 | 1990-01 | 6 | 1989-07..1990-12 | 11 | 78.8 | 1990-10 | R1 |
| 1995-02 | 1995-03 | 2 | 1995-02..1995-03 | 2 | 26.5 | 1995-03 | R1 |
| 1996-09 | 1997-01 | 5 | 1996-09..1997-01 | 5 | 42.8 | 1996-10 | R1 |
| 1999-06 | 2000-11 | 18 | 1999-06..2000-11 | 18 | 144.4 | 2000-02 | R1 |
| 2002-10 | 2003-03 | 6 | 2002-10..2003-03 | 6 | 73.0 | 2003-02 | R1 |
| 2004-04 | 2006-07 | 23 | 2004-04..2006-07 | 23 | 75.2 | 2004-10 | R1 |
| 2007-09 | 2007-12 | 4 | 2007-09..2008-09 | 13 | 98.5 | 2008-06 | R1 |
| 2009-11 | 2010-04 | 6 | 2009-11..2010-04 | 6 | 95.1 | 2010-02 | R2 |
| 2011-03 | 2011-07 | 5 | 2011-03..2011-07 | 5 | 37.2 | 2011-05 | R2 |
| 2016-12 | 2017-04 | 5 | 2016-12..2017-04 | 5 | 76.4 | 2017-02 | R2 |
| 2018-03 | 2018-10 | 8 | 2018-03..2018-10 | 8 | 52.2 | 2018-07 | R2 |
| 2021-03 | 2022-08 | 18 | 2021-03..2022-08 | 18 | 272.9 | 2021-04 | R3 |
| 2026-03 | 2026-08 | 4 | 2026-03..2026-08 | 4 | 64.3 | 2026-05 | R3 |

### D2 — `nopi36_sum12` ≥ 10 (primary); series starts 1949-12

| start (USREC=0) | end (USREC=0) | n ON (USREC=0) | raw span (all ON) | n ON (all) | peak | peak month | regime |
|---|---|---|---|---|---|---|---|
| 1973-08 | 1973-11 | 4 | 1973-08..1974-12 | 17 | 104.4 | 1974-01 | R0 |
| 1976-09 | 1977-08 | 12 | 1976-09..1977-08 | 12 | 22.0 | 1976-09 | R0 |
| 1979-05 | 1981-01 | 15 | 1979-05..1981-01 | 21 | 91.3 | 1980-04 | R0 |
| 1991-04 | 1991-08 | 5 | 1990-08..1991-08 | 13 | 52.0 | 1990-10 | R1 |
| 1996-04 | 1997-03 | 12 | 1996-04..1997-03 | 12 | 22.1 | 1996-12 | R1 |
| 2000-02 | 2001-03 | 14 | 2000-02..2001-05 | 16 | 30.4 | 2000-11 | R1 |
| 2004-05 | 2007-12 | 38 | 2004-05..2009-04 | 54 | 58.8 | 2008-06 | R1 |
| 2018-04 | 2019-03 | 12 | 2018-04..2019-03 | 12 | 17.1 | 2018-07 | R2 |
| 2021-10 | 2023-02 | 17 | 2021-10..2023-02 | 17 | 47.6 | 2022-06 | R3 |
| 2026-04 | 2026-08 | 5 | 2026-04..2026-08 | 5 | 13.3 | 2026-05 | R3 |

### D3-RED — `real_oil_12m_pct` ≥ 50 (primary); series starts 1948-01

| start (USREC=0) | end (USREC=0) | n ON (USREC=0) | raw span (all ON) | n ON (all) | peak | peak month | regime |
|---|---|---|---|---|---|---|---|
| — | — | 0 | 1974-01..1974-12 | 12 | 159.1 | 1974-01 | R0 |
| 1979-08 | 1980-01 | 6 | 1979-08..1980-07 | 12 | 117.5 | 1980-04 | R0 |
| 1987-07 | 1987-07 | 1 | 1987-07..1987-07 | 1 | 77.5 | 1987-07 | R1 |
| — | — | 0 | 1990-09..1990-11 | 3 | 68.1 | 1990-10 | R1 |
| 1999-08 | 2000-06 | 10 | 1999-08..2000-06 | 10 | 136.8 | 2000-02 | R1 |
| 2003-01 | 2003-02 | 2 | 2003-01..2003-02 | 2 | 67.7 | 2003-02 | R1 |
| 2004-09 | 2004-11 | 3 | 2004-09..2004-11 | 3 | 69.8 | 2004-10 | R1 |
| 2007-11 | 2007-11 | 1 | 2007-11..2008-08 | 9 | 89.8 | 2008-05 | R1 |
| 2009-12 | 2010-04 | 5 | 2009-12..2010-04 | 5 | 91.0 | 2010-02 | R2 |
| 2017-01 | 2017-02 | 2 | 2017-01..2017-02 | 2 | 71.5 | 2017-02 | R2 |
| 2021-03 | 2022-05 | 12 | 2021-03..2022-05 | 12 | 258.1 | 2021-04 | R3 |
| 2026-04 | 2026-05 | 2 | 2026-04..2026-05 | 2 | 57.7 | 2026-05 | R3 |

### D3-YELLOW — `real_oil_12m_pct` ≥ 25 (secondary); series starts 1948-01

| start (USREC=0) | end (USREC=0) | n ON (USREC=0) | raw span (all ON) | n ON (all) | peak | peak month | regime |
|---|---|---|---|---|---|---|---|
| 1948-01 | 1948-10 | 10 | 1948-01..1948-10 | 10 | 48.5 | 1948-03 | R0 |
| — | — | 0 | 1974-01..1974-12 | 12 | 159.1 | 1974-01 | R0 |
| 1979-07 | 1980-08 | 8 | 1979-07..1980-08 | 14 | 117.5 | 1980-04 | R0 |
| 1987-03 | 1987-10 | 7 | 1987-03..1987-10 | 7 | 77.5 | 1987-07 | R1 |
| 1989-09 | 1989-11 | 3 | 1989-09..1989-11 | 3 | 39.2 | 1989-10 | R1 |
| — | — | 0 | 1990-08..1990-11 | 4 | 68.1 | 1990-10 | R1 |
| 1996-09 | 1997-01 | 5 | 1996-09..1997-01 | 5 | 38.5 | 1996-10 | R1 |
| 1999-06 | 2000-11 | 18 | 1999-06..2000-11 | 18 | 136.8 | 2000-02 | R1 |
| 2002-10 | 2003-03 | 6 | 2002-10..2003-03 | 6 | 67.7 | 2003-02 | R1 |
| 2004-04 | 2006-05 | 20 | 2004-04..2006-05 | 20 | 69.8 | 2004-10 | R1 |
| 2007-10 | 2007-12 | 3 | 2007-10..2008-08 | 11 | 89.8 | 2008-05 | R1 |
| 2009-11 | 2010-04 | 6 | 2009-11..2010-04 | 6 | 91.0 | 2010-02 | R2 |
| 2011-04 | 2011-05 | 2 | 2011-04..2011-05 | 2 | 32.6 | 2011-05 | R2 |
| 2016-12 | 2017-03 | 4 | 2016-12..2017-03 | 4 | 71.5 | 2017-02 | R2 |
| 2018-04 | 2018-10 | 7 | 2018-04..2018-10 | 7 | 48.0 | 2018-07 | R2 |
| 2021-03 | 2022-08 | 18 | 2021-03..2022-08 | 18 | 258.1 | 2021-04 | R3 |
| 2026-03 | 2026-08 | 4 | 2026-03..2026-08 | 4 | 57.7 | 2026-05 | R3 |

### PPI-RED — `ppi_crude_12m_pct` ≥ 50 (robustness (pre-1983 companion of D1-RED)); series starts 1948-01

| start (USREC=0) | end (USREC=0) | n ON (USREC=0) | raw span (all ON) | n ON (all) | peak | peak month | regime |
|---|---|---|---|---|---|---|---|
| 1948-01 | 1948-02 | 2 | 1948-01..1948-02 | 2 | 57.5 | 1948-01 | R0 |
| — | — | 0 | 1974-01..1974-12 | 12 | 78.5 | 1974-08 | R0 |
| 1979-12 | 1980-01 | 2 | 1979-12..1980-06 | 7 | 63.6 | 1980-04 | R0 |
| 1981-02 | 1981-05 | 4 | 1981-02..1981-05 | 4 | 63.7 | 1981-02 | R0 |
| 1987-07 | 1987-08 | 2 | 1987-07..1987-08 | 2 | 69.7 | 1987-08 | R1 |
| — | — | 0 | 1990-09..1990-11 | 3 | 104.9 | 1990-10 | R1 |
| 1999-08 | 2000-10 | 14 | 1999-08..2000-10 | 14 | 218.7 | 2000-02 | R1 |
| 2002-12 | 2003-02 | 3 | 2002-12..2003-02 | 3 | 77.9 | 2003-02 | R1 |
| 2004-09 | 2005-07 | 5 | 2004-09..2005-07 | 5 | 71.2 | 2004-10 | R1 |
| 2007-11 | 2007-12 | 2 | 2007-11..2008-08 | 10 | 107.2 | 2008-06 | R1 |
| 2009-12 | 2010-04 | 5 | 2009-12..2010-04 | 5 | 129.3 | 2010-01 | R2 |
| 2017-01 | 2017-02 | 2 | 2017-01..2017-02 | 2 | 106.2 | 2017-02 | R2 |
| 2018-05 | 2018-07 | 3 | 2018-05..2018-07 | 3 | 63.6 | 2018-07 | R2 |
| 2021-03 | 2022-06 | 16 | 2021-03..2022-06 | 16 | 260.0 | 2021-04 | R3 |
| 2026-04 | 2026-05 | 2 | 2026-04..2026-05 | 2 | 70.9 | 2026-05 | R3 |

### PPI-D2 — `ppi_nopi36_sum12` ≥ 10 (robustness (pre-1983 companion of D2)); series starts 1950-12

| start (USREC=0) | end (USREC=0) | n ON (USREC=0) | raw span (all ON) | n ON (all) | peak | peak month | regime |
|---|---|---|---|---|---|---|---|
| 1953-06 | 1953-07 | 2 | 1953-06..1954-01 | 8 | 10.8 | 1953-06 | R0 |
| 1973-09 | 1976-05 | 17 | 1973-09..1976-05 | 33 | 57.9 | 1974-08 | R0 |
| 1978-09 | 1981-07 | 24 | 1978-09..1982-01 | 36 | 49.3 | 1981-02 | R0 |
| 1991-04 | 1991-09 | 6 | 1990-08..1991-09 | 14 | 65.8 | 1990-10 | R1 |
| 1996-04 | 1997-08 | 17 | 1996-04..1997-08 | 17 | 23.7 | 1997-01 | R1 |
| 2000-02 | 2001-03 | 14 | 2000-02..2001-05 | 16 | 31.4 | 2000-11 | R1 |
| 2004-05 | 2007-12 | 38 | 2004-05..2009-04 | 54 | 64.3 | 2008-07 | R1 |
| 2018-04 | 2019-03 | 12 | 2018-04..2019-03 | 12 | 21.0 | 2018-10 | R2 |
| 2022-01 | 2023-05 | 17 | 2022-01..2023-05 | 17 | 46.8 | 2022-06 | R3 |
| 2026-04 | 2026-08 | 5 | 2026-04..2026-08 | 5 | 18.7 | 2026-05 | R3 |

## 3. Outcomes vs NBER onsets (h = 12 headline, h = 18 second)

Common window: ON months 1953-04..last resolved (h=12: 2024-08; h=18: 2024-02), USREC_t=0; onsets 1953-08..2020-03 (11). 1953-08 IS evaluable for every oil-alone rule (series start 1947-01/1948-01/1949-12 ≤ 1953-08 − 18). Hit = an event in (first ON, last ON + h]; coincident = raw first ON in [onset, onset+3]; 1981-08 scored only against ON months 1980-08..1981-07; PENDING = episode contains an unresolved month. Month-level precision = share of ON months (USREC=0, resolved) with an onset in t+1..t+h. Lead = months from the crediting episode's first ON month to the event; a NEGATIVE lead on a coincident row = months AFTER the onset that the rule first fired.

### 3.1 h = 12

**D1-RED** (h=12): episodes in window 13 = 3 hit, 7 false positive, 2 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 3/10 = 30.0%; recall 3/11; month-level precision 9/49 = 18.4% vs base 124/744 = 16.7% (excluding coincident-episode months: 9/49 = 18.4%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| (1974-01 in-recession) | 1974-01..1974-12 | 0 | 184.0 | COINCIDENT | coincident with 1973-12 | — |
| 1979-08 | 1979-08..1980-07 | 6 | 149.2 | HIT | 1980-02 | 6 |
| 1987-07 | 1987-07..1987-07 | 1 | 84.5 | FALSE POSITIVE | — | — |
| (1990-09 in-recession) | 1990-09..1990-11 | 0 | 78.8 | COINCIDENT | coincident with 1990-08 | — |
| 1999-08 | 1999-08..2000-06 | 10 | 144.4 | HIT | 2001-04 | 20 |
| 2002-12 | 2002-12..2003-02 | 3 | 73.0 | FALSE POSITIVE | — | — |
| 2004-09 | 2004-09..2004-11 | 3 | 75.2 | FALSE POSITIVE | — | — |
| 2007-11 | 2007-11..2008-08 | 1 | 98.5 | HIT | 2008-01 | 2 |
| 2009-12 | 2009-12..2010-04 | 5 | 95.1 | FALSE POSITIVE | — | — |
| 2017-01 | 2017-01..2017-02 | 2 | 76.4 | FALSE POSITIVE | — | — |
| 2018-06 | 2018-06..2018-07 | 2 | 52.2 | FALSE POSITIVE | — | — |
| 2021-03 | 2021-03..2022-06 | 16 | 272.9 | FALSE POSITIVE | — | — |
| 2026-04 | 2026-04..2026-05 | 2 | 64.3 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | MISSED | — | — | — |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | COINCIDENT | -1 | — | 1974-01 |
| 1980-02 | CAUGHT | 6 | 1 | 1979-08 |
| 1981-08 | MISSED | — | — | — |
| 1990-08 | COINCIDENT | -1 | — | 1990-09 |
| 2001-04 | CAUGHT | 20 | 10 | 1999-08 |
| 2008-01 | CAUGHT | 2 | 2 | 2007-11 |
| 2020-03 | MISSED | — | — | — |

**D1-YELLOW** (h=12): episodes in window 16 = 4 hit, 10 false positive, 1 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 4/14 = 28.6%; recall 5/11; month-level precision 27/124 = 21.8% vs base 124/744 = 16.7% (excluding coincident-episode months: 27/124 = 21.8%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| (1974-01 in-recession) | 1974-01..1974-12 | 0 | 184.0 | COINCIDENT | coincident with 1973-12 | — |
| 1979-06 | 1979-06..1980-09 | 10 | 149.2 | HIT | 1980-02, 1981-08 | 8 |
| 1987-03 | 1987-03..1987-10 | 8 | 84.5 | FALSE POSITIVE | — | — |
| 1989-07 | 1989-07..1990-12 | 6 | 78.8 | HIT | 1990-08 | 13 |
| 1995-02 | 1995-02..1995-03 | 2 | 26.5 | FALSE POSITIVE | — | — |
| 1996-09 | 1996-09..1997-01 | 5 | 42.8 | FALSE POSITIVE | — | — |
| 1999-06 | 1999-06..2000-11 | 18 | 144.4 | HIT | 2001-04 | 22 |
| 2002-10 | 2002-10..2003-03 | 6 | 73.0 | FALSE POSITIVE | — | — |
| 2004-04 | 2004-04..2006-07 | 23 | 75.2 | FALSE POSITIVE | — | — |
| 2007-09 | 2007-09..2008-09 | 4 | 98.5 | HIT | 2008-01 | 4 |
| 2009-11 | 2009-11..2010-04 | 6 | 95.1 | FALSE POSITIVE | — | — |
| 2011-03 | 2011-03..2011-07 | 5 | 37.2 | FALSE POSITIVE | — | — |
| 2016-12 | 2016-12..2017-04 | 5 | 76.4 | FALSE POSITIVE | — | — |
| 2018-03 | 2018-03..2018-10 | 8 | 52.2 | FALSE POSITIVE | — | — |
| 2021-03 | 2021-03..2022-08 | 18 | 272.9 | FALSE POSITIVE | — | — |
| 2026-03 | 2026-03..2026-08 | 4 | 64.3 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | MISSED | — | — | — |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | COINCIDENT | -1 | — | 1974-01 |
| 1980-02 | CAUGHT | 8 | 1 | 1979-06 |
| 1981-08 | CAUGHT | 26 | 11 | 1979-06 |
| 1990-08 | CAUGHT | 13 | 7 | 1989-07 |
| 2001-04 | CAUGHT | 22 | 5 | 1999-06 |
| 2008-01 | CAUGHT | 4 | 1 | 2007-09 |
| 2020-03 | MISSED | — | — | — |

**D2** (h=12): episodes in window 10 = 5 hit, 3 false positive, 1 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 5/8 = 62.5%; recall 6/11; month-level precision 38/129 = 29.5% vs base 124/744 = 16.7% (excluding coincident-episode months: 38/124 = 30.6%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| 1973-08 | 1973-08..1974-12 | 4 | 104.4 | HIT | 1973-12 | 4 |
| 1976-09 | 1976-09..1977-08 | 12 | 22.0 | FALSE POSITIVE | — | — |
| 1979-05 | 1979-05..1981-01 | 15 | 91.3 | HIT | 1980-02, 1981-08 | 9 |
| 1991-04 | 1990-08..1991-08 | 5 | 52.0 | COINCIDENT | coincident with 1990-08 | — |
| 1996-04 | 1996-04..1997-03 | 12 | 22.1 | FALSE POSITIVE | — | — |
| 2000-02 | 2000-02..2001-05 | 14 | 30.4 | HIT | 2001-04 | 14 |
| 2004-05 | 2004-05..2009-04 | 38 | 58.8 | HIT | 2008-01 | 44 |
| 2018-04 | 2018-04..2019-03 | 12 | 17.1 | HIT | 2020-03 | 23 |
| 2021-10 | 2021-10..2023-02 | 17 | 47.6 | FALSE POSITIVE | — | — |
| 2026-04 | 2026-04..2026-08 | 5 | 13.3 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | MISSED | — | — | — |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | CAUGHT | 4 | 1 | 1973-08 |
| 1980-02 | CAUGHT | 9 | 1 | 1979-05 |
| 1981-08 | CAUGHT | 27 | 7 | 1979-05 |
| 1990-08 | COINCIDENT | 0 | — | 1990-08 |
| 2001-04 | CAUGHT | 14 | 1 | 2000-02 |
| 2008-01 | CAUGHT | 44 | 1 | 2004-05 |
| 2020-03 | CAUGHT | 23 | 12 | 2018-04 |

**D3-RED** (h=12): episodes in window 12 = 3 hit, 6 false positive, 2 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 3/9 = 33.3%; recall 3/11; month-level precision 9/42 = 21.4% vs base 124/744 = 16.7% (excluding coincident-episode months: 9/42 = 21.4%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| (1974-01 in-recession) | 1974-01..1974-12 | 0 | 159.1 | COINCIDENT | coincident with 1973-12 | — |
| 1979-08 | 1979-08..1980-07 | 6 | 117.5 | HIT | 1980-02 | 6 |
| 1987-07 | 1987-07..1987-07 | 1 | 77.5 | FALSE POSITIVE | — | — |
| (1990-09 in-recession) | 1990-09..1990-11 | 0 | 68.1 | COINCIDENT | coincident with 1990-08 | — |
| 1999-08 | 1999-08..2000-06 | 10 | 136.8 | HIT | 2001-04 | 20 |
| 2003-01 | 2003-01..2003-02 | 2 | 67.7 | FALSE POSITIVE | — | — |
| 2004-09 | 2004-09..2004-11 | 3 | 69.8 | FALSE POSITIVE | — | — |
| 2007-11 | 2007-11..2008-08 | 1 | 89.8 | HIT | 2008-01 | 2 |
| 2009-12 | 2009-12..2010-04 | 5 | 91.0 | FALSE POSITIVE | — | — |
| 2017-01 | 2017-01..2017-02 | 2 | 71.5 | FALSE POSITIVE | — | — |
| 2021-03 | 2021-03..2022-05 | 12 | 258.1 | FALSE POSITIVE | — | — |
| 2026-04 | 2026-04..2026-05 | 2 | 57.7 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | MISSED | — | — | — |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | COINCIDENT | -1 | — | 1974-01 |
| 1980-02 | CAUGHT | 6 | 1 | 1979-08 |
| 1981-08 | MISSED | — | — | — |
| 1990-08 | COINCIDENT | -1 | — | 1990-09 |
| 2001-04 | CAUGHT | 20 | 10 | 1999-08 |
| 2008-01 | CAUGHT | 2 | 2 | 2007-11 |
| 2020-03 | MISSED | — | — | — |

**D3-YELLOW** (h=12): episodes in window 16 = 4 hit, 9 false positive, 2 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 4/13 = 30.8%; recall 5/11; month-level precision 22/107 = 20.6% vs base 124/744 = 16.7% (excluding coincident-episode months: 22/107 = 20.6%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| (1974-01 in-recession) | 1974-01..1974-12 | 0 | 159.1 | COINCIDENT | coincident with 1973-12 | — |
| 1979-07 | 1979-07..1980-08 | 8 | 117.5 | HIT | 1980-02, 1981-08 | 7 |
| 1987-03 | 1987-03..1987-10 | 7 | 77.5 | FALSE POSITIVE | — | — |
| 1989-09 | 1989-09..1989-11 | 3 | 39.2 | HIT | 1990-08 | 11 |
| (1990-08 in-recession) | 1990-08..1990-11 | 0 | 68.1 | COINCIDENT | coincident with 1990-08 | — |
| 1996-09 | 1996-09..1997-01 | 5 | 38.5 | FALSE POSITIVE | — | — |
| 1999-06 | 1999-06..2000-11 | 18 | 136.8 | HIT | 2001-04 | 22 |
| 2002-10 | 2002-10..2003-03 | 6 | 67.7 | FALSE POSITIVE | — | — |
| 2004-04 | 2004-04..2006-05 | 20 | 69.8 | FALSE POSITIVE | — | — |
| 2007-10 | 2007-10..2008-08 | 3 | 89.8 | HIT | 2008-01 | 3 |
| 2009-11 | 2009-11..2010-04 | 6 | 91.0 | FALSE POSITIVE | — | — |
| 2011-04 | 2011-04..2011-05 | 2 | 32.6 | FALSE POSITIVE | — | — |
| 2016-12 | 2016-12..2017-03 | 4 | 71.5 | FALSE POSITIVE | — | — |
| 2018-04 | 2018-04..2018-10 | 7 | 48.0 | FALSE POSITIVE | — | — |
| 2021-03 | 2021-03..2022-08 | 18 | 258.1 | FALSE POSITIVE | — | — |
| 2026-03 | 2026-03..2026-08 | 4 | 57.7 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | MISSED | — | — | — |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | COINCIDENT | -1 | — | 1974-01 |
| 1980-02 | CAUGHT | 7 | 1 | 1979-07 |
| 1981-08 | CAUGHT | 25 | 12 | 1979-07 |
| 1990-08 | CAUGHT | 11 | 9 | 1989-09 |
| 2001-04 | CAUGHT | 22 | 5 | 1999-06 |
| 2008-01 | CAUGHT | 3 | 1 | 2007-10 |
| 2020-03 | MISSED | — | — | — |

**PPI-RED** (h=12): episodes in window 14 = 4 hit, 7 false positive, 2 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 4/11 = 36.4%; recall 4/11; month-level precision 14/58 = 24.1% vs base 124/744 = 16.7% (excluding coincident-episode months: 14/58 = 24.1%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| (1974-01 in-recession) | 1974-01..1974-12 | 0 | 78.5 | COINCIDENT | coincident with 1973-12 | — |
| 1979-12 | 1979-12..1980-06 | 2 | 63.6 | HIT | 1980-02 | 2 |
| 1981-02 | 1981-02..1981-05 | 4 | 63.7 | HIT | 1981-08 | 6 |
| 1987-07 | 1987-07..1987-08 | 2 | 69.7 | FALSE POSITIVE | — | — |
| (1990-09 in-recession) | 1990-09..1990-11 | 0 | 104.9 | COINCIDENT | coincident with 1990-08 | — |
| 1999-08 | 1999-08..2000-10 | 14 | 218.7 | HIT | 2001-04 | 20 |
| 2002-12 | 2002-12..2003-02 | 3 | 77.9 | FALSE POSITIVE | — | — |
| 2004-09 | 2004-09..2005-07 | 5 | 71.2 | FALSE POSITIVE | — | — |
| 2007-11 | 2007-11..2008-08 | 2 | 107.2 | HIT | 2008-01 | 2 |
| 2009-12 | 2009-12..2010-04 | 5 | 129.3 | FALSE POSITIVE | — | — |
| 2017-01 | 2017-01..2017-02 | 2 | 106.2 | FALSE POSITIVE | — | — |
| 2018-05 | 2018-05..2018-07 | 3 | 63.6 | FALSE POSITIVE | — | — |
| 2021-03 | 2021-03..2022-06 | 16 | 260.0 | FALSE POSITIVE | — | — |
| 2026-04 | 2026-04..2026-05 | 2 | 70.9 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | MISSED | — | — | — |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | COINCIDENT | -1 | — | 1974-01 |
| 1980-02 | CAUGHT | 2 | 1 | 1979-12 |
| 1981-08 | CAUGHT | 6 | 3 | 1981-02 |
| 1990-08 | COINCIDENT | -1 | — | 1990-09 |
| 2001-04 | CAUGHT | 20 | 6 | 1999-08 |
| 2008-01 | CAUGHT | 2 | 1 | 2007-11 |
| 2020-03 | MISSED | — | — | — |

**PPI-D2** (h=12): episodes in window 10 = 6 hit, 2 false positive, 1 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 6/8 = 75.0%; recall 7/11; month-level precision 47/147 = 32.0% vs base 124/744 = 16.7% (excluding coincident-episode months: 47/141 = 33.3%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| 1953-06 | 1953-06..1954-01 | 2 | 10.8 | HIT | 1953-08 | 2 |
| 1973-09 | 1973-09..1976-05 | 17 | 57.9 | HIT | 1973-12 | 3 |
| 1978-09 | 1978-09..1982-01 | 24 | 49.3 | HIT | 1980-02, 1981-08 | 17 |
| 1991-04 | 1990-08..1991-09 | 6 | 65.8 | COINCIDENT | coincident with 1990-08 | — |
| 1996-04 | 1996-04..1997-08 | 17 | 23.7 | FALSE POSITIVE | — | — |
| 2000-02 | 2000-02..2001-05 | 14 | 31.4 | HIT | 2001-04 | 14 |
| 2004-05 | 2004-05..2009-04 | 38 | 64.3 | HIT | 2008-01 | 44 |
| 2018-04 | 2018-04..2019-03 | 12 | 21.0 | HIT | 2020-03 | 23 |
| 2022-01 | 2022-01..2023-05 | 17 | 46.8 | FALSE POSITIVE | — | — |
| 2026-04 | 2026-04..2026-08 | 5 | 18.7 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | CAUGHT | 2 | 1 | 1953-06 |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | CAUGHT | 3 | 1 | 1973-09 |
| 1980-02 | CAUGHT | 17 | 1 | 1978-09 |
| 1981-08 | CAUGHT | 35 | 1 | 1978-09 |
| 1990-08 | COINCIDENT | 0 | — | 1990-08 |
| 2001-04 | CAUGHT | 14 | 1 | 2000-02 |
| 2008-01 | CAUGHT | 44 | 1 | 2004-05 |
| 2020-03 | CAUGHT | 23 | 12 | 2018-04 |

### 3.2 h = 18

**D1-RED** (h=18): episodes in window 13 = 3 hit, 7 false positive, 2 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 3/10 = 30.0%; recall 3/11; month-level precision 15/49 = 30.6% vs base 178/738 = 24.1% (excluding coincident-episode months: 15/49 = 30.6%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| (1974-01 in-recession) | 1974-01..1974-12 | 0 | 184.0 | COINCIDENT | coincident with 1973-12 | — |
| 1979-08 | 1979-08..1980-07 | 6 | 149.2 | HIT | 1980-02 | 6 |
| 1987-07 | 1987-07..1987-07 | 1 | 84.5 | FALSE POSITIVE | — | — |
| (1990-09 in-recession) | 1990-09..1990-11 | 0 | 78.8 | COINCIDENT | coincident with 1990-08 | — |
| 1999-08 | 1999-08..2000-06 | 10 | 144.4 | HIT | 2001-04 | 20 |
| 2002-12 | 2002-12..2003-02 | 3 | 73.0 | FALSE POSITIVE | — | — |
| 2004-09 | 2004-09..2004-11 | 3 | 75.2 | FALSE POSITIVE | — | — |
| 2007-11 | 2007-11..2008-08 | 1 | 98.5 | HIT | 2008-01 | 2 |
| 2009-12 | 2009-12..2010-04 | 5 | 95.1 | FALSE POSITIVE | — | — |
| 2017-01 | 2017-01..2017-02 | 2 | 76.4 | FALSE POSITIVE | — | — |
| 2018-06 | 2018-06..2018-07 | 2 | 52.2 | FALSE POSITIVE | — | — |
| 2021-03 | 2021-03..2022-06 | 16 | 272.9 | FALSE POSITIVE | — | — |
| 2026-04 | 2026-04..2026-05 | 2 | 64.3 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | MISSED | — | — | — |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | COINCIDENT | -1 | — | 1974-01 |
| 1980-02 | CAUGHT | 6 | 1 | 1979-08 |
| 1981-08 | MISSED | — | — | — |
| 1990-08 | COINCIDENT | -1 | — | 1990-09 |
| 2001-04 | CAUGHT | 20 | 10 | 1999-08 |
| 2008-01 | CAUGHT | 2 | 2 | 2007-11 |
| 2020-03 | MISSED | — | — | — |

**D1-YELLOW** (h=18): episodes in window 16 = 5 hit, 9 false positive, 1 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 5/14 = 35.7%; recall 6/11; month-level precision 37/124 = 29.8% vs base 178/738 = 24.1% (excluding coincident-episode months: 37/124 = 29.8%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| (1974-01 in-recession) | 1974-01..1974-12 | 0 | 184.0 | COINCIDENT | coincident with 1973-12 | — |
| 1979-06 | 1979-06..1980-09 | 10 | 149.2 | HIT | 1980-02, 1981-08 | 8 |
| 1987-03 | 1987-03..1987-10 | 8 | 84.5 | FALSE POSITIVE | — | — |
| 1989-07 | 1989-07..1990-12 | 6 | 78.8 | HIT | 1990-08 | 13 |
| 1995-02 | 1995-02..1995-03 | 2 | 26.5 | FALSE POSITIVE | — | — |
| 1996-09 | 1996-09..1997-01 | 5 | 42.8 | FALSE POSITIVE | — | — |
| 1999-06 | 1999-06..2000-11 | 18 | 144.4 | HIT | 2001-04 | 22 |
| 2002-10 | 2002-10..2003-03 | 6 | 73.0 | FALSE POSITIVE | — | — |
| 2004-04 | 2004-04..2006-07 | 23 | 75.2 | HIT | 2008-01 | 45 |
| 2007-09 | 2007-09..2008-09 | 4 | 98.5 | FALSE POSITIVE | — | — |
| 2009-11 | 2009-11..2010-04 | 6 | 95.1 | FALSE POSITIVE | — | — |
| 2011-03 | 2011-03..2011-07 | 5 | 37.2 | FALSE POSITIVE | — | — |
| 2016-12 | 2016-12..2017-04 | 5 | 76.4 | FALSE POSITIVE | — | — |
| 2018-03 | 2018-03..2018-10 | 8 | 52.2 | HIT | 2020-03 | 24 |
| 2021-03 | 2021-03..2022-08 | 18 | 272.9 | FALSE POSITIVE | — | — |
| 2026-03 | 2026-03..2026-08 | 4 | 64.3 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | MISSED | — | — | — |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | COINCIDENT | -1 | — | 1974-01 |
| 1980-02 | CAUGHT | 8 | 1 | 1979-06 |
| 1981-08 | CAUGHT | 26 | 11 | 1979-06 |
| 1990-08 | CAUGHT | 13 | 7 | 1989-07 |
| 2001-04 | CAUGHT | 22 | 5 | 1999-06 |
| 2008-01 | CAUGHT | 45 | 1 | 2004-04 |
| 2020-03 | CAUGHT | 24 | 17 | 2018-03 |

**D2** (h=18): episodes in window 10 = 5 hit, 3 false positive, 1 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 5/8 = 62.5%; recall 6/11; month-level precision 52/129 = 40.3% vs base 178/738 = 24.1% (excluding coincident-episode months: 52/124 = 41.9%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| 1973-08 | 1973-08..1974-12 | 4 | 104.4 | HIT | 1973-12 | 4 |
| 1976-09 | 1976-09..1977-08 | 12 | 22.0 | FALSE POSITIVE | — | — |
| 1979-05 | 1979-05..1981-01 | 15 | 91.3 | HIT | 1980-02, 1981-08 | 9 |
| 1991-04 | 1990-08..1991-08 | 5 | 52.0 | COINCIDENT | coincident with 1990-08 | — |
| 1996-04 | 1996-04..1997-03 | 12 | 22.1 | FALSE POSITIVE | — | — |
| 2000-02 | 2000-02..2001-05 | 14 | 30.4 | HIT | 2001-04 | 14 |
| 2004-05 | 2004-05..2009-04 | 38 | 58.8 | HIT | 2008-01 | 44 |
| 2018-04 | 2018-04..2019-03 | 12 | 17.1 | HIT | 2020-03 | 23 |
| 2021-10 | 2021-10..2023-02 | 17 | 47.6 | FALSE POSITIVE | — | — |
| 2026-04 | 2026-04..2026-08 | 5 | 13.3 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | MISSED | — | — | — |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | CAUGHT | 4 | 1 | 1973-08 |
| 1980-02 | CAUGHT | 9 | 1 | 1979-05 |
| 1981-08 | CAUGHT | 27 | 7 | 1979-05 |
| 1990-08 | COINCIDENT | 0 | — | 1990-08 |
| 2001-04 | CAUGHT | 14 | 1 | 2000-02 |
| 2008-01 | CAUGHT | 44 | 1 | 2004-05 |
| 2020-03 | CAUGHT | 23 | 12 | 2018-04 |

**D3-RED** (h=18): episodes in window 12 = 3 hit, 6 false positive, 2 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 3/9 = 33.3%; recall 3/11; month-level precision 15/42 = 35.7% vs base 178/738 = 24.1% (excluding coincident-episode months: 15/42 = 35.7%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| (1974-01 in-recession) | 1974-01..1974-12 | 0 | 159.1 | COINCIDENT | coincident with 1973-12 | — |
| 1979-08 | 1979-08..1980-07 | 6 | 117.5 | HIT | 1980-02 | 6 |
| 1987-07 | 1987-07..1987-07 | 1 | 77.5 | FALSE POSITIVE | — | — |
| (1990-09 in-recession) | 1990-09..1990-11 | 0 | 68.1 | COINCIDENT | coincident with 1990-08 | — |
| 1999-08 | 1999-08..2000-06 | 10 | 136.8 | HIT | 2001-04 | 20 |
| 2003-01 | 2003-01..2003-02 | 2 | 67.7 | FALSE POSITIVE | — | — |
| 2004-09 | 2004-09..2004-11 | 3 | 69.8 | FALSE POSITIVE | — | — |
| 2007-11 | 2007-11..2008-08 | 1 | 89.8 | HIT | 2008-01 | 2 |
| 2009-12 | 2009-12..2010-04 | 5 | 91.0 | FALSE POSITIVE | — | — |
| 2017-01 | 2017-01..2017-02 | 2 | 71.5 | FALSE POSITIVE | — | — |
| 2021-03 | 2021-03..2022-05 | 12 | 258.1 | FALSE POSITIVE | — | — |
| 2026-04 | 2026-04..2026-05 | 2 | 57.7 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | MISSED | — | — | — |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | COINCIDENT | -1 | — | 1974-01 |
| 1980-02 | CAUGHT | 6 | 1 | 1979-08 |
| 1981-08 | MISSED | — | — | — |
| 1990-08 | COINCIDENT | -1 | — | 1990-09 |
| 2001-04 | CAUGHT | 20 | 10 | 1999-08 |
| 2008-01 | CAUGHT | 2 | 2 | 2007-11 |
| 2020-03 | MISSED | — | — | — |

**D3-YELLOW** (h=18): episodes in window 16 = 5 hit, 8 false positive, 2 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 5/13 = 38.5%; recall 6/11; month-level precision 30/107 = 28.0% vs base 178/738 = 24.1% (excluding coincident-episode months: 30/107 = 28.0%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| (1974-01 in-recession) | 1974-01..1974-12 | 0 | 159.1 | COINCIDENT | coincident with 1973-12 | — |
| 1979-07 | 1979-07..1980-08 | 8 | 117.5 | HIT | 1980-02, 1981-08 | 7 |
| 1987-03 | 1987-03..1987-10 | 7 | 77.5 | FALSE POSITIVE | — | — |
| 1989-09 | 1989-09..1989-11 | 3 | 39.2 | HIT | 1990-08 | 11 |
| (1990-08 in-recession) | 1990-08..1990-11 | 0 | 68.1 | COINCIDENT | coincident with 1990-08 | — |
| 1996-09 | 1996-09..1997-01 | 5 | 38.5 | FALSE POSITIVE | — | — |
| 1999-06 | 1999-06..2000-11 | 18 | 136.8 | HIT | 2001-04 | 22 |
| 2002-10 | 2002-10..2003-03 | 6 | 67.7 | FALSE POSITIVE | — | — |
| 2004-04 | 2004-04..2006-05 | 20 | 69.8 | FALSE POSITIVE | — | — |
| 2007-10 | 2007-10..2008-08 | 3 | 89.8 | HIT | 2008-01 | 3 |
| 2009-11 | 2009-11..2010-04 | 6 | 91.0 | FALSE POSITIVE | — | — |
| 2011-04 | 2011-04..2011-05 | 2 | 32.6 | FALSE POSITIVE | — | — |
| 2016-12 | 2016-12..2017-03 | 4 | 71.5 | FALSE POSITIVE | — | — |
| 2018-04 | 2018-04..2018-10 | 7 | 48.0 | HIT | 2020-03 | 23 |
| 2021-03 | 2021-03..2022-08 | 18 | 258.1 | FALSE POSITIVE | — | — |
| 2026-03 | 2026-03..2026-08 | 4 | 57.7 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | MISSED | — | — | — |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | COINCIDENT | -1 | — | 1974-01 |
| 1980-02 | CAUGHT | 7 | 1 | 1979-07 |
| 1981-08 | CAUGHT | 25 | 12 | 1979-07 |
| 1990-08 | CAUGHT | 11 | 9 | 1989-09 |
| 2001-04 | CAUGHT | 22 | 5 | 1999-06 |
| 2008-01 | CAUGHT | 3 | 1 | 2007-10 |
| 2020-03 | CAUGHT | 23 | 17 | 2018-04 |

**PPI-RED** (h=18): episodes in window 14 = 4 hit, 7 false positive, 2 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 4/11 = 36.4%; recall 4/11; month-level precision 20/58 = 34.5% vs base 178/738 = 24.1% (excluding coincident-episode months: 20/58 = 34.5%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| (1974-01 in-recession) | 1974-01..1974-12 | 0 | 78.5 | COINCIDENT | coincident with 1973-12 | — |
| 1979-12 | 1979-12..1980-06 | 2 | 63.6 | HIT | 1980-02 | 2 |
| 1981-02 | 1981-02..1981-05 | 4 | 63.7 | HIT | 1981-08 | 6 |
| 1987-07 | 1987-07..1987-08 | 2 | 69.7 | FALSE POSITIVE | — | — |
| (1990-09 in-recession) | 1990-09..1990-11 | 0 | 104.9 | COINCIDENT | coincident with 1990-08 | — |
| 1999-08 | 1999-08..2000-10 | 14 | 218.7 | HIT | 2001-04 | 20 |
| 2002-12 | 2002-12..2003-02 | 3 | 77.9 | FALSE POSITIVE | — | — |
| 2004-09 | 2004-09..2005-07 | 5 | 71.2 | FALSE POSITIVE | — | — |
| 2007-11 | 2007-11..2008-08 | 2 | 107.2 | HIT | 2008-01 | 2 |
| 2009-12 | 2009-12..2010-04 | 5 | 129.3 | FALSE POSITIVE | — | — |
| 2017-01 | 2017-01..2017-02 | 2 | 106.2 | FALSE POSITIVE | — | — |
| 2018-05 | 2018-05..2018-07 | 3 | 63.6 | FALSE POSITIVE | — | — |
| 2021-03 | 2021-03..2022-06 | 16 | 260.0 | FALSE POSITIVE | — | — |
| 2026-04 | 2026-04..2026-05 | 2 | 70.9 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | MISSED | — | — | — |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | COINCIDENT | -1 | — | 1974-01 |
| 1980-02 | CAUGHT | 2 | 1 | 1979-12 |
| 1981-08 | CAUGHT | 6 | 3 | 1981-02 |
| 1990-08 | COINCIDENT | -1 | — | 1990-09 |
| 2001-04 | CAUGHT | 20 | 6 | 1999-08 |
| 2008-01 | CAUGHT | 2 | 1 | 2007-11 |
| 2020-03 | MISSED | — | — | — |

**PPI-D2** (h=18): episodes in window 10 = 6 hit, 2 false positive, 1 coincident, 1 pending, 0 in-recession-only; episode precision hits/(hits+FP) = 6/8 = 75.0%; recall 7/11; month-level precision 62/147 = 42.2% vs base 178/738 = 24.1% (excluding coincident-episode months: 62/141 = 44.0%).

| episode start | raw span | n ON (USREC=0) | peak | outcome | event(s) credited / coincident with | lead first-ON→event (m) |
|---|---|---|---|---|---|---|
| 1953-06 | 1953-06..1954-01 | 2 | 10.8 | HIT | 1953-08 | 2 |
| 1973-09 | 1973-09..1976-05 | 17 | 57.9 | HIT | 1973-12 | 3 |
| 1978-09 | 1978-09..1982-01 | 24 | 49.3 | HIT | 1980-02, 1981-08 | 17 |
| 1991-04 | 1990-08..1991-09 | 6 | 65.8 | COINCIDENT | coincident with 1990-08 | — |
| 1996-04 | 1996-04..1997-08 | 17 | 23.7 | FALSE POSITIVE | — | — |
| 2000-02 | 2000-02..2001-05 | 14 | 31.4 | HIT | 2001-04 | 14 |
| 2004-05 | 2004-05..2009-04 | 38 | 64.3 | HIT | 2008-01 | 44 |
| 2018-04 | 2018-04..2019-03 | 12 | 21.0 | HIT | 2020-03 | 23 |
| 2022-01 | 2022-01..2023-05 | 17 | 46.8 | FALSE POSITIVE | — | — |
| 2026-04 | 2026-04..2026-08 | 5 | 18.7 | PENDING | — | — |

| onset | per-event | lead from first ON (m) | months from last ON before event | crediting first ON |
|---|---|---|---|---|
| 1953-08 | CAUGHT | 2 | 1 | 1953-06 |
| 1957-09 | MISSED | — | — | — |
| 1960-05 | MISSED | — | — | — |
| 1970-01 | MISSED | — | — | — |
| 1973-12 | CAUGHT | 3 | 1 | 1973-09 |
| 1980-02 | CAUGHT | 17 | 1 | 1978-09 |
| 1981-08 | CAUGHT | 35 | 1 | 1978-09 |
| 1990-08 | COINCIDENT | 0 | — | 1990-08 |
| 2001-04 | CAUGHT | 14 | 1 | 2000-02 |
| 2008-01 | CAUGHT | 44 | 1 | 2004-05 |
| 2020-03 | CAUGHT | 23 | 12 | 2018-04 |

### 3.3 Summary — per definition, per horizon (common window)

| h | definition | month precision | base | episode hits/(hits+FP) | recall | false positives (first ON) | coincident (raw first ON) | pending |
|---|---|---|---|---|---|---|---|---|
| 12 | D1-RED | 9/49 = 18.4% | 16.7% | 3/10 = 30.0% | 3/11 | 1987-07, 2002-12, 2004-09, 2009-12, 2017-01, 2018-06, 2021-03 | 1974-01, 1990-09 | 2026-04 |
| 12 | D1-YELLOW | 27/124 = 21.8% | 16.7% | 4/14 = 28.6% | 5/11 | 1987-03, 1995-02, 1996-09, 2002-10, 2004-04, 2009-11, 2011-03, 2016-12, 2018-03, 2021-03 | 1974-01 | 2026-03 |
| 12 | D2 | 38/129 = 29.5% | 16.7% | 5/8 = 62.5% | 6/11 | 1976-09, 1996-04, 2021-10 | 1990-08 | 2026-04 |
| 12 | D3-RED | 9/42 = 21.4% | 16.7% | 3/9 = 33.3% | 3/11 | 1987-07, 2003-01, 2004-09, 2009-12, 2017-01, 2021-03 | 1974-01, 1990-09 | 2026-04 |
| 12 | D3-YELLOW | 22/107 = 20.6% | 16.7% | 4/13 = 30.8% | 5/11 | 1987-03, 1996-09, 2002-10, 2004-04, 2009-11, 2011-04, 2016-12, 2018-04, 2021-03 | 1974-01, 1990-08 | 2026-03 |
| 12 | PPI-RED | 14/58 = 24.1% | 16.7% | 4/11 = 36.4% | 4/11 | 1987-07, 2002-12, 2004-09, 2009-12, 2017-01, 2018-05, 2021-03 | 1974-01, 1990-09 | 2026-04 |
| 12 | PPI-D2 | 47/147 = 32.0% | 16.7% | 6/8 = 75.0% | 7/11 | 1996-04, 2022-01 | 1990-08 | 2026-04 |
| 18 | D1-RED | 15/49 = 30.6% | 24.1% | 3/10 = 30.0% | 3/11 | 1987-07, 2002-12, 2004-09, 2009-12, 2017-01, 2018-06, 2021-03 | 1974-01, 1990-09 | 2026-04 |
| 18 | D1-YELLOW | 37/124 = 29.8% | 24.1% | 5/14 = 35.7% | 6/11 | 1987-03, 1995-02, 1996-09, 2002-10, 2007-09, 2009-11, 2011-03, 2016-12, 2021-03 | 1974-01 | 2026-03 |
| 18 | D2 | 52/129 = 40.3% | 24.1% | 5/8 = 62.5% | 6/11 | 1976-09, 1996-04, 2021-10 | 1990-08 | 2026-04 |
| 18 | D3-RED | 15/42 = 35.7% | 24.1% | 3/9 = 33.3% | 3/11 | 1987-07, 2003-01, 2004-09, 2009-12, 2017-01, 2021-03 | 1974-01, 1990-09 | 2026-04 |
| 18 | D3-YELLOW | 30/107 = 28.0% | 24.1% | 5/13 = 38.5% | 6/11 | 1987-03, 1996-09, 2002-10, 2004-04, 2009-11, 2011-04, 2016-12, 2021-03 | 1974-01, 1990-08 | 2026-03 |
| 18 | PPI-RED | 20/58 = 34.5% | 24.1% | 4/11 = 36.4% | 4/11 | 1987-07, 2002-12, 2004-09, 2009-12, 2017-01, 2018-05, 2021-03 | 1974-01, 1990-09 | 2026-04 |
| 18 | PPI-D2 | 62/147 = 42.2% | 24.1% | 6/8 = 75.0% | 7/11 | 1996-04, 2022-01 | 1990-08 | 2026-04 |

**Q1 PRIMARY (D1-RED, h = 12, NBER onsets, episode level, common window): 3 hits of 10 scoreable episodes = 30.0%; recall 3/11; month-level precision 18.4% vs base 16.7%.**

Reading notes (rule artifacts, stated so nobody over-reads the D2 row):

- D2's 2008-01 credit comes from the single 54-month 2004-05..2009-04 episode (NOPI12 never fell below 10 for more than 6 months in 2004–08): lead from first ON = 44 months; the last ON month before the onset was 2007-12. D2's 2020-03 credit rests on ON at exactly e−12 (2019-03, the last month of the 2018-04 episode) and the event is the COVID shock. D2's 1981-08 credit uses the double-dip window (ON 1980-08..1981-01). Descriptively (NOT a spec statistic): without those three credits D2 would be 3 hits / 5 FP (2004-05 and 2018-04 become false positives), recall 3/11 — the same recall as D1-RED — i.e. the D2-over-D1 margin is carried by the long-episode and edge credits the §4 rule allows.
- D1-YELLOW at h=18: the 2004-04..2006-07 episode (23 ON months) reaches 2008-01 (last ON + 18 = 2008-01) and, being the earliest, takes the credit; the 2007-09 episode that actually preceded the onset is then a false positive. Per-event recall is unaffected.
- D1-RED's 2001-04 credit: first ON 1999-08, last ON before onset 2000-06 (10 months); its 2008-01 credit is a single ON month, 2007-11 (2007-12 read +47.9, yellow).
- 1973-12: D1/D3 first ON 1974-01 (coincident, as pre-declared) — but D2 (NOPI12) fired 1973-08 on the WTISPLC posted-price step 3.56→4.31 (+19 log-pct) and PPI-D2 fired 1973-09, so under the NOPI definition 1973-12 is CAUGHT with a 4-month (3-month) lead, NOT coincident. The pre-declared 'every definition' expectation fails for D2. On WPU0561 the 1973-12 print (+27.5%) is YELLOW, not RED, so PPI-RED's first ON is 1974-01, same as WTISPLC.

§5 trigger rows (h = 12, NBER, common window; 'D2 beats D1 on episode precision by ≥ 1 episode with equal-or-better recall'):

| definition | hits | false positives | recall |
|---|---|---|---|
| D1-RED | 3 | 7 | 3/11 |
| D2 (NOPI12 ≥ 10) | 5 | 3 | 6/11 |
| D3-RED | 3 | 6 | 3/11 |

- D2 vs D1: precision 5/8 vs 3/10, recall 6 vs 3 → D2 better on both (row candidate — the §5 NOPI12 trigger-leg row applies). Interpretation of 'by ≥ 1 episode': ≥ 1 more hit OR ≥ 1 fewer false positive, with recall ≥ D1's.
- D3 vs D1 and D2: D3 does NOT beat both on precision with ≥ recall → no real-oil leg.

### 3.4 Secondary full-window row (ON months 1947-01+, onsets 1948-12..2020-03; evaluability by each series' own start)

| h | definition | month precision | base | episode hits/(hits+FP) | recall | not evaluable onsets | 1948-12 |
|---|---|---|---|---|---|---|---|
| 12 | D1-RED | 12/52 = 23.1% | 17.8% | 4/11 | 4/12 | — | caught |
| 12 | D1-YELLOW | 38/143 = 26.6% | 17.8% | 5/15 | 6/12 | — | caught |
| 12 | D2 | 38/129 = 29.5% | 17.8% | 5/8 | 6/11 | 1948-12 | not evaluable |
| 12 | D3-RED | 9/42 = 21.4% | 17.8% | 3/9 | 3/11 | 1948-12 | not evaluable |
| 12 | D3-YELLOW | 32/117 = 27.4% | 17.8% | 5/14 | 5/11 | 1948-12 | not evaluable |
| 12 | PPI-RED | 16/60 = 26.7% | 17.8% | 5/12 | 4/11 | 1948-12 | not evaluable |
| 12 | PPI-D2 | 47/147 = 32.0% | 17.8% | 6/8 | 7/11 | 1948-12 | not evaluable |
| 18 | D1-RED | 18/52 = 34.6% | 26.2% | 4/11 | 4/12 | — | caught |
| 18 | D1-YELLOW | 51/143 = 35.7% | 26.2% | 6/15 | 7/12 | — | caught |
| 18 | D2 | 52/129 = 40.3% | 26.2% | 5/8 | 6/11 | 1948-12 | not evaluable |
| 18 | D3-RED | 15/42 = 35.7% | 26.2% | 3/9 | 3/11 | 1948-12 | not evaluable |
| 18 | D3-YELLOW | 40/117 = 34.2% | 26.2% | 6/14 | 6/11 | 1948-12 | not evaluable |
| 18 | PPI-RED | 22/60 = 36.7% | 26.2% | 5/12 | 4/11 | 1948-12 | not evaluable |
| 18 | PPI-D2 | 62/147 = 42.2% | 26.2% | 6/8 | 7/11 | 1948-12 | not evaluable |

## 4. Kill-rate recount (common window, WTISPLC; h = 12 for 'preceded')

| definition | measured kill_rate (replaces 'preceded ~10 of 11 postwar recessions') |
|---|---|
| D1-RED | 3 of 11 postwar onsets (1953-08..2020-03) preceded, 7 named false positives (1987-07, 2002-12, 2004-09, 2009-12, 2017-01, 2018-06, 2021-03), 2 coincident (1974-01, 1990-09) |
| D1-YELLOW | 5 of 11 postwar onsets (1953-08..2020-03) preceded, 10 named false positives (1987-03, 1995-02, 1996-09, 2002-10, 2004-04, 2009-11, 2011-03, 2016-12, 2018-03, 2021-03), 1 coincident (1974-01) |
| D2 | 6 of 11 postwar onsets (1953-08..2020-03) preceded, 3 named false positives (1976-09, 1996-04, 2021-10), 1 coincident (1990-08) |
| D3-RED | 3 of 11 postwar onsets (1953-08..2020-03) preceded, 6 named false positives (1987-07, 2003-01, 2004-09, 2009-12, 2017-01, 2021-03), 2 coincident (1974-01, 1990-09) |
| D3-YELLOW | 5 of 11 postwar onsets (1953-08..2020-03) preceded, 9 named false positives (1987-03, 1996-09, 2002-10, 2004-04, 2009-11, 2011-04, 2016-12, 2018-04, 2021-03), 2 coincident (1974-01, 1990-08) |
| PPI-RED | 4 of 11 postwar onsets (1953-08..2020-03) preceded, 7 named false positives (1987-07, 2002-12, 2004-09, 2009-12, 2017-01, 2018-05, 2021-03), 2 coincident (1974-01, 1990-09) |
| PPI-D2 | 7 of 11 postwar onsets (1953-08..2020-03) preceded, 2 named false positives (1996-04, 2022-01), 1 coincident (1990-08) |

Hamilton's '10 of 11' is a narrative count (his own 1983/2011 dating of oil-price events); it is NOT reproducible from this instrument on any definition — see the per-event tables above. The recount is what `pins.py` `kill_rate` must say per §5.

### 4.1 PPI (WPU0561) robustness rows for pre-1983 onsets — WTISPLC rule / PPI companion, h = 12

**D1-RED / PPI-RED**

| onset | WTISPLC / PPI | first ON (WTISPLC rule) | first ON (PPI rule) | lead WTISPLC (m) | lead PPI (m) |
|---|---|---|---|---|---|
| 1953-08 | miss/miss | — | — | — | — |
| 1957-09 | miss/miss | — | — | — | — |
| 1960-05 | miss/miss | — | — | — | — |
| 1970-01 | miss/miss | — | — | — | — |
| 1973-12 | coincident/coincident | 1974-01 | 1974-01 | -1 | -1 |
| 1980-02 | hit/hit | 1979-08 | 1979-12 | 6 | 2 |
| 1981-08 | miss/hit | — | 1981-02 | — | 6 |

**D2 / PPI-D2**

| onset | WTISPLC / PPI | first ON (WTISPLC rule) | first ON (PPI rule) | lead WTISPLC (m) | lead PPI (m) |
|---|---|---|---|---|---|
| 1953-08 | miss/hit | — | 1953-06 | — | 2 |
| 1957-09 | miss/miss | — | — | — | — |
| 1960-05 | miss/miss | — | — | — | — |
| 1970-01 | miss/miss | — | — | — | — |
| 1973-12 | hit/hit | 1973-08 | 1973-09 | 4 | 3 |
| 1980-02 | hit/hit | 1979-05 | 1978-09 | 9 | 17 |
| 1981-08 | hit/hit | 1979-05 | 1978-09 | 27 | 35 |

### 4.2 Pre-declared expectations — checked

| expectation | definition | measured | first ON (raw) | verdict |
|---|---|---|---|---|
| 1973-12 coincident/missed | D1-RED | COINCIDENT | 1974-01 | as pre-declared |
| 1973-12 coincident/missed | D2 | CAUGHT | 1973-08 | **NOT as pre-declared — caught with a lead** |
| 1973-12 coincident/missed | D3-RED | COINCIDENT | 1974-01 | as pre-declared |
| 1973-12 coincident/missed | PPI-RED | COINCIDENT | 1974-01 | as pre-declared |
| 1973-12 coincident/missed | PPI-D2 | CAUGHT | 1973-09 | **NOT as pre-declared — caught with a lead** |
| 1990-08 coincident | D1-RED | COINCIDENT | 1990-09 | as pre-declared |
| 1990-08 coincident | D2 | COINCIDENT | 1990-08 | as pre-declared |
| 1990-08 coincident | D3-RED | COINCIDENT | 1990-09 | as pre-declared |
| 1990-08 coincident | PPI-RED | COINCIDENT | 1990-09 | as pre-declared |
| 1990-08 coincident | PPI-D2 | COINCIDENT | 1990-08 | as pre-declared |
| 2022 false positive (h=12) | D1-RED | FALSE POSITIVE | 2021-03 | as pre-declared |
| 2022 false positive (h=18) | D1-RED | FALSE POSITIVE | 2021-03 | as pre-declared |
| 2022 false positive (h=12) | D2 | FALSE POSITIVE | 2021-10 | as pre-declared |
| 2022 false positive (h=18) | D2 | FALSE POSITIVE | 2021-10 | as pre-declared |
| 2022 false positive (h=12) | D3-RED | FALSE POSITIVE | 2021-03 | as pre-declared |
| 2022 false positive (h=18) | D3-RED | FALSE POSITIVE | 2021-03 | as pre-declared |

## 5. Curve-conditioned rules (1957-09 onward, 10 onsets; ON months 1953-09..last resolved) — oil isolated from the policy channel

This is the first time the canary's oil signal is scored ALONE and beside the curve, instead of inside the bundled oil-OR-policy window of `studies/pin-rule-hindcast.md` v3 (deployed accident gauge: fast-red+curve 34% / 4 of 13; oil-or-policy window + curve 45% / 5 of 6 on drawdowns, 37% / 4 of 4 on onsets). Curve flat = min `spread_gs` over the trailing 6 months < 0.25. 1953-08 is NOT TESTABLE for curve rules (4 months of curve history) and is excluded from every denominator here; for like-for-like the oil-alone rows in this section use the same 1953-09+ window and the same 10 onsets. Drawdown events: B1 running-peak (headline), B2 local-peak (second); same episode rule, same USREC=0 filter, same coincident/pending rules; no double-dip rule applies to drawdowns. Recall evaluability uses the rule's data start (curve rules 1953-09).

### 5.1 vs NBER onsets (10 events: 1957-09, 1960-05, 1970-01, 1973-12, 1980-02, 1981-08, 1990-08, 2001-04, 2008-01, 2020-03)

| h | rule | month precision | base | episode hits/(hits+FP) | recall | events caught | false positives (first ON) | coincident | pending |
|---|---|---|---|---|---|---|---|---|---|
| 12 | curve flat alone | 96/174 = 55.2% | 16.2% | 9/11 = 81.8% | 10/10 | 1957-09, 1960-05, 1970-01, 1973-12, 1980-02, 1981-08, 1990-08, 2001-04, 2008-01, 2020-03 | 1965-12, 1998-09 | — | 2022-11 |
| 12 | D1-RED alone | 9/49 = 18.4% | 16.2% | 3/10 = 30.0% | 3/10 | 1980-02, 2001-04, 2008-01 | 1987-07, 2002-12, 2004-09, 2009-12, 2017-01, 2018-06, 2021-03 | 1974-01, 1990-09 | 2026-04 |
| 12 | D1-RED AND curve flat | 7/7 = 100.0% | 16.2% | 2/2 = 100.0% | 2/10 | 1980-02, 2008-01 | — | 1974-01 | — |
| 12 | D2 alone | 38/129 = 29.5% | 16.2% | 5/8 = 62.5% | 6/10 | 1973-12, 1980-02, 1981-08, 2001-04, 2008-01, 2020-03 | 1976-09, 1996-04, 2021-10 | 1990-08 | 2026-04 |
| 12 | D2 AND curve flat | 35/51 = 68.6% | 16.2% | 5/6 = 83.3% | 6/10 | 1973-12, 1980-02, 1981-08, 2001-04, 2008-01, 2020-03 | 2022-11 | — | — |
| 12 | D3-RED alone | 9/42 = 21.4% | 16.2% | 3/9 = 33.3% | 3/10 | 1980-02, 2001-04, 2008-01 | 1987-07, 2003-01, 2004-09, 2009-12, 2017-01, 2021-03 | 1974-01, 1990-09 | 2026-04 |
| 12 | D3-RED AND curve flat | 7/7 = 100.0% | 16.2% | 2/2 = 100.0% | 2/10 | 1980-02, 2008-01 | — | 1974-01 | — |
| 18 | curve flat alone | 113/168 = 67.3% | 23.7% | 9/11 = 81.8% | 10/10 | 1957-09, 1960-05, 1970-01, 1973-12, 1980-02, 1981-08, 1990-08, 2001-04, 2008-01, 2020-03 | 1965-12, 1998-09 | — | 2022-11 |
| 18 | D1-RED alone | 15/49 = 30.6% | 23.7% | 3/10 = 30.0% | 3/10 | 1980-02, 2001-04, 2008-01 | 1987-07, 2002-12, 2004-09, 2009-12, 2017-01, 2018-06, 2021-03 | 1974-01, 1990-09 | 2026-04 |
| 18 | D1-RED AND curve flat | 7/7 = 100.0% | 23.7% | 2/2 = 100.0% | 2/10 | 1980-02, 2008-01 | — | 1974-01 | — |
| 18 | D2 alone | 52/129 = 40.3% | 23.7% | 5/8 = 62.5% | 6/10 | 1973-12, 1980-02, 1981-08, 2001-04, 2008-01, 2020-03 | 1976-09, 1996-04, 2021-10 | 1990-08 | 2026-04 |
| 18 | D2 AND curve flat | 41/51 = 80.4% | 23.7% | 5/6 = 83.3% | 6/10 | 1973-12, 1980-02, 1981-08, 2001-04, 2008-01, 2020-03 | 2022-11 | — | — |
| 18 | D3-RED alone | 15/42 = 35.7% | 23.7% | 3/9 = 33.3% | 3/10 | 1980-02, 2001-04, 2008-01 | 1987-07, 2003-01, 2004-09, 2009-12, 2017-01, 2021-03 | 1974-01, 1990-09 | 2026-04 |
| 18 | D3-RED AND curve flat | 7/7 = 100.0% | 23.7% | 2/2 = 100.0% | 2/10 | 1980-02, 2008-01 | — | 1974-01 | — |

### 5.2 vs B1 drawdown starts (15 events: 1956-07, 1961-12, 1966-01, 1968-11, 1972-12, 1980-11, 1987-08, 1990-05, 1998-06, 2000-08, 2007-10, 2018-09, 2019-12, 2021-12, 2025-01)

| h | rule | month precision | base | episode hits/(hits+FP) | recall | events caught | false positives (first ON) | coincident | pending |
|---|---|---|---|---|---|---|---|---|---|
| 12 | curve flat alone | 54/174 = 31.0% | 22.6% | 8/11 = 72.7% | 8/15 | 1966-01, 1968-11, 1980-11, 1990-05, 2000-08, 2007-10, 2019-12, 2025-01 | 1957-02, 1959-12, 1973-06 | 1998-09 | — |
| 12 | D1-RED alone | 25/49 = 51.0% | 22.6% | 5/9 = 55.6% | 5/15 | 1980-11, 1987-08, 2000-08, 2018-09, 2021-12 | 2002-12, 2004-09, 2009-12, 2017-01 | 2007-11 | 2026-04 |
| 12 | D1-RED AND curve flat | 3/7 = 42.9% | 22.6% | 1/1 = 100.0% | 1/15 | 1980-11 | — | 2007-11 | — |
| 12 | D2 alone | 29/129 = 22.5% | 22.6% | 5/8 = 62.5% | 6/15 | 1980-11, 2000-08, 2007-10, 2018-09, 2019-12, 2021-12 | 1973-08, 1976-09, 1996-04 | 1990-08 | 2026-04 |
| 12 | D2 AND curve flat | 14/51 = 27.5% | 22.6% | 4/6 = 66.7% | 4/15 | 1980-11, 2000-08, 2007-10, 2019-12 | 1973-08, 2022-11 | — | — |
| 12 | D3-RED alone | 23/42 = 54.8% | 22.6% | 4/8 = 50.0% | 4/15 | 1980-11, 1987-08, 2000-08, 2021-12 | 2003-01, 2004-09, 2009-12, 2017-01 | 2007-11 | 2026-04 |
| 12 | D3-RED AND curve flat | 3/7 = 42.9% | 22.6% | 1/1 = 100.0% | 1/15 | 1980-11 | — | 2007-11 | — |
| 18 | curve flat alone | 72/168 = 42.9% | 33.0% | 7/12 = 58.3% | 9/15 | 1966-01, 1968-11, 1980-11, 1990-05, 2000-08, 2007-10, 2019-12, 2021-12, 2025-01 | 1957-02, 1959-12, 1968-05, 1973-06, 2000-07 | — | — |
| 18 | D1-RED alone | 28/49 = 57.1% | 33.0% | 5/9 = 55.6% | 6/15 | 1980-11, 1987-08, 2000-08, 2018-09, 2019-12, 2021-12 | 2002-12, 2004-09, 2009-12, 2017-01 | 2007-11 | 2026-04 |
| 18 | D1-RED AND curve flat | 6/7 = 85.7% | 33.0% | 1/1 = 100.0% | 1/15 | 1980-11 | — | 2007-11 | — |
| 18 | D2 alone | 48/129 = 37.2% | 33.0% | 6/8 = 75.0% | 7/15 | 1980-11, 1998-06, 2000-08, 2007-10, 2018-09, 2019-12, 2021-12 | 1973-08, 1976-09 | 1990-08 | 2026-04 |
| 18 | D2 AND curve flat | 26/51 = 51.0% | 33.0% | 4/6 = 66.7% | 4/15 | 1980-11, 2000-08, 2007-10, 2019-12 | 1973-08, 2022-11 | — | — |
| 18 | D3-RED alone | 26/42 = 61.9% | 33.0% | 4/8 = 50.0% | 4/15 | 1980-11, 1987-08, 2000-08, 2021-12 | 2003-01, 2004-09, 2009-12, 2017-01 | 2007-11 | 2026-04 |
| 18 | D3-RED AND curve flat | 6/7 = 85.7% | 33.0% | 1/1 = 100.0% | 1/15 | 1980-11 | — | 2007-11 | — |

### 5.3 vs B2 drawdown starts (18 events: 1956-07, 1961-12, 1966-01, 1968-11, 1972-12, 1976-12, 1980-01, 1980-11, 1987-08, 1990-05, 1998-06, 2000-08, 2007-10, 2011-04, 2018-09, 2019-12, 2021-12, 2025-01)

| h | rule | month precision | base | episode hits/(hits+FP) | recall | events caught | false positives (first ON) | coincident | pending |
|---|---|---|---|---|---|---|---|---|---|
| 12 | curve flat alone | 64/174 = 36.8% | 27.2% | 8/11 = 72.7% | 9/18 | 1966-01, 1968-11, 1980-01, 1980-11, 1990-05, 2000-08, 2007-10, 2019-12, 2025-01 | 1957-02, 1959-12, 1973-06 | 1998-09 | — |
| 12 | D1-RED alone | 29/49 = 59.2% | 27.2% | 6/9 = 66.7% | 7/18 | 1980-01, 1980-11, 1987-08, 2000-08, 2011-04, 2018-09, 2021-12 | 2002-12, 2004-09, 2017-01 | 2007-11 | 2026-04 |
| 12 | D1-RED AND curve flat | 6/7 = 85.7% | 27.2% | 1/1 = 100.0% | 2/18 | 1980-01, 1980-11 | — | 2007-11 | — |
| 12 | D2 alone | 38/129 = 29.5% | 27.2% | 6/8 = 75.0% | 8/18 | 1976-12, 1980-01, 1980-11, 2000-08, 2007-10, 2018-09, 2019-12, 2021-12 | 1973-08, 1996-04 | 1990-08 | 2026-04 |
| 12 | D2 AND curve flat | 20/51 = 39.2% | 27.2% | 4/6 = 66.7% | 5/18 | 1980-01, 1980-11, 2000-08, 2007-10, 2019-12 | 1973-08, 2022-11 | — | — |
| 12 | D3-RED alone | 27/42 = 64.3% | 27.2% | 5/8 = 62.5% | 6/18 | 1980-01, 1980-11, 1987-08, 2000-08, 2011-04, 2021-12 | 2003-01, 2004-09, 2017-01 | 2007-11 | 2026-04 |
| 12 | D3-RED AND curve flat | 6/7 = 85.7% | 27.2% | 1/1 = 100.0% | 2/18 | 1980-01, 1980-11 | — | 2007-11 | — |
| 18 | curve flat alone | 78/168 = 46.4% | 39.2% | 7/12 = 58.3% | 10/18 | 1966-01, 1968-11, 1980-01, 1980-11, 1990-05, 2000-08, 2007-10, 2019-12, 2021-12, 2025-01 | 1957-02, 1959-12, 1968-05, 1973-06, 2000-07 | — | — |
| 18 | D1-RED alone | 33/49 = 67.3% | 39.2% | 6/9 = 66.7% | 8/18 | 1980-01, 1980-11, 1987-08, 2000-08, 2011-04, 2018-09, 2019-12, 2021-12 | 2002-12, 2004-09, 2017-01 | 2007-11 | 2026-04 |
| 18 | D1-RED AND curve flat | 6/7 = 85.7% | 39.2% | 1/1 = 100.0% | 2/18 | 1980-01, 1980-11 | — | 2007-11 | — |
| 18 | D2 alone | 51/129 = 39.5% | 39.2% | 7/8 = 87.5% | 9/18 | 1976-12, 1980-01, 1980-11, 1998-06, 2000-08, 2007-10, 2018-09, 2019-12, 2021-12 | 1973-08 | 1990-08 | 2026-04 |
| 18 | D2 AND curve flat | 26/51 = 51.0% | 39.2% | 4/6 = 66.7% | 5/18 | 1980-01, 1980-11, 2000-08, 2007-10, 2019-12 | 1973-08, 2022-11 | — | — |
| 18 | D3-RED alone | 31/42 = 73.8% | 39.2% | 5/8 = 62.5% | 6/18 | 1980-01, 1980-11, 1987-08, 2000-08, 2011-04, 2021-12 | 2003-01, 2004-09, 2017-01 | 2007-11 | 2026-04 |
| 18 | D3-RED AND curve flat | 6/7 = 85.7% | 39.2% | 1/1 = 100.0% | 2/18 | 1980-01, 1980-11 | — | 2007-11 | — |

Read-out (h = 12):

- vs NBER onsets: curve flat alone: month precision 55.2% (base 16.2%), episodes 9/11, recall 10/10; D1-RED alone: month precision 18.4% (base 16.2%), episodes 3/10, recall 3/10; D1-RED AND curve flat: month precision 100.0% (base 16.2%), episodes 2/2, recall 2/10; D2 alone: month precision 29.5% (base 16.2%), episodes 5/8, recall 6/10; D2 AND curve flat: month precision 68.6% (base 16.2%), episodes 5/6, recall 6/10.
- vs B1 drawdown starts: curve flat alone: month precision 31.0% (base 22.6%), episodes 8/11, recall 8/15; D1-RED alone: month precision 51.0% (base 22.6%), episodes 5/9, recall 5/15; D1-RED AND curve flat: month precision 42.9% (base 22.6%), episodes 1/1, recall 1/15; D2 alone: month precision 22.5% (base 22.6%), episodes 5/8, recall 6/15; D2 AND curve flat: month precision 27.5% (base 22.6%), episodes 4/6, recall 4/15.
- On NBER onsets oil alone (D1-RED) is indistinguishable from the base rate at month level (18.4% vs 16.2%) and catches 3 of 10; the curve alone catches 10 of 10 at 55% month precision. Requiring oil AND curve leaves 7 ON months, 2 episodes, both hits (1979-08→1980-02, 2007-11→2008-01) — precision 100% on a recall of 2/10, i.e. oil removes 8 of the curve's 10 catches and adds no episode the curve did not already have. D2 AND curve: 5/6 episodes, 6/10 recall, 69% month precision — better than D2 alone but still strictly inside the curve's own catch set.
- On S&P drawdowns oil alone does BETTER than on recessions: D1-RED alone 51% month precision vs 23% base, 5/9 episodes (1980-11, 1987-08, 2000-08, 2018-09, 2021-12), and the four D1 false positives on drawdowns (2002-12, 2004-09, 2009-12, 2017-01) are also NBER false positives. That is the oil-shock/equity-drawdown link the pin board's 3–12m damage window is about, not a recession link.
- Against the deployed bundled numbers (oil-OR-policy window + curve: 45% / 5-of-6 on drawdowns, 37% / 4-of-4 on onsets; fast-red + curve 34% / 4-of-13): the isolated oil+curve leg is 1/1 (42.9% month) on B1 drawdowns and 2/2 (100% month) on onsets with recall 1/15 and 2/10. The bundled rule's hits were therefore coming mostly from the policy leg and the curve, not from oil; §5 'Always' row (split oil-alone / policy-alone in pin_rule_hindcast) is confirmed as necessary.

Comparison to the deployed accident gauge: the bundled oil-OR-policy+curve rule reported 45% / 5-of-6 on drawdowns and 37% / 4-of-4 on onsets. Oil-alone and oil-AND-curve numbers above are the isolated equivalents; where 'D1-RED AND curve flat' has fewer hits than 'curve flat alone', the oil leg is REMOVING recall from the curve rather than adding precision — see the rows.

## 6. Regime breakdown by SIGNAL month (R0 1947–1985, R1 1986–2008, R2 2009–2019, R3 2020+); NBER onsets, common window

### 6.1 h = 12

| regime | definition | ON months | episodes | hits | month precision | false positives (first ON) | pending | base rate |
|---|---|---|---|---|---|---|---|---|
| R0 | D1-RED | 6 | 2 | 1 | 6/6 = 100.0% | — | — | 24.1% |
| R0 | D2 | 31 | 3 | 2 | 19/31 = 61.3% | 1976-09 | — | 24.1% |
| R0 | D3-RED | 6 | 2 | 1 | 6/6 = 100.0% | — | — | 24.1% |
| R0 | D1-YELLOW | 10 | 2 | 1 | 10/10 = 100.0% | — | — | 24.1% |
| R0 | D3-YELLOW | 8 | 2 | 1 | 8/8 = 100.0% | — | — | 24.1% |
| R1 | D1-RED | 18 | 6 | 2 | 3/18 = 16.7% | 1987-07, 2002-12, 2004-09 | — | 14.5% |
| R1 | D2 | 69 | 4 | 2 | 18/69 = 26.1% | 1996-04 | — | 14.5% |
| R1 | D3-RED | 17 | 6 | 2 | 3/17 = 17.6% | 1987-07, 2003-01, 2004-09 | — | 14.5% |
| R1 | D1-YELLOW | 72 | 8 | 3 | 17/72 = 23.6% | 1987-03, 1995-02, 1996-09, 2002-10, 2004-04 | — | 14.5% |
| R1 | D3-YELLOW | 62 | 8 | 3 | 14/62 = 22.6% | 1987-03, 1996-09, 2002-10, 2004-04 | — | 14.5% |
| R2 | D1-RED | 9 | 3 | 0 | 0/9 = 0.0% | 2009-12, 2017-01, 2018-06 | — | 7.9% |
| R2 | D2 | 12 | 1 | 1 | 1/12 = 8.3% | — | — | 7.9% |
| R2 | D3-RED | 7 | 2 | 0 | 0/7 = 0.0% | 2009-12, 2017-01 | — | 7.9% |
| R2 | D1-YELLOW | 24 | 4 | 0 | 0/24 = 0.0% | 2009-11, 2011-03, 2016-12, 2018-03 | — | 7.9% |
| R2 | D3-YELLOW | 19 | 4 | 0 | 0/19 = 0.0% | 2009-11, 2011-04, 2016-12, 2018-04 | — | 7.9% |
| R3 | D1-RED | 16 | 2 | n/a (no scoreable onset) | — | 2021-03 | 2026-04 | 3.7% |
| R3 | D2 | 17 | 2 | n/a (no scoreable onset) | — | 2021-10 | 2026-04 | 3.7% |
| R3 | D3-RED | 12 | 2 | n/a (no scoreable onset) | — | 2021-03 | 2026-04 | 3.7% |
| R3 | D1-YELLOW | 18 | 2 | n/a (no scoreable onset) | — | 2021-03 | 2026-03 | 3.7% |
| R3 | D3-YELLOW | 18 | 2 | n/a (no scoreable onset) | — | 2021-03 | 2026-03 | 3.7% |

### 6.2 h = 18

| regime | definition | ON months | episodes | hits | month precision | false positives (first ON) | pending | base rate |
|---|---|---|---|---|---|---|---|---|
| R0 | D1-RED | 6 | 2 | 1 | 6/6 = 100.0% | — | — | 33.5% |
| R0 | D2 | 31 | 3 | 2 | 19/31 = 61.3% | 1976-09 | — | 33.5% |
| R0 | D3-RED | 6 | 2 | 1 | 6/6 = 100.0% | — | — | 33.5% |
| R0 | D1-YELLOW | 10 | 2 | 1 | 10/10 = 100.0% | — | — | 33.5% |
| R0 | D3-YELLOW | 8 | 2 | 1 | 8/8 = 100.0% | — | — | 33.5% |
| R1 | D1-RED | 18 | 6 | 2 | 9/18 = 50.0% | 1987-07, 2002-12, 2004-09 | — | 21.8% |
| R1 | D2 | 69 | 4 | 2 | 26/69 = 37.7% | 1996-04 | — | 21.8% |
| R1 | D3-RED | 17 | 6 | 2 | 9/17 = 52.9% | 1987-07, 2003-01, 2004-09 | — | 21.8% |
| R1 | D1-YELLOW | 72 | 8 | 3 | 25/72 = 34.7% | 1987-03, 1995-02, 1996-09, 2002-10, 2007-09 | — | 21.8% |
| R1 | D3-YELLOW | 62 | 8 | 3 | 20/62 = 32.3% | 1987-03, 1996-09, 2002-10, 2004-04 | — | 21.8% |
| R2 | D1-RED | 9 | 3 | 0 | 0/9 = 0.0% | 2009-12, 2017-01, 2018-06 | — | 12.7% |
| R2 | D2 | 12 | 1 | 1 | 7/12 = 58.3% | — | — | 12.7% |
| R2 | D3-RED | 7 | 2 | 0 | 0/7 = 0.0% | 2009-12, 2017-01 | — | 12.7% |
| R2 | D1-YELLOW | 24 | 4 | 1 | 2/24 = 8.3% | 2009-11, 2011-03, 2016-12 | — | 12.7% |
| R2 | D3-YELLOW | 19 | 4 | 1 | 2/19 = 10.5% | 2009-11, 2011-04, 2016-12 | — | 12.7% |
| R3 | D1-RED | 16 | 2 | n/a (no scoreable onset) | — | 2021-03 | 2026-04 | 4.2% |
| R3 | D2 | 17 | 2 | n/a (no scoreable onset) | — | 2021-10 | 2026-04 | 4.2% |
| R3 | D3-RED | 12 | 2 | n/a (no scoreable onset) | — | 2021-03 | 2026-04 | 4.2% |
| R3 | D1-YELLOW | 18 | 2 | n/a (no scoreable onset) | — | 2021-03 | 2026-03 | 4.2% |
| R3 | D3-YELLOW | 18 | 2 | n/a (no scoreable onset) | — | 2021-03 | 2026-03 | 4.2% |

## 7. Q5 — the three dated readings

| reading | value | grade / state | notes |
|---|---|---|---|
| Live daily channel (deployed, /pins as of 2026-09-15) | WTI 12m change +52.4% (print 2026-09-09 $97.26 vs 252 trading days earlier) | RED | score 81.0; /recession-model 12m 21.5% (band 17.8–25.7, AUC 0.686) on 3m10y CMT +0.86; TP-adj 12m 21.9% |
| Monthly mean, latest complete month 2026-08 — D1 | oil_12m_pct = +29.4% (WTISPLC 83.90) | YELLOW | peak of the 2026 episode: +64.3% in 2026-05 |
| Monthly mean 2026-08 — D3 real | real_oil_12m_pct = +25.2% | YELLOW | peak +57.7% in 2026-05 |
| NOPI12 2026-08 — D2 | nopi36_sum12 = 13.3 log-pct | ON at 8: ON / ON at 10 (headline): ON / ON at 12: ON | monthly spikes since 2026-01: 2026-03 2.2, 2026-04 9.3, 2026-05 1.8; peak sum12 13.3 in 2026-05 |

- Curve state now: spread_gs +0.96pp, 6-month min +0.64 → curve flat = False; live CMT +0.86.
- Curve-state caveat for the analogs: the fit basis (`spread_gs` 6-month min) says NOT flat throughout 2026, but the deployed daily-183 rule and the CMT basis both read flat in 2026-04 (§1(ii)/(iii)); on the deployed rule the closest curve-state analogs would be the flat-at-first-ON episodes 1979-08 (hit) and 2007-11 (hit) rather than the not-flat set below.
- The live daily print (RED, +52.4%) and the monthly-mean D1 (+29.4%, YELLOW) disagree on grade for the current month — exactly the point-vs-mean gap of §1(i); the monthly-mean episode (D1-RED) was ON only in 2026-04..05 and is PENDING.

### 7.1 Closest analog episodes (by peak reading, then by curve state at first ON)

**D1-RED** — current episode peak 64.3, curve flat at first ON = False (spread_gs +0.71)

| analog (first ON) | peak | abs Δpeak | curve at first ON | spread_gs | outcome (h=12) | event |
|---|---|---|---|---|---|---|
| 2002-12 | 73.0 | 8.7 | not flat | +2.84 | FALSE POSITIVE | — |
| 2004-09 | 75.2 | 10.9 | not flat | +2.48 | FALSE POSITIVE | — |
| 2018-06 | 52.2 | 12.1 | not flat | +1.01 | FALSE POSITIVE | — |
| 2017-01 | 76.4 | 12.1 | not flat | +1.92 | FALSE POSITIVE | — |

Same curve state (not flat) analogs, nearest by peak: 2002-12 (peak 73.0, FALSE POSITIVE); 2004-09 (peak 75.2, FALSE POSITIVE); 2018-06 (peak 52.2, FALSE POSITIVE); 2017-01 (peak 76.4, FALSE POSITIVE)

**D2** — current episode peak 13.3, curve flat at first ON = False (spread_gs +0.71)

| analog (first ON) | peak | abs Δpeak | curve at first ON | spread_gs | outcome (h=12) | event |
|---|---|---|---|---|---|---|
| 2018-04 | 17.1 | 3.8 | not flat | +1.11 | HIT | 2020-03 |
| 1976-09 | 22.0 | 8.7 | not flat | +2.51 | FALSE POSITIVE | — |
| 1996-04 | 22.1 | 8.9 | not flat | +1.56 | FALSE POSITIVE | — |
| 2000-02 | 30.4 | 17.1 | not flat | +0.97 | HIT | 2001-04 |

Same curve state (not flat) analogs, nearest by peak: 2018-04 (peak 17.1, HIT); 1976-09 (peak 22.0, FALSE POSITIVE); 1996-04 (peak 22.1, FALSE POSITIVE); 2000-02 (peak 30.4, HIT)

**D3-RED** — current episode peak 57.7, curve flat at first ON = False (spread_gs +0.71)

| analog (first ON) | peak | abs Δpeak | curve at first ON | spread_gs | outcome (h=12) | event |
|---|---|---|---|---|---|---|
| 2003-01 | 67.7 | 10.0 | not flat | +2.88 | FALSE POSITIVE | — |
| 1990-09 | 68.1 | 10.4 | not flat | +1.53 | COINCIDENT | — |
| 2004-09 | 69.8 | 12.1 | not flat | +2.48 | FALSE POSITIVE | — |
| 2017-01 | 71.5 | 13.8 | not flat | +1.92 | FALSE POSITIVE | — |

Same curve state (not flat) analogs, nearest by peak: 2003-01 (peak 67.7, FALSE POSITIVE); 1990-09 (peak 68.1, COINCIDENT); 2004-09 (peak 69.8, FALSE POSITIVE); 2017-01 (peak 71.5, FALSE POSITIVE)

## 8. Figures

- `fig1_oil_history.png` — nominal (top) and real (bottom) WTI 12-month % change 1947–2026 with NBER bands, +25/+50 lines, and every D1-RED / D2 / D3-RED episode start marked with its h = 12 outcome (shape + label + status colour).
- `fig4_lead_strip.png` — one row per NBER onset (top, 11) and per B1 drawdown start (bottom, 15): lead in months from the crediting episode's first ON month for D1-RED / D2 / D3-RED, with coincident and missed labelled; vertical guides at h = 12 and 18.

## 9. Reading choices where the spec is ambiguous (logged, not searched)

1. In-recession ON months are not 'OFF months': they neither count (USREC=0 filter) nor break an episode; the raw first ON month (possibly in-recession) drives the coincident test — required to reproduce the spec's own 1973-12 / 1990-08 expectations.
2. Classification precedence: hit > coincident > pending > false positive; an episode with no USREC=0 month and no coincident onset is 'in-recession (excluded)'.
3. Resolved: t + h ≤ 2025-08 (spec text), so the last resolved ON month is 2024-08 (h=12) / 2024-02 (h=18).
4. Recall evaluability by the rule's own series start (not the common precision window); curve rules start 1953-09.
5. Drawdown scoring re-uses the NBER episode machinery (USREC=0 filter, coincident window [e, e+3], resolved rule) with no double-dip rule; evaluable if e − h ≥ series start.
6. Month-level precision is mechanical over all USREC=0 resolved ON months; the variant excluding coincident-episode months is shown beside it.
7. '≥ 1 episode better' (§5 D2-vs-D1 row) read as ≥ 1 more hit or ≥ 1 fewer false positive with recall ≥ D1's.
