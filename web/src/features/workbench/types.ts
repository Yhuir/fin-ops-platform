export type WorkbenchRecordType = "oa" | "bank" | "invoice";

export type WorkbenchActionVariant = "detail-only" | "bank-review" | "confirm-exception";

export type WorkbenchDetailField = {
  label: string;
  value: string;
};

export type WorkbenchRecord = {
  id: string;
  caseId?: string;
  recordType: WorkbenchRecordType;
  label: string;
  status: string;
  statusCode: string;
  statusTone: string;
  exceptionHandled: boolean;
  amount: string;
  counterparty: string;
  tableValues: Record<string, string>;
  detailFields: WorkbenchDetailField[];
  actionVariant: WorkbenchActionVariant;
  availableActions: string[];
};

export type WorkbenchProjectSetting = {
  id: string;
  projectCode: string;
  projectName: string;
  projectStatus: "active" | "completed";
  departmentName?: string | null;
  ownerName?: string | null;
};

export type BankAccountMapping = {
  id: string;
  last4: string;
  bankName: string;
};

export type WorkbenchSettings = {
  projects: {
    active: WorkbenchProjectSetting[];
    completed: WorkbenchProjectSetting[];
    completedProjectIds: string[];
  };
  bankAccountMappings: BankAccountMapping[];
};

export type WorkbenchPaneRows = {
  oa: WorkbenchRecord[];
  bank: WorkbenchRecord[];
  invoice: WorkbenchRecord[];
};

export type WorkbenchMatchConfidence = "high" | "medium" | "low";

export type WorkbenchGroupType = "auto_closed" | "manual_confirmed" | "candidate";

export type WorkbenchCandidateGroup = {
  id: string;
  groupType: WorkbenchGroupType;
  matchConfidence: WorkbenchMatchConfidence;
  reason: string;
  rows: WorkbenchPaneRows;
};

export type WorkbenchSummary = {
  oaCount: number;
  bankCount: number;
  invoiceCount: number;
  pairedCount: number;
  openCount: number;
  exceptionCount: number;
  totalCount: number;
};

export type WorkbenchData = {
  month: string;
  summary: WorkbenchSummary;
  paired: {
    groups: WorkbenchCandidateGroup[];
  };
  open: {
    groups: WorkbenchCandidateGroup[];
  };
};

export type IgnoredWorkbenchData = {
  month: string;
  rows: WorkbenchRecord[];
};
