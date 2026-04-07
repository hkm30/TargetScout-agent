export function LiteratureTab({
  papers,
  summary,
  decisionSummary,
}: {
  papers: any[];
  summary: string;
  decisionSummary: string;
}) {
  return (
    <div>
      {/* Decision Agent's structured conclusion */}
      {decisionSummary && (
        <div
          style={{
            background: "#f0f9ff",
            border: "1px solid #bae6fd",
            borderRadius: "8px",
            padding: "16px",
            marginBottom: "16px",
          }}
        >
          <h3 style={{ margin: "0 0 8px", fontSize: "1em", color: "#0369a1" }}>
            文献研究评估
          </h3>
          <p style={{ margin: 0 }}>{decisionSummary}</p>
        </div>
      )}

      {/* Raw agent output */}
      {summary && typeof summary === "string" && (
        <>
          <h4>Agent 研究摘要</h4>
          <p>{typeof summary === "object" ? JSON.stringify(summary) : summary}</p>
        </>
      )}

      {papers.length > 0 && (
        <>
          <h4>关键论文</h4>
          {papers.map((p, i) => {
            const pmid = p.pmid || p.id || "";
            const title = p.title || "";
            const link = p.link || (pmid ? `https://pubmed.ncbi.nlm.nih.gov/${pmid}/` : "");
            const authors = p.authors || "";
            const year = p.year || "";
            const abstract = p.abstract || p.finding || p.key_relevance || "";
            return (
              <div key={pmid || i} style={{ borderBottom: "1px solid #eee", padding: "8px 0" }}>
                {link ? (
                  <a href={link} target="_blank" rel="noreferrer">{title}</a>
                ) : (
                  <strong>{title}</strong>
                )}
                <br />
                <small>
                  {authors ? `${authors} ` : ""}
                  {year ? `(${year})` : ""}
                  {pmid ? ` — PMID: ${pmid}` : ""}
                </small>
                {abstract && (
                  <p style={{ fontSize: "0.9em", color: "#555" }}>
                    {String(abstract).slice(0, 300)}{String(abstract).length > 300 ? "..." : ""}
                  </p>
                )}
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}
