from __future__ import annotations

import datetime as dt
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import pandas as pd

from .providers.cftc import CftcClient
from .providers.fred import FredClient
from .providers.stooq import StooqClient
from .providers.tradingeconomics import TradingEconomicsClient
from .scoring import bias_from_score, clamp, conviction_from_score
from .timeseries import (
    age_days,
    asof_end_of_day_utc,
    asof_timestamp,
    iso_date_or_none,
    last_report_on_or_before,
    last_value_on_or_before,
    parse_asof_date,
    stale_flag,
)


def _split_pair(pair: str) -> Tuple[str, str]:
    p = pair.strip().upper()
    if p in ("USOIL", "WTI"):
        return ("WTI", "USD")
    if len(p) == 6:
        return p[:3], p[3:]
    if p in ("XAUUSD", "XAGUSD"):
        return p[:3], p[3:]
    raise ValueError(f"Unsupported pair format: {pair}")


@dataclass
class PillarResult:
    raw: Optional[float]
    score: Optional[float]
    obs_date: Optional[pd.Timestamp] = None
    age_days: Optional[int] = None
    stale: Optional[bool] = None
    meta: dict = field(default_factory=dict)

    def raw_or_none(self) -> Optional[float]:
        return None if self.raw is None else float(self.raw)

    def score_or_none(self) -> Optional[float]:
        return None if self.score is None else float(self.score)


