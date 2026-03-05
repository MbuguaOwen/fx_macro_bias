from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from ..engine import MacroBiasEngine
from ..overlay import build_sentiment_overlay
from ..overlay.utils import overlay_summary, rows_for_dashboard
from .compare import build_compare_payload
from .templates import render_dashboard_html


def _parse_date(s: str) -> _dt.date:
    return _dt.date.fromisoformat(str(s))


def _today_utc_date() -> _dt.date:
    return _dt.datetime.utcnow().date()


def _last_friday(d: _dt.date) -> _dt.date:
    # Friday = 4
    offset = (d.weekday() - 4) % 7
    return d - _dt.timedelta(days=offset)


def _weekly_asof_dates(weeks: int, end_date: Optional[str] = None, asof: Optional[str] = None) -> List[str]:
    if asof:
        return [_parse_date(asof).isoformat()]
    end = _parse_date(end_date) if end_date else _today_utc_date()
    fri = _last_friday(end)
    out = [fri - _dt.timedelta(days=7 * i) for i in range(int(weeks))]
    return [d.isoformat() for d in sorted(out)]


def _bias_to_num(bias: object) -> int:
    b = str(bias or "")
    if b in ("BULL_BASE", "LONG", "BULLISH"):
        return 1
    if b in ("BEAR_BASE", "SHORT", "BEARISH"):
        return -1
    return 0


def _clean_value(v):
    if isinstance(v, dict):
        return {k: _clean_value(v[k]) for k in sorted(v.keys())}
    if isinstance(v, list):
        return [_clean_value(x) for x in v]
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if isinstance(v, (pd.Series, pd.Index)):
        return [_clean_value(x) for x in v.tolist()]
    return v


def stable_payload_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _overlay_hint_from_error(err: str) -> str:
    e = str(err or "").lower()
    if "playwright" in e:
        return "Install Playwright and Chromium: pip install playwright && playwright install chromium."
    if "captcha" in e or "login" in e or "403" in e or "forbidden" in e:
        return "The page may require captcha/login or manual access. Verify page access in a browser first."
    if "no options url" in e or "bad url" in e or "invalid url" in e:
        return "Provide a valid Investing options URL via --options-url or FXBIAS_OPTIONS_URL."
    if "parse" in e or "no rows" in e or "no table" in e or "empty" in e:
        return "The options table was not parsed. Verify the URL points to an Investing options table page."
    return "Retry with --refresh and verify URL accessibility and page structure."


def _normalize_overlay(overlay: Optional[dict], weeks: List[str]) -> dict:
    overlay = overlay or {}
    requested = bool(overlay.get("requested"))
    request = _clean_value(overlay.get("request") or {})
    error = overlay.get("error")

    entries = overlay.get("entries") or []
    cleaned_entries = []
    for e in entries:
        item = {k: _clean_value(v) for k, v in (e or {}).items()}
        pair = str(item.get("symbol") or "").upper()
        as_of = str(item.get("as_of") or "")
        if not pair or not as_of:
            continue
        item["symbol"] = pair
        item["as_of"] = as_of
        cleaned_entries.append(item)

    by_key = {}
    for e in sorted(cleaned_entries, key=lambda x: (x["as_of"], x["symbol"])):
        by_key[f'{e["symbol"]}|{e["as_of"]}'] = e

    enabled = bool(by_key)
    latest_week = weeks[-1] if weeks else None
    target_symbol = str(request.get("symbol") or "XAUUSD").upper()
    latest = None
    if latest_week:
        latest = by_key.get(f"{target_symbol}|{latest_week}")
        if latest is None:
            for k in sorted(by_key.keys(), reverse=True):
                if k.endswith(f"|{latest_week}"):
                    latest = by_key[k]
                    break

    if not requested:
        status = {
            "state": "disabled",
            "message": "Market overlay was not requested for this report.",
            "hint": "Enable with --with-options --options-url <investing-options-url> or set FXBIAS_OPTIONS_URL.",
        }
    elif error:
        status = {
            "state": "error",
            "message": f"Overlay request failed: {error}",
            "hint": _overlay_hint_from_error(str(error)),
        }
    elif enabled:
        status = {
            "state": "ok",
            "message": "Market overlay loaded.",
            "hint": "Overlay is informational only and does not affect fundamentals scoring.",
        }
    else:
        status = {
            "state": "error",
            "message": "Overlay was requested but no entries were available.",
            "hint": "Check URL/page access and parseability, then rerun with --refresh.",
        }

    return {
        "requested": requested,
        "enabled": enabled,
        "latest": latest,
        "by_key": by_key,
        "request": request,
        "error": None if error is None else str(error),
        "status": status,
    }


