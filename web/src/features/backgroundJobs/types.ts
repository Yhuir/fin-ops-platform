export type BackgroundJobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "partial_success"
  | "failed"
  | "cancelled"
  | "acknowledged"
  | "superseded";

export type BackgroundJobType =
  | "etc_invoice_import"
  | "file_import"
  | "settings_data_reset"
  | "oa_attachment_invoice_parse"
  | "workbench_matching"
  | "workbench_rebuild"
  | "tax_certified_import"
  | "etc_oa_draft";

export type BackgroundJob = {
  jobId: string;
  type: BackgroundJobType | string;
  label: string;
  shortLabel: string;
  status: BackgroundJobStatus;
  phase: string;
  current: number;
  total: number;
  percent: number;
  message: string;
  resultSummary: Record<string, unknown>;
  affectedScopeKeys: string[];
  source: Record<string, unknown>;
  retryable: boolean;
  retryMode: string;
  acknowledgeable: boolean;
  attention: boolean;
  supersededByJobId: string | null;
  affectedMonths: string[];
  error: string | null;
  createdAt: string;
  updatedAt: string;
  finishedAt: string | null;
};

export type BackgroundJobActivePayload = {
  jobs: BackgroundJob[];
};
