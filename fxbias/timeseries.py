from __future__ import annotations

import datetime as dt
from typing import Optional, Tuple

import pandas as pd


def parse_asof_date(asof: object) -> dt.date:
    if asof is None:
        return dt.datetime.utcnow().date()
    if isinstance(asof, dt.datetime):
        return asof.date()
    if isinstance(asof, dt.date):
        return asof
    if isinstance(asof, pd.Timestamp):
        return asof.to_pydatetime().date()
    return dt.date.fromisoformat(str(asof))


def asof_timestamp(asof: object) -> pd.Timestamp:
    return pd.Timestamp(parse_asof_date(asof))


def asof_end_of_day_utc(asof: object) -> pd.Timestamp:
    d = parse_asof_date(asof)
    return pd.Timestamp(dt.datetime(d.year, d.month, d.day, 23, 59, 59), tz="UTC")


def _normalize_index_like_ts(x: object) -> pd.Timestamp:
    ts = pd.Timestamp(x)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.normalize()


def last_value_on_or_before(series: pd.Series, asof: object) -> Tuple[Optional[float], Optional[pd.Timestamp]]:
    if series is None or len(series) == 0:
        return None, None
    s = series.dropna()
    if s.empty:
        return None, None
    cutoff = asof_timestamp(asof)
    s = s.sort_index()
    s = s[s.index <= cutoff]
    if s.empty:
        return None, None
    obs_ts = pd.Timestamp(s.index[-1])
    try:
        val = float(s.iloc[-1])
    except Exception:
        val = s.iloc[-1]
    return val, obs_ts


def last_row_on_or_before(df: pd.DataFrame, asof: object) -> Tuple[Optional[pd.Series], Optional[pd.Timestamp]]:
    if df is None or df.empty:
        return None, None
    cutoff = asof_timestamp(asof)
    x = df.sort_index()
    x = x[x.index <= cutoff]
    if x.empty:
        return None, None
    obs_ts = pd.Timestamp(x.index[-1])
    return x.iloc[-1], obs_ts


def cot_release_dt_utc(report_date: object) -> pd.Timestamp:
    # Use Friday end-of-day UTC for conservative no-lookahead eligibility.
    d = pd.Timestamp(report_date).tz_localize(None).date()
    release_date = d + dt.timedelta(days=3)
    return pd.Timestamp(dt.datetime(release_date.year, release_date.month, release_date.day, 23, 59, 59), tz="UTC")


def last_report_on_or_before(cot_df: pd.DataFrame, asof: object) -> Tuple[Optional[pd.Series], Optional[pd.Timestamp]]:
    if cot_df is None or cot_df.empty:
        return None, None
    asof_eod = asof_end_of_day_utc(asof)
    if "release_dt" not in cot_df.columns:
        raise KeyError("cot_df must contain release_dt column")
    x = cot_df.copy()
    x = x.sort_values("report_date")
    rel = pd.to_datetime(x["release_dt"], utc=True, errors="coerce")
    x = x[rel <= asof_eod]
    if x.empty:
        return None, None
    row = x.iloc[-1]
    return row, pd.Timestamp(row["report_date"])


def age_days(asof: object, obs_date: object) -> Optional[int]:
    if obs_date is None:
        return None
    a = parse_asof_date(asof)
    o = pd.Timestamp(obs_date).tz_localize(None).date()
    return int((a - o).days)


def stale_flag(asof: object, obs_date: object, threshold_days: Optional[int]) -> Optional[bool]:
    if threshold_days is None:
        return None
    age = age_days(asof, obs_date)
    if age is None:
        return None
    return bool(age > threshold_days)


def iso_date_or_none(x: object) -> Optional[str]:
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass
    ts = pd.Timestamp(x)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.date().isoformat()

