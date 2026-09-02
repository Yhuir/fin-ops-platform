import type {
  BankAccountMapping,
  OaApplicantCredentialSummary,
  SaveOaApplicantCredentialRequest,
  WorkbenchAccessControl,
  WorkbenchAccessUser,
  WorkbenchSettings,
  WorkbenchOaImportSettings,
  WorkbenchProjectSetting,
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
  | "projects"
  | "bank_accounts"
  | "pending_invoice_tags"
  | "oa_retention"
  | "oa_invoice_offset"
  | "oa_applicant_credentials"
  | "access_accounts"
  | "data_reset";

export type SettingsNavigationItem = {
  id: SettingsSectionId;
  label: string;
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

export type SettingsPendingInvoiceTagsSectionProps = {
  controlsDisabled: boolean;
  tags: WorkbenchSettings["bankTransactionTags"]["tags"];
  groups: WorkbenchSettings["pendingInvoiceTagGroups"];
  activeGroup: keyof WorkbenchSettings["pendingInvoiceTagGroups"];
  onSelectGroup: (group: keyof WorkbenchSettings["pendingInvoiceTagGroups"]) => void;
  onAddExistingTag: (code: string) => void;
  onRemoveTag: (code: string) => void;
};

export type SettingsOaRetentionSectionProps = {
  controlsDisabled: boolean;
  cutoffDate: string;
  oaImport: WorkbenchOaImportSettings;
  onChangeCutoffDate: (value: string) => void;
  onChangeAttachmentInvoicePromotionMode: (value: WorkbenchOaImportSettings["attachmentInvoicePromotionMode"]) => void;
  onToggleFormType: (value: string) => void;
  onToggleStatus: (value: string) => void;
};

export type SettingsOaInvoiceOffsetSectionProps = {
  controlsDisabled: boolean;
  applicantsText: string;
  onChangeApplicantsText: (value: string) => void;
};

export type SettingsOaApplicantCredentialsSectionProps = {
  controlsDisabled: boolean;
  credentials: OaApplicantCredentialSummary[];
  isLoading: boolean;
  isSaving: boolean;
  status: ProjectActionStatus | null;
  targetApplicantNameDraft: string;
  targetApplicantCodeDraft: string;
  oaUsernameDraft: string;
  oaPasswordDraft: string;
  canSaveCredential: boolean;
  onChangeTargetApplicantNameDraft: (value: string) => void;
  onChangeTargetApplicantCodeDraft: (value: string) => void;
  onChangeOaUsernameDraft: (value: string) => void;
  onChangeOaPasswordDraft: (value: string) => void;
  onSelectCredential: (credential: OaApplicantCredentialSummary) => void;
  onSaveCredential: (payload: SaveOaApplicantCredentialRequest) => Promise<void> | void;
  onClearCredential: (targetApplicantCode: string) => Promise<void> | void;
};

export type SettingsAccessAccountsSectionProps = {
  controlsDisabled: boolean;
  administrator: WorkbenchAccessControl["administrator"] | null;
  managedAccessAccounts: ManagedAccessAccount[];
  isLoading: boolean;
  isSaving: boolean;
  status: ProjectActionStatus | null;
  validationMessage: string | null;
  onAddAccessAccount: (user: WorkbenchAccessUser) => void;
  onSearchAccessUsers: (query: string, signal?: AbortSignal) => Promise<WorkbenchAccessUser[]>;
  onUpdateManagedAccessAccount: (
    accountId: string,
    updater: (account: ManagedAccessAccount) => ManagedAccessAccount,
  ) => void;
  onDeleteManagedAccessAccount: (accountId: string) => void;
  onSave: () => Promise<void> | void;
};

export type SettingsDataResetSectionProps = {
  controlsDisabled: boolean;
  dataResetStatus: DataResetStatus | null;
  dataResetProgress: WorkbenchSettingsDataResetJob | null;
  actions: DataResetActionConfig[];
  onOpenDataResetConfirm: (action: WorkbenchSettingsDataResetAction) => void;
};
