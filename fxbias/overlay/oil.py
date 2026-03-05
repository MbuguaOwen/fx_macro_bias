from __future__ import annotations

import pandas as pd

from ..timeseries import iso_date_or_none, stale_flag
from .base import BaseSentimentOverlay


class OilSentimentOverlay(BaseSentimentOverlay):
    family_name = "oil"
    signal_names = ("eia_inventories", "opec_stance", "cot", "usd", "risk_sentiment", "baker_hughes_rig_count")

    def supports(self, symbol: str) -> bool:
        return str(symbol).upper() in {"WTI", "USOIL"}

    def build(self, symbol: str, as_of: str, macro_row: dict | None = None) -> dict:
        symbol_u = str(symbol).upper()
        signals = {
            "eia_inventories": self._manual_placeholder_signal(symbol_u, "eia_inventories"),
            "opec_stance": self._manual_placeholder_signal(symbol_u, "opec_stance"),
            "cot": self._cot_signal(as_of=as_of),
            "usd": self._usd_signal(as_of=as_of),
            "risk_sentiment": self._risk_signal(as_of=as_of),
            "baker_hughes_rig_count": self._rig_count_signal(as_of=as_of, symbol=symbol_u),
        }
        return self.finalize(
            symbol=symbol_u,
            as_of=as_of,
            macro_row=macro_row,
            signals=signals,
            extra_meta={"family": self.family_name, "scaffold": True},
        )

    def _manual_placeholder_signal(self, symbol: str, signal_name: str) -> dict:
        manual = self.manual_signal(symbol, signal_name)
        if manual is not None:
            return manual
        return self.unavailable_signal(signal_name, reason="source_unavailable", meta={"source": "placeholder"})

    def _cot_signal(self, as_of: str) -> dict:
        cot_cfg = (self.family_cfg().get("cot") or {})
        dataset_id = str(cot_cfg.get("dataset_id") or self.engine.cftc_cfg.get("disagg_futures_only", "72hh-3qpy"))
        contract_name = cot_cfg.get("contract_name")
        return self.cot_signal(
            "cot",
            kind="disagg",
            dataset_id=dataset_id,
            contract_name=contract_name,
            as_of=as_of,
            direction=1.0,
            meta={"theme": "oil_positioning"},
        )

    def _usd_signal(self, as_of: str) -> dict:
        cfg = (self.family_cfg().get("usd") or {})
        series_id = str(cfg.get("series_id") or ((self.engine.fred_cfg.get("risk", {}) or {}).get("dxy") or "DTWEXBGS"))
        try:
            series = self.engine._fred_series(series_id, None, pd.Timestamp(as_of).date())
        except Exception as exc:
            return self.unavailable_signal("usd", reason="series_error", meta={"series_id": series_id, "error": str(exc)})
        return self.series_last_vs_sma_signal(
            "usd",
            series=series,
            as_of=as_of,
            trend_window=int(cfg.get("trend_window", 50)),
            scale=float(cfg.get("scale", 2.5)),
            invert=True,
            meta={"series_id": series_id, "theme": "inverse_usd"},
        )

    def _risk_signal(self, as_of: str) -> dict:
        regime = self.engine._risk_regime(as_of)
        if not regime:
            return self.unavailable_signal("risk_sentiment", reason="missing_regime")
        obs_date = pd.Timestamp(regime["obs_date"]) if regime.get("obs_date") else None
        return self.signal(
            "risk_sentiment",
            score=(0.75 if bool(regime.get("risk_on")) else -0.75),
            obs_date=obs_date,
            stale=bool(stale_flag(as_of, obs_date, self.signal_stale_days("risk_sentiment"))),
            meta={
                "available": True,
                "risk_on": bool(regime.get("risk_on")),
                "usd_bid": regime.get("usd_bid"),
                "regime_obs_date": iso_date_or_none(obs_date),
            },
        )

    def _rig_count_signal(self, as_of: str, symbol: str) -> dict:
        manual = self.manual_signal(symbol, "baker_hughes_rig_count")
        if manual is not None:
            return manual
        cfg = (self.family_cfg().get("baker_hughes_rig_count") or {})
        series_id = cfg.get("series_id")
        if not series_id:
            return self.unavailable_signal("baker_hughes_rig_count", reason="source_unavailable", meta={"source": "placeholder"})
        try:
            series = self.engine._fred_series(str(series_id), None, pd.Timestamp(as_of).date())
        except Exception as exc:
            return self.unavailable_signal("baker_hughes_rig_count", reason="series_error", meta={"series_id": str(series_id), "error": str(exc)})
        return self.series_last_vs_sma_signal(
            "baker_hughes_rig_count",
            series=series,
            as_of=as_of,
            trend_window=int(cfg.get("trend_window", 26)),
            scale=float(cfg.get("scale", 40.0)),
            invert=True,
            meta={"series_id": str(series_id), "theme": "inverse_supply"},
        )
