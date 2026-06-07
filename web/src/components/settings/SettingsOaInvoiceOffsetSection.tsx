import type { SettingsOaInvoiceOffsetSectionProps } from "./types";

export default function SettingsOaInvoiceOffsetSection({
  controlsDisabled,
  applicantsText,
  onChangeApplicantsText,
}: SettingsOaInvoiceOffsetSectionProps) {
  return (
    <section
      aria-labelledby="settings-section-oa-invoice-offset-title"
      className="settings-section-panel"
      id="settings-section-oa-invoice-offset"
      role="region"
    >
      <header className="settings-section-header">
        <h3 id="settings-section-oa-invoice-offset-title">冲账规则</h3>
      </header>
      <div className="settings-section-body">
        <label className="settings-field settings-field--wide">
          <span>冲账申请人</span>
          <input
            disabled={controlsDisabled}
            type="text"
            value={applicantsText}
            onChange={(event) => onChangeApplicantsText(event.currentTarget.value)}
          />
          <small>多个申请人以逗号或空格分隔</small>
        </label>
        <div className="settings-inline-alert settings-inline-alert--info" role="status">
          <strong>自动配对规则</strong>
          <p>
            OA 申请人在名单内时，自动配对该 OA 和 OA 附件解析出的发票，并打“冲”标签；该组不计入成本统计。
          </p>
        </div>
      </div>
    </section>
  );
}
