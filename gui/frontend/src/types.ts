// types.ts — shared TypeScript interfaces for the Chickpea SRG RAG GUI

export type IntentType =
  | 'GENE_PROFILE'
  | 'GENE_LIST'
  | 'EXPRESSION'
  | 'SEQUENCE'
  | 'STRESS_LABEL'
  | 'COMPARISON'
  | 'OUT_OF_SCOPE';

export type OutputFormat =
  | 'FULL_PROFILE'
  | 'COMPACT_LIST'
  | 'FOCUSED'
  | 'NONE';

export interface StageEvent {
  stage: string;
  label: string;
  index: number;
}

export interface PipelineResult {
  gene_id: string;
  intent: IntentType;
  output_format: OutputFormat;
  agents_used: string[];
  llm_response: string;
  validation_applied: boolean;
  router_note: string;
  error?: string;
}

export interface HealthResponse {
  status: 'ok' | 'error';
  backend: string;
}

export interface HistoryEntry {
  id: string;
  timestamp: number;
  query: string;
  result: PipelineResult;
}
