import { Trash2 } from "lucide-react";

import type { WorkbenchAccessRole } from "../../features/workbench/types";
import type { SettingsAccessAccountsSectionProps } from "./types";

const ACCESS_ROLE_OPTIONS: Array<{ value: WorkbenchAccessRole; label: string }> = [
  { value: "full_access", label: "所有操作均可" },
  { value: "read_export_only", label: "只可看和只可导出" },
];

export default function SettingsAccessAccountsSection({
  controlsDisabled,
  administrator,
  managedAccessAccounts,
  isLoading,
  isSaving,
  status,
  validationMessage,
  accessUsernameDraft,
  accessRoleDraft,
  canAddAccessAccount,
  onChangeAccessUsernameDraft,
  onChangeAccessRoleDraft,
  onAddAccessAccount,
  onUpdateManagedAccessAccount,
  onDeleteManagedAccessAccount,
  onSave,
}: SettingsAccessAccountsSectionProps) {
  return (
    <section
      aria-labelledby="settings-section-access-accounts-title"
      className="settings-section-panel"
      id="settings-section-access-accounts"
      role="region"
    >
      <header className="settings-section-header">
        <h3 id="settings-section-access-accounts-title">访问账户管理</h3>
      </header>
      <div className="settings-section-body">
        <div className="settings-access-admin-note" role="status">
          <strong>权限管理员</strong>
          <div className="settings-access-admin-list">
            <span>{administrator?.username ?? "正在加载..."}</span>
          </div>
          <small>管理员为受保护账户，不可在 APP 内修改。</small>
        </div>

        {status ? (
          <div
            className={`settings-inline-alert settings-inline-alert--${status.tone}`}
            role={status.tone === "error" ? "alert" : "status"}
          >
            {status.message}
          </div>
        ) : null}
        {validationMessage ? (
          <div className="settings-inline-alert settings-inline-alert--error" role="alert">
            {validationMessage}
          </div>
        ) : null}
        {isLoading ? (
          <div className="settings-inline-alert settings-inline-alert--info" role="status">
            正在加载访问账户...
          </div>
        ) : null}

        <div className="settings-access-form">
          <label className="settings-field">
            <span>新增访问账户</span>
            <input
              disabled={controlsDisabled}
              type="text"
              value={accessUsernameDraft}
              onChange={(event) => onChangeAccessUsernameDraft(event.currentTarget.value)}
            />
          </label>
          <label className="settings-field">
            <span>新增账户权限</span>
            <select
              aria-label="新增账户权限"
              className="settings-select-control"
              disabled={controlsDisabled}
              value={accessRoleDraft}
              onChange={(event) => onChangeAccessRoleDraft(event.currentTarget.value as WorkbenchAccessRole)}
            >
              {ACCESS_ROLE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <button
            className="settings-primary-button"
            disabled={!canAddAccessAccount || controlsDisabled}
            type="button"
            onClick={onAddAccessAccount}
          >
            新增账户
          </button>
        </div>

        {managedAccessAccounts.length === 0 ? (
          <div className="settings-inline-alert settings-inline-alert--info" role="status">
            当前没有单独配置的可访问 OA 账户。
          </div>
        ) : (
          <div className="settings-native-table-shell">
            <table className="settings-native-table" aria-label="访问账户">
              <thead>
                <tr>
                  <th scope="col">账户</th>
                  <th scope="col">权限级别</th>
                  <th scope="col">操作</th>
                </tr>
              </thead>
              <tbody>
                {managedAccessAccounts.map((account) => (
                  <tr key={account.id}>
                    <td>
                      <input
                        aria-label={`${account.username} 账户`}
                        className="settings-table-input"
                        disabled={controlsDisabled}
                        type="text"
                        value={account.username}
                        onChange={(event) => {
                          const username = event.currentTarget.value;
                          onUpdateManagedAccessAccount(account.id, (current) => ({
                            ...current,
                            username,
                          }));
                        }}
                      />
                    </td>
                    <td>
                      <select
                        aria-label={`${account.username} 权限级别`}
                        className="settings-select-control settings-table-select"
                        disabled={controlsDisabled}
                        value={account.role}
                        onChange={(event) => {
                          const role = event.currentTarget.value as WorkbenchAccessRole;
                          onUpdateManagedAccessAccount(account.id, (current) => ({
                            ...current,
                            role,
                          }));
                        }}
                      >
                        {ACCESS_ROLE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <button
                        aria-label={`${account.username} 删除`}
                        className="settings-icon-button settings-icon-button--danger"
                        disabled={controlsDisabled}
                        type="button"
                        onClick={() => onDeleteManagedAccessAccount(account.id)}
                      >
                        <Trash2 aria-hidden="true" size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <button
          className="settings-primary-button"
          disabled={controlsDisabled || isLoading || isSaving || validationMessage !== null}
          type="button"
          onClick={onSave}
        >
          {isSaving ? "保存中..." : "保存访问账户"}
        </button>
      </div>
    </section>
  );
}
