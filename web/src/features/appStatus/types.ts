export type AppStatusLevel = "ok" | "busy" | "blocked";
export type AppStatusColor = "green" | "yellow" | "red";

export type AppStatusOverall = {
  level: AppStatusLevel;
  color: AppStatusColor;
  reason: string;
  blocksMutations: boolean;
};

export type AppStatusDomain = {
  key: string;
  label: string;
  route: string;
  level: AppStatusLevel;
  status: string;
  reason: string;
  details: string[];
  readModels: string[];
  readModelScopes: AppStatusReadModelScope[];
  workers: string[];
  jobIds: string[];
  updatedAt: string;
};

export type AppStatusReadModelScope = {
  readModelKey: string;
  scopeType: string;
  scopeKey: string;
  status: string;
  lastError: string;
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

export type AppStatusOverview = {
  version: number;
  generatedAt: string;
  overall: AppStatusOverall;
  domains: AppStatusDomain[];
  backgroundTasks: AppStatusTask[];
  alerts: Array<Record<string, unknown>>;
};
