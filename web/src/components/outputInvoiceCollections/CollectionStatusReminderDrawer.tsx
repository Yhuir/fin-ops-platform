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
  OutputInvoiceCollectionRow,
  OutputInvoiceCollectionStatusUpdateRequest,
  OutputInvoiceCollectionReminderUpdateRequest,
} from "../../features/outputInvoiceCollections/types";

type CollectionStatusReminderDrawerProps = {
  open: boolean;
  row: OutputInvoiceCollectionRow | null;
  onSaveStatus: (rowId: string, payload: OutputInvoiceCollectionStatusUpdateRequest) => Promise<void>;
  onSaveReminder: (rowId: string, payload: OutputInvoiceCollectionReminderUpdateRequest) => Promise<void>;
  onClose: () => void;
};

const statusOptions = [
  { code: "pending_collection", label: "待收款" },
  { code: "pending_red_invoice", label: "待冲红" },
  { code: "collected", label: "已收款" },
];

export default function CollectionStatusReminderDrawer({
  open,
  row,
  onSaveStatus,
  onSaveReminder,
  onClose,
}: CollectionStatusReminderDrawerProps) {
  const [statusCode, setStatusCode] = useState("");
  const [expectedCollectionDate, setExpectedCollectionDate] = useState("");
  const [statusNote, setStatusNote] = useState("");
  const [remindAt, setRemindAt] = useState("");
  const [reminderNote, setReminderNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !row) {
      return;
    }
    setStatusCode(row.collectionStatus.manualOverride?.statusCode || row.collectionStatus.code || "pending_collection");
    setExpectedCollectionDate(row.collectionStatus.expectedCollectionDate || "");
    setStatusNote(row.collectionStatus.manualOverride?.note || "");
    setRemindAt(toDatetimeLocal(row.collectionStatus.reminder?.remindAt || ""));
    setReminderNote(row.collectionStatus.reminder?.note || "");
    setError(null);
  }, [open, row]);

  const handleSubmit = async () => {
    if (!row) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onSaveStatus(row.id, {
        statusCode,
        expectedCollectionDate: expectedCollectionDate || undefined,
        note: statusNote,
        expectedVersion: row.collectionStatus.manualOverride?.version ?? 0,
      });
      if (remindAt) {
        await onSaveReminder(row.id, {
          remindAt: new Date(remindAt).toISOString(),
          channel: "oa",
          note: reminderNote,
        });
      }
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
        "aria-label": open ? "收款状态和提醒" : undefined,
        sx: { width: { xs: "100%", sm: 520 }, maxWidth: "100vw" },
      }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2.5, py: 1.5 }}>
          <div>
            <Typography component="h2" variant="h6" fontWeight={900}>收款状态</Typography>
            <Typography variant="caption" color="text.secondary">{row?.invoice.displayNo || row?.invoice.invoiceNo || ""}</Typography>
          </div>
          <IconButton aria-label="关闭收款状态抽屉" onClick={onClose}>
            <CloseOutlinedIcon />
          </IconButton>
        </Stack>
        <Divider />
        <Stack spacing={2} sx={{ p: 2.5 }}>
          {error ? <Alert severity="error">{error}</Alert> : null}
          <TextField select label="手动状态" size="small" value={statusCode} onChange={(event) => setStatusCode(event.target.value)}>
            {statusOptions.map((option) => (
              <MenuItem key={option.code} value={option.code}>{option.label}</MenuItem>
            ))}
          </TextField>
          <TextField
            label="预计收款日期"
            type="date"
            size="small"
            value={expectedCollectionDate}
            onChange={(event) => setExpectedCollectionDate(event.target.value)}
            InputLabelProps={{ shrink: true }}
          />
          <TextField label="状态备注" size="small" multiline minRows={3} value={statusNote} onChange={(event) => setStatusNote(event.target.value)} />
          <Divider />
          <TextField
            label="提醒时间"
            type="datetime-local"
            size="small"
            value={remindAt}
            onChange={(event) => setRemindAt(event.target.value)}
            InputLabelProps={{ shrink: true }}
          />
          <TextField label="提醒备注" size="small" multiline minRows={2} value={reminderNote} onChange={(event) => setReminderNote(event.target.value)} />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button onClick={onClose} disabled={submitting}>取消</Button>
            <Button variant="contained" onClick={handleSubmit} disabled={submitting || !statusCode}>保存</Button>
          </Stack>
        </Stack>
      </Stack>
    </Drawer>
  );
}

function toDatetimeLocal(value: string) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
