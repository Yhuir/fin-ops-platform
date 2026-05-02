import type { SettingsDataResetSectionProps } from "./types";

export default function SettingsDataResetSection({
  controlsDisabled,
  dataResetStatus,
  dataResetProgress,
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
          {actions.map((item) => {
            const progress = dataResetProgress?.action === item.action ? dataResetProgress : null;
            const isRunning = dataResetProgress !== null;
            const progressLabel = progress
              ? `${progress.message || "正在清理"} ${progress.percent}%`
              : item.label;
            return (
              <article key={item.action} className="data-reset-card">
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.description}</p>
                </div>
                <button
                  className={`secondary-button danger-button data-reset-action-button${progress ? " data-reset-action-button-progress" : ""}`}
                  type="button"
                  disabled={controlsDisabled || isRunning}
                  onClick={() => onOpenDataResetConfirm(item.action)}
                >
                  {progress ? (
                    <span
                      aria-hidden="true"
                      className="data-reset-action-button-progress-bar"
                      style={{ width: `${progress.percent}%` }}
                    />
                  ) : null}
                  <span className="data-reset-action-button-label">{progressLabel}</span>
                </button>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
