import { useMemo, useState } from "react";

import { useSession } from "../../contexts/SessionContext";
import type {
  BankAccountMapping,
  WorkbenchAccessRole,
  WorkbenchProjectSetting,
  WorkbenchSettings,
  WorkbenchSettingsDataResetAction,
  WorkbenchSettingsDataResetResult,
} from "../../features/workbench/types";

type ManagedAccessAccount = {
  id: string;
  username: string;
  role: WorkbenchAccessRole;
};

type WorkbenchSettingsModalProps = {
  settings: WorkbenchSettings;
  isSaving: boolean;
  canSave: boolean;
  canManageAccessControl: boolean;
  onClose: () => void;
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
};

type SettingsSectionId =
  | "projects"
  | "bank_accounts"
  | "oa_retention"
  | "oa_invoice_offset"
  | "access_accounts"
  | "data_reset";

type DataResetDialogState =
  | { step: "confirm"; action: WorkbenchSettingsDataResetAction }
  | { step: "password"; action: WorkbenchSettingsDataResetAction }
  | null;

type DataResetStatus = {
  tone: "success" | "error";
  message: string;
};

type DataResetActionConfig = {
  action: WorkbenchSettingsDataResetAction;
  label: string;
  title: string;
  description: string;
  impact: string[];
};

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
  onClose,
  onDataReset,
  onSave,
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
  const [last4Draft, setLast4Draft] = useState("");
  const [accessUsernameDraft, setAccessUsernameDraft] = useState("");
  const [accessRoleDraft, setAccessRoleDraft] = useState<WorkbenchAccessRole>("full_access");
  const [activeSectionId, setActiveSectionId] = useState<SettingsSectionId>("projects");
  const [dataResetDialog, setDataResetDialog] = useState<DataResetDialogState>(null);
  const [dataResetPassword, setDataResetPassword] = useState("");
  const [dataResetStatus, setDataResetStatus] = useState<DataResetStatus | null>(null);
  const [isDataResetting, setIsDataResetting] = useState(false);

  const controlsDisabled = !canSave || isSaving || isDataResetting;
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
  const canAddAccessAccount = accessUsernameDraft.trim().length > 0;
  const currentSessionUser =
    session.status === "authenticated" || session.status === "forbidden" ? session.session.user : null;
  const currentAccountLabel = currentSessionUser
    ? `${currentSessionUser.displayName}（${currentSessionUser.username}）`
    : "--";
  const canManageOaInvoiceOffset =
    currentSessionUser !== null && OA_INVOICE_OFFSET_SETTINGS_VISIBLE_USERNAMES.has(currentSessionUser.username);
  const settingsNavigationItems = useMemo(
    () => [
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
    ].filter((item) => item.visible),
    [
      activeProjects.length,
      adminUsernames.length,
      canManageAccessControl,
      canManageOaInvoiceOffset,
      completedProjects.length,
      managedAccessAccounts.length,
      mappings.length,
      oaInvoiceOffsetApplicantsText,
    ],
  );

  function handleAddMapping() {
    if (!canAddMapping || controlsDisabled) {
      return;
    }
    const nextLast4 = last4Draft.trim();
    if (mappings.some((item) => item.last4 === nextLast4)) {
      setMappings((current) =>
        current.map((item) => (item.last4 === nextLast4 ? { ...item, bankName: bankNameDraft.trim() } : item)),
      );
    } else {
      setMappings((current) => [
        ...current,
        {
          id: `bank_mapping_${nextLast4}`,
          last4: nextLast4,
          bankName: bankNameDraft.trim(),
        },
      ]);
    }
    setLast4Draft("");
    setBankNameDraft("");
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
    const action = dataResetDialog.action;
    const passwordForRequest = dataResetPassword;
    try {
      const result = await onDataReset({
        action,
        oaPassword: passwordForRequest,
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
    <div className="export-center-modal-layer" role="presentation">
      <button
        aria-label="关闭设置"
        className="export-center-modal-backdrop"
        type="button"
        disabled={isDataResetting}
        onClick={onClose}
      />
      <section
        aria-labelledby="workbench-settings-modal-title"
        aria-modal="true"
        className="export-center-modal workbench-settings-modal"
        role="dialog"
      >
        <header className="export-center-modal-header">
          <div>
            <h2 id="workbench-settings-modal-title">关联台设置</h2>
            <p>管理项目完工状态、银行账户映射，以及受控账号的访问权限。</p>
            <div className="settings-session-account">
              <span className="settings-session-account-label">登录账户：</span>
              <strong>{currentAccountLabel}</strong>
            </div>
          </div>
          <button className="secondary-button" type="button" onClick={onClose} disabled={isSaving || isDataResetting}>
            关闭
          </button>
        </header>

        <div className="export-center-modal-body workbench-settings-body">
          {!canSave ? <div className="state-panel settings-state-banner">当前账号仅支持查看和导出，不能保存设置。</div> : null}

          <div className="settings-two-column-layout">
            <aside className="cost-explorer-lane settings-tree-panel" aria-label="设置导航">
              <header className="cost-explorer-lane-header settings-nav-header">
                <h3>设置分类</h3>
                <span>{settingsNavigationItems.length}</span>
              </header>
              <div className="cost-explorer-list settings-tree" role="tree" aria-label="设置分类">
                {settingsNavigationItems.map((item) => (
                  <button
                    key={item.id}
                    role="treeitem"
                    aria-selected={activeSectionId === item.id}
                    className={`cost-explorer-item settings-tree-item${activeSectionId === item.id ? " active" : ""}`}
                    type="button"
                    onClick={() => setActiveSectionId(item.id)}
                  >
                    <span className="settings-tree-copy">
                      <strong>{item.label}</strong>
                      <small>{item.description}</small>
                    </span>
                    <span className="settings-tree-count">{item.count}</span>
                  </button>
                ))}
              </div>
            </aside>

            <div className="settings-content-panel">
              {activeSectionId === "projects" ? (
                <section className="cost-explorer-lane settings-section-panel">
                  <div className="cost-explorer-lane-header settings-section-header">
                    <h3>项目状态管理</h3>
                  </div>
                  <div className="settings-section-body">
                    <div className="settings-project-columns">
                    <div className="settings-project-column">
                      <div className="settings-project-column-head">
                        <strong>进行中项目</strong>
                        <span>{activeProjects.length} 个</span>
                      </div>
                      <div className="settings-project-list">
                        {activeProjects.map((project) => (
                          <button
                            key={project.id}
                            className="settings-project-row"
                            type="button"
                            disabled={controlsDisabled}
                            onClick={() => setCompletedProjectIds((current) => toggleCompleted(project.id, current))}
                          >
                            <span>{project.projectName}</span>
                            <span>标记完成</span>
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="settings-project-column">
                      <div className="settings-project-column-head">
                        <strong>已完成项目</strong>
                        <span>{completedProjects.length} 个</span>
                      </div>
                      <div className="settings-project-list">
                        {completedProjects.map((project) => (
                          <button
                            key={project.id}
                            className="settings-project-row done"
                            type="button"
                            disabled={controlsDisabled}
                            onClick={() => setCompletedProjectIds((current) => toggleCompleted(project.id, current))}
                          >
                            <span>{project.projectName}</span>
                            <span>移回进行中</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                  </div>
                </section>
              ) : null}

              {activeSectionId === "bank_accounts" ? (
                <section className="cost-explorer-lane settings-section-panel">
                  <div className="cost-explorer-lane-header settings-section-header">
                    <h3>银行账户映射</h3>
                  </div>
                  <div className="settings-section-body">
                  <div className="settings-bank-mapping-form">
                    <label className="project-export-select-field">
                      <span>银行名称</span>
                      <input
                        value={bankNameDraft}
                        disabled={controlsDisabled}
                        onChange={(event) => setBankNameDraft(event.currentTarget.value)}
                      />
                    </label>
                    <label className="project-export-select-field">
                      <span>银行卡后四位</span>
                      <input
                        maxLength={4}
                        value={last4Draft}
                        disabled={controlsDisabled}
                        onChange={(event) => setLast4Draft(event.currentTarget.value.replace(/\D/g, ""))}
                      />
                    </label>
                    <button
                      className="primary-button"
                      type="button"
                      disabled={!canAddMapping || controlsDisabled}
                      onClick={handleAddMapping}
                    >
                      新增映射
                    </button>
                  </div>

                  <div className="settings-bank-mapping-list">
                    {mappings.length === 0 ? <div className="cost-explorer-empty">当前没有银行映射。</div> : null}
                    {mappings.map((mapping) => (
                      <div key={mapping.id} className="settings-bank-mapping-row">
                        <label className="project-export-select-field">
                          <span>银行名称</span>
                          <input
                            value={mapping.bankName}
                            disabled={controlsDisabled}
                            onChange={(event) =>
                              setMappings((current) =>
                                current.map((item) => (item.id === mapping.id ? { ...item, bankName: event.currentTarget.value } : item)),
                              )
                            }
                          />
                        </label>
                        <label className="project-export-select-field">
                          <span>后四位</span>
                          <input
                            maxLength={4}
                            value={mapping.last4}
                            disabled={controlsDisabled}
                            onChange={(event) =>
                              setMappings((current) =>
                                current.map((item) =>
                                  item.id === mapping.id
                                    ? { ...item, last4: event.currentTarget.value.replace(/\D/g, "").slice(0, 4) }
                                    : item,
                                ),
                              )
                            }
                          />
                        </label>
                        <button
                          className="secondary-button danger-button"
                          type="button"
                          disabled={controlsDisabled}
                          onClick={() => setMappings((current) => current.filter((item) => item.id !== mapping.id))}
                        >
                          删除
                        </button>
                      </div>
                    ))}
                  </div>
                  </div>
                </section>
              ) : null}

              {activeSectionId === "oa_retention" ? (
                <section className="cost-explorer-lane settings-section-panel">
                  <div className="cost-explorer-lane-header settings-section-header">
                    <h3>保OA</h3>
                  </div>
                  <div className="settings-section-body">
                    <div className="settings-bank-mapping-form">
                      <label className="project-export-select-field">
                        <span>保留起始日期</span>
                        <input
                          aria-label="保OA起始日期"
                          type="date"
                          value={oaRetentionCutoffDate}
                          disabled={controlsDisabled}
                          onChange={(event) => setOaRetentionCutoffDate(event.currentTarget.value)}
                        />
                      </label>
                      <div className="settings-access-admin-note">
                        <strong>保留规则</strong>
                        <p>
                          保留该日期及之后的 OA；保留与这些 OA 同组的流水和发票；如果旧 OA 与该日期及之后的流水同组，也会重新保留。
                        </p>
                      </div>
                    </div>
                  </div>
                </section>
              ) : null}

              {activeSectionId === "oa_invoice_offset" && canManageOaInvoiceOffset ? (
                <section className="cost-explorer-lane settings-section-panel">
                  <div className="cost-explorer-lane-header settings-section-header">
                    <h3>冲账规则</h3>
                  </div>
                  <div className="settings-section-body">
                    <div className="settings-bank-mapping-form">
                      <label className="project-export-select-field">
                        <span>冲账申请人</span>
                        <input
                          aria-label="冲账申请人"
                          value={oaInvoiceOffsetApplicantsText}
                          disabled={controlsDisabled}
                          onChange={(event) => setOaInvoiceOffsetApplicantsText(event.currentTarget.value)}
                        />
                      </label>
                      <div className="settings-access-admin-note">
                        <strong>自动配对规则</strong>
                        <p>
                          OA 申请人在名单内时，自动配对该 OA 和 OA 附件解析出的发票，并打“冲”标签；该组不计入成本统计。
                        </p>
                      </div>
                    </div>
                  </div>
                </section>
              ) : null}

              {activeSectionId === "access_accounts" && canManageAccessControl ? (
                <section className="cost-explorer-lane settings-section-panel">
                  <div className="cost-explorer-lane-header settings-section-header">
                    <h3>访问账户管理</h3>
                  </div>
                  <div className="settings-section-body">
                  <div className="settings-access-admin-note">
                    <strong>权限管理员</strong>
                    <div className="settings-access-admin-list">
                      {adminUsernames.map((username) => (
                        <span key={username} className="zone-selection-pill">
                          {username}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="settings-bank-mapping-form settings-access-form">
                    <label className="project-export-select-field">
                      <span>新增访问账户</span>
                      <input
                        value={accessUsernameDraft}
                        disabled={controlsDisabled}
                        onChange={(event) => setAccessUsernameDraft(event.currentTarget.value)}
                      />
                    </label>
                    <label className="project-export-select-field">
                      <span>新增账户权限</span>
                      <select
                        aria-label="新增账户权限"
                        value={accessRoleDraft}
                        disabled={controlsDisabled}
                        onChange={(event) => setAccessRoleDraft(event.currentTarget.value as WorkbenchAccessRole)}
                      >
                        <option value="full_access">所有操作均可</option>
                        <option value="read_export_only">只可看和只可导出</option>
                      </select>
                    </label>
                    <button
                      className="primary-button"
                      type="button"
                      disabled={!canAddAccessAccount || controlsDisabled}
                      onClick={handleAddAccessAccount}
                    >
                      新增账户
                    </button>
                  </div>

                  <div className="settings-bank-mapping-list">
                    {managedAccessAccounts.length === 0 ? (
                      <div className="cost-explorer-empty">当前没有单独配置的可访问 OA 账户。</div>
                    ) : null}
                    {managedAccessAccounts.map((account) => (
                      <div key={account.id} className="settings-bank-mapping-row">
                        <label className="project-export-select-field">
                          <span>账户</span>
                          <input
                            value={account.username}
                            disabled={controlsDisabled}
                            onChange={(event) =>
                              setManagedAccessAccounts((current) =>
                                current.map((item) =>
                                  item.id === account.id ? { ...item, username: event.currentTarget.value } : item,
                                ),
                              )
                            }
                          />
                        </label>
                        <label className="project-export-select-field">
                          <span>权限级别</span>
                          <select
                            aria-label={`权限级别-${account.username}`}
                            value={account.role}
                            disabled={controlsDisabled}
                            onChange={(event) =>
                              setManagedAccessAccounts((current) =>
                                current.map((item) =>
                                  item.id === account.id
                                    ? { ...item, role: event.currentTarget.value as WorkbenchAccessRole }
                                    : item,
                                ),
                              )
                            }
                          >
                            <option value="full_access">所有操作均可</option>
                            <option value="read_export_only">只可看和只可导出</option>
                          </select>
                        </label>
                        <button
                          className="secondary-button danger-button"
                          type="button"
                          disabled={controlsDisabled}
                          onClick={() =>
                            setManagedAccessAccounts((current) => current.filter((item) => item.id !== account.id))
                          }
                        >
                          删除
                        </button>
                      </div>
                    ))}
                  </div>
                  </div>
                </section>
              ) : null}

              {activeSectionId === "data_reset" && canManageAccessControl ? (
                <section className="cost-explorer-lane settings-section-panel">
                  <div className="cost-explorer-lane-header settings-section-header">
                    <h3>数据重置</h3>
                  </div>
                  <div className="settings-section-body">
                    <div className="settings-access-admin-note data-reset-warning">
                      <strong>高风险操作</strong>
                      <p>
                        这些按钮只清理 app 内部数据，不允许触碰 `form_data_db.form_data`。每次执行前都需要二次确认和当前 OA 用户密码复核。
                      </p>
                    </div>
                    {dataResetStatus ? (
                      <div className={`state-panel data-reset-status data-reset-status-${dataResetStatus.tone}`}>
                        {dataResetStatus.message}
                      </div>
                    ) : null}
                    <div className="data-reset-actions">
                      {DATA_RESET_ACTIONS.map((item) => (
                        <article key={item.action} className="data-reset-card">
                          <div>
                            <strong>{item.title}</strong>
                            <p>{item.description}</p>
                          </div>
                          <button
                            className="secondary-button danger-button"
                            type="button"
                            disabled={controlsDisabled}
                            onClick={() => handleOpenDataResetConfirm(item.action)}
                          >
                            {item.label}
                          </button>
                        </article>
                      ))}
                    </div>
                  </div>
                </section>
              ) : null}
            </div>
          </div>
        </div>

        <footer className="export-center-modal-footer">
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
    </div>
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
