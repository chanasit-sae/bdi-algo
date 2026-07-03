// Table of flagged breath pairs. Clicking a row makes it the "active" event
// (drawn brighter on the chart).
export default function DoubleTriggerTable({ events, activeIdx, onSelect }) {
  if (!events.length) {
    return <p className="muted">No double-triggered pairs detected with the current settings.</p>;
  }
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="dt-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Breaths</th>
            <th title="expiratory gap between the pair">Te gap (s)</th>
            <th title="the Ti reference the gap was compared against">Ti ref (s)</th>
            <th title="Te / Ti_ref — flagged when below the ratio threshold">Te/Ti</th>
            <th title="combined tidal volume of the pair">Vt pair (mL)</th>
            <th title="Vt pair / (2 x capture median Vt)">Vt ratio</th>
            <th title="Vt ratio exceeds the stacking threshold">Stacked</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e, i) => (
            <tr key={i} className={i === activeIdx ? "active" : ""} onClick={() => onSelect(i)}>
              <td>{i + 1}</td>
              <td>
                {e.breath_idx_a} → {e.breath_idx_b}
              </td>
              <td>{e.te_gap.toFixed(2)}</td>
              <td>{e.ti_ref.toFixed(2)}</td>
              <td>{e.te_ti_ratio.toFixed(2)}</td>
              <td>{e.vt_pair.toFixed(0)}</td>
              <td>{e.vt_ratio != null ? e.vt_ratio.toFixed(2) : "—"}</td>
              <td>{e.stacked ? "yes" : "no"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
