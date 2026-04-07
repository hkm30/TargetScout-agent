import { useEffect, useState } from "react";
import { fetchReports, deleteReport, exportWord } from "../api";
import type { ReportListItem } from "../types";

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

export function HistoryPage({ onViewReport }: Props) {
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState<ReportListItem | null>(null);

  const loadReports = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchReports();
      setReports(data.reports);
    } catch (e: any) {
      setError(e.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReports();
  }, []);

  const handleDelete = async (report: ReportListItem) => {
    try {
      await deleteReport(report.id, report.target);
      setReports((prev) => prev.filter((r) => r.id !== report.id));
    } catch (e: any) {
      alert("删除失败: " + (e.message || "未知错误"));
    }
    setDeleteConfirm(null);
  };

  const handleExport = async (report: ReportListItem) => {
    try {
      await exportWord(report.id, report.target);
    } catch {
      alert("导出失败，请稍后重试。");
    }
  };

  return (
    <div>
      <div className="content-header">
        <div className="content-title">历史评估报告</div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading && <div className="text-secondary">加载中...</div>}

      {!loading && reports.length === 0 && !error && (
        <div className="text-secondary">暂无历史报告。</div>
      )}

      {reports.map((report) => (
        <div
          key={report.id}
          className="card card-clickable"
          onClick={() => onViewReport(report.id, report.target)}
        >
          <div className="report-card">
            <div className="report-card__body">
              <div className="report-card__title">
                {report.target}{report.indication ? ` - ${report.indication}` : ""}
              </div>
              <div className="report-card__summary">{report.summary || "暂无摘要"}</div>
              <div className="report-card__meta">
                {report.created_at ? new Date(report.created_at).toLocaleDateString("zh-CN") : ""}
                {report.score != null ? ` | 综合评分: ${report.score}` : ""}
              </div>
            </div>
            <div className="report-card__actions">
              {report.recommendation && (
                <span className={badgeClass(report.recommendation)}>
                  {badgeLabel(report.recommendation)}
                </span>
              )}
              <button
                className="btn"
                onClick={(e) => { e.stopPropagation(); handleExport(report); }}
              >
                导出
              </button>
              <button
                className="btn btn-danger"
                onClick={(e) => { e.stopPropagation(); setDeleteConfirm(report); }}
              >
                删除
              </button>
            </div>
          </div>
        </div>
      ))}

      {/* Delete confirmation dialog */}
      {deleteConfirm && (
        <div className="confirm-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-dialog__title">确认删除</div>
            <div className="confirm-dialog__text">
              确定要删除「{deleteConfirm.target}{deleteConfirm.indication ? ` - ${deleteConfirm.indication}` : ""}」的评估报告吗？此操作不可撤销。
            </div>
            <div className="confirm-dialog__actions">
              <button className="btn" onClick={() => setDeleteConfirm(null)}>取消</button>
              <button
                className="btn btn-danger"
                style={{ background: "#ef4444", color: "#fff", borderColor: "#ef4444" }}
                onClick={() => handleDelete(deleteConfirm)}
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
