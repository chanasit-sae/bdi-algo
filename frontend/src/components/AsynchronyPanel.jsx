// Human label per event `type`. Add new asynchrony types here as the
// backend gains new detectors — everything else (highlighting, this list)
// already works off the generic t0/t1/detail fields.
const TYPE_LABEL = {
  double_trigger: "Double triggering",
  ineffective_effort: "Ineffective effort",
  auto_peep: "Auto-PEEP",
};

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
              {TYPE_LABEL[e.type] || e.type}
              {e.breath_idx_a != null && ` · breath ${e.breath_idx_a}`}
              {e.breath_idx_b != null && ` → ${e.breath_idx_b}`}
            </span>
            <span className="asy-ratio">{e.detail}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
