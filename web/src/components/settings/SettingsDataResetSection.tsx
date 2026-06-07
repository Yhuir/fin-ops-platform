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
      className="settings-section-panel"
      id="settings-section-data-reset"
      role="region"
    >
      <header className="settings-section-header">
        <h3 id="settings-section-data-reset-title">数据重置</h3>
      </header>
      <div className="settings-section-body">
        <div className="settings-inline-alert settings-inline-alert--warning" role="status">
          <strong>高风险操作</strong>
          <p>
            这些按钮只清理 app 内部数据，不允许触碰 `form_data_db.form_data`。每次执行前都需要二次确认和当前 OA 用户密码复核。
          </p>
        </div>
        {dataResetStatus ? (
          <div
            className={`settings-inline-alert settings-inline-alert--${dataResetStatus.tone}`}
            role={dataResetStatus.tone === "error" ? "alert" : "status"}
          >
            {dataResetStatus.message}
          </div>
        ) : null}
        <div className="settings-data-reset-grid">
          {actions.map((item) => {
            const progress = dataResetProgress?.action === item.action ? dataResetProgress : null;
            const isRunning = dataResetProgress !== null;
            const progressLabel = progress
              ? `${progress.message || "正在清理"} ${progress.percent}%`
              : item.label;
            return (
              <article className="settings-data-reset-card" key={item.action}>
                <div className="settings-data-reset-card__body">
                  <strong>{item.title}</strong>
                  <p>{item.description}</p>
                  <ul>
                    {item.impact.map((impactItem) => (
                      <li key={impactItem}>{impactItem}</li>
                    ))}
                  </ul>
                </div>
                <div className="settings-data-reset-card__actions">
                  {progress ? (
                    <progress
                      aria-label={progressLabel}
                      className="settings-data-reset-progress"
                      max={100}
                      value={progress.percent}
                    />
                  ) : null}
                  <button
                    className="settings-danger-button"
                    disabled={controlsDisabled || isRunning}
                    type="button"
                    onClick={() => onOpenDataResetConfirm(item.action)}
                  >
                    {progressLabel}
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
