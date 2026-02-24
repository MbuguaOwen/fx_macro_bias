from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from ..timeseries import cot_release_dt_utc

SODA_BASE = "https://publicreporting.cftc.gov/resource"


def _to_float(x):
    try:
        return float(x)
    except Exception:
        return None


@dataclass
class CftcClient:
    cache_dir: Path
    timeout_s: int = 30
    user_agent: str = "fxbias/0.1.0"

    def __post_init__(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, dataset_id: str, key: str) -> Path:
        safe = key.replace(" ", "_").replace("/", "_").replace("=", "_").replace(":", "_").lower()
        return self.cache_dir / f"cftc_{dataset_id}_{safe}.json"

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _get_json(self, url: str, params: dict) -> list:
        headers = {"User-Agent": self.user_agent}
        r = requests.get(url, params=params, headers=headers, timeout=self.timeout_s)
        r.raise_for_status()
        return r.json()

    def query(
        self,
        dataset_id: str,
        where: Optional[str] = None,
        select: Optional[str] = None,
        limit: int = 50000,
        order: Optional[str] = None,
        refresh: bool = False,
        cache_key: str = "query",
    ) -> pd.DataFrame:
        cpath = self._cache_path(dataset_id, cache_key)
        if (not refresh) and cpath.exists():
            data = json.loads(cpath.read_text(encoding="utf-8"))
        else:
            url = f"{SODA_BASE}/{dataset_id}.json"
            params = {"$limit": limit}
            if where:
                params["$where"] = where
            if select:
                params["$select"] = select
            if order:
                params["$order"] = order
            data = self._get_json(url, params=params)
            cpath.write_text(json.dumps(data), encoding="utf-8")
        return pd.DataFrame(data)

    @staticmethod
    def _date_col(df: pd.DataFrame) -> Optional[str]:
        for col in ("report_date_as_yyyy_mm_dd", "report_date"):
            if col in df.columns:
                return col
        return None

    @staticmethod
    def _pick_col(columns: list[str], candidates: list[str]) -> Optional[str]:
        lower_map = {c.lower(): c for c in columns}
        for cand in candidates:
            if cand.lower() in lower_map:
                return lower_map[cand.lower()]
        for c in columns:
            lc = c.lower()
            if any(cand.lower() in lc for cand in candidates):
                return c
        return None

    def _parse_position_history(self, df: pd.DataFrame, kind: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

        date_col = self._date_col(df)
        if not date_col:
            return pd.DataFrame()

        cols = list(df.columns)
        if kind == "tff":
            long_col = self._pick_col(cols, ["lev_money_positions_long_all", "lev_money_positions_long"])
            short_col = self._pick_col(cols, ["lev_money_positions_short_all", "lev_money_positions_short"])
        elif kind == "disagg":
            long_col = self._pick_col(cols, ["m_money_positions_long_all", "m_money_positions_long"])
            short_col = self._pick_col(cols, ["m_money_positions_short_all", "m_money_positions_short"])
        else:
            raise ValueError(f"Unsupported kind={kind}")

        oi_col = self._pick_col(cols, ["open_interest_all", "open_interest"])
        if not long_col or not short_col:
            return pd.DataFrame()

        x = df.copy()
        x["report_date"] = pd.to_datetime(x[date_col], errors="coerce").dt.tz_localize(None)
        x = x.dropna(subset=["report_date"]).sort_values("report_date")
        x["long"] = x[long_col].map(_to_float)
        x["short"] = x[short_col].map(_to_float)
        x["net"] = x["long"] - x["short"]
        if oi_col and oi_col in x.columns:
            x["open_interest"] = x[oi_col].map(_to_float)
            x["net_oi"] = x["net"] / x["open_interest"].replace({0.0: pd.NA})
        else:
            x["open_interest"] = pd.NA
            x["net_oi"] = pd.NA
        x["value"] = x["net_oi"].where(x["net_oi"].notna(), x["net"])
        x["release_dt"] = x["report_date"].map(cot_release_dt_utc)
        keep = [
            "report_date",
            "release_dt",
            "contract_market_name",
            "market_and_exchange_names",
            "open_interest",
            "net",
            "net_oi",
            "value",
        ]
        for c in keep:
            if c not in x.columns:
                x[c] = pd.NA
        return x[keep].dropna(subset=["value"]).reset_index(drop=True)

    def contract_history(
        self,
        dataset_id: str,
        contract_name: str,
        kind: str,
        refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Historical COT rows for one exact contract_market_name (futures-only).
        kind in {"tff","disagg"}.
        """
        where_parts = [
            f"upper(contract_market_name) = '{contract_name.upper()}'",
            "futonly_or_combined = 'FutOnly'",
        ]
        where = " and ".join(where_parts)
        cache_key = f"{kind}_{contract_name}_full"
        df = self.query(
            dataset_id=dataset_id,
            where=where,
            select=None,
            limit=50000,
            order="report_date_as_yyyy_mm_dd asc",
            refresh=refresh,
            cache_key=cache_key,
        )
        return self._parse_position_history(df, kind=kind)

    def latest_net_position_tff(
        self,
        dataset_id: str,
        contract_match: str,
        refresh: bool = False,
    ) -> Optional[dict]:
        """
        Backward-compatible latest helper (kept for older call sites).
        Uses exact contract_market_name first, then legacy substring fallback.
        """
        df = self.contract_history(dataset_id, contract_match, kind="tff", refresh=refresh)
        if df.empty:
            where = f"upper(market_and_exchange_names) like '%{contract_match.upper()}%'"
            raw = self.query(
                dataset_id=dataset_id,
                where=where,
                select=None,
                limit=50000,
                order="report_date_as_yyyy_mm_dd asc",
                refresh=refresh,
                cache_key=f"tff_legacy_{contract_match}",
            )
            df = self._parse_position_history(raw, kind="tff")
        return self._latest_with_z(df)

    def latest_net_position_disagg(
        self,
        dataset_id: str,
        contract_match: str,
        refresh: bool = False,
    ) -> Optional[dict]:
        df = self.contract_history(dataset_id, contract_match, kind="disagg", refresh=refresh)
        if df.empty:
            where = f"upper(market_and_exchange_names) like '%{contract_match.upper()}%'"
            raw = self.query(
                dataset_id=dataset_id,
                where=where,
                select=None,
                limit=50000,
                order="report_date_as_yyyy_mm_dd asc",
                refresh=refresh,
                cache_key=f"disagg_legacy_{contract_match}",
            )
            df = self._parse_position_history(raw, kind="disagg")
        return self._latest_with_z(df)

    @staticmethod
    def _latest_with_z(df: pd.DataFrame, lookback_weeks: int = 156) -> Optional[dict]:
        if df is None or df.empty:
            return None
        series = pd.to_numeric(df["value"], errors="coerce").dropna()
        if len(series) < 26:
            return None
        latest_val = float(series.iloc[-1])
        look = series.tail(lookback_weeks)
        mu = float(look.mean())
        sd = float(look.std(ddof=0)) or 1e-9
        z = (latest_val - mu) / sd
        last = df.loc[series.index[-1]]
        return {
            "value": latest_val,
            "z": float(z),
            "as_of": pd.Timestamp(last["report_date"]).date().isoformat() if "report_date" in last else None,
            "report_date": pd.Timestamp(last["report_date"]).date().isoformat() if "report_date" in last else None,
            "release_dt": str(last["release_dt"]) if "release_dt" in last else None,
            "n": int(len(look)),
        }

