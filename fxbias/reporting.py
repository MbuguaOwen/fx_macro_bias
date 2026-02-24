import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict

import pandas as pd

from .engine import MacroBiasEngine


def _parse_date(s: str) -> _dt.date:
    return _dt.date.fromisoformat(s)

def _today_utc_date() -> _dt.date:
    return _dt.datetime.utcnow().date()

def _last_friday(d: _dt.date) -> _dt.date:
    # Friday = 4
    offset = (d.weekday() - 4) % 7
    return d - _dt.timedelta(days=offset)

def _weekly_asof_dates(weeks: int, end_date: Optional[str] = None) -> List[str]:
    end = _parse_date(end_date) if end_date else _today_utc_date()
    fri = _last_friday(end)
    dates = [fri - _dt.timedelta(days=7*i) for i in range(weeks)]
    dates = sorted(dates)  # oldest -> newest
    return [d.isoformat() for d in dates]

def _bias_to_num(b: str) -> int:
    if b in ("BULL_BASE", "LONG", "BULLISH"):
        return 1
    if b in ("BEAR_BASE", "SHORT", "BEARISH"):
        return -1
    return 0

def _make_html_dashboard(out_html: Path, weeks: List[str], panel: pd.DataFrame, meta_by_week: Dict[str, dict]) -> None:
    """Generate a single self-contained interactive HTML dashboard.

    Features
    - Overview heatmaps (bias / score / conviction)
    - Click-to-drill into a specific (pair, week)
    - Pair Explorer tab with dropdowns + time-series + provenance + risk component staleness

    Design goals
    - Deterministic output for a given input panel
    - No external assets except Plotly CDN
    """
    import html as _html
    import json as _json

    # Ensure deterministic ordering
    panel = panel.copy()
    panel["pair"] = panel["pair"].astype(str)
    panel["as_of"] = panel["as_of"].astype(str)
    panel = panel.sort_values(["pair", "as_of"]).reset_index(drop=True)

    # Pivot for heatmaps
    heat = panel.pivot(index="pair", columns="as_of", values="bias_num").reindex(columns=weeks)
    score_col = "total_score" if "total_score" in panel.columns else "score"
    score_heat = panel.pivot(index="pair", columns="as_of", values=score_col).reindex(columns=weeks)
    conviction_heat = panel.pivot(index="pair", columns="as_of", values="conviction_abs").reindex(columns=weeks) if "conviction_abs" in panel.columns else score_heat.abs()

    latest = weeks[-1]
    latest_df = (
        panel[panel["as_of"] == latest]
        .copy()
        .sort_values([score_col, "pair"], ascending=[False, True])
    )

    def _fmt_num(v):
        try:
            if v is None or pd.isna(v):
                return "NA"
            return f"{float(v):+.2f}"
        except Exception:
            return "NA"

    def _esc(v):
        try:
            if v is None or pd.isna(v):
                return ""
        except Exception:
            pass
        return _html.escape(str(v))

    def _pill_class(bias: object) -> str:
        if bias == "BULL_BASE":
            return "pill b"
        if bias == "BEAR_BASE":
            return "pill s"
        return "pill n"

    # Latest week leaderboard (clickable rows)
    latest_rows_html = []
    for _, r in latest_df.iterrows():
        bias = r.get("final_bias") or r.get("bias")
        conv = _esc(r.get("conviction_tier"))
        stale = bool(r.get("overall_staleness_flag")) if "overall_staleness_flag" in r else False
        pair = _esc(r.get("pair"))
        w = _esc(latest)
        latest_rows_html.append(
            f'<tr class="rowlink" data-pair="{pair}" data-week="{w}">'
            f'<td>{pair}</td>'
            f'<td>{_fmt_num(r.get("rates"))}</td>'
            f'<td>{_fmt_num(r.get("growth"))}</td>'
            f'<td>{_fmt_num(r.get("risk"))}</td>'
            f'<td>{_fmt_num(r.get("positioning"))}</td>'
            f'<td>{_fmt_num(r.get(score_col))}</td>'
            f'<td>{conv}</td>'
            f'<td><span class="{_pill_class(bias)}">{_esc(bias)}</span></td>'
            f'<td>{"STALE" if stale else ""}</td>'
            '</tr>'
        )
    latest_rows_html = "\n".join(latest_rows_html)

    # Bias counts over time
    counts = (
        panel.groupby(["as_of", "final_bias" if "final_bias" in panel.columns else "bias"])
        .size()
        .reset_index(name="n")
        .rename(columns={"final_bias": "bias"})
        .pivot(index="as_of", columns="bias", values="n")
        .fillna(0)
        .reindex(weeks)
    )

    def _safe(v):
        try:
            if pd.isna(v):
                return None
        except Exception:
            pass
        return v

    # Data quality summary
    stale_panel = panel.copy()
    if "overall_staleness_flag" in stale_panel.columns:
        stale_rate = float(stale_panel["overall_staleness_flag"].fillna(False).mean())
    else:
        stale_rate = 0.0
    stale_cols = [c for c in ["rates_stale", "growth_stale", "risk_stale", "pos_stale"] if c in stale_panel.columns]
    stale_counts = {c: int(stale_panel[c].fillna(False).sum()) for c in stale_cols}
    most_stale = max(stale_counts, key=stale_counts.get) if stale_counts else None

    # Minimal row payload for drilldown
    drill_cols = [
        "as_of",
        "pair",
        "rates",
        "growth",
        "risk",
        "positioning",
        score_col,
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
        "_pillar_meta",
    ]
    present_cols = [c for c in drill_cols if c in panel.columns]
    rows = panel[present_cols].to_dict(orient="records")

    payload = {
        "weeks": weeks,
        "pairs": heat.index.tolist(),
        "bias_heat": [[_safe(v) for v in row] for row in heat.values.tolist()],
        "score_heat": [[float(v) if _safe(v) is not None else None for v in row] for row in score_heat.values.tolist()],
        "conviction_heat": [[float(v) if _safe(v) is not None else None for v in row] for row in conviction_heat.values.tolist()],
        "counts": {
            "index": counts.index.tolist(),
            "columns": counts.columns.tolist(),
            "values": [[int(_safe(v) or 0) for v in row] for row in counts.values.tolist()],
        },
        "meta_by_week": meta_by_week,
        "data_quality": {
            "stale_rate": stale_rate,
            "most_stale_pillar": most_stale,
            "stale_counts": stale_counts,
        },
        "rows": rows,
        "score_col": score_col,
        "generated_utc": _dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }

    from string import Template as _Template

    payload_json = _json.dumps(payload, default=str)

    tmpl = _Template("""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>FX Macro Bias — Weekly Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
  <style>
    :root {
      --bg: #0b1020;
      --card: #111a33;
      --muted: #9aa4bf;
      --text: #e8ecff;
      --accent: #6ea8fe;
      --border: rgba(255,255,255,0.08);
      --good: rgba(110,168,254,0.16);
      --bad: rgba(255,77,109,0.14);
      --neu: rgba(200,200,200,0.08);
    }
    body { margin:0; background:var(--bg); color:var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
    }
    .wrap { max-width: 1280px; margin: 0 auto; padding: 22px; }
    .top { display:flex; align-items:center; justify-content:space-between; gap:12px;
      border-bottom:1px solid var(--border); padding-bottom:14px; margin-bottom:16px; }
    h1 { font-size:20px; margin:0; letter-spacing:0.2px; }
    .sub { color:var(--muted); font-size:13px; }
    .tabs { display:flex; gap:10px; margin: 14px 0; flex-wrap: wrap; }
    .tabbtn { cursor:pointer; border:1px solid var(--border); background:rgba(255,255,255,0.03);
      color:var(--text); padding:8px 12px; border-radius:999px; font-size:13px; }
    .tabbtn.active { border-color: rgba(110,168,254,0.55); background: rgba(110,168,254,0.12); }
    .grid { display:grid; grid-template-columns: 1fr; gap: 14px; }
    @media (min-width: 980px) { .grid2 { grid-template-columns: 1.3fr 0.7fr; } }
    .card { background:var(--card); border:1px solid var(--border); border-radius:16px; padding:14px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.30); }
    .card h2 { font-size:14px; margin:0 0 10px 0; color:#cdd6ff; }
    .muted { color:var(--muted); }
    .foot { margin-top: 10px; color:var(--muted); font-size: 12px; }
    .controls { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
    select, input { background: rgba(255,255,255,0.03); color: var(--text); border:1px solid var(--border);
      border-radius: 10px; padding: 8px 10px; font-size: 13px; outline: none; }
    .kpi { display:grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    @media (max-width: 980px) { .kpi { grid-template-columns: repeat(2, 1fr); } }
    .kcard { border:1px solid var(--border); border-radius:14px; padding:10px; background: rgba(255,255,255,0.02); }
    .klabel { font-size: 12px; color: var(--muted); }
    .kval { font-size: 16px; font-weight: 800; margin-top: 4px; }
    .pill { display:inline-block; padding: 2px 8px; border-radius: 999px; font-weight: 800;
      border: 1px solid var(--border); font-size: 12px; }
    .b{ background: var(--good); color:#bcd2ff; }
    .s{ background: var(--bad); color:#ffb3c2; }
    .n{ background: var(--neu); color:#d7ddf6; }
    .table { width:100%; border-collapse:collapse; font-size:12px; }
    .table th, .table td { border-bottom:1px solid var(--border); padding:8px 8px; text-align:right; white-space:nowrap; }
    .table th:first-child, .table td:first-child { text-align:left; }
    tr.rowlink:hover { background: rgba(110,168,254,0.06); }
    a { color: var(--accent); }
    .hidden { display:none; }
    .twoCol { display:grid; grid-template-columns: 1fr; gap: 14px; }
    @media (min-width: 980px) { .twoCol { grid-template-columns: 1fr 1fr; } }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; }
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <h1>FX Macro Bias — Weekly Dashboard</h1>
      <div class="sub">Weeks: $WEEK_START → $WEEK_END • Generated: $GENERATED</div>
    </div>
    <div class="sub">Interactive: click heatmap cells or leaderboard rows to drill into a pair/week</div>
  </div>

  <div class="tabs">
    <button class="tabbtn active" data-tab="overview">Overview</button>
    <button class="tabbtn" data-tab="pair">Pair Explorer</button>
    <button class="tabbtn" data-tab="quality">Data Quality</button>
    <button class="tabbtn" data-tab="meta">Report Meta</button>
  </div>

  <div id="tab-overview">
    <div class="grid grid2">
      <div class="card">
        <h2>Final Bias Heatmap (BULL / NEUTRAL / BEAR)</h2>
        <div id="bias_heat" style="height: 520px;"></div>
        <div class="foot">Click a cell to open Pair Explorer at that (pair, week).</div>
      </div>

      <div class="card">
        <h2>Bias Distribution Over Time</h2>
        <div id="counts" style="height: 260px;"></div>
        <h2 style="margin-top: 14px;">Score Heatmap</h2>
        <div id="score_heat" style="height: 170px;"></div>
        <h2 style="margin-top: 14px;">Conviction Heatmap</h2>
        <div id="conviction_heat" style="height: 150px;"></div>
      </div>
    </div>

    <div class="card" style="margin-top: 14px;">
      <h2>Latest Week Leaderboard ($LATEST)</h2>
      <table class="table">
        <thead>
          <tr>
            <th>Pair</th>
            <th>Rates</th>
            <th>Growth</th>
            <th>Risk</th>
            <th>Positioning</th>
            <th>Total</th>
            <th>Conviction</th>
            <th>Bias</th>
            <th>Quality</th>
          </tr>
        </thead>
        <tbody>
          $LATEST_ROWS
        </tbody>
      </table>
      <div class="foot">Rows are clickable → opens Pair Explorer.</div>
    </div>
  </div>

  <div id="tab-pair" class="hidden">
    <div class="card">
      <div class="controls">
        <div class="sub"><b>Selection</b></div>
        <select id="selPair"></select>
        <select id="selWeek"></select>
        <input id="pairSearch" placeholder="Search pair…" />
        <div class="sub" id="selHint"></div>
      </div>
    </div>

    <div class="card" style="margin-top:14px;">
      <h2>Snapshot</h2>
      <div class="kpi">
        <div class="kcard"><div class="klabel">Final Bias</div><div class="kval" id="kBias">—</div></div>
        <div class="kcard"><div class="klabel">Total Score</div><div class="kval" id="kScore">—</div></div>
        <div class="kcard"><div class="klabel">Conviction</div><div class="kval" id="kConv">—</div></div>
        <div class="kcard"><div class="klabel">Quality</div><div class="kval" id="kQual">—</div></div>
      </div>
      <div class="twoCol" style="margin-top:12px;">
        <div>
          <h2>Pillar Scores</h2>
          <table class="table" id="pillTbl"></table>
        </div>
        <div>
          <h2>Provenance</h2>
          <table class="table" id="provTbl"></table>
        </div>
      </div>
      <div class="foot" id="riskNote"></div>
    </div>

    <div class="grid grid2" style="margin-top:14px;">
      <div class="card">
        <h2>Total Score History (selected pair)</h2>
        <div id="pairScoreTs" style="height: 320px;"></div>
      </div>
      <div class="card">
        <h2>Bias History (selected pair)</h2>
        <div id="pairBiasTs" style="height: 320px;"></div>
      </div>
    </div>

    <div class="card" style="margin-top:14px;">
      <h2>Raw Meta (pair/week)</h2>
      <div class="mono" id="rawMeta"></div>
      <div class="foot">Structured per-pair pillar metadata (methods, report_date, risk components, etc.).</div>
    </div>
  </div>

  <div id="tab-quality" class="hidden">
    <div class="card">
      <h2>Quality Summary</h2>
      <div id="dqBox" class="sub"></div>
      <div class="foot">Recurring staleness should force the week into DEGRADED state (or downweight the pillar) rather than silently scoring.</div>
    </div>

    <div class="card" style="margin-top:14px;">
      <h2>Week-by-Week Risk Regime Provenance</h2>
      <table class="table" id="riskWeekTbl"></table>
      <div class="foot">Risk is computed from SPX/VIX/DXY — if DXY is stale, USD tilts should be disabled for that week.</div>
    </div>
  </div>

  <div id="tab-meta" class="hidden">
    <div class="card">
      <h2>Report Meta (by week)</h2>
      <div class="sub">Click a week row to copy the JSON meta block.</div>
      <table class="table" id="metaTbl"></table>
      <div class="foot">Meta includes weights, thresholds, and risk regime diagnostics.</div>
    </div>
  </div>

</div>

<script>
  const DATA = $PAYLOAD_JSON;
  const weeks = DATA.weeks;
  const pairs = DATA.pairs;

  function biasTextNum(v) { if (v === 1) return 'BULL'; if (v === -1) return 'BEAR'; return 'NEUTRAL'; }
  function pillHTML(bias) {
    if (bias === 'BULL_BASE') return '<span class="pill b">BULL_BASE</span>';
    if (bias === 'BEAR_BASE') return '<span class="pill s">BEAR_BASE</span>';
    return '<span class="pill n">NEUTRAL</span>';
  }
  function fmtNum(v, d=2) {
    if (v === null || v === undefined || v === '' || Number.isNaN(v)) return 'NA';
    const x = Number(v);
    if (Number.isNaN(x)) return 'NA';
    return (x >= 0 ? '+' : '') + x.toFixed(d);
  }

  const ROWS = DATA.rows || [];
  const rowKey = (pair, week) => pair + '|' + week;
  const IDX = new Map();
  for (const r of ROWS) {
    const p = String(r.pair || '').toUpperCase();
    const w = String(r.as_of || '');
    IDX.set(rowKey(p, w), r);
  }

  let selPair = pairs.length ? pairs[0] : '';
  let selWeek = weeks.length ? weeks[weeks.length - 1] : '';

  function setTab(name) {
    for (const el of document.querySelectorAll('.tabbtn')) el.classList.remove('active');
    for (const el of document.querySelectorAll('[id^="tab-"]')) el.classList.add('hidden');
    document.querySelector('.tabbtn[data-tab=' + name + ']').classList.add('active');
    document.getElementById('tab-' + name).classList.remove('hidden');
  }

  for (const btn of document.querySelectorAll('.tabbtn')) {
    btn.addEventListener('click', () => setTab(btn.dataset.tab));
  }

  const selPairEl = document.getElementById('selPair');
  const selWeekEl = document.getElementById('selWeek');
  const searchEl = document.getElementById('pairSearch');

  function populateControls() {
    selPairEl.innerHTML = '';
    for (const p of pairs) {
      const o = document.createElement('option');
      o.value = p; o.textContent = p;
      selPairEl.appendChild(o);
    }
    selWeekEl.innerHTML = '';
    for (const w of weeks) {
      const o = document.createElement('option');
      o.value = w; o.textContent = w;
      selWeekEl.appendChild(o);
    }
    selPairEl.value = selPair;
    selWeekEl.value = selWeek;
  }

  function updatePairExplorer() {
    selPair = String(selPairEl.value || selPair).toUpperCase();
    selWeek = String(selWeekEl.value || selWeek);

    const r = IDX.get(rowKey(selPair, selWeek));
    document.getElementById('selHint').textContent = r ? '' : 'No data found for this pair/week.';

    const bias = (r && (r.final_bias || r.bias)) || 'NEUTRAL';
    const score = r ? (r[DATA.score_col] ?? r.total_score ?? r.score) : null;
    const convTier = (r && r.conviction_tier) || '';
    const qual = (r && (r.overall_staleness_flag ? 'STALE' : 'OK')) || '—';

    document.getElementById('kBias').innerHTML = pillHTML(bias);
    document.getElementById('kScore').textContent = fmtNum(score, 3);
    document.getElementById('kConv').textContent = convTier || '—';
    document.getElementById('kQual').textContent = qual;

    const pillTbl = document.getElementById('pillTbl');
    pillTbl.innerHTML = '<thead><tr><th>Pillar</th><th>Score</th></tr></thead><tbody>' +
      ['rates','growth','risk','positioning'].map(k => {
        const v = r ? r[k] : null;
        return '<tr><td>' + k + '</td><td>' + fmtNum(v, 3) + '</td></tr>';
      }).join('') + '</tbody>';

    const provTbl = document.getElementById('provTbl');
    const provRows = ['rates','growth','risk','pos'].map(k => {
      const obs = r ? r[k + '_obs_date'] : null;
      const age = r ? r[k + '_age_days'] : null;
      const stale = r ? r[k + '_stale'] : null;
      return '<tr><td>' + k + '</td><td>' + (obs || 'NA') + '</td><td>' + (age ?? 'NA') + '</td><td>' + (stale ? 'YES' : '') + '</td></tr>';
    }).join('');
    provTbl.innerHTML = '<thead><tr><th>Pillar</th><th>obs_date</th><th>age_days</th><th>stale</th></tr></thead><tbody>' + provRows + '</tbody>';

    const wm = (DATA.meta_by_week || {})[selWeek] || {};
    const rr = wm.risk_regime || {};
    const staleParts = (rr.stale_components || []).join(', ');
    const rn = [];
    if (rr.obs_date) rn.push('risk_obs_date=' + rr.obs_date);
    if (rr.spx_obs_date) rn.push('spx=' + rr.spx_obs_date);
    if (rr.vix_obs_date) rn.push('vix=' + rr.vix_obs_date);
    if (rr.dxy_obs_date) rn.push('dxy=' + rr.dxy_obs_date);
    if (staleParts) rn.push('stale_components=[' + staleParts + ']');
    if (rr.warning) rn.push('warning=' + rr.warning);
    document.getElementById('riskNote').textContent = rn.length ? ('Risk regime: ' + rn.join(' • ')) : '';

    const raw = r ? (r._pillar_meta || {}) : {};
    const rm = { pair: selPair, as_of: selWeek, final_bias: bias, score: score, conviction_tier: convTier, pillar_meta: raw, week_risk_regime: rr };
    document.getElementById('rawMeta').textContent = JSON.stringify(rm, null, 2);

    const xs = weeks;
    const ysScore = xs.map(w => {
      const rrw = IDX.get(rowKey(selPair, w));
      const v = rrw ? (rrw[DATA.score_col] ?? rrw.total_score ?? rrw.score) : null;
      return v === undefined ? null : v;
    });

    Plotly.newPlot('pairScoreTs', [{
      type:'scatter', mode:'lines+markers', x: xs, y: ysScore,
      hovertemplate: '<b>' + selPair + '</b><br>%{x}<br>score=%{y:.3f}<extra></extra>'
    }], {
      margin:{l:40,r:10,t:10,b:40},
      paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
      font:{color:'#e8ecff'},
      xaxis:{gridcolor:'rgba(255,255,255,0.06)'},
      yaxis:{gridcolor:'rgba(255,255,255,0.06)'}
    }, {displayModeBar:false});

    const ysBias = xs.map(w => {
      const rrw = IDX.get(rowKey(selPair, w));
      const b = rrw ? (rrw.final_bias || rrw.bias) : 'NEUTRAL';
      if (b === 'BULL_BASE') return 1;
      if (b === 'BEAR_BASE') return -1;
      return 0;
    });

    Plotly.newPlot('pairBiasTs', [{
      type:'scatter', mode:'lines+markers', x: xs, y: ysBias,
      hovertemplate: '<b>' + selPair + '</b><br>%{x}<br>bias=%{y}<extra></extra>'
    }], {
      margin:{l:40,r:10,t:10,b:40},
      paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
      font:{color:'#e8ecff'},
      xaxis:{gridcolor:'rgba(255,255,255,0.06)'},
      yaxis:{gridcolor:'rgba(255,255,255,0.06)', tickvals:[-1,0,1], ticktext:['BEAR','NEUTRAL','BULL']}
    }, {displayModeBar:false});
  }

  function select(pair, week) {
    selPair = String(pair || selPair).toUpperCase();
    selWeek = String(week || selWeek);
    selPairEl.value = selPair;
    selWeekEl.value = selWeek;
    setTab('pair');
    updatePairExplorer();
  }

  Plotly.newPlot('bias_heat', [{
    type:'heatmap', x: weeks, y: pairs, z: DATA.bias_heat, zmin:-1, zmax:1,
    hovertemplate:'<b>%{y}</b><br>%{x}<br>Bias=%{z} (' + '%{customdata}' + ')<extra></extra>',
    customdata: DATA.bias_heat.map(r => r.map(v => biasTextNum(v)))
  }], {
    margin:{l:110,r:10,t:10,b:40},
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{color:'#e8ecff'},
    xaxis:{gridcolor:'rgba(255,255,255,0.06)'},
    yaxis:{gridcolor:'rgba(255,255,255,0.06)'}
  }, {displayModeBar:false}).then(gd => {
    gd.on('plotly_click', ev => {
      const p = ev.points[0].y;
      const w = ev.points[0].x;
      select(p, w);
    });
  });

  Plotly.newPlot('score_heat', [{
    type:'heatmap', x: weeks, y: pairs, z: DATA.score_heat,
    hovertemplate:'<b>%{y}</b><br>%{x}<br>Score=%{z:.3f}<extra></extra>'
  }], {
    margin:{l:110,r:10,t:10,b:30},
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{color:'#e8ecff'},
    xaxis:{gridcolor:'rgba(255,255,255,0.06)'},
    yaxis:{gridcolor:'rgba(255,255,255,0.06)'}
  }, {displayModeBar:false}).then(gd => {
    gd.on('plotly_click', ev => select(ev.points[0].y, ev.points[0].x));
  });

  Plotly.newPlot('conviction_heat', [{
    type:'heatmap', x: weeks, y: pairs, z: DATA.conviction_heat, zmin:0, zmax:1,
    hovertemplate:'<b>%{y}</b><br>%{x}<br>|Score|=%{z:.3f}<extra></extra>'
  }], {
    margin:{l:110,r:10,t:10,b:30},
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{color:'#e8ecff'},
    xaxis:{gridcolor:'rgba(255,255,255,0.06)'},
    yaxis:{gridcolor:'rgba(255,255,255,0.06)'}
  }, {displayModeBar:false}).then(gd => {
    gd.on('plotly_click', ev => select(ev.points[0].y, ev.points[0].x));
  });

  const c = DATA.counts;
  const traces = c.columns.map((col, i) => ({ type:'bar', name:col, x:c.index, y:c.values.map(r => r[i]) }));
  Plotly.newPlot('counts', traces, {
    barmode:'stack',
    margin:{l:40,r:10,t:10,b:30},
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{color:'#e8ecff'},
    xaxis:{gridcolor:'rgba(255,255,255,0.06)'},
    yaxis:{gridcolor:'rgba(255,255,255,0.06)', title:'Pairs'},
    legend:{orientation:'h', y:-0.25},
  }, {displayModeBar:false});

  for (const tr of document.querySelectorAll('tr.rowlink')) {
    tr.addEventListener('click', () => select(tr.dataset.pair, tr.dataset.week));
  }

  searchEl.addEventListener('input', () => {
    const q = (searchEl.value || '').trim().toUpperCase();
    if (!q) return;
    const hit = pairs.find(p => p.includes(q));
    if (hit) { selPairEl.value = hit; updatePairExplorer(); }
  });

  selPairEl.addEventListener('change', updatePairExplorer);
  selWeekEl.addEventListener('change', updatePairExplorer);

  const dq = DATA.data_quality || {};
  document.getElementById('dqBox').innerHTML =
    'Overall stale rate: <b>' + (((dq.stale_rate || 0) * 100).toFixed(1)) + '%</b><br/>' +
    'Most stale pillar: <b>' + (dq.most_stale_pillar || 'n/a') + '</b><br/>' +
    'Stale counts: <span class="mono">' + JSON.stringify(dq.stale_counts || {}) + '</span>';

  const riskTbl = document.getElementById('riskWeekTbl');
  const m = DATA.meta_by_week || {};
  const riskRows = weeks.map(w => {
    const rr = (m[w] || {}).risk_regime || {};
    const stale = (rr.stale_components || []).join(', ');
    const warn = rr.warning || '';
    return '<tr><td>' + w + '</td><td>' + (rr.obs_date || 'NA') + '</td><td>' + (rr.spx_obs_date || 'NA') + '</td><td>' + (rr.vix_obs_date || 'NA') + '</td><td>' + (rr.dxy_obs_date || 'NA') + '</td><td>' + stale + '</td><td>' + warn + '</td></tr>';
  }).join('');
  riskTbl.innerHTML = '<thead><tr><th>as_of</th><th>risk_obs_date</th><th>spx</th><th>vix</th><th>dxy</th><th>stale_components</th><th>warning</th></tr></thead><tbody>' + riskRows + '</tbody>';

  const metaTbl = document.getElementById('metaTbl');
  const metaRows = weeks.map(w => {
    const mm = m[w] || {};
    const th = (mm.thresholds || {}).bias_threshold;
    const wt = mm.weights ? 'yes' : '';
    const rr = mm.risk_regime || {};
    return '<tr class="rowlink" data-week="' + w + '"><td>' + w + '</td><td>' + (th ?? 'NA') + '</td><td>' + wt + '</td><td>' + (rr.warning || '') + '</td></tr>';
  }).join('');
  metaTbl.innerHTML = '<thead><tr><th>as_of</th><th>bias_threshold</th><th>weights</th><th>risk_warning</th></tr></thead><tbody>' + metaRows + '</tbody>';
  for (const tr of metaTbl.querySelectorAll('tr.rowlink')) {
    tr.addEventListener('click', () => {
      const w = tr.dataset.week;
      const mm = m[w] || {};
      navigator.clipboard?.writeText(JSON.stringify(mm, null, 2));
      alert('Copied meta JSON for ' + w + ' to clipboard');
    });
  }

  populateControls();
  updatePairExplorer();
</script>
</body>
</html>""")

    html = tmpl.substitute(
        WEEK_START=weeks[0],
        WEEK_END=weeks[-1],
        GENERATED=payload["generated_utc"],
        LATEST=weeks[-1],
        LATEST_ROWS=latest_rows_html,
        PAYLOAD_JSON=payload_json,
    )

    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")


