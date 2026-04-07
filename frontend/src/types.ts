export interface Citation {
  title: string;
  link: string;
  source_type: "PubMed" | "ClinicalTrials" | "Web";
}

export interface Report {
  target: string;
  indication: string;
  literature_summary: string;
  clinical_trials_summary: string;
  competition_summary: string;
  major_risks: string[];
  major_opportunities: string[];
  recommendation: "Go" | "No-Go" | "Need More Data";
  reasoning: string;
  uncertainty: string;
  citations: Citation[];
  report_id?: string;
}

export interface Trial {
  nct_id: string;
  title: string;
  phase: string;
  status: string;
  conditions: string[];
  interventions: { name: string; type: string }[];
  sponsor: string;
  link: string;
}

export interface Paper {
  pmid: string;
  title: string;
  abstract: string;
  authors: string;
  year: string;
  link: string;
  source_type: string;
}

export interface SubTask {
  agent: string;
  description: string;
  tools: string[];
}

export interface ParsedInput {
  target: string;
  indication: string;
  synonyms: string;
  focus: string;
  time_range: string;
}

export interface ParseResult {
  parsed: ParsedInput;
  sub_tasks: SubTask[];
  knowledge_base_context: { historical_reports: any[]; count: number };
}

export interface SSEStatusEvent {
  stage: string;
  status: "started" | "completed" | "failed";
  error?: string;
}

export interface AssessmentResult {
  report: Report;
  raw_outputs: {
    literature: { papers?: any[]; summary?: any; [key: string]: any };
    clinical_trials: { trials?: any[]; summary?: any; [key: string]: any };
    competition: { summary?: any; major_players?: any[]; [key: string]: any };
  };
  knowledge_base_context: { historical_reports: any[]; count: number };
  partial_failures?: string[];
}

export type Page = "assess" | "history" | "search";
export type AssessStep = "input" | "confirm" | "running" | "done";

export interface ReportListItem {
  id: string;
  target: string;
  indication: string;
  recommendation: string;
  summary: string;
  created_at: string;
  score?: number;
}

export interface SearchResultItem {
  id: string;
  target: string;
  indication: string;
  recommendation: string;
  summary: string;
  created_at: string;
  score: number;
}

export interface PartialResultData {
  stage: string;
  result: Record<string, unknown>;
}
