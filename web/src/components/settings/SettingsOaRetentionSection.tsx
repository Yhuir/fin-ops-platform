import OaManualSearchImportTable from "./OaManualSearchImportTable";
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
      className="settings-section-panel"
      id="settings-section-oa-retention"
      role="region"
    >
      <header className="settings-section-header">
        <h3 id="settings-section-oa-retention-title">OA导入设置</h3>
      </header>
      <div className="settings-section-body">
        <label className="settings-field settings-field--date">
          <span>OA导入起始日期</span>
          <input
            disabled={controlsDisabled}
            type="date"
            value={cutoffDate}
            onChange={(event) => onChangeCutoffDate(event.currentTarget.value)}
          />
        </label>

        <div className="settings-oa-import-layout">
          <fieldset className="settings-checkbox-group" disabled={controlsDisabled}>
            <legend>表单类型</legend>
            <div className="settings-checkbox-list">
              {formTypeOptions.map((option) => (
                <label className="settings-checkbox-row" key={option.value}>
                  <input
                    checked={oaImport.formTypes.includes(option.value)}
                    type="checkbox"
                    onChange={() => onToggleFormType(option.value)}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className="settings-checkbox-group" disabled={controlsDisabled}>
            <legend>流程状态</legend>
            <div className="settings-checkbox-list">
              {statusOptions.map((option) => (
                <label className="settings-checkbox-row" key={option.value}>
                  <input
                    checked={oaImport.statuses.includes(option.value)}
                    type="checkbox"
                    onChange={() => onToggleStatus(option.value)}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        <div className="settings-inline-alert settings-inline-alert--info" role="status">
          <strong>保留规则</strong>
          <p>
            保留该日期及之后的 OA；保留与这些 OA 同组的流水和发票；如果旧 OA 与该日期及之后的流水同组，也会重新保留。
          </p>
        </div>

        <OaManualSearchImportTable />
      </div>
    </section>
  );
}
