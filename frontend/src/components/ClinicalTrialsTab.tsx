function countBy(trials: any[], key: string): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const t of trials) {
    const val = t[key] || "Unknown";
    counts[val] = (counts[val] || 0) + 1;
  }
  return counts;
}

function StatBar({ label, counts }: { label: string; counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (total === 0) return null;
  return (
    <div style={{ marginBottom: "12px" }}>
      <strong>{label}</strong>
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "4px" }}>
        {Object.entries(counts)
          .sort(([, a], [, b]) => b - a)
          .map(([name, count]) => (
            <span
              key={name}
              style={{
                background: "#f3f4f6",
                border: "1px solid #d1d5db",
                borderRadius: "6px",
                padding: "4px 10px",
                fontSize: "0.85em",
              }}
            >
              {name}: <strong>{count}</strong>
            </span>
          ))}
      </div>
    </div>
  );
}

export function ClinicalTrialsTab({
  trials,
  summary,
  decisionSummary,
}: {
  trials: any[];
  summary: string;
  decisionSummary: string;
}) {
  const phaseCounts = countBy(trials, "phase");
  const statusCounts = countBy(trials, "status");

  return (
    <div>
      {/* Decision Agent's structured conclusion */}
      {decisionSummary && (
        <div
          style={{
            background: "#faf5ff",
            border: "1px solid #d8b4fe",
            borderRadius: "8px",
            padding: "16px",
            marginBottom: "16px",
          }}
        >
          <h3 style={{ margin: "0 0 8px", fontSize: "1em", color: "#7c3aed" }}>
            临床试验评估
          </h3>
          <p style={{ margin: 0 }}>{decisionSummary}</p>
        </div>
      )}

      {/* Phase & Status distribution */}
      {trials.length > 0 && (
        <div style={{ marginBottom: "16px" }}>
          <StatBar label="临床阶段分布" counts={phaseCounts} />
          <StatBar label="试验状态分布" counts={statusCounts} />
        </div>
      )}

      {/* Raw agent output */}
      {summary && typeof summary === "string" && (
        <>
          <h4>Agent 研究摘要</h4>
          <p>{summary}</p>
        </>
      )}

      {trials.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "8px" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid #333", textAlign: "left" }}>
              <th>NCT 编号</th>
              <th>标题</th>
              <th>阶段</th>
              <th>状态</th>
              <th>申办方</th>
            </tr>
          </thead>
          <tbody>
            {trials.map((t, i) => {
              const nctId = t.nct_id || t.nctId || "";
              const link = t.link || (nctId ? `https://clinicaltrials.gov/study/${nctId}` : "");
              return (
                <tr key={nctId || i} style={{ borderBottom: "1px solid #eee" }}>
                  <td>
                    {link ? (
                      <a href={link} target="_blank" rel="noreferrer">{nctId}</a>
                    ) : (
                      nctId
                    )}
                  </td>
                  <td>{t.title || ""}</td>
                  <td>{t.phase || ""}</td>
                  <td>{t.status || ""}</td>
                  <td>{t.sponsor || ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