def _normalize_sentiment_overlay(overlay: Optional[dict], weeks: List[str]) -> dict:
    overlay = overlay or {}
    requested = bool(overlay.get("requested"))
    error = overlay.get("error")
    request = _clean_value(overlay.get("request") or {})
    affects_core_score = bool(overlay.get("affects_core_score", False))
    show_in_report = bool(overlay.get("show_in_report", True))

    entries = []
    for item in overlay.get("entries") or []:
        row = {k: _clean_value(v) for k, v in (item or {}).items()}
        symbol = str(row.get("symbol") or "").upper()
        as_of = str(row.get("as_of") or "")
        if not symbol or not as_of:
            continue
        row["symbol"] = symbol
        row["as_of"] = as_of
        entries.append(row)
    entries = sorted(entries, key=lambda x: (x["as_of"], x["symbol"]))

    dashboard_entries = rows_for_dashboard(entries)
    by_key = {f'{row["symbol"]}|{row["as_of"]}': row for row in dashboard_entries}
    latest_week = weeks[-1] if weeks else None
    summary = overlay_summary(entries, latest_week)
    latest_entries = [row for row in dashboard_entries if row.get("as_of") == latest_week] if latest_week else []

    if not requested:
        status = {
            "state": "disabled",
            "message": "Sentiment overlay was not requested for this report.",
            "hint": "Enable with --with-sentiment or configure sentiment_overlay.enabled=true.",
        }
    elif error:
        status = {
            "state": "error",
            "message": f"Sentiment overlay failed: {error}",
            "hint": "The report kept running; inspect the sentiment artifact for the error and rerun with --refresh if needed.",
        }
    elif entries:
        status = {
            "state": "ok",
            "message": "Sentiment overlay loaded.",
            "hint": "Sentiment is informational only and does not alter the 4-pillar fundamentals score.",
        }
    else:
        status = {
            "state": "partial",
            "message": "Sentiment overlay was requested but no supported pair/date entries were available.",
            "hint": "Unsupported instruments are skipped and missing sources are marked unavailable per signal.",
        }

    return {
        "requested": requested,
        "enabled": bool(entries),
        "affects_core_score": affects_core_score,
        "show_in_report": show_in_report,
        "entries": dashboard_entries,
        "latest_entries": latest_entries,
        "by_key": by_key,
        "request": request,
        "error": None if error is None else str(error),
        "summary": _clean_value(summary),
        "status": status,
    }


def _merge_sentiment_panel(panel: pd.DataFrame, sentiment_overlay: Optional[dict]) -> pd.DataFrame:
    x = panel.copy()
    defaults = {
        "sentiment_bias": None,
        "sentiment_score": None,
        "sentiment_conviction": None,
        "sentiment_agrees_with_macro": None,
        "sentiment_stale": None,
        "sentiment_summary": None,
    }
    for col, value in defaults.items():
        if col not in x.columns:
            x[col] = value

    overlay = sentiment_overlay or {}
    entries = sorted(overlay.get("entries") or [], key=lambda r: (str((r or {}).get("as_of") or ""), str((r or {}).get("symbol") or "")))
    by_key = {}
    for entry in entries:
        symbol = str((entry or {}).get("symbol") or "").upper()
        as_of = str((entry or {}).get("as_of") or "")
        if symbol and as_of:
            by_key[f"{symbol}|{as_of}"] = entry

    if x.empty:
        return x

    for idx, row in x.iterrows():
        key = f'{str(row.get("pair") or "").upper()}|{str(row.get("as_of") or "")}'
        entry = by_key.get(key)
        if not entry:
            continue
        x.at[idx, "sentiment_bias"] = entry.get("sentiment_bias")
        x.at[idx, "sentiment_score"] = entry.get("sentiment_score")
        x.at[idx, "sentiment_conviction"] = entry.get("sentiment_conviction")
        x.at[idx, "sentiment_agrees_with_macro"] = entry.get("agreement_with_macro")
        x.at[idx, "sentiment_stale"] = entry.get("sentiment_stale")
        x.at[idx, "sentiment_summary"] = entry.get("headline_summary")
    return x.sort_values(["as_of", "pair"], kind="mergesort").reset_index(drop=True)


