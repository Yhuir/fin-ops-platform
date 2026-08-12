import type { WorkbenchRecordType } from "./types";

export type WorkbenchExceptionBusinessLine = "expense" | "income" | "data_anomaly" | (string & {});

export type WorkbenchExceptionResultStatus = "closed" | "open" | "ignored" | "cancelled" | (string & {});

export type WorkbenchExceptionScenario = {
  businessLine: WorkbenchExceptionBusinessLine;
  scenarioCode: string;
  scenarioLabel: string;
  confidence?: string;
  requiredObjects?: string[];
  amountRelation?: string;
};

export type WorkbenchExceptionAmountSummary = {
  oaTotal: string;
  bankExpenseTotal: string;
  bankIncomeTotal: string;
  inputInvoiceTotal: string;
  outputInvoiceTotal: string;
  relation: string;
};

export type WorkbenchExceptionAction = {
  actionCode: string;
  label: string;
  resultStatus: WorkbenchExceptionResultStatus;
  requiredFields: string[];
  description?: string;
};

export type WorkbenchExceptionWarning = {
  code: string;
  severity: "info" | "warning" | "error" | (string & {});
  message: string;
};

export type WorkbenchExceptionCandidateEvidence = {
  id?: string;
  label: string;
  detail?: string;
  metadata?: Record<string, unknown>;
};

export type WorkbenchExceptionPreview = {
  ruleVersion: string;
  scenario: WorkbenchExceptionScenario;
  amountSummary: WorkbenchExceptionAmountSummary;
  automaticActions: WorkbenchExceptionAction[];
  availableActions: WorkbenchExceptionAction[];
  warnings: WorkbenchExceptionWarning[];
  workflowProjection: Record<string, unknown>;
  candidateEvidence: WorkbenchExceptionCandidateEvidence[];
  canApply: boolean;
};

export type WorkbenchExceptionPreviewPayload = {
  month: string;
  rowIds: string[];
  rowTypes: WorkbenchRecordType[];
};

export type WorkbenchExceptionApplyPayload = {
  month: string;
  rowIds: string[];
  rowTypes: WorkbenchRecordType[];
  scenarioCode: string;
  actionCode: string;
  payload: Record<string, unknown>;
};

export type WorkbenchExceptionApplyResult = {
  success: boolean;
  case: Record<string, unknown> | null;
  pairRelation: Record<string, unknown> | null;
  updatedRows: Array<Record<string, unknown>>;
  affectedRowIds: string[];
  affectedScopeKeys: string[];
  message?: string;
};
