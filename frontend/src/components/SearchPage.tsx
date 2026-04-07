import { useState } from "react";
import { searchKnowledge } from "../api";
import type { SearchResultItem } from "../types";

interface Props {
  onViewReport: (id: string, target: string) => void;
}

function badgeClass(rec: string): string {
  const r = rec.toLowerCase();
  if (r === "go") return "badge badge--go";
  if (r === "no-go" || r === "nogo") return "badge badge--nogo";
  return "badge badge--more";
}

function badgeLabel(rec: string): string {
  const r = rec.toLowerCase();
  if (r === "go") return "Go";
  if (r === "no-go" || r === "nogo") return "No-Go";
  return "需更多数据";
}

export function SearchPage({ onViewReport }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = await searchKnowledge(query.trim());
      setResults(data.results);
      setCount(data.count);
    } catch (e: any) {
      setError(e.message || "搜索失败");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  return (
    <div>
      <div className="content-header">
        <div className="content-title">知识库检索</div>
      </div>

      <div className="search-box">
        <input
          className="search-input"
          placeholder="输入搜索关键词，例如：EGFR 耐药机制"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button className="btn btn-primary" style={{ padding: "10px 24px", fontSize: 14 }} onClick={handleSearch} disabled={loading}>
          {loading ? "搜索中..." : "搜索"}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {count !== null && (
        <div className="text-secondary mb-16">找到 {count} 条相关记录</div>
      )}

      {results.map((item) => (
        <div
          key={item.id}
          className="card card-clickable"
          onClick={() => onViewReport(item.id, item.target)}
        >
          <div className="report-card">
            <div className="report-card__body">
              <div className="report-card__title">
                {item.target}{item.indication ? ` - ${item.indication}` : ""}
              </div>
              <div className="report-card__summary">{item.summary || "暂无摘要"}</div>
              <div className="report-card__meta">
                {item.created_at ? new Date(item.created_at).toLocaleDateString("zh-CN") : ""}
                {item.score != null ? ` | 相关度: ${item.score.toFixed(2)}` : ""}
              </div>
            </div>
            {item.recommendation && (
              <span className={badgeClass(item.recommendation)}>
                {badgeLabel(item.recommendation)}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