def _overview_kpis(panel: pd.DataFrame, latest_week: Optional[str]) -> dict:
    if panel.empty or not latest_week:
        return {
            "pairs_tracked": 0,
            "macro_bullish": 0,
            "macro_bearish": 0,
            "macro_neutral": 0,
            "sentiment_coverage": 0,
            "sentiment_agreement_rate": None,
        }

    latest = panel[panel["as_of"].astype(str) == str(latest_week)].copy()
    bias_col = "final_bias" if "final_bias" in latest.columns else "bias"
    macro_bullish = int((latest[bias_col].astype(str) == "BULL_BASE").sum()) if bias_col in latest.columns else 0
    macro_bearish = int((latest[bias_col].astype(str) == "BEAR_BASE").sum()) if bias_col in latest.columns else 0
    macro_neutral = int((latest[bias_col].astype(str) == "NEUTRAL").sum()) if bias_col in latest.columns else 0

    coverage = int(latest["sentiment_bias"].notna().sum()) if "sentiment_bias" in latest.columns else 0
    agreement_rate = None
    if "sentiment_agrees_with_macro" in latest.columns:
        comparable = latest["sentiment_agrees_with_macro"].dropna()
        if not comparable.empty:
            agreement_rate = float(pd.to_numeric(comparable, errors="coerce").fillna(0).mean())

    return {
        "pairs_tracked": int(len(latest)),
        "macro_bullish": macro_bullish,
        "macro_bearish": macro_bearish,
        "macro_neutral": macro_neutral,
        "sentiment_coverage": coverage,
        "sentiment_agreement_rate": agreement_rate,
    }


def _data_quality_summary(panel: pd.DataFrame) -> dict:
    x = panel.copy()
    stale_counts = {
        "rates": int(pd.to_numeric(x.get("rates_stale"), errors="coerce").fillna(0).astype(int).sum())
        if "rates_stale" in x.columns
        else 0,
        "growth": int(pd.to_numeric(x.get("growth_stale"), errors="coerce").fillna(0).astype(int).sum())
        if "growth_stale" in x.columns
        else 0,
        "risk": int(pd.to_numeric(x.get("risk_stale"), errors="coerce").fillna(0).astype(int).sum())
        if "risk_stale" in x.columns
        else 0,
        "positioning": int(pd.to_numeric(x.get("pos_stale"), errors="coerce").fillna(0).astype(int).sum())
        if "pos_stale" in x.columns
        else 0,
    }

    overall_rate = float(pd.to_numeric(x.get("overall_staleness_flag"), errors="coerce").fillna(0).mean()) if "overall_staleness_flag" in x.columns else 0.0
    provider_counts = {
        "stooq": stale_counts["rates"] + stale_counts["growth"],
        "fred+stooq": stale_counts["risk"],
        "cftc": stale_counts["positioning"],
    }

    def _last_date(cols: Iterable[str]) -> Optional[str]:
        vals = []
        for c in cols:
            if c not in x.columns:
                continue
            s = pd.to_datetime(x[c], errors="coerce").dropna()
            if not s.empty:
                vals.append(s.max())
        if not vals:
            return None
        return max(vals).date().isoformat()

    provider_summary = [
        {
            "provider": "stooq",
            "stale_count": int(provider_counts["stooq"]),
            "last_updated": _last_date(["rates_obs_date", "growth_obs_date"]),
        },
        {
            "provider": "fred+stooq",
            "stale_count": int(provider_counts["fred+stooq"]),
            "last_updated": _last_date(["risk_obs_date"]),
        },
        {
            "provider": "cftc",
            "stale_count": int(provider_counts["cftc"]),
            "last_updated": _last_date(["pos_obs_date"]),
        },
    ]
    provider_summary = sorted(provider_summary, key=lambda r: (r["provider"]))
    most_stale = max(provider_summary, key=lambda r: r["stale_count"])["provider"] if provider_summary else None

    return {
        "overall_stale_rate": overall_rate,
        "stale_counts": stale_counts,
        "provider_summary": provider_summary,
        "most_stale_provider": most_stale,
    }


