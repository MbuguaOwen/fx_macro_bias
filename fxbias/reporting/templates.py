from __future__ import annotations

import json
from string import Template


def render_dashboard_html(payload: dict, latest_rows_html: str) -> str:
    payload_json = json.dumps(payload, sort_keys=True, default=str)
    weeks = payload.get("weeks") or []
    week_start = weeks[0] if weeks else "NA"
    week_end = weeks[-1] if weeks else "NA"
    generated = payload.get("generated_utc", "NA")
    latest = payload.get("latest_week", week_end)

    tmpl = Template(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>FX Macro Bias Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
  <style>
    :root {
      --bg0: #090f1d;
      --bg1: #102038;
      --panel: rgba(12, 24, 44, 0.86);
      --panel-soft: rgba(16, 30, 52, 0.72);
      --line: rgba(142, 177, 224, 0.25);
      --text: #f4f8ff;
      --muted: #aec5e0;
      --accent: #57c7ff;
      --accent-2: #8fe388;
      --warn: #f2b061;
      --bad: #ff7f93;
      --ok: #8fe388;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      font-family: "Space Grotesk", "IBM Plex Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(1200px 680px at -10% -10%, #163a61 0%, transparent 60%),
        radial-gradient(860px 520px at 110% 0%, #1e4c52 0%, transparent 55%),
        linear-gradient(160deg, var(--bg0), var(--bg1));
      min-height: 100vh;
    }
    .shell { max-width: 1440px; margin: 0 auto; padding: 24px; }
    .top {
      display: flex;
      gap: 16px;
      justify-content: space-between;
      align-items: flex-end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 16px;
      margin-bottom: 18px;
    }
    h1 { margin: 0; font-size: 24px; letter-spacing: 0.4px; }
    .sub { color: var(--muted); font-size: 13px; }
    .tabs { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
    .tab-btn {
      border: 1px solid var(--line);
      background: var(--panel-soft);
      color: var(--text);
      border-radius: 999px;
      padding: 8px 14px;
      font-size: 13px;
      cursor: pointer;
      transition: all 0.18s ease;
    }
    .tab-btn:hover { border-color: rgba(87, 199, 255, 0.6); }
    .tab-btn.active {
      background: linear-gradient(120deg, rgba(87, 199, 255, 0.22), rgba(143, 227, 136, 0.14));
      border-color: rgba(87, 199, 255, 0.55);
      box-shadow: 0 10px 22px rgba(0, 0, 0, 0.25);
    }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }
    .grid { display: grid; gap: 14px; }
    .grid.two { grid-template-columns: 1fr; }
    @media (min-width: 1080px) { .grid.two { grid-template-columns: 1.28fr 0.72fr; } }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      box-shadow: 0 14px 30px rgba(0, 0, 0, 0.32);
      backdrop-filter: blur(6px);
    }
    h2 { margin: 0 0 10px 0; font-size: 14px; letter-spacing: 0.3px; color: #d3e6ff; }
    .kpi-grid { display: grid; gap: 10px; grid-template-columns: repeat(4, 1fr); }
    @media (max-width: 980px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
    .kpi { border: 1px solid var(--line); border-radius: 12px; padding: 10px; background: rgba(255,255,255,0.02); }
    .kpi .label { color: var(--muted); font-size: 12px; }
    .kpi .value { font-size: 16px; font-weight: 700; margin-top: 4px; }
    .table-wrap { overflow: auto; max-width: 100%; }
    table.tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
    .tbl th, .tbl td {
      border-bottom: 1px solid var(--line);
      padding: 7px 8px;
      text-align: right;
      white-space: nowrap;
    }
    .tbl th:first-child, .tbl td:first-child { text-align: left; }
    .row-click:hover { background: rgba(87, 199, 255, 0.1); }
    .pill {
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      border: 1px solid var(--line);
      font-weight: 700;
      font-size: 11px;
    }
    .pill.bull { color: #bff5b8; background: rgba(143, 227, 136, 0.15); }
    .pill.bear { color: #ffc0cb; background: rgba(255, 127, 147, 0.18); }
    .pill.neut { color: #deebf8; background: rgba(181, 196, 214, 0.14); }
    .pill.overlay-bull { color: #bff5b8; border-color: rgba(143,227,136,0.45); }
    .pill.overlay-bear { color: #ffc0cb; border-color: rgba(255,127,147,0.45); }
    .pill.overlay-neut { color: #deebf8; border-color: rgba(181,196,214,0.45); }
    .controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
    .controls select, .controls input {
      background: rgba(255,255,255,0.02);
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 7px 10px;
      font-size: 13px;
    }
    .mono { font-family: "IBM Plex Mono", "Consolas", monospace; font-size: 12px; color: var(--muted); white-space: pre-wrap; word-break: break-word; }
    .split { display: grid; gap: 14px; grid-template-columns: 1fr; }
    @media (min-width: 1080px) { .split { grid-template-columns: 280px 1fr; } }
    .overlay-note {
      margin-top: 8px;
      padding: 10px;
      border: 1px dashed rgba(87,199,255,0.45);
      border-radius: 10px;
      font-size: 12px;
      color: #d8e6f6;
      background: rgba(19, 42, 69, 0.55);
    }
    .flip-bad { color: #ffc0cb; font-weight: 700; }
    .flip-neutral { color: #f2b061; font-weight: 700; }
    .method-list { margin: 0; padding-left: 18px; }
    .foot { margin-top: 8px; font-size: 12px; color: var(--muted); }
    .badge-stale { color: #ffd6b8; }
  </style>
</head>
<body>
  <div class="shell">
    <div class="top">
      <div>
        <h1>FX Macro Bias - Fundamentals + Market Overlay</h1>
        <div class="sub">Weeks: $WEEK_START to $WEEK_END | Generated: $GENERATED</div>
      </div>
      <div class="sub">Deterministic payload, provenance and staleness included</div>
    </div>

    <div class="tabs">
      <button class="tab-btn active" data-tab="overview">Overview</button>
      <button class="tab-btn" data-tab="drill">Pair Drilldown</button>
      <button class="tab-btn" data-tab="compare">Compare</button>
      <button class="tab-btn" data-tab="quality">Data Quality</button>
      <button class="tab-btn" data-tab="methods">Methods</button>
    </div>

    <section id="tab-overview" class="tab-panel active">
      <div class="grid two">
        <div class="card">
          <h2>Final Bias Heatmap</h2>
          <div id="plot-bias" style="height:520px;"></div>
          <div class="foot">Click a heatmap cell to open Pair Drilldown at that pair/week.</div>
        </div>
        <div class="grid">
          <div class="card">
            <h2>Bias Distribution</h2>
            <div id="plot-counts" style="height:250px;"></div>
          </div>
          <div class="card">
            <h2>Score Heatmap</h2>
            <div id="plot-score" style="height:200px;"></div>
          </div>
          <div class="card">
            <h2>Conviction Heatmap</h2>
            <div id="plot-conv" style="height:200px;"></div>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top:14px;">
        <h2>Latest Week Leaderboard ($LATEST_WEEK)</h2>
        <div class="table-wrap">
          <table class="tbl">
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
                <th>Staleness</th>
              </tr>
            </thead>
            <tbody>
              $LATEST_ROWS
            </tbody>
          </table>
        </div>
      </div>

      <div class="card" style="margin-top:14px;">
        <h2 id="overlay-title">Market Overlay Summary</h2>
        <div id="overlay-summary" class="sub">Overlay status unavailable.</div>
        <div class="overlay-note">Options skew is an overlay only and does not alter the 4-pillar fundamentals score.</div>
      </div>

      <div class="card" style="margin-top:14px;">
        <h2>Instrument Notes</h2>
        <div id="instrument-notes" class="sub">No instrument notes configured.</div>
      </div>
    </section>

    <section id="tab-drill" class="tab-panel">
      <div class="split">
        <div class="card">
          <h2>Selection</h2>
          <div class="controls">
            <label class="sub">Pair</label>
            <select id="sel-pair"></select>
            <label class="sub">Week</label>
            <select id="sel-week"></select>
          </div>
          <div class="foot" id="sel-meta"></div>
        </div>
        <div class="card">
          <h2>Snapshot</h2>
          <div class="kpi-grid">
            <div class="kpi"><div class="label">Final Bias</div><div class="value" id="k-bias">NA</div></div>
            <div class="kpi"><div class="label">Total Score</div><div class="value" id="k-score">NA</div></div>
            <div class="kpi"><div class="label">Conviction</div><div class="value" id="k-conv">NA</div></div>
            <div class="kpi"><div class="label">Staleness</div><div class="value" id="k-stale">NA</div></div>
          </div>
        </div>
      </div>

      <div class="grid two" style="margin-top:14px;">
        <div class="card">
          <h2>Pillar Scores and Raw Inputs</h2>
          <div class="table-wrap"><table class="tbl" id="tbl-pillars"></table></div>
        </div>
        <div class="card">
          <h2>Provenance and Staleness</h2>
          <div class="table-wrap"><table class="tbl" id="tbl-prov"></table></div>
        </div>
      </div>

      <div class="card" style="margin-top:14px;">
        <h2>Market Overlay for Selection</h2>
        <div id="overlay-drill" class="sub">No overlay for this pair/date.</div>
      </div>

      <div class="grid two" style="margin-top:14px;">
        <div class="card">
          <h2>Total Score History</h2>
          <div id="plot-pair-score" style="height:320px;"></div>
        </div>
        <div class="card">
          <h2>Bias History</h2>
          <div id="plot-pair-bias" style="height:320px;"></div>
        </div>
      </div>

      <div class="card" style="margin-top:14px;">
        <h2>Raw Meta</h2>
        <div id="raw-meta" class="mono"></div>
      </div>
    </section>

    <section id="tab-compare" class="tab-panel">
      <div class="card">
        <h2>Compare Report Dates</h2>
        <div class="controls">
          <label class="sub">Date A</label>
          <select id="cmp-a"></select>
          <label class="sub">Date B</label>
          <select id="cmp-b"></select>
          <span id="cmp-flips" class="sub"></span>
        </div>
      </div>
      <div class="card" style="margin-top:14px;">
        <h2>Delta Table (B - A)</h2>
        <div class="table-wrap"><table class="tbl" id="tbl-compare"></table></div>
      </div>
    </section>

    <section id="tab-quality" class="tab-panel">
      <div class="card">
        <h2>Data Quality Summary</h2>
        <div id="quality-summary" class="sub"></div>
      </div>
      <div class="card" style="margin-top:14px;">
        <h2>Provider Freshness</h2>
        <div class="table-wrap"><table class="tbl" id="tbl-provider"></table></div>
      </div>
      <div class="card" style="margin-top:14px;">
        <h2>Risk Regime Timestamps by Week</h2>
        <div class="table-wrap"><table class="tbl" id="tbl-risk-regime"></table></div>
      </div>
    </section>

    <section id="tab-methods" class="tab-panel">
      <div class="card">
        <h2>Scoring and Normalization</h2>
        <ul class="method-list" id="methods-score"></ul>
      </div>
      <div class="card" style="margin-top:14px;">
        <h2>Staleness and Provenance</h2>
        <ul class="method-list" id="methods-quality"></ul>
      </div>
      <div class="card" style="margin-top:14px;">
        <h2>Market Overlay (Not Fundamentals)</h2>
        <ul class="method-list" id="methods-overlay"></ul>
      </div>
    </section>
  </div>

  <script>
    const DATA = $PAYLOAD_JSON;
    const weeks = DATA.weeks || [];
    const pairs = DATA.pairs || [];
    const rows = DATA.rows || [];
    const scoreCol = DATA.score_col || "total_score";
    const overlayRoot = DATA.market_overlay || {};
    const overlayStatus = overlayRoot.status || {};
    const overlayRequest = overlayRoot.request || {};

    const idx = new Map();
    for (const row of rows) {
      const pair = String(row.pair || "").toUpperCase();
      const week = String(row.as_of || "");
      const key = `${pair}|${week}`;
      idx.set(key, row);
    }

    function fmt(v, d=2) {
      if (v === null || v === undefined || v === "" || Number.isNaN(Number(v))) return "NA";
      const x = Number(v);
      return (x >= 0 ? "+" : "") + x.toFixed(d);
    }
    function toBiasNum(b) {
      if (b === "BULL_BASE") return 1;
      if (b === "BEAR_BASE") return -1;
      return 0;
    }
    function biasPill(b) {
      if (b === "BULL_BASE") return '<span class="pill bull">BULL_BASE</span>';
      if (b === "BEAR_BASE") return '<span class="pill bear">BEAR_BASE</span>';
      return '<span class="pill neut">NEUTRAL</span>';
    }
    function overlayPill(label) {
      if (label === "BULLISH") return '<span class="pill overlay-bull">BULLISH</span>';
      if (label === "BEARISH") return '<span class="pill overlay-bear">BEARISH</span>';
      return '<span class="pill overlay-neut">NEUTRAL</span>';
    }
    function rowKey(pair, week) {
      return `${String(pair || "").toUpperCase()}|${String(week || "")}`;
    }

    function setTab(tab) {
      for (const b of document.querySelectorAll(".tab-btn")) b.classList.remove("active");
      for (const p of document.querySelectorAll(".tab-panel")) p.classList.remove("active");
      document.querySelector(`.tab-btn[data-tab="${tab}"]`).classList.add("active");
      document.getElementById(`tab-${tab}`).classList.add("active");
    }
    for (const b of document.querySelectorAll(".tab-btn")) {
      b.addEventListener("click", () => setTab(b.dataset.tab));
    }

    function clickToDrill(pair, week) {
      document.getElementById("sel-pair").value = pair;
      document.getElementById("sel-week").value = week;
      updateDrill();
      setTab("drill");
    }

    Plotly.newPlot("plot-bias", [{
      type: "heatmap",
      x: weeks,
      y: pairs,
      z: DATA.heatmaps.bias,
      zmin: -1,
      zmax: 1,
      hovertemplate: "<b>%{y}</b><br>%{x}<br>Bias=%{z}<extra></extra>",
      colorscale: [
        [0.0, "#ff7f93"],
        [0.5, "#99aabc"],
        [1.0, "#8fe388"],
      ],
    }], {
      margin: {l: 115, r: 14, t: 8, b: 35},
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: {color: "#f4f8ff"},
      xaxis: {gridcolor: "rgba(255,255,255,0.07)"},
      yaxis: {gridcolor: "rgba(255,255,255,0.07)"},
    }, {displayModeBar: false}).then(gd => {
      gd.on("plotly_click", (ev) => clickToDrill(ev.points[0].y, ev.points[0].x));
    });

    Plotly.newPlot("plot-score", [{
      type: "heatmap",
      x: weeks,
      y: pairs,
      z: DATA.heatmaps.score,
      hovertemplate: "<b>%{y}</b><br>%{x}<br>Score=%{z:.3f}<extra></extra>",
    }], {
      margin: {l: 115, r: 14, t: 8, b: 35},
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: {color: "#f4f8ff"},
    }, {displayModeBar: false}).then(gd => {
      gd.on("plotly_click", (ev) => clickToDrill(ev.points[0].y, ev.points[0].x));
    });

    Plotly.newPlot("plot-conv", [{
      type: "heatmap",
      x: weeks,
      y: pairs,
      z: DATA.heatmaps.conviction,
      zmin: 0,
      zmax: 1,
      hovertemplate: "<b>%{y}</b><br>%{x}<br>|score|=%{z:.3f}<extra></extra>",
    }], {
      margin: {l: 115, r: 14, t: 8, b: 35},
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: {color: "#f4f8ff"},
    }, {displayModeBar: false}).then(gd => {
      gd.on("plotly_click", (ev) => clickToDrill(ev.points[0].y, ev.points[0].x));
    });

    const cnt = DATA.counts || {index: [], columns: [], values: []};
    const traces = (cnt.columns || []).map((col, i) => ({
      type: "bar",
      name: col,
      x: cnt.index,
      y: (cnt.values || []).map(v => v[i] || 0),
    }));
    Plotly.newPlot("plot-counts", traces, {
      barmode: "stack",
      margin: {l: 34, r: 10, t: 8, b: 34},
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: {color: "#f4f8ff"},
      xaxis: {gridcolor: "rgba(255,255,255,0.07)"},
      yaxis: {gridcolor: "rgba(255,255,255,0.07)"},
      legend: {orientation: "h", y: -0.25},
    }, {displayModeBar: false});

    const pairSel = document.getElementById("sel-pair");
    const weekSel = document.getElementById("sel-week");
    for (const p of pairs) {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      pairSel.appendChild(opt);
    }
    for (const w of weeks) {
      const opt = document.createElement("option");
      opt.value = w;
      opt.textContent = w;
      weekSel.appendChild(opt);
    }
    pairSel.value = pairs.length ? pairs[0] : "";
    weekSel.value = weeks.length ? weeks[weeks.length - 1] : "";

    function overlayFor(pair, week) {
      const ov = (DATA.market_overlay || {}).by_key || {};
      return ov[rowKey(pair, week)] || null;
    }

    function updateDrill() {
      const pair = String(pairSel.value || "").toUpperCase();
      const week = String(weekSel.value || "");
      const key = rowKey(pair, week);
      const row = idx.get(key);
      const selMeta = document.getElementById("sel-meta");
      selMeta.textContent = `ID=${key}`;

      if (!row) {
        document.getElementById("k-bias").textContent = "NA";
        document.getElementById("k-score").textContent = "NA";
        document.getElementById("k-conv").textContent = "NA";
        document.getElementById("k-stale").textContent = "NA";
        return;
      }

      const bias = row.final_bias || row.bias || "NEUTRAL";
      document.getElementById("k-bias").innerHTML = biasPill(bias);
      document.getElementById("k-score").textContent = fmt(row[scoreCol], 3);
      document.getElementById("k-conv").textContent = row.conviction_tier || "NA";
      document.getElementById("k-stale").innerHTML = row.overall_staleness_flag ? '<span class="badge-stale">STALE</span>' : "OK";

      const pillars = ["rates", "growth", "risk", "positioning"].map((p) => (
        `<tr id="pillar-${pair}-${week}-${p}"><td>${p}</td><td>${fmt(row[p], 3)}</td><td>${fmt(row[p + "_raw"], 4)}</td></tr>`
      )).join("");
      document.getElementById("tbl-pillars").innerHTML = `<thead><tr><th>Pillar</th><th>Score</th><th>Raw</th></tr></thead><tbody>${pillars}</tbody>`;

      const provMap = [
        ["rates", row.rates_obs_date, row.rates_age_days, row.rates_stale],
        ["growth", row.growth_obs_date, row.growth_age_days, row.growth_stale],
        ["risk", row.risk_obs_date, row.risk_age_days, row.risk_stale],
        ["positioning", row.pos_obs_date, row.pos_age_days, row.pos_stale],
      ];
      const provRows = provMap.map((x) => (
        `<tr id="prov-${pair}-${week}-${x[0]}"><td>${x[0]}</td><td>${x[1] || "NA"}</td><td>${x[2] ?? "NA"}</td><td>${x[3] ? "YES" : ""}</td></tr>`
      )).join("");
      document.getElementById("tbl-prov").innerHTML = `<thead><tr><th>Pillar</th><th>obs_date</th><th>age_days</th><th>stale</th></tr></thead><tbody>${provRows}</tbody>`;

      const ov = overlayFor(pair, week);
      const od = document.getElementById("overlay-drill");
      if (!ov) {
        const msg = overlayStatus.message || "No overlay for this pair/date.";
        const hint = overlayStatus.hint || "";
        od.innerHTML = hint ? `${msg}<br/>${hint}` : msg;
      } else {
        od.innerHTML = `${overlayPill(ov.label)} rr10=${fmt(ov.rr10, 2)} | rr25=${fmt(ov.rr25, 2)} | atm_iv=${fmt(ov.approx_atm_iv, 2)} | tenor=${ov.tenor || "NA"} | expiry=${ov.expiry_date || "NA"} | as_of=${ov.as_of || "NA"}`;
      }

      const scoreTs = weeks.map(w => {
        const rw = idx.get(rowKey(pair, w));
        if (!rw) return null;
        const v = Number(rw[scoreCol]);
        return Number.isNaN(v) ? null : v;
      });
      Plotly.newPlot("plot-pair-score", [{
        type: "scatter",
        mode: "lines+markers",
        x: weeks,
        y: scoreTs,
        hovertemplate: `<b>${pair}</b><br>%{x}<br>score=%{y:.3f}<extra></extra>`,
        line: {color: "#57c7ff"},
      }], {
        margin: {l: 38, r: 10, t: 8, b: 36},
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: {color: "#f4f8ff"},
      }, {displayModeBar: false});

      const biasTs = weeks.map(w => {
        const rw = idx.get(rowKey(pair, w));
        return toBiasNum(rw ? (rw.final_bias || rw.bias) : "NEUTRAL");
      });
      Plotly.newPlot("plot-pair-bias", [{
        type: "scatter",
        mode: "lines+markers",
        x: weeks,
        y: biasTs,
        hovertemplate: `<b>${pair}</b><br>%{x}<br>bias=%{y}<extra></extra>`,
        line: {color: "#8fe388"},
      }], {
        margin: {l: 38, r: 10, t: 8, b: 36},
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: {color: "#f4f8ff"},
        yaxis: {tickvals: [-1, 0, 1], ticktext: ["BEAR", "NEUTRAL", "BULL"]},
      }, {displayModeBar: false});

      const raw = {
        pair: pair,
        as_of: week,
        score: row[scoreCol],
        final_bias: row.final_bias || row.bias,
        pillar_meta: row._pillar_meta || {},
      };
      document.getElementById("raw-meta").textContent = JSON.stringify(raw, null, 2);
    }
    pairSel.addEventListener("change", updateDrill);
    weekSel.addEventListener("change", updateDrill);
    updateDrill();

    for (const tr of document.querySelectorAll("tr.row-click")) {
      tr.addEventListener("click", () => clickToDrill(tr.dataset.pair, tr.dataset.week));
    }

    const ovLatest = overlayRoot.latest || null;
    const ovSummary = document.getElementById("overlay-summary");
    const ovTitle = document.getElementById("overlay-title");
    const ovSymbol = String((ovLatest && ovLatest.symbol) || overlayRequest.symbol || "XAUUSD").toUpperCase();
    ovTitle.textContent = `Market Overlay Summary (${ovSymbol})`;
    if (!ovLatest) {
      const message = overlayStatus.message || "Overlay unavailable.";
      const hint = overlayStatus.hint || "";
      const enable = !overlayRoot.requested
        ? "Enable with --with-options --options-url <investing-options-url> or set FXBIAS_OPTIONS_URL."
        : "";
      ovSummary.innerHTML =
        `${message}` +
        (hint ? `<br/>${hint}` : "") +
        (enable ? `<br/>${enable}` : "");
    } else {
      ovSummary.innerHTML =
        `${overlayPill(ovLatest.label)} rr10=${fmt(ovLatest.rr10, 2)} | atm_iv=${fmt(ovLatest.approx_atm_iv, 2)} | tenor=${ovLatest.tenor || "NA"} | expiry=${ovLatest.expiry_date || "NA"} | as_of=${ovLatest.as_of || "NA"}`;
    }

    const notesNode = document.getElementById("instrument-notes");
    const instNotes = ((DATA.report_notes || {}).instrument_notes || {});
    const noteKeys = Object.keys(instNotes).sort();
    if (!noteKeys.length) {
      notesNode.textContent = "No instrument notes configured.";
    } else {
      const body = noteKeys.map((k) => `<tr><td>${k}</td><td style="text-align:left">${instNotes[k]}</td></tr>`).join("");
      notesNode.innerHTML = `<div class="table-wrap"><table class="tbl"><thead><tr><th>Instrument</th><th>Rationale</th></tr></thead><tbody>${body}</tbody></table></div>`;
    }

    const cmpA = document.getElementById("cmp-a");
    const cmpB = document.getElementById("cmp-b");
    for (const w of weeks) {
      const oa = document.createElement("option");
      oa.value = w; oa.textContent = w; cmpA.appendChild(oa);
      const ob = document.createElement("option");
      ob.value = w; ob.textContent = w; cmpB.appendChild(ob);
    }
    const cmpDefault = DATA.compare || {};
    cmpA.value = cmpDefault.default_a || (weeks.length > 1 ? weeks[weeks.length - 2] : (weeks[0] || ""));
    cmpB.value = cmpDefault.default_b || (weeks[weeks.length - 1] || "");

    function renderCompare() {
      const a = String(cmpA.value || "");
      const b = String(cmpB.value || "");
      const key = `${a}|${b}`;
      const rows = ((DATA.compare || {}).by_key || {})[key] || [];
      const body = rows.map(r => {
        const flip = r.flip || "";
        let cls = "";
        if (flip === "BULL->BEAR" || flip === "BEAR->BULL") cls = "flip-bad";
        if (flip === "->NEUTRAL") cls = "flip-neutral";
        return `<tr id="cmp-${r.pair}-${a}-${b}">
          <td>${r.pair}</td>
          <td>${fmt(r.delta_rates, 3)}</td>
          <td>${fmt(r.delta_growth, 3)}</td>
          <td>${fmt(r.delta_risk, 3)}</td>
          <td>${fmt(r.delta_positioning, 3)}</td>
          <td>${fmt(r.delta_total_score, 3)}</td>
          <td>${r.bias_a || "NA"}</td>
          <td>${r.bias_b || "NA"}</td>
          <td class="${cls}">${flip}</td>
          <td>${r.persistence_b ?? "NA"}</td>
        </tr>`;
      }).join("");
      document.getElementById("tbl-compare").innerHTML = `<thead>
        <tr>
          <th>Pair</th><th>dRates</th><th>dGrowth</th><th>dRisk</th><th>dPos</th><th>dTotal</th>
          <th>Bias A</th><th>Bias B</th><th>Flip</th><th>Persistence@B</th>
        </tr>
      </thead><tbody>${body}</tbody>`;
      const f = ((DATA.compare || {}).flip_counts || {})[key] || {};
      document.getElementById("cmp-flips").textContent = `Flips: B->S ${f["BULL->BEAR"] || 0}, S->B ${f["BEAR->BULL"] || 0}, ->N ${f["->NEUTRAL"] || 0}`;
    }
    cmpA.addEventListener("change", renderCompare);
    cmpB.addEventListener("change", renderCompare);
    renderCompare();

    const dq = DATA.data_quality || {};
    document.getElementById("quality-summary").innerHTML =
      `Overall stale rate: <b>${((dq.overall_stale_rate || 0) * 100).toFixed(1)}%</b><br/>` +
      `Stale counts per pillar: <span class="mono">${JSON.stringify(dq.stale_counts || {})}</span><br/>` +
      `Most stale provider: <b>${dq.most_stale_provider || "NA"}</b>`;

    const providerRows = (dq.provider_summary || []).map(p => (
      `<tr><td>${p.provider}</td><td>${p.stale_count}</td><td>${p.last_updated || "NA"}</td></tr>`
    )).join("");
    document.getElementById("tbl-provider").innerHTML =
      `<thead><tr><th>Provider</th><th>Stale Count</th><th>Last Updated</th></tr></thead><tbody>${providerRows}</tbody>`;

    const riskWeekRows = (weeks || []).map(w => {
      const m = (DATA.meta_by_week || {})[w] || {};
      const r = m.risk_regime || {};
      return `<tr><td>${w}</td><td>${r.obs_date || "NA"}</td><td>${r.spx_obs_date || "NA"}</td><td>${r.vix_obs_date || "NA"}</td><td>${r.dxy_obs_date || "NA"}</td><td>${(r.stale_components || []).join(", ")}</td></tr>`;
    }).join("");
    document.getElementById("tbl-risk-regime").innerHTML =
      `<thead><tr><th>as_of</th><th>risk_obs</th><th>spx</th><th>vix</th><th>dxy</th><th>stale_components</th></tr></thead><tbody>${riskWeekRows}</tbody>`;

    function fillMethods(id, rows) {
      document.getElementById(id).innerHTML = (rows || []).map(x => `<li>${x}</li>`).join("");
    }
    fillMethods("methods-score", (DATA.methods || {}).scoring || []);
    fillMethods("methods-quality", (DATA.methods || {}).quality || []);
    fillMethods("methods-overlay", (DATA.methods || {}).overlay || []);
  </script>
</body>
</html>
"""
    )

    return tmpl.safe_substitute(
        WEEK_START=week_start,
        WEEK_END=week_end,
        GENERATED=generated,
        LATEST_WEEK=latest,
        LATEST_ROWS=latest_rows_html,
        PAYLOAD_JSON=payload_json,
    )
