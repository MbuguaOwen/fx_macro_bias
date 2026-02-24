from __future__ import annotations

import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

STOOQ_CSV_URL = "https://stooq.com/q/d/l/"

@dataclass
class StooqClient:
    cache_dir: Path
    timeout_s: int = 20
    user_agent: str = "fxbias/0.1.0"

    def __post_init__(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, symbol: str, interval: str) -> Path:
        safe = symbol.lower().replace("^", "_caret_").replace("/", "_")
        return self.cache_dir / f"stooq_{safe}_{interval}.csv"

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _fetch_csv(self, symbol: str, interval: str) -> str:
        params = {"s": symbol, "i": interval}
        headers = {"User-Agent": self.user_agent}
        r = requests.get(STOOQ_CSV_URL, params=params, headers=headers, timeout=self.timeout_s)
        r.raise_for_status()
        return r.text

    def get_ohlc(self, symbol: str, interval: str = "d", refresh: bool = False) -> pd.DataFrame:
        """
        Returns dataframe with Date index and columns: Open, High, Low, Close, Volume (if available).
        """
        cpath = self._cache_path(symbol, interval)
        if (not refresh) and cpath.exists():
            text = cpath.read_text(encoding="utf-8", errors="ignore")
        else:
            text = self._fetch_csv(symbol, interval)
            cpath.write_text(text, encoding="utf-8")

        df = pd.read_csv(io.StringIO(text))
        # Some stooq symbols return "No data" html; detect that.
        if df.empty or "Date" not in df.columns:
            raise ValueError(f"Stooq returned no usable data for symbol={symbol}")
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").set_index("Date")
        return df

    def get_last_close(self, symbol: str, interval: str = "d", refresh: bool = False) -> float:
        df = self.get_ohlc(symbol=symbol, interval=interval, refresh=refresh)
        return float(df["Close"].iloc[-1])

    def get_return(self, symbol: str, days: int = 63, refresh: bool = False) -> Optional[float]:
        """
        Simple close-to-close return over `days` trading days (approx. 3 months = 63).
        Returns None if insufficient history.
        """
        df = self.get_ohlc(symbol=symbol, interval="d", refresh=refresh)
        if len(df) < days + 1:
            return None
        c0 = float(df["Close"].iloc[-(days+1)])
        c1 = float(df["Close"].iloc[-1])
        if c0 == 0:
            return None
        return (c1 / c0) - 1.0

    def sma(self, symbol: str, window: int, refresh: bool = False) -> Optional[float]:
        df = self.get_ohlc(symbol=symbol, interval="d", refresh=refresh)
        if len(df) < window:
            return None
        return float(df["Close"].tail(window).mean())
