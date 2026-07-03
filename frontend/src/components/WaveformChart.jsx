import { useEffect, useRef } from "react";
import { drawChart } from "../lib/charts.js";

// A single labelled waveform canvas. Redraws on data change and on window
// resize (canvas pixel size is derived from its CSS box).
export default function WaveformChart({ title, color, t, y, breaths, sel, baseVal }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const render = () =>
      drawChart(canvasRef.current, { t, y, color, breaths, sel, baseVal });
    render();
    window.addEventListener("resize", render);
    return () => window.removeEventListener("resize", render);
  }, [t, y, color, breaths, sel, baseVal]);

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
