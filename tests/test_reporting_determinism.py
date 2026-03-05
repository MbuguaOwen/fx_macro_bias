import pandas as pd

from fxbias.reporting import build_dashboard_payload, stable_payload_json
from fxbias.reporting.templates import render_dashboard_html


def _panel_rows():
    return [
        {"as_of": "2026-02-20", "pair": "USDJPY", "rates": -0.2, "growth": -0.1, "risk": 0.1, "positioning": 0.0, "total_score": -0.2, "final_bias": "BEAR_BASE", "conviction_abs": 0.2},
        {"as_of": "2026-02-13", "pair": "EURUSD", "rates": 0.1, "growth": 0.2, "risk": 0.0, "positioning": 0.1, "total_score": 0.3, "final_bias": "BULL_BASE", "conviction_abs": 0.3},
        {"as_of": "2026-02-20", "pair": "EURUSD", "rates": 0.2, "growth": 0.1, "risk": 0.0, "positioning": 0.0, "total_score": 0.3, "final_bias": "BULL_BASE", "conviction_abs": 0.3},
        {"as_of": "2026-02-13", "pair": "USDJPY", "rates": -0.1, "growth": -0.1, "risk": 0.0, "positioning": 0.0, "total_score": -0.2, "final_bias": "BEAR_BASE", "conviction_abs": 0.2},
    ]


def test_payload_order_is_deterministic():
    panel_a = pd.DataFrame(_panel_rows())
    panel_b = pd.DataFrame(list(reversed(_panel_rows())))
    weeks = ["2026-02-20", "2026-02-13"]
    meta = {"2026-02-20": {"as_of": "2026-02-20"}, "2026-02-13": {"as_of": "2026-02-13"}}

    payload_a = build_dashboard_payload(panel=panel_a, weeks=weeks, meta_by_week=meta, generated_utc="2026-03-05 00:00 UTC")
    payload_b = build_dashboard_payload(
        panel=panel_b,
        weeks=list(reversed(weeks)),
        meta_by_week=dict(reversed(list(meta.items()))),
        generated_utc="2026-03-05 00:00 UTC",
    )

    assert payload_a["weeks"] == ["2026-02-13", "2026-02-20"]
    assert payload_a["pairs"] == ["EURUSD", "USDJPY"]
    assert stable_payload_json(payload_a) == stable_payload_json(payload_b)


def test_dashboard_html_renders_date_toggle_controls():
    panel = pd.DataFrame(_panel_rows())
    weeks = ["2026-02-20", "2026-02-13"]
    meta = {"2026-02-20": {"as_of": "2026-02-20"}, "2026-02-13": {"as_of": "2026-02-13"}}
    payload = build_dashboard_payload(panel=panel, weeks=weeks, meta_by_week=meta, generated_utc="2026-03-05 00:00 UTC")

    html = render_dashboard_html(payload=payload, latest_rows_html="")

    assert 'id="overview-week"' in html
    assert 'id="tbl-overview-leaderboard"' in html
    assert 'id="sentiment-week-title"' in html
