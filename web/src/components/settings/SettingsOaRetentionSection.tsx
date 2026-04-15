import type { SettingsOaRetentionSectionProps } from "./types";

export default function SettingsOaRetentionSection({
  controlsDisabled,
  cutoffDate,
  onChangeCutoffDate,
}: SettingsOaRetentionSectionProps) {
  return (
    <section
      aria-labelledby="settings-section-oa-retention-title"
      className="cost-explorer-lane settings-section-panel"
      id="settings-section-oa-retention"
      role="region"
    >
      <div className="cost-explorer-lane-header settings-section-header">
        <h3 id="settings-section-oa-retention-title">保OA</h3>
      </div>
      <div className="settings-section-body">
        <div className="settings-bank-mapping-form">
          <label className="project-export-select-field">
            <span>保留起始日期</span>
            <input
              aria-label="保OA起始日期"
              type="date"
              value={cutoffDate}
              disabled={controlsDisabled}
              onChange={(event) => onChangeCutoffDate(event.currentTarget.value)}
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
  );
}
