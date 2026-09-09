"""Merge-blocking gate tests for the EDGAR nowcast layer.

The entire value of this layer is that it counts FILINGS and not index
ROWS. form.idx emits one row per filer, so a registration with forty
co-registrant subsidiaries produces forty rows for one document.
Counting rows measures corporate structure, not deal activity - and
the measured inflation reaches 8.7x on S-4. Gate 1 is therefore the
reason this file exists.
"""

import ma_edgar as me


def _row(form, cik, date, acc):
    return (f"{form:<16} SOME COMPANY NAME {cik:<10} {date}  "
            f"edgar/data/{cik}/{acc}.txt")


# --- GATE 1: rows are not filings ----------------------------------

def test_co_registrants_collapse_to_one_filing():
    """THE load-bearing gate. Forty filers, one accession, one filing."""
    acc = "0000912057-25-000001"
    rows = [_row("DEFM14A", 1000 + i, "2025-01-15", acc) for i in range(40)]
    m = me.parse_index_lines(rows)
    assert len(m[("2025-01", "DEFM14A")]) == 1, (
        "co-registrant rows were counted as separate filings - this is "
        "the 8.7x S-4 inflation bug")


def test_distinct_accessions_are_kept_apart():
    rows = [
        _row("DEFM14A", 1, "2025-01-15", "0000912057-25-000001"),
        _row("DEFM14A", 2, "2025-01-16", "0000912057-25-000002"),
        _row("DEFM14A", 3, "2025-01-17", "0000912057-25-000003"),
    ]
    m = me.parse_index_lines(rows)
    assert sum(len(v) for v in m.values()) == 3


def test_only_the_two_clean_forms_are_counted():
    """S-4, SC 13D, SC TO-T and 425 are excluded BY DESIGN, not by
    oversight - each needs a documented dedup and break adjustment
    before it could earn a place."""
    assert set(me.FORMS) == {"DEFM14A", "PREM14A"}
    rows = [
        _row("S-4", 1, "2025-01-15", "0000912057-25-000001"),
        _row("SC TO-T", 2, "2025-01-15", "0000912057-25-000002"),
        _row("425", 3, "2025-01-15", "0000912057-25-000003"),
        _row("SCHEDULE 13D", 4, "2025-01-15", "0000912057-25-000004"),
        _row("DEFM14A", 5, "2025-01-15", "0000912057-25-000005"),
    ]
    m = me.parse_index_lines(rows)
    assert sum(len(v) for v in m.values()) == 1
    assert ("2025-01", "DEFM14A") in m


def test_months_are_split_by_filing_date():
    rows = [
        _row("DEFM14A", 1, "2025-01-31", "0000912057-25-000001"),
        _row("DEFM14A", 2, "2025-02-01", "0000912057-25-000002"),
    ]
    m = me.parse_index_lines(rows)
    assert len(m[("2025-01", "DEFM14A")]) == 1
    assert len(m[("2025-02", "DEFM14A")]) == 1


def test_malformed_rows_are_dropped_not_guessed():
    rows = [
        "DEFM14A   NO DATE OR ACCESSION HERE",
        "",
        "   ",
        _row("DEFM14A", 1, "2025-01-15", "0000912057-25-000001"),
    ]
    m = me.parse_index_lines(rows)
    assert sum(len(v) for v in m.values()) == 1


# --- GATE 2: the phase-in cutoff is real ---------------------------

def test_pre_1997_is_not_scoreable():
    """EDGAR became mandatory only in May 1996. DEFM14A per quarter runs
    8 (1994Q1) -> 27 (1996Q1) -> 92 (2000Q1); a series starting before
    then measures EDGAR ADOPTION, not deal activity."""
    for q in ("1994Q1", "1995Q4", "1996Q1", "1996Q4"):
        assert not me.scoreable(q), f"{q} must not score"
    for q in ("1997Q1", "2000Q1", "2026Q1"):
        assert me.scoreable(q), f"{q} must score"


def test_ingest_starts_before_scoring_starts():
    """We ingest from 1994 deliberately so the adoption ramp is visible
    on the chart and the cutoff is arguable from the data rather than
    asserted."""
    iy, iq = me.INGEST_FROM
    sy, sq = int(me.SCORE_FROM[:4]), int(me.SCORE_FROM[5])
    assert (iy, iq) < (sy, sq)


# --- GATE 3: the traps stay documented -----------------------------

def test_rename_map_is_present():
    """SC 14D1 -> SC TO-T (Jan 2000) and SC 13D -> SCHEDULE 13D (Dec
    2024) silently zero a series. Neither form is used, but the map
    must survive so that re-adding one is a deliberate act."""
    assert "SC 14D1" in me.KNOWN_RENAMES
    assert "SC 13D" in me.KNOWN_RENAMES
    for old, (new, when) in me.KNOWN_RENAMES.items():
        assert new and len(when) == 7


def test_sec_user_agent_is_set():
    """SEC BLOCKS requests without a descriptive contact UA - the exact
    opposite of FRED, which returns an empty reply to any custom UA.
    The two fetchers disagree on purpose."""
    assert "@" in me.SEC_UA and len(me.SEC_UA) > 20
