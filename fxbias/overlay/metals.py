from __future__ import annotations

import pandas as pd

from ..timeseries import stale_flag
from .base import BaseSentimentOverlay
from .utils import sentiment_bias_from_score


class MetalsSentimentOverlay(BaseSentimentOverlay):
    family_name = "metals"
    signal_names = ("cot", "real_yields", "dxy", "etf_flows", "vix", "gold_silver_ratio")
    supported_symbols = {"XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"}

    def supports(self, symbol: str) -> bool:
        return str(symbol).upper() in self.supported_symbols

    def build(self, symbol: str, as_of: str, macro_row: dict | None = None) -> dict:
        symbol_u = str(symbol).upper()
        family_cfg = self.family_cfg()
        signals = {
            "cot": self._cot_signal(metal=symbol_u[:3], as_of=as_of),
            "real_yields": self._real_yields_signal(as_of=as_of),
            "dxy": self._dxy_signal(as_of=as_of),
            "etf_flows": self._etf_flow_signal(symbol=symbol_u),
            "vix": self._vix_signal(symbol=symbol_u, as_of=as_of),
            "gold_silver_ratio": self._gold_silver_ratio_signal(symbol=symbol_u, as_of=as_of),
        }
        return self.finalize(
            symbol=symbol_u,
            as_of=as_of,
            macro_row=macro_row,
            signals=signals,
            extra_meta={"family": self.family_name, "configured_keys": sorted(family_cfg.keys())},
        )

    def _cot_signal(self, metal: str, as_of: str) -> dict:
        disagg_id = self.engine.cftc_cfg.get("disagg_futures_only", "72hh-3qpy")
        metmap = self.engine.cftc_cfg.get("metal_contract_match", {}) or {}
        return self.cot_signal(
            "cot",
            kind="disagg",
            dataset_id=disagg_id,
            contract_name=metmap.get(metal),
            as_of=as_of,
            direction=1.0,
            meta={"theme": "positioning"},
        )

    def _real_yields_signal(self, as_of: str) -> dict:
        cfg = (self.family_cfg().get("real_yields") or {})
        series_id = str(cfg.get("series_id") or "DFII10")
        try:
            series = self.engine._fred_series(series_id, None, pd.Timestamp(as_of).date())
        except Exception as exc:
            return self.unavailable_signal("real_yields", reason="series_error", meta={"series_id": series_id, "error": str(exc)})
        return self.series_last_vs_sma_signal(
            "real_yields",
            series=series,
            as_of=as_of,
            trend_window=int(cfg.get("trend_window", 20)),
            scale=float(cfg.get("scale", 0.35)),
            invert=True,
            meta={"series_id": series_id, "theme": "inverse_real_yield"},
        )

    def _dxy_signal(self, as_of: str) -> dict:
        cfg = (self.family_cfg().get("dxy") or {})
        series_id = str(cfg.get("series_id") or ((self.engine.fred_cfg.get("risk", {}) or {}).get("dxy") or "DTWEXBGS"))
        try:
            series = self.engine._fred_series(series_id, None, pd.Timestamp(as_of).date())
        except Exception as exc:
            return self.unavailable_signal("dxy", reason="series_error", meta={"series_id": series_id, "error": str(exc)})
        return self.series_last_vs_sma_signal(
            "dxy",
            series=series,
            as_of=as_of,
            trend_window=int(cfg.get("trend_window", 50)),
            scale=float(cfg.get("scale", 2.5)),
            invert=True,
            meta={"series_id": series_id, "theme": "inverse_usd"},
        )

    def _etf_flow_signal(self, symbol: str) -> dict:
        manual = self.manual_signal(symbol, "etf_flows")
        if manual is not None:
            return manual
        return self.unavailable_signal("etf_flows", reason="source_unavailable", meta={"source": "placeholder"})

    def _vix_signal(self, symbol: str, as_of: str) -> dict:
        cfg = (self.family_cfg().get("vix") or {})
        series_id = str(cfg.get("series_id") or ((self.engine.fred_cfg.get("risk", {}) or {}).get("vix") or "VIXCLS"))
        sensitivity = 1.0 if symbol in {"XAUUSD", "XPTUSD"} else float(cfg.get("silver_sensitivity", 0.5))
        try:
            series = self.engine._fred_series(series_id, None, pd.Timestamp(as_of).date())
        except Exception as exc:
            return self.unavailable_signal("vix", reason="series_error", meta={"series_id": series_id, "error": str(exc)})
        signal = self.series_last_vs_sma_signal(
            "vix",
            series=series,
            as_of=as_of,
            trend_window=int(cfg.get("trend_window", 20)),
            scale=float(cfg.get("scale", 4.0)),
            invert=False,
            meta={"series_id": series_id, "theme": "fear_regime"},
        )
        score = float(signal.get("score") or 0.0) * float(sensitivity)
        signal["score"] = score
        signal["bias"] = sentiment_bias_from_score(score, threshold=self.bias_threshold())
        signal["meta"] = dict(signal.get("meta") or {})
        signal["meta"]["sensitivity"] = float(sensitivity)
        return signal

    def _gold_silver_ratio_signal(self, symbol: str, as_of: str) -> dict:
        if symbol not in {"XAUUSD", "XAGUSD"}:
            return self.unavailable_signal("gold_silver_ratio", reason="not_applicable", meta={"symbol": symbol})
        cfg = (self.family_cfg().get("ratio") or {})
        gold_symbol = str(cfg.get("gold_symbol") or "xauusd")
        silver_symbol = str(cfg.get("silver_symbol") or "xagusd")
        try:
            gold = self.engine._stooq_close_series(gold_symbol, None, pd.Timestamp(as_of).date())
            silver = self.engine._stooq_close_series(silver_symbol, None, pd.Timestamp(as_of).date())
        except Exception as exc:
            return self.unavailable_signal("gold_silver_ratio", reason="series_error", meta={"error": str(exc)})
        aligned = pd.concat({"gold": gold, "silver": silver}, axis=1).dropna().sort_index()
        if aligned.empty:
            return self.unavailable_signal("gold_silver_ratio", reason="insufficient_history")
        ratio = (aligned["gold"] / aligned["silver"].replace({0.0: pd.NA})).dropna()
        if ratio.empty:
            return self.unavailable_signal("gold_silver_ratio", reason="insufficient_history")
        signal = self.series_last_vs_sma_signal(
            "gold_silver_ratio",
            series=ratio,
            as_of=as_of,
            trend_window=int(cfg.get("trend_window", 20)),
            scale=float(cfg.get("scale", 2.0)),
            invert=(symbol == "XAGUSD"),
            meta={"gold_symbol": gold_symbol, "silver_symbol": silver_symbol, "theme": "cross_context"},
        )
        signal["stale"] = bool(stale_flag(as_of, signal.get("obs_date"), self.signal_stale_days("gold_silver_ratio")))
        return signal
