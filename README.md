# FX Macro Bias Engine (4 Pillars)

A command-line tool that produces a **directional macro bias** per pair (10+ FX pairs + Gold + Silver) by scoring:

1) **Interest-rate differentials** (2Y yield spread proxy)  
2) **Growth divergence** (proxy via relative equity performance)  
3) **Risk sentiment** (SPX/VIX/DXY regime)  
4) **Positioning (COT)** via CFTC Public Reporting (Socrata) datasets

## What you get
- Per-pair table: pillar scores + weighted final bias (`BULL_BASE`, `BEAR_BASE`, `NEUTRAL`)
- Conviction tier (`NONE`, `WEAK`, `MODERATE`, `STRONG`, `EXTREME`)
- Weekly report panel CSV with pillar obs dates / staleness flags
- A JSON output option for bots / pipelines
- Disk cache to avoid re-downloading

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -r requirements.txt

# Run defaults (12 FX pairs + XAUUSD + XAGUSD)
python -m fxbias run

# Custom list
python -m fxbias run --pairs EURUSD GBPUSD USDJPY XAUUSD XAGUSD

# JSON output
python -m fxbias run --format json --out out/bias.json

# Weekly as-of debug for one pair (raw values + scores + provenance)
python -m fxbias debug-pair --pair EURUSD --weeks 8 --end 2026-02-20
```

## Data sources (high level)
- Market data (prices, indices, bond yields): **Stooq CSV endpoints** (no key)  
- Positioning: **CFTC Public Reporting Environment (Socrata / SODA)**

Notes:
- Growth divergence defaults to a **proxy** (3M equity-index relative return).
- Hard growth mode (`CESI` + `PMI`) is supported via TradingEconomics API (optional).
- Some symbols may be missing for exotic countries; the engine degrades gracefully (score weight re-normalizes).
- COT positioning is release-aligned (Tuesday `report_date`, Friday `release_dt` eligibility).

## Config
Edit `config/default.yaml` to:
- change pairs list
- adjust weights
- override ticker mappings
- tune conviction bands / bias threshold / staleness thresholds
- enable hard growth mode (`growth.mode: hard`)

## Optional: hard growth mode (CESI + PMI)

The engine supports a configurable hard growth pillar blend using TradingEconomics historical indicators.

1. Set an API key:
   - Windows PowerShell: `$env:TRADINGECONOMICS_API_KEY="YOUR_KEY"`
2. In `config/default.yaml`, set:
   - `growth.mode: "hard"`

If the key is missing/unavailable, hard growth data will be missing and the engine will renormalize weights (or fall back to proxy if `growth.fallback_to_proxy: true`).

## Disclaimer
Educational / research tool. Not investment advice.


## Weekly dashboards (last 4 weeks)

```bash
python -m fxbias report --weeks 4 --format both --outdir out
```

This generates:
- `out/weekly_dashboard_YYYYMMDD.html` (interactive)
- `out/weekly_dashboard_YYYYMMDD.pdf` (print-ready)
- `out/weekly_panel_YYYYMMDD.csv` (audit)
