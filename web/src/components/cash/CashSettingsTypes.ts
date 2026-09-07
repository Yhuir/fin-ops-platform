export type CashAccountSetting = {
  id: string;
  name: string;
  kind: "cash" | "savings";
  opening_date: string;
  opening_amount: string;
  enabled: boolean;
  remark: string | null;
  version: number;
};

export type CashCategorySetting = {
  id: string;
  name: string;
  group: "receipt" | "payment" | "turnover";
  enabled: boolean;
  remark: string | null;
  version: number;
};

export type CashBillLabelSetting = {
  id: string;
  bank_name: string;
  label: string;
  enabled: boolean;
  version: number;
};

export type CashProjectSelection = {
  allowed_stage_codes: string[];
  configured: boolean;
  version: number;
};

export type CashProjectSetting = {
  id: string;
  code: string | null;
  name: string;
  stage_code: string | null;
  stage_name: string | null;
  selectable: boolean;
  unavailable_reason: "ended" | "stage_not_allowed" | "stage_missing" | "stage_unknown" | null;
};

export type CashProjectsPage = {
  rows: CashProjectSetting[];
  stages: { code: string; name: string }[];
  total: number;
  page: number;
  page_size: number;
  read_at: string;
  selection_settings_version: number;
  configured: boolean;
};

export const cashCategoryGroupLabels = { receipt: "收入", payment: "支出", turnover: "往来（收付均可）" };
export const cashProjectUnavailableLabels = {
  ended: "已结束", stage_not_allowed: "该阶段未勾选", stage_missing: "阶段缺失", stage_unknown: "未知阶段",
};
