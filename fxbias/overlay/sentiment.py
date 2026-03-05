from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd

from .jpy import JpySentimentOverlay
from .metals import MetalsSentimentOverlay
from .oil import OilSentimentOverlay


def _panel_lookup(panel: Optional[pd.DataFrame]) -> dict:
    if panel is None or panel.empty:
        return {}
    out = {}
    for row in panel.to_dict(orient="records"):
        pair = str(row.get("pair") or row.get("symbol") or "").upper()
        as_of = str(row.get("as_of") or "")
        if pair and as_of:
            out[f"{pair}|{as_of}"] = row
    return out


def build_sentiment_overlay(
    *,
    engine,
    pairs: Iterable[str],
    asofs: Iterable[str],
    panel: Optional[pd.DataFrame],
    requested: bool,
) -> dict:
    sentiment_cfg = dict(engine.cfg.get("sentiment_overlay", {}) or {})
    pairs_sorted = sorted({str(p).upper() for p in pairs})
    asofs_sorted = sorted({str(a) for a in asofs})
    payload = {
        "requested": bool(requested),
        "entries": [],
        "error": None,
        "request": {
            "pairs": pairs_sorted,
            "asofs": asofs_sorted,
            "affects_core_score": bool(sentiment_cfg.get("affects_core_score", False)),
            "show_in_report": bool(sentiment_cfg.get("show_in_report", True)),
        },
        "affects_core_score": bool(sentiment_cfg.get("affects_core_score", False)),
        "show_in_report": bool(sentiment_cfg.get("show_in_report", True)),
    }
    if not requested:
        return payload

    builders = [
        MetalsSentimentOverlay(engine=engine),
        JpySentimentOverlay(engine=engine),
        OilSentimentOverlay(engine=engine),
    ]
    row_lookup = _panel_lookup(panel)
    entries = []
    for as_of in asofs_sorted:
        for symbol in pairs_sorted:
            builder = next((item for item in builders if item.supports(symbol)), None)
            if builder is None:
                continue
            macro_row = row_lookup.get(f"{symbol}|{as_of}")
            entries.append(builder.safe_build(symbol=symbol, as_of=as_of, macro_row=macro_row))

    payload["entries"] = sorted(entries, key=lambda x: (str(x.get("as_of") or ""), str(x.get("symbol") or "")))
    return payload
