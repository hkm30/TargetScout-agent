const BADGE: Record<string, string> = {
  PubMed: "#3b82f6",
  pubmed: "#3b82f6",
  ClinicalTrials: "#8b5cf6",
  clinicaltrials: "#8b5cf6",
  Web: "#6b7280",
  web: "#6b7280",
  FDA: "#ef4444",
};

function normalizeCitation(c: any): { title: string; link: string; sourceType: string } {
  if (typeof c === "string") {
    return { title: c, link: "", sourceType: "Web" };
  }
  return {
    title: c.title || c.id || "",
    link: c.link || c.url || (c.id && c.type === "pubmed" ? `https://pubmed.ncbi.nlm.nih.gov/${c.id}/` : "") || "",
    sourceType: c.source_type || c.type || c.source || "Web",
  };
}

export function CitationList({ citations }: { citations: any[] }) {
  if (!citations || citations.length === 0) return null;

  return (
    <div>
      <h3>参考文献</h3>
      {citations.map((c, i) => {
        const { title, link, sourceType } = normalizeCitation(c);
        return (
          <div key={i} style={{ padding: "4px 0" }}>
            <span
              style={{
                background: BADGE[sourceType] || "#999",
                color: "#fff",
                padding: "2px 8px",
                borderRadius: "4px",
                fontSize: "0.8em",
                marginRight: "8px",
              }}
            >
              {sourceType}
            </span>
            {link ? (
              <a href={link} target="_blank" rel="noreferrer">
                {title}
              </a>
            ) : (
              <span>{title}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
