import type { WorkbenchAccessRole } from "../../features/workbench/types";
import type { SettingsAccessAccountsSectionProps } from "./types";

export default function SettingsAccessAccountsSection({
  controlsDisabled,
  adminUsernames,
  managedAccessAccounts,
  accessUsernameDraft,
  accessRoleDraft,
  canAddAccessAccount,
  onChangeAccessUsernameDraft,
  onChangeAccessRoleDraft,
  onAddAccessAccount,
  onUpdateManagedAccessAccount,
  onDeleteManagedAccessAccount,
}: SettingsAccessAccountsSectionProps) {
  return (
    <section
      aria-labelledby="settings-section-access-accounts-title"
      className="cost-explorer-lane settings-section-panel"
      id="settings-section-access-accounts"
      role="region"
    >
      <div className="cost-explorer-lane-header settings-section-header">
        <h3 id="settings-section-access-accounts-title">访问账户管理</h3>
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
              onChange={(event) => onChangeAccessUsernameDraft(event.currentTarget.value)}
            />
          </label>
          <label className="project-export-select-field">
            <span>新增账户权限</span>
            <select
              aria-label="新增账户权限"
              value={accessRoleDraft}
              disabled={controlsDisabled}
              onChange={(event) => onChangeAccessRoleDraft(event.currentTarget.value as WorkbenchAccessRole)}
            >
              <option value="full_access">所有操作均可</option>
              <option value="read_export_only">只可看和只可导出</option>
            </select>
          </label>
          <button
            className="primary-button"
            type="button"
            disabled={!canAddAccessAccount || controlsDisabled}
            onClick={onAddAccessAccount}
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
                    onUpdateManagedAccessAccount(account.id, (current) => ({
                      ...current,
                      username: event.currentTarget.value,
                    }))
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
                    onUpdateManagedAccessAccount(account.id, (current) => ({
                      ...current,
                      role: event.currentTarget.value as WorkbenchAccessRole,
                    }))
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
                onClick={() => onDeleteManagedAccessAccount(account.id)}
              >
                删除
              </button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
