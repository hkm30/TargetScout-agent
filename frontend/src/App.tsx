import { useState } from "react";
import "./App.css";
import {
  parseAssessment,
  confirmAssessmentSSE,
  exportMarkdown,
  exportWord,
  exportPdf,
  fetchReport,
} from "./api";
import type {
  AssessmentResult,
  ParseResult,
  ParsedInput,
  Page,
  AssessStep,
  PartialResultData,
} from "./types";
import { Sidebar } from "./components/Sidebar";
import { SearchForm } from "./components/SearchForm";
import { ConfirmationPanel } from "./components/ConfirmationPanel";
import { RunningView } from "./components/RunningView";
import { ResultsView } from "./components/ResultsView";
import { HistoryPage } from "./components/HistoryPage";
import { SearchPage } from "./components/SearchPage";

export default function App() {
  // Page routing
  const [page, setPage] = useState<Page>("assess");
  const [assessStep, setAssessStep] = useState<AssessStep>("input");

  // Assessment state
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [result, setResult] = useState<AssessmentResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [agentProgress, setAgentProgress] = useState<Record<string, string>>({});
  const [partialResults, setPartialResults] = useState<Record<string, PartialResultData>>({});

  const handleNavigate = (p: Page) => {
    setPage(p);
    setError("");
  };

  const handleReset = () => {
    setPage("assess");
    setAssessStep("input");
    setResult(null);
    setParseResult(null);
    setError("");
    setAgentProgress({});
    setPartialResults({});
  };

  const handleSubmit = async (
    target: string,
    indication: string,
    synonyms: string,
    focus: string,
    timeRange: string,
  ) => {
    setLoading(true);
    setError("");
    setResult(null);
    setParseResult(null);
    try {
      const data = await parseAssessment(target, indication, synonyms, focus, timeRange);
      setParseResult(data);
      setAssessStep("confirm");
    } catch (e: any) {
      setError(e.message || "解析失败");
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async (modified: ParsedInput) => {
    setLoading(true);
    setError("");
    setAssessStep("running");
    setAgentProgress({});
    setPartialResults({});
    try {
      const data = await confirmAssessmentSSE(modified, (event) => {
        if (event.event === "status") {
          setAgentProgress((prev) => ({
            ...prev,
            [event.data.stage]: event.data.status,
          }));
        }
        if (event.event === "partial_result") {
          setPartialResults((prev) => ({
            ...prev,
            [event.data.stage]: event.data,
          }));
        }
      });
      setResult(data);
      setAssessStep("done");
    } catch (e: any) {
      setError(e.message || "评估失败");
      setAssessStep("confirm");
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    setAssessStep("input");
    setParseResult(null);
    setError("");
  };

  const handleViewReport = async (id: string, target: string) => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchReport(id, target);
      setResult(data);
      setPage("assess");
      setAssessStep("done");
    } catch (e: any) {
      setError(e.message || "加载报告失败");
    } finally {
      setLoading(false);
    }
  };

  const handleExportMarkdown = async () => {
    if (!result) return;
    try {
      const md = await exportMarkdown(result.report.report_id || result.report.target, result.report.target);
      const blob = new Blob([md], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${result.report.target}_report.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("Markdown 导出失败，报告可能尚未保存。");
    }
  };

  const handleExportWord = async () => {
    if (!result) return;
    try {
      await exportWord(result.report.report_id || result.report.target, result.report.target);
    } catch {
      alert("Word 导出失败，报告可能尚未保存。");
    }
  };

  const handleExportPdf = async () => {
    if (!result) return;
    try {
      await exportPdf(result.report.report_id || result.report.target, result.report.target);
    } catch {
      alert("PDF 导出失败，报告可能尚未保存。");
    }
  };

  return (
    <div className="app-layout">
      <Sidebar page={page} assessStep={assessStep} onNavigate={handleNavigate} />

      <main className="main-content">
        {error && <div className="error-banner">{error}</div>}

        {/* Assess Page */}
        {page === "assess" && assessStep === "input" && (
          <div>
            <div className="content-header">
              <div className="content-title">新建靶点评估</div>
            </div>
            <div className="card">
              <SearchForm onSubmit={handleSubmit} loading={loading} />
            </div>
          </div>
        )}

        {page === "assess" && assessStep === "confirm" && parseResult && (
          <div>
            <div className="content-header">
              <div className="content-title">确认评估参数</div>
            </div>
            <ConfirmationPanel
              parseResult={parseResult}
              onConfirm={handleConfirm}
              onBack={handleBack}
              loading={loading}
            />
          </div>
        )}

        {page === "assess" && assessStep === "running" && parseResult && (
          <RunningView
            target={parseResult.parsed.target}
            indication={parseResult.parsed.indication}
            agentProgress={agentProgress}
            partialResults={partialResults}
          />
        )}

        {page === "assess" && assessStep === "done" && result && (
          <ResultsView
            result={result}
            onNewAssessment={handleReset}
            onExportWord={handleExportWord}
            onExportPdf={handleExportPdf}
            onExportMarkdown={handleExportMarkdown}
          />
        )}

        {/* History Page */}
        {page === "history" && (
          <HistoryPage onViewReport={handleViewReport} />
        )}

        {/* Search Page */}
        {page === "search" && (
          <SearchPage onViewReport={handleViewReport} />
        )}
      </main>
    </div>
  );
}
