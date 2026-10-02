import { Button } from "@heroui/react";
import { useEffect, useMemo, useState } from "react";

import { usePageSessionState } from "../../contexts/PageSessionStateContext";
import type {
  BankAccountMapping,
  OaApplicantCredentialSummary,
  SaveOaApplicantCredentialRequest,
  WorkbenchAccessAccount,
  WorkbenchAccessControl,
  WorkbenchAccessUser,
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
import SettingsOaRetentionSection from "./SettingsOaRetentionSection";
import SettingsTabs from "./SettingsTabs";
import type {
  DataResetActionConfig,
  DataResetStatus,
  ManagedAccessAccount,
  SettingsActionStatus,
  SettingsNavigationItem,
  SettingsSectionId,
} from "./types";

type SettingsPageContentProps = {
  settings: WorkbenchSettings;
  accessControl: WorkbenchAccessControl | null;
  accessControlStatus: SettingsActionStatus | null;
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
    bankAccountMappings: BankAccountMapping[];
    workbenchColumnLayouts: WorkbenchSettings["workbenchColumnLayouts"];
    oaRetention: WorkbenchSettings["oaRetention"];
    oaImport: WorkbenchSettings["oaImport"];
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
  onSaveOaApplicantCredential: (payload: SaveOaApplicantCredentialRequest) => Promise<void>;
  onDeleteOaApplicantCredential: (targetApplicantCode: string) => Promise<void>;
};

type SettingsDraftSession = {
  activeSectionId: SettingsSectionId;
  bankNameDraft: string;
  bankShortNameDraft: string;
  last4Draft: string;
};

type DataResetDialogState =
  | { step: "confirm"; action: WorkbenchSettingsDataResetAction; idempotencyKey: string; preview: WorkbenchSettingsDataResetPreview }
  | { step: "password"; action: WorkbenchSettingsDataResetAction; idempotencyKey: string; preview: WorkbenchSettingsDataResetPreview }
  | null;


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
    && (
      session.activeSectionId === "bank_accounts"
      || session.activeSectionId === "oa_retention"
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

function toggleValue(value: string, values: string[]) {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
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
  onDataReset,
  onLoadDataResetPreview,
  onDeleteOaApplicantCredential,
  onSave,
  onSaveAccessControl,
  onSearchAccessUsers,
  onSaveOaApplicantCredential,
}: SettingsPageContentProps) {
  const draftSession = usePageSessionState<SettingsDraftSession>({
    pageKey: "settings",
    stateKey: "safeDraft",
    version: 2,
    initialValue: {
      activeSectionId: "bank_accounts",
      bankNameDraft: "",
      bankShortNameDraft: "",
      last4Draft: "",
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
  const bankNameDraft = draftSession.value.bankNameDraft;
  const setBankNameDraft = (value: string) => setDraftField("bankNameDraft", value);
  const bankShortNameDraft = draftSession.value.bankShortNameDraft;
  const setBankShortNameDraft = (value: string) => setDraftField("bankShortNameDraft", value);
  const last4Draft = draftSession.value.last4Draft;
  const setLast4Draft = (value: string) => setDraftField("last4Draft", value);
  const [oaApplicantCredentialStatus, setOaApplicantCredentialStatus] = useState<SettingsActionStatus | null>(null);
  const [oaApplicantNameDraft, setOaApplicantNameDraft] = useState("");
  const [oaApplicantCodeDraft, setOaApplicantCodeDraft] = useState("");
  const [oaApplicantUsernameDraft, setOaApplicantUsernameDraft] = useState("");
  const [oaApplicantPasswordDraft, setOaApplicantPasswordDraft] = useState("");
  const activeSectionId = draftSession.value.activeSectionId;
  const setActiveSectionId = (value: SettingsSectionId) => setDraftField("activeSectionId", value);
  const [dataResetDialog, setDataResetDialog] = useState<DataResetDialogState>(null);
  const [dataResetPassword, setDataResetPassword] = useState("");
  const [dataResetReason, setDataResetReason] = useState("");
  const [dataResetStatus, setDataResetStatus] = useState<DataResetStatus | null>(null);
  const [dataResetProgress, setDataResetProgress] = useState<WorkbenchSettingsDataResetJob | null>(null);
  const [isDataResetting, setIsDataResetting] = useState(false);

  const controlsDisabled = !canSave || isSaving || isDataResetting;
  const hasUnsavedSettings = useMemo(() => {
    const sameValues = (left: string[], right: string[]) => JSON.stringify([...left].sort()) === JSON.stringify([...right].sort());
    return JSON.stringify(mappings) !== JSON.stringify(settings.bankAccountMappings)
      || oaRetentionCutoffDate !== settings.oaRetention.cutoffDate
      || !sameValues(oaImportFormTypes, settings.oaImport.formTypes)
      || !sameValues(oaImportStatuses, settings.oaImport.statuses)
      || oaAttachmentInvoicePromotionMode !== settings.oaImport.attachmentInvoicePromotionMode;
  }, [mappings, oaRetentionCutoffDate, oaImportFormTypes, oaImportStatuses,
    oaAttachmentInvoicePromotionMode, settings]);
  const accessControlControlsDisabled = !canSave
    || isAccessControlLoading
    || isAccessControlSaving
    || accessControl === null;

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
  const settingsNavigationItems = useMemo<SettingsNavigationItem[]>(() => {
    const items = [
      {
        id: "bank_accounts" as const,
        label: "银行账户",
        visible: true,
      },
      {
        id: "oa_retention" as const,
        label: "OA导入设置",
        visible: true,
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
    canManageAccessControl,
  ]);

  useEffect(() => {
    if (!settingsNavigationItems.some((item) => item.id === activeSectionId)) {
      setActiveSectionId(settingsNavigationItems[0]?.id ?? "bank_accounts");
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

  function handleSave() {
    onSave({
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
      <div className="settings-workspace">
          <header className="settings-content-header">
            <div className="settings-content-title">
              <h1>设置</h1>
            </div>
            {!["access_accounts", "oa_applicant_credentials", "data_reset"].includes(activeSectionId) ? (
              <div className="settings-save-actions">
                {hasUnsavedSettings ? <span className="settings-draft-status" role="status">有未保存修改</span> : null}
                <Button
                  isDisabled={controlsDisabled}
                  isPending={isSaving}
                  variant="primary"
                  onPress={handleSave}
                >
                  {isSaving ? "保存中..." : "保存全部设置"}
                </Button>
              </div>
            ) : null}
          </header>
          <SettingsTabs items={settingsNavigationItems} activeSectionId={activeSectionId} onSelect={setActiveSectionId}>
            <section aria-label="设置内容" className="settings-content-panel">

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
                  savedAccounts={buildManagedAccessAccounts(accessControl)}
                  onReset={() => setManagedAccessAccounts(buildManagedAccessAccounts(accessControl))}
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
          </SettingsTabs>
      </div>
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
