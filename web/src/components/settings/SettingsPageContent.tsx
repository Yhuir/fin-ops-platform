import { Button } from "@heroui/react";
import { useEffect, useMemo, useState } from "react";

import { usePageSessionState } from "../../contexts/PageSessionStateContext";
import { useSession } from "../../contexts/SessionContext";
import type {
  BankAccountMapping,
  OaApplicantCredentialSummary,
  SaveOaApplicantCredentialRequest,
  WorkbenchAccessAccount,
  WorkbenchAccessControl,
  WorkbenchAccessUser,
  WorkbenchProjectSetting,
  WorkbenchSettings,
  WorkbenchSettingsDataResetAction,
  WorkbenchSettingsDataResetJob,
  WorkbenchSettingsDataResetPreview,
  WorkbenchSettingsDataResetResult,
} from "../../features/workbench/types";
import SettingsAccessAccountsSection from "./SettingsAccessAccountsSection";
import SettingsBankAccountsSection from "./SettingsBankAccountsSection";
import SettingsDataResetDialogs from "./SettingsDataResetDialogs";
import SettingsDataResetSection from "./SettingsDataResetSection";
import SettingsOaApplicantCredentialsSection from "./SettingsOaApplicantCredentialsSection";
import SettingsOaInvoiceOffsetSection from "./SettingsOaInvoiceOffsetSection";
import SettingsOaRetentionSection from "./SettingsOaRetentionSection";
import SettingsPendingInvoiceTagsSection from "./SettingsPendingInvoiceTagsSection";
import SettingsProjectsSection from "./SettingsProjectsSection";
import SettingsTreeNav from "./SettingsTreeNav";
import type {
  DataResetActionConfig,
  DataResetStatus,
  ManagedAccessAccount,
  ProjectActionStatus,
  SettingsNavigationItem,
  SettingsSectionId,
} from "./types";

type SettingsPageContentProps = {
  settings: WorkbenchSettings;
  accessControl: WorkbenchAccessControl | null;
  accessControlStatus: ProjectActionStatus | null;
  isSaving: boolean;
  isAccessControlLoading: boolean;
  isAccessControlSaving: boolean;
  canSave: boolean;
  canManageAccessControl: boolean;
  activeDataResetJob: WorkbenchSettingsDataResetJob | null;
  oaApplicantCredentials: OaApplicantCredentialSummary[];
  isOaApplicantCredentialLoading: boolean;
  isOaApplicantCredentialSaving: boolean;
  onSave: (payload: {
    completedProjectIds: string[];
    bankAccountMappings: BankAccountMapping[];
    workbenchColumnLayouts: WorkbenchSettings["workbenchColumnLayouts"];
    oaRetention: WorkbenchSettings["oaRetention"];
    oaImport: WorkbenchSettings["oaImport"];
    oaInvoiceOffset: WorkbenchSettings["oaInvoiceOffset"];
    bankTransactionTags: WorkbenchSettings["bankTransactionTags"];
    pendingInvoiceTagGroups: WorkbenchSettings["pendingInvoiceTagGroups"];
  }) => void;
  onSaveAccessControl: (accounts: WorkbenchAccessAccount[]) => Promise<void>;
  onSearchAccessUsers: (query: string, signal?: AbortSignal) => Promise<WorkbenchAccessUser[]>;
  onDataReset: (payload: {
    action: WorkbenchSettingsDataResetAction;
    oaPassword: string;
    idempotencyKey: string;
    reason: string;
    impactFingerprint: string;
    recoveryReceiptId: string;
    onProgress?: (job: WorkbenchSettingsDataResetJob) => void;
  }) => Promise<WorkbenchSettingsDataResetResult>;
  onLoadDataResetPreview: (
    action: WorkbenchSettingsDataResetAction,
  ) => Promise<WorkbenchSettingsDataResetPreview>;
  onSyncProjects: () => Promise<WorkbenchSettings>;
  onCreateProject: (payload: {
    projectCode: string;
    projectName: string;
  }) => Promise<WorkbenchSettings>;
  onDeleteProject: (projectId: string) => Promise<WorkbenchSettings>;
  onSaveOaApplicantCredential: (payload: SaveOaApplicantCredentialRequest) => Promise<void>;
  onDeleteOaApplicantCredential: (targetApplicantCode: string) => Promise<void>;
};

type SettingsDraftSession = {
  activeSectionId: SettingsSectionId;
  bankNameDraft: string;
  bankShortNameDraft: string;
  last4Draft: string;
  projectCodeDraft: string;
  projectNameDraft: string;
};

