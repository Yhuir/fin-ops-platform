import { useMemo, useState } from "react";

import SettingsAccessAccountsSection from "../settings/SettingsAccessAccountsSection";
import SettingsBankAccountsSection from "../settings/SettingsBankAccountsSection";
import SettingsDataResetSection from "../settings/SettingsDataResetSection";
import SettingsOaInvoiceOffsetSection from "../settings/SettingsOaInvoiceOffsetSection";
import SettingsOaRetentionSection from "../settings/SettingsOaRetentionSection";
import SettingsProjectsSection from "../settings/SettingsProjectsSection";
import SettingsTreeNav from "../settings/SettingsTreeNav";
import type {
  DataResetActionConfig,
  DataResetStatus,
  ManagedAccessAccount,
  ProjectActionStatus,
  SettingsNavigationItem,
  SettingsSectionId,
} from "../settings/types";
import { useSession } from "../../contexts/SessionContext";
import type {
  BankAccountMapping,
  WorkbenchAccessRole,
  WorkbenchProjectSetting,
  WorkbenchSettings,
  WorkbenchSettingsDataResetAction,
  WorkbenchSettingsDataResetResult,
} from "../../features/workbench/types";

type WorkbenchSettingsModalProps = {
  settings: WorkbenchSettings;
  isSaving: boolean;
  canSave: boolean;
  canManageAccessControl: boolean;
  onSave: (payload: {
    completedProjectIds: string[];
    bankAccountMappings: BankAccountMapping[];
    allowedUsernames: string[];
    readonlyExportUsernames: string[];
    adminUsernames: string[];
    workbenchColumnLayouts: WorkbenchSettings["workbenchColumnLayouts"];
    oaRetention: WorkbenchSettings["oaRetention"];
    oaInvoiceOffset: WorkbenchSettings["oaInvoiceOffset"];
  }) => void;
  onDataReset: (payload: {
    action: WorkbenchSettingsDataResetAction;
    oaPassword: string;
  }) => Promise<WorkbenchSettingsDataResetResult>;
  onSyncProjects: () => Promise<WorkbenchSettings>;
  onCreateProject: (payload: {
    projectCode: string;
    projectName: string;
  }) => Promise<WorkbenchSettings>;
  onDeleteProject: (projectId: string) => Promise<WorkbenchSettings>;
};

type DataResetDialogState =
  | { step: "confirm"; action: WorkbenchSettingsDataResetAction }
  | { step: "password"; action: WorkbenchSettingsDataResetAction }
  | null;

const OA_INVOICE_OFFSET_SETTINGS_VISIBLE_USERNAMES = new Set(["YNSYLP005", "YNSYKJ001"]);

