from __future__ import annotations

from typing import Dict, Optional, Tuple


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def bias_from_score(score: float, bull_bear_threshold: float = 0.20) -> str:
    if score >= bull_bear_threshold:
        return "BULL_BASE"
    if score <= -bull_bear_threshold:
        return "BEAR_BASE"
    return "NEUTRAL"


def load_conviction_cfg(cfg: dict) -> dict:
    c = dict(cfg or {})
    c.setdefault("neutral_threshold", 0.15)
    c.setdefault(
        "bands",
        {
            "weak": 0.20,
            "moderate": 0.45,
            "strong": 0.70,
            "extreme": 1.01,
        },
    )
    return c


def conviction_from_score(score: float, cfg: Optional[dict] = None) -> str:
    x = abs(float(score))
    c = load_conviction_cfg(cfg)
    neutral_th = float(c.get("neutral_threshold", 0.15))
    bands = c.get("bands", {})
    weak = float(bands.get("weak", 0.20))
    moderate = float(bands.get("moderate", 0.45))
    strong = float(bands.get("strong", 0.70))
    extreme = float(bands.get("extreme", 1.01))

    if x < neutral_th:
        return "NONE"
    if x < weak:
        return "WEAK"
    if x < moderate:
        return "MODERATE"
    if x < strong:
        return "STRONG"
    if x < extreme:
        return "EXTREME"
    return "EXTREME"

