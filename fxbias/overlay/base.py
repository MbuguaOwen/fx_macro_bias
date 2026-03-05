from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from ..engine import MacroBiasEngine, _split_pair
from ..scoring import clamp
from ..timeseries import iso_date_or_none, last_value_on_or_before, stale_flag
from .utils import finalize_sentiment_result, make_signal, make_unavailable_signal, signal_score_from_bias


@dataclass
class BaseSentimentOverlay:
    engine: MacroBiasEngine

    family_name: str = field(default="", init=False)
    signal_names: tuple[str, ...] = field(default_factory=tuple, init=False)

    @property
    def cfg(self) -> dict:
        return self.engine.cfg

    @property
    def sentiment_cfg(self) -> dict:
        return dict(self.cfg.get("sentiment_overlay", {}) or {})

    def family_cfg(self) -> dict:
        families = self.sentiment_cfg.get("families", {}) or {}
        return dict(families.get(self.family_name, {}) or {})

    def family_weights(self) -> dict:
        weights = self.sentiment_cfg.get("weights", {}) or {}
        return dict(weights.get(self.family_name, {}) or {})

    def bias_threshold(self) -> float:
        thresholds = self.sentiment_cfg.get("thresholds", {}) or {}
        return float(thresholds.get("bias_threshold", 0.20))

    def signal_stale_days(self, signal_name: str) -> Optional[int]:
        staleness = self.sentiment_cfg.get("staleness", {}) or {}
        signals = staleness.get("signals", {}) or {}
        family = staleness.get("families", {}) or {}
        family_signals = (family.get(self.family_name, {}) or {}).get("signals", {}) or {}
        raw = family_signals.get(signal_name, signals.get(signal_name, staleness.get("default_days")))
        return None if raw is None else int(raw)

    def supports(self, symbol: str) -> bool:
        raise NotImplementedError

    def build(self, symbol: str, as_of: str, macro_row: Optional[dict] = None) -> dict:
        raise NotImplementedError

    def safe_build(self, symbol: str, as_of: str, macro_row: Optional[dict] = None) -> dict:
        try:
            return self.build(symbol=symbol, as_of=as_of, macro_row=macro_row)
        except Exception as exc:
            signals = {
                name: self.unavailable_signal(name, reason=f"builder_error:{type(exc).__name__}", meta={"error": str(exc)})
                for name in self.signal_names
            }
            return self.finalize(
                symbol=symbol,
                as_of=as_of,
                macro_row=macro_row,
                signals=signals,
                extra_meta={"family": self.family_name, "error": str(exc)},
            )

    def finalize(self, *, symbol: str, as_of: str, macro_row: Optional[dict], signals: dict, extra_meta: Optional[dict] = None) -> dict:
        macro_bias = None if not macro_row else (macro_row.get("final_bias") or macro_row.get("bias"))
        return finalize_sentiment_result(
            symbol=symbol,
            as_of=as_of,
            macro_bias=macro_bias,
            signals=signals,
            weights=self.family_weights(),
            bias_threshold=self.bias_threshold(),
            conviction_cfg=self.engine.conviction_cfg,
            extra_meta=extra_meta,
        )

    def split_pair(self, symbol: str) -> tuple[str, str]:
        return _split_pair(symbol)

    def manual_signal(self, symbol: str, signal_name: str) -> Optional[dict]:
        manual = self.sentiment_cfg.get("manual_signals", {}) or {}
        candidates = [
            (((manual.get(self.family_name) or {}).get(str(symbol).upper()) or {}).get(signal_name)),
            ((manual.get(str(symbol).upper()) or {}).get(signal_name)),
        ]
        for candidate in candidates:
            if isinstance(candidate, dict):
                raw_score = candidate.get("score")
                if raw_score is None:
                    raw_score = signal_score_from_bias(candidate.get("bias"))
                return self.signal(
                    signal_name,
                    score=raw_score,
                    obs_date=candidate.get("obs_date"),
                    stale=bool(candidate.get("stale", False)),
                    meta={
                        "available": True,
                        "source": "manual",
                        **dict(candidate.get("meta") or {}),
                    },
                )
        return None

    def signal(self, signal_name: str, *, score: Optional[float], obs_date: Optional[object], stale: bool, meta: Optional[dict] = None) -> dict:
        return make_signal(
            score=score,
            obs_date=obs_date,
            stale=stale,
            threshold=self.bias_threshold(),
            meta={"available": True, **dict(meta or {})},
        )

    def unavailable_signal(self, signal_name: str, reason: str, *, meta: Optional[dict] = None) -> dict:
        return make_unavailable_signal(reason, meta=meta)

    def series_last_vs_sma_signal(
        self,
        signal_name: str,
        *,
        series: pd.Series,
        as_of: str,
        trend_window: int,
        scale: float,
        invert: bool = False,
        meta: Optional[dict] = None,
    ) -> dict:
        last_value, last_dt = last_value_on_or_before(series, as_of)
        sma_value, sma_dt = self.engine._sma_on_or_before(series, as_of, trend_window)
        if last_value is None or sma_value is None:
            return self.unavailable_signal(signal_name, reason="insufficient_history")
        obs_candidates = [d for d in (last_dt, sma_dt) if d is not None]
        obs_date = min(obs_candidates) if obs_candidates else None
        raw = float(last_value - sma_value)
        score = clamp(((-1.0 if invert else 1.0) * raw) / float(scale), -1.0, 1.0)
        stale = bool(stale_flag(as_of, obs_date, self.signal_stale_days(signal_name)))
        return self.signal(
            signal_name,
            score=score,
            obs_date=obs_date,
            stale=stale,
            meta={
                "available": True,
                "last_value": float(last_value),
                "sma_window": int(trend_window),
                "sma_value": float(sma_value),
                "raw_delta": float(raw),
                **dict(meta or {}),
            },
        )

    def cot_signal(
        self,
        signal_name: str,
        *,
        kind: str,
        dataset_id: str,
        contract_name: Optional[str],
        as_of: str,
        direction: float = 1.0,
        meta: Optional[dict] = None,
    ) -> dict:
        if not contract_name:
            return self.unavailable_signal(signal_name, reason="missing_contract_mapping")
        try:
            res = self.engine._cftc_z_asof(kind, dataset_id, contract_name, as_of)
        except Exception as exc:
            return self.unavailable_signal(signal_name, reason="cot_error", meta={"error": str(exc), "contract": contract_name})
        if not res:
            return self.unavailable_signal(signal_name, reason="no_cot_history", meta={"contract": contract_name})
        obs_date = pd.Timestamp(res["report_date"])
        score = clamp(math.tanh(float(direction) * float(res["z"]) / 2.0), -1.0, 1.0)
        stale = bool(stale_flag(as_of, obs_date, self.signal_stale_days(signal_name)))
        return self.signal(
            signal_name,
            score=score,
            obs_date=obs_date,
            stale=stale,
            meta={
                "available": True,
                "contract": contract_name,
                "z": float(res["z"]),
                "value": float(res["value"]),
                "report_date": iso_date_or_none(res["report_date"]),
                "release_dt": str(res["release_dt"]) if res.get("release_dt") is not None else None,
                "n": int(res["n"]),
                **dict(meta or {}),
            },
        )
