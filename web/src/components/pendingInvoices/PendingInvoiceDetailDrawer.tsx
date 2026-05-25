import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import type {
  PendingInvoiceObjectDetail,
  PendingInvoiceObjectDetailTarget,
  PendingInvoiceOaPrintLayout,
} from "../../features/pendingInvoices/types";
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
  const body = (
    <>
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
      {detail?.oaPrintLayout ? <OaPrintLayout layout={detail.oaPrintLayout} /> : null}
      {!detail?.oaPrintLayout ? detail?.sections.map((section) => (
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
      )) : null}
      {!loading && !error && detail && detail.sections.length === 0 && detail.detailAvailable !== false && !detail.oaPrintLayout ? (
        <Alert severity="info">暂无更多详情。</Alert>
      ) : null}
    </>
  );

  if (target?.kind === "oa") {
    return (
      <Dialog
        open={open}
        onClose={onClose}
        fullWidth
        maxWidth="xl"
        aria-labelledby="pending-invoice-oa-print-title"
        PaperProps={{ sx: { height: { xs: "100%", md: "calc(100vh - 96px)" } } }}
      >
        <DialogTitle id="pending-invoice-oa-print-title" sx={{ fontWeight: 500 }}>
          {title}
        </DialogTitle>
        <DialogContent dividers sx={{ bgcolor: "grey.50" }}>
          <Stack spacing={2}>{body}</Stack>
        </DialogContent>
        <DialogActions sx={{ justifyContent: "space-between", px: 3, py: 1.5 }}>
          <Button
            variant="contained"
            onClick={() => {
              if (typeof window !== "undefined" && typeof window.print === "function") {
                window.print();
              }
            }}
          >
            {detail?.oaPrintLayout?.downloadLabel || "打印下载"}
          </Button>
          <Button onClick={onClose} aria-label="关闭详情抽屉">关闭</Button>
        </DialogActions>
      </Dialog>
    );
  }

  return (
    <PendingInvoiceDrawerFrame
      open={open}
      title={title}
      subtitle={detail?.subtitle || target?.id}
      closeLabel="关闭详情抽屉"
      onClose={onClose}
    >
      {body}
    </PendingInvoiceDrawerFrame>
  );
}

function OaPrintLayout({ layout }: { layout: PendingInvoiceOaPrintLayout }) {
  return (
    <Box
      sx={{
        bgcolor: "background.paper",
        color: "text.primary",
        mx: "auto",
        p: { xs: 1.5, md: 2.5 },
        width: "100%",
        maxWidth: 1180,
      }}
    >
      <Typography component="h2" align="center" fontWeight={700} sx={{ fontSize: 18, mb: 1.5 }}>
        {layout.formTitle}
      </Typography>
      <Box
        component="table"
        sx={{
          borderCollapse: "collapse",
          tableLayout: "fixed",
          width: "100%",
          "& th, & td": {
            border: "1px solid",
            borderColor: "grey.900",
            px: 1,
            py: 0.55,
            fontSize: 13,
            lineHeight: 1.35,
            verticalAlign: "middle",
            wordBreak: "break-word",
          },
          "& th": {
            bgcolor: "grey.50",
            fontWeight: 500,
            textAlign: "right",
            width: 120,
          },
        }}
      >
        <tbody>
          {layout.fields.map((field) => (
            <tr key={field.label}>
              <th>{field.label}</th>
              <td>{formatValue(field.value)}</td>
            </tr>
          ))}
          {layout.approvals.length > 0 ? (
            <>
              <tr>
                <td colSpan={2} style={{ textAlign: "center", fontWeight: 700 }}>
                  申请提交/审批意见及评论
                </td>
              </tr>
              <tr>
                <td colSpan={2} style={{ padding: 0 }}>
                  <Box
                    sx={{
                      display: "grid",
                      gridTemplateColumns: { xs: "1fr", md: `repeat(${Math.min(layout.approvals.length, 3)}, minmax(0, 1fr))` },
                    }}
                  >
                    {layout.approvals.map((approval, index) => (
                      <Box
                        key={`${approval.title}-${index}`}
                        sx={{
                          minHeight: 96,
                          p: 1.5,
                          textAlign: "center",
                          borderLeft: { md: index === 0 ? 0 : "1px solid" },
                          borderTop: { xs: index === 0 ? 0 : "1px solid", md: 0 },
                          borderColor: "grey.900",
                        }}
                      >
                        <Typography fontWeight={500} sx={{ fontSize: 13 }}>{approval.title}</Typography>
                        {approval.lines.map((line) => (
                          <Typography key={line} sx={{ fontSize: 13 }}>{line}</Typography>
                        ))}
                        {approval.signature ? (
                          <Typography sx={{ mt: 1, fontFamily: "cursive", fontSize: 18 }}>{approval.signature}</Typography>
                        ) : null}
                      </Box>
                    ))}
                  </Box>
                </td>
              </tr>
            </>
          ) : null}
        </tbody>
      </Box>
    </Box>
  );
}

function formatValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}