def _compare_payload(panel: pd.DataFrame, weeks: List[str], compare_dates: Optional[Tuple[str, str]] = None) -> dict:
    by_key = {}
    flip_counts = {}

    for i, a in enumerate(weeks):
        for b in weeks[i + 1 :]:
            cmp = build_compare_payload(panel=panel, as_of_a=a, as_of_b=b)
            key = f"{a}|{b}"
            by_key[key] = cmp["rows"]
            flip_counts[key] = cmp["flip_counts"]

    if compare_dates and f"{compare_dates[0]}|{compare_dates[1]}" in by_key:
        default_a, default_b = compare_dates
    elif len(weeks) >= 2:
        default_a, default_b = weeks[-2], weeks[-1]
    elif len(weeks) == 1:
        default_a = default_b = weeks[0]
    else:
        default_a = default_b = ""

    return {
        "default_a": default_a,
        "default_b": default_b,
        "by_key": by_key,
        "flip_counts": flip_counts,
    }


def _latest_rows_html(panel: pd.DataFrame, latest_week: str, score_col: str) -> str:
    if panel.empty or "as_of" not in panel.columns or "pair" not in panel.columns:
        return ""
    x = panel[panel["as_of"] == latest_week].copy()
    if score_col not in x.columns:
        score_col = "total_score" if "total_score" in x.columns else "score"
    x = x.sort_values([score_col, "pair"], ascending=[False, True], kind="mergesort")

    def fmt(v) -> str:
        try:
            if pd.isna(v):
                return "NA"
            return f"{float(v):+.2f}"
        except Exception:
            return "NA"

    def pill(bias: object) -> str:
        b = str(bias or "")
        if b == "BULL_BASE":
            return '<span class="pill bull">BULL_BASE</span>'
        if b == "BEAR_BASE":
            return '<span class="pill bear">BEAR_BASE</span>'
        return '<span class="pill neut">NEUTRAL</span>'

    out = []
    for _, r in x.iterrows():
        pair = str(r.get("pair", "")).upper()
        week = str(r.get("as_of", ""))
        rid = f"row-{pair}-{week.replace('-', '')}"
        out.append(
            "<tr "
            f'id="{rid}" class="row-click" data-pair="{pair}" data-week="{week}">'
            f"<td>{pair}</td>"
            f"<td>{fmt(r.get('rates'))}</td>"
            f"<td>{fmt(r.get('growth'))}</td>"
            f"<td>{fmt(r.get('risk'))}</td>"
            f"<td>{fmt(r.get('positioning'))}</td>"
            f"<td>{fmt(r.get(score_col))}</td>"
            f"<td>{str(r.get('conviction_tier') or 'NA')}</td>"
            f"<td>{pill(r.get('final_bias') or r.get('bias'))}</td>"
            f"<td>{'STALE' if bool(r.get('overall_staleness_flag')) else ''}</td>"
            "</tr>"
        )
    return "\n".join(out)