type DataResetDialogState =
  | { step: "confirm"; action: WorkbenchSettingsDataResetAction; idempotencyKey: string; preview: WorkbenchSettingsDataResetPreview }
  | { step: "password"; action: WorkbenchSettingsDataResetAction; idempotencyKey: string; preview: WorkbenchSettingsDataResetPreview }
  | null;

const OA_INVOICE_OFFSET_SETTINGS_VISIBLE_USERNAMES = new Set(["YNSYLP005", "YNSYKJ001"]);

function isSettingsDraftSession(value: unknown): value is SettingsDraftSession {
  if (!value || typeof value !== "object") {
    return false;
  }
  const session = value as Record<string, unknown>;
  return (
    typeof session.activeSectionId === "string"
    && typeof session.bankNameDraft === "string"
    && typeof session.bankShortNameDraft === "string"
    && typeof session.last4Draft === "string"
    && typeof session.projectCodeDraft === "string"
    && typeof session.projectNameDraft === "string"
    && (
      session.activeSectionId === "projects"
      || session.activeSectionId === "bank_accounts"
      || session.activeSectionId === "pending_invoice_tags"
      || session.activeSectionId === "oa_retention"
      || session.activeSectionId === "oa_invoice_offset"
      || session.activeSectionId === "oa_applicant_credentials"
      || session.activeSectionId === "access_accounts"
      || session.activeSectionId === "data_reset"
    )
  );
}

const DATA_RESET_ACTIONS: DataResetActionConfig[] = [
  {
    action: "reset_bank_transactions",
    label: "清除所有银行流水数据",
  },
  {
    action: "reset_invoices",
    label: "清除所有发票（进销）数据",
  },
  {
    action: "reset_oa_and_rebuild",
    label: "清除所有 OA 数据并重新写入",
  },
];

function dataResetActionConfig(action: WorkbenchSettingsDataResetAction) {
  return DATA_RESET_ACTIONS.find((item) => item.action === action) ?? DATA_RESET_ACTIONS[0];
}

function toggleCompleted(projectId: string, completedProjectIds: string[]) {
  return completedProjectIds.includes(projectId)
    ? completedProjectIds.filter((id) => id !== projectId)
    : [...completedProjectIds, projectId];
}

