from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import yaml
from rich.console import Console
from rich.table import Table

from .config import load_config
from .engine import MacroBiasEngine
from .providers.investing_options import compute_skew_metrics, fetch_options_surface
from .reporting import _weekly_asof_dates, build_weekly_report


def _parse_compare_dates(s: Optional[str]) -> Optional[Tuple[str, str]]:
    if not s:
        return None
    parts = [x.strip() for x in str(s).split(",") if x.strip()]
    if len(parts) != 2:
        raise ValueError("--compare must be in format YYYY-MM-DD,YYYY-MM-DD")
    # validate ISO date format early
    dt.date.fromisoformat(parts[0])
    dt.date.fromisoformat(parts[1])
    return parts[0], parts[1]


def _resolve_report_weeks(*, weeks: Optional[int], months: Optional[int], asof: Optional[str]) -> int:
    if asof:
        return 1
    if months is not None:
        if int(months) < 1:
            raise ValueError("--months must be >= 1")
        # Convert a monthly lookback into an approximate count of weekly report dates.
        return max(1, int(round(float(months) * 52.0 / 12.0)))
    resolved_weeks = 4 if weeks is None else int(weeks)
    if resolved_weeks < 1:
        raise ValueError("--weeks must be >= 1")
    return resolved_weeks


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(out.get(key), dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_sentiment_overlay_override(path: Optional[str]) -> dict:
    if not path:
        return {}
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("--sentiment-config must point to a YAML mapping")
    if "sentiment_overlay" in raw and isinstance(raw.get("sentiment_overlay"), dict):
        return dict(raw["sentiment_overlay"])
    return dict(raw)


def _make_options_overlay(
    *,
    provider: str,
    requested: bool,
    symbol: str,
    as_of: str,
    url: Optional[str],
    tenor: str,
    headless: bool,
    refresh: bool,
) -> dict:
    request = {
        "provider": str(provider or "investing"),
        "symbol": str(symbol or "XAUUSD").upper(),
        "tenor": str(tenor or "1M"),
        "url": str(url or ""),
        "as_of": str(as_of or ""),
    }
    payload = {
        "requested": bool(requested),
        "entries": [],
        "error": None,
        "request": request,
    }

    if not payload["requested"]:
        return payload
    if not url:
        payload["error"] = "No options URL resolved. Use --options-url or set FXBIAS_OPTIONS_URL."
        return payload

    try:
        surface = fetch_options_surface(url=url, tenor=request["tenor"], headless=headless, refresh=refresh)
        if surface.empty:
            payload["error"] = "Options overlay fetch returned no rows."
            return payload

        sym = request["symbol"]
        if "symbol" in surface.columns:
            surface["symbol"] = sym
        metrics = compute_skew_metrics(surface)
        metrics["symbol"] = sym
        metrics["as_of"] = request["as_of"]
        metrics["source_url"] = url
        payload["entries"] = [metrics]
        return payload
    except Exception as exc:
        payload["error"] = str(exc)
        return payload


def _write_options_snapshot_artifacts(symbol: str, out_dir: Path, surface: pd.DataFrame, summary: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M")
    sym = symbol.upper()

    parquet_path = out_dir / f"{sym}_options_surface_{stamp}.parquet"
    json_path = out_dir / f"{sym}_options_summary_{stamp}.json"
    html_path = out_dir / f"{sym}_options_snapshot_{stamp}.html"

    try:
        surface.to_parquet(parquet_path, index=False)
    except Exception as exc:
        raise RuntimeError("pyarrow is required for parquet output. Install with: pip install pyarrow") from exc
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8")

    tbl = surface.to_html(index=False, border=0, classes="tbl")
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{sym} Options Snapshot</title>
  <style>
    body {{ font-family: "IBM Plex Sans", "Segoe UI", sans-serif; margin: 24px; color: #0f1f33; }}
    .card {{ border: 1px solid #cad8e8; border-radius: 12px; padding: 14px; margin-bottom: 14px; }}
    .pill {{ display: inline-block; border: 1px solid #9ab3cf; border-radius: 999px; padding: 2px 8px; font-weight: 700; }}
    .tbl {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
    .tbl th, .tbl td {{ border-bottom: 1px solid #e5edf4; text-align: right; padding: 6px; }}
    .tbl th:first-child, .tbl td:first-child {{ text-align: left; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>{sym} Options Snapshot</h2>
    <div><span class="pill">{summary.get("label", "NEUTRAL")}</span></div>
    <p>rr10={summary.get("rr10")} | rr25={summary.get("rr25")} | approx_atm_iv={summary.get("approx_atm_iv")} | expiry={summary.get("expiry_date")}</p>
  </div>
  <div class="card">{tbl}</div>
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")

    return {"parquet": str(parquet_path), "json": str(json_path), "html": str(html_path)}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fxbias", description="FX Macro Bias Engine (4 pillars)")
    p.add_argument("--config", default="config/default.yaml", help="Path to YAML config")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Compute macro bias for pairs")
    run.add_argument("--pairs", nargs="*", help="Override pairs list (e.g., EURUSD GBPUSD XAUUSD)")
    run.add_argument("--format", choices=["table", "json"], default="table")
    run.add_argument("--out", default=None, help="Write output to a file (json only recommended)")
    run.add_argument("--asof", default=None, help="As-of date YYYY-MM-DD (default: latest available)")
    run.add_argument("--refresh", action="store_true", help="Ignore cache and refetch")

    report = sub.add_parser("report", help="Generate weekly dashboards (HTML/PDF)")
    report.add_argument("--pairs", nargs="*", help="Override pairs list")
    report.add_argument("--weeks", type=int, default=None, help="How many weeks back (default: 4)")
    report.add_argument("--months", type=int, default=None, help="Approximate monthly lookback, converted to weekly report dates (e.g. 3 -> about 13 weeks)")
    report.add_argument("--asof", default=None, help="Single as-of date YYYY-MM-DD (overrides --weeks)")
    report.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today, aligned to last Friday)")
    report.add_argument("--compare", default=None, help="Compare dates A,B (e.g. 2026-02-13,2026-02-20)")
    report.add_argument("--with-options", action="store_true", help="Enable Investing.com options skew overlay")
    report.add_argument("--with-sentiment", action="store_true", help="Enable deterministic sentiment overlay")
    report.add_argument("--sentiment-only", action="store_true", help="Enable sentiment overlay and suppress options overlay")
    report.add_argument("--sentiment-config", default=None, help="Optional YAML override for sentiment_overlay settings")
    report.add_argument("--options-url", default=None, help="Investing options page URL")
    report.add_argument("--options-symbol", default=None, help="Overlay symbol label (defaults to config)")
    report.add_argument("--options-tenor", default=None, help="Overlay tenor label (defaults to config)")
    report.add_argument("--no-headless", action="store_true", help="Disable headless browser for options fetch")
    report.add_argument("--outdir", default="out", help="Output directory")
    report.add_argument("--format", choices=["html", "pdf", "both"], default="both")
    report.add_argument("--refresh", action="store_true", help="Ignore cache and refetch")

    opt = sub.add_parser("options-snapshot", help="Capture a market overlay options snapshot")
    opt.add_argument("--symbol", required=True, help="Symbol label, e.g. XAUUSD")
    opt.add_argument("--tenor", default="1M", help="Tenor label (default: 1M)")
    opt.add_argument("--url", required=True, help="Investing options URL")
    opt.add_argument("--out", default="out", help="Output directory")
    opt.add_argument("--no-headless", action="store_true", help="Disable headless browser")
    opt.add_argument("--refresh", action="store_true", help="Ignore cache and refetch")

    dbg = sub.add_parser("debug-pair", help="Debug one pair across weekly as-of dates with pillar raw/score values")
    dbg.add_argument("--pair", required=True, help="FX pair, e.g. EURUSD")
    dbg.add_argument("--weeks", type=int, default=8, help="How many weeks back (default: 8)")
    dbg.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today aligned to Friday)")
    dbg.add_argument("--no-provenance", action="store_true", help="Suppress provenance table")

    cal = sub.add_parser("calibrate-conviction", help="Compute conviction distribution and suggest thresholds")
    cal.add_argument("--pairs", nargs="*", help="Override pairs list")
    cal.add_argument("--weeks", type=int, default=52, help="How many weeks back (default: 52)")
    cal.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today aligned to Friday)")
    cal.add_argument("--format", choices=["table", "json"], default="table")
    cal.add_argument("--out", default=None, help="Write output to a file (json only recommended)")

    return p


def main():
    args = _build_parser().parse_args()
    cfg = load_config(args.config)

    if args.cmd == "run":
        pairs = args.pairs or cfg["pairs"]
        engine = MacroBiasEngine(cfg, refresh=args.refresh)
        df, meta = engine.run(pairs=pairs, asof=args.asof)

        if args.format == "json":
            payload = {"meta": meta, "rows": df.to_dict(orient="records")}
            s = json.dumps(payload, indent=2, default=str)
            if args.out:
                outp = Path(args.out)
                outp.parent.mkdir(parents=True, exist_ok=True)
                outp.write_text(s, encoding="utf-8")
            else:
                print(s)
            return

        console = Console(width=220)
        table = Table(title=f"FX Macro Bias (as_of={meta.get('as_of')})")
        for col in ["pair", "rates", "growth", "risk", "positioning", "score", "conviction", "bias"]:
            table.add_column(col, justify="right" if col not in ("pair", "bias") else "left")
        for _, r in df.iterrows():
            table.add_row(
                r["pair"],
                f'{float(r["rates"]):+.2f}' if r["rates"] is not None and str(r["rates"]) != "nan" else "NA",
                f'{float(r["growth"]):+.2f}' if r["growth"] is not None and str(r["growth"]) != "nan" else "NA",
                f'{float(r["risk"]):+.2f}' if r["risk"] is not None and str(r["risk"]) != "nan" else "NA",
                f'{float(r["positioning"]):+.2f}' if r["positioning"] is not None and str(r["positioning"]) != "nan" else "NA",
                f'{float(r.get("total_score", r.get("score", 0.0))):+.2f}',
                str(r.get("conviction_tier", "")),
                str(r.get("final_bias", r.get("bias", ""))),
            )
        console.print(table)
        console.print("[dim]Notes: weights auto-renormalize when a pillar is missing for a pair.[/dim]")
        return

    if args.cmd == "report":
        try:
            sentiment_override = _load_sentiment_overlay_override(args.sentiment_config)
        except ValueError as exc:
            raise SystemExit(str(exc))
        except FileNotFoundError as exc:
            raise SystemExit(str(exc))
        if sentiment_override:
            cfg["sentiment_overlay"] = _deep_merge(cfg.get("sentiment_overlay", {}) or {}, sentiment_override)

        pairs = args.pairs or cfg["pairs"]
        formats = ("html", "pdf") if args.format == "both" else (args.format,)
        try:
            compare_dates = _parse_compare_dates(args.compare)
        except ValueError as exc:
            raise SystemExit(str(exc))
        try:
            report_weeks = _resolve_report_weeks(weeks=args.weeks, months=args.months, asof=args.asof)
        except ValueError as exc:
            raise SystemExit(str(exc))

        overlay_cfg = cfg.get("market_overlay", {}) or {}
        sentiment_cfg = cfg.get("sentiment_overlay", {}) or {}
        overlay_provider = str(overlay_cfg.get("provider") or "investing")
        overlay_env = str(overlay_cfg.get("url_env") or "FXBIAS_OPTIONS_URL")
        resolved_url = (
            args.options_url
            or os.getenv(overlay_env)
            or overlay_cfg.get("options_url")
        )
        sentiment_requested = bool(args.with_sentiment or args.sentiment_only or sentiment_cfg.get("enabled"))
        overlay_requested = bool((not args.sentiment_only) and (args.with_options or overlay_cfg.get("enabled") or resolved_url))
        overlay_symbol = str(args.options_symbol or overlay_cfg.get("default_symbol") or "XAUUSD").upper()
        overlay_tenor = str(args.options_tenor or overlay_cfg.get("default_tenor") or "1M")
        asofs = _weekly_asof_dates(weeks=report_weeks, end_date=args.end, asof=args.asof)
        overlay_asof = asofs[-1] if asofs else ""
        market_overlay = _make_options_overlay(
            provider=overlay_provider,
            requested=overlay_requested,
            symbol=overlay_symbol,
            as_of=overlay_asof,
            url=resolved_url,
            tenor=overlay_tenor,
            headless=(not args.no_headless),
            refresh=args.refresh,
        )

        outputs = build_weekly_report(
            cfg,
            pairs=pairs,
            weeks=report_weeks,
            end_date=args.end,
            outdir=args.outdir,
            refresh=args.refresh,
            formats=formats,
            asof=args.asof,
            compare_dates=compare_dates,
            market_overlay=market_overlay,
            sentiment_requested=sentiment_requested,
            report_notes=cfg.get("report_notes") or {},
        )

        console = Console()
        table = Table(title="Weekly Dashboard Outputs")
        table.add_column("type", style="bold")
        table.add_column("path")
        for k in sorted(outputs.keys()):
            table.add_row(k, outputs[k])
        console.print(table)
        return

    if args.cmd == "options-snapshot":
        try:
            surface = fetch_options_surface(
                url=args.url,
                tenor=args.tenor,
                headless=(not args.no_headless),
                refresh=args.refresh,
            )
        except RuntimeError as exc:
            raise SystemExit(str(exc))
        symbol = args.symbol.upper()
        if "symbol" in surface.columns:
            surface["symbol"] = symbol
        summary = compute_skew_metrics(surface)
        summary["symbol"] = symbol
        summary["source_url"] = args.url
        try:
            artifacts = _write_options_snapshot_artifacts(symbol=symbol, out_dir=Path(args.out), surface=surface, summary=summary)
        except RuntimeError as exc:
            raise SystemExit(str(exc))

        console = Console()
        table = Table(title=f"Options Snapshot ({symbol})")
        table.add_column("type", style="bold")
        table.add_column("path")
        for k in ("json", "parquet", "html"):
            table.add_row(k, artifacts[k])
        console.print(table)
        return

    if args.cmd == "debug-pair":
        engine = MacroBiasEngine(cfg, refresh=getattr(args, "refresh", False))
        df_debug, provenance = engine.debug_pair_series(pair=args.pair, weeks=args.weeks, end_date=args.end)

        console = Console(width=220)
        cols = [
            "asof",
            "rates_raw",
            "growth_raw",
            "risk_raw",
            "positioning_raw",
            "rates_score",
            "growth_score",
            "risk_score",
            "positioning_score",
            "total_score",
            "final_bias",
        ]

        def _num(v):
            try:
                import pandas as _pd

                if v is None or _pd.isna(v):
                    return None
                return float(v)
            except Exception:
                return None

        display_df = df_debug.copy()
        for c in cols:
            if c in ("asof", "final_bias"):
                continue
            if c in display_df.columns:
                display_df[c] = display_df[c].map(_num)
        console.print(f"Debug Pair: {args.pair.upper()} ({args.weeks} weeks)")
        with pd.option_context("display.width", 240, "display.max_columns", None):
            console.print(display_df[cols].to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

        if not args.no_provenance:
            ptable = Table(title="Pillar Provenance (obs_date / age_days / raw)")
            ptable.add_column("asof")
            for c in ["rates", "growth", "risk", "positioning"]:
                ptable.add_column(c)
            for row in provenance:

                def _pp(k):
                    x = row.get(k, {}) or {}
                    raw = x.get("raw")
                    try:
                        raw_s = f"{float(raw):+.4f}"
                    except Exception:
                        raw_s = "NA"
                    return f'{x.get("obs_date") or "NA"} / {x.get("age_days") if x.get("age_days") is not None else "NA"} / {raw_s}'

                ptable.add_row(str(row.get("asof")), _pp("rates"), _pp("growth"), _pp("risk"), _pp("positioning"))
            console.print(ptable)
        return

    if args.cmd == "calibrate-conviction":
        pairs = args.pairs or cfg["pairs"]
        engine = MacroBiasEngine(cfg, refresh=getattr(args, "refresh", False))
        out = engine.conviction_distribution(pairs=pairs, weeks=args.weeks, end_date=args.end)

        if args.format == "json":
            s = json.dumps(out, indent=2, default=str)
            if args.out:
                outp = Path(args.out)
                outp.parent.mkdir(parents=True, exist_ok=True)
                outp.write_text(s, encoding="utf-8")
            else:
                print(s)
            return

        console = Console(width=120)
        q = out.get("quantiles") or {}
        summ = out.get("summary") or {}
        rec = out.get("recommended") or {}
        bands = rec.get("bands") or {}

        t = Table(title=f"Conviction Calibration (weeks={out.get('weeks')}, pairs={out.get('pairs')}, n={out.get('n')})")
        t.add_column("metric", style="bold")
        t.add_column("value")
        for k in ["min", "max", "mean", "std"]:
            if k in summ:
                t.add_row(k, f"{float(summ[k]):.4f}")
        for k in ["q05", "q10", "q25", "q50", "q75", "q90", "q95"]:
            key = float(k[1:]) / 100.0
            if key in q:
                t.add_row(k, f"{float(q[key]):.4f}")
        console.print(t)

        t2 = Table(title="Recommended conviction thresholds (YAML snippet)")
        t2.add_column("key", style="bold")
        t2.add_column("value")
        if rec.get("neutral_threshold") is not None:
            t2.add_row("neutral_threshold", f"{float(rec['neutral_threshold']):.4f}")
        for k in ["weak", "moderate", "strong", "extreme"]:
            if k in bands:
                t2.add_row(f"bands.{k}", f"{float(bands[k]):.4f}")
        console.print(t2)
        return


if __name__ == "__main__":
    main()
