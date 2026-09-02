import { Button, ProgressBar } from "@heroui/react";

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
      className="settings-section-panel settings-section-panel--compact"
      id="settings-section-data-reset"
      role="region"
    >
      <header className="settings-section-header">
        <h3 id="settings-section-data-reset-title">数据重置</h3>
      </header>
      <div className="settings-section-body">
        {dataResetStatus ? (
          <div
            className={`settings-inline-alert settings-inline-alert--${dataResetStatus.tone}`}
            role={dataResetStatus.tone === "error" ? "alert" : "status"}
          >
            {dataResetStatus.message}
          </div>
        ) : null}
        <div className="settings-data-reset-list">
          {actions.map((item) => {
            const progress = dataResetProgress?.action === item.action ? dataResetProgress : null;
            const isRunning = dataResetProgress !== null;
            const progressLabel = progress
              ? `${progress.message || "正在清理"} ${progress.percent}%`
              : item.label;
            return (
              <div className="settings-data-reset-row" key={item.action}>
                <div className="settings-data-reset-row__content">
                  <strong>{item.label}</strong>
                  {progress ? (
                    <ProgressBar
                      aria-label={progressLabel}
                      color="danger"
                      maxValue={100}
                      size="sm"
                      value={progress.percent}
                    >
                      <ProgressBar.Track>
                        <ProgressBar.Fill />
                      </ProgressBar.Track>
                    </ProgressBar>
                  ) : null}
                </div>
                <Button
                  aria-label={progressLabel}
                  isDisabled={controlsDisabled || isRunning}
                  size="sm"
                  variant="danger"
                  onPress={() => onOpenDataResetConfirm(item.action)}
                >
                  {progress ? `${progress.percent}%` : "执行"}
                </Button>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
