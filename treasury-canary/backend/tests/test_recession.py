from app.metrics.recession import near_term_forward_spread, recession_probability


def test_probit_reproduces_ny_fed_table():
    # ~30% at spread 0, ~50% near -0.82, single digits when strongly positive.
    assert abs(recession_probability(0.0) - 29.7) < 1.0
    assert abs(recession_probability(-0.82) - 50.0) < 1.5
    assert recession_probability(1.21) < 12.0
    assert recession_probability(2.5) < 5.0


def test_probit_monotonic_decreasing_in_spread():
    probs = [recession_probability(s) for s in (-1.5, -0.5, 0.0, 0.5, 1.5)]
    assert probs == sorted(probs, reverse=True)


def test_probit_none():
    assert recession_probability(None) is None


def test_near_term_forward_spread():
    assert near_term_forward_spread(3.5, 4.0) == -0.5   # market pricing cuts
    assert near_term_forward_spread(None, 4.0) is None
