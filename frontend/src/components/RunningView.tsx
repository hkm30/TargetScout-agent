import type { PartialResultData } from "../types";

interface Props {
  target: string;
  indication: string;
  agentProgress: Record<string, string>;
  partialResults: Record<string, PartialResultData>;
}

const STAGE_LABELS: Record<string, string> = {
  knowledge_base: "知识库检索",
  literature: "📚 文献研究",
  clinical_trials: "🏥 临床试验分析",
  competition: "🏢 竞争情报",
  decision: "决策综合",
  saving: "保存结果",
};

const PARALLEL_AGENTS = ["literature", "clinical_trials", "competition"] as const;

function stageIcon(status: string | undefined): string {
  if (status === "completed") return "✅";
  if (status === "started") return "⏳";
  if (status === "failed") return "❌";
  return "⬜";
}

function completedCount(progress: Record<string, string>): number {
  return Object.values(progress).filter((s) => s === "completed").length;
}

function summarizeResult(_stage: string, data: Record<string, unknown>): string {
  const raw = data.summary ?? data.overall_assessment;
  if (typeof raw === "string") return raw.slice(0, 200);
  if (raw && typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    const text = obj.overall_assessment || obj.summary || obj.text;
    if (typeof text === "string") return text.slice(0, 200);
    return JSON.stringify(raw).slice(0, 200);
  }
  return JSON.stringify(data).slice(0, 200);
}

export function RunningView({ target, indication, agentProgress, partialResults }: Props) {
  const done = completedCount(agentProgress);
  const total = 6;

  return (
    <div>
      <div className="content-header">
        <div className="content-title">正在分析中...</div>
      </div>

      {/* Progress card */}
      <div className="progress-card">
        <div className="progress-header">
          <span style={{ fontSize: 14, fontWeight: 600 }}>
            {target}{indication ? ` - ${indication}` : ""}
          </span>
          <span className="text-muted">进度 {done}/{total}</span>
        </div>

        {/* Phase 1: Knowledge base */}
        <div className="progress-phase">
          <span style={{ fontSize: 16 }}>{stageIcon(agentProgress.knowledge_base)}</span>
          <span>{STAGE_LABELS.knowledge_base}</span>
          <span className="text-muted" style={{ marginLeft: "auto" }}>
            {agentProgress.knowledge_base === "completed" ? "完成" : agentProgress.knowledge_base === "started" ? "进行中..." : "等待中"}
          </span>
        </div>

        {/* Phase 2: Parallel agents */}
        <div className="parallel-agents">
          {PARALLEL_AGENTS.map((key) => {
            const status = agentProgress[key];
            let cardClass = "agent-card agent-card--waiting";
            let labelClass = "agent-card__label agent-card__label--waiting";
            let icon = "⬜";
            let statusText = "等待中";

            if (status === "completed") {
              cardClass = "agent-card agent-card--done";
              labelClass = "agent-card__label agent-card__label--done";
              icon = "✅";
              statusText = "完成";
            } else if (status === "started") {
              cardClass = "agent-card agent-card--running";
              labelClass = "agent-card__label agent-card__label--running";
              icon = "⏳";
              statusText = "进行中...";
            } else if (status === "failed") {
              cardClass = "agent-card agent-card--done";
              icon = "❌";
              statusText = "失败";
            }

            return (
              <div key={key} className={cardClass}>
                <div className="agent-card__icon">{icon}</div>
                <div className={labelClass}>{STAGE_LABELS[key]}</div>
                <div className="agent-card__status" style={{ color: status === "started" ? "#92400E" : status === "completed" ? "#166534" : "#999" }}>
                  {statusText}
                </div>
                {status === "started" && (
                  <div className="agent-card__progress-bar">
                    <div className="agent-card__progress-fill" style={{ width: "60%" }} />
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Phase 3: Decision */}
        <div className="progress-phase" style={{ opacity: agentProgress.decision ? 1 : 0.4 }}>
          <span style={{ fontSize: 16 }}>{stageIcon(agentProgress.decision)}</span>
          <span style={{ color: agentProgress.decision ? "#1B1B1B" : "#999" }}>{STAGE_LABELS.decision}</span>
          <span className="text-muted" style={{ marginLeft: "auto" }}>
            {agentProgress.decision === "completed" ? "完成" : agentProgress.decision === "started" ? "进行中..." : "等待中"}
          </span>
        </div>

        {/* Phase 4: Saving */}
        <div className="progress-phase" style={{ opacity: agentProgress.saving ? 1 : 0.4 }}>
          <span style={{ fontSize: 16 }}>{stageIcon(agentProgress.saving)}</span>
          <span style={{ color: agentProgress.saving ? "#1B1B1B" : "#999" }}>{STAGE_LABELS.saving}</span>
          <span className="text-muted" style={{ marginLeft: "auto" }}>
            {agentProgress.saving === "completed" ? "完成" : agentProgress.saving === "started" ? "进行中..." : "等待中"}
          </span>
        </div>
      </div>

      {/* Partial results */}
      {Object.keys(partialResults).length > 0 && (
        <>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#555", marginBottom: 8 }}>
            已完成的分析结果
          </div>
          {Object.entries(partialResults).map(([stage, data]) => (
            <div key={stage} className="partial-result">
              <div className="partial-result__title">{STAGE_LABELS[stage] || stage}</div>
              <div className="partial-result__text">
                {summarizeResult(stage, data.result)}...
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
