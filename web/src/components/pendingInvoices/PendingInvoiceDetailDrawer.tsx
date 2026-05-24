import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import type { PendingInvoiceObjectDetail, PendingInvoiceObjectDetailTarget } from "../../features/pendingInvoices/types";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceDetailDrawerProps = {
  open: boolean;
  target: PendingInvoiceObjectDetailTarget | null;
  loadDetail: (target: PendingInvoiceObjectDetailTarget) => Promise<PendingInvoiceObjectDetail>;
  onClose: () => void;
};

const fallbackTitles: Record<PendingInvoiceObjectDetailTarget["kind"], string> = {
  bankTransaction: "流水详情",
  invoice: "发票详情",
  oa: "OA详情",
};

export default function PendingInvoiceDetailDrawer({
  open,
  target,
  loadDetail,
  onClose,
}: PendingInvoiceDetailDrawerProps) {
  const [detail, setDetail] = useState<PendingInvoiceObjectDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !target) {
      setDetail(null);
      setLoading(false);
      setError(null);
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError(null);
    setDetail(null);
    loadDetail(target)
      .then((payload) => {
        if (active) {
          setDetail(payload);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "详情加载失败");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [loadDetail, open, target]);

  const title = detail?.title || (target ? fallbackTitles[target.kind] : "详情");

  return (
    <PendingInvoiceDrawerFrame
      open={open}
      title={title}
      subtitle={detail?.subtitle || target?.id}
      closeLabel="关闭详情抽屉"
      onClose={onClose}
    >
      {loading ? (
        <Stack direction="row" spacing={1.25} alignItems="center">
          <CircularProgress aria-label="正在加载详情" size={22} />
          <Typography variant="body2" color="text.secondary">正在加载完整详情</Typography>
        </Stack>
      ) : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      {detail?.detailAvailable === false ? (
        <Alert severity="info">{detail.unavailableReason || "后端未返回可展示的完整详情。"}</Alert>
      ) : null}
      {detail?.sections.map((section) => (
        <Paper key={section.title} variant="outlined" sx={{ borderRadius: 1, p: 2 }}>
          <Typography variant="subtitle2" fontWeight={900} sx={{ mb: 1.25 }}>
            {section.title}
          </Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" }, gap: 1.5 }}>
            {section.fields.map((field) => (
              <Box key={`${section.title}-${field.label}`}>
                <Typography variant="caption" color="text.secondary" fontWeight={800}>
                  {field.label}
                </Typography>
                <Typography variant="body2" sx={{ mt: 0.25, wordBreak: "break-word" }}>
                  {formatValue(field.value)}
                </Typography>
              </Box>
            ))}
          </Box>
        </Paper>
      ))}
      {!loading && !error && detail && detail.sections.length === 0 && detail.detailAvailable !== false ? (
        <Alert severity="info">暂无更多详情。</Alert>
      ) : null}
    </PendingInvoiceDrawerFrame>
  );
}

function formatValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}
