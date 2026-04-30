import type { SettingsOaRetentionSectionProps } from "./types";

export default function SettingsOaRetentionSection({
  controlsDisabled,
  cutoffDate,
  oaImport,
  onChangeCutoffDate,
  onToggleFormType,
  onToggleStatus,
}: SettingsOaRetentionSectionProps) {
  const formTypeOptions = oaImport.availableFormTypes.filter((option) =>
    ["支付申请", "日常报销"].includes(option.label),
  );
  const statusOptions = oaImport.availableStatuses.filter((option) =>
    ["已完成", "进行中"].includes(option.label),
  );

  return (
    <section
      aria-labelledby="settings-section-oa-retention-title"
      className="cost-explorer-lane settings-section-panel"
      id="settings-section-oa-retention"
      role="region"
    >
      <div className="cost-explorer-lane-header settings-section-header">
        <h3 id="settings-section-oa-retention-title">OA导入设置</h3>
      </div>
      <div className="settings-section-body">
        <div className="settings-oa-import-layout">
          <label className="project-export-select-field">
            <span>保留起始日期</span>
            <input
              aria-label="OA导入起始日期"
              type="date"
              value={cutoffDate}
              disabled={controlsDisabled}
              onChange={(event) => onChangeCutoffDate(event.currentTarget.value)}
            />
          </label>
          <fieldset className="settings-checkbox-group">
            <legend>表单类型</legend>
            <div className="settings-checkbox-list">
              {formTypeOptions.map((option) => (
                <label key={option.value} className="settings-checkbox-row">
                  <input
                    type="checkbox"
                    checked={oaImport.formTypes.includes(option.value)}
                    disabled={controlsDisabled}
                    onChange={() => onToggleFormType(option.value)}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className="settings-checkbox-group">
            <legend>流程状态</legend>
            <div className="settings-checkbox-list">
              {statusOptions.map((option) => (
                <label key={option.value} className="settings-checkbox-row">
                  <input
                    type="checkbox"
                    checked={oaImport.statuses.includes(option.value)}
                    disabled={controlsDisabled}
                    onChange={() => onToggleStatus(option.value)}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
          </fieldset>
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
