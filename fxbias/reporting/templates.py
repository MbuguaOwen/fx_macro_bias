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
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>FX Macro Bias Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
<style>
:root{--bg:#08121e;--bg2:#12243a;--panel:linear-gradient(180deg,rgba(18,31,49,.94),rgba(9,19,34,.95));--line:rgba(138,170,205,.22);--line2:rgba(138,170,205,.34);--text:#edf5ff;--muted:#a9bcd0;--accent:#6ec0ff;--accent2:#53d7bb;--ok:#8fd8a1;--bad:#ff9ca7;--warn:#f3c47e}
*{box-sizing:border-box}body{margin:0;color:var(--text);font-family:"IBM Plex Sans","Segoe UI",sans-serif;background:radial-gradient(1200px 720px at -10% -10%,rgba(40,96,154,.46),transparent 60%),radial-gradient(960px 540px at 110% 0,rgba(16,120,108,.22),transparent 58%),linear-gradient(155deg,var(--bg),var(--bg2));min-height:100vh}
.shell{max-width:1480px;margin:0 auto;padding:24px}.hero{display:flex;gap:16px;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;border-bottom:1px solid var(--line2);padding-bottom:18px;margin-bottom:16px}h1{margin:0;font-family:"Space Grotesk","IBM Plex Sans",sans-serif;font-size:30px;letter-spacing:.02em}.sub{color:var(--muted);font-size:13px}.lead{color:#dceafb;font-size:14px;line-height:1.5}.note{padding:10px 12px;border-radius:12px;border:1px dashed rgba(110,192,255,.38);background:linear-gradient(135deg,rgba(18,39,62,.72),rgba(14,30,46,.7));font-size:12px;color:#dceafb}.tabs{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}.tab-btn{border:1px solid var(--line);background:rgba(17,34,56,.85);color:var(--text);border-radius:999px;padding:8px 14px;font-size:13px;cursor:pointer;transition:.18s ease}.tab-btn:hover{border-color:var(--line2)}.tab-btn.active{background:linear-gradient(120deg,rgba(110,192,255,.24),rgba(83,215,187,.18));border-color:rgba(110,192,255,.5);box-shadow:0 10px 24px rgba(0,0,0,.22)}.tab-panel{display:none}.tab-panel.active{display:block}
.grid{display:grid;gap:14px}.two{grid-template-columns:1fr}.three{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}@media(min-width:1080px){.two{grid-template-columns:1.18fr .82fr}.three{grid-template-columns:repeat(3,minmax(0,1fr))}.kpis{grid-template-columns:repeat(6,minmax(0,1fr))}}
.split{display:grid;gap:14px;grid-template-columns:1fr}@media(min-width:1080px){.split{grid-template-columns:320px 1fr}}.card{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:14px;box-shadow:0 16px 34px rgba(0,0,0,.28)}.exec{padding:18px}.exec-grid{display:grid;gap:12px;grid-template-columns:1fr}@media(min-width:1080px){.exec-grid{grid-template-columns:1.1fr .9fr .9fr}}.exec-box{padding:14px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.03)}.exec-box strong{display:block;margin-bottom:6px;color:#f2f7ff}
h2{margin:0 0 10px 0;font-size:14px;font-family:"Space Grotesk","IBM Plex Sans",sans-serif;color:#d8ebff}.kpi{border:1px solid var(--line);border-radius:14px;padding:12px;background:linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,.02))}.label{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em}.value{margin-top:6px;font-size:18px;font-weight:700}.small{font-size:15px}
.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center}select,input{background:rgba(255,255,255,.03);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:7px 10px;font-size:13px}.table-wrap{overflow:auto;max-width:100%}table.tbl{width:100%;border-collapse:collapse;font-size:12px}.tbl th,.tbl td{border-bottom:1px solid var(--line);padding:8px;text-align:right;white-space:nowrap;vertical-align:top}.tbl thead th{background:rgba(255,255,255,.03);color:#dfefff}.tbl tbody tr:nth-child(even){background:rgba(255,255,255,.016)}.tbl th:first-child,.tbl td:first-child{text-align:left}.tbl .wrap{text-align:left;white-space:normal}tr.row-click:hover{background:rgba(110,192,255,.08);cursor:pointer}
.pill{display:inline-flex;align-items:center;border-radius:999px;padding:3px 9px;border:1px solid var(--line);font-size:11px;font-weight:700}.bull,.sent-bull,.agree-yes,.fresh{color:#c5ffd3;background:rgba(143,216,161,.16);border-color:rgba(143,216,161,.38)}.bear,.sent-bear,.agree-no{color:#ffd4d9;background:rgba(255,156,167,.16);border-color:rgba(255,156,167,.38)}.neut,.sent-neut,.agree-na,.na{color:#dbe6f2;background:rgba(219,230,242,.12)}.stale{color:#ffe0b2;background:rgba(243,196,126,.18);border-color:rgba(243,196,126,.38)}.mono{font-family:"IBM Plex Mono","Consolas",monospace;font-size:12px;color:var(--muted);white-space:pre-wrap;word-break:break-word}.foot{margin-top:8px;font-size:12px;color:var(--muted)}.method-list{margin:0;padding-left:18px}.flip-bad{color:#ffd4d9;font-weight:700}.flip-neutral{color:#ffe0b2;font-weight:700}
</style></head>
<body><div class="shell">
<div class="hero"><div><h1>FX Macro Bias Weekly Report</h1><div class="sub">Weeks: $WEEK_START to $WEEK_END | Generated: $GENERATED</div></div><div class="note">Sentiment is informational only. It does not alter the 4-pillar fundamentals score, total score, or final macro bias.</div></div>
<div class="tabs">
<button class="tab-btn active" data-tab="overview">Overview</button><button class="tab-btn" data-tab="sentiment">Sentiment</button><button class="tab-btn" data-tab="drill">Pair Drilldown</button><button class="tab-btn" data-tab="compare">Compare</button><button class="tab-btn" data-tab="quality">Data Quality</button><button class="tab-btn" data-tab="methods">Methods</button>
</div>

<section id="tab-overview" class="tab-panel active">
<div class="card exec"><h2>Executive Snapshot</h2><div class="exec-grid">
<div class="exec-box"><strong>Macro Board</strong><div id="exec-macro" class="lead">Loading macro overview.</div></div>
<div class="exec-box"><strong>Sentiment Board</strong><div id="exec-sentiment" class="lead">Loading sentiment overview.</div></div>
<div class="exec-box"><strong>Report Scope</strong><div id="exec-scope" class="lead">Loading report scope.</div></div>
</div></div>
<div class="grid kpis">
<div class="kpi"><div class="label">Pairs Tracked</div><div class="value" id="kpi-pairs">NA</div></div>
<div class="kpi"><div class="label">Macro Bullish</div><div class="value" id="kpi-bull">NA</div></div>
<div class="kpi"><div class="label">Macro Bearish</div><div class="value" id="kpi-bear">NA</div></div>
<div class="kpi"><div class="label">Macro Neutral</div><div class="value" id="kpi-neut">NA</div></div>
<div class="kpi"><div class="label">Sentiment Coverage</div><div class="value" id="kpi-cover">NA</div></div>
<div class="kpi"><div class="label">Sentiment Agreement</div><div class="value" id="kpi-agree">NA</div></div>
</div>
<div class="grid two" style="margin-top:14px;">
<div class="card"><h2>Final Bias Heatmap</h2><div id="plot-bias" style="height:520px;"></div><div class="foot">Click any heatmap cell to open the pair/date drilldown.</div></div>
<div class="grid">
<div class="card"><h2>Bias Distribution</h2><div id="plot-counts" style="height:250px;"></div></div>
<div class="card"><h2>Score Heatmap</h2><div id="plot-score" style="height:210px;"></div></div>
<div class="card"><h2>Conviction Heatmap</h2><div id="plot-conv" style="height:210px;"></div></div>
</div></div>
<div class="card" style="margin-top:14px;"><div class="controls" style="justify-content:space-between;margin-bottom:10px;"><h2 id="leaderboard-title">Leaderboard ($LATEST_WEEK)</h2><div class="controls"><label class="sub">Report Week</label><select id="overview-week"></select><span id="overview-meta" class="sub"></span></div></div><div class="table-wrap"><table class="tbl" id="tbl-overview-leaderboard"><thead><tr><th>Pair</th><th>Rates</th><th>Growth</th><th>Risk</th><th>Positioning</th><th>Total</th><th>Conviction</th><th>Bias</th><th>Staleness</th></tr></thead><tbody>$LATEST_ROWS</tbody></table></div></div>
<div class="grid two" style="margin-top:14px;">
<div class="card"><h2 id="overlay-title">Market Overlay Summary</h2><div id="overlay-summary" class="sub">Overlay status unavailable.</div><div class="note" style="margin-top:10px;">Options skew remains informational and does not modify the fundamentals engine.</div></div>
<div class="card"><h2>Sentiment Overlay Summary</h2><div id="sentiment-overview" class="sub">Sentiment overlay status unavailable.</div><div class="note" style="margin-top:10px;">Deterministic, instrument-aware, and reported beside macro bias for context only.</div></div>
</div>
<div class="card" style="margin-top:14px;"><h2>Instrument Notes</h2><div id="instrument-notes" class="sub">No instrument notes configured.</div></div>
</section>

<section id="tab-sentiment" class="tab-panel">
<div class="card"><h2>Sentiment Overlay</h2><div class="note">This layer never changes the fundamentals total score or final macro bias. It exists for repeatable weekly cross-checking and pair/date drilldown.</div></div>
<div class="split" style="margin-top:14px;">
<div class="card"><h2>Selection</h2><div class="controls"><label class="sub">Pair</label><select id="sentiment-pair"></select><label class="sub">Week</label><select id="sentiment-week"></select></div><div class="foot" id="sentiment-selection-meta"></div></div>
<div class="card"><h2>Snapshot</h2><div class="grid three">
<div class="kpi"><div class="label">Macro Bias</div><div class="value small" id="s-macro-bias">NA</div></div>
<div class="kpi"><div class="label">Macro Score</div><div class="value small" id="s-macro-score">NA</div></div>
<div class="kpi"><div class="label">Sentiment Bias</div><div class="value small" id="s-sent-bias">NA</div></div>
<div class="kpi"><div class="label">Sentiment Score</div><div class="value small" id="s-sent-score">NA</div></div>
<div class="kpi"><div class="label">Agreement</div><div class="value small" id="s-agreement">NA</div></div>
<div class="kpi"><div class="label">Freshness</div><div class="value small" id="s-freshness">NA</div></div>
</div></div></div>
<div class="grid two" style="margin-top:14px;">
<div class="card"><h2>Explanation</h2><div id="sentiment-summary-text" class="sub">No sentiment explanation for this pair/date.</div></div>
<div class="card"><h2 id="sentiment-week-title">Sentiment Table ($LATEST_WEEK)</h2><div class="table-wrap"><table class="tbl" id="tbl-sentiment-latest"></table></div></div>
</div>
<div class="card" style="margin-top:14px;"><h2>Signal Detail and Freshness</h2><div class="table-wrap"><table class="tbl" id="tbl-sentiment-signals"></table></div></div>
</section>

<section id="tab-drill" class="tab-panel">
<div class="split">
<div class="card"><h2>Selection</h2><div class="controls"><label class="sub">Pair</label><select id="sel-pair"></select><label class="sub">Week</label><select id="sel-week"></select></div><div class="foot" id="sel-meta"></div></div>
<div class="card"><h2>Macro Snapshot</h2><div class="grid three">
<div class="kpi"><div class="label">Final Bias</div><div class="value small" id="k-bias">NA</div></div>
<div class="kpi"><div class="label">Total Score</div><div class="value small" id="k-score">NA</div></div>
<div class="kpi"><div class="label">Conviction</div><div class="value small" id="k-conv">NA</div></div>
<div class="kpi"><div class="label">Macro Staleness</div><div class="value small" id="k-stale">NA</div></div>
<div class="kpi"><div class="label">Sentiment Bias</div><div class="value small" id="k-sent-bias">NA</div></div>
<div class="kpi"><div class="label">Macro vs Sentiment</div><div class="value small" id="k-sent-align">NA</div></div>
</div></div></div>
<div class="grid two" style="margin-top:14px;">
<div class="card"><h2>Pillar Scores and Raw Inputs</h2><div class="table-wrap"><table class="tbl" id="tbl-pillars"></table></div></div>
<div class="card"><h2>Provenance and Staleness</h2><div class="table-wrap"><table class="tbl" id="tbl-prov"></table></div></div>
</div>
<div class="grid two" style="margin-top:14px;">
<div class="card"><h2>Market Overlay for Selection</h2><div id="overlay-drill" class="sub">No options overlay for this pair/date.</div></div>
<div class="card"><h2>Sentiment Overlay for Selection</h2><div id="sentiment-drill" class="sub">No sentiment overlay for this pair/date.</div></div>
</div>
<div class="grid two" style="margin-top:14px;"><div class="card"><h2>Total Score History</h2><div id="plot-pair-score" style="height:320px;"></div></div><div class="card"><h2>Bias History</h2><div id="plot-pair-bias" style="height:320px;"></div></div></div>
<div class="card" style="margin-top:14px;"><h2>Raw Meta</h2><div id="raw-meta" class="mono"></div></div>
</section>

<section id="tab-compare" class="tab-panel">
<div class="card"><h2>Compare Report Dates</h2><div class="controls"><label class="sub">Date A</label><select id="cmp-a"></select><label class="sub">Date B</label><select id="cmp-b"></select><span id="cmp-flips" class="sub"></span></div></div>
<div class="card" style="margin-top:14px;"><h2>Delta Table (B - A)</h2><div class="table-wrap"><table class="tbl" id="tbl-compare"></table></div></div>
</section>

<section id="tab-quality" class="tab-panel">
<div class="card"><h2>Data Quality Summary</h2><div id="quality-summary" class="sub"></div></div>
<div class="card" style="margin-top:14px;"><h2>Provider Freshness</h2><div class="table-wrap"><table class="tbl" id="tbl-provider"></table></div></div>
<div class="card" style="margin-top:14px;"><h2>Risk Regime Timestamps by Week</h2><div class="table-wrap"><table class="tbl" id="tbl-risk-regime"></table></div></div>
</section>

<section id="tab-methods" class="tab-panel">
<div class="card"><h2>Macro Scoring and Normalization</h2><ul class="method-list" id="methods-score"></ul></div>
<div class="card" style="margin-top:14px;"><h2>Data Quality and Provenance</h2><ul class="method-list" id="methods-quality"></ul></div>
<div class="grid two" style="margin-top:14px;"><div class="card"><h2>Market Overlay</h2><ul class="method-list" id="methods-overlay"></ul></div><div class="card"><h2>Sentiment Overlay</h2><ul class="method-list" id="methods-sentiment"></ul></div></div>
</section>

</div><script>
const DATA=$PAYLOAD_JSON,weeks=DATA.weeks||[],pairs=DATA.pairs||[],rows=DATA.rows||[],scoreCol=DATA.score_col||"total_score",marketOverlay=DATA.market_overlay||{},marketStatus=marketOverlay.status||{},marketReq=marketOverlay.request||{},sentimentOverlay=DATA.sentiment_overlay||{},sentimentStatus=sentimentOverlay.status||{},sentimentEntries=sentimentOverlay.entries||[];
const idx=new Map();for(const row of rows){idx.set(`${String(row.pair||"").toUpperCase()}|${String(row.as_of||"")}`,row)}
const key=(p,w)=>`${String(p||"").toUpperCase()}|${String(w||"")}`;const fmt=(v,d=2)=>v===null||v===undefined||v===""||Number.isNaN(Number(v))?"NA":`${Number(v)>=0?"+":""}${Number(v).toFixed(d)}`;const pct=v=>v===null||v===undefined||v===""||Number.isNaN(Number(v))?"NA":`${(Number(v)*100).toFixed(0)}%`;
const biasNum=b=>b==="BULL_BASE"?1:b==="BEAR_BASE"?-1:0;
const pill=(cls,label)=>`<span class="pill ${cls}">${label}</span>`;
const macroPill=b=>b==="BULL_BASE"?pill("bull","BULL_BASE"):b==="BEAR_BASE"?pill("bear","BEAR_BASE"):pill("neut","NEUTRAL");
const sentPill=b=>b==="BULLISH"?pill("sent-bull","BULLISH"):b==="BEARISH"?pill("sent-bear","BEARISH"):pill("sent-neut","NEUTRAL");
const agreePill=v=>v===true?pill("agree-yes","AGREE"):v===false?pill("agree-no","DISAGREE"):pill("agree-na","N/A");
const freshPill=v=>v===true?pill("stale","STALE"):v===false?pill("fresh","FRESH"):pill("na","N/A");
const marketFor=(p,w)=>((marketOverlay||{}).by_key||{})[key(p,w)]||null;const sentimentFor=(p,w)=>((sentimentOverlay||{}).by_key||{})[key(p,w)]||null;
const defaultPair=pairs[0]||"",defaultWeek=weeks[weeks.length-1]||"";
let overviewWeek=defaultWeek;
function setTab(tab){for(const b of document.querySelectorAll(".tab-btn"))b.classList.remove("active");for(const p of document.querySelectorAll(".tab-panel"))p.classList.remove("active");document.querySelector(`.tab-btn[data-tab="${tab}"]`).classList.add("active");document.getElementById(`tab-${tab}`).classList.add("active")}
for(const b of document.querySelectorAll(".tab-btn"))b.addEventListener("click",()=>setTab(b.dataset.tab));
function fill(sel,vals){for(const v of vals){const o=document.createElement("option");o.value=v;o.textContent=v;sel.appendChild(o)}}
function rowsForWeek(week){return rows.filter(row=>String(row.as_of||"")===String(week||"")).slice().sort((a,b)=>{const av=Number(a[scoreCol]),bv=Number(b[scoreCol]);if(Number.isFinite(av)&&Number.isFinite(bv)&&bv!==av)return bv-av;return String(a.pair||"").localeCompare(String(b.pair||""))})}
function sentimentRowsForWeek(week){return sentimentEntries.filter(row=>String(row.as_of||"")===String(week||"")).slice().sort((a,b)=>String(a.symbol||"").localeCompare(String(b.symbol||"")))}
function overviewKpisForWeek(week){const weekRows=rowsForWeek(week),comparable=weekRows.map(r=>r.sentiment_agrees_with_macro).filter(v=>v===true||v===false);return{pairs_tracked:weekRows.length,macro_bullish:weekRows.filter(r=>(r.final_bias||r.bias)==="BULL_BASE").length,macro_bearish:weekRows.filter(r=>(r.final_bias||r.bias)==="BEAR_BASE").length,macro_neutral:weekRows.filter(r=>(r.final_bias||r.bias)==="NEUTRAL").length,sentiment_coverage:weekRows.filter(r=>r.sentiment_bias!==null&&r.sentiment_bias!==undefined&&r.sentiment_bias!=="").length,sentiment_agreement_rate:comparable.length?(comparable.filter(Boolean).length/comparable.length):null}}
function sentimentSummaryForWeek(week){const weekRows=sentimentRowsForWeek(week),biasCounts={BULLISH:0,BEARISH:0,NEUTRAL:0};let staleCount=0;const comparable=[];for(const row of weekRows){const b=String(row.sentiment_bias||"NEUTRAL");if(Object.prototype.hasOwnProperty.call(biasCounts,b))biasCounts[b]+=1;if(row.sentiment_stale===true)staleCount+=1;if(row.agreement_with_macro===true||row.agreement_with_macro===false)comparable.push(row.agreement_with_macro)}return{coverage_count:weekRows.length,bias_counts:biasCounts,agreement_rate:comparable.length?(comparable.filter(Boolean).length/comparable.length):null,stale_count:staleCount,rows:weekRows}}
function marketOverviewForWeek(week){const byKey=(marketOverlay||{}).by_key||{},target=String(marketReq.symbol||"XAUUSD").toUpperCase(),targetHit=byKey[key(target,week)]||null;if(targetHit)return targetHit;for(const k of Object.keys(byKey).sort()){const row=byKey[k]||{};if(String(row.as_of||"")===String(week||""))return row}return null}
function bindRowClicks(selector){for(const tr of document.querySelectorAll(selector))tr.addEventListener("click",()=>jump(tr.dataset.pair,tr.dataset.week,tr.dataset.tab||"drill"))}
const pairSel=document.getElementById("sel-pair"),weekSel=document.getElementById("sel-week"),sp=document.getElementById("sentiment-pair"),sw=document.getElementById("sentiment-week"),overviewWeekSel=document.getElementById("overview-week");
fill(pairSel,pairs);fill(sp,pairs);fill(weekSel,weeks);fill(sw,weeks);fill(overviewWeekSel,weeks);
function setOverviewWeek(week,opts={}){const resolved=weeks.includes(week)?week:defaultWeek;overviewWeek=resolved;if(overviewWeekSel)overviewWeekSel.value=resolved;renderOverview(resolved);if(opts.syncSelectors===false)return;if(weekSel)weekSel.value=resolved;if(sw)sw.value=resolved;updateDrill();updateSentiment()}
function setSelection(pair,week){const p=pairs.includes(pair)?pair:defaultPair,w=weeks.includes(week)?week:defaultWeek;pairSel.value=p;weekSel.value=w;sp.value=p;sw.value=w;setOverviewWeek(w,{syncSelectors:false});updateDrill();updateSentiment()}
pairSel.addEventListener("change",()=>setSelection(pairSel.value,weekSel.value));weekSel.addEventListener("change",()=>setSelection(pairSel.value,weekSel.value));sp.addEventListener("change",()=>setSelection(sp.value,sw.value));sw.addEventListener("change",()=>setSelection(sp.value,sw.value));overviewWeekSel.addEventListener("change",()=>setOverviewWeek(overviewWeekSel.value));
function jump(pair,week,tab="drill"){setSelection(String(pair||"").toUpperCase(),String(week||""));setTab(tab)}

Plotly.newPlot("plot-bias",[{type:"heatmap",x:weeks,y:pairs,z:DATA.heatmaps.bias,zmin:-1,zmax:1,hovertemplate:"<b>%{y}</b><br>%{x}<br>Bias=%{z}<extra></extra>",colorscale:[[0,"#ff9ca7"],[.5,"#9eb3c9"],[1,"#8fd8a1"]]}],{margin:{l:120,r:14,t:8,b:35},paper_bgcolor:"rgba(0,0,0,0)",plot_bgcolor:"rgba(0,0,0,0)",font:{color:"#edf5ff"}},{displayModeBar:false}).then(gd=>gd.on("plotly_click",ev=>jump(ev.points[0].y,ev.points[0].x)));
Plotly.newPlot("plot-score",[{type:"heatmap",x:weeks,y:pairs,z:DATA.heatmaps.score,hovertemplate:"<b>%{y}</b><br>%{x}<br>Score=%{z:.3f}<extra></extra>"}],{margin:{l:120,r:14,t:8,b:35},paper_bgcolor:"rgba(0,0,0,0)",plot_bgcolor:"rgba(0,0,0,0)",font:{color:"#edf5ff"}},{displayModeBar:false}).then(gd=>gd.on("plotly_click",ev=>jump(ev.points[0].y,ev.points[0].x)));
Plotly.newPlot("plot-conv",[{type:"heatmap",x:weeks,y:pairs,z:DATA.heatmaps.conviction,zmin:0,zmax:1,hovertemplate:"<b>%{y}</b><br>%{x}<br>|score|=%{z:.3f}<extra></extra>"}],{margin:{l:120,r:14,t:8,b:35},paper_bgcolor:"rgba(0,0,0,0)",plot_bgcolor:"rgba(0,0,0,0)",font:{color:"#edf5ff"}},{displayModeBar:false}).then(gd=>gd.on("plotly_click",ev=>jump(ev.points[0].y,ev.points[0].x)));
const cnt=DATA.counts||{index:[],columns:[],values:[]};Plotly.newPlot("plot-counts",(cnt.columns||[]).map((c,i)=>({type:"bar",name:c,x:cnt.index,y:(cnt.values||[]).map(v=>v[i]||0)})),{barmode:"stack",margin:{l:34,r:10,t:8,b:34},paper_bgcolor:"rgba(0,0,0,0)",plot_bgcolor:"rgba(0,0,0,0)",font:{color:"#edf5ff"},legend:{orientation:"h",y:-.25}},{displayModeBar:false});

function renderOverview(week){
 const activeWeek=weeks.includes(week)?week:defaultWeek,k=overviewKpisForWeek(activeWeek),sentWeek=sentimentSummaryForWeek(activeWeek);document.getElementById("kpi-pairs").textContent=k.pairs_tracked??"NA";document.getElementById("kpi-bull").textContent=k.macro_bullish??"NA";document.getElementById("kpi-bear").textContent=k.macro_bearish??"NA";document.getElementById("kpi-neut").textContent=k.macro_neutral??"NA";document.getElementById("kpi-cover").textContent=k.sentiment_coverage??"NA";document.getElementById("kpi-agree").textContent=pct(k.sentiment_agreement_rate);document.getElementById("overview-meta").textContent=activeWeek?`Active report week ${activeWeek}`:"No report weeks available.";
 document.getElementById("exec-macro").textContent=`${k.pairs_tracked||0} pairs tracked for ${activeWeek||"NA"} with ${k.macro_bullish||0} bullish, ${k.macro_bearish||0} bearish, and ${k.macro_neutral||0} neutral macro calls.`;
 document.getElementById("exec-sentiment").textContent=!sentimentOverlay.requested?"Sentiment overlay was not requested for this run.":!sentWeek.coverage_count?`${sentimentStatus.message||"Sentiment overlay unavailable."}`:`Coverage ${sentWeek.coverage_count||0} | bullish ${(sentWeek.bias_counts||{}).BULLISH||0} | bearish ${(sentWeek.bias_counts||{}).BEARISH||0} | agreement ${pct(sentWeek.agreement_rate)}.`;
 document.getElementById("exec-scope").textContent=`Core engine: rates, growth, risk, positioning. Active week ${activeWeek||"NA"} stays fully date-switchable and overlay layers remain informational only.`;
 const ovLatest=marketOverviewForWeek(activeWeek),ovNode=document.getElementById("overlay-summary"),ovTitle=document.getElementById("overlay-title");ovTitle.textContent=`Market Overlay Summary (${String((ovLatest&&ovLatest.symbol)||marketReq.symbol||"XAUUSD").toUpperCase()})`;ovNode.innerHTML=!ovLatest?`${marketStatus.message||"Overlay unavailable."}${marketStatus.hint?`<br/>${marketStatus.hint}`:""}`:`${sentPill(ovLatest.label||"NEUTRAL")} rr10=${fmt(ovLatest.rr10,2)} | rr25=${fmt(ovLatest.rr25,2)} | atm_iv=${fmt(ovLatest.approx_atm_iv,2)} | tenor=${ovLatest.tenor||"NA"} | expiry=${ovLatest.expiry_date||"NA"} | as_of=${ovLatest.as_of||"NA"}`;
 const sNode=document.getElementById("sentiment-overview");sNode.innerHTML=!sentimentOverlay.requested?`${sentimentStatus.message||"Sentiment overlay not requested."}${sentimentStatus.hint?`<br/>${sentimentStatus.hint}`:""}`:!sentWeek.coverage_count?`${sentimentStatus.message||"Sentiment overlay unavailable."}${sentimentStatus.hint?`<br/>${sentimentStatus.hint}`:""}`:`Coverage=${sentWeek.coverage_count||0} | Bullish=${(sentWeek.bias_counts||{}).BULLISH||0} | Bearish=${(sentWeek.bias_counts||{}).BEARISH||0} | Neutral=${(sentWeek.bias_counts||{}).NEUTRAL||0} | Agreement=${pct(sentWeek.agreement_rate)} | Stale=${sentWeek.stale_count||0}`;
 const leaderboardRows=rowsForWeek(activeWeek).map(r=>`<tr class="row-click" data-pair="${String(r.pair||"").toUpperCase()}" data-week="${r.as_of||""}"><td>${String(r.pair||"").toUpperCase()}</td><td>${fmt(r.rates,2)}</td><td>${fmt(r.growth,2)}</td><td>${fmt(r.risk,2)}</td><td>${fmt(r.positioning,2)}</td><td>${fmt(r[scoreCol],2)}</td><td>${r.conviction_tier||"NA"}</td><td>${macroPill(r.final_bias||r.bias||"NEUTRAL")}</td><td>${r.overall_staleness_flag?"STALE":""}</td></tr>`).join("");document.getElementById("leaderboard-title").textContent=`Leaderboard (${activeWeek||"NA"})`;document.getElementById("tbl-overview-leaderboard").innerHTML=`<thead><tr><th>Pair</th><th>Rates</th><th>Growth</th><th>Risk</th><th>Positioning</th><th>Total</th><th>Conviction</th><th>Bias</th><th>Staleness</th></tr></thead><tbody>${leaderboardRows}</tbody>`;bindRowClicks("#tbl-overview-leaderboard tr.row-click");
 const inst=((DATA.report_notes||{}).instrument_notes||{}),keys=Object.keys(inst).sort(),node=document.getElementById("instrument-notes");node.innerHTML=!keys.length?"No instrument notes configured.":`<div class="table-wrap"><table class="tbl"><thead><tr><th>Instrument</th><th>Rationale</th></tr></thead><tbody>${keys.map(k=>`<tr><td>${k}</td><td class="wrap">${inst[k]}</td></tr>`).join("")}</tbody></table></div>`;
}
function renderSentimentTable(week){const activeWeek=weeks.includes(week)?week:defaultWeek,weekRows=sentimentSummaryForWeek(activeWeek).rows.map(item=>{const macro=idx.get(key(item.symbol,item.as_of));return `<tr class="row-click" data-pair="${item.symbol}" data-week="${item.as_of}" data-tab="sentiment"><td>${item.symbol}</td><td>${macro?macroPill(macro.final_bias||macro.bias||"NEUTRAL"):"NA"}</td><td>${sentPill(item.sentiment_bias)}</td><td>${fmt(item.sentiment_score,3)}</td><td>${item.sentiment_conviction||"NA"}</td><td>${agreePill(item.agreement_with_macro)}</td><td>${freshPill(item.sentiment_stale)}</td><td class="wrap">${item.headline_summary||""}</td></tr>`}).join("");document.getElementById("sentiment-week-title").textContent=`Sentiment Table (${activeWeek||"NA"})`;document.getElementById("tbl-sentiment-latest").innerHTML=`<thead><tr><th>Pair</th><th>Macro Bias</th><th>Sentiment Bias</th><th>Score</th><th>Conviction</th><th>Agreement</th><th>Freshness</th><th>Summary</th></tr></thead><tbody>${weekRows}</tbody>`;bindRowClicks("#tbl-sentiment-latest tr.row-click")}
function updateSentiment(){
 const pair=String(sp.value||"").toUpperCase(),week=String(sw.value||""),row=idx.get(key(pair,week)),sent=sentimentFor(pair,week);document.getElementById("sentiment-selection-meta").textContent=`ID=${key(pair,week)}`;renderSentimentTable(week);
 document.getElementById("s-macro-bias").innerHTML=row?macroPill(row.final_bias||row.bias||"NEUTRAL"):"NA";document.getElementById("s-macro-score").textContent=row?fmt(row[scoreCol],3):"NA";document.getElementById("s-sent-bias").innerHTML=sent?sentPill(sent.sentiment_bias):"NA";document.getElementById("s-sent-score").textContent=sent?fmt(sent.sentiment_score,3):"NA";document.getElementById("s-agreement").innerHTML=sent?agreePill(sent.agreement_with_macro):agreePill(null);document.getElementById("s-freshness").innerHTML=sent?freshPill(sent.sentiment_stale):freshPill(null);
 document.getElementById("sentiment-summary-text").innerHTML=!sent?`${sentimentStatus.message||"No sentiment overlay for this pair/date."}${sentimentStatus.hint?`<br/>${sentimentStatus.hint}`:""}`:(sent.headline_summary||"No sentiment summary available.");
 const signalRows=sent&&sent.signals_table?sent.signals_table.map(s=>`<tr><td>${s.signal_name}</td><td>${s.available?"YES":"NO"}</td><td>${sentPill(s.bias)}</td><td>${fmt(s.score,3)}</td><td>${fmt(s.weight,2)}</td><td>${fmt(s.contribution,3)}</td><td>${s.obs_date||"NA"}</td><td>${s.stale?"YES":""}</td><td class="wrap">${JSON.stringify(s.meta||{})}</td></tr>`).join(""):"";document.getElementById("tbl-sentiment-signals").innerHTML=`<thead><tr><th>Signal</th><th>Available</th><th>Bias</th><th>Score</th><th>Weight</th><th>Contribution</th><th>obs_date</th><th>stale</th><th>meta</th></tr></thead><tbody>${signalRows}</tbody>`;
}
function updateDrill(){
 const pair=String(pairSel.value||"").toUpperCase(),week=String(weekSel.value||""),row=idx.get(key(pair,week)),sent=sentimentFor(pair,week);document.getElementById("sel-meta").textContent=`ID=${key(pair,week)}`;
 if(!row){for(const id of["k-bias","k-score","k-conv","k-stale","k-sent-bias","k-sent-align"])document.getElementById(id).textContent="NA";return}
 document.getElementById("k-bias").innerHTML=macroPill(row.final_bias||row.bias||"NEUTRAL");document.getElementById("k-score").textContent=fmt(row[scoreCol],3);document.getElementById("k-conv").textContent=row.conviction_tier||"NA";document.getElementById("k-stale").innerHTML=freshPill(!!row.overall_staleness_flag);document.getElementById("k-sent-bias").innerHTML=sent?sentPill(sent.sentiment_bias):"NA";document.getElementById("k-sent-align").innerHTML=sent?agreePill(sent.agreement_with_macro):agreePill(null);
 document.getElementById("tbl-pillars").innerHTML=`<thead><tr><th>Pillar</th><th>Score</th><th>Raw</th></tr></thead><tbody>${["rates","growth","risk","positioning"].map(p=>`<tr><td>${p}</td><td>${fmt(row[p],3)}</td><td>${fmt(row[p+"_raw"],4)}</td></tr>`).join("")}</tbody>`;
 document.getElementById("tbl-prov").innerHTML=`<thead><tr><th>Pillar</th><th>obs_date</th><th>age_days</th><th>stale</th></tr></thead><tbody>${[["rates",row.rates_obs_date,row.rates_age_days,row.rates_stale],["growth",row.growth_obs_date,row.growth_age_days,row.growth_stale],["risk",row.risk_obs_date,row.risk_age_days,row.risk_stale],["positioning",row.pos_obs_date,row.pos_age_days,row.pos_stale]].map(x=>`<tr><td>${x[0]}</td><td>${x[1]||"NA"}</td><td>${x[2]??"NA"}</td><td>${x[3]?"YES":""}</td></tr>`).join("")}</tbody>`;
 const ov=marketFor(pair,week),ovNode=document.getElementById("overlay-drill");ovNode.innerHTML=!ov?`${marketStatus.message||"No options overlay for this pair/date."}${marketStatus.hint?`<br/>${marketStatus.hint}`:""}`:`${sentPill(ov.label||"NEUTRAL")} rr10=${fmt(ov.rr10,2)} | rr25=${fmt(ov.rr25,2)} | atm_iv=${fmt(ov.approx_atm_iv,2)} | tenor=${ov.tenor||"NA"} | expiry=${ov.expiry_date||"NA"} | as_of=${ov.as_of||"NA"}`;
 const sentNode=document.getElementById("sentiment-drill");sentNode.innerHTML=!sent?`${sentimentStatus.message||"No sentiment overlay for this pair/date."}${sentimentStatus.hint?`<br/>${sentimentStatus.hint}`:""}`:`${sentPill(sent.sentiment_bias)} score=${fmt(sent.sentiment_score,3)} | conviction=${sent.sentiment_conviction||"NA"} | ${agreePill(sent.agreement_with_macro)} | ${freshPill(sent.sentiment_stale)}<br/>${sent.headline_summary||""}`;
 Plotly.newPlot("plot-pair-score",[{type:"scatter",mode:"lines+markers",x:weeks,y:weeks.map(w=>{const rw=idx.get(key(pair,w));const v=rw?Number(rw[scoreCol]):NaN;return Number.isNaN(v)?null:v}),hovertemplate:`<b>${pair}</b><br>%{x}<br>score=%{y:.3f}<extra></extra>`,line:{color:"#6ec0ff"}}],{margin:{l:38,r:10,t:8,b:36},paper_bgcolor:"rgba(0,0,0,0)",plot_bgcolor:"rgba(0,0,0,0)",font:{color:"#edf5ff"}},{displayModeBar:false});
 Plotly.newPlot("plot-pair-bias",[{type:"scatter",mode:"lines+markers",x:weeks,y:weeks.map(w=>{const rw=idx.get(key(pair,w));return biasNum(rw?(rw.final_bias||rw.bias):"NEUTRAL")}),hovertemplate:`<b>${pair}</b><br>%{x}<br>bias=%{y}<extra></extra>`,line:{color:"#8fd8a1"}}],{margin:{l:38,r:10,t:8,b:36},paper_bgcolor:"rgba(0,0,0,0)",plot_bgcolor:"rgba(0,0,0,0)",font:{color:"#edf5ff"},yaxis:{tickvals:[-1,0,1],ticktext:["BEAR","NEUTRAL","BULL"]}},{displayModeBar:false});
 document.getElementById("raw-meta").textContent=JSON.stringify({pair:pair,as_of:week,total_score:row[scoreCol],final_bias:row.final_bias||row.bias,sentiment:sent?{sentiment_bias:sent.sentiment_bias,sentiment_score:sent.sentiment_score,agreement_with_macro:sent.agreement_with_macro,sentiment_stale:sent.sentiment_stale,signals:sent.signals||{}}:null,pillar_meta:row._pillar_meta||{}},null,2);
}
const cmpA=document.getElementById("cmp-a"),cmpB=document.getElementById("cmp-b");fill(cmpA,weeks);fill(cmpB,weeks);const cmpDef=DATA.compare||{};cmpA.value=cmpDef.default_a||(weeks.length>1?weeks[weeks.length-2]:(weeks[0]||""));cmpB.value=cmpDef.default_b||(weeks[weeks.length-1]||"");
function renderCompare(){const a=String(cmpA.value||""),b=String(cmpB.value||""),k=`${a}|${b}`,rows=((DATA.compare||{}).by_key||{})[k]||[];document.getElementById("tbl-compare").innerHTML=`<thead><tr><th>Pair</th><th>dRates</th><th>dGrowth</th><th>dRisk</th><th>dPos</th><th>dTotal</th><th>Bias A</th><th>Bias B</th><th>Flip</th><th>Persistence@B</th></tr></thead><tbody>${rows.map(r=>{const flip=r.flip||"";const cls=flip==="BULL->BEAR"||flip==="BEAR->BULL"?"flip-bad":flip==="->NEUTRAL"?"flip-neutral":"";return `<tr><td>${r.pair}</td><td>${fmt(r.delta_rates,3)}</td><td>${fmt(r.delta_growth,3)}</td><td>${fmt(r.delta_risk,3)}</td><td>${fmt(r.delta_positioning,3)}</td><td>${fmt(r.delta_total_score,3)}</td><td>${r.bias_a||"NA"}</td><td>${r.bias_b||"NA"}</td><td class="${cls}">${flip}</td><td>${r.persistence_b??"NA"}</td></tr>`}).join("")}</tbody>`;const f=((DATA.compare||{}).flip_counts||{})[k]||{};document.getElementById("cmp-flips").textContent=`Flips: B->S ${f["BULL->BEAR"]||0}, S->B ${f["BEAR->BULL"]||0}, ->N ${f["->NEUTRAL"]||0}`}
cmpA.addEventListener("change",renderCompare);cmpB.addEventListener("change",renderCompare);
function renderQuality(){const dq=DATA.data_quality||{};document.getElementById("quality-summary").innerHTML=`Overall stale rate: <b>${((dq.overall_stale_rate||0)*100).toFixed(1)}%</b><br/>Stale counts per pillar: <span class="mono">${JSON.stringify(dq.stale_counts||{})}</span><br/>Most stale provider: <b>${dq.most_stale_provider||"NA"}</b>`;document.getElementById("tbl-provider").innerHTML=`<thead><tr><th>Provider</th><th>Stale Count</th><th>Last Updated</th></tr></thead><tbody>${(dq.provider_summary||[]).map(p=>`<tr><td>${p.provider}</td><td>${p.stale_count}</td><td>${p.last_updated||"NA"}</td></tr>`).join("")}</tbody>`;document.getElementById("tbl-risk-regime").innerHTML=`<thead><tr><th>as_of</th><th>risk_obs</th><th>spx</th><th>vix</th><th>dxy</th><th>stale_components</th></tr></thead><tbody>${(weeks||[]).map(w=>{const m=(DATA.meta_by_week||{})[w]||{},r=m.risk_regime||{};return `<tr><td>${w}</td><td>${r.obs_date||"NA"}</td><td>${r.spx_obs_date||"NA"}</td><td>${r.vix_obs_date||"NA"}</td><td>${r.dxy_obs_date||"NA"}</td><td class="wrap">${(r.stale_components||[]).join(", ")}</td></tr>`}).join("")}</tbody>`}
const fillMethods=(id,rows)=>document.getElementById(id).innerHTML=(rows||[]).map(x=>`<li>${x}</li>`).join("");
renderOverview();renderCompare();renderQuality();fillMethods("methods-score",(DATA.methods||{}).scoring||[]);fillMethods("methods-quality",(DATA.methods||{}).quality||[]);fillMethods("methods-overlay",(DATA.methods||{}).overlay||[]);fillMethods("methods-sentiment",(DATA.methods||{}).sentiment||[]);setSelection(defaultPair,defaultWeek);
</script></body></html>"""
    )
    return tmpl.safe_substitute(
        WEEK_START=week_start,
        WEEK_END=week_end,
        GENERATED=generated,
        LATEST_WEEK=latest,
        LATEST_ROWS=latest_rows_html,
        PAYLOAD_JSON=payload_json,
    )
