from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .compare import build_compare_payload, build_compare_table, classify_flip, persistence_streak
from .dashboard import (
    _last_friday,
    _make_pdf_dashboard,
    _parse_date,
    _today_utc_date,
    _weekly_asof_dates,
    build_dashboard_payload,
    build_weekly_report,
    stable_payload_json,
)
from .dashboard import _make_html_dashboard as _render_payload_html


def _make_html_dashboard(out_html: Path, weeks: List[str], panel: pd.DataFrame, meta_by_week: Dict[str, dict]) -> None:
    """Backward-compatible wrapper for legacy callers."""
    payload = build_dashboard_payload(panel=panel, weeks=weeks, meta_by_week=meta_by_week)
    _render_payload_html(out_html=out_html, payload=payload)


__all__ = [
    "_parse_date",
    "_today_utc_date",
    "_last_friday",
    "_weekly_asof_dates",
    "_make_html_dashboard",
    "_make_pdf_dashboard",
    "build_dashboard_payload",
    "build_weekly_report",
    "stable_payload_json",
    "build_compare_payload",
    "build_compare_table",
    "classify_flip",
    "persistence_streak",
]

