interface HistoricalReport {
  id: string;
  target: string;
  indication: string;
  recommendation: string;
  summary: string;
  created_at: string;
  score?: number;
}

interface Props {
  reports: HistoricalReport[];
}

export function HistoricalContext({ reports }: Props) {
  if (!reports || reports.length === 0) return null;

  return (
    <div
      style={{
        background: "#f0f9ff",
        border: "1px solid #7dd3fc",
        borderRadius: "8px",
        padding: "16px",
        marginBottom: "16px",
      }}
    >
      <h3 style={{ margin: "0 0 12px", fontSize: "1em" }}>
        历史评估记录（{reports.length} 条）
      </h3>
      {reports.map((r) => (
        <div
          key={r.id}
          style={{
            background: "#fff",
            border: "1px solid #e0e7ff",
            borderRadius: "6px",
            padding: "12px",
            marginBottom: "8px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <strong>
              {r.target}
              {r.indication ? ` / ${r.indication}` : ""}
            </strong>
            <span
              style={{
                padding: "2px 8px",
                borderRadius: "4px",
                fontSize: "0.8em",
                fontWeight: 600,
                background:
                  r.recommendation === "Go"
                    ? "#dcfce7"
                    : r.recommendation === "No-Go"
                      ? "#fee2e2"
                      : "#fef3c7",
                color:
                  r.recommendation === "Go"
                    ? "#166534"
                    : r.recommendation === "No-Go"
                      ? "#991b1b"
                      : "#92400e",
              }}
            >
              {r.recommendation}
            </span>
          </div>
          <p style={{ margin: "8px 0 4px", fontSize: "0.9em", color: "#555" }}>
            {r.summary ? r.summary.slice(0, 200) + (r.summary.length > 200 ? "..." : "") : ""}
          </p>
          <div style={{ fontSize: "0.75em", color: "#888" }}>
            {r.created_at ? new Date(r.created_at).toLocaleDateString() : ""}
          </div>
        </div>
      ))}
    </div>
  );
}