def build_dashboard_payload(
    panel: pd.DataFrame,
    weeks: List[str],
    meta_by_week: Dict[str, dict],
    market_overlay: Optional[dict] = None,
    sentiment_overlay: Optional[dict] = None,
    compare_dates: Optional[Tuple[str, str]] = None,
    generated_utc: Optional[str] = None,
    report_notes: Optional[dict] = None,
) -> dict:
    x = panel.copy()
    x["pair"] = x["pair"].astype(str).str.upper()
    x["as_of"] = x["as_of"].astype(str)
    x = x.sort_values(["as_of", "pair"], kind="mergesort").reset_index(drop=True)

    score_col = "total_score" if "total_score" in x.columns else "score"
    bias_col = "final_bias" if "final_bias" in x.columns else "bias"
    if "bias_num" not in x.columns:
        x["bias_num"] = x[bias_col].map(_bias_to_num)

    pairs = sorted(x["pair"].dropna().astype(str).unique().tolist())
    weeks_sorted = sorted(weeks)
    generated_value = generated_utc
    if generated_value is None:
        generated_value = f"{weeks_sorted[-1]} 00:00 UTC" if weeks_sorted else "NA"

    bias_heat = x.pivot(index="pair", columns="as_of", values="bias_num").reindex(index=pairs, columns=weeks_sorted)
    score_heat = x.pivot(index="pair", columns="as_of", values=score_col).reindex(index=pairs, columns=weeks_sorted)
    conv_source = "conviction_abs" if "conviction_abs" in x.columns else score_col
    conviction_heat = x.pivot(index="pair", columns="as_of", values=conv_source).reindex(index=pairs, columns=weeks_sorted)
    if conv_source != "conviction_abs":
        conviction_heat = conviction_heat.abs()

    counts = (
        x.groupby(["as_of", bias_col], sort=True).size().reset_index(name="n").pivot(index="as_of", columns=bias_col, values="n").fillna(0)
    )
    counts = counts.reindex(index=weeks_sorted, fill_value=0)

    base_cols = [
        "as_of",
        "pair",
        "base",
        "quote",
        "rates",
        "growth",
        "risk",
        "positioning",
        "rates_raw",
        "growth_raw",
        "risk_raw",
        "positioning_raw",
        "total_score",
        "score",
        "conviction_tier",
        "conviction_abs",
        "final_bias",
        "bias",
        "rates_obs_date",
        "growth_obs_date",
        "risk_obs_date",
        "pos_obs_date",
        "rates_age_days",
        "growth_age_days",
        "risk_age_days",
        "pos_age_days",
        "rates_stale",
        "growth_stale",
        "risk_stale",
        "pos_stale",
        "overall_staleness_flag",
        "sentiment_bias",
        "sentiment_score",
        "sentiment_conviction",
        "sentiment_agrees_with_macro",
        "sentiment_stale",
        "sentiment_summary",
        "_pillar_meta",
    ]
    present_base = [c for c in base_cols if c in x.columns]
    extra_cols = sorted(c for c in x.columns if c not in present_base)
    row_cols = present_base + extra_cols

    rows = [{k: _clean_value(r[k]) for k in row_cols} for _, r in x[row_cols].iterrows()]

    payload = {
        "generated_utc": generated_value,
        "weeks": weeks_sorted,
        "latest_week": weeks_sorted[-1] if weeks_sorted else None,
        "pairs": pairs,
        "score_col": score_col,
        "heatmaps": {
            "bias": [[None if pd.isna(v) else int(v) for v in row] for row in bias_heat.values.tolist()],
            "score": [[None if pd.isna(v) else float(v) for v in row] for row in score_heat.values.tolist()],
            "conviction": [[None if pd.isna(v) else float(v) for v in row] for row in conviction_heat.values.tolist()],
        },
        "counts": {
            "index": counts.index.astype(str).tolist(),
            "columns": [str(c) for c in counts.columns.tolist()],
            "values": [[int(v) for v in row] for row in counts.values.tolist()],
        },
        "rows": rows,
        "meta_by_week": {k: _clean_value(meta_by_week[k]) for k in sorted(meta_by_week.keys())},
        "data_quality": _data_quality_summary(x),
        "overview_kpis": _overview_kpis(x, weeks_sorted[-1] if weeks_sorted else None),
        "market_overlay": _normalize_overlay(market_overlay, weeks_sorted),
        "sentiment_overlay": _normalize_sentiment_overlay(sentiment_overlay, weeks_sorted),
        "report_notes": _clean_value(report_notes or {"instrument_notes": {}}),
        "compare": _compare_payload(x, weeks_sorted, compare_dates=compare_dates),
        "methods": {
            "scoring": [
                "4 pillars (rates, growth, risk, positioning) are scored in [-1, +1].",
                "Composite score uses configured weights with auto-renormalization when a pillar is missing.",
                "Bias is mapped using threshold bands; conviction tiers map from absolute composite score.",
            ],
            "quality": [
                "Each pillar carries obs_date, age_days, and stale flags using configured thresholds.",
                "overall_staleness_flag is true when any weighted pillar is stale.",
                "Provider freshness summary tracks stale counts and last updated timestamps.",
            ],
            "overlay": [
                "Options skew overlay (rr10/rr25/ATM IV) is informational only.",
                "Overlay never modifies fundamentals pillar scores or final_bias.",
                "BULLISH if rr10 >= +0.40, BEARISH if rr10 <= -0.40, else NEUTRAL.",
            ],
            "sentiment": [
                "Sentiment overlay is deterministic, instrument-aware, and fully separate from the 4-pillar macro score.",
                "Per-family weighted signals are renormalized across available sources when some inputs are unavailable.",
                "agreement_with_macro is null when either side is neutral; otherwise it flags directional alignment only.",
            ],
        },
    }
    return payload


