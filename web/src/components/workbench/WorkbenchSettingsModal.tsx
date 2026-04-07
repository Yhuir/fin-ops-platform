import { useMemo, useState } from "react";

import type {
  BankAccountMapping,
  WorkbenchAccessRole,
  WorkbenchProjectSetting,
  WorkbenchSettings,
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
  }) => void;
};

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

export default function WorkbenchSettingsModal({
  settings,
  isSaving,
  canSave,
  canManageAccessControl,
  onClose,
  onSave,
}: WorkbenchSettingsModalProps) {
  const [completedProjectIds, setCompletedProjectIds] = useState<string[]>(settings.projects.completedProjectIds);
  const [mappings, setMappings] = useState<BankAccountMapping[]>(settings.bankAccountMappings);
  const [managedAccessAccounts, setManagedAccessAccounts] = useState<ManagedAccessAccount[]>(
    buildManagedAccessAccounts(settings),
  );
  const [bankNameDraft, setBankNameDraft] = useState("");
  const [last4Draft, setLast4Draft] = useState("");
  const [accessUsernameDraft, setAccessUsernameDraft] = useState("");
  const [accessRoleDraft, setAccessRoleDraft] = useState<WorkbenchAccessRole>("full_access");

  const controlsDisabled = !canSave || isSaving;
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
    });
  }

  return (
    <div className="export-center-modal-layer" role="presentation">
      <button aria-label="关闭设置" className="export-center-modal-backdrop" type="button" onClick={onClose} />
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
          </div>
          <button className="secondary-button" type="button" onClick={onClose} disabled={isSaving}>
            关闭
          </button>
        </header>

        <div className="export-center-modal-body workbench-settings-body">
          {!canSave ? <div className="state-panel">当前账号仅支持查看和导出，不能保存设置。</div> : null}

          <section className="export-center-section">
            <div className="export-center-section-header">
              <h3>项目状态管理</h3>
            </div>
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
          </section>

          {canManageAccessControl ? (
            <section className="export-center-section">
              <div className="export-center-section-header">
                <h3>访问账户管理</h3>
              </div>
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
            </section>
          ) : null}

          <section className="export-center-section">
            <div className="export-center-section-header">
              <h3>银行账户映射</h3>
            </div>
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
          </section>
        </div>

        <footer className="export-center-modal-footer">
          <button className="primary-button" type="button" disabled={controlsDisabled} onClick={handleSave}>
            {isSaving ? "保存中..." : "保存设置"}
          </button>
        </footer>
      </section>
    </div>
  );
}
