# Frozen ICE BofA reference history

FRED's note on every `BAML*` series: **"Starting in April 2026, this series will only include
3 years of observations."** Anything ranking one of these against "its history" silently became a
3-year rank on that date. Measured consequences before this reference existed: the pin board's CCC
percentile read **99.2** when the true full-history rank was **~62**, and the severity index's HY
complacency component read **87.2** against a true **96.1**.

These files supply the dropped history. `app/sources/ice_reference.py` splices them onto whatever
FRED still serves, at the source layer, so every consumer is fixed at once. **Live FRED values
always win on overlap**; these files only cover dates FRED no longer returns, and are never
fetched at runtime.

## Files

| series | rows | range | sha256 |
|---|---|---|---|
| `BAMLC0A0CM` | 6,183 | 2000-01-03 .. 2023-09-08 | `7114dc8ff2ad330c1160db1069b20f0c2edb2c3627c6ef07a11f92d8f47c65f3` |
| `BAMLC0A4CBBB` | 6,967 | 1996-12-31 .. 2023-09-08 | `857081bb0f2ff189db1b5d022fba0eb58b341a748b1f0382ad1ce2cdc37760c6` |
| `BAMLH0A0HYM2` | 6,967 | 1996-12-31 .. 2023-09-08 | `4258d28b7ba01c5195570be19c9361682fc561bacd86b06f66a5e3b1570233ab` |
| `BAMLH0A3HYC` | 6,660 | 1996-12-31 .. 2022-07-06 | `4c76b56285ea4f1cbc4ef584ebe2127647d2f8ac3df8705ec3b6010eee968ba6` |

## Provenance

Reconstructed from public mirrors of FRED's own pre-truncation exports, then reconciled against
FRED's live authoritative window. **Every overlapping date matched at 1e-4 with zero mismatches:**

| check | overlap | mismatches |
|---|---|---|
| `BAMLH0A3HYC` (CCC) vs FRED live | 787 | **0** |
| `BAMLC0A4CBBB` (BBB) vs FRED live | 787 | **0** |
| `BAMLH0A0HYM2` (HY) vs FRED live | 787 | **0** |
| `BAMLC0A0CM` (IG) vs FRED live | 778 | **0** |
| HY across three independent mirrors | 6,962-7,599 | **0** |
| CCC across two independent exports | 5,229 | **0** |

Published extremes reproduce exactly: CCC record high **44.29 (2008-12-15)** and low **4.14
(2007-06-05)**; HY high **21.82 (2008-12-15)** and low **2.41 (2007-06-01)**.

Upstream sources:

- `raw.githubusercontent.com/mattdburke/ngfs-credit-ratings/main/rawdata/fredgraph.csv` — a
  verbatim multi-tier FRED export (CCC, BBB, and five other ICE tiers), 1996-12-31..2022-07-06.
- `raw.githubusercontent.com/fagan2888/GMS_VAAS/master/IR_txt_2/data/BAMLH0A3HYC.txt` — a FRED
  `.txt` export carrying FRED's own header block, used as the independent CCC cross-check.
- `raw.githubusercontent.com/viki-m13/bonds/main/data/fred/{BAMLC0A4CBBB,BAMLC0A0CM}.csv`
- `raw.githubusercontent.com/maaurocp/Trading_Protocol/main/data/raw/fred_BAMLH0A0HYM2.csv`

## Known gap — deliberate

`BAMLH0A3HYC` (CCC) has **no data for 2022-07-07 .. 2023-09-10 (432 days, 5.8%)**. It is left as a
hole. Interpolating it would fabricate history in the series used to rank credit distress. It
contains neither record extreme nor any episode peak the anchors cite, though it does span the
2022-H2 selloff and the March-2023 SVB episode. Closing it needs a pre-April-2026 FRED download or
an archived capture of FRED's own CSV endpoint.

## Caveats

- **Licensing.** These are redistributions of ICE Data Indices content. Freezing them here was an
  explicit owner decision (PIN_SATURATION.md DD Q24), not a default. The licensed alternative is a
  paid FRED tier or ICE direct.
- **Not point-in-time.** Current-vintage snapshots taken on different dates, so an expanding
  percentile built on them carries mild look-ahead if ICE ever revised history. Evidence says it
  does not: 5,229 CCC days agreeing across snapshots ~5 years apart, zero mismatches.
- **Never fetch upstream at runtime.** Unversioned personal repos are deletable and rewritable.
  Pull once, freeze, verify by checksum.
