from pathlib import Path

from fxbias.providers.investing_options import compute_skew_metrics, parse_options_surface_html


def test_parse_and_compute_skew_metrics_from_fixture():
    fixture = Path("tests/fixtures/investing_options_sample.html").read_text(encoding="utf-8")
    url = "https://www.investing.com/currencies/xau-usd-options"
    df = parse_options_surface_html(url=url, html=fixture, tenor="1M")

    assert not df.empty
    assert list(df.columns[:6]) == ["put_delta", "put_price", "strike", "call_price", "call_delta", "imp_vol"]
    assert df["symbol"].iloc[0] == "XAUUSD"
    assert float(df["put_delta"].max()) <= 0.0
    assert float(df["call_delta"].min()) >= 0.0

    m = compute_skew_metrics(df)
    assert m["label"] == "BULLISH"
    assert round(float(m["approx_atm_iv"]), 2) == 16.40
    assert round(float(m["iv_10_put"]), 2) == 15.80
    assert round(float(m["iv_10_call"]), 2) == 16.80
    assert round(float(m["rr10"]), 2) == 1.00
    assert round(float(m["rr25"]), 2) == 0.60

