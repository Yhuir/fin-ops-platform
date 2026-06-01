import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useMemo, useState } from "react";

import type {
  OutputInvoiceCollectionRedRelationRequest,
  OutputInvoiceCollectionRow,
} from "../../features/outputInvoiceCollections/types";

type RedInvoiceRelationDrawerProps = {
  open: boolean;
  row: OutputInvoiceCollectionRow | null;
  candidateRows: OutputInvoiceCollectionRow[];
  onConfirm: (rowId: string, payload: OutputInvoiceCollectionRedRelationRequest) => Promise<void>;
  onRevoke: (relationId: string) => Promise<void>;
  onClose: () => void;
};

export default function RedInvoiceRelationDrawer({
  open,
  row,
  candidateRows,
  onConfirm,
  onRevoke,
  onClose,
}: RedInvoiceRelationDrawerProps) {
  const [search, setSearch] = useState("");
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [relationType, setRelationType] = useState<"red_invoice" | "blue_invoice">("red_invoice");
  const [evidence, setEvidence] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setSearch("");
    setSelectedCandidateId("");
    setRelationType("red_invoice");
    setEvidence("");
    setError(null);
  }, [open]);

  const candidates = useMemo(() => {
    const currentIdentity = new Set([row?.id, row?.invoiceId, row?.invoiceIdentityKey].filter(Boolean));
    const keyword = search.trim().toLowerCase();
    return candidateRows
      .filter((candidate) => !currentIdentity.has(candidate.id) && !currentIdentity.has(candidate.invoiceId) && !currentIdentity.has(candidate.invoiceIdentityKey))
      .filter((candidate) => {
        if (!keyword) {
          return true;
        }
        const searchable = [
          candidate.invoice.displayNo,
          candidate.invoice.invoiceNo,
          candidate.invoice.buyerName,
          candidate.invoice.totalWithTax,
          candidate.invoice.issueDate,
          candidate.invoiceId,
        ].join(" ").toLowerCase();
        return searchable.includes(keyword);
      })
      .slice(0, 20);
  }, [candidateRows, row, search]);
  const selectedCandidate = candidates.find((candidate) => candidate.id === selectedCandidateId)
    ?? candidateRows.find((candidate) => candidate.id === selectedCandidateId)
    ?? null;

  const handleSubmit = async () => {
    if (!row) {
      return;
    }
    if (!selectedCandidate) {
      setError("请选择关联发票");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm(row.id, {
        relatedInvoiceId: selectedCandidate.invoiceId,
        relatedInvoiceIdentityKey: selectedCandidate.invoiceIdentityKey || (selectedCandidate.invoiceId ? `id:${selectedCandidate.invoiceId}` : undefined),
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

  const handleRevoke = async (relationId: string) => {
    setSubmitting(true);
    setError(null);
    try {
      await onRevoke(relationId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "撤销失败");
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
                <Stack key={`${item.id}:${item.source}`} direction="row" spacing={1} alignItems="center" justifyContent="space-between">
                  <Typography variant="body2" color="text.secondary">
                    {item.invoiceNo || item.id} / {item.source || "auto"} / {item.evidence || item.reason}
                  </Typography>
                  {item.source === "manual" && item.relationId ? (
                    <Button
                      size="small"
                      color="warning"
                      variant="outlined"
                      disabled={submitting}
                      onClick={() => handleRevoke(item.relationId || "")}
                    >
                      撤销人工关系 {item.invoiceNo || item.id}
                    </Button>
                  ) : null}
                </Stack>
              ))}
            </Stack>
          ) : null}
          <TextField
            label="搜索关联发票"
            size="small"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="按发票号、购方、金额或日期搜索"
          />
          <RadioGroup
            aria-label="关联发票候选"
            value={selectedCandidateId}
            onChange={(event) => setSelectedCandidateId(event.target.value)}
          >
            <Stack spacing={1} sx={{ maxHeight: 240, overflow: "auto" }}>
              {candidates.length === 0 ? (
                <Typography variant="body2" color="text.secondary">暂无匹配候选发票。</Typography>
              ) : null}
              {candidates.map((candidate) => {
                const displayNo = candidate.invoice.displayNo || candidate.invoice.invoiceNo || candidate.invoiceId;
                const label = `${displayNo} / ${candidate.invoice.buyerName || "购方为空"} / ${candidate.invoice.totalWithTax || "金额为空"} / ${candidate.invoice.issueDate || "日期为空"}`;
                return (
                  <FormControlLabel
                    key={candidate.id}
                    value={candidate.id}
                    control={<Radio size="small" />}
                    label={label}
                  />
                );
              })}
            </Stack>
          </RadioGroup>
          <TextField select label="关系类型" size="small" value={relationType} onChange={(event) => setRelationType(event.target.value as "red_invoice" | "blue_invoice")}>
            <MenuItem value="red_invoice">红字发票</MenuItem>
            <MenuItem value="blue_invoice">蓝字发票</MenuItem>
          </TextField>
          <TextField label="确认依据" size="small" multiline minRows={4} value={evidence} onChange={(event) => setEvidence(event.target.value)} />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button onClick={onClose} disabled={submitting}>取消</Button>
            <Button variant="contained" onClick={handleSubmit} disabled={submitting || !selectedCandidate || !evidence.trim()}>确认关系</Button>
          </Stack>
        </Stack>
      </Stack>
    </Drawer>
  );
}
