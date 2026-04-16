import { useState } from "react";
import type { ParseResult, ParsedInput, SubTask, UploadedDocument } from "../types";
import { HistoricalContext } from "./HistoricalContext";

interface Props {
  parseResult: ParseResult;
  documents: UploadedDocument[];
  onConfirm: (modified: ParsedInput) => void;
  onBack: () => void;
  initialSuggestions: string;
  onCancel: () => void;
  onRemoveDocument: (docId: string) => void;
  loading: boolean;
}

export function ConfirmationPanel({ parseResult, documents, initialSuggestions, onConfirm, onBack, onCancel, onRemoveDocument, loading }: Props) {
  const [target, setTarget] = useState(parseResult.parsed.target);
  const [indication, setIndication] = useState(parseResult.parsed.indication);
  const [synonyms, setSynonyms] = useState(parseResult.parsed.synonyms);
  const [focus, setFocus] = useState(parseResult.parsed.focus);
  const [timeRange, setTimeRange] = useState(parseResult.parsed.time_range);
  const [userSuggestions, setUserSuggestions] = useState(initialSuggestions);

  const handleConfirm = () => {
    onConfirm({
      target,
      indication,
      synonyms,
      focus,
      time_range: timeRange,
      document_ids: [...new Set(documents.filter((d) => d.status === "ready" || d.status === "duplicate" || d.status === "pending").map((d) => d.id))],
      user_suggestions: userSuggestions,
    });
  };

  const inputStyle = {
    display: "block" as const,
    width: "100%",
    padding: "8px",
    marginTop: "4px",
    border: "1px solid #d1d5db",
    borderRadius: "4px",
  };

  return (
    <div>
      <h2 style={{ marginBottom: "8px" }}>确认查询参数</h2>
      <p style={{ color: "#666", marginBottom: "16px" }}>
        请审核解析结果和任务规划，可修改任意字段后运行。
      </p>

      {/* Editable parsed input */}
      <div
        style={{
          background: "#f9fafb",
          border: "1px solid #e5e7eb",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "16px",
        }}
      >
        <h3 style={{ margin: "0 0 12px", fontSize: "1em" }}>解析结果</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "10px", maxWidth: "500px" }}>
          <label>
            靶点名称 *
            <input type="text" value={target} onChange={(e) => setTarget(e.target.value)} style={inputStyle} />
          </label>
          <label>
            适应症
            <input type="text" value={indication} onChange={(e) => setIndication(e.target.value)} style={inputStyle} />
          </label>
          <label>
            同义词 / 别名
            <input type="text" value={synonyms} onChange={(e) => setSynonyms(e.target.value)} style={inputStyle} />
          </label>
          <label>
            研究重点
            <select value={focus} onChange={(e) => setFocus(e.target.value)} style={inputStyle}>
              <option value="">全部领域</option>
              <option value="literature">文献 / 基础研究</option>
              <option value="clinical">临床信号</option>
              <option value="competition">竞争格局</option>
            </select>
          </label>
          <label>
            其他建议（可选）
            <textarea
              value={userSuggestions}
              onChange={(e) => setUserSuggestions(e.target.value)}
              placeholder="例如：请关注该靶点在耐药性方面的最新进展，特别是T790M突变..."
              rows={3}
              style={{ ...inputStyle, resize: "vertical" }}
            />
          </label>
          <label>
            时间范围
            <select value={timeRange} onChange={(e) => setTimeRange(e.target.value)} style={inputStyle}>
              <option value="">默认（5 年）</option>
              <option value="1095">近 3 年</option>
              <option value="1825">近 5 年</option>
              <option value="3650">近 10 年</option>
            </select>
          </label>
        </div>
      </div>

      {/* Uploaded Documents */}
      {documents.length > 0 && (
        <div
          style={{
            background: "#eff6ff",
            border: "1px solid #bfdbfe",
            borderRadius: "8px",
            padding: "16px",
            marginBottom: "16px",
          }}
        >
          <h3 style={{ margin: "0 0 12px", fontSize: "1em" }}>已上传文档</h3>
          {documents.map((doc) => (
            <div
              key={doc.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 12px",
                background: "#fff",
                borderRadius: "4px",
                marginBottom: "6px",
                fontSize: "0.9em",
              }}
            >
              <span>
                {(doc.status === "ready" || doc.status === "pending" || doc.status === "duplicate") ? "✓" : doc.status === "failed" ? "✗" : "⏳"}{" "}
                {doc.file_name}
                <span style={{ color: "#9ca3af", marginLeft: "8px" }}>
                  ({(doc.file_size / 1024 / 1024).toFixed(1)}MB)
                </span>
              </span>
              <button
                type="button"
                onClick={() => onRemoveDocument(doc.id)}
                disabled={loading}
                style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af" }}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Sub-tasks plan */}
      <div
        style={{
          background: "#f0fdf4",
          border: "1px solid #86efac",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "16px",
        }}
      >
        <h3 style={{ margin: "0 0 12px", fontSize: "1em" }}>计划执行的子任务</h3>
        {parseResult.sub_tasks.map((task: SubTask, i: number) => (
          <div
            key={i}
            style={{
              background: "#fff",
              border: "1px solid #d1fae5",
              borderRadius: "6px",
              padding: "10px 14px",
              marginBottom: "8px",
            }}
          >
            <strong>{task.agent}</strong>
            <p style={{ margin: "4px 0", fontSize: "0.9em", color: "#555" }}>{task.description}</p>
            <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
              {task.tools.map((tool, j) => (
                <span
                  key={j}
                  style={{
                    padding: "2px 8px",
                    background: "#e0f2fe",
                    borderRadius: "4px",
                    fontSize: "0.75em",
                    color: "#0369a1",
                  }}
                >
                  {tool}
                </span>
              ))}
              {task.tools.length === 0 && (
                <span style={{ fontSize: "0.75em", color: "#888" }}>无外部工具（仅 LLM 推理）</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Historical context */}
      <HistoricalContext reports={parseResult.knowledge_base_context?.historical_reports || []} />

      {/* Action buttons: [确认并运行] [返回修改] [取消] */}
      <div style={{ display: "flex", gap: "8px", marginTop: "16px" }}>
        <button
          onClick={handleConfirm}
          disabled={loading || !target.trim()}
          style={{
            padding: "10px 24px",
            background: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            cursor: loading ? "not-allowed" : "pointer",
            fontWeight: 600,
          }}
        >
          {loading ? "分析运行中..." : "确认并运行"}
        </button>
        <button
          onClick={onBack}
          disabled={loading}
          style={{
            padding: "10px 24px",
            background: "#fff",
            border: "1px solid #d1d5db",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          返回修改
        </button>
        <button
          onClick={onCancel}
          disabled={loading}
          style={{
            padding: "10px 24px",
            background: "#fff",
            border: "1px solid #d1d5db",
            borderRadius: "6px",
            cursor: "pointer",
            color: "#dc2626",
          }}
        >
          取消
        </button>
      </div>
    </div>
  );
}
