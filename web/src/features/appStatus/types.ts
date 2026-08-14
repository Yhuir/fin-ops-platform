export type AppStatusLevel = "ok" | "busy" | "blocked";
export type AppStatusColor = "green" | "yellow" | "red";

export type AppStatusOverall = {
  level: AppStatusLevel;
  color: AppStatusColor;
  reason: string;
  blocksMutations: boolean;
  writeSafety: AppStatusWriteSafety;
};

export type AppStatusWriteSafety = {
  status: string;
  reason: string;
  blocksMutations: boolean;
  blockers: string[];
};

export type AppStatusDomain = {
  key: string;
  label: string;
  route: string;
  level: AppStatusLevel;
  status: string;
  reason: string;
  details: string[];
  workers: string[];
  jobIds: string[];
  updatedAt: string;
};

export type AppStatusTask = {
  jobId: string;
  type: string;
  status: string;
  label: string;
  shortLabel: string;
  message: string;
  phase: string;
  current: number;
  total: number;
  percent: number | null;
  affectedDomains: string[];
  affectedScopes: string[];
  affectedMonths: string[];
  route: string;
  attention: boolean;
  updatedAt: string;
};

export type AppStatusRuntimeSummaryGroup = {
  total: number;
  fresh?: number;
  ready?: number;
  idle?: number;
  working?: number;
  refreshing?: number;
  stale?: number;
  missing?: number;
  failed?: number;
  unavailable?: number;
  mismatched?: number;
  required?: number;
  issueCount?: number;
  scopeIssueCount?: number;
};

export type AppStatusQueueSummary = {
  eventTypeCount: number;
  pending: number;
  processing: number;
  failed: number;
  backlog: number;
};

export type AppStatusRuntimeSummary = {
  workers: AppStatusRuntimeSummaryGroup;
  queue: AppStatusQueueSummary;
};

export type AppStatusOverview = {
  version: number;
  generatedAt: string;
  overall: AppStatusOverall;
  runtimeSummary: AppStatusRuntimeSummary;
  domains: AppStatusDomain[];
  backgroundTasks: AppStatusTask[];
  alerts: Array<Record<string, unknown>>;
};
