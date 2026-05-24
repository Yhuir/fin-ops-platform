import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useEffect, useMemo, useState, type ReactNode } from "react";

export type OaReversePreviewRequest = {
  sourceFilters: unknown[];
  selectedInvoiceIds: string[];
};

export type OaReversePreviewGroup = {
  targetApplicantCode?: string | null;
  targetApplicantName: string;
  invoiceCount: number;
  totalWithTax: string;
  candidateInvoiceIds?: string[];
  rejectedInvoices?: OaReverseRejectedInvoice[];
};

export type OaReverseRejectedInvoice = {
  invoiceId: string;
  invoiceNumber?: string | null;
  reasonCode?: string | null;
  reason: string;
};

export type OaReversePreviewPayload = {
  previewId?: string;
  source?: string;
  invoiceCount: number;
  totalWithTax: string;
  groups: OaReversePreviewGroup[];
  warnings?: string[];
  canCreateDraft?: boolean;
  nextAction?: string;
};

type OaReverseWorkspaceDrawerProps = {
  open: boolean;
  sourceFilters: unknown[];
  selectedInvoiceIds: string[];
  loadPreview: (request: OaReversePreviewRequest) => Promise<OaReversePreviewPayload>;
  onClose: () => void;
};

export default function OaReverseWorkspaceDrawer({
  open,
  sourceFilters,
  selectedInvoiceIds,
  loadPreview,
  onClose,
}: OaReverseWorkspaceDrawerProps) {
  const [preview, setPreview] = useState<OaReversePreviewPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useMemo(() => ({ sourceFilters, selectedInvoiceIds }), [sourceFilters, selectedInvoiceIds]);

  useEffect(() => {
    if (!open) {
      setPreview(null);
      setLoading(false);
      setError(null);
      return undefined;
    }

    let active = true;
    setLoading(true);
    setError(null);
    loadPreview(request)
      .then((payload) => {
        if (active) {
          setPreview(payload);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "反提 OA 预览加载失败");
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
  }, [loadPreview, open, request]);

  return (
    <Drawer
      anchor="right"
      open={open}
      variant="persistent"
      onClose={onClose}
      transitionDuration={{ enter: 180, exit: 140 }}
      PaperProps={{
        "aria-label": open ? "以发票反提 OA 工作流" : undefined,
        role: "presentation",
        sx: { width: { xs: "100%", sm: "min(920px, 58vw)" }, maxWidth: "100vw" },
      }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2.5, py: 1.5 }}>
          <Box>
            <Typography component="h2" variant="h6" fontWeight={900}>以发票反提 OA</Typography>
            <Typography variant="caption" color="text.secondary">
              只读预览，候选数、合计和拒绝原因均以后端返回为准
            </Typography>
          </Box>
          <IconButton aria-label="关闭以发票反提 OA 工作流" onClick={onClose}>
            <CloseOutlinedIcon />
          </IconButton>
        </Stack>
        <Divider />
        <Stack spacing={2} sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 2.5 }}>
          {loading ? (
            <Stack direction="row" alignItems="center" spacing={1.25}>
              <CircularProgress aria-label="正在加载反提 OA 预览" size={22} />
              <Typography variant="body2" color="text.secondary">正在读取后端预览</Typography>
            </Stack>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {preview ? (
            <>
              <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" }, gap: 1.5 }}>
                <SummaryMetric label="候选发票数" value={String(preview.invoiceCount)} />
                <SummaryMetric label="候选价税合计" value={preview.totalWithTax} />
              </Box>
              {preview.warnings && preview.warnings.length > 0 ? (
                <Stack spacing={1}>
                  {preview.warnings.map((warning) => <Alert key={warning} severity="info">{warning}</Alert>)}
                </Stack>
              ) : null}
              <Section title="目标 OA 分组">
                {preview.groups.length === 0 ? <Typography variant="body2" color="text.secondary">暂无可提交分组。</Typography> : null}
                <Stack spacing={1}>
                  {preview.groups.map((group) => (
                    <Paper key={group.targetApplicantCode || group.targetApplicantName} variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                        <Typography variant="subtitle2" fontWeight={900}>{group.targetApplicantName}</Typography>
                        {group.targetApplicantCode ? <Chip size="small" variant="outlined" label={group.targetApplicantCode} /> : null}
                        <Chip size="small" label={`${group.invoiceCount} 张`} />
                        <Chip size="small" color="primary" variant="outlined" label={group.totalWithTax} />
                      </Stack>
                    </Paper>
                  ))}
                </Stack>
              </Section>
              <Section title="不可提交原因">
                {rejectedInvoices(preview).length === 0 ? <Typography variant="body2" color="text.secondary">当前预览未返回不可提交发票。</Typography> : null}
                <Stack spacing={1}>
                  {rejectedInvoices(preview).map((item) => (
                    <Alert key={item.invoiceId} severity="warning">
                      <Stack spacing={0.25}>
                        <Typography variant="body2" fontWeight={800}>{item.invoiceNumber || item.invoiceId}</Typography>
                        <Typography variant="body2">{item.reason}</Typography>
                      </Stack>
                    </Alert>
                  ))}
                </Stack>
              </Section>
              <Section title="候选发票清单">
                <TableContainer component={Paper} variant="outlined">
                  <Table size="small" aria-label="反提 OA 候选发票清单">
                    <TableHead>
                      <TableRow>
                        <TableCell>发票号码</TableCell>
                        <TableCell>销方</TableCell>
                        <TableCell>开票日期</TableCell>
                        <TableCell align="right">价税合计</TableCell>
                        <TableCell>状态</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {candidateInvoiceIds(preview).map((invoiceId) => (
                        <TableRow key={invoiceId}>
                          <TableCell>{invoiceId}</TableCell>
                          <TableCell>-</TableCell>
                          <TableCell>-</TableCell>
                          <TableCell align="right">-</TableCell>
                          <TableCell>候选</TableCell>
                        </TableRow>
                      ))}
                      {candidateInvoiceIds(preview).length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={5}>当前预览未返回候选发票。</TableCell>
                        </TableRow>
                      ) : null}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Section>
            </>
          ) : null}
        </Stack>
      </Stack>
    </Drawer>
  );
}

function rejectedInvoices(preview: OaReversePreviewPayload) {
  const byId = new Map<string, OaReverseRejectedInvoice>();
  for (const group of preview.groups) {
    for (const item of group.rejectedInvoices ?? []) {
      byId.set(item.invoiceId, item);
    }
  }
  return Array.from(byId.values());
}

function candidateInvoiceIds(preview: OaReversePreviewPayload) {
  const ids = new Set<string>();
  for (const group of preview.groups) {
    for (const invoiceId of group.candidateInvoiceIds ?? []) {
      ids.add(invoiceId);
    }
  }
  return Array.from(ids);
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
      <Typography variant="caption" color="text.secondary" fontWeight={800}>{label}</Typography>
      <Typography variant="h6" fontWeight={900}>{value}</Typography>
    </Paper>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2" fontWeight={900}>{title}</Typography>
      {children}
    </Stack>
  );
}