function toggleValue(value: string, values: string[]) {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function sortProjects(projects: WorkbenchProjectSetting[]) {
  return [...projects].sort((left, right) => left.projectName.localeCompare(right.projectName, "zh-CN"));
}

function buildManagedAccessAccounts(accessControl: WorkbenchAccessControl | null): ManagedAccessAccount[] {
  return (accessControl?.accounts ?? [])
    .map((account) => ({
      id: `access-${account.username}`,
      username: account.username,
      displayName: account.displayName,
      oaStatus: account.oaStatus,
      pageKeys: account.pageKeys,
    }))
    .sort((left, right) => left.username.localeCompare(right.username, "zh-CN"));
}

function normalizeManagedAccounts(accounts: ManagedAccessAccount[]) {
  const deduped = new Map<string, ManagedAccessAccount>();
  accounts.forEach((account, index) => {
    const username = account.username.trim();
    if (!username) {
      return;
    }
    deduped.set(username, {
      id: account.id || `access-${index}`,
      username,
      displayName: account.displayName,
      oaStatus: account.oaStatus,
      pageKeys: [...new Set(account.pageKeys)].sort(),
    });
  });
  return Array.from(deduped.values()).sort((left, right) => left.username.localeCompare(right.username, "zh-CN"));
}

function parseApplicantNames(value: string) {
  const seen = new Set<string>();
  const names: string[] = [];
  value
    .split(/[,\n;，；、]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .forEach((name) => {
      if (seen.has(name)) {
        return;
      }
      seen.add(name);
      names.push(name);
    });
  return names;
}

function pendingInvoiceTagGroupIssue(
  bankTransactionTags: WorkbenchSettings["bankTransactionTags"],
  pendingInvoiceTagGroups: WorkbenchSettings["pendingInvoiceTagGroups"],
) {
  const tagsByCode = new Map(bankTransactionTags.tags.map((tag) => [tag.code, tag]));
  for (const codes of Object.values(pendingInvoiceTagGroups)) {
    for (const code of codes) {
      const tag = tagsByCode.get(code);
      if (!tag) {
        return "待找发票筛选引用了不存在的银行明细标签，请移除后再保存。";
      }
      if (tag.status === "archived") {
        return "待找发票筛选引用了已停用的银行明细标签，请先从待找发票筛选中移除。";
      }
    }
  }
  return null;
}

function parseResetErrorMessage(message: string) {
  try {
    const payload = JSON.parse(message) as { message?: unknown };
    if (typeof payload.message === "string" && payload.message.trim()) {
      return payload.message;
    }
  } catch {
    // The API helper throws raw text for non-JSON failures.
  }
  return message || "数据重置失败，请稍后重试。";
}

export default function SettingsPageContent({
  activeDataResetJob,
  settings,
  accessControl,
  accessControlStatus,
  isSaving,
  isAccessControlLoading,
  isAccessControlSaving,
  isOaApplicantCredentialLoading,
  isOaApplicantCredentialSaving,
  oaApplicantCredentials,
  canSave,
  canManageAccessControl,
  onCreateProject,
  onDataReset,
  onLoadDataResetPreview,
  onDeleteProject,
  onDeleteOaApplicantCredential,
  onSave,
  onSaveAccessControl,
  onSearchAccessUsers,
  onSaveOaApplicantCredential,
  onSyncProjects,
}: SettingsPageContentProps) {
  const session = useSession();
  const draftSession = usePageSessionState<SettingsDraftSession>({
    pageKey: "settings",
    stateKey: "safeDraft",
    version: 2,
    initialValue: {
      activeSectionId: "projects",
      bankNameDraft: "",
      bankShortNameDraft: "",
      last4Draft: "",
      projectCodeDraft: "",
      projectNameDraft: "",
    },
    ttlMs: 2 * 60 * 60 * 1000,
    storage: "session",
    validate: isSettingsDraftSession,
  });
  const setDraftField = <Key extends keyof SettingsDraftSession>(
    key: Key,
    value: SettingsDraftSession[Key],
  ) => {
    draftSession.setValue((current) => ({ ...current, [key]: value }));
  };
  const [completedProjectIds, setCompletedProjectIds] = useState<string[]>(settings.projects.completedProjectIds);
  const [mappings, setMappings] = useState<BankAccountMapping[]>(settings.bankAccountMappings);
  const [managedAccessAccounts, setManagedAccessAccounts] = useState<ManagedAccessAccount[]>(
    buildManagedAccessAccounts(accessControl),
  );
  const [oaRetentionCutoffDate, setOaRetentionCutoffDate] = useState(settings.oaRetention.cutoffDate);
  const [oaImportFormTypes, setOaImportFormTypes] = useState(settings.oaImport.formTypes);
  const [oaImportStatuses, setOaImportStatuses] = useState(settings.oaImport.statuses);
  const [oaAttachmentInvoicePromotionMode, setOaAttachmentInvoicePromotionMode] = useState(
    settings.oaImport.attachmentInvoicePromotionMode,
  );
  const [oaInvoiceOffsetApplicantsText, setOaInvoiceOffsetApplicantsText] = useState(
    settings.oaInvoiceOffset.applicantNames.join("、"),
  );
  const [pendingInvoiceTagGroups, setPendingInvoiceTagGroups] = useState(settings.pendingInvoiceTagGroups);
  const [activePendingInvoiceGroup, setActivePendingInvoiceGroup] = useState<keyof WorkbenchSettings["pendingInvoiceTagGroups"]>("requiresInvoice");
  const bankNameDraft = draftSession.value.bankNameDraft;
  const setBankNameDraft = (value: string) => setDraftField("bankNameDraft", value);
  const bankShortNameDraft = draftSession.value.bankShortNameDraft;
  const setBankShortNameDraft = (value: string) => setDraftField("bankShortNameDraft", value);
  const last4Draft = draftSession.value.last4Draft;
  const setLast4Draft = (value: string) => setDraftField("last4Draft", value);
  const projectCodeDraft = draftSession.value.projectCodeDraft;
  const setProjectCodeDraft = (value: string) => setDraftField("projectCodeDraft", value);
  const projectNameDraft = draftSession.value.projectNameDraft;
  const setProjectNameDraft = (value: string) => setDraftField("projectNameDraft", value);
  const [projectActionStatus, setProjectActionStatus] = useState<ProjectActionStatus | null>(null);
  const [isProjectActionBusy, setIsProjectActionBusy] = useState(false);
  const [oaApplicantCredentialStatus, setOaApplicantCredentialStatus] = useState<ProjectActionStatus | null>(null);
  const [oaApplicantNameDraft, setOaApplicantNameDraft] = useState("");
  const [oaApplicantCodeDraft, setOaApplicantCodeDraft] = useState("");
  const [oaApplicantUsernameDraft, setOaApplicantUsernameDraft] = useState("");
  const [oaApplicantPasswordDraft, setOaApplicantPasswordDraft] = useState("");
  const activeSectionId = draftSession.value.activeSectionId;
  const setActiveSectionId = (value: SettingsSectionId) => setDraftField("activeSectionId", value);
  const [dataResetDialog, setDataResetDialog] = useState<DataResetDialogState>(null);
  const [dataResetPassword, setDataResetPassword] = useState("");
  const [dataResetReason, setDataResetReason] = useState("");
  const [settingsActionStatus, setSettingsActionStatus] = useState<DataResetStatus | null>(null);
  const [dataResetStatus, setDataResetStatus] = useState<DataResetStatus | null>(null);
  const [dataResetProgress, setDataResetProgress] = useState<WorkbenchSettingsDataResetJob | null>(null);
  const [isDataResetting, setIsDataResetting] = useState(false);

  const controlsDisabled = !canSave || isSaving || isDataResetting || isProjectActionBusy;
  const accessControlControlsDisabled = !canSave
    || isAccessControlLoading
    || isAccessControlSaving
    || accessControl === null;

  const activeProjects = useMemo(
    () => sortProjects(settings.projects.active.filter((project) => !completedProjectIds.includes(project.id))),
    [completedProjectIds, settings.projects.active],
  );
  const completedProjects = useMemo(
    () =>
      sortProjects([
        ...settings.projects.completed,
        ...settings.projects.active.filter((project) => completedProjectIds.includes(project.id)),
      ]).filter((project, index, rows) => rows.findIndex((row) => row.id === project.id) === index),
    [completedProjectIds, settings.projects.active, settings.projects.completed],
  );

  useEffect(() => {
    setManagedAccessAccounts(buildManagedAccessAccounts(accessControl));
  }, [accessControl]);

  useEffect(() => {
    const isTerminal =
      activeDataResetJob === null ||
      ["completed", "failed", "error", "cancelled", "canceled"].includes(activeDataResetJob.status);
    if (!isTerminal && activeDataResetJob !== null) {
      setDataResetStatus(null);
      setDataResetProgress(activeDataResetJob);
      setIsDataResetting(true);
      return;
    }
    if (activeDataResetJob === null && dataResetProgress !== null && isDataResetting) {
      setDataResetProgress(null);
      setIsDataResetting(false);
    }
  }, [activeDataResetJob, dataResetProgress, isDataResetting]);

  const canAddMapping =
    last4Draft.trim().length === 4 && /^\d{4}$/.test(last4Draft.trim()) && bankNameDraft.trim().length > 0;
  const canAddProject = projectCodeDraft.trim().length > 0 && projectNameDraft.trim().length > 0;
  const normalizedAccessAccounts = managedAccessAccounts.map((account) => ({
    username: account.username.trim(),
    displayName: account.displayName,
    oaStatus: account.oaStatus,
    pageKeys: account.pageKeys,
  }));
  const normalizedAccessUsernames = normalizedAccessAccounts.map((account) => account.username);
  const accessControlValidationMessage = normalizedAccessUsernames.some((username) => !username)
    ? "访问账户不能为空。"
    : new Set(normalizedAccessUsernames).size !== normalizedAccessUsernames.length
      ? "访问账户不能重复。"
      : normalizedAccessUsernames.includes(accessControl?.administrator.username ?? "")
        ? "受保护管理员不能作为普通访问账户编辑。"
        : normalizedAccessAccounts.some((account) => account.pageKeys.length === 0)
          ? "每个访问账户至少需要选择一个页面。"
          : null;
  const canSaveOaApplicantCredential =
    oaApplicantNameDraft.trim().length > 0
    && oaApplicantCodeDraft.trim().length > 0
    && oaApplicantUsernameDraft.trim().length > 0
    && oaApplicantPasswordDraft.length > 0;
  const currentSessionUser =
    session.status === "authenticated" || session.status === "forbidden" ? session.session.user : null;
  const canManageOaInvoiceOffset =
    currentSessionUser !== null && OA_INVOICE_OFFSET_SETTINGS_VISIBLE_USERNAMES.has(currentSessionUser.username);
  const settingsNavigationItems = useMemo<SettingsNavigationItem[]>(() => {
    const items = [
      {
        id: "projects" as const,
        label: "项目状态",
        visible: true,
      },
      {
        id: "bank_accounts" as const,
        label: "银行账户",
        visible: true,
      },
      {
        id: "pending_invoice_tags" as const,
        label: "待找发票筛选",
        visible: true,
      },
      {
        id: "oa_retention" as const,
        label: "OA导入设置",
        visible: true,
      },
      {
        id: "oa_invoice_offset" as const,
        label: "冲账规则",
        visible: canManageOaInvoiceOffset,
      },
      {
        id: "oa_applicant_credentials" as const,
        label: "OA申请人凭据",
        visible: canManageAccessControl,
      },
      {
        id: "access_accounts" as const,
        label: "访问账户",
        visible: canManageAccessControl,
      },
      {
        id: "data_reset" as const,
        label: "数据重置",
        visible: canManageAccessControl,
      },
    ];
    return items.filter((item) => item.visible).map(({ visible: _visible, ...item }) => item);
  }, [
    canManageOaInvoiceOffset,
    canManageAccessControl,
  ]);

  useEffect(() => {
    if (!settingsNavigationItems.some((item) => item.id === activeSectionId)) {
      setActiveSectionId(settingsNavigationItems[0]?.id ?? "projects");
    }
  }, [activeSectionId, settingsNavigationItems]);

  function handleAddMapping() {
    if (!canAddMapping || controlsDisabled) {
      return;
    }
    const nextLast4 = last4Draft.trim();
    if (mappings.some((item) => item.last4 === nextLast4)) {
      setMappings((current) =>
        current.map((item) =>
          item.last4 === nextLast4
            ? { ...item, bankName: bankNameDraft.trim(), shortName: bankShortNameDraft.trim() }
            : item,
        ),
      );
    } else {
      setMappings((current) => [
        ...current,
        {
          id: `bank_mapping_${nextLast4}`,
          last4: nextLast4,
          bankName: bankNameDraft.trim(),
          shortName: bankShortNameDraft.trim(),
        },
      ]);
    }
    setLast4Draft("");
    setBankNameDraft("");
    setBankShortNameDraft("");
  }

  function applyProjectSettings(nextSettings: WorkbenchSettings, message: string) {
    setCompletedProjectIds(nextSettings.projects.completedProjectIds);
    setProjectActionStatus({ tone: "success", message });
  }

  function projectActionErrorMessage(error: unknown) {
    if (error instanceof Error && error.message.trim()) {
      try {
        const payload = JSON.parse(error.message) as { message?: string };
        return payload.message || error.message;
      } catch {
        return error.message;
      }
    }
    return "项目状态更新失败，请稍后重试。";
  }

  async function handleSyncProjects() {
    if (controlsDisabled) {
      return;
    }
    setProjectActionStatus(null);
    setIsProjectActionBusy(true);
    try {
      const nextSettings = await onSyncProjects();
      applyProjectSettings(nextSettings, "已从 OA 拉取项目。");
    } catch (error) {
      setProjectActionStatus({ tone: "error", message: projectActionErrorMessage(error) });
    } finally {
      setIsProjectActionBusy(false);
    }
  }

  async function handleAddProject() {
    if (!canAddProject || controlsDisabled) {
      return;
    }
    setProjectActionStatus(null);
    setIsProjectActionBusy(true);
    try {
      const nextSettings = await onCreateProject({
        projectCode: projectCodeDraft.trim(),
        projectName: projectNameDraft.trim(),
      });
      setProjectCodeDraft("");
      setProjectNameDraft("");
      applyProjectSettings(nextSettings, "已新增本地项目。");
    } catch (error) {
      setProjectActionStatus({ tone: "error", message: projectActionErrorMessage(error) });
    } finally {
      setIsProjectActionBusy(false);
    }
  }

  async function handleDeleteProject(project: WorkbenchProjectSetting) {
    if (controlsDisabled) {
      return;
    }
    const confirmed = window.confirm(`确认删除“${project.projectName}”？`);
    if (!confirmed) {
      return;
    }
    setProjectActionStatus(null);
    setIsProjectActionBusy(true);
    try {
      const nextSettings = await onDeleteProject(project.id);
      applyProjectSettings(nextSettings, "已删除本地项目或状态覆盖。");
    } catch (error) {
      setProjectActionStatus({ tone: "error", message: projectActionErrorMessage(error) });
    } finally {
      setIsProjectActionBusy(false);
    }
  }

  function handleAddAccessAccount(user: WorkbenchAccessUser) {
    const nextUsername = user.username.trim();
    if (!nextUsername || controlsDisabled || nextUsername === accessControl?.administrator.username) {
      return;
    }
    setManagedAccessAccounts((current) => {
      const existingIndex = current.findIndex((item) => item.username === nextUsername);
      if (existingIndex >= 0) {
        return current;
      }
      return normalizeManagedAccounts([
        ...current,
        {
          id: `access-${nextUsername}`,
          username: nextUsername,
          displayName: user.displayName,
          oaStatus: user.active ? "active" : "inactive",
          pageKeys: [],
        },
      ]);
    });
  }

  function handleSelectOaApplicantCredential(credential: OaApplicantCredentialSummary) {
    setOaApplicantCredentialStatus(null);
    setOaApplicantNameDraft(credential.targetApplicantName);
    setOaApplicantCodeDraft(credential.targetApplicantCode);
    setOaApplicantUsernameDraft(credential.oaUsername);
    setOaApplicantPasswordDraft("");
  }

  async function handleSaveOaApplicantCredential(payload: SaveOaApplicantCredentialRequest) {
    if (!canSaveOaApplicantCredential || controlsDisabled || isOaApplicantCredentialSaving) {
      return;
    }
    setOaApplicantCredentialStatus(null);
    try {
      await onSaveOaApplicantCredential(payload);
      setOaApplicantPasswordDraft("");
      setOaApplicantCredentialStatus({ tone: "success", message: "已保存 OA 申请人凭据。" });
    } catch (error) {
      setOaApplicantCredentialStatus({
        tone: "error",
        message: error instanceof Error ? parseResetErrorMessage(error.message) : "OA 申请人凭据保存失败，请稍后重试。",
      });
    }
  }

  async function handleClearOaApplicantCredential(targetApplicantCode: string) {
    if (controlsDisabled || isOaApplicantCredentialSaving || !targetApplicantCode.trim()) {
      return;
    }
    setOaApplicantCredentialStatus(null);
    try {
      await onDeleteOaApplicantCredential(targetApplicantCode);
      setOaApplicantPasswordDraft("");
      setOaApplicantCredentialStatus({ tone: "success", message: "已清空 OA 申请人密码。" });
    } catch (error) {
      setOaApplicantCredentialStatus({
        tone: "error",
        message: error instanceof Error ? parseResetErrorMessage(error.message) : "OA 申请人凭据更新失败，请稍后重试。",
      });
    }
  }

  function addTagToPendingInvoiceGroup(code: string) {
    setPendingInvoiceTagGroups((current) => {
      const withoutCode = {
        requiresInvoice: current.requiresInvoice.filter((item) => item !== code),
        bankStatementAsInvoice: current.bankStatementAsInvoice.filter((item) => item !== code),
        noInvoiceRequired: current.noInvoiceRequired.filter((item) => item !== code),
      };
      return {
        ...withoutCode,
        [activePendingInvoiceGroup]: [...withoutCode[activePendingInvoiceGroup], code],
      };
    });
  }

  function handleSave() {
    setSettingsActionStatus(null);
    const pendingInvoiceIssue = pendingInvoiceTagGroupIssue(settings.bankTransactionTags, pendingInvoiceTagGroups);
    if (pendingInvoiceIssue) {
      setSettingsActionStatus({ tone: "error", message: pendingInvoiceIssue });
      return;
    }
    onSave({
      completedProjectIds,
      bankAccountMappings: mappings,
      workbenchColumnLayouts: settings.workbenchColumnLayouts,
      oaRetention: {
        cutoffDate: oaRetentionCutoffDate || "2026-01-01",
      },
      oaImport: {
        ...settings.oaImport,
        formTypes: oaImportFormTypes,
        statuses: oaImportStatuses,
        attachmentInvoicePromotionMode: oaAttachmentInvoicePromotionMode,
      },
      oaInvoiceOffset: {
        applicantNames: parseApplicantNames(oaInvoiceOffsetApplicantsText),
      },
      bankTransactionTags: settings.bankTransactionTags,
      pendingInvoiceTagGroups,
    });
  }

  async function handleSaveAccessControl() {
    if (accessControlControlsDisabled || accessControlValidationMessage) {
      return;
    }
    await onSaveAccessControl(normalizedAccessAccounts);
  }

  async function handleOpenDataResetConfirm(action: WorkbenchSettingsDataResetAction) {
    if (controlsDisabled) {
      return;
    }
    setDataResetStatus(null);
    try {
      const preview = await onLoadDataResetPreview(action);
      setDataResetReason("");
      setDataResetDialog({ step: "confirm", action, idempotencyKey: crypto.randomUUID(), preview });
    } catch (error) {
      setDataResetStatus({
        tone: "error",
        message: error instanceof Error ? parseResetErrorMessage(error.message) : "无法读取数据重置范围。",
      });
    }
  }

  function handleContinueDataReset() {
    if (!dataResetDialog) {
      return;
    }
    setDataResetPassword("");
    setDataResetDialog({
      step: "password",
      action: dataResetDialog.action,
      idempotencyKey: dataResetDialog.idempotencyKey,
      preview: dataResetDialog.preview,
    });
  }

  async function handleConfirmDataReset() {
    if (!dataResetDialog || isDataResetting || !dataResetPassword || dataResetReason.trim().length < 5) {
      return;
    }
    setIsDataResetting(true);
    setDataResetStatus(null);
    setDataResetProgress(null);
    try {
      const result = await onDataReset({
        action: dataResetDialog.action,
        oaPassword: dataResetPassword,
        idempotencyKey: dataResetDialog.idempotencyKey,
        reason: dataResetReason.trim(),
        impactFingerprint: dataResetDialog.preview.impactFingerprint,
        recoveryReceiptId: dataResetDialog.preview.recoveryReceiptId ?? "",
        onProgress: (job) => {
          setDataResetPassword("");
          setDataResetDialog(null);
          setDataResetProgress(job);
        },
      });
      setDataResetPassword("");
      setDataResetDialog(null);
      setDataResetProgress(null);
      setDataResetStatus({
        tone: "success",
        message: result.message || "数据重置已完成。",
      });
    } catch (error) {
      setDataResetPassword("");
      setDataResetProgress(null);
      setDataResetStatus({
        tone: "error",
        message: error instanceof Error ? parseResetErrorMessage(error.message) : "数据重置失败，请稍后重试。",
      });
    } finally {
      setIsDataResetting(false);
    }
  }

  function handleCancelDataResetDialog() {
    if (isDataResetting) {
      return;
    }
    setDataResetPassword("");
    setDataResetReason("");
    setDataResetDialog(null);
  }

  return (
    <div className="settings-layout">
        <nav className="settings-nav-shell">
          <SettingsTreeNav
            items={settingsNavigationItems}
            activeSectionId={activeSectionId}
            onSelect={setActiveSectionId}
          />
        </nav>

        <section aria-label="设置内容" className="settings-content-panel">
          <header className="settings-content-header">
            <div className="settings-content-title">
              <h1>设置</h1>
              {settingsActionStatus ? (
                <div
                  className={`settings-inline-alert settings-inline-alert--${settingsActionStatus.tone}`}
                  role={settingsActionStatus.tone === "error" ? "alert" : "status"}
                >
                  {settingsActionStatus.message}
                </div>
              ) : null}
            </div>
            {!["access_accounts", "oa_applicant_credentials", "data_reset"].includes(activeSectionId) ? (
              <div className="settings-save-actions">
                <Button
                  isDisabled={controlsDisabled}
                  isPending={isSaving}
                  variant="primary"
                  onPress={handleSave}
                >
                  {isSaving ? "保存中..." : "保存设置"}
                </Button>
              </div>
            ) : null}
          </header>

            {activeSectionId === "projects" ? (
                <SettingsProjectsSection
                  activeProjects={activeProjects}
                  completedProjects={completedProjects}
                  controlsDisabled={controlsDisabled}
                  projectActionStatus={projectActionStatus}
                  projectCodeDraft={projectCodeDraft}
                  projectNameDraft={projectNameDraft}
                  onChangeProjectCodeDraft={setProjectCodeDraft}
                  onChangeProjectNameDraft={setProjectNameDraft}
                  onSyncProjects={handleSyncProjects}
                  onAddProject={handleAddProject}
                  onToggleCompleted={(projectId) => setCompletedProjectIds((current) => toggleCompleted(projectId, current))}
                  onDeleteProject={handleDeleteProject}
                  isProjectActionBusy={isProjectActionBusy}
                  canAddProject={canAddProject}
                />
              ) : null}

              {activeSectionId === "bank_accounts" ? (
                <SettingsBankAccountsSection
                  controlsDisabled={controlsDisabled}
                  mappings={mappings}
                  bankNameDraft={bankNameDraft}
                  bankShortNameDraft={bankShortNameDraft}
                  last4Draft={last4Draft}
                  canAddMapping={canAddMapping}
                  onChangeBankNameDraft={setBankNameDraft}
                  onChangeBankShortNameDraft={setBankShortNameDraft}
                  onChangeLast4Draft={setLast4Draft}
                  onAddMapping={handleAddMapping}
                  onUpdateMapping={(mappingId, updater) =>
                    setMappings((current) => current.map((item) => (item.id === mappingId ? updater(item) : item)))
                  }
                  onDeleteMapping={(mappingId) =>
                    setMappings((current) => current.filter((item) => item.id !== mappingId))
                  }
                />
              ) : null}

              {activeSectionId === "pending_invoice_tags" ? (
                <SettingsPendingInvoiceTagsSection
                  controlsDisabled={controlsDisabled}
                  tags={settings.bankTransactionTags.tags}
                  groups={pendingInvoiceTagGroups}
                  activeGroup={activePendingInvoiceGroup}
                  onSelectGroup={setActivePendingInvoiceGroup}
                  onAddExistingTag={addTagToPendingInvoiceGroup}
                  onRemoveTag={(code) =>
                    setPendingInvoiceTagGroups((current) => ({
                      ...current,
                      [activePendingInvoiceGroup]: current[activePendingInvoiceGroup].filter((item) => item !== code),
                    }))
                  }
                />
              ) : null}

              {activeSectionId === "oa_retention" ? (
                <SettingsOaRetentionSection
                  controlsDisabled={controlsDisabled}
                  cutoffDate={oaRetentionCutoffDate}
                  oaImport={{
                    ...settings.oaImport,
                    formTypes: oaImportFormTypes,
                    statuses: oaImportStatuses,
                    attachmentInvoicePromotionMode: oaAttachmentInvoicePromotionMode,
                  }}
                  onChangeCutoffDate={setOaRetentionCutoffDate}
                  onChangeAttachmentInvoicePromotionMode={setOaAttachmentInvoicePromotionMode}
                  onToggleFormType={(value) => setOaImportFormTypes((current) => toggleValue(value, current))}
                  onToggleStatus={(value) => setOaImportStatuses((current) => toggleValue(value, current))}
                />
              ) : null}

              {activeSectionId === "oa_invoice_offset" && canManageOaInvoiceOffset ? (
                <SettingsOaInvoiceOffsetSection
                  controlsDisabled={controlsDisabled}
                  applicantsText={oaInvoiceOffsetApplicantsText}
                  onChangeApplicantsText={setOaInvoiceOffsetApplicantsText}
                />
              ) : null}

              {activeSectionId === "oa_applicant_credentials" && canManageAccessControl ? (
                <SettingsOaApplicantCredentialsSection
                  controlsDisabled={controlsDisabled}
                  credentials={oaApplicantCredentials}
                  isLoading={isOaApplicantCredentialLoading}
                  isSaving={isOaApplicantCredentialSaving}
                  status={oaApplicantCredentialStatus}
                  targetApplicantNameDraft={oaApplicantNameDraft}
                  targetApplicantCodeDraft={oaApplicantCodeDraft}
                  oaUsernameDraft={oaApplicantUsernameDraft}
                  oaPasswordDraft={oaApplicantPasswordDraft}
                  canSaveCredential={canSaveOaApplicantCredential}
                  onChangeTargetApplicantNameDraft={setOaApplicantNameDraft}
                  onChangeTargetApplicantCodeDraft={setOaApplicantCodeDraft}
                  onChangeOaUsernameDraft={setOaApplicantUsernameDraft}
                  onChangeOaPasswordDraft={setOaApplicantPasswordDraft}
                  onSelectCredential={handleSelectOaApplicantCredential}
                  onSaveCredential={handleSaveOaApplicantCredential}
                  onClearCredential={handleClearOaApplicantCredential}
                />
              ) : null}

              {activeSectionId === "access_accounts" && canManageAccessControl ? (
                <SettingsAccessAccountsSection
                  controlsDisabled={accessControlControlsDisabled}
                  administrator={accessControl?.administrator ?? null}
                  managedAccessAccounts={managedAccessAccounts}
                  isLoading={isAccessControlLoading}
                  isSaving={isAccessControlSaving}
                  status={accessControlStatus}
                  validationMessage={accessControlValidationMessage}
                  onAddAccessAccount={handleAddAccessAccount}
                  onSearchAccessUsers={onSearchAccessUsers}
                  onUpdateManagedAccessAccount={(accountId, updater) =>
                    setManagedAccessAccounts((current) => current.map((item) => (item.id === accountId ? updater(item) : item)))
                  }
                  onDeleteManagedAccessAccount={(accountId) =>
                    setManagedAccessAccounts((current) => current.filter((item) => item.id !== accountId))
                  }
                  onSave={handleSaveAccessControl}
                />
              ) : null}

              {activeSectionId === "data_reset" && canManageAccessControl ? (
                <SettingsDataResetSection
                  controlsDisabled={controlsDisabled}
                  dataResetStatus={dataResetStatus}
                  dataResetProgress={dataResetProgress}
                  actions={DATA_RESET_ACTIONS}
                  onOpenDataResetConfirm={handleOpenDataResetConfirm}
                />
              ) : null}
        </section>
      {dataResetDialog ? (
        <SettingsDataResetDialogs
          config={dataResetActionConfig(dataResetDialog.action)}
          isBusy={isDataResetting}
          password={dataResetPassword}
          preview={dataResetDialog.preview}
          reason={dataResetReason}
          step={dataResetDialog.step}
          onCancel={handleCancelDataResetDialog}
          onContinue={handleContinueDataReset}
          onPasswordChange={setDataResetPassword}
          onReasonChange={setDataResetReason}
          onSubmit={handleConfirmDataReset}
        />
      ) : null}
    </div>
  );
}
