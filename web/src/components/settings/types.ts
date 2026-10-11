import type {
  BankAccountMapping,
  WorkbenchAccessControl,
  WorkbenchAccessUser,
  WorkbenchSettings,
  WorkbenchOaImportSettings,
  WorkbenchSettingsDataResetAction,
  WorkbenchSettingsDataResetJob,
} from "../../features/workbench/types";

export type ManagedAccessAccount = {
  id: string;
  username: string;
  displayName: string;
  oaStatus: "active" | "inactive" | "missing";
  pageKeys: string[];
};

export type SettingsSectionId =
  | "bank_accounts"
  | "oa_retention"
  | "access_accounts"
  | "data_reset"
  | "batch-accounting";

export type SettingsNavigationItem = {
  id: SettingsSectionId;
  label: string;
};

export type SettingsActionStatus = {
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
};

export type SettingsBankAccountsSectionProps = {
  controlsDisabled: boolean;
  mappings: BankAccountMapping[];
  bankNameDraft: string;
  bankShortNameDraft: string;
  last4Draft: string;
  canAddMapping: boolean;
  hasPendingMapping: boolean;
  invalidMappingIds: ReadonlySet<string>;
  validationMessage: string | null;
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
  cutoffDateError: string | null;
  oaImport: WorkbenchOaImportSettings;
  onChangeCutoffDate: (value: string) => void;
  onChangeAttachmentInvoicePromotionMode: (value: WorkbenchOaImportSettings["attachmentInvoicePromotionMode"]) => void;
  onToggleFormType: (value: string) => void;
  onToggleStatus: (value: string) => void;
};

export type SettingsAccessAccountsSectionProps = {
  changedAccountIds: ReadonlySet<string>;
  controlsDisabled: boolean;
  administrator: WorkbenchAccessControl["administrator"] | null;
  managedAccessAccounts: ManagedAccessAccount[];
  isLoading: boolean;
  isSaving: boolean;
  onAddAccessAccount: (user: WorkbenchAccessUser) => void;
  onSearchAccessUsers: (query: string, signal?: AbortSignal) => Promise<WorkbenchAccessUser[]>;
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