def _make_pdf_dashboard(out_pdf: Path, weeks: List[str], panel: pd.DataFrame) -> None:
    # Lightweight PDF: summary table + small charts rendered via matplotlib, embedded via reportlab.
    import io
    import matplotlib.pyplot as plt
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    latest = weeks[-1]
    score_col = "total_score" if "total_score" in panel.columns else "score"
    bias_col = "final_bias" if "final_bias" in panel.columns else "bias"
    latest_df = panel[panel["as_of"] == latest].copy().sort_values(score_col, ascending=False)

    # Chart: score distribution (hist)
    buf1 = io.BytesIO()
    plt.figure(figsize=(7, 3.2))
    plt.hist(latest_df[score_col].astype(float).values, bins=20)
    plt.title(f"Score distribution — {latest}")
    plt.xlabel("score")
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(buf1, format="png", dpi=160)
    plt.close()
    buf1.seek(0)

    # Chart: bias counts
    buf2 = io.BytesIO()
    counts = panel.groupby(["as_of","bias"]).size().reset_index(name="n")
    piv = counts.pivot(index="as_of", columns="bias", values="n").fillna(0).reindex(weeks)
    plt.figure(figsize=(7, 3.2))
    for col in piv.columns:
        plt.plot(piv.index, piv[col].values, marker="o", label=col)
    plt.title("Bias counts over time")
    plt.xlabel("week (as_of)")
    plt.ylabel("pairs")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.legend()
    plt.savefig(buf2, format="png", dpi=160)
    plt.close()
    buf2.seek(0)

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_pdf), pagesize=letter)
    W, H = letter

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, H-50, "FX Macro Bias — Weekly Dashboard")
    c.setFont("Helvetica", 10)
    c.drawString(40, H-68, f"Weeks: {weeks[0]} → {weeks[-1]}   Generated: {_dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    c.line(40, H-78, W-40, H-78)

    # Charts
    img1 = ImageReader(buf1)
    c.drawImage(img1, 40, H-330, width=W-80, height=220, preserveAspectRatio=True, mask='auto')

    img2 = ImageReader(buf2)
    c.drawImage(img2, 40, H-565, width=W-80, height=220, preserveAspectRatio=True, mask='auto')

    c.showPage()

    # Table page (top N)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, H-50, f"Latest Week Leaderboard ({latest})")
    c.setFont("Helvetica", 9)

    cols = ["pair","rates","growth","risk","positioning","score","conv","bias"]
    x = [40, 115, 170, 225, 280, 360, 415, 470]
    y = H-80

    # header row
    c.setFont("Helvetica-Bold", 9)
    for i, col in enumerate(cols):
        c.drawString(x[i], y, col)
    y -= 12
    c.setFont("Helvetica", 9)
    c.line(40, y+6, W-40, y+6)

    def fmt(v):
        try:
            if v is None or pd.isna(v):
                return "NA"
            return f"{float(v):+.2f}"
        except Exception:
            return "NA"

    for _, r in latest_df.head(40).iterrows():
        row = [r["pair"], fmt(r["rates"]), fmt(r["growth"]), fmt(r["risk"]), fmt(r["positioning"]), fmt(r[score_col]), r.get("conviction_tier",""), r.get(bias_col,"")]
        for i, val in enumerate(row):
            c.drawString(x[i], y, str(val))
        y -= 12
        if y < 60:
            c.showPage()
            y = H-60

    c.save()


def build_weekly_report(
    cfg: dict,
    pairs: List[str],
    weeks: int = 4,
    end_date: Optional[str] = None,
    outdir: str = "out",
    refresh: bool = False,
    formats: Tuple[str, ...] = ("html", "pdf"),
) -> Dict[str, str]:
    """Produces weekly dashboards for the last N weeks.

    Returns a dict of generated file paths.
    """
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    asofs = _weekly_asof_dates(weeks=weeks, end_date=end_date)
    engine = MacroBiasEngine(cfg, refresh=refresh)
    engine.prepare_history(pairs=pairs, asofs=asofs)

    frames = []
    meta_by_week = {}
    for d in asofs:
        df, meta = engine.run(pairs=pairs, asof=d)
        df = df.copy()
        df["as_of"] = d
        bias_col = "final_bias" if "final_bias" in df.columns else "bias"
        df["bias_num"] = df[bias_col].apply(_bias_to_num)
        frames.append(df)
        meta_by_week[d] = meta

    panel = pd.concat(frames, ignore_index=True)

    stamp = asofs[-1].replace("-", "")
    outputs: Dict[str, str] = {}
    if "html" in formats:
        out_html = out / f"weekly_dashboard_{stamp}.html"
        _make_html_dashboard(out_html, asofs, panel, meta_by_week)
        outputs["html"] = str(out_html)
    if "pdf" in formats:
        out_pdf = out / f"weekly_dashboard_{stamp}.pdf"
        _make_pdf_dashboard(out_pdf, asofs, panel)
        outputs["pdf"] = str(out_pdf)

    # Also save raw panel as parquet/csv for audit
    out_csv = out / f"weekly_panel_{stamp}.csv"
    csv_panel = panel.drop(columns=[c for c in ['_pillar_meta'] if c in panel.columns])
    csv_panel.to_csv(out_csv, index=False)
    outputs["csv"] = str(out_csv)

    return outputs
