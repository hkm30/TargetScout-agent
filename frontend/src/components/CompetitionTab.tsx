export function CompetitionTab({
  summary,
  players,
  sources,
  decisionSummary,
}: {
  summary: string;
  players: any[];
  sources: any[];
  decisionSummary: string;
}) {
  return (
    <div>
      {/* Decision Agent's structured conclusion */}
      {decisionSummary && (
        <div
          style={{
            background: "#fefce8",
            border: "1px solid #fde047",
            borderRadius: "8px",
            padding: "16px",
            marginBottom: "16px",
          }}
        >
          <h3 style={{ margin: "0 0 8px", fontSize: "1em", color: "#a16207" }}>
            竞争格局评估
          </h3>
          <p style={{ margin: 0 }}>{decisionSummary}</p>
        </div>
      )}

      {/* Raw agent output */}
      {summary && (
        <>
          <h4>Agent 研究摘要</h4>
          <p>{summary}</p>
        </>
      )}

      {players.length > 0 && (
        <>
          <h4>主要竞争者</h4>
          <ul>
            {players.map((p, i) => (
              <li key={i}>
                {typeof p === "string"
                  ? p
                  : typeof p === "object" && p !== null
                    ? `${p.company || p.name || ""} — ${(p.programs || []).join(", ") || p.positioning || ""}`
                    : String(p)}
              </li>
            ))}
          </ul>
        </>
      )}

      {sources.length > 0 && (
        <>
          <h4>信息来源</h4>
          {sources.map((s, i) => {
            const title = s.title || s.name || "";
            const url = s.url || s.link || "";
            const type = s.type || "";
            const typeLabel =
              type === "pubmed" ? "PubMed" :
              type === "clinical_trial" ? "ClinicalTrials.gov" :
              type === "web" ? "Web" : "";
            return (
              <div key={i} style={{ borderBottom: "1px solid #eee", padding: "8px 0" }}>
                {url ? (
                  <a href={url} target="_blank" rel="noreferrer">{title || url}</a>
                ) : (
                  <strong>{title}</strong>
                )}
                {typeLabel && (
                  <span style={{
                    marginLeft: "8px",
                    fontSize: "0.8em",
                    background: "#f3f4f6",
                    border: "1px solid #d1d5db",
                    borderRadius: "4px",
                    padding: "2px 6px",
                  }}>
                    {typeLabel}
                  </span>
                )}
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}
