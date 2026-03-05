from __future__ import annotations

import pandas as pd

from ..scoring import clamp
from ..timeseries import iso_date_or_none, last_value_on_or_before, stale_flag
from .base import BaseSentimentOverlay


class JpySentimentOverlay(BaseSentimentOverlay):
    family_name = "jpy"
    signal_names = ("boj_tone", "rate_diff", "risk_sentiment", "cot", "intervention_risk")

    def supports(self, symbol: str) -> bool:
        symbol_u = str(symbol).upper()
        return len(symbol_u) == 6 and symbol_u.endswith("JPY") and symbol_u != "JPYJPY"

    def build(self, symbol: str, as_of: str, macro_row: dict | None = None) -> dict:
        symbol_u = str(symbol).upper()
        signals = {
            "boj_tone": self._boj_tone_signal(as_of=as_of),
            "rate_diff": self._rate_diff_signal(symbol=symbol_u, as_of=as_of),
            "risk_sentiment": self._risk_signal(symbol=symbol_u, as_of=as_of),
            "cot": self._cot_signal(as_of=as_of),
            "intervention_risk": self._intervention_signal(as_of=as_of),
        }
        return self.finalize(
            symbol=symbol_u,
            as_of=as_of,
            macro_row=macro_row,
            signals=signals,
            extra_meta={"family": self.family_name},
        )

    def _boj_tone_signal(self, as_of: str) -> dict:
        cfg = (self.family_cfg().get("boj_tone") or {})
        symbol_id = str(cfg.get("jgb2y_symbol") or ((self.engine.stooq_cfg.get("yields_2y", {}) or {}).get("JPY") or "2yjpy.b"))
        fast_window = int(cfg.get("fast_window", 20))
        slow_window = int(cfg.get("slow_window", 60))
        scale = float(cfg.get("scale", 0.10))
        try:
            series = self.engine._stooq_close_series(symbol_id, None, pd.Timestamp(as_of).date())
        except Exception as exc:
            return self.unavailable_signal("boj_tone", reason="series_error", meta={"symbol": symbol_id, "error": str(exc)})
        fast, fast_dt = self.engine._sma_on_or_before(series, as_of, fast_window)
        slow, slow_dt = self.engine._sma_on_or_before(series, as_of, slow_window)
        if fast is None or slow is None:
            return self.unavailable_signal("boj_tone", reason="insufficient_history", meta={"symbol": symbol_id})
        obs_date = min([d for d in (fast_dt, slow_dt) if d is not None]) if (fast_dt is not None and slow_dt is not None) else (fast_dt or slow_dt)
        jpy_score = clamp((float(fast) - float(slow)) / scale, -1.0, 1.0)
        pair_score = -jpy_score
        return self.signal(
            "boj_tone",
            score=pair_score,
            obs_date=obs_date,
            stale=bool(stale_flag(as_of, obs_date, self.signal_stale_days("boj_tone"))),
            meta={
                "available": True,
                "proxy": "market_implied_jgb_2y_trend",
                "yield_symbol": symbol_id,
                "fast_window": fast_window,
                "slow_window": slow_window,
                "fast_value": float(fast),
                "slow_value": float(slow),
                "jpy_direction_score": float(jpy_score),
            },
        )

    def _rate_diff_signal(self, symbol: str, as_of: str) -> dict:
        base, quote = self.split_pair(symbol)
        pillar = self.engine.pillar_rates(base, quote, as_of)
        if pillar.score is None:
            meta = dict(pillar.meta or {})
            meta["available"] = False
            return self.unavailable_signal("rate_diff", reason=meta.get("reason", "pillar_unavailable"), meta=meta)
        return self.signal(
            "rate_diff",
            score=float(pillar.score),
            obs_date=pillar.obs_date,
            stale=bool(pillar.stale),
            meta={
                "available": True,
                "raw": float(pillar.raw_or_none() or 0.0),
                **dict(pillar.meta or {}),
            },
        )

    def _risk_signal(self, symbol: str, as_of: str) -> dict:
        regime = self.engine._risk_regime(as_of)
        if not regime:
            return self.unavailable_signal("risk_sentiment", reason="missing_regime")
        multipliers = (self.family_cfg().get("risk_sentiment", {}) or {}).get("multipliers", {}) or {}
        score_mag = float(multipliers.get(symbol, 1.0 if symbol in {"AUDJPY", "NZDJPY"} else 0.75))
        obs_date = pd.Timestamp(regime["obs_date"]) if regime.get("obs_date") else None
        return self.signal(
            "risk_sentiment",
            score=(score_mag if bool(regime.get("risk_on")) else -score_mag),
            obs_date=obs_date,
            stale=bool(stale_flag(as_of, obs_date, self.signal_stale_days("risk_sentiment"))),
            meta={
                "available": True,
                "risk_on": bool(regime.get("risk_on")),
                "usd_bid": regime.get("usd_bid"),
                "multiplier": float(score_mag),
                "regime_obs_date": iso_date_or_none(obs_date),
            },
        )

    def _cot_signal(self, as_of: str) -> dict:
        tff_id = self.engine.cftc_cfg.get("tff_futures_only", "gpe5-46if")
        curmap = self.engine.cftc_cfg.get("currency_contract_match", {}) or {}
        return self.cot_signal(
            "cot",
            kind="tff",
            dataset_id=tff_id,
            contract_name=curmap.get("JPY"),
            as_of=as_of,
            direction=-1.0,
            meta={"theme": "jpy_positioning"},
        )

    def _intervention_signal(self, as_of: str) -> dict:
        cfg = (self.family_cfg().get("intervention_risk") or {})
        anchor_symbol = str(cfg.get("anchor_symbol") or "usdjpy")
        high_level = float(cfg.get("high_level", 155.0))
        extreme_level = float(cfg.get("extreme_level", 160.0))
        trend_days = int(cfg.get("trend_days", 63))
        trend_threshold = float(cfg.get("trend_threshold", 0.08))
        try:
            series = self.engine._stooq_close_series(anchor_symbol, None, pd.Timestamp(as_of).date())
        except Exception as exc:
            return self.unavailable_signal("intervention_risk", reason="series_error", meta={"symbol": anchor_symbol, "error": str(exc)})
        last_close, obs_date = last_value_on_or_before(series, as_of)
        trend_return, _, trend_start = self.engine._return_on_or_before(series, as_of, trend_days)
        if last_close is None or obs_date is None:
            return self.unavailable_signal("intervention_risk", reason="insufficient_history", meta={"symbol": anchor_symbol})

        score = 0.0
        if float(last_close) >= extreme_level:
            score = -1.0
        elif float(last_close) >= high_level:
            score = -0.4 - 0.6 * ((float(last_close) - high_level) / max(extreme_level - high_level, 1e-9))
        elif trend_return is not None and float(trend_return) >= trend_threshold:
            score = -0.35

        return self.signal(
            "intervention_risk",
            score=score,
            obs_date=obs_date,
            stale=bool(stale_flag(as_of, obs_date, self.signal_stale_days("intervention_risk"))),
            meta={
                "available": True,
                "anchor_symbol": anchor_symbol,
                "anchor_close": float(last_close),
                "high_level": float(high_level),
                "extreme_level": float(extreme_level),
                "trend_days": int(trend_days),
                "trend_return": None if trend_return is None else float(trend_return),
                "trend_start_date": iso_date_or_none(trend_start),
                "logic": "bearish_pair_when_usdjpy_level_or_trend_implies_intervention_risk",
            },
        )
