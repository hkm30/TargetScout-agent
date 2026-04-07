import type { Report } from "../types";

const COLORS: Record<string, string> = {
  Go: "#22c55e",
  "No-Go": "#ef4444",
  "Need More Data": "#f59e0b",
};

export function ResultCard({ report }: { report: Report }) {
  const color = COLORS[report.recommendation] || "#999";

  return (
    <div
      style={{
        border: `3px solid ${color}`,
        borderRadius: "12px",
        padding: "24px",
        marginBottom: "20px",
      }}
    >
      {/* Header: recommendation badge */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "12px" }}>
        <span
          style={{
            background: color,
            color: "#fff",
            padding: "6px 18px",
            borderRadius: "20px",
            fontSize: "1.2em",
            fontWeight: 700,
          }}
        >
          {report.recommendation}
        </span>
        <span style={{ fontSize: "1.1em" }}>
          <strong>{report.target}</strong>
          {report.indication ? ` — ${report.indication}` : ""}
        </span>
      </div>

      {/* Reasoning */}
      <div style={{ marginBottom: "16px" }}>
        <h4 style={{ margin: "0 0 4px" }}>决策理由</h4>
        <p style={{ margin: 0 }}>{report.reasoning}</p>
      </div>

      {/* Uncertainty */}
      {report.uncertainty && (
        <div style={{ marginBottom: "16px", color: "#666", fontStyle: "italic" }}>
          不确定性：{report.uncertainty}
        </div>
      )}

      {/* Risks & Opportunities side by side */}
      <div style={{ display: "flex", gap: "24px" }}>
        {/* Major Risks */}
        <div style={{ flex: 1 }}>
          <h4 style={{ margin: "0 0 8px", color: "#ef4444" }}>主要风险</h4>
          {Array.isArray(report.major_risks) && report.major_risks.length ? (
            <ul style={{ margin: 0, paddingLeft: "20px" }}>
              {report.major_risks.map((r, i) => (
                <li key={i} style={{ marginBottom: "4px" }}>{String(r)}</li>
              ))}
            </ul>
          ) : (
            <p style={{ margin: 0, color: "#999" }}>未识别</p>
          )}
        </div>

        {/* Major Opportunities */}
        <div style={{ flex: 1 }}>
          <h4 style={{ margin: "0 0 8px", color: "#22c55e" }}>主要机会</h4>
          {Array.isArray(report.major_opportunities) && report.major_opportunities.length ? (
            <ul style={{ margin: 0, paddingLeft: "20px" }}>
              {report.major_opportunities.map((o, i) => (
                <li key={i} style={{ marginBottom: "4px" }}>{String(o)}</li>
              ))}
            </ul>
          ) : (
            <p style={{ margin: 0, color: "#999" }}>未识别</p>
          )}
        </div>
      </div>
    </div>
  );
}
