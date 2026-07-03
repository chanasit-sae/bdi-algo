"""Zero-dependency visualization server for the SMART-ICU ventilator sample.

Serves an interactive dashboard (pick patient -> pick capture -> plot
Flow/Pressure/Volume + view metadata) using only the Python standard library
and vanilla JS. No pip installs, no CDN, runs offline.

    python3 backend/viz_server.py [--port 8000] [--data DIR]
    -> open http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import numpy as np

from parser import load_dataset, metadata_frame, load_waveform, SAMPLE_RATE_HZ
from breath_segment import segment_capture, estimate_baseline
from breath_metrics import add_metrics

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "smart_icu_data"


def _denan(obj):
    """Recursively replace float NaN with None so output is valid JSON.

    pandas leaves NaN in numeric columns even after .where(); json.dumps emits
    bare `NaN`, which Python accepts but browsers' JSON.parse rejects.
    """
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _denan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_denan(v) for v in obj]
    return obj


MIN_FLOW_RANGE = 5.0  # L/min; below this the flow is flat -> ventilator not on a patient


def _is_connected(data_dir: Path, fname: str) -> bool:
    """True if the flow has real breathing excursion (not a flat/disconnected trace)."""
    flow = load_waveform(data_dir / fname)["flow"]
    return float(flow.max() - flow.min()) >= MIN_FLOW_RANGE


def build_index(data_dir: Path) -> dict:
    """Flattened metadata grouped by patient, plus the set of valid CSV names.

    Every capture is included; captures whose flow is flat (no breathing,
    ventilator not connected to a patient) are tagged connected=False so the
    frontend can hide them by default and reveal them on demand.
    """
    records = load_dataset(data_dir)
    df = metadata_frame(records)
    captures = df.dropna(subset=["raw_data"]).where(df.notna(), None)
    rows = captures.to_dict(orient="records")
    connected = {r["raw_data"]: _is_connected(data_dir, r["raw_data"]) for r in rows}
    valid = {r["raw_data"] for r in rows}
    patients: dict[str, dict] = {}
    for r in rows:
        pid = r["patient_id"]
        p = patients.setdefault(
            pid,
            {
                "patient_id": pid,
                "age": r["age"],
                "sex": r["sex"],
                "bw_kg": r["bw_kg"],
                "ht_cm": r["ht_cm"],
                "bmi": r["bmi"],
                "ven": r["ven"],
                "captures": [],
            },
        )
        p["captures"].append(
            {
                "raw_data": r["raw_data"],
                "day": r["day"],
                "time": r["capture_time"],
                "pdx": r["pdx"],
                "pdx_icd": r["pdx_icd"],
                "sdx": r["sdx"],
                "sdx_icd": r["sdx_icd"],
                "operation": r["operation"],
                "connected": connected[r["raw_data"]],
            }
        )
    return {"patients": list(patients.values()), "valid": valid}


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Ventilator Waveform Viewer</title>
<style>
  :root { --bg:#0f1720; --panel:#16212e; --fg:#dbe4ee; --muted:#8ea1b5;
          --flow:#4fc3f7; --press:#ff8a65; --vol:#81c784; --slope:#ba68c8; --line:#2b3a4a; }
  * { box-sizing: border-box; }
  body { margin:0; font:14px/1.5 system-ui,sans-serif; background:var(--bg); color:var(--fg); }
  header { padding:12px 18px; background:var(--panel); border-bottom:1px solid var(--line);
           display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
  header h1 { font-size:15px; margin:0; font-weight:600; }
  select { background:#0b1119; color:var(--fg); border:1px solid var(--line);
           border-radius:6px; padding:6px 8px; font-size:13px; }
  label { color:var(--muted); font-size:12px; margin-right:4px; }
  main { display:grid; grid-template-columns: 1fr 300px; gap:16px; padding:16px; }
  .charts { display:flex; flex-direction:column; gap:14px; }
  .chart-card { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:10px 12px; }
  .chart-card h3 { margin:0 0 6px; font-size:13px; font-weight:600; }
  canvas { width:100%; height:180px; display:block; }
  aside { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; height:max-content; }
  aside h2 { font-size:13px; margin:0 0 10px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; }
  .kv { display:grid; grid-template-columns:auto 1fr; gap:4px 10px; font-size:13px; }
  .kv dt { color:var(--muted); }
  .kv dd { margin:0; word-break:break-word; }
  .swatch { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:middle; }
  .muted { color:var(--muted); }
</style>
</head>
<body>
<header>
  <h1>Ventilator Waveform Viewer</h1>
  <div><label>Patient</label><select id="patient"></select></div>
  <div><label>Capture</label><select id="capture"></select></div>
  <div><label>Breath</label><select id="breath"></select></div>
  <div><label title="crossing baseline: zero, auto = per-capture low-percentile offset, manual = the offset field, slope = adaptive slope-change onset detection (level-agnostic)">Baseline</label>
    <select id="baseline"><option value="zero">zero</option><option value="auto">auto</option><option value="manual">manual</option><option value="slope">slope</option></select></div>
  <div><label title="manual crossing-baseline offset (L/min); used when Baseline = manual">Offset</label>
    <input id="baseoff" type="number" value="0" step="1" style="width:64px;
      background:#0b1119;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:13px"></div>
  <div><label title="dead-band around baseline (L/min) to reject noise crossings">Hysteresis</label>
    <input id="hyst" type="number" value="0" min="0" step="1" style="width:64px;
      background:#0b1119;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:13px"></div>
  <div><label title="min flow rise rate (L/min per second) at inspiration onset; both this and hysteresis must be met to mark a breath. ~30 recommended">Slope</label>
    <input id="slope" type="number" value="30" min="0" step="1" style="width:64px;
      background:#0b1119;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:13px"></div>
  <div><label title="Baseline=slope: slope jump (L/min per second) above the recent trend that flags a breath start">&Delta;slope</label>
    <input id="sdelta" type="number" value="100" min="0" step="5" style="width:64px;
      background:#0b1119;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:13px"></div>
  <div><label title="Baseline=slope: trailing trend window in seconds">Win s</label>
    <input id="swin" type="number" value="0.32" min="0.04" step="0.04" style="width:64px;
      background:#0b1119;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:13px"></div>
  <div><label title="Baseline=slope: min spacing between onsets in seconds; suppresses the expiratory-recovery double-fire">Refr s</label>
    <input id="srefr" type="number" value="1.0" min="0" step="0.1" style="width:64px;
      background:#0b1119;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:13px"></div>
  <div><label title="Baseline=slope: drop onsets preceded by a steep flow DECREASE (expiratory limb); pre-onset slope below this magnitude (L/min per second) is rejected. 0 = off">ExpGuard</label>
    <input id="sguard" type="number" value="100" min="0" step="10" style="width:64px;
      background:#0b1119;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:13px"></div>
  <div><label title="Baseline=slope: min peak inspiratory flow (L/min) the rise must reach for an onset to count; ~60-90 for a normal adult. 0 = off. Tick 'avg' to use the whole-capture average flow as the threshold instead.">PeakMin</label>
    <input id="speak" type="number" value="60" min="0" step="5" style="width:64px;
      background:#0b1119;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:13px">
    <label style="font-weight:400;margin-left:4px" title="use the whole-capture average flow as the PeakMin threshold"><input id="speakMean" type="checkbox" style="vertical-align:middle"> avg</label></div>
  <div><label title="also list flat captures where the ventilator is not connected to a patient">Show disconnected</label>
    <input id="showDisc" type="checkbox"></div>
  <span class="muted" id="status"></span>
</header>
<main>
  <div class="charts">
    <div class="chart-card"><h3><span class="swatch" style="background:var(--flow)"></span>Flow (L/min)</h3><canvas id="c-flow"></canvas></div>
    <div class="chart-card"><h3><span class="swatch" style="background:var(--press)"></span>Pressure (cmH2O)</h3><canvas id="c-pressure"></canvas></div>
    <div class="chart-card"><h3><span class="swatch" style="background:var(--vol)"></span>Volume (mL)</h3><canvas id="c-volume"></canvas></div>
    <div class="chart-card"><h3><span class="swatch" style="background:var(--slope)"></span>Flow slope (L/min/s)</h3><canvas id="c-slope"></canvas></div>
  </div>
  <aside>
    <h2>Metadata</h2>
    <dl class="kv" id="meta"></dl>
    <h2 style="margin-top:16px">Breath</h2>
    <dl class="kv" id="breath-meta"><dd class="muted">select a breath</dd></dl>
  </aside>
</main>
<script>
const COLORS = { flow:'#4fc3f7', pressure:'#ff8a65', volume:'#81c784', slope:'#ba68c8' };
const INSP_FILL = 'rgba(79,195,247,0.13)';   // inspiration band
const EXP_FILL  = 'rgba(255,138,101,0.13)';  // expiration band
let INDEX = null;
let CUR = { file:null, wf:null, breaths:[] };  // current capture state

async function j(url){ const r = await fetch(location.origin + url); if(!r.ok) throw new Error(await r.text()); return r.json(); }

function drawChart(canvasId, t, y, color, breaths, sel, baseVal){
  const cv = document.getElementById(canvasId);
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  cv.width = w*dpr; cv.height = h*dpr;
  const ctx = cv.getContext('2d'); ctx.scale(dpr,dpr);
  ctx.clearRect(0,0,w,h);
  const padL=46, padR=8, padT=8, padB=20;
  const plotW=w-padL-padR, plotH=h-padT-padB;
  if(!y.length){ return; }
  let ymin=Math.min(...y), ymax=Math.max(...y);
  if(ymin===ymax){ ymin-=1; ymax+=1; }
  const tmax = t[t.length-1] || 1;
  const Xt = tt => padL + (tt/tmax)*plotW;   // time (s) -> px
  const Y = v => padT + (1-(v-ymin)/(ymax-ymin))*plotH;

  // phase bands for the selected breath
  if(sel){
    ctx.fillStyle=INSP_FILL;
    ctx.fillRect(Xt(sel.t_insp_start), padT, Xt(sel.t_insp_end)-Xt(sel.t_insp_start), plotH);
    ctx.fillStyle=EXP_FILL;
    ctx.fillRect(Xt(sel.t_insp_end), padT, Xt(sel.t_exp_end)-Xt(sel.t_insp_end), plotH);
  }
  // faint breath-boundary lines (inspiration onsets)
  if(breaths && breaths.length){
    ctx.strokeStyle='#3a4c60'; ctx.lineWidth=1;
    for(const b of breaths){ const x=Xt(b.t_insp_start);
      ctx.beginPath(); ctx.moveTo(x,padT); ctx.lineTo(x,padT+plotH); ctx.stroke(); }
  }
  // grid + y labels
  ctx.strokeStyle='#2b3a4a'; ctx.fillStyle='#8ea1b5'; ctx.font='11px system-ui'; ctx.lineWidth=1;
  for(let g=0; g<=4; g++){
    const yy=padT+g/4*plotH, val=ymax-(g/4)*(ymax-ymin);
    ctx.beginPath(); ctx.moveTo(padL,yy); ctx.lineTo(w-padR,yy); ctx.stroke();
    ctx.fillText(val.toFixed(0), 4, yy+3);
  }
  if(ymin<0 && ymax>0){ ctx.strokeStyle='#43586e'; ctx.beginPath();
    ctx.moveTo(padL,Y(0)); ctx.lineTo(w-padR,Y(0)); ctx.stroke(); }
  // crossing baseline (dashed) — the level segmentation splits insp/exp on
  if(baseVal!=null && baseVal>ymin && baseVal<ymax){
    ctx.strokeStyle='#d08770'; ctx.setLineDash([4,3]); ctx.beginPath();
    ctx.moveTo(padL,Y(baseVal)); ctx.lineTo(w-padR,Y(baseVal)); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle='#d08770'; ctx.fillText(baseVal.toFixed(1), padL+2, Y(baseVal)-3); }
  ctx.fillStyle='#8ea1b5';
  ctx.fillText('0s', padL, h-6); ctx.fillText(tmax.toFixed(1)+'s', w-padR-24, h-6);
  // series
  ctx.strokeStyle=color; ctx.lineWidth=1.6; ctx.beginPath();
  for(let i=0;i<y.length;i++){ const xx=Xt(t[i]), yy=Y(y[i]); i?ctx.lineTo(xx,yy):ctx.moveTo(xx,yy); }
  ctx.stroke();
}

function renderCharts(sel){
  const wf = CUR.wf; if(!wf) return;
  drawChart('c-flow', wf.t_sec, wf.flow, COLORS.flow, CUR.breaths, sel, CUR.baseline);
  drawChart('c-pressure', wf.t_sec, wf.pressure, COLORS.pressure, CUR.breaths, sel, null);
  drawChart('c-volume', wf.t_sec, wf.volume, COLORS.volume, CUR.breaths, sel, null);
  const slopeRef = (document.getElementById('baseline').value === 'slope')
    ? (parseFloat(document.getElementById('sdelta').value) || 0)
    : (parseFloat(document.getElementById('slope').value) || 0);
  drawChart('c-slope', wf.t_sec, wf.slope, COLORS.slope, CUR.breaths, sel, slopeRef || null);
}

async function selectCapture(file){
  document.getElementById('status').textContent = 'loading '+file+' ...';
  const hyst = parseFloat(document.getElementById('hyst').value) || 0;
  const slope = parseFloat(document.getElementById('slope').value) || 0;
  const sdelta = parseFloat(document.getElementById('sdelta').value) || 0;
  const swin = parseFloat(document.getElementById('swin').value) || 0.32;
  const srefr = parseFloat(document.getElementById('srefr').value) || 0;
  const sguard = parseFloat(document.getElementById('sguard').value) || 0;
  const speak = document.getElementById('speakMean').checked
    ? 'mean' : (parseFloat(document.getElementById('speak').value) || 0);
  const mode = document.getElementById('baseline').value;
  const baseline = (mode === 'manual')
    ? (parseFloat(document.getElementById('baseoff').value) || 0)
    : mode;
  const [wf, br] = await Promise.all([
    j('/api/waveform?file='+encodeURIComponent(file)),
    j('/api/breaths?file='+encodeURIComponent(file)+'&hysteresis='+hyst+'&baseline='+baseline
      +'&slope='+slope+'&sdelta='+sdelta+'&swin='+swin+'&srefr='+srefr+'&sguard='+sguard+'&speak='+speak),
  ]);
  CUR = { file, wf, breaths: br.breaths, baseline: br.baseline };
  const n = wf.t_sec.length, dur = wf.t_sec[n-1] || 0;
  document.getElementById('status').textContent =
    `${n} samples · ${dur.toFixed(1)}s @ 25Hz · ${CUR.breaths.length} breaths`;
  fillBreaths();
  renderCharts(null);
  renderMeta(file);
  renderBreathMeta(null);
}

function fillBreaths(){
  const sel = document.getElementById('breath');
  const opts = ['<option value="-1">— whole capture —</option>'];
  CUR.breaths.forEach((b,i)=> opts.push(
    `<option value="${i}">breath ${b.breath_idx} · ${b.t_insp_start.toFixed(2)}–${b.t_exp_end.toFixed(2)}s${b.is_complete?'':' (partial)'}</option>`));
  sel.innerHTML = opts.join('');
  sel.value = '-1';
}

function onBreathChange(){
  const i = parseInt(document.getElementById('breath').value, 10);
  const sel = (i>=0) ? CUR.breaths[i] : null;
  renderCharts(sel);
  renderBreathMeta(sel);
}

function renderMeta(file){
  const p = INDEX.patients.find(p=>p.captures.some(c=>c.raw_data===file));
  const c = p.captures.find(c=>c.raw_data===file);
  const rows = [
    ['Patient', p.patient_id],
    ['Sex / Age', (p.sex||'?')+' · '+(p.age??'?')+' yr'],
    ['BW / HT', (p.bw_kg??'—')+' kg / '+(p.ht_cm??'—')+' cm'],
    ['BMI', p.bmi??'—'],
    ['Ventilator', p.ven??'—'],
    ['ICU day', c.day??'—'],
    ['Time', c.time??'—'],
    ['PDx', c.pdx? c.pdx : '—'],
    ['SDx', c.sdx? c.sdx : '—'],
    ['Operation', c.operation? c.operation : '—'],
    ['File', c.raw_data],
  ];
  document.getElementById('meta').innerHTML =
    rows.map(([k,v])=>`<dt>${k}</dt><dd>${v}</dd>`).join('');
}

function renderBreathMeta(b){
  const el = document.getElementById('breath-meta');
  if(!b){ el.innerHTML = '<dd class="muted">select a breath</dd>'; return; }
  const f = (v,d=2)=> v==null? '—' : (+v).toFixed(d);
  const rows = [
    ['Index', b.breath_idx + (b.is_complete? '' : ' (partial)')],
    ['<span class="swatch" style="background:'+COLORS.flow+'"></span>Inspiration', f(b.ti_sec,2)+' s'],
    ['<span class="swatch" style="background:'+COLORS.press+'"></span>Expiration', f(b.te_sec,2)+' s'],
    ['I:E', b.ie_ratio==null? '—' : '1 : '+f(1/b.ie_ratio,2)],
    ['Cycle time', f(b.cycle_time_sec,2)+' s'],
    ['Duty (Ti/Ttot)', f(b.duty_cycle,2)],
    ['Rate', f(b.rr_bpm,1)+' /min'],
    ['Tidal vol', f(b.tidal_volume_ml,1)+' mL'],
    ['Vt insp / exp', f(b.vti_ml,0)+' / '+f(b.vte_ml,0)+' mL'],
    ['Leak', f(b.leak_ml,0)+' mL'],
    ['Peak flow insp', f(b.peak_insp_flow,1)+' L/min'],
    ['Peak flow exp', f(b.peak_exp_flow,1)+' L/min'],
    ['Mean insp flow', f(b.mean_insp_flow,1)+' L/min'],
    ['Time to peak', f(b.time_to_peak_flow_sec,2)+' s'],
    ['End-exp flow', f(b.end_exp_flow,1)+' L/min'],
    ['Flow shape', f(b.flow_shape_ratio,2)],
    ['PIP', f(b.pip_cmh2o,1)+' cmH₂O'],
    ['Plateau', f(b.plateau_pressure_cmh2o,1)+' cmH₂O'],
    ['Mean press', f(b.mean_pressure,1)+' cmH₂O'],
    ['PEEP', f(b.peep,1)+' cmH₂O'],
    ['Driving press', f(b.driving_pressure_cmh2o,1)+' cmH₂O'],
    ['Compliance (stat)', f(b.static_compliance_ml_cmh2o,1)+' mL/cmH₂O'],
    ['Compliance (dyn)', f(b.dynamic_compliance_ml_cmh2o,1)+' mL/cmH₂O'],
    ['Resistance', f(b.resistance_cmh2o_l_s,1)+' cmH₂O/(L/s)'],
  ];
  el.innerHTML = rows.map(([k,v])=>`<dt>${k}</dt><dd>${v}</dd>`).join('');
}

function syncBaselineUI(){
  // grey out fields that don't apply to the current baseline mode
  const mode = document.getElementById('baseline').value;
  const setEnabled = (id, on) => { const e=document.getElementById(id);
    e.disabled=!on; e.style.opacity=on?'1':'0.4'; };
  setEnabled('baseoff', mode === 'manual');
  const slopeMode = mode === 'slope';
  setEnabled('sdelta', slopeMode);
  setEnabled('swin', slopeMode);
  setEnabled('srefr', slopeMode);
  setEnabled('sguard', slopeMode);
  setEnabled('speakMean', slopeMode);
  setEnabled('speak', slopeMode && !document.getElementById('speakMean').checked);
  // the level-crossing slope gate / hysteresis don't apply in slope mode
  setEnabled('slope', !slopeMode);
  setEnabled('hyst', !slopeMode);
}

function showDisc(){ return document.getElementById('showDisc').checked; }
function visibleCaps(p){ return showDisc() ? p.captures : p.captures.filter(c=>c.connected); }

function fillPatients(){
  const psel = document.getElementById('patient');
  const prev = psel.value;
  const pats = INDEX.patients.filter(p=>visibleCaps(p).length);
  psel.innerHTML = pats.map(p=>
    `<option value="${p.patient_id}">${p.patient_id.slice(0,8)}… (${visibleCaps(p).length} cap)</option>`).join('');
  const keep = pats.some(p=>p.patient_id===prev) ? prev : (pats[0] && pats[0].patient_id);
  if(keep){ psel.value = keep; fillCaptures(keep); }
}

function fillCaptures(pid){
  const p = INDEX.patients.find(p=>p.patient_id===pid);
  const caps = visibleCaps(p);
  const sel = document.getElementById('capture');
  sel.innerHTML = caps.map(c=>
    `<option value="${c.raw_data}">day ${c.day} · ${c.time}${c.connected?'':' · disconnected'}</option>`).join('');
  if(caps.length) selectCapture(caps[0].raw_data);
}

async function init(){
  INDEX = await j('/api/index');
  document.getElementById('patient').onchange = e => fillCaptures(e.target.value);
  document.getElementById('capture').onchange = e => selectCapture(e.target.value);
  document.getElementById('breath').onchange = onBreathChange;
  document.getElementById('hyst').onchange = () => { if(CUR.file) selectCapture(CUR.file); };
  document.getElementById('slope').onchange = () => { if(CUR.file) selectCapture(CUR.file); };
  for(const id of ['sdelta','swin','srefr','sguard','speak'])
    document.getElementById(id).onchange = () => { if(CUR.file) selectCapture(CUR.file); };
  document.getElementById('speakMean').onchange = () => { syncBaselineUI(); if(CUR.file) selectCapture(CUR.file); };
  document.getElementById('baseline').onchange = () => { syncBaselineUI(); if(CUR.file) selectCapture(CUR.file); };
  document.getElementById('baseoff').oninput = () => { if(CUR.file) selectCapture(CUR.file); };
  syncBaselineUI();
  document.getElementById('showDisc').onchange = fillPatients;
  fillPatients();
  window.addEventListener('resize', ()=>{
    const i = parseInt(document.getElementById('breath').value, 10);
    renderCharts(i>=0 ? CUR.breaths[i] : null);
  });
}
init().catch(e=>document.getElementById('status').textContent='error: '+e.message);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    data_dir: Path = DEFAULT_DATA
    index: dict = {}

    def log_message(self, *a):  # quieter console
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        body = json.dumps(_denan(obj), allow_nan=False).encode("utf-8")
        self._send(code, body, "application/json")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif url.path == "/api/index":
            payload = {"patients": self.index["patients"]}
            self._json(payload)
        elif url.path == "/api/waveform":
            fname = parse_qs(url.query).get("file", [""])[0]
            if fname not in self.index["valid"]:  # guard against path traversal
                return self._json({"error": "unknown file"}, 404)
            wf = load_waveform(self.data_dir / fname)
            slope = np.gradient(wf["flow"].to_numpy()) * SAMPLE_RATE_HZ
            self._json(
                {
                    "t_sec": wf["t_sec"].round(3).tolist(),
                    "flow": wf["flow"].tolist(),
                    "pressure": wf["pressure"].tolist(),
                    "volume": wf["volume"].tolist(),
                    "slope": np.round(slope, 1).tolist(),
                }
            )
        elif url.path == "/api/breaths":
            qs = parse_qs(url.query)
            fname = qs.get("file", [""])[0]
            if fname not in self.index["valid"]:
                return self._json({"error": "unknown file"}, 404)
            try:
                hyst = max(0.0, float(qs.get("hysteresis", ["0"])[0]))
            except ValueError:
                hyst = 0.0
            def _qf(key, default):
                try:
                    return float(qs.get(key, [str(default)])[0])
                except ValueError:
                    return default
            slope = max(0.0, _qf("slope", 0.0))
            sdelta = max(0.0, _qf("sdelta", 100.0))
            swin = max(0.04, _qf("swin", 0.32))
            srefr = max(0.0, _qf("srefr", 1.0))
            sguard = max(0.0, _qf("sguard", 100.0))
            speak_raw = qs.get("speak", ["60"])[0]
            speak = "mean" if speak_raw == "mean" else max(0.0, _qf("speak", 60.0))
            baseline = qs.get("baseline", ["zero"])[0]
            wf = load_waveform(self.data_dir / fname)
            if baseline == "auto":
                base_arg = "auto"
                base_val = estimate_baseline(wf["flow"].to_numpy())
            elif baseline == "slope":
                base_arg = "slope"
                base_val = estimate_baseline(wf["flow"].to_numpy())
            elif baseline == "zero":
                base_arg, base_val = "zero", 0.0
            else:  # numeric manual offset; bad input -> zero
                try:
                    base_val = float(baseline)
                    base_arg = base_val
                except ValueError:
                    base_arg, base_val = "zero", 0.0
            breaths = segment_capture(wf, raw_data=fname, baseline=base_arg,
                                      hysteresis=hyst, slope_threshold=slope,
                                      slope_window_sec=swin, slope_delta=sdelta,
                                      slope_refractory_sec=srefr, slope_exp_guard=sguard,
                                      slope_peak_min=speak)
            breaths = add_metrics(breaths, wf)
            self._json({"breaths": breaths.to_dict(orient="records"), "baseline": base_val})
        else:
            self._json({"error": "not found"}, 404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    args = ap.parse_args()

    Handler.data_dir = args.data
    Handler.index = build_index(args.data)
    n_cap = sum(len(p["captures"]) for p in Handler.index["patients"])
    print(f"loaded {len(Handler.index['patients'])} patients, {n_cap} captures from {args.data}")
    print(f"serving http://localhost:{args.port}  (Ctrl+C to stop)")
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
