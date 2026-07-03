import { useEffect, useRef } from "react";
import { drawChart } from "../lib/charts.js";

// A single labelled waveform canvas. Redraws on data change and on window
// resize (canvas pixel size is derived from its CSS box). `highlights` is an
// optional list of { t0, t1, active } spans (e.g. flagged double-trigger
// pairs) drawn as a red band under the breath boundary lines.
export default function WaveformChart({ title, color, t, y, breaths, sel, baseVal, highlights }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const render = () =>
      drawChart(canvasRef.current, { t, y, color, breaths, sel, baseVal, highlights });
    render();
    window.addEventListener("resize", render);
    return () => window.removeEventListener("resize", render);
  }, [t, y, color, breaths, sel, baseVal, highlights]);

  return (
    <div className="chart-card">
      <h3>
        <span className="swatch" style={{ background: color }} />
        {title}
      </h3>
      <canvas ref={canvasRef} />
    </div>
  );
}
