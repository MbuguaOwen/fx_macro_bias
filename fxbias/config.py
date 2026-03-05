from __future__ import annotations

from pathlib import Path

import yaml

def load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p.resolve()}")
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    # defaults
    cfg.setdefault("cache_dir", ".cache")
    cfg.setdefault("weights", {"rates":0.45,"growth":0.20,"risk":0.15,"positioning":0.20})
    cfg.setdefault("thresholds", {"bias_threshold": 0.20})
    cfg.setdefault("conviction", {
        "neutral_threshold": 0.15,
        "bands": {"weak": 0.20, "moderate": 0.45, "strong": 0.70, "extreme": 1.01},
    })
    cfg.setdefault("staleness", {
        "days": {"rates": 5, "risk": 5, "positioning": 10, "growth": 45, "cesi": 7, "pmi": 45},
    })
    cfg.setdefault("fred", {"risk": {"vix": "VIXCLS", "dxy": "DTWEXBGS"}})
    cfg.setdefault("growth", {"mode": "proxy"})
    cfg.setdefault("tradingeconomics", {"api_key_env": "TRADINGECONOMICS_API_KEY"})
    cftc = cfg.setdefault("cftc", {})
    cftc.setdefault("positioning", {"usd_zero_baseline": True})
    market_overlay = cfg.setdefault("market_overlay", {})
    market_overlay.setdefault("enabled", False)
    market_overlay.setdefault("provider", "investing")
    market_overlay.setdefault("url_env", "FXBIAS_OPTIONS_URL")
    market_overlay.setdefault("default_symbol", "XAUUSD")
    market_overlay.setdefault("default_tenor", "1M")
    sentiment_overlay = cfg.setdefault("sentiment_overlay", {})
    sentiment_overlay.setdefault("enabled", False)
    sentiment_overlay.setdefault("affects_core_score", False)
    sentiment_overlay.setdefault("show_in_report", True)
    sentiment_overlay.setdefault("manual_signals", {})
    sentiment_thresholds = sentiment_overlay.setdefault("thresholds", {})
    sentiment_thresholds.setdefault("bias_threshold", 0.20)
    sentiment_staleness = sentiment_overlay.setdefault("staleness", {})
    sentiment_staleness.setdefault("default_days", 10)
    sentiment_staleness.setdefault(
        "signals",
        {
            "cot": 10,
            "real_yields": 5,
            "dxy": 5,
            "etf_flows": 14,
            "vix": 5,
            "gold_silver_ratio": 5,
            "boj_tone": 5,
            "rate_diff": 5,
            "risk_sentiment": 5,
            "intervention_risk": 5,
            "eia_inventories": 10,
            "opec_stance": 30,
            "usd": 5,
            "baker_hughes_rig_count": 14,
        },
    )
    sentiment_overlay.setdefault(
        "weights",
        {
            "metals": {
                "cot": 0.30,
                "real_yields": 0.25,
                "dxy": 0.20,
                "etf_flows": 0.15,
                "vix": 0.10,
                "gold_silver_ratio": 0.0,
            },
            "jpy": {
                "boj_tone": 0.25,
                "rate_diff": 0.25,
                "risk_sentiment": 0.20,
                "cot": 0.20,
                "intervention_risk": 0.10,
            },
            "oil": {
                "eia_inventories": 0.25,
                "opec_stance": 0.20,
                "cot": 0.20,
                "usd": 0.15,
                "risk_sentiment": 0.10,
                "baker_hughes_rig_count": 0.10,
            },
        },
    )
    sentiment_overlay.setdefault(
        "families",
        {
            "metals": {
                "instruments": ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"],
                "real_yields": {"series_id": "DFII10", "trend_window": 20, "scale": 0.35},
                "dxy": {"series_id": "DTWEXBGS", "trend_window": 50, "scale": 2.5},
                "vix": {"series_id": "VIXCLS", "trend_window": 20, "scale": 4.0, "silver_sensitivity": 0.5},
                "ratio": {"gold_symbol": "xauusd", "silver_symbol": "xagusd", "trend_window": 20, "scale": 2.0},
            },
            "jpy": {
                "instruments": ["USDJPY", "GBPJPY", "EURJPY", "AUDJPY", "NZDJPY"],
                "boj_tone": {"jgb2y_symbol": "2yjpy.b", "fast_window": 20, "slow_window": 60, "scale": 0.10},
                "risk_sentiment": {
                    "multipliers": {
                        "USDJPY": 0.75,
                        "EURJPY": 0.75,
                        "GBPJPY": 0.85,
                        "AUDJPY": 1.00,
                        "NZDJPY": 1.00,
                    }
                },
                "intervention_risk": {"anchor_symbol": "usdjpy", "high_level": 155.0, "extreme_level": 160.0, "trend_days": 63, "trend_threshold": 0.08},
            },
            "oil": {
                "instruments": ["USOIL", "WTI"],
                "usd": {"series_id": "DTWEXBGS", "trend_window": 50, "scale": 2.5},
                "cot": {"dataset_id": cftc.get("disagg_futures_only", "72hh-3qpy"), "contract_name": None},
                "baker_hughes_rig_count": {"series_id": None, "trend_window": 26, "scale": 40.0},
            },
        },
    )
    report_notes = cfg.setdefault("report_notes", {})
    report_notes.setdefault("instrument_notes", {})
    return cfg
