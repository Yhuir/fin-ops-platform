import type { SettingsOaInvoiceOffsetSectionProps } from "./types";

export default function SettingsOaInvoiceOffsetSection({
  controlsDisabled,
  applicantsText,
  onChangeApplicantsText,
}: SettingsOaInvoiceOffsetSectionProps) {
  return (
    <section
      aria-labelledby="settings-section-oa-invoice-offset-title"
      className="cost-explorer-lane settings-section-panel"
      id="settings-section-oa-invoice-offset"
      role="region"
    >
      <div className="cost-explorer-lane-header settings-section-header">
        <h3 id="settings-section-oa-invoice-offset-title">冲账规则</h3>
      </div>
      <div className="settings-section-body">
        <div className="settings-bank-mapping-form">
          <label className="project-export-select-field">
            <span>冲账申请人</span>
            <input
              aria-label="冲账申请人"
              value={applicantsText}
              disabled={controlsDisabled}
              onChange={(event) => onChangeApplicantsText(event.currentTarget.value)}
            />
          </label>
          <div className="settings-access-admin-note">
            <strong>自动配对规则</strong>
            <p>
              OA 申请人在名单内时，自动配对该 OA 和 OA 附件解析出的发票，并打“冲”标签；该组不计入成本统计。
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
