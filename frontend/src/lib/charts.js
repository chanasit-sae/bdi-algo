// Canvas waveform renderer, ported from the original viz_server drawChart.
// Pure function of (canvas, data) so it can be called from a React effect.

export const COLORS = {
  flow: "#4fc3f7",
  pressure: "#ff8a65",
  volume: "#81c784",
  slope: "#ba68c8",
};
const INSP_FILL = "rgba(79,195,247,0.13)"; // inspiration band
const EXP_FILL = "rgba(255,138,101,0.13)"; // expiration band
const FLAG_FILL = "rgba(244,67,54,0.20)"; // flagged event band (e.g. double-trigger)
const FLAG_STROKE = "#f44336";

export function drawChart(canvas, { t, y, color, breaths, sel, baseVal, highlights }) {
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  const padL = 46,
    padR = 8,
    padT = 8,
    padB = 20;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;
  if (!y || !y.length) return;
  let ymin = Math.min(...y),
    ymax = Math.max(...y);
  if (ymin === ymax) {
    ymin -= 1;
    ymax += 1;
  }
  const tmax = t[t.length - 1] || 1;
  const Xt = (tt) => padL + (tt / tmax) * plotW; // time (s) -> px
  const Y = (v) => padT + (1 - (v - ymin) / (ymax - ymin)) * plotH;

  // phase bands for the selected breath
  if (sel) {
    ctx.fillStyle = INSP_FILL;
    ctx.fillRect(Xt(sel.t_insp_start), padT, Xt(sel.t_insp_end) - Xt(sel.t_insp_start), plotH);
    ctx.fillStyle = EXP_FILL;
    ctx.fillRect(Xt(sel.t_insp_end), padT, Xt(sel.t_exp_end) - Xt(sel.t_insp_end), plotH);
  }
  // flagged-event bands (e.g. double-triggered breath pairs), drawn under everything else
  if (highlights && highlights.length) {
    for (const hl of highlights) {
      const x0 = Xt(hl.t0),
        x1 = Xt(hl.t1);
      ctx.fillStyle = hl.active ? "rgba(244,67,54,0.32)" : FLAG_FILL;
      ctx.fillRect(x0, padT, x1 - x0, plotH);
      ctx.strokeStyle = FLAG_STROKE;
      ctx.lineWidth = hl.active ? 2 : 1;
      ctx.strokeRect(x0, padT, x1 - x0, plotH);
    }
  }
  // faint breath-boundary lines (inspiration onsets)
  if (breaths && breaths.length) {
    ctx.strokeStyle = "#3a4c60";
    ctx.lineWidth = 1;
    for (const b of breaths) {
      const x = Xt(b.t_insp_start);
      ctx.beginPath();
      ctx.moveTo(x, padT);
      ctx.lineTo(x, padT + plotH);
      ctx.stroke();
    }
  }
  // grid + y labels
  ctx.strokeStyle = "#2b3a4a";
  ctx.fillStyle = "#8ea1b5";
  ctx.font = "11px system-ui";
  ctx.lineWidth = 1;
  for (let g = 0; g <= 4; g++) {
    const yy = padT + (g / 4) * plotH;
    const val = ymax - (g / 4) * (ymax - ymin);
    ctx.beginPath();
    ctx.moveTo(padL, yy);
    ctx.lineTo(w - padR, yy);
    ctx.stroke();
    ctx.fillText(val.toFixed(0), 4, yy + 3);
  }
  if (ymin < 0 && ymax > 0) {
    ctx.strokeStyle = "#43586e";
    ctx.beginPath();
    ctx.moveTo(padL, Y(0));
    ctx.lineTo(w - padR, Y(0));
    ctx.stroke();
  }
  // crossing baseline (dashed) — the level segmentation splits insp/exp on it
  if (baseVal != null && baseVal > ymin && baseVal < ymax) {
    ctx.strokeStyle = "#d08770";
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(padL, Y(baseVal));
    ctx.lineTo(w - padR, Y(baseVal));
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "#d08770";
    ctx.fillText(baseVal.toFixed(1), padL + 2, Y(baseVal) - 3);
  }
  ctx.fillStyle = "#8ea1b5";
  ctx.fillText("0s", padL, h - 6);
  ctx.fillText(tmax.toFixed(1) + "s", w - padR - 24, h - 6);
  // series
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.6;
  ctx.beginPath();
  for (let i = 0; i < y.length; i++) {
    const xx = Xt(t[i]),
      yy = Y(y[i]);
    i ? ctx.lineTo(xx, yy) : ctx.moveTo(xx, yy);
  }
  ctx.stroke();
}
