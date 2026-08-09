import { Button } from "@heroui/react";

import { formatMoney } from "../../features/money";
import type { TaxSummary } from "../../features/tax/types";

type TaxSummaryBandProps = {
  summary: TaxSummary;
  outputCount: number;
  selectedPlanInputCount: number;
  certifiedCount: number;
  canSave?: boolean;
  isSaving?: boolean;
  saveDisabled?: boolean;
  onSave?: () => void;
};

export default function TaxSummaryBand({
  summary,
  outputCount,
  selectedPlanInputCount,
  certifiedCount,
  canSave = false,
  isSaving = false,
  saveDisabled = false,
  onSave,
}: TaxSummaryBandProps) {
  const metrics = [
    { label: "销项税额", value: summary.outputTax, tone: "default" },
    { label: "已认证结果进项税额", value: summary.certifiedInputTax, tone: "default" },
    { label: "计划进项税额", value: summary.plannedInputTax, tone: "default" },
    { label: "本月抵扣额", value: summary.deductibleTax, tone: "default" },
    {
      label: summary.resultLabel,
      value: summary.resultAmount,
      tone: summary.resultLabel === "本月应纳税额" ? "warning" : "success",
    },
  ] as const;

  return (
    <section aria-label="税金抵扣汇总" className="tax-summary-band">
      <div className="tax-summary-band__metrics">
        {metrics.map((metric) => (
          <div className={`tax-summary-band__metric tax-summary-band__metric--${metric.tone}`} key={metric.label}>
            <span>{metric.label}</span>
            <strong>{formatMoney(metric.value)}</strong>
          </div>
        ))}
      </div>
      <div className="tax-summary-band__footer">
        <strong className="tax-summary-band__title">税金抵扣试算</strong>
        <div className="tax-summary-band__counts">
          <span>销项票 {outputCount}</span>
          <span>已认证 {certifiedCount}</span>
          <span>计划勾选 {selectedPlanInputCount}</span>
        </div>
        {canSave ? (
          <Button
            isDisabled={saveDisabled || isSaving}
            isPending={isSaving}
            onPress={onSave}
            size="sm"
            type="button"
          >
            {isSaving ? "保存中" : "保存计划"}
          </Button>
        ) : null}
      </div>
    </section>
  );
}
