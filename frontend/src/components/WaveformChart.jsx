import { useEffect, useRef } from "react";
import { drawChart, pixelXToTime } from "../lib/charts.js";

// A single labelled waveform canvas. Redraws on data change and on window
// resize (canvas pixel size is derived from its CSS box). `highlights` is an
// optional list of { t0, t1, active } spans (e.g. flagged double-trigger
// pairs) drawn as a red band under the breath boundary lines. Clicking the
// canvas maps the click's x position back to a time (via the same padding
// math drawChart uses) and reports it through `onSelectTime`, so the parent
// can pick whichever breath spans that time.
export default function WaveformChart({ title, color, t, y, breaths, sel, baseVal, highlights, onSelectTime }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const render = () =>
      drawChart(canvasRef.current, { t, y, color, breaths, sel, baseVal, highlights });
    render();
    window.addEventListener("resize", render);
    return () => window.removeEventListener("resize", render);
  }, [t, y, color, breaths, sel, baseVal, highlights]);

  function handleClick(e) {
    if (!onSelectTime || !t || !t.length) return;
    const rect = canvasRef.current.getBoundingClientRect();
    onSelectTime(pixelXToTime(canvasRef.current, t, e.clientX - rect.left));
  }

  return (
    <div className="chart-card">
      <h3>
        <span className="swatch" style={{ background: color }} />
        {title}
      </h3>
      <canvas ref={canvasRef} onClick={handleClick} style={onSelectTime ? { cursor: "pointer" } : undefined} />
    </div>
  );
}
