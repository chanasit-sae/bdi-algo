// AI% + mechanical power headline numbers, split out of MetadataPanel so it
// can sit in its own column next to the Asynchrony panel. AI% is the bigger,
// accent-colored figure (the one meant to be readable at a glance); MP sits
// below it, smaller, as supporting context. Both are fetched separately from
// (and slower than) the waveform, so `aiLoading`/`mpLoading` distinguish
// "still computing" from "computed, nothing to show".
export default function VitalsPanel({ asynchronyIndex, aiLoading, mpStatus, mpLoading }) {
  const aiPct = asynchronyIndex != null ? asynchronyIndex * 100 : null;
  const aiColor = aiPct != null && aiPct > 10 ? "var(--alert)" : "var(--accent)";

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
        <div style={{ fontSize: 18, fontWeight: 600, lineHeight: 1 }}>
          {mpLoading ? "…" : mpStatus ? mpStatus.avg_mp_j_per_min.toFixed(1) : "—"}
          {!mpLoading && mpStatus && (
            <span style={{ fontSize: 11, fontWeight: 400, color: "var(--muted)" }}> J/min</span>
          )}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.5, marginTop: 2 }}>
          Mech. power
        </div>
      </div>
    </div>
  );
}
