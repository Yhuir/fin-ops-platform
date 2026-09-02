import { Input } from "@heroui/react";

import type { SettingsOaInvoiceOffsetSectionProps } from "./types";

export default function SettingsOaInvoiceOffsetSection({
  controlsDisabled,
  applicantsText,
  onChangeApplicantsText,
}: SettingsOaInvoiceOffsetSectionProps) {
  return (
    <section
      aria-labelledby="settings-section-oa-invoice-offset-title"
      className="settings-section-panel settings-section-panel--compact"
      id="settings-section-oa-invoice-offset"
      role="region"
    >
      <header className="settings-section-header">
        <h3 id="settings-section-oa-invoice-offset-title">冲账规则</h3>
      </header>
      <div className="settings-section-body">
        <label className="settings-field settings-field--wide">
          <span>冲账申请人</span>
          <Input
            aria-label="冲账申请人"
            disabled={controlsDisabled}
            placeholder="多个姓名用逗号分隔"
            value={applicantsText}
            onChange={(event) => onChangeApplicantsText(event.currentTarget.value)}
          />
        </label>
      </div>
    </section>
  );
}
