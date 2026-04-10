import { useState, useRef } from "react";
import type { UploadedDocument } from "../types";
import { uploadDocuments, deleteDocument } from "../api";

interface Props {
  onSubmit: (target: string, indication: string, synonyms: string, focus: string, timeRange: string, documents: UploadedDocument[], userSuggestions: string) => void;
  loading: boolean;
}

const ACCEPTED_TYPES = ".pdf,.docx,.txt,.md";
const MAX_FILES = 5;
const MAX_SIZE_MB = 10;

export function SearchForm({ onSubmit, loading }: Props) {
  const [target, setTarget] = useState("");
  const [indication, setIndication] = useState("");
  const [synonyms, setSynonyms] = useState("");
  const [focus, setFocus] = useState("");
  const [timeRange, setTimeRange] = useState("");
  const [userSuggestions, setUserSuggestions] = useState("");
  const [documents, setDocuments] = useState<UploadedDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;

    const files = Array.from(fileList);
    const remaining = MAX_FILES - documents.length;
    if (files.length > remaining) {
      alert(`最多上传 ${MAX_FILES} 个文件，还可上传 ${remaining} 个`);
      return;
    }

    // Validate extensions and sizes
    const allowedExts = [".pdf", ".docx", ".txt", ".md"];
    for (const f of files) {
      const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
      if (!allowedExts.includes(ext)) {
        alert(`文件 ${f.name} 格式不支持，仅支持 PDF/Word/TXT/Markdown`);
        return;
      }
      if (f.size > MAX_SIZE_MB * 1024 * 1024) {
        alert(`文件 ${f.name} 超过 ${MAX_SIZE_MB}MB 限制`);
        return;
      }
    }

    // Add placeholders
    const placeholders: UploadedDocument[] = files.map((f) => ({
      id: "",
      file_name: f.name,
      file_size: f.size,
      status: "uploading" as const,
    }));
    setDocuments((prev) => [...prev, ...placeholders]);
    setUploading(true);

    try {
      const resp = await uploadDocuments(files);
      setDocuments((prev) => {
        // Replace placeholders with actual results
        const existing = prev.filter((d) => d.status !== "uploading");
        const uploaded = resp.documents.map((d) => ({
          ...d,
          status: d.status as UploadedDocument["status"],
        }));
        return [...existing, ...uploaded];
      });
    } catch {
      setDocuments((prev) => prev.filter((d) => d.status !== "uploading"));
      alert("文件上传失败，请重试");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleRemove = async (docId: string) => {
    const doc = documents.find((d) => d.id === docId);
    if (docId && doc?.status !== "duplicate") {
      try {
        await deleteDocument(docId);
      } catch {
        // Best effort
      }
    }
    setDocuments((prev) => prev.filter((d) => d.id !== docId));
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    handleFiles(e.dataTransfer.files);
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (target.trim())
          onSubmit(target.trim(), indication.trim(), synonyms.trim(), focus.trim(), timeRange, documents.filter((d) => d.status === "ready" || d.status === "duplicate" || d.status === "pending"), userSuggestions.trim());
      }}
      style={{ display: "flex", flexDirection: "column", gap: "12px", maxWidth: "500px" }}
    >
      <label>
        靶点名称 *
        <input
          type="text"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="例如 GLP-1R、TL1A、PCSK9"
          required
          style={{ display: "block", width: "100%", padding: "8px", marginTop: "4px" }}
        />
      </label>
      <label>
        适应症（可选）
        <input
          type="text"
          value={indication}
          onChange={(e) => setIndication(e.target.value)}
          placeholder="例如 肥胖症、炎症性肠病、高胆固醇血症"
          style={{ display: "block", width: "100%", padding: "8px", marginTop: "4px" }}
        />
      </label>
      <label>
        同义词 / 别名（可选）
        <input
          type="text"
          value={synonyms}
          onChange={(e) => setSynonyms(e.target.value)}
          placeholder="例如 GLP1R、胰高血糖素样肽-1受体"
          style={{ display: "block", width: "100%", padding: "8px", marginTop: "4px" }}
        />
      </label>
      <label>
        研究重点（可选）
        <select
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
          style={{ display: "block", width: "100%", padding: "8px", marginTop: "4px" }}
        >
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
          style={{ display: "block", width: "100%", padding: "8px", marginTop: "4px", resize: "vertical" }}
        />
      </label>
      <label>
        时间范围（可选）
        <select
          value={timeRange}
          onChange={(e) => setTimeRange(e.target.value)}
          style={{ display: "block", width: "100%", padding: "8px", marginTop: "4px" }}
        >
          <option value="">默认（5 年）</option>
          <option value="1095">近 3 年</option>
          <option value="1825">近 5 年</option>
          <option value="3650">近 10 年</option>
        </select>
      </label>

      {/* File Upload Area */}
      <div>
        <label style={{ display: "block", marginBottom: "4px" }}>上传私有文档（可选）</label>
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => fileInputRef.current?.click()}
          style={{
            border: "2px dashed #d1d5db",
            borderRadius: "8px",
            padding: "20px",
            textAlign: "center",
            cursor: "pointer",
            background: "#f9fafb",
          }}
        >
          <div style={{ color: "#6b7280", fontSize: "0.9em" }}>
            拖拽文件到此处或点击上传
          </div>
          <div style={{ color: "#9ca3af", fontSize: "0.8em", marginTop: "4px" }}>
            支持 PDF / Word / TXT / Markdown，最多 {MAX_FILES} 个文件，单文件 ≤ {MAX_SIZE_MB}MB
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_TYPES}
            multiple
            onChange={(e) => handleFiles(e.target.files)}
            style={{ display: "none" }}
          />
        </div>

        {/* File list */}
        {documents.length > 0 && (
          <div style={{ marginTop: "8px", display: "flex", flexDirection: "column", gap: "4px" }}>
            {documents.map((doc, i) => (
              <div
                key={doc.id || `uploading-${i}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "6px 10px",
                  background: doc.status === "failed" ? "#fef2f2" : doc.status === "duplicate" ? "#fefce8" : "#f0fdf4",
                  borderRadius: "4px",
                  fontSize: "0.85em",
                }}
              >
                <span>
                  {doc.status === "ready" && "✓ "}
                  {doc.status === "pending" && "✓ "}
                  {doc.status === "duplicate" && "✓ "}
                  {doc.status === "uploading" && "⏳ "}
                  {doc.status === "failed" && "✗ "}
                  {doc.file_name}
                  <span style={{ color: "#9ca3af", marginLeft: "8px" }}>
                    ({(doc.file_size / 1024 / 1024).toFixed(1)}MB)
                  </span>
                  {doc.status === "uploading" && <span style={{ color: "#6b7280", marginLeft: "8px" }}>上传中...</span>}
                  {doc.status === "pending" && <span style={{ color: "#16a34a", marginLeft: "8px" }}>已上传</span>}
                  {doc.status === "duplicate" && <span style={{ color: "#ca8a04", marginLeft: "8px" }}>{doc.message || "文件已经上传过"}</span>}
                  {doc.status === "failed" && <span style={{ color: "#dc2626", marginLeft: "8px" }}>{doc.error || "失败"}</span>}
                </span>
                {doc.status !== "uploading" && (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); handleRemove(doc.id); }}
                    style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af", fontSize: "1em" }}
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <button type="submit" disabled={loading || uploading || !target.trim()} style={{ padding: "10px 20px" }}>
        {loading ? "解析中..." : "开始评估"}
      </button>
    </form>
  );
}