def _make_html_dashboard(out_html: Path, payload: dict) -> None:
    latest_rows_html = _latest_rows_html(
        panel=pd.DataFrame(payload.get("rows") or []),
        latest_week=str(payload.get("latest_week") or ""),
        score_col=str(payload.get("score_col") or "total_score"),
    )
    html = render_dashboard_html(payload=payload, latest_rows_html=latest_rows_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")


def _make_pdf_dashboard(out_pdf: Path, weeks: List[str], panel: pd.DataFrame) -> None:
    import io

    import matplotlib.pyplot as plt
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    if panel.empty:
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(out_pdf), pagesize=letter)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, 760, "FX Macro Bias Dashboard")
        c.setFont("Helvetica", 10)
        c.drawString(40, 740, "No rows available for the requested date range.")
        c.save()
        return

    latest = weeks[-1]
    score_col = "total_score" if "total_score" in panel.columns else "score"
    bias_col = "final_bias" if "final_bias" in panel.columns else "bias"
    latest_df = panel[panel["as_of"] == latest].copy().sort_values(score_col, ascending=False)

    buf1 = io.BytesIO()
    plt.figure(figsize=(7.0, 3.2))
    plt.hist(pd.to_numeric(latest_df[score_col], errors="coerce").dropna().values, bins=20)
    plt.title(f"Score Distribution - {latest}")
    plt.xlabel("score")
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(buf1, format="png", dpi=150)
    plt.close()
    buf1.seek(0)

    buf2 = io.BytesIO()
    counts = panel.groupby(["as_of", bias_col]).size().reset_index(name="n").pivot(index="as_of", columns=bias_col, values="n").fillna(0)
    counts = counts.reindex(weeks).fillna(0)
    plt.figure(figsize=(7.0, 3.2))
    for c in counts.columns:
        plt.plot(counts.index, counts[c], marker="o", label=str(c))
    plt.title("Bias Counts Over Time")
    plt.xlabel("as_of")
    plt.ylabel("pairs")
    plt.xticks(rotation=20, ha="right")
    plt.legend()
    plt.tight_layout()
    plt.savefig(buf2, format="png", dpi=150)
    plt.close()
    buf2.seek(0)

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_pdf), pagesize=letter)
    w, h = letter
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, h - 48, "FX Macro Bias Dashboard")
    c.setFont("Helvetica", 10)
    c.drawString(40, h - 65, f"Weeks: {weeks[0]} to {weeks[-1]}")
    c.line(40, h - 74, w - 40, h - 74)

    c.drawImage(ImageReader(buf1), 40, h - 330, width=w - 80, height=220, preserveAspectRatio=True, mask="auto")
    c.drawImage(ImageReader(buf2), 40, h - 565, width=w - 80, height=220, preserveAspectRatio=True, mask="auto")
    c.showPage()

    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, h - 50, f"Latest Week Leaderboard ({latest})")
    c.setFont("Helvetica", 9)
    cols = ["pair", "rates", "growth", "risk", "positioning", "score", "conv", "bias"]
    xpos = [40, 115, 170, 225, 280, 360, 415, 470]
    y = h - 80
    for i, col in enumerate(cols):
        c.drawString(xpos[i], y, col)
    y -= 12
    c.line(40, y + 6, w - 40, y + 6)

    def fmt(v):
        try:
            if pd.isna(v):
                return "NA"
            return f"{float(v):+.2f}"
        except Exception:
            return "NA"

    for _, r in latest_df.head(40).iterrows():
        row = [
            r.get("pair"),
            fmt(r.get("rates")),
            fmt(r.get("growth")),
            fmt(r.get("risk")),
            fmt(r.get("positioning")),
            fmt(r.get(score_col)),
            r.get("conviction_tier"),
            r.get(bias_col),
        ]
        for i, val in enumerate(row):
            c.drawString(xpos[i], y, str(val))
        y -= 12
        if y < 60:
            c.showPage()
            y = h - 60
    c.save()


