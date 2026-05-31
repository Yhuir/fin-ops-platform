import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import type {
  OutputInvoiceCollectionRedRelationRequest,
  OutputInvoiceCollectionRow,
} from "../../features/outputInvoiceCollections/types";

type RedInvoiceRelationDrawerProps = {
  open: boolean;
  row: OutputInvoiceCollectionRow | null;
  onConfirm: (rowId: string, payload: OutputInvoiceCollectionRedRelationRequest) => Promise<void>;
  onClose: () => void;
};

export default function RedInvoiceRelationDrawer({
  open,
  row,
  onConfirm,
  onClose,
}: RedInvoiceRelationDrawerProps) {
  const [relatedInvoiceId, setRelatedInvoiceId] = useState("");
  const [relationType, setRelationType] = useState<"red_invoice" | "blue_invoice">("red_invoice");
  const [evidence, setEvidence] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setRelatedInvoiceId("");
    setRelationType("red_invoice");
    setEvidence("");
    setError(null);
  }, [open]);

  const handleSubmit = async () => {
    if (!row) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm(row.id, {
        relatedInvoiceId,
        relatedInvoiceIdentityKey: relatedInvoiceId ? `id:${relatedInvoiceId}` : undefined,
        relationType,
        evidence,
        confidence: "manual_confirmed",
      });
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        "aria-label": open ? "红蓝票关系" : undefined,
        sx: { width: { xs: "100%", sm: 560 }, maxWidth: "100vw" },
      }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2.5, py: 1.5 }}>
          <div>
            <Typography component="h2" variant="h6" fontWeight={900}>红蓝票关系</Typography>
            <Typography variant="caption" color="text.secondary">{row?.invoice.displayNo || row?.invoice.invoiceNo || ""}</Typography>
          </div>
          <IconButton aria-label="关闭红蓝票关系抽屉" onClick={onClose}>
            <CloseOutlinedIcon />
          </IconButton>
        </Stack>
        <Divider />
        <Stack spacing={2} sx={{ p: 2.5 }}>
          {error ? <Alert severity="error">{error}</Alert> : null}
          {row?.redInvoice.summaries.length ? (
            <Stack spacing={0.75}>
              <Typography variant="subtitle2" fontWeight={900}>已有依据</Typography>
              {row.redInvoice.summaries.map((item) => (
                <Typography key={`${item.id}:${item.source}`} variant="body2" color="text.secondary">
                  {item.invoiceNo || item.id} / {item.source || "auto"} / {item.evidence || item.reason}
                </Typography>
              ))}
            </Stack>
          ) : null}
          <TextField label="关联发票 ID" size="small" value={relatedInvoiceId} onChange={(event) => setRelatedInvoiceId(event.target.value)} />
          <TextField select label="关系类型" size="small" value={relationType} onChange={(event) => setRelationType(event.target.value as "red_invoice" | "blue_invoice")}>
            <MenuItem value="red_invoice">红字发票</MenuItem>
            <MenuItem value="blue_invoice">蓝字发票</MenuItem>
          </TextField>
          <TextField label="确认依据" size="small" multiline minRows={4} value={evidence} onChange={(event) => setEvidence(event.target.value)} />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button onClick={onClose} disabled={submitting}>取消</Button>
            <Button variant="contained" onClick={handleSubmit} disabled={submitting || !relatedInvoiceId || !evidence}>确认关系</Button>
          </Stack>
        </Stack>
      </Stack>
    </Drawer>
  );
}
