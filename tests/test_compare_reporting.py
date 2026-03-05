import pandas as pd

from fxbias.reporting import build_dashboard_payload
from fxbias.reporting.compare import build_compare_table, classify_flip, persistence_streak


def _panel_fixture() -> pd.DataFrame:
    rows = [
        {"as_of": "2026-02-06", "pair": "EURUSD", "rates": 0.20, "growth": 0.10, "risk": 0.05, "positioning": 0.05, "total_score": 0.40, "final_bias": "BULL_BASE"},
        {"as_of": "2026-02-13", "pair": "EURUSD", "rates": 0.25, "growth": 0.15, "risk": 0.05, "positioning": 0.05, "total_score": 0.50, "final_bias": "BULL_BASE"},
        {"as_of": "2026-02-20", "pair": "EURUSD", "rates": -0.15, "growth": -0.05, "risk": -0.05, "positioning": -0.05, "total_score": -0.30, "final_bias": "BEAR_BASE"},
        {"as_of": "2026-02-06", "pair": "USDJPY", "rates": -0.20, "growth": -0.15, "risk": -0.05, "positioning": 0.00, "total_score": -0.40, "final_bias": "BEAR_BASE"},
        {"as_of": "2026-02-13", "pair": "USDJPY", "rates": -0.25, "growth": -0.20, "risk": -0.05, "positioning": 0.00, "total_score": -0.50, "final_bias": "BEAR_BASE"},
        {"as_of": "2026-02-20", "pair": "USDJPY", "rates": -0.10, "growth": -0.10, "risk": 0.00, "positioning": 0.00, "total_score": -0.20, "final_bias": "BEAR_BASE"},
    ]
    return pd.DataFrame(rows)


def test_classify_flip():
    assert classify_flip("BULL_BASE", "BEAR_BASE") == "BULL->BEAR"
    assert classify_flip("BEAR_BASE", "BULL_BASE") == "BEAR->BULL"
    assert classify_flip("BEAR_BASE", "NEUTRAL") == "->NEUTRAL"
    assert classify_flip("NEUTRAL", "NEUTRAL") == ""


def test_compare_and_persistence():
    panel = _panel_fixture()
    streaks = persistence_streak(panel, as_of_b="2026-02-20")
    assert streaks["EURUSD"] == 1
    assert streaks["USDJPY"] == 3

    cmp = build_compare_table(panel, as_of_a="2026-02-13", as_of_b="2026-02-20")
    eur = cmp[cmp["pair"] == "EURUSD"].iloc[0]
    usd = cmp[cmp["pair"] == "USDJPY"].iloc[0]

    assert eur["flip"] == "BULL->BEAR"
    assert round(float(eur["delta_total_score"]), 3) == -0.800
    assert int(eur["persistence_b"]) == 1

    assert usd["flip"] == ""
    assert round(float(usd["delta_total_score"]), 3) == 0.300
    assert int(usd["persistence_b"]) == 3


def test_dashboard_compare_supports_reversed_and_same_day_date_order():
    panel = _panel_fixture()
    weeks = ["2026-02-06", "2026-02-13", "2026-02-20"]
    meta = {week: {"as_of": week} for week in weeks}

    payload = build_dashboard_payload(
        panel=panel,
        weeks=weeks,
        meta_by_week=meta,
        compare_dates=("2026-02-20", "2026-02-13"),
    )

    reversed_rows = payload["compare"]["by_key"]["2026-02-20|2026-02-13"]
    same_day_rows = payload["compare"]["by_key"]["2026-02-20|2026-02-20"]
    eur_reversed = next(row for row in reversed_rows if row["pair"] == "EURUSD")

    assert payload["compare"]["default_a"] == "2026-02-20"
    assert payload["compare"]["default_b"] == "2026-02-13"
    assert round(float(eur_reversed["delta_total_score"]), 3) == 0.800
    assert all(round(float(row["delta_total_score"]), 3) == 0.0 for row in same_day_rows)