def build_weekly_report(
    cfg: dict,
    pairs: List[str],
    weeks: int = 4,
    end_date: Optional[str] = None,
    outdir: str = "out",
    refresh: bool = False,
    formats: Tuple[str, ...] = ("html", "pdf"),
    asof: Optional[str] = None,
    compare_dates: Optional[Tuple[str, str]] = None,
    market_overlay: Optional[dict] = None,
    sentiment_requested: bool = False,
    report_notes: Optional[dict] = None,
) -> Dict[str, str]:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    pair_list = sorted({str(p).upper() for p in pairs})
    asofs = _weekly_asof_dates(weeks=weeks, end_date=end_date, asof=asof)

    engine = MacroBiasEngine(cfg, refresh=refresh)
    engine.prepare_history(pairs=pair_list, asofs=asofs)

    frames = []
    meta_by_week = {}
    for d in asofs:
        df, meta = engine.run(pairs=pair_list, asof=d)
        x = df.copy()
        x["as_of"] = d
        bcol = "final_bias" if "final_bias" in x.columns else "bias"
        x["bias_num"] = x[bcol].map(_bias_to_num)
        x = x.sort_values(["pair"], kind="mergesort")
        frames.append(x)
        meta_by_week[d] = meta

    panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not panel.empty:
        panel = panel.sort_values(["as_of", "pair"], kind="mergesort").reset_index(drop=True)
    sentiment_overlay = build_sentiment_overlay(
        engine=engine,
        pairs=pair_list,
        asofs=asofs,
        panel=panel,
        requested=bool(sentiment_requested),
    )
    panel = _merge_sentiment_panel(panel, sentiment_overlay)
    payload = build_dashboard_payload(
        panel=panel,
        weeks=asofs,
        meta_by_week=meta_by_week,
        market_overlay=market_overlay,
        sentiment_overlay=sentiment_overlay,
        compare_dates=compare_dates,
        report_notes=report_notes,
    )

    stamp = asofs[-1].replace("-", "") if asofs else _dt.datetime.utcnow().strftime("%Y%m%d")
    outputs: Dict[str, str] = {}

    if "html" in formats:
        out_html = out / f"weekly_dashboard_{stamp}.html"
        _make_html_dashboard(out_html=out_html, payload=payload)
        outputs["html"] = str(out_html)

    if "pdf" in formats:
        out_pdf = out / f"weekly_dashboard_{stamp}.pdf"
        _make_pdf_dashboard(out_pdf=out_pdf, weeks=asofs, panel=panel)
        outputs["pdf"] = str(out_pdf)

    out_csv = out / f"weekly_panel_{stamp}.csv"
    csv_panel = panel.copy()
    if "_pillar_meta" in csv_panel.columns:
        csv_panel["_pillar_meta"] = csv_panel["_pillar_meta"].map(lambda x: json.dumps(_clean_value(x), sort_keys=True))
    csv_panel.to_csv(out_csv, index=False)
    outputs["csv"] = str(out_csv)
    outputs["panel.csv"] = str(out_csv)

    out_json = out / f"weekly_panel_{stamp}.json"
    panel_payload = {
        "generated_utc": payload.get("generated_utc"),
        "weeks": asofs,
        "rows": [{k: _clean_value(v) for k, v in row.items()} for row in panel.to_dict(orient="records")],
        "meta_by_week": {k: _clean_value(v) for k, v in sorted(meta_by_week.items())},
    }
    out_json.write_text(json.dumps(panel_payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    outputs["json"] = str(out_json)
    outputs["panel.json"] = str(out_json)

    if market_overlay and bool((market_overlay or {}).get("requested")):
        out_opt = out / f"options_overlay_{stamp}.json"
        out_opt.write_text(json.dumps(_clean_value(market_overlay), indent=2, sort_keys=True, default=str), encoding="utf-8")
        outputs["options.json"] = str(out_opt)

    if sentiment_overlay and bool((sentiment_overlay or {}).get("requested")):
        out_sent = out / f"sentiment_overlay_{stamp}.json"
        out_sent.write_text(json.dumps(_clean_value(sentiment_overlay), indent=2, sort_keys=True, default=str), encoding="utf-8")
        outputs["sentiment.json"] = str(out_sent)

    return outputs