@dataclass
class MacroBiasEngine:
    cfg: dict
    refresh: bool = False

    def __post_init__(self):
        cache_dir = Path(self.cfg.get("cache_dir", ".cache"))
        self.stooq = StooqClient(cache_dir=cache_dir)
        self.cftc = CftcClient(cache_dir=cache_dir)
        self.fred = FredClient(cache_dir=cache_dir)

        te_cfg = self.cfg.get("tradingeconomics", {})
        te_env = te_cfg.get("api_key_env", "TRADINGECONOMICS_API_KEY")
        te_key = te_cfg.get("api_key") or os.getenv(te_env)
        self.te = TradingEconomicsClient(cache_dir=cache_dir, api_key=te_key)

        self.weights = dict(self.cfg.get("weights", {}))
        self.stooq_cfg = self.cfg.get("stooq", {})
        self.cftc_cfg = self.cfg.get("cftc", {})
        self.fred_cfg = self.cfg.get("fred", {})
        self.growth_cfg = self.cfg.get("growth", {})
        self.thresholds_cfg = self.cfg.get("thresholds", {})
        self.conviction_cfg = self.cfg.get("conviction", {})
        self.staleness_cfg = self.cfg.get("staleness", {})

        self._range_cache: dict = {}
        self._full_cache: dict = {}

    # ---------------- caching / data access ----------------
    def _range_key(self, dataset: str, symbol: str, start: Optional[str], end: Optional[str], granularity: str):
        return (dataset, symbol, start, end, granularity)

    def _date_bounds_str(self, start: Optional[dt.date], end: Optional[dt.date]) -> Tuple[Optional[str], Optional[str]]:
        return (start.isoformat() if start else None, end.isoformat() if end else None)

    def _slice_series(self, s: pd.Series, start: Optional[dt.date], end: Optional[dt.date]) -> pd.Series:
        if s is None or s.empty:
            return s
        x = s.sort_index()
        if start is not None:
            x = x[x.index >= pd.Timestamp(start)]
        if end is not None:
            x = x[x.index <= pd.Timestamp(end)]
        return x

    def _slice_df_by_report_date(self, df: pd.DataFrame, start: Optional[dt.date], end: Optional[dt.date]) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        x = df.sort_values("report_date")
        if start is not None:
            x = x[x["report_date"] >= pd.Timestamp(start)]
        if end is not None:
            x = x[x["report_date"] <= pd.Timestamp(end)]
        return x.reset_index(drop=True)

    def _stooq_close_series(self, symbol: str, start: Optional[dt.date], end: Optional[dt.date]) -> pd.Series:
        start_s, end_s = self._date_bounds_str(start, end)
        key = self._range_key("stooq_close", symbol, start_s, end_s, "d")
        if key in self._range_cache:
            return self._range_cache[key]
        full_key = ("stooq_full", symbol, "d")
        if full_key not in self._full_cache:
            df = self.stooq.get_ohlc(symbol=symbol, interval="d", refresh=self.refresh)
            self._full_cache[full_key] = pd.to_numeric(df["Close"], errors="coerce").dropna()
        s = self._slice_series(self._full_cache[full_key], start, end)
        self._range_cache[key] = s
        return s

    def _fred_series(self, series_id: str, start: Optional[dt.date], end: Optional[dt.date]) -> pd.Series:
        start_s, end_s = self._date_bounds_str(start, end)
        key = self._range_key("fred_series", series_id, start_s, end_s, "native")
        if key in self._range_cache:
            return self._range_cache[key]
        full_key = ("fred_full", series_id)
        if full_key not in self._full_cache:
            self._full_cache[full_key] = self.fred.get_series(series_id, refresh=self.refresh)
        s = self._slice_series(self._full_cache[full_key], start, end)
        self._range_cache[key] = s
        return s

    def _cftc_contract_history(self, dataset_id: str, contract_name: str, kind: str, start: Optional[dt.date], end: Optional[dt.date]) -> pd.DataFrame:
        start_s, end_s = self._date_bounds_str(start, end)
        key = self._range_key(f"cftc_{kind}", f"{dataset_id}:{contract_name}", start_s, end_s, "w")
        if key in self._range_cache:
            return self._range_cache[key]
        full_key = ("cftc_full", kind, dataset_id, contract_name)
        if full_key not in self._full_cache:
            self._full_cache[full_key] = self.cftc.contract_history(dataset_id=dataset_id, contract_name=contract_name, kind=kind, refresh=self.refresh)
        df = self._slice_df_by_report_date(self._full_cache[full_key], start, end)
        self._range_cache[key] = df
        return df

    def _te_indicator_series(self, country: str, indicator: str, start: dt.date, end: dt.date) -> pd.Series:
        start_s, end_s = start.isoformat(), end.isoformat()
        key = self._range_key("te_indicator", f"{country}:{indicator}", start_s, end_s, "native")
        if key in self._range_cache:
            return self._range_cache[key]
        full_key = ("te_full", country, indicator, start_s, end_s)
        if full_key not in self._full_cache:
            df = self.te.historical_indicator(country=country, indicator=indicator, start=start_s, end=end_s, refresh=self.refresh)
            if df.empty or "obs_dt" not in df.columns or "value_num" not in df.columns:
                s = pd.Series(dtype=float)
            else:
                s = pd.to_numeric(df["value_num"], errors="coerce")
                s.index = pd.to_datetime(df["obs_dt"]).dt.tz_localize(None)
                s = s.dropna().sort_index()
            self._full_cache[full_key] = s
        self._range_cache[key] = self._full_cache[full_key]
        return self._range_cache[key]

    def prepare_history(self, pairs: List[str], asofs: Iterable[object]) -> None:
        asof_dates = sorted({parse_asof_date(a) for a in asofs})
        if not asof_dates:
            return
        asof_min, asof_max = asof_dates[0], asof_dates[-1]

        prefetch_cfg = self.cfg.get("prefetch", {})
        daily_buffer_days = int(prefetch_cfg.get("daily_buffer_days", 900))
        cot_buffer_days = int(prefetch_cfg.get("cot_buffer_days", 1800))
        growth_window_days = int(self.growth_cfg.get("zscore_window_days", 756)) + 365

        daily_start = asof_min - dt.timedelta(days=max(daily_buffer_days, growth_window_days))
        daily_end = asof_max
        cot_start = asof_min - dt.timedelta(days=cot_buffer_days)
        cot_end = asof_max

        currencies = set()
        metals = set()
        for p in pairs:
            b, q = _split_pair(p)
            (metals if b in ("XAU", "XAG", "XPT", "XPD") else currencies).add(b)
            (metals if q in ("XAU", "XAG", "XPT", "XPD") else currencies).add(q)

        ymap = self.stooq_cfg.get("yields_2y", {})
        for ccy in currencies:
            if ymap.get(ccy):
                try:
                    self._stooq_close_series(ymap[ccy], daily_start, daily_end)
                except Exception:
                    pass

        if str(self.growth_cfg.get("mode", "proxy")).lower() != "hard":
            emap = self.stooq_cfg.get("equity_index", {})
            for ccy in currencies:
                if emap.get(ccy):
                    try:
                        self._stooq_close_series(emap[ccy], daily_start, daily_end)
                    except Exception:
                        pass

        risk_stooq = self.stooq_cfg.get("risk", {})
        if risk_stooq.get("spx"):
            try:
                self._stooq_close_series(risk_stooq["spx"], daily_start, daily_end)
            except Exception:
                pass
        fred_risk = self.fred_cfg.get("risk", {})
        for sid in (fred_risk.get("vix", "VIXCLS"), fred_risk.get("dxy", "DTWEXBGS")):
            try:
                self._fred_series(sid, daily_start, daily_end)
            except Exception:
                pass

        tff_id = self.cftc_cfg.get("tff_futures_only", "gpe5-46if")
        disagg_id = self.cftc_cfg.get("disagg_futures_only", "72hh-3qpy")
        curmap = self.cftc_cfg.get("currency_contract_match", {})
        metmap = self.cftc_cfg.get("metal_contract_match", {})
        for ccy in currencies:
            if curmap.get(ccy):
                try:
                    self._cftc_contract_history(tff_id, curmap[ccy], "tff", cot_start, cot_end)
                except Exception:
                    pass
        for metal in metals:
            if metmap.get(metal):
                try:
                    self._cftc_contract_history(disagg_id, metmap[metal], "disagg", cot_start, cot_end)
                except Exception:
                    pass

        if str(self.growth_cfg.get("mode", "proxy")).lower() == "hard" and self.te.enabled:
            hard_start = asof_min - dt.timedelta(days=growth_window_days)
            hard_end = asof_max
            sources = [str(x).lower() for x in (self.growth_cfg.get("sources") or ["cesi", "pmi"])]
            te_g = self.growth_cfg.get("te", {})
            country_map = te_g.get("country_map", {})
            indicator_map = te_g.get("indicator_map", {"cesi": "economic surprise index", "pmi": "manufacturing pmi"})
            for source in sources:
                ind = indicator_map.get(source)
                if not ind:
                    continue
                for ccy in currencies:
                    country = country_map.get(ccy)
                    if country:
                        try:
                            self._te_indicator_series(country, ind, hard_start, hard_end)
                        except Exception:
                            pass

    # ---------------- helpers ----------------
    def _pillar_stale_days(self, pillar: str) -> Optional[int]:
        days_cfg = self.staleness_cfg.get("days", {})
        v = days_cfg.get(pillar)
        return None if v is None else int(v)

    def _make_pillar(
        self,
        pillar: str,
        asof: object,
        raw: Optional[float],
        score: Optional[float],
        obs_date: Optional[pd.Timestamp],
        meta: Optional[dict] = None,
    ) -> PillarResult:
        return PillarResult(
            raw=None if raw is None else float(raw),
            score=None if score is None else float(score),
            obs_date=obs_date,
            age_days=age_days(asof, obs_date),
            stale=stale_flag(asof, obs_date, self._pillar_stale_days(pillar)),
            meta=meta or {},
        )

    def _return_on_or_before(self, s: pd.Series, asof: object, days: int):
        if s is None or s.empty:
            return None, None, None
        x = s.dropna().sort_index()
        x = x[x.index <= asof_timestamp(asof)]
        if len(x) < days + 1:
            return None, None, None
        c0 = float(x.iloc[-(days + 1)])
        c1 = float(x.iloc[-1])
        if c0 == 0:
            return None, None, None
        return (c1 / c0) - 1.0, pd.Timestamp(x.index[-1]), pd.Timestamp(x.index[-(days + 1)])

    def _sma_on_or_before(self, s: pd.Series, asof: object, window: int):
        if s is None or s.empty:
            return None, None
        x = s.dropna().sort_index()
        x = x[x.index <= asof_timestamp(asof)]
        if len(x) < window:
            return None, None
        return float(x.tail(window).mean()), pd.Timestamp(x.index[-1])

    def _score_diff_from_series(self, base_s: pd.Series, quote_s: pd.Series, asof: object, source_name: str):
        b_val, b_dt = last_value_on_or_before(base_s, asof)
        q_val, q_dt = last_value_on_or_before(quote_s, asof)
        if b_val is None or q_val is None:
            return None, None, None, {}
        raw = float(b_val - q_val)
        obs_date = min([d for d in (b_dt, q_dt) if d is not None]) if (b_dt is not None and q_dt is not None) else (b_dt or q_dt)

        method = str(self.growth_cfg.get("normalize_method", "tanh")).lower()
        window_days = int(self.growth_cfg.get("zscore_window_days", 756))
        scales = self.growth_cfg.get("scales", {"cesi": 50.0, "pmi": 3.0})
        scale = float((scales or {}).get(source_name, 50.0 if source_name == "cesi" else 3.0))

        if method == "zscore":
            hist = pd.concat({"b": base_s, "q": quote_s}, axis=1).sort_index().ffill().dropna()
            hist = hist[hist.index <= asof_timestamp(asof)]
            start = asof_timestamp(asof) - pd.Timedelta(days=window_days)
            look = hist[hist.index >= start]
            if len(look) >= 20:
                diff = (look["b"] - look["q"]).astype(float)
                mu = float(diff.mean())
                sd = float(diff.std(ddof=0)) or 1e-9
                z = (raw - mu) / sd
                score = clamp(float(math.tanh(z / 2.0)), -1.0, 1.0)
                return raw, score, obs_date, {"method": "zscore_tanh", "z": z, "mu": mu, "sd": sd}

        score = clamp(float(math.tanh(raw / scale)), -1.0, 1.0)
        return raw, score, obs_date, {"method": "tanh", "scale": scale}

    def _cftc_z_asof(self, kind: str, dataset_id: str, contract_name: str, asof: object) -> Optional[dict]:
        hist = self._cftc_contract_history(dataset_id, contract_name, kind, start=None, end=parse_asof_date(asof))
        if hist is None or hist.empty:
            return None
        row, _ = last_report_on_or_before(hist, asof)
        if row is None:
            return None
        eligible = hist.copy()
        eligible = eligible[pd.to_datetime(eligible["release_dt"], utc=True) <= asof_end_of_day_utc(asof)]
        eligible = eligible[eligible["report_date"] <= pd.Timestamp(row["report_date"])]
        series = pd.to_numeric(eligible["value"], errors="coerce").dropna()
        if len(series) < 26:
            return None
        look = series.tail(156)
        latest_val = float(series.iloc[-1])
        mu = float(look.mean())
        sd = float(look.std(ddof=0)) or 1e-9
        return {
            "value": latest_val,
            "z": float((latest_val - mu) / sd),
            "report_date": pd.Timestamp(row["report_date"]),
            "release_dt": pd.Timestamp(row["release_dt"]),
            "n": int(len(look)),
        }

    # ---------------- PILLARS ----------------
    def pillar_rates(self, base: str, quote: str, asof: object) -> PillarResult:
        ymap = self.stooq_cfg.get("yields_2y", {})
        b, q = ymap.get(base), ymap.get(quote)
        if not b or not q:
            return self._make_pillar("rates", asof, None, None, None, {"reason": "missing_symbol_mapping"})
        try:
            sb = self._stooq_close_series(b, None, parse_asof_date(asof))
            sq = self._stooq_close_series(q, None, parse_asof_date(asof))
            yb, db = last_value_on_or_before(sb, asof)
            yq, dq = last_value_on_or_before(sq, asof)
        except Exception as e:
            return self._make_pillar("rates", asof, None, None, None, {"error": str(e)})
        if yb is None or yq is None:
            return self._make_pillar("rates", asof, None, None, None, {"reason": "missing_history"})
        raw = float(yb - yq)
        score = clamp(raw / 2.0, -1.0, 1.0)
        obs_date = min([d for d in (db, dq) if d is not None]) if (db is not None and dq is not None) else (db or dq)
        return self._make_pillar(
            "rates",
            asof,
            raw,
            score,
            obs_date,
            {"base_yield": yb, "quote_yield": yq, "base_obs_date": iso_date_or_none(db), "quote_obs_date": iso_date_or_none(dq)},
        )

    def pillar_growth(self, base: str, quote: str, asof: object) -> PillarResult:
        mode = str(self.growth_cfg.get("mode", "proxy")).lower()
        if mode == "hard":
            out = self._pillar_growth_hard(base, quote, asof)
            if out.score is not None or not bool(self.growth_cfg.get("fallback_to_proxy", False)):
                return out
        return self._pillar_growth_proxy(base, quote, asof)

    def _pillar_growth_proxy(self, base: str, quote: str, asof: object) -> PillarResult:
        emap = self.stooq_cfg.get("equity_index", {})
        b, q = emap.get(base), emap.get(quote)
        if not b or not q:
            return self._make_pillar("growth", asof, None, None, None, {"mode": "proxy", "reason": "missing_symbol_mapping"})
        try:
            sb = self._stooq_close_series(b, None, parse_asof_date(asof))
            sq = self._stooq_close_series(q, None, parse_asof_date(asof))
            rb, db, db0 = self._return_on_or_before(sb, asof, days=63)
            rq, dq, dq0 = self._return_on_or_before(sq, asof, days=63)
        except Exception as e:
            return self._make_pillar("growth", asof, None, None, None, {"mode": "proxy", "error": str(e)})
        if rb is None or rq is None:
            return self._make_pillar("growth", asof, None, None, None, {"mode": "proxy", "reason": "insufficient_history"})
        raw = float(rb - rq)
        score = clamp(raw / 0.10, -1.0, 1.0)
        obs_date = min([d for d in (db, dq) if d is not None]) if (db is not None and dq is not None) else (db or dq)
        return self._make_pillar(
            "growth",
            asof,
            raw,
            score,
            obs_date,
            {
                "mode": "proxy",
                "base_return_63d": rb,
                "quote_return_63d": rq,
                "base_obs_date": iso_date_or_none(db),
                "quote_obs_date": iso_date_or_none(dq),
                "base_start_date": iso_date_or_none(db0),
                "quote_start_date": iso_date_or_none(dq0),
            },
        )

    def _pillar_growth_hard(self, base: str, quote: str, asof: object) -> PillarResult:
        asof_d = parse_asof_date(asof)
        start = asof_d - dt.timedelta(days=int(self.growth_cfg.get("zscore_window_days", 756)) + 365)
        sources = [str(x).lower() for x in (self.growth_cfg.get("sources") or ["cesi", "pmi"])]
        w_cfg = self.growth_cfg.get("weights", {"cesi": 0.7, "pmi": 0.3})
        te_g = self.growth_cfg.get("te", {})
        country_map = te_g.get("country_map", {})
        indicator_map = te_g.get("indicator_map", {"cesi": "economic surprise index", "pmi": "manufacturing pmi"})

        components = {}
        for source in sources:
            ind = indicator_map.get(source)
            bc = country_map.get(base)
            qc = country_map.get(quote)
            if not ind or not bc or not qc or (not self.te.enabled):
                continue
            try:
                sb = self._te_indicator_series(bc, ind, start, asof_d)
                sq = self._te_indicator_series(qc, ind, start, asof_d)
                raw, score, obs_date, meta = self._score_diff_from_series(sb, sq, asof, source)
            except Exception as e:
                raw = score = None
                obs_date = None
                meta = {"error": str(e)}
            if score is None:
                continue
            comp_age = age_days(asof, obs_date)
            source_th = self._pillar_stale_days(source)
            if source_th is None:
                source_th = self._pillar_stale_days("growth")
            comp_stale = stale_flag(asof, obs_date, source_th)
            meta = dict(meta or {})
            meta["age_days"] = comp_age
            meta["stale"] = comp_stale
            components[source] = {"raw": raw, "score": score, "obs_date": obs_date, "meta": meta}

        if not components:
            return self._make_pillar("growth", asof, None, None, None, {"mode": "hard", "reason": "no_components"})

        ww = {k: float(w_cfg.get(k, 0.0)) for k in components}
        total_w = sum(ww.values())
        if total_w <= 0:
            ww = {k: 1.0 / len(components) for k in components}
        else:
            ww = {k: v / total_w for k, v in ww.items()}

        raw = sum(float(components[k]["raw"]) * ww[k] for k in components)
        score = sum(float(components[k]["score"]) * ww[k] for k in components)
        obs_dates = [v["obs_date"] for v in components.values() if v["obs_date"] is not None]
        obs_date = min(obs_dates) if obs_dates else None
        meta_components = {
            k: {
                "raw": float(v["raw"]),
                "score": float(v["score"]),
                "obs_date": iso_date_or_none(v["obs_date"]),
                **(v.get("meta") or {}),
            }
            for k, v in components.items()
        }
        return self._make_pillar(
            "growth",
            asof,
            raw,
            clamp(score, -1.0, 1.0),
            obs_date,
            {"mode": "hard", "components": meta_components, "component_weights": ww},
        )

    def _risk_regime(self, asof: object) -> Optional[dict]:
        risk_stooq = self.stooq_cfg.get("risk", {})
        fred_risk = self.fred_cfg.get("risk", {})
        spx_sym = risk_stooq.get("spx", "^spx")
        try:
            spx_s = self._stooq_close_series(spx_sym, None, parse_asof_date(asof))
            vix_s = self._fred_series(fred_risk.get("vix", "VIXCLS"), None, parse_asof_date(asof))
            dxy_s = self._fred_series(fred_risk.get("dxy", "DTWEXBGS"), None, parse_asof_date(asof))
        except Exception:
            return None
        spx_sma50, spx_dt = self._sma_on_or_before(spx_s, asof, 50)
        spx_sma200, _ = self._sma_on_or_before(spx_s, asof, 200)
        vix_last, vix_dt = last_value_on_or_before(vix_s, asof)
        vix_sma20, _ = self._sma_on_or_before(vix_s, asof, 20)
        dxy_sma50, dxy_dt = self._sma_on_or_before(dxy_s, asof, 50)
        dxy_sma200, _ = self._sma_on_or_before(dxy_s, asof, 200)
        if None in (spx_sma50, spx_sma200, vix_last, vix_sma20, dxy_sma50, dxy_sma200):
            return None

        # Component-level staleness: do NOT silently use a stale DXY leg.
        # Defaults to risk staleness days unless component overrides are provided.
        risk_days = self._pillar_stale_days("risk")
        spx_days = self._pillar_stale_days("risk_spx")
        vix_days = self._pillar_stale_days("risk_vix")
        dxy_days = self._pillar_stale_days("risk_dxy")
        spx_days = risk_days if spx_days is None else spx_days
        vix_days = risk_days if vix_days is None else vix_days
        dxy_days = risk_days if dxy_days is None else dxy_days

        spx_stale = stale_flag(asof, spx_dt, spx_days)
        vix_stale = stale_flag(asof, vix_dt, vix_days)
        dxy_stale = stale_flag(asof, dxy_dt, dxy_days)

        risk_on = (spx_sma50 > spx_sma200) and (vix_last < vix_sma20)
        # If DXY is stale, keep SPX+VIX regime but disable USD tilts.
        usd_bid = None if dxy_stale else (dxy_sma50 > dxy_sma200)
        obs_dates = [d for d in (spx_dt, vix_dt, dxy_dt) if d is not None]
        obs_date = min(obs_dates) if obs_dates else None
        return {
            "as_of": parse_asof_date(asof).isoformat(),
            "risk_on": bool(risk_on),
            "usd_bid": None if usd_bid is None else bool(usd_bid),
            "vix": float(vix_last),
            "spx_sma50": float(spx_sma50),
            "spx_sma200": float(spx_sma200),
            "vix_sma20": float(vix_sma20),
            "dxy_sma50": float(dxy_sma50),
            "dxy_sma200": float(dxy_sma200),
            "obs_date": iso_date_or_none(obs_date),
            "spx_obs_date": iso_date_or_none(spx_dt),
            "vix_obs_date": iso_date_or_none(vix_dt),
            "dxy_obs_date": iso_date_or_none(dxy_dt),
            "spx_age_days": age_days(asof, spx_dt),
            "vix_age_days": age_days(asof, vix_dt),
            "dxy_age_days": age_days(asof, dxy_dt),
            "spx_stale": spx_stale,
            "vix_stale": vix_stale,
            "dxy_stale": dxy_stale,
            "stale_components": [
                k
                for k, v in (
                    ("spx", spx_stale),
                    ("vix", vix_stale),
                    ("dxy", dxy_stale),
                )
                if v
            ],
        }

    def pillar_risk(self, base: str, quote: str, regime: Optional[dict], asof: object) -> PillarResult:
        if not regime:
            return self._make_pillar("risk", asof, None, None, None, {"reason": "missing_regime"})
        risk_on = bool(regime["risk_on"])
        usd_bid = regime.get("usd_bid", None)
        if usd_bid is not None:
            usd_bid = bool(usd_bid)

        def is_risk_on_ccy(ccy: str) -> bool:
            return ccy in ("AUD", "NZD", "CAD")

        def is_haven(ccy: str) -> bool:
            return ccy in ("JPY", "CHF")

        score = 0.0
        if risk_on:
            if is_risk_on_ccy(base): score += 0.5
            if is_risk_on_ccy(quote): score -= 0.5
            if is_haven(base): score -= 0.5
            if is_haven(quote): score += 0.5
        else:
            if is_haven(base): score += 0.5
            if is_haven(quote): score -= 0.5
            if is_risk_on_ccy(base): score -= 0.5
            if is_risk_on_ccy(quote): score += 0.5
        # USD tilt is only applied when DXY is fresh.
        if usd_bid is not None:
            if base == "USD" and usd_bid: score += 0.25
            if quote == "USD" and usd_bid: score -= 0.25
            if base == "USD" and (not usd_bid): score -= 0.25
            if quote == "USD" and (not usd_bid): score += 0.25
        score = clamp(score, -1.0, 1.0)
        obs_date = pd.Timestamp(regime["obs_date"]) if regime.get("obs_date") else None
        meta = {"regime": regime}
        if regime.get("dxy_stale"):
            meta["warning"] = "dxy_stale_usd_tilt_disabled"
        return self._make_pillar("risk", asof, score, score, obs_date, meta)

    def pillar_positioning(self, base: str, quote: str, asof: object) -> PillarResult:
        tff_id = self.cftc_cfg.get("tff_futures_only", "gpe5-46if")
        disagg_id = self.cftc_cfg.get("disagg_futures_only", "72hh-3qpy")
        curmap = self.cftc_cfg.get("currency_contract_match", {})
        metmap = self.cftc_cfg.get("metal_contract_match", {})
        pos_cfg = self.cftc_cfg.get("positioning", {})
        usd_zero_baseline = bool(pos_cfg.get("usd_zero_baseline", True))

        if base in ("XAU", "XAG", "XPT", "XPD") or quote in ("XAU", "XAG", "XPT", "XPD"):
            metal = base if base in ("XAU", "XAG", "XPT", "XPD") else quote
            name = metmap.get(metal)
            if not name:
                return self._make_pillar("positioning", asof, None, None, None, {"reason": "missing_metal_mapping"})
            res = self._cftc_z_asof("disagg", disagg_id, name, asof)
            if not res:
                return self._make_pillar("positioning", asof, None, None, None, {"reason": "no_cot_history"})
            signed_z = float(res["z"] if metal == base else -res["z"])
            score = float(math.tanh(signed_z / 2.0))
            obs_date = pd.Timestamp(res["report_date"])
            return self._make_pillar(
                "positioning",
                asof,
                signed_z,
                score,
                obs_date,
                {"contract": name, "report_date": iso_date_or_none(res["report_date"]), "release_dt": str(res["release_dt"]), "n": int(res["n"])},
            )

        def leg(ccy: str):
            if ccy == "USD" and usd_zero_baseline and ccy not in curmap:
                return {"z": 0.0, "value": 0.0, "report_date": None, "release_dt": None, "synthetic": True}
            name = curmap.get(ccy)
            if not name:
                if ccy == "USD" and usd_zero_baseline:
                    return {"z": 0.0, "value": 0.0, "report_date": None, "release_dt": None, "synthetic": True}
                return None
            out = self._cftc_z_asof("tff", tff_id, name, asof)
            if out is None and ccy == "USD" and usd_zero_baseline:
                return {"z": 0.0, "value": 0.0, "report_date": None, "release_dt": None, "synthetic": True}
            if out is not None:
                out["contract"] = name
            return out

        rb = leg(base)
        rq = leg(quote)
        if not rb or not rq:
            return self._make_pillar("positioning", asof, None, None, None, {"reason": "missing_currency_cot"})

        raw = float(rb["z"] - rq["z"])
        score = float(math.tanh(raw / 2.0))
        obs_candidates = [pd.Timestamp(x["report_date"]) for x in (rb, rq) if x.get("report_date") is not None]
        obs_date = min(obs_candidates) if obs_candidates else None
        meta = {
            "base": {
                "contract": rb.get("contract"),
                "z": float(rb["z"]),
                "report_date": iso_date_or_none(rb.get("report_date")),
                "release_dt": str(rb.get("release_dt")) if rb.get("release_dt") is not None else None,
                "synthetic": bool(rb.get("synthetic", False)),
            },
            "quote": {
                "contract": rq.get("contract"),
                "z": float(rq["z"]),
                "report_date": iso_date_or_none(rq.get("report_date")),
                "release_dt": str(rq.get("release_dt")) if rq.get("release_dt") is not None else None,
                "synthetic": bool(rq.get("synthetic", False)),
            },
        }
        return self._make_pillar("positioning", asof, raw, score, obs_date, meta)

    # ---------------- compute / run ----------------
    def _compute_pair(self, pair: str, asof: object, regime: Optional[dict]) -> dict:
        base, quote = _split_pair(pair)
        pillars = {
            "rates": self.pillar_rates(base, quote, asof),
            "growth": self.pillar_growth(base, quote, asof),
            "risk": self.pillar_risk(base, quote, regime, asof),
            "positioning": self.pillar_positioning(base, quote, asof),
        }

        w = dict(self.weights)
        for k, p in pillars.items():
            if p.score is None:
                w[k] = 0.0
        w_sum = float(sum(w.values()))
        if w_sum <= 0:
            eff_w = {k: 0.0 for k in w}
            total_score = 0.0
        else:
            eff_w = {k: float(v) / w_sum for k, v in w.items()}
            total_score = sum((pillars[k].score or 0.0) * eff_w[k] for k in pillars)

        # Allow pair-specific bias threshold overrides.
        pair_u = pair.upper()
        pair_overrides = (self.thresholds_cfg.get("pair_overrides") or {})
        pth = (pair_overrides.get(pair_u) or {}).get("bias_threshold")
        bias_threshold = float(pth if pth is not None else self.thresholds_cfg.get("bias_threshold", 0.20))
        final_bias = bias_from_score(total_score, bull_bear_threshold=bias_threshold)
        conviction = conviction_from_score(total_score, cfg=self.conviction_cfg)
        overall_stale = any(bool(pillars[k].stale) and eff_w.get(k, 0.0) > 0 for k in pillars)
        pos_meta = pillars["positioning"].meta or {}
        pos_base = pos_meta.get("base") or {}
        pos_quote = pos_meta.get("quote") or {}

        row = {
            "pair": pair.upper(),
            "base": base,
            "quote": quote,
            "rates_raw": pillars["rates"].raw_or_none(),
            "growth_raw": pillars["growth"].raw_or_none(),
            "risk_raw": pillars["risk"].raw_or_none(),
            "positioning_raw": pillars["positioning"].raw_or_none(),
            "rates_score": pillars["rates"].score_or_none(),
            "growth_score": pillars["growth"].score_or_none(),
            "risk_score": pillars["risk"].score_or_none(),
            "positioning_score": pillars["positioning"].score_or_none(),
            "rates": pillars["rates"].score_or_none(),
            "growth": pillars["growth"].score_or_none(),
            "risk": pillars["risk"].score_or_none(),
            "positioning": pillars["positioning"].score_or_none(),
            "total_score": float(total_score),
            "score": float(total_score),
            "final_bias": final_bias,
            "bias": final_bias,
            "conviction_tier": conviction,
            "conviction_abs": float(abs(total_score)),
            "conviction_score": float(abs(total_score)),
            "w_rates": eff_w.get("rates", 0.0),
            "w_growth": eff_w.get("growth", 0.0),
            "w_risk": eff_w.get("risk", 0.0),
            "w_positioning": eff_w.get("positioning", 0.0),
            "rates_obs_date": iso_date_or_none(pillars["rates"].obs_date),
            "rates_age_days": pillars["rates"].age_days,
            "rates_stale": pillars["rates"].stale,
            "growth_obs_date": iso_date_or_none(pillars["growth"].obs_date),
            "growth_age_days": pillars["growth"].age_days,
            "growth_stale": pillars["growth"].stale,
            "risk_obs_date": iso_date_or_none(pillars["risk"].obs_date),
            "risk_age_days": pillars["risk"].age_days,
            "risk_stale": pillars["risk"].stale,
            "pos_obs_date": iso_date_or_none(pillars["positioning"].obs_date),
            "pos_age_days": pillars["positioning"].age_days,
            "pos_stale": pillars["positioning"].stale,
            "pos_report_date": pos_meta.get("report_date"),
            "pos_release_dt": pos_meta.get("release_dt"),
            "pos_base_report_date": pos_base.get("report_date"),
            "pos_base_release_dt": pos_base.get("release_dt"),
            "pos_quote_report_date": pos_quote.get("report_date"),
            "pos_quote_release_dt": pos_quote.get("release_dt"),
            "overall_staleness_flag": bool(overall_stale),
            "_pillar_meta": {k: pillars[k].meta for k in pillars},
        }
        return row

    def run(self, pairs: List[str], asof: Optional[str] = None):
        asof_d = parse_asof_date(asof)
        self.prepare_history(pairs=pairs, asofs=[asof_d])
        regime = self._risk_regime(asof_d)
        rows = [self._compute_pair(pair, asof_d, regime) for pair in pairs]
        df = pd.DataFrame(rows).sort_values(["total_score", "pair"], ascending=[False, True]).reset_index(drop=True)
        meta = {
            "as_of": asof_d.isoformat(),
            "risk_regime": regime,
            "weights": self.weights,
            "thresholds": {
                "bias_threshold": float(self.thresholds_cfg.get("bias_threshold", 0.20)),
                "conviction": self.conviction_cfg or {},
            },
            "notes": {
                "rates": "2Y yield spread proxy (Stooq), sliced on-or-before as_of",
                "growth": "Hard mode (CESI/PMI via TradingEconomics, optional) or proxy equity return differential",
                "risk": "SPX (Stooq) + VIX/Dollar index (FRED) regime tilt, computed as-of",
                "positioning": "CFTC COT with report_date/release_dt alignment (Friday release eligibility)",
                "weights": "Auto-renormalized when pillars are missing",
            },
        }
        return df, meta

    def debug_pair_series(self, pair: str, weeks: int, end_date: Optional[str] = None):
        from .reporting import _weekly_asof_dates  # local import to avoid import cycle

        asofs = _weekly_asof_dates(weeks=weeks, end_date=end_date)
        self.prepare_history(pairs=[pair], asofs=asofs)
        rows = []
        provenance = []
        for d in asofs:
            df, meta = self.run(pairs=[pair], asof=d)
            r = df.iloc[0].to_dict()
            rows.append(
                {
                    "asof": d,
                    "rates_raw": r.get("rates_raw"),
                    "growth_raw": r.get("growth_raw"),
                    "risk_raw": r.get("risk_raw"),
                    "positioning_raw": r.get("positioning_raw"),
                    "rates_score": r.get("rates_score"),
                    "growth_score": r.get("growth_score"),
                    "risk_score": r.get("risk_score"),
                    "positioning_score": r.get("positioning_score"),
                    "total_score": r.get("total_score"),
                    "final_bias": r.get("final_bias"),
                }
            )
            pm = r.get("_pillar_meta") or {}
            provenance.append(
                {
                    "asof": d,
                    "rates": {"obs_date": r.get("rates_obs_date"), "age_days": r.get("rates_age_days"), "raw": r.get("rates_raw")},
                    "growth": {
                        "obs_date": r.get("growth_obs_date"),
                        "age_days": r.get("growth_age_days"),
                        "raw": r.get("growth_raw"),
                        "mode": (pm.get("growth") or {}).get("mode"),
                    },
                    "risk": {"obs_date": r.get("risk_obs_date"), "age_days": r.get("risk_age_days"), "raw": r.get("risk_raw")},
                    "positioning": {
                        "obs_date": r.get("pos_obs_date"),
                        "age_days": r.get("pos_age_days"),
                        "raw": r.get("positioning_raw"),
                        "base_report_date": (((pm.get("positioning") or {}).get("base") or {}).get("report_date")),
                        "quote_report_date": (((pm.get("positioning") or {}).get("quote") or {}).get("report_date")),
                        "report_date": (pm.get("positioning") or {}).get("report_date"),
                    },
                    "risk_regime": meta.get("risk_regime"),
                }
            )
        return pd.DataFrame(rows), provenance

    def conviction_distribution(self, pairs: List[str], weeks: int, end_date: Optional[str] = None) -> dict:
        """Compute conviction (abs(total_score)) distribution over weekly as-of dates.

        This is used to calibrate conviction band thresholds to the actual score range your
        composite produces.
        """
        from .reporting import _weekly_asof_dates  # local import to avoid import cycle

        asofs = _weekly_asof_dates(weeks=weeks, end_date=end_date)
        self.prepare_history(pairs=pairs, asofs=asofs)

        xs: List[float] = []
        rows = 0
        for d in asofs:
            df, _ = self.run(pairs=pairs, asof=d)
            if df is None or df.empty:
                continue
            v = pd.to_numeric(df.get("conviction_abs"), errors="coerce").dropna()
            xs.extend([float(x) for x in v.values.tolist()])
            rows += len(df)

        if not xs:
            return {"n": 0, "weeks": len(asofs), "pairs": len(pairs), "quantiles": {}, "summary": {}}

        s = pd.Series(xs)
        quantiles = {q: float(s.quantile(q)) for q in (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)}
        summary = {
            "min": float(s.min()),
            "max": float(s.max()),
            "mean": float(s.mean()),
            "std": float(s.std(ddof=0)),
        }
        # Opinionated defaults: use quantiles to set bands so you actually see STRONG/EXTREME.
        recommended = {
            "neutral_threshold": float(s.quantile(0.10)),
            "bands": {
                "weak": float(s.quantile(0.25)),
                "moderate": float(s.quantile(0.60)),
                "strong": float(s.quantile(0.85)),
                "extreme": float(s.quantile(0.95)),
            },
        }
        return {
            "n": int(len(xs)),
            "rows": int(rows),
            "weeks": int(len(asofs)),
            "pairs": int(len(pairs)),
            "quantiles": quantiles,
            "summary": summary,
            "recommended": recommended,
        }
