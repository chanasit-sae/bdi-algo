const f = (v, d = 2) => (v == null ? "—" : (+v).toFixed(d));

// List of flagged asynchrony events for the currently loaded capture. Clicking
// one makes it "active" (bright band on the chart) and selects its first
// breath in the Breath dropdown above.
export default function AsynchronyPanel({ events, activeIdx, onSelect }) {
  if (!events.length) {
    return <p className="muted" style={{ fontSize: 13 }}>none detected with the current settings</p>;
  }
  return (
    <ul className="asy-list">
      {events.map((e, i) => (
        <li key={i}>
          <button
            type="button"
            className={"asy-item" + (i === activeIdx ? " active" : "")}
            onClick={() => onSelect(i)}
          >
            <span className="asy-idx">
              breaths {e.breath_idx_a} → {e.breath_idx_b}
            </span>
            <span className="asy-ratio">Te/Ti {f(e.te_ti_ratio)}</span>
            {e.stacked && <span className="notif-badge">stacked</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}
