// AI% + mechanical power headline numbers, split out of MetadataPanel so it
// can sit in its own column next to the Asynchrony panel. Both are shown at
// equal size/weight -- same front-facing prominence, not one supporting the
// other. Both are fetched separately from (and slower than) the waveform, so
// `aiLoading`/`mpLoading` distinguish "still computing" from "computed,
// nothing to show".
// MP color bands: <=12 J/min green (normal), 12-17 amber (watch), >17 red
// (Serpa Neto et al. 2018 threshold range -- see docs/asynchrony.md §5).
// Exported so PatientsPage's cards use the exact same bands.
export function mpColorFor(value) {
  if (value == null) return "var(--muted)";
  if (value > 17) return "var(--alert)";
  if (value > 12) return "var(--press)";
  return "var(--vol)";
}

export default function VitalsPanel({ asynchronyIndex, aiLoading, mpStatus, mpLoading }) {
  const aiPct = asynchronyIndex != null ? asynchronyIndex * 100 : null;
  const aiColor = aiPct != null && aiPct > 10 ? "var(--alert)" : "var(--accent)";
  const mpColor = mpColorFor(mpStatus ? mpStatus.avg_mp_j_per_min : null);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <div style={{ fontSize: 36, fontWeight: 700, lineHeight: 1, color: aiLoading ? "var(--muted)" : aiColor }}>
          {aiLoading ? "…" : aiPct != null ? `${aiPct.toFixed(1)}%` : "—"}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.5, marginTop: 2 }}>
          Asynchrony index
        </div>
      </div>
      <div>
        <div style={{ fontSize: 36, fontWeight: 700, lineHeight: 1, color: mpLoading ? "var(--muted)" : mpColor }}>
          {mpLoading ? "…" : mpStatus ? mpStatus.avg_mp_j_per_min.toFixed(1) : "—"}
          {!mpLoading && mpStatus && (
            <span style={{ fontSize: 14, fontWeight: 400, color: "var(--muted)" }}> J/min</span>
          )}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.5, marginTop: 2 }}>
          Mech. power
        </div>
      </div>
    </div>
  );
}
