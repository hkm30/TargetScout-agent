import { useState } from "react";

interface Props {
  onSubmit: (target: string, indication: string, synonyms: string, focus: string, timeRange: string) => void;
  loading: boolean;
}

export function SearchForm({ onSubmit, loading }: Props) {
  const [target, setTarget] = useState("");
  const [indication, setIndication] = useState("");
  const [synonyms, setSynonyms] = useState("");
  const [focus, setFocus] = useState("");
  const [timeRange, setTimeRange] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (target.trim())
          onSubmit(target.trim(), indication.trim(), synonyms.trim(), focus.trim(), timeRange);
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
      <button type="submit" disabled={loading || !target.trim()} style={{ padding: "10px 20px" }}>
        {loading ? "解析中..." : "开始评估"}
      </button>
    </form>
  );
}
