#!/usr/bin/env python3
"""Candidate semiconductor universe for point-in-time SOXX/SOX reconstruction.

Survivorship-bias discipline: this list INCLUDES names that were acquired,
merged away, or delisted during 2010-2026. Ranking the *whole* candidate set
by point-in-time market cap at each rebalance date is what keeps 2013's
basket full of 2013's winners (BRCM, ALTR, XLNX) instead of 2026's (NVDA).

Ticker-reuse hazard: several dead tickers were later reassigned to unrelated
companies (ALTR = Altera until 2015, Altair Engineering after 2017; CY,
LLTC, ISIL etc. vary by vendor). fetch_data.py truncates every name in
DEAD_TICKERS at its `through` date and logs any series that extends past it,
so a reused ticker can never leak a foreign company's returns into the
basket.
"""

# --- currently listed (2026) semis and semicap ------------------------------
LIVE = [
    # logic / compute
    "NVDA", "AMD", "INTC", "AVGO", "QCOM", "TXN", "ADI", "MRVL", "NXPI",
    "MCHP", "ON", "MPWR", "LSCC", "SLAB", "SIMO", "RMBS", "CRUS", "POWI",
    "SYNA", "MTSI", "DIOD", "MXL", "SMTC", "AOSL", "CEVA", "HIMX", "ALGM",
    "INDI", "NVEC", "MRAM", "VSH", "WOLF", "AMBA", "SITM", "PI", "CRDO",
    # memory / storage
    "MU", "SGH",
    # foundry / IDM ADRs and US listings
    "TSM", "UMC", "ASX", "GFS", "TSEM", "STM", "ASML",
    # RF / analog
    "SWKS", "QRVO",
    # semicap / materials / test
    "AMAT", "LRCX", "KLAC", "TER", "ENTG", "MKSI", "AMKR", "ONTO", "FORM",
    "CAMT", "NVMI", "ICHR", "UCTT", "VECO", "KLIC", "ACLS", "AEIS", "COHR",
    "OLED", "AXTI",
    # newer listings (PIT membership handled by first-trade date)
    "ARM", "ALAB",
]

# --- dead / acquired names, with the last date their data is trustworthy ----
# `through` = last trading month the ticker represented THAT company. Sourced
# from deal close dates; fetch_data.py hard-truncates on these.
DEAD_TICKERS = {
    "XLNX": "2022-02-28",   # acquired by AMD
    "MXIM": "2021-08-31",   # acquired by ADI
    "BRCM": "2016-02-29",   # Avago/Broadcom merger
    "ALTR": "2015-12-31",   # acquired by Intel (ticker later reused)
    "IDTI": "2019-03-31",   # acquired by Renesas
    "CY":   "2020-04-30",   # Cypress -> Infineon
    "CAVM": "2018-07-31",   # Cavium -> Marvell
    "ISIL": "2017-02-28",   # Intersil -> Renesas
    "LLTC": "2017-03-31",   # Linear Tech -> ADI
    "FCS":  "2016-09-30",   # Fairchild -> ON
    "ATML": "2016-04-30",   # Atmel -> Microchip
    "MSCC": "2018-05-31",   # Microsemi -> Microchip
    "PMCS": "2016-01-31",   # PMC-Sierra -> Microsemi
    "SNDK": "2016-05-31",   # SanDisk -> Western Digital
    "IPHI": "2021-04-30",   # Inphi -> Marvell
    "NPTN": "2022-08-31",   # NeoPhotonics -> Lumentum
    "IRF":  "2015-01-31",   # Int'l Rectifier -> Infineon
    "VTSS": "2015-04-30",   # Vitesse -> Microsemi
    "SIMG": "2015-03-31",   # Silicon Image -> Lattice
    "OVTI": "2016-01-31",   # OmniVision -> consortium
    "ISSI": "2015-12-31",   # ISSI -> Uphill
    "NVLS": "2012-06-30",   # Novellus -> Lam Research
    "VSEA": "2011-11-30",   # Varian Semi -> Applied Materials
    "TQNT": "2014-12-31",   # TriQuint -> Qorvo
    "RFMD": "2014-12-31",   # RFMD -> Qorvo
    "NANO": "2019-10-31",   # Nanometrics -> Onto
    "RTEC": "2019-10-31",   # Rudolph -> Onto
    "AMCC": "2017-01-31",   # Applied Micro -> MACOM
    "PLXT": "2014-08-31",   # PLX Technology -> Avago
    "SPIL": "2018-04-30",   # Siliconware -> ASE
    "EXAR": "2017-05-31",   # Exar -> MaxLinear
    "MTSN": "2021-01-31",   # Mattson -> Beijing E-Town
    "IIVI": "2022-09-30",   # II-VI renamed Coherent (COHR)
    "CREE": "2021-10-31",   # Cree renamed Wolfspeed (WOLF)
}

DEAD = sorted(DEAD_TICKERS)

# Benchmarks / instruments (not index members).
INSTRUMENTS = ["SOXL", "SOXS", "SOXX", "SPY", "QQQ"]

ALL_TICKERS = INSTRUMENTS + LIVE + DEAD

# ICE Semiconductor Index capping rules (SOXX's benchmark since 2021-06;
# the prior PHLX SOX used a similar modified-cap scheme). Applied in
# universe.py's weighting helper and validated in tests.
INDEX_SIZE = 30
CAP_TOP5 = 0.08      # top 5 by weight capped at 8% each
CAP_REST = 0.04      # remaining names capped at 4% each


def modified_cap_weights(caps, index_size=INDEX_SIZE,
                         cap_top5=CAP_TOP5, cap_rest=CAP_REST):
    """ICE-style modified cap weighting: rank, take top `index_size`, cap the
    top 5 at 8% and everyone else at 4%, redistribute the overflow pro-rata
    to uncapped names, iterating to convergence.

    `caps` is a {ticker: market_cap} mapping. Returns {ticker: weight}
    summing to 1.0. Pure function -> unit-tested against known edge cases.
    """
    ranked = sorted(caps.items(), key=lambda kv: -kv[1])[:index_size]
    if not ranked:
        return {}
    names = [t for t, _ in ranked]
    total = sum(c for _, c in ranked)
    w = {t: c / total for t, c in ranked}

    # Cap assignment follows the *market-cap* rank (index rulebook), so the
    # cap tier is fixed before iteration rather than chasing weights.
    caps_by_name = {t: (cap_top5 if i < 5 else cap_rest)
                    for i, t in enumerate(names)}

    for _ in range(100):
        over = {t: w[t] - caps_by_name[t] for t in names if w[t] > caps_by_name[t] + 1e-12}
        if not over:
            break
        spill = sum(over.values())
        for t in over:
            w[t] = caps_by_name[t]
        free = [t for t in names if t not in over and w[t] < caps_by_name[t] - 1e-12]
        if not free:
            break  # everything capped; renormalize below
        free_total = sum(w[t] for t in free)
        if free_total <= 0:
            break
        for t in free:
            w[t] += spill * w[t] / free_total

    s = sum(w.values())
    return {t: v / s for t, v in w.items()}
