"""Fed Z.1 (Financial Accounts) L.213 / F.213: who holds US "corporate and
foreign bonds", by sector, via FRED's keyless CSV mirrors (BOGZ1 ids).

Three kinds of series, and the unit trap this module exists to police:
  FL = level, end of quarter, NSA            ($ millions)
  FA = transactions, seasonally adjusted ANNUAL RATE (SAAR)
  FU = transactions, NOT annualised, NSA
A SAAR flow is ~4x the quarterly flow; mixing FA with FU (the memo's FRED-FU893
vs FA893 example: 299,829 vs 1,351,916 for 2026Q2) silently overstates or
understates by 4x. Every series here carries its kind, `sum_flows` refuses to
add different kinds, and the payload reports the FA/FU ratio so a wrong code
shows up as a number, not a silent error.

FRED does not mirror every line (verified live 2026-10-15): the headline
rest-of-world level (FL263063005) and the households level/SAAR flow
(FL/FA153063005) 404, as do the ex-eREIT nonfinancial lines. Those sectors are
DERIVED from partition identities built on lines FRED does serve:
  rest of world  = all sectors - domestic nonfinancial (FL38) - private
                   depository & MMFs (FL78) - other financial + insurance &
                   pensions (FL91) - monetary authority (FL713011525, "other
                   U.S. reserves, foreign securities", ~$10bn; FRED mirrors it)
                   [= the Z.1 ROW line FL263063005 to the dollar: 5,195.694
                   for 2026Q2 against the package]
  households     = domestic nonfinancial (FL38) - general government (FL36)
                   [includes equity REITs' ~$14bn of holdings]
  other financial = other financial corps & MMFs (FL85) minus the funds listed
  other depository = private depository & MMFs (FL78) minus banks, foreign
                   banking offices and MMFs (credit unions, affiliated areas)
The instrument is "corporate and foreign bonds": US corporates + foreign bonds
held in the US + private-label ABS; the rest-of-world line is "corporate
bonds" (US issuers). Quarterly, ~10-week lag. $ millions -> $bn here.
"""
from __future__ import annotations

import logging
from datetime import date

from . import fred_csv

logger = logging.getLogger(__name__)

