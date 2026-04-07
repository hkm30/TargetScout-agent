import type { AssessmentResult, ParseResult, ParsedInput } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";
const API_KEY = import.meta.env.VITE_API_KEY || "";

function getHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  if (API_KEY) h["X-API-Key"] = API_KEY;
  return h;
}

export interface SSEEvent {
  event: string;
  data: any;
}

export async function parseAssessment(
  target: string,
  indication: string,
  synonyms?: string,
  focus?: string,
  time_range?: string,
): Promise<ParseResult> {
  const body: Record<string, string> = { target, indication };
  if (synonyms) body.synonyms = synonyms;
  if (focus) body.focus = focus;
  if (time_range) body.time_range = time_range;
  const resp = await fetch(`${API_BASE}/assess/parse`, {
    method: "POST",
    headers: { ...getHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}

/**
 * Confirm assessment via SSE streaming — calls onEvent for each progress event
 * and resolves with the final AssessmentResult.
 */
export async function confirmAssessmentSSE(
  parsed: ParsedInput,
  onEvent: (event: SSEEvent) => void,
): Promise<AssessmentResult> {
  const resp = await fetch(`${API_BASE}/assess/confirm`, {
    method: "POST",
    headers: { ...getHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(parsed),
  });
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  if (!resp.body) throw new Error("No response body");

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: AssessmentResult | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Parse SSE events from buffer
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || ""; // keep incomplete last part

    for (const part of parts) {
      if (!part.trim()) continue;
      let currentEvent = "message";
      let currentData = "";
      for (const line of part.split("\n")) {
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7);
        } else if (line.startsWith("data: ")) {
          currentData += line.slice(6);
        }
      }
      if (currentData) {
        try {
          const data = JSON.parse(currentData);
          const evt: SSEEvent = { event: currentEvent, data };
          onEvent(evt);
          if (currentEvent === "result") {
            finalResult = data;
          }
        } catch {
          // ignore malformed events
        }
      }
    }
  }

  if (!finalResult) throw new Error("No result received from stream");
  return finalResult;
}

/** Legacy non-streaming confirm (backward compatible) */
export async function confirmAssessment(
  parsed: ParsedInput,
): Promise<AssessmentResult> {
  const resp = await fetch(`${API_BASE}/assess/confirm`, {
    method: "POST",
    headers: { ...getHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(parsed),
  });
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}

export async function assessTarget(
  target: string,
  indication: string,
  synonyms?: string,
  focus?: string,
  time_range?: string,
): Promise<AssessmentResult> {
  const body: Record<string, string> = { target, indication };
  if (synonyms) body.synonyms = synonyms;
  if (focus) body.focus = focus;
  if (time_range) body.time_range = time_range;
  const resp = await fetch(`${API_BASE}/assess`, {
    method: "POST",
    headers: { ...getHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}

export async function exportMarkdown(
  reportId: string,
  target: string
): Promise<string> {
  const resp = await fetch(`${API_BASE}/export/markdown`, {
    method: "POST",
    headers: { ...getHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ report_id: reportId, target }),
  });
  if (!resp.ok) throw new Error(`Export failed: ${resp.status}`);
  const data = await resp.json();
  return data.markdown;
}

export async function exportWord(reportId: string, target: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/export/word`, {
    method: "POST",
    headers: { ...getHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ report_id: reportId, target }),
  });
  if (!resp.ok) throw new Error(`Export failed: ${resp.status}`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${target}_report.docx`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function exportPdf(reportId: string, target: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/export/pdf`, {
    method: "POST",
    headers: { ...getHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ report_id: reportId, target }),
  });
  if (!resp.ok) throw new Error(`Export failed: ${resp.status}`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${target}_report.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function fetchReports(): Promise<{ reports: import("./types").ReportListItem[] }> {
  const res = await fetch(`${API_BASE}/reports`, { headers: getHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch reports: ${res.status}`);
  return res.json();
}

export async function fetchReport(id: string, target: string): Promise<import("./types").AssessmentResult> {
  const res = await fetch(`${API_BASE}/reports/${id}?target=${encodeURIComponent(target)}`, { headers: getHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch report: ${res.status}`);
  return res.json();
}

export async function deleteReport(id: string, target: string): Promise<void> {
  const res = await fetch(`${API_BASE}/reports/${id}?target=${encodeURIComponent(target)}`, {
    method: "DELETE",
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to delete report: ${res.status}`);
}

export async function searchKnowledge(query: string, topK: number = 5): Promise<{ results: import("./types").SearchResultItem[]; count: number }> {
  const res = await fetch(`${API_BASE}/knowledge/search`, {
    method: "POST",
    headers: { ...getHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  return res.json();
}
