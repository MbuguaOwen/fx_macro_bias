from __future__ import annotations

import json
from typing import Dict, Iterable, Optional

from ..scoring import clamp, conviction_from_score
from ..timeseries import iso_date_or_none


def stable_overlay_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def sort_dict(d: Optional[dict]) -> dict:
    return {k: d[k] for k in sorted((d or {}).keys())}


def sentiment_bias_from_score(score: Optional[float], threshold: float = 0.20) -> str:
    x = 0.0 if score is None else float(score)
    if x >= float(threshold):
        return "BULLISH"
    if x <= -float(threshold):
        return "BEARISH"
    return "NEUTRAL"


def sentiment_conviction_from_score(score: Optional[float], conviction_cfg: Optional[dict] = None) -> str:
    tier = conviction_from_score(0.0 if score is None else float(score), cfg=conviction_cfg)
    return "WEAK" if tier == "NONE" else str(tier)


def agreement_with_macro(macro_bias: Optional[object], sentiment_bias: Optional[object]) -> Optional[bool]:
    mb = str(macro_bias or "")
    sb = str(sentiment_bias or "")
    if mb not in {"BULL_BASE", "BEAR_BASE"}:
        return None
    if sb not in {"BULLISH", "BEARISH"}:
        return None
    return bool((mb == "BULL_BASE" and sb == "BULLISH") or (mb == "BEAR_BASE" and sb == "BEARISH"))


def signal_score_from_bias(bias: Optional[str]) -> float:
    b = str(bias or "").upper()
    if b == "BULLISH":
        return 1.0
    if b == "BEARISH":
        return -1.0
    return 0.0


def make_signal(
    *,
    score: Optional[float],
    obs_date: Optional[object],
    stale: bool,
    threshold: float,
    meta: Optional[dict] = None,
) -> dict:
    score_f = clamp(0.0 if score is None else float(score), -1.0, 1.0)
    return {
        "bias": sentiment_bias_from_score(score_f, threshold=threshold),
        "score": float(score_f),
        "obs_date": iso_date_or_none(obs_date),
        "stale": bool(stale),
        "meta": sort_dict(meta),
    }


def make_unavailable_signal(reason: str, *, stale: bool = True, meta: Optional[dict] = None) -> dict:
    merged = dict(meta or {})
    merged["available"] = False
    merged["reason"] = str(reason)
    return {
        "bias": "NEUTRAL",
        "score": 0.0,
        "obs_date": None,
        "stale": bool(stale),
        "meta": sort_dict(merged),
    }


def normalize_signal_map(signals: Dict[str, dict]) -> Dict[str, dict]:
    return {name: signals[name] for name in sorted(signals.keys())}


def contributing_signal_names(signals: Dict[str, dict], weights: Dict[str, float]) -> Iterable[str]:
    for name in sorted(weights.keys()):
        signal = signals.get(name) or {}
        meta = signal.get("meta") or {}
        if not bool(meta.get("available", True)):
            continue
        yield name


def summarize_sentiment(
    *,
    symbol: str,
    sentiment_bias: str,
    sentiment_score: float,
    sentiment_conviction: str,
    agreement: Optional[bool],
    signals: Dict[str, dict],
) -> str:
    available = []
    missing = []
    stale = []
    for name in sorted(signals.keys()):
        signal = signals[name] or {}
        meta = signal.get("meta") or {}
        if bool(meta.get("available", True)):
            contrib = float(meta.get("contribution", 0.0))
            available.append((abs(contrib), name, signal.get("bias"), contrib))
            if bool(signal.get("stale")):
                stale.append(name)
        else:
            missing.append(name)

    drivers = ", ".join(
        f"{name} {bias} ({contrib:+.2f})"
        for _, name, bias, contrib in sorted(available, key=lambda x: (-x[0], x[1]))[:3]
    )
    agreement_text = "aligned with macro" if agreement is True else ("against macro" if agreement is False else "macro alignment inconclusive")

    parts = [
        f"{symbol} sentiment is {sentiment_bias} ({sentiment_conviction}, {float(sentiment_score):+.2f})",
        agreement_text,
    ]
    if drivers:
        parts.append(f"main drivers: {drivers}")
    if stale:
        parts.append(f"stale: {', '.join(sorted(stale))}")
    if missing:
        parts.append(f"unavailable: {', '.join(sorted(missing))}")
    return "; ".join(parts) + "."


