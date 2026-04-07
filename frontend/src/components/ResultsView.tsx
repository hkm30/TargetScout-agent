import { useState } from "react";
import type { AssessmentResult } from "../types";
import { ResultCard } from "./ResultCard";
import { LiteratureTab } from "./LiteratureTab";
import { ClinicalTrialsTab } from "./ClinicalTrialsTab";
import { CompetitionTab } from "./CompetitionTab";
import { CitationList } from "./CitationList";
import { HistoricalContext } from "./HistoricalContext";

type Tab = "literature" | "trials" | "competition";

interface Props {
  result: AssessmentResult;
  onNewAssessment: () => void;
  onExportWord: () => void;
  onExportPdf: () => void;
  onExportMarkdown: () => void;
}

/** Safely convert a summary field to string */
function safeSummary(val: unknown): string {
  if (!val) return "";
  if (typeof val === "string") return val;
  if (typeof val === "object") {
    const obj = val as Record<string, unknown>;
    return (obj.overall_assessment as string) || (obj.summary as string) || JSON.stringify(val);
  }
  return String(val);
}

export function ResultsView({ result, onNewAssessment, onExportWord, onExportPdf, onExportMarkdown }: Props) {
  const [tab, setTab] = useState<Tab>("literature");

  return (
    <div>
      <div className="content-header">
        <div className="content-title">评估结果</div>
        <div className="btn-group">
          <button className="btn" onClick={onNewAssessment}>新建评估</button>
          <button className="btn" onClick={onExportWord}>导出 Word</button>
          <button className="btn" onClick={onExportPdf}>导出 PDF</button>
          <button className="btn" onClick={onExportMarkdown}>导出 Markdown</button>
        </div>
      </div>

      {/* Partial failures warning */}
      {result.partial_failures && result.partial_failures.length > 0 && (
        <div className="error-banner" style={{ background: "#fef3c7", borderColor: "#f59e0b", color: "#92400E" }}>
          <strong>警告：</strong>部分数据源出错，结果可能不完整。
          <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
            {result.partial_failures.map((f, i) => (
              <li key={i} style={{ fontSize: "0.9em" }}>{f}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Result card */}
      <ResultCard report={result.report} />

      {/* Historical context */}
      <HistoricalContext reports={result.knowledge_base_context?.historical_reports || []} />

      {/* Tab bar */}
      <div className="content-tabs">
        {([
          { key: "literature" as Tab, label: "📚 文献研究" },
          { key: "trials" as Tab, label: "🏥 临床试验" },
          { key: "competition" as Tab, label: "🏢 竞争分析" },
        ]).map((t) => (
          <div
            key={t.key}
            className={`content-tab${tab === t.key ? " content-tab--active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </div>
        ))}
      </div>

      <div className="tab-panel">
        {tab === "literature" && (
          <LiteratureTab
            papers={Array.isArray(result.raw_outputs.literature?.papers) ? result.raw_outputs.literature.papers : []}
            summary={safeSummary(result.raw_outputs.literature?.summary)}
            decisionSummary={result.report.literature_summary || ""}
          />
        )}
        {tab === "trials" && (
          <ClinicalTrialsTab
            trials={Array.isArray(result.raw_outputs.clinical_trials?.trials) ? result.raw_outputs.clinical_trials.trials : []}
            summary={safeSummary(result.raw_outputs.clinical_trials?.summary)}
            decisionSummary={result.report.clinical_trials_summary || ""}
          />
        )}
        {tab === "competition" && (
          <CompetitionTab
            summary={safeSummary(result.raw_outputs.competition?.summary)}
            players={Array.isArray(result.raw_outputs.competition?.major_players) ? result.raw_outputs.competition.major_players : []}
            sources={Array.isArray(result.raw_outputs.competition?.sources) ? result.raw_outputs.competition.sources : []}
            decisionSummary={result.report.competition_summary || ""}
          />
        )}
      </div>

      {/* Citations */}
      <div style={{ marginTop: 14 }}>
        <CitationList citations={result.report.citations || []} />
      </div>
    </div>
  );
}