const DATA_RESET_ACTIONS: DataResetActionConfig[] = [
  {
    action: "reset_bank_transactions",
    label: "清除所有银行流水数据",
    title: "清除所有银行流水数据",
    description: "清空已导入银行流水、相关匹配结果、配对状态和工作台缓存，不影响 OA 源库。",
    impact: ["已导入银行流水会被清空", "相关已配对 / 异常 / 忽略状态会被清空", "不会触碰 form_data_db.form_data"],
  },
  {
    action: "reset_invoices",
    label: "清除所有发票（进销）数据",
    title: "清除所有发票（进销）数据",
    description: "清空已导入进项票 / 销项票、税金认证记录、相关匹配结果和工作台缓存。",
    impact: ["已导入发票会被清空", "税金认证导入记录会被清空", "不会触碰 OA 源库"],
  },
  {
    action: "reset_oa_and_rebuild",
    label: "清除所有 OA 数据并重新写入",
    title: "清除所有 OA 数据并重新写入",
    description: "按模式 B 清空 OA 相关 app 侧缓存和人工状态，再按保OA日期重新构建。",
    impact: ["OA 附件发票缓存会被清空", "OA 相关配对 / 异常 / 忽略状态会被清空", "不会删除 OA 原始数据"],
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

function sortProjects(projects: WorkbenchProjectSetting[]) {
  return [...projects].sort((left, right) => left.projectName.localeCompare(right.projectName, "zh-CN"));
}

function buildManagedAccessAccounts(settings: WorkbenchSettings): ManagedAccessAccount[] {
  const readonlySet = new Set(settings.accessControl.readonlyExportUsernames);
  const adminSet = new Set(settings.accessControl.adminUsernames);
  return settings.accessControl.allowedUsernames
    .filter((username) => !adminSet.has(username))
    .map((username) => ({
      id: `access-${username}`,
      username,
      role: (readonlySet.has(username) ? "read_export_only" : "full_access") as WorkbenchAccessRole,
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
      role: account.role,
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

export default function WorkbenchSettingsModal({
  settings,
  isSaving,
  canSave,
  canManageAccessControl,
  onCreateProject,
  onDataReset,
  onDeleteProject,
  onSave,
  onSyncProjects,
}: WorkbenchSettingsModalProps) {
  const session = useSession();
  const [completedProjectIds, setCompletedProjectIds] = useState<string[]>(settings.projects.completedProjectIds);
  const [mappings, setMappings] = useState<BankAccountMapping[]>(settings.bankAccountMappings);
  const [managedAccessAccounts, setManagedAccessAccounts] = useState<ManagedAccessAccount[]>(
    buildManagedAccessAccounts(settings),
  );
  const [oaRetentionCutoffDate, setOaRetentionCutoffDate] = useState(settings.oaRetention.cutoffDate);
  const [oaInvoiceOffsetApplicantsText, setOaInvoiceOffsetApplicantsText] = useState(
    settings.oaInvoiceOffset.applicantNames.join("、"),
  );
  const [bankNameDraft, setBankNameDraft] = useState("");
  const [bankShortNameDraft, setBankShortNameDraft] = useState("");
  const [last4Draft, setLast4Draft] = useState("");
  const [projectCodeDraft, setProjectCodeDraft] = useState("");
  const [projectNameDraft, setProjectNameDraft] = useState("");
  const [projectActionStatus, setProjectActionStatus] = useState<ProjectActionStatus | null>(null);
  const [isProjectActionBusy, setIsProjectActionBusy] = useState(false);
  const [accessUsernameDraft, setAccessUsernameDraft] = useState("");
  const [accessRoleDraft, setAccessRoleDraft] = useState<WorkbenchAccessRole>("full_access");
  const [activeSectionId, setActiveSectionId] = useState<SettingsSectionId>("projects");
  const [dataResetDialog, setDataResetDialog] = useState<DataResetDialogState>(null);
  const [dataResetPassword, setDataResetPassword] = useState("");
  const [dataResetStatus, setDataResetStatus] = useState<DataResetStatus | null>(null);
  const [isDataResetting, setIsDataResetting] = useState(false);

  const controlsDisabled = !canSave || isSaving || isDataResetting || isProjectActionBusy;
  const adminUsernames = settings.accessControl.adminUsernames;

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

  const canAddMapping =
    last4Draft.trim().length === 4 && /^\d{4}$/.test(last4Draft.trim()) && bankNameDraft.trim().length > 0;
  const canAddProject = projectCodeDraft.trim().length > 0 && projectNameDraft.trim().length > 0;
  const canAddAccessAccount = accessUsernameDraft.trim().length > 0;
  const currentSessionUser =
    session.status === "authenticated" || session.status === "forbidden" ? session.session.user : null;
  const canManageOaInvoiceOffset =
    currentSessionUser !== null && OA_INVOICE_OFFSET_SETTINGS_VISIBLE_USERNAMES.has(currentSessionUser.username);
  const settingsNavigationItems = useMemo<SettingsNavigationItem[]>(() => {
    const items = [
      {
        id: "projects" as const,
        label: "项目状态",
        description: "进行中 / 已完成",
        count: activeProjects.length + completedProjects.length,
        visible: true,
      },
      {
        id: "bank_accounts" as const,
        label: "银行账户",
        description: "银行名称与尾号",
        count: mappings.length,
        visible: true,
      },
      {
        id: "oa_retention" as const,
        label: "保OA",
        description: "按日期保留关联 OA",
        count: 1,
        visible: true,
      },
      {
        id: "oa_invoice_offset" as const,
        label: "冲账规则",
        description: "按 OA 申请人自动配发票",
        count: parseApplicantNames(oaInvoiceOffsetApplicantsText).length,
        visible: canManageOaInvoiceOffset,
      },
      {
        id: "access_accounts" as const,
        label: "访问账户",
        description: "可访问账号权限",
        count: managedAccessAccounts.length + adminUsernames.length,
        visible: canManageAccessControl,
      },
      {
        id: "data_reset" as const,
        label: "数据重置",
        description: "高风险清理工具",
        count: DATA_RESET_ACTIONS.length,
        visible: canManageAccessControl,
      },
    ];
    return items.filter((item) => item.visible).map(({ visible: _visible, ...item }) => item);
  }, [
    activeProjects.length,
    completedProjects.length,
    mappings.length,
    oaInvoiceOffsetApplicantsText,
    canManageOaInvoiceOffset,
    managedAccessAccounts.length,
    adminUsernames.length,
    canManageAccessControl,
  ]);

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
    const confirmed = window.confirm(
      "删除只会移除 app 本地项目或本地状态覆盖，不会删除 OA 源项目和历史数据。是否继续？",
    );
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

  function handleAddAccessAccount() {
    const nextUsername = accessUsernameDraft.trim();
    if (!nextUsername || controlsDisabled) {
      return;
    }
    setManagedAccessAccounts((current) => {
      const existingIndex = current.findIndex((item) => item.username === nextUsername);
      if (existingIndex >= 0) {
        return current.map((item, index) =>
          index === existingIndex ? { ...item, role: accessRoleDraft } : item,
        );
      }
      return normalizeManagedAccounts([
        ...current,
        {
          id: `access-${nextUsername}`,
          username: nextUsername,
          role: accessRoleDraft,
        },
      ]);
    });
    setAccessUsernameDraft("");
    setAccessRoleDraft("full_access");
  }

  function handleSave() {
    const normalizedAccounts = normalizeManagedAccounts(managedAccessAccounts);
    onSave({
      completedProjectIds,
      bankAccountMappings: mappings,
      allowedUsernames: normalizedAccounts.map((account) => account.username),
      readonlyExportUsernames: normalizedAccounts
        .filter((account) => account.role === "read_export_only")
        .map((account) => account.username),
      adminUsernames,
      workbenchColumnLayouts: settings.workbenchColumnLayouts,
      oaRetention: {
        cutoffDate: oaRetentionCutoffDate || "2026-01-01",
      },
      oaInvoiceOffset: {
        applicantNames: parseApplicantNames(oaInvoiceOffsetApplicantsText),
      },
    });
  }

  function handleOpenDataResetConfirm(action: WorkbenchSettingsDataResetAction) {
    if (controlsDisabled) {
      return;
    }
    setDataResetStatus(null);
    setDataResetDialog({ step: "confirm", action });
  }

  function handleContinueDataReset() {
    if (!dataResetDialog) {
      return;
    }
    setDataResetPassword("");
    setDataResetDialog({ step: "password", action: dataResetDialog.action });
  }

  async function handleConfirmDataReset() {
    if (!dataResetDialog || isDataResetting || !dataResetPassword) {
      return;
    }
    setIsDataResetting(true);
    setDataResetStatus(null);
    try {
      const result = await onDataReset({
        action: dataResetDialog.action,
        oaPassword: dataResetPassword,
      });
      setDataResetPassword("");
      setDataResetDialog(null);
      setDataResetStatus({
        tone: "success",
        message: result.message || "数据重置已完成。",
      });
    } catch (error) {
      setDataResetPassword("");
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
    setDataResetDialog(null);
  }

  return (
    <>
      <section aria-label="设置内容" className="settings-page-panel">
        <div className="settings-page-body workbench-settings-body">
          {!canSave ? <div className="state-panel settings-state-banner">当前账号仅支持查看和导出，不能保存设置。</div> : null}

          <div className="settings-two-column-layout">
            <SettingsTreeNav
              items={settingsNavigationItems}
              activeSectionId={activeSectionId}
              onSelect={setActiveSectionId}
            />

            <div className="settings-content-panel">
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

              {activeSectionId === "oa_retention" ? (
                <SettingsOaRetentionSection
                  controlsDisabled={controlsDisabled}
                  cutoffDate={oaRetentionCutoffDate}
                  onChangeCutoffDate={setOaRetentionCutoffDate}
                />
              ) : null}

              {activeSectionId === "oa_invoice_offset" && canManageOaInvoiceOffset ? (
                <SettingsOaInvoiceOffsetSection
                  controlsDisabled={controlsDisabled}
                  applicantsText={oaInvoiceOffsetApplicantsText}
                  onChangeApplicantsText={setOaInvoiceOffsetApplicantsText}
                />
              ) : null}

              {activeSectionId === "access_accounts" && canManageAccessControl ? (
                <SettingsAccessAccountsSection
                  controlsDisabled={controlsDisabled}
                  adminUsernames={adminUsernames}
                  managedAccessAccounts={managedAccessAccounts}
                  accessUsernameDraft={accessUsernameDraft}
                  accessRoleDraft={accessRoleDraft}
                  canAddAccessAccount={canAddAccessAccount}
                  onChangeAccessUsernameDraft={setAccessUsernameDraft}
                  onChangeAccessRoleDraft={setAccessRoleDraft}
                  onAddAccessAccount={handleAddAccessAccount}
                  onUpdateManagedAccessAccount={(accountId, updater) =>
                    setManagedAccessAccounts((current) => current.map((item) => (item.id === accountId ? updater(item) : item)))
                  }
                  onDeleteManagedAccessAccount={(accountId) =>
                    setManagedAccessAccounts((current) => current.filter((item) => item.id !== accountId))
                  }
                />
              ) : null}

              {activeSectionId === "data_reset" && canManageAccessControl ? (
                <SettingsDataResetSection
                  controlsDisabled={controlsDisabled}
                  dataResetStatus={dataResetStatus}
                  actions={DATA_RESET_ACTIONS}
                  onOpenDataResetConfirm={handleOpenDataResetConfirm}
                />
              ) : null}
            </div>
          </div>
        </div>
        <footer className="settings-page-footer">
          <button className="primary-button" type="button" disabled={controlsDisabled} onClick={handleSave}>
            {isSaving ? "保存中..." : "保存设置"}
          </button>
        </footer>
      </section>
      {dataResetDialog ? (
        <DataResetDialog
          config={dataResetActionConfig(dataResetDialog.action)}
          isBusy={isDataResetting}
          password={dataResetPassword}
          step={dataResetDialog.step}
          onCancel={handleCancelDataResetDialog}
          onContinue={handleContinueDataReset}
          onPasswordChange={setDataResetPassword}
          onSubmit={handleConfirmDataReset}
        />
      ) : null}
    </>
  );
}

function DataResetDialog({
  config,
  isBusy,
  password,
  step,
  onCancel,
  onContinue,
  onPasswordChange,
  onSubmit,
}: {
  config: DataResetActionConfig;
  isBusy: boolean;
  password: string;
  step: "confirm" | "password";
  onCancel: () => void;
  onContinue: () => void;
  onPasswordChange: (value: string) => void;
  onSubmit: () => void;
}) {
  if (step === "confirm") {
    return (
      <div className="detail-modal-backdrop" role="presentation">
        <button aria-label="取消数据重置确认" className="detail-modal-backdrop-foreground" type="button" onClick={onCancel} />
        <section aria-labelledby="data-reset-confirm-title" aria-modal="true" className="detail-modal data-reset-dialog" role="dialog">
          <header className="detail-modal-header">
            <div>
              <h2 id="data-reset-confirm-title">确认数据重置</h2>
              <p>{config.description}</p>
            </div>
          </header>
          <div className="detail-modal-body">
            <ul className="data-reset-impact-list">
              {config.impact.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <footer className="detail-modal-footer">
            <button className="secondary-button" type="button" onClick={onCancel}>
              取消
            </button>
            <button className="primary-button danger-button" type="button" onClick={onContinue}>
              继续
            </button>
          </footer>
        </section>
      </div>
    );
  }

  return (
    <div className="detail-modal-backdrop" role="presentation">
      <button aria-label="取消 OA 密码复核" className="detail-modal-backdrop-foreground" type="button" onClick={onCancel} />
      <section aria-labelledby="data-reset-password-title" aria-modal="true" className="detail-modal data-reset-dialog" role="dialog">
        <header className="detail-modal-header">
          <div>
            <h2 id="data-reset-password-title">OA 密码复核</h2>
            <p>请输入当前 OA 用户密码以确认本次高风险操作。</p>
          </div>
        </header>
        <div className="detail-modal-body">
          <label className="project-export-select-field data-reset-password-field">
            <span>当前 OA 用户密码</span>
            <input
              aria-label="当前 OA 用户密码"
              autoComplete="current-password"
              autoFocus
              type="password"
              value={password}
              disabled={isBusy}
              onChange={(event) => onPasswordChange(event.currentTarget.value)}
            />
          </label>
        </div>
        <footer className="detail-modal-footer">
          <button className="secondary-button" type="button" disabled={isBusy} onClick={onCancel}>
            取消
          </button>
          <button className="primary-button danger-button" type="button" disabled={isBusy || !password} onClick={onSubmit}>
            {isBusy ? "清理中..." : "确认清理"}
          </button>
        </footer>
      </section>
    </div>
  );
}
