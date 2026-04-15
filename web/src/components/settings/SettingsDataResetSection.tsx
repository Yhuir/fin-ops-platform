import type { SettingsDataResetSectionProps } from "./types";

export default function SettingsDataResetSection({
  controlsDisabled,
  dataResetStatus,
  actions,
  onOpenDataResetConfirm,
}: SettingsDataResetSectionProps) {
  return (
    <section
      aria-labelledby="settings-section-data-reset-title"
      className="cost-explorer-lane settings-section-panel"
      id="settings-section-data-reset"
      role="region"
    >
      <div className="cost-explorer-lane-header settings-section-header">
        <h3 id="settings-section-data-reset-title">数据重置</h3>
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
          {actions.map((item) => (
            <article key={item.action} className="data-reset-card">
              <div>
                <strong>{item.title}</strong>
                <p>{item.description}</p>
              </div>
              <button
                className="secondary-button danger-button"
                type="button"
                disabled={controlsDisabled}
                onClick={() => onOpenDataResetConfirm(item.action)}
              >
                {item.label}
              </button>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