# Sector -> (level code, SAAR flow code). Codes are FRED ids; the Z.1 mnemonic
# is the 9-digit core (sector 2 digits, instrument 3063, series 005/003/045/095).
SECTORS: dict[str, dict] = {
    "all_sectors":            {"label": "All sectors (L.213 total)",
                               "FL": "BOGZ1FL893063005Q", "FA": "BOGZ1FA893063005Q"},
    "rest_of_world":          {"label": "Rest of the world (foreign holders)",
                               "FL": None, "FA": "ROWCBAQ027S", "derived_level": True},
    "rest_of_world_ex_abs":   {"label": "Rest of the world, US corporate bonds ex MBS/ABS",
                               "FL": "BOGZ1FL263063095Q", "FA": "BOGZ1FA263063095Q",
                               "memo": True},
    "life_insurers":          {"label": "Life insurers",
                               "FL": "BOGZ1FL543063005Q", "FA": "BOGZ1FA543063005Q"},
    "pc_insurers":            {"label": "Property-casualty insurers (incl. residual-market reinsurers)",
                               "FL": "BOGZ1FL513063005Q", "FA": "BOGZ1FA513063005Q"},
    "private_pensions":       {"label": "Private pension funds",
                               "FL": "BOGZ1FL573063005Q", "FA": "BOGZ1FA573063005Q"},
    "state_local_pensions":   {"label": "State & local government employee DB pension funds",
                               "FL": "BOGZ1FL223063045Q", "FA": "BOGZ1FA223063045Q"},
    "federal_pensions":       {"label": "Federal government retirement funds",
                               "FL": "BOGZ1FL343063005Q", "FA": "BOGZ1FA343063005Q"},
    "mutual_funds":           {"label": "Mutual funds",
                               "FL": "BOGZ1FL653063005Q", "FA": "BOGZ1FA653063005Q"},
    "etfs":                   {"label": "Exchange-traded funds",
                               "FL": "BOGZ1FL563063003Q", "FA": "BOGZ1FA563063003Q"},
    "closed_end_funds":       {"label": "Closed-end funds",
                               "FL": "BOGZ1FL553063003Q", "FA": "BOGZ1FA553063003Q"},
    "hedge_funds":            {"label": "Hedge funds (domestic, long value)",
                               "FL": "BOGZ1FL623063003Q", "FA": "BOGZ1FA623063003Q"},
    "money_market_funds":     {"label": "Money market funds",
                               "FL": "BOGZ1FL633063005Q", "FA": "BOGZ1FA633063005Q"},
    "other_financial":        {"label": "Other financial (GSEs, brokers, finance & holding cos, other funds)",
                               "FL": None, "FA": None, "derived_level": True, "derived_flow": True},
    "banks_us_chartered":     {"label": "US-chartered depository institutions (incl. IBFs)",
                               "FL": "BOGZ1FL763063005Q", "FA": "BOGZ1FA763063005Q"},
    "foreign_banking_offices": {"label": "Foreign banking offices in the US",
                                "FL": "BOGZ1FL753063005Q", "FA": "BOGZ1FA753063005Q"},
    "other_depository":       {"label": "Credit unions and banks in US-affiliated areas",
                               "FL": None, "FA": None, "derived_level": True, "derived_flow": True},
    "households":             {"label": "Households & nonprofits (residual sector; incl. eREITs)",
                               "FL": None, "FA": None, "derived_level": True, "derived_flow": True},
    "general_government":     {"label": "Federal, state & local governments",
                               "FL": "BOGZ1FL363063005Q", "FA": "BOGZ1FA363063005Q"},
}
# Aggregates that FRED serves and the derivations lean on.
AGGREGATES: dict[str, dict] = {
    "domestic_nonfinancial":  {"FL": "BOGZ1FL383063005Q", "FA": "BOGZ1FA383063005Q"},
    "priv_depository_and_mmf": {"FL": "BOGZ1FL783063005Q", "FA": "BOGZ1FA783063005Q"},
    "other_fin_ins_pens":     {"FL": "BOGZ1FL913063005Q", "FA": "BOGZ1FA913063005Q"},
    "other_fin_and_mmf":      {"FL": "BOGZ1FL853063005Q", "FA": "BOGZ1FA853063005Q"},
    "pension_funds_total":    {"FL": "BOGZ1FL593063005Q", "FA": "BOGZ1FA593063005Q"},
    # monetary authority: other U.S. reserves, foreign securities (level only;
    # subtracted so the derived rest-of-world equals the Z.1 ROW line exactly)
    "central_bank_reserves":  {"FL": "BOGZ1FL713011525Q", "FA": None},
}
# Unannualised flows (FU) — fetched only to police the units and for the
# households line FRED does serve unannualised.
UNADJUSTED: dict[str, str] = {
    "all_sectors": "BOGZ1FU893063005Q",
    "households": "BOGZ1FU153063005Q",
    "nfc_issuance": "BOGZ1FU103163005Q",
}
# Nonfinancial corporate business net bond issuance (liability side).
NFC_ISSUANCE_SAAR = "BOGZ1FA103163005Q"            # incl. equity REITs (the spec's series)
NFC_ISSUANCE_SAAR_EX_REITS = "NCBCBLQ027S"          # FRED's human-named ex-eREIT line
NFC_ISSUANCE_LEVEL = "BOGZ1FL103163005Q"

_FUNDS_IN_OTHER_FIN = ("mutual_funds", "etfs", "closed_end_funds", "hedge_funds", "money_market_funds")
_DEPOSITORY_NAMED = ("banks_us_chartered", "foreign_banking_offices", "money_market_funds")
_PARTITION = ("rest_of_world", "households", "general_government", "life_insurers", "pc_insurers",
              "private_pensions", "state_local_pensions", "federal_pensions", "mutual_funds",
              "etfs", "closed_end_funds", "hedge_funds", "money_market_funds", "other_financial",
              "banks_us_chartered", "foreign_banking_offices", "other_depository")
BASIS = ("Fed Z.1 L.213/F.213 via FRED keyless CSV; instrument = corporate and foreign bonds "
         "(US corporates + foreign bonds held in the US + private-label ABS); levels NSA end of "
         "quarter, flows SAAR unless marked unannualised; $bn")


def kind(code: str) -> str:
    """'FL' | 'FA' | 'FU' for a FRED Z.1 id; human-named ids are looked up."""
    if code.startswith("BOGZ1F") and code[6] in "LAU":
        return "F" + code[6]
    if code in ("ROWCBAQ027S", NFC_ISSUANCE_SAAR_EX_REITS):
        return "FA"   # FRED titles: "...Transactions", which FRED serves at SAAR
    raise ValueError(f"unknown Z.1 series kind for {code}")


class Series:
    """One Z.1 series with its unit kind attached, so flows cannot be mixed."""
    __slots__ = ("code", "kind", "values")

    def __init__(self, code: str, values: list[float | None], kind_: str | None = None):
        self.code = code
        self.kind = kind_ or kind(code)
        self.values = values

    def __repr__(self) -> str:
        return f"Series({self.code}, {self.kind}, n={len(self.values)})"


