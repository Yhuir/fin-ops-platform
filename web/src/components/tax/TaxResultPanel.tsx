import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

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
    <Paper className="tax-result-panel" component="section" variant="outlined">
      <Stack className="tax-result-copy" spacing={0.75}>
        <Typography className="tax-result-title" fontWeight={800}>
          税金抵扣试算
        </Typography>
        <Typography color="text.secondary">
          销项票 {outputCount} 张按开票情况只读计入，已认证结果 {certifiedCount} 张自动纳入，
          当前计划中额外勾选 {selectedPlanInputCount} 张未认证进项票参与试算。
        </Typography>
      </Stack>
      <Stack className="tax-result-figure" spacing={0.5}>
        <Typography component="span" color="text.secondary">
          {resultLabel}
        </Typography>
        <Typography component="strong" variant="h5" fontWeight={900}>
          {resultAmount}
        </Typography>
        {canSave ? (
          <Button
            type="button"
            variant="contained"
            size="small"
            onClick={onSave}
            disabled={saveDisabled || isSaving}
          >
            {isSaving ? "保存中" : "保存计划"}
          </Button>
        ) : null}
      </Stack>
    </Paper>
  );
}
