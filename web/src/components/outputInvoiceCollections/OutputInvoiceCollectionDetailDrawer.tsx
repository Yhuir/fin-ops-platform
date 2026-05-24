import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

export type OutputInvoiceCollectionDetailTarget = {
  kind: "invoice" | "bank" | "relationList";
  id: string;
  rowId?: string;
};

export type OutputInvoiceCollectionDetailField = {
  label: string;
  value: string | number | null | undefined;
};

export type OutputInvoiceCollectionDetailSection = {
  title: string;
  fields: OutputInvoiceCollectionDetailField[];
};

export type OutputInvoiceCollectionDetailPayload = {
  title?: string;
  subtitle?: string;
  detailAvailable?: boolean;
  unavailableReason?: string;
  sections: OutputInvoiceCollectionDetailSection[];
};

type OutputInvoiceCollectionDetailDrawerProps = {
  open: boolean;
  target: OutputInvoiceCollectionDetailTarget | null;
  loadDetail: (target: OutputInvoiceCollectionDetailTarget) => Promise<OutputInvoiceCollectionDetailPayload>;
  onClose: () => void;
};

const fallbackTitles: Record<OutputInvoiceCollectionDetailTarget["kind"], string> = {
  invoice: "发票详情",
  bank: "银行流水详情",
  relationList: "关联明细",
};

export default function OutputInvoiceCollectionDetailDrawer({
  open,
  target,
  loadDetail,
  onClose,
}: OutputInvoiceCollectionDetailDrawerProps) {
  const [detail, setDetail] = useState<OutputInvoiceCollectionDetailPayload | null>(null);
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

  const title = detail?.title ?? (target ? fallbackTitles[target.kind] : "详情");

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      transitionDuration={{ enter: 180, exit: 140 }}
      PaperProps={{
        "aria-label": "销项发票收款情况详情",
        sx: { width: { xs: "100%", sm: 720 }, maxWidth: "100vw" },
      }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2.5, py: 1.5 }}>
          <Box>
            <Typography component="h2" variant="h6" fontWeight={900}>{title}</Typography>
            {detail?.subtitle || target?.id ? (
              <Typography variant="caption" color="text.secondary">
                {detail?.subtitle ?? target?.id}
              </Typography>
            ) : null}
          </Box>
          <IconButton aria-label="关闭详情抽屉" onClick={onClose}>
            <CloseOutlinedIcon />
          </IconButton>
        </Stack>
        <Divider />
        <Stack spacing={2} sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 2.5 }}>
          {loading ? (
            <Stack direction="row" alignItems="center" spacing={1.25}>
              <CircularProgress aria-label="正在加载详情" size={22} />
              <Typography variant="body2" color="text.secondary">正在加载完整详情</Typography>
            </Stack>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {detail?.detailAvailable === false ? (
            <Alert severity="info">
              <Typography variant="subtitle2" fontWeight={900}>关联详情不可用</Typography>
              <Typography variant="body2">{detail.unavailableReason ?? "后端未返回可展示的完整关联详情。"}</Typography>
            </Alert>
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
                      {formatDetailValue(field.value)}
                    </Typography>
                  </Box>
                ))}
              </Box>
            </Paper>
          ))}
          {!loading && !error && detail && detail.sections.length === 0 && detail.detailAvailable !== false ? (
            <Alert severity="info">暂无更多详情。</Alert>
          ) : null}
        </Stack>
      </Stack>
    </Drawer>
  );
}

function formatDetailValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}
