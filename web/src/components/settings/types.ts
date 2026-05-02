import type {
  BankAccountMapping,
  WorkbenchAccessRole,
  WorkbenchOaImportSettings,
  WorkbenchProjectSetting,
  WorkbenchSettingsDataResetAction,
  WorkbenchSettingsDataResetJob,
} from "../../features/workbench/types";

export type ManagedAccessAccount = {
  id: string;
  username: string;
  role: WorkbenchAccessRole;
};

export type SettingsSectionId =
  | "projects"
  | "bank_accounts"
  | "oa_retention"
  | "oa_invoice_offset"
  | "access_accounts"
  | "data_reset";

export type SettingsNavigationItem = {
  id: SettingsSectionId;
  label: string;
  description: string;
  count: number;
};

export type ProjectActionStatus = {
  tone: "success" | "error";
  message: string;
};

export type DataResetStatus = {
  tone: "success" | "error";
  message: string;
};

export type DataResetActionConfig = {
  action: WorkbenchSettingsDataResetAction;
  label: string;
  title: string;
  description: string;
  impact: string[];
};

export type SettingsProjectsSectionProps = {
  activeProjects: WorkbenchProjectSetting[];
  completedProjects: WorkbenchProjectSetting[];
  controlsDisabled: boolean;
  projectActionStatus: ProjectActionStatus | null;
  projectCodeDraft: string;
  projectNameDraft: string;
  onChangeProjectCodeDraft: (value: string) => void;
  onChangeProjectNameDraft: (value: string) => void;
  onSyncProjects: () => Promise<void> | void;
  onAddProject: () => Promise<void> | void;
  onToggleCompleted: (projectId: string) => void;
  onDeleteProject: (project: WorkbenchProjectSetting) => Promise<void> | void;
  isProjectActionBusy: boolean;
  canAddProject: boolean;
};

export type SettingsBankAccountsSectionProps = {
  controlsDisabled: boolean;
  mappings: BankAccountMapping[];
  bankNameDraft: string;
  bankShortNameDraft: string;
  last4Draft: string;
  canAddMapping: boolean;
  onChangeBankNameDraft: (value: string) => void;
  onChangeBankShortNameDraft: (value: string) => void;
  onChangeLast4Draft: (value: string) => void;
  onAddMapping: () => void;
  onUpdateMapping: (mappingId: string, updater: (mapping: BankAccountMapping) => BankAccountMapping) => void;
  onDeleteMapping: (mappingId: string) => void;
};

export type SettingsOaRetentionSectionProps = {
  controlsDisabled: boolean;
  cutoffDate: string;
  oaImport: WorkbenchOaImportSettings;
  onChangeCutoffDate: (value: string) => void;
  onToggleFormType: (value: string) => void;
  onToggleStatus: (value: string) => void;
};

export type SettingsOaInvoiceOffsetSectionProps = {
  controlsDisabled: boolean;
  applicantsText: string;
  onChangeApplicantsText: (value: string) => void;
};

export type SettingsAccessAccountsSectionProps = {
  controlsDisabled: boolean;
  adminUsernames: string[];
  managedAccessAccounts: ManagedAccessAccount[];
  accessUsernameDraft: string;
  accessRoleDraft: WorkbenchAccessRole;
  canAddAccessAccount: boolean;
  onChangeAccessUsernameDraft: (value: string) => void;
  onChangeAccessRoleDraft: (value: WorkbenchAccessRole) => void;
  onAddAccessAccount: () => void;
  onUpdateManagedAccessAccount: (
    accountId: string,
    updater: (account: ManagedAccessAccount) => ManagedAccessAccount,
  ) => void;
  onDeleteManagedAccessAccount: (accountId: string) => void;
};

export type SettingsDataResetSectionProps = {
  controlsDisabled: boolean;
  dataResetStatus: DataResetStatus | null;
  dataResetProgress: WorkbenchSettingsDataResetJob | null;
  actions: DataResetActionConfig[];
  onOpenDataResetConfirm: (action: WorkbenchSettingsDataResetAction) => void;
};
