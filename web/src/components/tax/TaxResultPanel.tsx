import { Button } from "@heroui/react";

type TaxResultPanelProps = {
  outputCount: number;
  selectedPlanInputCount: number;
  certifiedCount: number;
  resultLabel: string;
  resultAmount: string;
  canSave?: boolean;
  isSaving?: boolean;
  saveDisabled?: boolean;
  onSave?: () => void;
};

export default function TaxResultPanel({
  outputCount,
  selectedPlanInputCount,
  certifiedCount,
  resultLabel,
  resultAmount,
  canSave = false,
  isSaving = false,
  saveDisabled = false,
  onSave,
}: TaxResultPanelProps) {
  return (
    <section className="tax-result-panel">
      <div className="tax-result-copy">
        <p className="tax-result-title">
          税金抵扣试算
        </p>
        <p>
          销项票 {outputCount} 张按开票情况只读计入，已认证结果 {certifiedCount} 张自动纳入，
          当前计划中额外勾选 {selectedPlanInputCount} 张未认证进项票参与试算。
        </p>
      </div>
      <div className="tax-result-figure">
        <span>
          {resultLabel}
        </span>
        <strong>
          {resultAmount}
        </strong>
        {canSave ? (
          <Button
            type="button"
            size="sm"
            isDisabled={saveDisabled || isSaving}
            isPending={isSaving}
            onPress={onSave}
          >
            {isSaving ? "保存中" : "保存计划"}
          </Button>
        ) : null}
      </div>
    </section>
  );
}
