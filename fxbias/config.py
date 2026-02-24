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
    return cfg
