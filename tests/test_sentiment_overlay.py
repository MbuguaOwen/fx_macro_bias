import pandas as pd

from fxbias.overlay.utils import (
    agreement_with_macro,
    finalize_sentiment_result,
    make_signal,
    make_unavailable_signal,
    sentiment_bias_from_score,
    stable_overlay_json,
)
from fxbias.reporting import build_dashboard_payload
from fxbias.reporting.dashboard import _merge_sentiment_panel


def _signal(score, obs_date="2026-03-13", stale=False):
    return make_signal(
        score=score,
        obs_date=obs_date,
        stale=stale,
        threshold=0.20,
        meta={"available": True},
    )


def test_sentiment_score_thresholding():
    assert sentiment_bias_from_score(0.19, threshold=0.20) == "NEUTRAL"
    assert sentiment_bias_from_score(0.20, threshold=0.20) == "BULLISH"
    assert sentiment_bias_from_score(-0.21, threshold=0.20) == "BEARISH"


def test_agreement_with_macro_logic():
    assert agreement_with_macro("BULL_BASE", "BULLISH") is True
    assert agreement_with_macro("BEAR_BASE", "BULLISH") is False
    assert agreement_with_macro("NEUTRAL", "BULLISH") is None
    assert agreement_with_macro("BULL_BASE", "NEUTRAL") is None


def test_missing_sources_degrade_gracefully_and_stably():
    result_a = finalize_sentiment_result(
        symbol="XAUUSD",
        as_of="2026-03-14",
        macro_bias="BULL_BASE",
        signals={
            "vix": _signal(0.6),
            "etf_flows": make_unavailable_signal("source_unavailable", meta={"source": "placeholder"}),
            "cot": _signal(0.4),
        },
        weights={"cot": 0.3, "etf_flows": 0.2, "vix": 0.5},
        bias_threshold=0.20,
        conviction_cfg=None,
    )
    result_b = finalize_sentiment_result(
        symbol="XAUUSD",
        as_of="2026-03-14",
        macro_bias="BULL_BASE",
        signals={
            "cot": _signal(0.4),
            "vix": _signal(0.6),
            "etf_flows": make_unavailable_signal("source_unavailable", meta={"source": "placeholder"}),
        },
        weights={"vix": 0.5, "etf_flows": 0.2, "cot": 0.3},
        bias_threshold=0.20,
        conviction_cfg=None,
    )

    assert round(float(result_a["sentiment_score"]), 6) == 0.525
    assert result_a["sentiment_bias"] == "BULLISH"
    assert result_a["agreement_with_macro"] is True
    assert result_a["signals"]["etf_flows"]["meta"]["available"] is False
    assert "unavailable: etf_flows" in result_a["headline_summary"]
    assert stable_overlay_json(result_a) == stable_overlay_json(result_b)


def test_merge_sentiment_panel_preserves_pair_and_date_sorting():
    panel = pd.DataFrame(
        [
            {"as_of": "2026-03-14", "pair": "USDJPY", "total_score": -0.2, "final_bias": "BEAR_BASE"},
            {"as_of": "2026-03-07", "pair": "XAUUSD", "total_score": 0.4, "final_bias": "BULL_BASE"},
            {"as_of": "2026-03-07", "pair": "USDJPY", "total_score": -0.1, "final_bias": "BEAR_BASE"},
        ]
    )
    overlay = {
        "requested": True,
        "entries": [
            {
                "symbol": "USDJPY",
                "as_of": "2026-03-14",
                "overlay_type": "sentiment",
                "sentiment_bias": "BEARISH",
                "sentiment_score": -0.5,
                "sentiment_conviction": "STRONG",
                "agreement_with_macro": True,
                "signals": {},
                "headline_summary": "USDJPY sentiment is BEARISH.",
                "sentiment_stale": False,
            },
            {
                "symbol": "XAUUSD",
                "as_of": "2026-03-07",
                "overlay_type": "sentiment",
                "sentiment_bias": "BULLISH",
                "sentiment_score": 0.3,
                "sentiment_conviction": "MODERATE",
                "agreement_with_macro": True,
                "signals": {},
                "headline_summary": "XAUUSD sentiment is BULLISH.",
                "sentiment_stale": True,
            },
        ],
    }

    merged = _merge_sentiment_panel(panel, overlay)

    assert merged[["as_of", "pair"]].to_dict(orient="records") == [
        {"as_of": "2026-03-07", "pair": "USDJPY"},
        {"as_of": "2026-03-07", "pair": "XAUUSD"},
        {"as_of": "2026-03-14", "pair": "USDJPY"},
    ]
    assert list(merged["sentiment_bias"]) == [None, "BULLISH", "BEARISH"]
    assert list(merged["sentiment_stale"]) == [None, True, False]


def test_dashboard_payload_sentiment_is_sorted_and_json_stable():
    panel = pd.DataFrame(
        [
            {"as_of": "2026-03-14", "pair": "USDJPY", "total_score": -0.2, "final_bias": "BEAR_BASE", "conviction_abs": 0.2},
            {"as_of": "2026-03-07", "pair": "XAUUSD", "total_score": 0.4, "final_bias": "BULL_BASE", "conviction_abs": 0.4},
        ]
    )
    weeks = ["2026-03-14", "2026-03-07"]
    meta = {"2026-03-14": {"as_of": "2026-03-14"}, "2026-03-07": {"as_of": "2026-03-07"}}
    sentiment_a = {
        "requested": True,
        "entries": [
            {
                "symbol": "USDJPY",
                "as_of": "2026-03-14",
                "overlay_type": "sentiment",
                "sentiment_bias": "BEARISH",
                "sentiment_score": -0.5,
                "sentiment_conviction": "STRONG",
                "agreement_with_macro": True,
                "signals": {"cot": _signal(-0.5)},
                "headline_summary": "USDJPY sentiment is BEARISH.",
                "sentiment_stale": False,
            },
            {
                "symbol": "XAUUSD",
                "as_of": "2026-03-07",
                "overlay_type": "sentiment",
                "sentiment_bias": "BULLISH",
                "sentiment_score": 0.3,
                "sentiment_conviction": "MODERATE",
                "agreement_with_macro": True,
                "signals": {"cot": _signal(0.3)},
                "headline_summary": "XAUUSD sentiment is BULLISH.",
                "sentiment_stale": True,
            },
        ],
    }
    sentiment_b = {
        "requested": True,
        "entries": list(reversed(sentiment_a["entries"])),
    }

    merged_a = _merge_sentiment_panel(panel, sentiment_a)
    merged_b = _merge_sentiment_panel(panel, sentiment_b)
    payload_a = build_dashboard_payload(
        panel=merged_a,
        weeks=weeks,
        meta_by_week=meta,
        sentiment_overlay=sentiment_a,
        generated_utc="2026-03-15 00:00 UTC",
    )
    payload_b = build_dashboard_payload(
        panel=merged_b,
        weeks=list(reversed(weeks)),
        meta_by_week=dict(reversed(list(meta.items()))),
        sentiment_overlay=sentiment_b,
        generated_utc="2026-03-15 00:00 UTC",
    )

    assert payload_a["weeks"] == ["2026-03-07", "2026-03-14"]
    assert [row["symbol"] for row in payload_a["sentiment_overlay"]["entries"]] == ["XAUUSD", "USDJPY"]
    assert payload_a["sentiment_overlay"]["summary"]["latest_week"] == "2026-03-14"
    assert stable_overlay_json(payload_a["sentiment_overlay"]) == stable_overlay_json(payload_b["sentiment_overlay"])
