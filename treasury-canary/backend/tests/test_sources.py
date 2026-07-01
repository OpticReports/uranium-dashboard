from datetime import date

from app.sources.fred import _parse, recession_start_dates


def test_fred_parse_handles_missing_dot():
    raw = {"observations": [
        {"date": "2026-01-02", "value": "4.10"},
        {"date": "2026-01-03", "value": "."},      # FRED missing marker -> None
        {"date": "2026-01-06", "value": "4.05"},
    ]}
    dates, vals = _parse(raw)
    assert dates == [date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 6)]
    assert vals == [4.10, None, 4.05]


def test_recession_start_dates():
    dates = [date(2026, 1, i) for i in range(1, 8)]
    usrec = [0, 0, 1, 1, 0, 1, 1]   # two runs -> two onsets
    starts = recession_start_dates(dates, usrec)
    assert starts == [date(2026, 1, 3), date(2026, 1, 6)]
