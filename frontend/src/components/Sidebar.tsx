import { useEffect, useState } from "react";
import type { Page, AssessStep } from "../types";

interface Props {
  page: Page;
  assessStep: AssessStep;
  onNavigate: (page: Page) => void;
}

const STEPS: { key: AssessStep; label: string }[] = [
  { key: "input", label: "输入参数" },
  { key: "confirm", label: "确认任务" },
  { key: "running", label: "运行分析" },
  { key: "done", label: "查看结果" },
];

const STEP_ORDER: AssessStep[] = ["input", "confirm", "running", "done"];

function stepIndex(s: AssessStep): number {
  return STEP_ORDER.indexOf(s);
}

export function Sidebar({ page, assessStep, onNavigate }: Props) {
  const showStepper = page === "assess" && assessStep !== "input";
  const currentIdx = stepIndex(assessStep);

  const [backendTag, setBackendTag] = useState("");
  const [backendBuildTime, setBackendBuildTime] = useState("");

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((d) => {
        if (d.build_tag) setBackendTag(d.build_tag);
        if (d.build_time) setBackendBuildTime(d.build_time);
      })
      .catch(() => {});
  }, []);

  return (
    <nav className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">💊</div>
        药物靶点决策系统
      </div>

      <div
        className={`nav-item${page === "assess" ? " active" : ""}`}
        onClick={() => onNavigate("assess")}
      >
        📝 新建评估
      </div>
      <div
        className={`nav-item${page === "history" ? " active" : ""}`}
        onClick={() => onNavigate("history")}
      >
        📋 历史报告
      </div>
      <div
        className={`nav-item${page === "search" ? " active" : ""}`}
        onClick={() => onNavigate("search")}
      >
        🔍 知识检索
      </div>

      {showStepper && (
        <>
          <div className="nav-divider" />
          <div className="nav-section">当前评估</div>
          {STEPS.map((s, i) => {
            const idx = stepIndex(s.key);
            let dotClass = "step-dot step-dot--pending";
            let labelClass = "step-label step-label--pending";
            let dotContent: string = String(i + 1);

            if (idx < currentIdx) {
              dotClass = "step-dot step-dot--done";
              labelClass = "step-label step-label--done";
              dotContent = "✓";
            } else if (idx === currentIdx) {
              if (s.key === "running") {
                dotClass = "step-dot step-dot--running";
                dotContent = "⟳";
              } else {
                dotClass = "step-dot step-dot--current";
                dotContent = String(i + 1);
              }
              labelClass = "step-label step-label--current";
            }

            return (
              <div key={s.key} className="step-item">
                <div className={dotClass}>
                  {s.key === "running" && idx === currentIdx ? (
                    <span className="spin">{dotContent}</span>
                  ) : (
                    dotContent
                  )}
                </div>
                <span className={labelClass}>{s.label}</span>
              </div>
            );
          })}
        </>
      )}

      <div className="sidebar-spacer" />

      <div className="sidebar-footer">
        Frontend: {__GIT_TAG__}<br />
        Backend: {backendTag || "..."}<br />
        构建: {new Date(backendBuildTime || __BUILD_TIME__).toLocaleString("zh-CN", {
          timeZone: "Asia/Shanghai",
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        })} CST
      </div>
    </nav>
  );
}