def finalize_sentiment_result(
    *,
    symbol: str,
    as_of: str,
    macro_bias: Optional[object],
    signals: Dict[str, dict],
    weights: Dict[str, float],
    bias_threshold: float,
    conviction_cfg: Optional[dict] = None,
    overlay_type: str = "sentiment",
    extra_meta: Optional[dict] = None,
) -> dict:
    normalized_signals = normalize_signal_map(signals)
    normalized_weights = {k: float(weights[k]) for k in sorted(weights.keys())}

    active = []
    total_weight = 0.0
    for name in contributing_signal_names(normalized_signals, normalized_weights):
        w = float(normalized_weights.get(name, 0.0))
        if w <= 0:
            continue
        total_weight += w
        active.append((name, w))

    total_score = 0.0
    for name, weight in active:
        total_score += float((normalized_signals[name] or {}).get("score") or 0.0) * weight
    sentiment_score = 0.0 if total_weight <= 0 else clamp(total_score / total_weight, -1.0, 1.0)

    enriched_signals = {}
    any_stale = False
    for name in sorted(normalized_signals.keys()):
        signal = dict(normalized_signals[name] or {})
        meta = dict(signal.get("meta") or {})
        available = bool(meta.get("available", True))
        weight = float(normalized_weights.get(name, 0.0))
        contribution = 0.0
        if available and total_weight > 0 and weight > 0:
            contribution = float(signal.get("score") or 0.0) * (weight / total_weight)
            any_stale = any_stale or bool(signal.get("stale"))
        elif not available:
            meta["available"] = False
        meta["weight"] = weight
        meta["contribution"] = float(contribution)
        signal["meta"] = sort_dict(meta)
        enriched_signals[name] = signal

    if total_weight <= 0:
        any_stale = True

    bias = sentiment_bias_from_score(sentiment_score, threshold=bias_threshold)
    conviction = sentiment_conviction_from_score(sentiment_score, conviction_cfg=conviction_cfg)
    agreement = agreement_with_macro(macro_bias, bias)

    result = {
        "symbol": str(symbol).upper(),
        "as_of": str(as_of),
        "overlay_type": overlay_type,
        "sentiment_bias": bias,
        "sentiment_score": float(sentiment_score),
        "sentiment_conviction": conviction,
        "agreement_with_macro": agreement,
        "signals": enriched_signals,
        "headline_summary": summarize_sentiment(
            symbol=str(symbol).upper(),
            sentiment_bias=bias,
            sentiment_score=sentiment_score,
            sentiment_conviction=conviction,
            agreement=agreement,
            signals=enriched_signals,
        ),
        "sentiment_stale": bool(any_stale),
    }
    if extra_meta:
        result["meta"] = sort_dict(extra_meta)
    return result


def cleaned_signal_table(signals: Dict[str, dict]) -> list[dict]:
    rows = []
    for name in sorted(signals.keys()):
        signal = signals[name] or {}
        meta = dict(signal.get("meta") or {})
        rows.append(
            {
                "signal_name": name,
                "bias": str(signal.get("bias") or "NEUTRAL"),
                "score": float(signal.get("score") or 0.0),
                "obs_date": signal.get("obs_date"),
                "stale": bool(signal.get("stale")),
                "available": bool(meta.get("available", True)),
                "weight": float(meta.get("weight", 0.0)),
                "contribution": float(meta.get("contribution", 0.0)),
                "meta": sort_dict(meta),
            }
        )
    return rows


def rows_for_dashboard(entries: list[dict]) -> list[dict]:
    out = []
    for entry in sorted(entries, key=lambda x: (str(x.get("as_of") or ""), str(x.get("symbol") or ""))):
        row = dict(entry or {})
        row["signals_table"] = cleaned_signal_table(row.get("signals") or {})
        out.append(row)
    return out


def overlay_summary(entries: list[dict], latest_week: Optional[str]) -> dict:
    rows = [dict(item or {}) for item in sorted(entries, key=lambda x: (str(x.get("as_of") or ""), str(x.get("symbol") or "")))]
    latest_rows = [r for r in rows if str(r.get("as_of") or "") == str(latest_week or "")]
    bias_counts = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
    agreement_count = 0
    disagreement_count = 0
    unknown_agreement = 0
    stale_count = 0
    for row in latest_rows:
        bias_counts[str(row.get("sentiment_bias") or "NEUTRAL")] += 1
        agree = row.get("agreement_with_macro")
        if agree is True:
            agreement_count += 1
        elif agree is False:
            disagreement_count += 1
        else:
            unknown_agreement += 1
        if bool(row.get("sentiment_stale")):
            stale_count += 1

    comparable = agreement_count + disagreement_count
    agreement_rate = None if comparable <= 0 else float(agreement_count / comparable)

    return {
        "latest_week": latest_week,
        "coverage_count": int(len(latest_rows)),
        "agreement_count": int(agreement_count),
        "disagreement_count": int(disagreement_count),
        "unknown_agreement_count": int(unknown_agreement),
        "stale_count": int(stale_count),
        "agreement_rate": agreement_rate,
        "bias_counts": bias_counts,
        "latest_rows": rows_for_dashboard(latest_rows),
    }
