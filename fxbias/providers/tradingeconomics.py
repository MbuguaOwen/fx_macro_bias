from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

TE_API_BASE = "https://api.tradingeconomics.com"


def _slug(s: str) -> str:
    return str(s).strip().lower().replace(" ", "%20")


@dataclass
class TradingEconomicsClient:
    cache_dir: Path
    api_key: Optional[str] = None
    timeout_s: int = 30
    user_agent: str = "fxbias/0.1.0"

    def __post_init__(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _cache_path(self, kind: str, country: str, indicator: str, start: str, end: str) -> Path:
        key = f"{kind}|{country}|{indicator}|{start}|{end}"
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        safe_country = country.lower().replace(" ", "_")
        safe_indicator = indicator.lower().replace(" ", "_")
        return self.cache_dir / f"te_{kind}_{safe_country}_{safe_indicator}_{start}_{end}_{h}.json"

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _get_json(self, url: str) -> list:
        headers = {"User-Agent": self.user_agent}
        r = requests.get(url, headers=headers, timeout=self.timeout_s)
        r.raise_for_status()
        return r.json()

    def historical_indicator(
        self,
        country: str,
        indicator: str,
        start: str,
        end: str,
        refresh: bool = False,
    ) -> pd.DataFrame:
        """
        TradingEconomics historical indicator endpoint.
        Returns DataFrame with at least date + value columns when available.
        """
        if not self.enabled:
            return pd.DataFrame()

        cpath = self._cache_path("historical", country, indicator, start, end)
        if (not refresh) and cpath.exists():
            data = json.loads(cpath.read_text(encoding="utf-8"))
        else:
            country_slug = _slug(country)
            ind_slug = _slug(indicator)
            url = (
                f"{TE_API_BASE}/historical/country/{country_slug}/indicator/{ind_slug}/"
                f"{start}/{end}?c={self.api_key}&f=json"
            )
            data = self._get_json(url)
            cpath.write_text(json.dumps(data), encoding="utf-8")

        if not isinstance(data, list):
            return pd.DataFrame()

        df = pd.DataFrame(data)
        if df.empty:
            return df

        date_cols = [c for c in ("DateTime", "date", "Date") if c in df.columns]
        value_cols = [c for c in ("Value", "value", "LastUpdate", "Actual") if c in df.columns]
        if date_cols:
            df["obs_dt"] = pd.to_datetime(df[date_cols[0]], errors="coerce", utc=True).dt.tz_convert(None)
        if "obs_dt" in df.columns:
            df = df.dropna(subset=["obs_dt"]).sort_values("obs_dt")
        if value_cols:
            df["value_num"] = pd.to_numeric(df[value_cols[0]], errors="coerce")
        elif "Value" in df.columns:
            df["value_num"] = pd.to_numeric(df["Value"], errors="coerce")
        return df