def combine(a: Series, b: Series, op: str, code: str = "derived") -> Series:
    """a ± b with the same kind only; a FA/FU (or FL/flow) mix raises."""
    if a.kind != b.kind:
        raise ValueError(f"refusing to mix Z.1 kinds {a.kind} ({a.code}) and {b.kind} ({b.code})")
    if op not in ("+", "-"):
        raise ValueError(op)
    vals = [None if x is None or y is None else round(x + y if op == "+" else x - y, 3)
            for x, y in zip(a.values, b.values)]
    return Series(code, vals, a.kind)


def sum_flows(parts: list[Series], code: str = "sum") -> Series:
    """Sum of flows of ONE kind; raises on a mixed list."""
    kinds = {p.kind for p in parts}
    if len(kinds) != 1:
        raise ValueError(f"refusing to sum mixed Z.1 kinds: {sorted(kinds)}")
    out = parts[0]
    for p in parts[1:]:
        out = combine(out, p, "+", code)
    return Series(code, out.values, out.kind)


def _quarter(d: date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _bn(v: float | None) -> float | None:
    return None if v is None else round(v / 1000.0, 3)


def _ratio(num: list[float | None], den: list[float | None], n: int) -> float | None:
    """mean(num) / mean(den) over the last n common observations."""
    a = [x for x in num[-n:] if x is not None]
    b = [y for y in den[-n:] if y is not None]
    if len(a) < n or len(b) < n or not sum(b):
        return None
    return round((sum(a) / n) / (sum(b) / n), 3)


def fetch_holders(start: str = "2015-01-01") -> dict:
    """Holder-sector levels (FL) and SAAR flows (FA) of corporate & foreign
    bonds, $bn, quarterly from `start`, with the derivations and unit checks
    described in the module docstring."""
    direct_ids = [c for s in SECTORS.values() for c in (s["FL"], s["FA"]) if c]
    direct_ids += [c for a in AGGREGATES.values() for c in (a["FL"], a["FA"]) if c]
    direct_ids += list(UNADJUSTED.values()) + [NFC_ISSUANCE_SAAR, NFC_ISSUANCE_SAAR_EX_REITS,
                                               NFC_ISSUANCE_LEVEL]
    raw = fred_csv.fetch_many(direct_ids, start)
    axis = sorted({d for ds, _ in raw.values() for d in ds})
    quarters = [_quarter(d) for d in axis]

    def ser(code: str) -> Series:
        ds, vs = raw.get(code, ([], []))
        m = {d: _bn(v) for d, v in zip(ds, vs)}
        return Series(code, [m.get(d) for d in axis])

    # direct series, by sector and kind
    lv: dict[str, Series] = {}
    fl: dict[str, Series] = {}
    for key, s in SECTORS.items():
        if s["FL"]:
            lv[key] = ser(s["FL"])
        if s["FA"]:
            fl[key] = ser(s["FA"])
    agg_lv = {k: ser(a["FL"]) for k, a in AGGREGATES.items() if a["FL"]}
    agg_fl = {k: ser(a["FA"]) for k, a in AGGREGATES.items() if a["FA"]}

    # derivations — each step is same-kind arithmetic, so combine() enforces it
    for lab, book, agg in (("level", lv, agg_lv), ("flow", fl, agg_fl)):
        if lab == "level":
            row = combine(combine(combine(combine(book["all_sectors"], agg["domestic_nonfinancial"], "-"),
                                          agg["priv_depository_and_mmf"], "-"), agg["other_fin_ins_pens"], "-"),
                          agg["central_bank_reserves"], "-", "rest_of_world:derived")
            book["rest_of_world"] = row
        book["households"] = combine(agg["domestic_nonfinancial"], book["general_government"], "-",
                                     "households:derived")
        other_fin = agg["other_fin_and_mmf"]
        for k in _FUNDS_IN_OTHER_FIN:
            other_fin = combine(other_fin, book[k], "-")
        book["other_financial"] = Series("other_financial:derived", other_fin.values, other_fin.kind)
        other_dep = agg["priv_depository_and_mmf"]
        for k in _DEPOSITORY_NAMED:
            other_dep = combine(other_dep, book[k], "-")
        book["other_depository"] = Series("other_depository:derived", other_dep.values, other_dep.kind)

    # partition check: the 17 display sectors should re-sum to the L.213 total
    part_l = sum_flows([lv[k] for k in _PARTITION], "partition")
    gap = [None if a is None or b is None or not b else round(100.0 * (a - b) / b, 3)
           for a, b in zip(part_l.values, lv["all_sectors"].values)]
    part_f = sum_flows([fl[k] for k in _PARTITION], "partition")

    fu_all = ser(UNADJUSTED["all_sectors"])
    fu_hh = ser(UNADJUSTED["households"])
    fu_nfc = ser(UNADJUSTED["nfc_issuance"])
    fu_all.kind = fu_hh.kind = fu_nfc.kind = "FU"
    nfc = ser(NFC_ISSUANCE_SAAR)
    nfc_ex = ser(NFC_ISSUANCE_SAAR_EX_REITS)
    nfc_lv = ser(NFC_ISSUANCE_LEVEL)
    fa_fu_latest = _ratio(fl["all_sectors"].values, fu_all.values, 1)
    fa_fu_4q = _ratio(fl["all_sectors"].values, fu_all.values, 4)
    unit_ok = fa_fu_4q is not None and 3.5 <= fa_fu_4q <= 4.6
    if fa_fu_4q is not None and not unit_ok:
        logger.warning("Z.1 unit check failed: FA/FU over 4q = %s (expected ~4)", fa_fu_4q)

    sectors_out = []
    for key, s in SECTORS.items():
        sectors_out.append({"key": key, "label": s["label"], "level_code": s["FL"],
                            "flow_code": s["FA"], "derived_level": bool(s.get("derived_level")),
                            "derived_flow": bool(s.get("derived_flow")), "memo": bool(s.get("memo")),
                            "in_partition": key in _PARTITION})
    ids_for_status = [c for c in direct_ids]
    return {
        "asof": quarters[-1] if quarters else None,
        "quarters": quarters,
        "dates": [d.isoformat() for d in axis],
        "unit": "$bn",
        "basis": BASIS,
        "levels": {k: v.values for k, v in lv.items()},
        "flows_saar": {k: v.values for k, v in fl.items()},
        "flows_unadj": {"all_sectors": fu_all.values, "households": fu_hh.values,
                        "nfc_issuance": fu_nfc.values},
        "pensions": {
            "private": {"level": lv["private_pensions"].values, "flow_saar": fl["private_pensions"].values},
            "state_local": {"level": lv["state_local_pensions"].values,
                            "flow_saar": fl["state_local_pensions"].values},
            "federal": {"level": lv["federal_pensions"].values, "flow_saar": fl["federal_pensions"].values},
            "total": {"level": agg_lv["pension_funds_total"].values,
                      "flow_saar": agg_fl["pension_funds_total"].values},
        },
        "nfc_issuance": {"saar": nfc.values, "saar_ex_reits": nfc_ex.values, "level": nfc_lv.values,
                         "unadj": fu_nfc.values, "codes": {"saar": NFC_ISSUANCE_SAAR,
                                                           "saar_ex_reits": NFC_ISSUANCE_SAAR_EX_REITS,
                                                           "level": NFC_ISSUANCE_LEVEL,
                                                           "unadj": UNADJUSTED["nfc_issuance"]}},
        "sectors": sectors_out,
        "derived": {
            "rest_of_world": "all sectors - domestic nonfinancial - private depository & MMFs - "
                             "other financial, insurance & pensions - monetary authority (FL713011525, "
                             "~$10bn); equals the Z.1 ROW line FL263063005, which FRED does not mirror; "
                             "SAAR flow is FRED ROWCBAQ027S",
            "households": "domestic nonfinancial - general government (includes equity REITs)",
            "other_financial": "other financial corps & MMFs minus mutual, exchange-traded, "
                               "closed-end, hedge and money market funds",
            "other_depository": "private depository & MMFs minus US-chartered banks, foreign "
                                "banking offices and MMFs",
        },
        "checks": {
            "fa_over_fu_latest": fa_fu_latest,
            "fa_over_fu_4q": fa_fu_4q,
            "units_consistent": unit_ok,
            "partition_gap_pct": gap,
            "partition_level_sum": part_l.values,
            "partition_flow_sum": part_f.values,
        },
        "src": {"fred_pattern": fred_csv.url("BOGZ1FL<sector>3063005Q"),
                "all_sectors_level": fred_csv.url(SECTORS["all_sectors"]["FL"]),
                "all_sectors_saar": fred_csv.url(SECTORS["all_sectors"]["FA"]),
                "all_sectors_unadj": fred_csv.url(UNADJUSTED["all_sectors"]),
                "nfc_issuance_saar": fred_csv.url(NFC_ISSUANCE_SAAR),
                "z1_release": "https://www.federalreserve.gov/releases/z1/"},
        "status": fred_csv.worst_status(ids_for_status),
    }
