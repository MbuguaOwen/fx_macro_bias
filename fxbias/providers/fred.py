from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

FRED_GRAPH_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"


@dataclass
class FredClient:
    cache_dir: Path
    timeout_s: int = 20
    user_agent: str = "fxbias/0.1.0"

    def __post_init__(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, series_id: str) -> Path:
        safe = series_id.strip().upper().replace("/", "_")
        return self.cache_dir / f"fred_{safe}.csv"

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _fetch_csv(self, series_id: str) -> str:
        headers = {"User-Agent": self.user_agent}
        r = requests.get(FRED_GRAPH_CSV, params={"id": series_id}, headers=headers, timeout=self.timeout_s)
        r.raise_for_status()
        return r.text

    def get_series(self, series_id: str, refresh: bool = False) -> pd.Series:
        cpath = self._cache_path(series_id)
        if (not refresh) and cpath.exists():
            text = cpath.read_text(encoding="utf-8", errors="ignore")
        else:
            text = self._fetch_csv(series_id)
            cpath.write_text(text, encoding="utf-8")

        df = pd.read_csv(io.StringIO(text))
        date_col = None
        for c in ("DATE", "observation_date"):
            if c in df.columns:
                date_col = c
                break
        if df.empty or not date_col:
            raise ValueError(f"FRED returned no usable data for series_id={series_id}")

        value_col = [c for c in df.columns if c != date_col]
        if not value_col:
            raise ValueError(f"FRED missing value column for series_id={series_id}")
        value_col = value_col[0]

        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
        df = df.dropna(subset=[date_col]).sort_values(date_col).set_index(date_col)
        return df[value_col].astype(float)
