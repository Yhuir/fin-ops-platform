import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
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
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import type {
  CreateInputInvoiceUsageOaReverseBatchRequest,
  InputInvoiceUsageOaReverseBatch,
  InputInvoiceUsageOaReverseInvoice,
  InputInvoiceUsageOaReverseVersionedRequest,
  ManualInputInvoiceUsageOaReverseStatusRequest,
  RevokeInputInvoiceUsageOaReverseDraftRequest,
} from "../../features/inputInvoiceUsage/types";

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
  candidateInvoices?: InputInvoiceUsageOaReverseInvoice[];
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
  previewHash?: string;
  source?: string;
  invoiceCount: number;
  totalWithTax: string;
  groups: OaReversePreviewGroup[];
  candidateInvoices?: InputInvoiceUsageOaReverseInvoice[];
  warnings?: string[];
  canCreateDraft?: boolean;
  nextAction?: string;
  unavailableReason?: string;
  permissions?: {
    canCreateBatch?: boolean;
    canCreateDraft?: boolean;
    canRevoke?: boolean;
    canManualStatus?: boolean;
  };
};

type OaReverseWorkspaceDrawerProps = {
  open: boolean;
  sourceFilters: unknown[];
  selectedInvoiceIds: string[];
  loadPreview: (request: OaReversePreviewRequest) => Promise<OaReversePreviewPayload>;
  createBatch?: (request: CreateInputInvoiceUsageOaReverseBatchRequest) => Promise<InputInvoiceUsageOaReverseBatch>;
  loadBatch?: (batchId: string) => Promise<InputInvoiceUsageOaReverseBatch>;
  createDraft?: (batchId: string, request: InputInvoiceUsageOaReverseVersionedRequest) => Promise<InputInvoiceUsageOaReverseBatch>;
  refreshStatus?: (batchId: string, request: Pick<InputInvoiceUsageOaReverseVersionedRequest, "expectedVersion">) => Promise<InputInvoiceUsageOaReverseBatch>;
  revokeDraft?: (batchId: string, request: RevokeInputInvoiceUsageOaReverseDraftRequest) => Promise<InputInvoiceUsageOaReverseBatch>;
  manualStatus?: (batchId: string, request: ManualInputInvoiceUsageOaReverseStatusRequest) => Promise<InputInvoiceUsageOaReverseBatch>;
  onClose: () => void;
};

export default function OaReverseWorkspaceDrawer({
  open,
  sourceFilters,
  selectedInvoiceIds,
  loadPreview,
  createBatch,
  createDraft,
  refreshStatus,
  revokeDraft,
  manualStatus,
  onClose,
}: OaReverseWorkspaceDrawerProps) {
  const [preview, setPreview] = useState<OaReversePreviewPayload | null>(null);
  const [batch, setBatch] = useState<InputInvoiceUsageOaReverseBatch | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [revokeReason, setRevokeReason] = useState("");
  const [manualReason, setManualReason] = useState("");
  const request = useMemo(() => ({ sourceFilters, selectedInvoiceIds }), [sourceFilters, selectedInvoiceIds]);

  useEffect(() => {
    if (!open) {
      setPreview(null);
      setBatch(null);
      setLoading(false);
      setActionLoading(null);
      setError(null);
      setFeedback(null);
      setRevokeReason("");
      setManualReason("");
      return undefined;
    }

    let active = true;
    setLoading(true);
    setError(null);
    loadPreview(request)
      .then((payload) => {
        if (active) {
          setPreview(payload);
          setBatch(null);
          setFeedback(null);
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

  const candidateInvoices = preview ? invoicesFromPreview(preview) : [];
  const rejected = preview ? rejectedInvoices(preview) : [];
  const canCreateBatch = Boolean(
    preview
    && createBatch
    && preview.previewId
    && preview.canCreateDraft
    && candidateInvoices.length > 0
    && (preview.permissions?.canCreateBatch ?? true),
  );
  const canCreateDraft = Boolean(batch && createDraft && (batch.canCreateDraft ?? true) && !batch.oaDraftUrl);
  const canRefreshStatus = Boolean(batch && refreshStatus && (batch.canRefreshStatus ?? true));
  const canRevoke = Boolean(batch && revokeDraft && batch.oaDraftUrl && (batch.canRevoke ?? true));
  const canManualFallback = Boolean(batch && manualStatus && isManualFallbackStatus(batch.status, batch.oaDetectionStatus) && (batch.canManualStatus ?? true));

  const runBatchAction = (
    actionName: string,
    action: () => Promise<InputInvoiceUsageOaReverseBatch>,
    successMessage: string,
  ) => {
    setActionLoading(actionName);
    setError(null);
    setFeedback(null);
    action()
      .then((nextBatch) => {
        setBatch(nextBatch);
        setFeedback(successMessage);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : `${successMessage}失败。`);
      })
      .finally(() => setActionLoading(null));
  };

  const handleCreateBatch = () => {
    if (!preview?.previewId || !createBatch) {
      return;
    }
    runBatchAction(
      "createBatch",
      () => createBatch({
        previewId: preview.previewId ?? "",
        expectedPreviewHash: preview.previewHash,
        idempotencyKey: createIdempotencyKey("input-invoice-usage-oa-reverse-batch"),
        selectedInvoiceIds: candidateInvoices.map((invoice) => invoice.invoiceId),
        targetApplicantCode: firstTargetApplicantCode(preview),
      }),
      "本地批次已创建。",
    );
  };

  const handleCreateDraft = () => {
    if (!batch || !createDraft) {
      return;
    }
    runBatchAction(
      "createDraft",
      () => createDraft(batch.batchId, {
        expectedVersion: batch.version,
        idempotencyKey: createIdempotencyKey("input-invoice-usage-oa-reverse-draft"),
      }),
      "OA 草稿已创建，等待外部 OA 投影检测。",
    );
  };

  const handleRefreshStatus = () => {
    if (!batch || !refreshStatus) {
      return;
    }
    runBatchAction(
      "refreshStatus",
      () => refreshStatus(batch.batchId, { expectedVersion: batch.version }),
      "OA 状态已刷新。",
    );
  };

  const handleRevokeDraft = () => {
    if (!batch || !revokeDraft) {
      return;
    }
    runBatchAction(
      "revokeDraft",
      () => revokeDraft(batch.batchId, {
        expectedVersion: batch.version,
        reason: revokeReason,
        idempotencyKey: createIdempotencyKey("input-invoice-usage-oa-reverse-revoke"),
      }),
      "本地草稿绑定已释放。",
    );
  };

  const handleManualStatus = (decision: "submitted" | "not_submitted") => {
    if (!batch || !manualStatus) {
      return;
    }
    runBatchAction(
      `manualStatus:${decision}`,
      () => manualStatus(batch.batchId, {
        expectedVersion: batch.version,
        idempotencyKey: createIdempotencyKey("input-invoice-usage-oa-reverse-manual-status"),
        decision,
        reason: manualReason,
      }),
      "人工状态已记录。",
    );
  };

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
          {feedback ? <Alert severity="success">{feedback}</Alert> : null}
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
              {!preview.canCreateDraft ? (
                <Alert severity="info">
                  {preview.unavailableReason || preview.nextAction || "后端当前未允许创建 OA 草稿。"}
                </Alert>
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
                {rejected.length === 0 ? <Typography variant="body2" color="text.secondary">当前预览未返回不可提交发票。</Typography> : null}
                <Stack spacing={1}>
                  {rejected.map((item) => (
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
                      {candidateInvoices.map((invoice) => (
                        <TableRow key={invoice.invoiceId}>
                          <TableCell>{invoice.displayNo || invoice.invoiceNumber || invoice.invoiceId}</TableCell>
                          <TableCell>{invoice.sellerName || "-"}</TableCell>
                          <TableCell>{invoice.issueDate || "-"}</TableCell>
                          <TableCell align="right">{invoice.totalWithTax || "-"}</TableCell>
                          <TableCell>{invoice.paymentStatusLabel || "候选"}</TableCell>
                        </TableRow>
                      ))}
                      {candidateInvoices.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={5}>当前预览未返回候选发票。</TableCell>
                        </TableRow>
                      ) : null}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Section>
              <Section title="批次与 OA 草稿">
                {batch ? <BatchStatusPanel batch={batch} /> : <Typography variant="body2" color="text.secondary">尚未创建本地批次。</Typography>}
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  {canCreateBatch ? (
                    <Button
                      variant="contained"
                      disabled={Boolean(actionLoading)}
                      onClick={handleCreateBatch}
                    >
                      {actionLoading === "createBatch" ? "创建批次中..." : "创建本地批次"}
                    </Button>
                  ) : null}
                  {canCreateDraft ? (
                    <Button
                      variant="contained"
                      disabled={Boolean(actionLoading)}
                      onClick={handleCreateDraft}
                    >
                      {actionLoading === "createDraft" ? "创建草稿中..." : "创建 OA 草稿"}
                    </Button>
                  ) : null}
                  {batch?.oaDraftUrl ? (
                    <Button
                      variant="outlined"
                      component="a"
                      href={batch.oaDraftUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      打开 OA 草稿
                    </Button>
                  ) : null}
                  {canRefreshStatus ? (
                    <Button
                      variant="outlined"
                      disabled={Boolean(actionLoading)}
                      onClick={handleRefreshStatus}
                    >
                      {actionLoading === "refreshStatus" ? "刷新中..." : "刷新 OA 状态"}
                    </Button>
                  ) : null}
                </Stack>
                {canRevoke ? (
                  <Stack spacing={1}>
                    <TextField
                      label="撤销原因"
                      size="small"
                      value={revokeReason}
                      onChange={(event) => setRevokeReason(event.target.value)}
                    />
                    <Button
                      variant="outlined"
                      color="warning"
                      disabled={Boolean(actionLoading) || !revokeReason.trim()}
                      onClick={handleRevokeDraft}
                    >
                      {actionLoading === "revokeDraft" ? "撤销中..." : "撤销本地草稿绑定"}
                    </Button>
                  </Stack>
                ) : null}
                {canManualFallback ? (
                  <Stack spacing={1}>
                    <TextField
                      label="人工处理原因"
                      size="small"
                      value={manualReason}
                      onChange={(event) => setManualReason(event.target.value)}
                    />
                    <Stack direction="row" spacing={1}>
                      <Button
                        variant="outlined"
                        disabled={Boolean(actionLoading) || !manualReason.trim()}
                        onClick={() => handleManualStatus("submitted")}
                      >
                        标记已进入 OA
                      </Button>
                      <Button
                        variant="outlined"
                        disabled={Boolean(actionLoading) || !manualReason.trim()}
                        onClick={() => handleManualStatus("not_submitted")}
                      >
                        标记未进入 OA
                      </Button>
                    </Stack>
                  </Stack>
                ) : null}
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

function invoicesFromPreview(preview: OaReversePreviewPayload) {
  const byId = new Map<string, InputInvoiceUsageOaReverseInvoice>();
  for (const invoice of preview.candidateInvoices ?? []) {
    byId.set(invoice.invoiceId, invoice);
  }
  for (const group of preview.groups) {
    for (const invoice of group.candidateInvoices ?? []) {
      byId.set(invoice.invoiceId, {
        ...invoice,
        targetApplicantName: invoice.targetApplicantName || group.targetApplicantName,
      });
    }
    for (const invoiceId of group.candidateInvoiceIds ?? []) {
      if (!byId.has(invoiceId)) {
        byId.set(invoiceId, {
          invoiceId,
          invoiceNumber: invoiceId,
          displayNo: invoiceId,
          sellerName: "",
          issueDate: "",
          totalWithTax: "",
          paymentStatusLabel: "候选",
          targetApplicantName: group.targetApplicantName,
        });
      }
    }
  }
  return Array.from(byId.values());
}

function firstTargetApplicantCode(preview: OaReversePreviewPayload) {
  return preview.groups.find((group) => group.targetApplicantCode)?.targetApplicantCode ?? null;
}

function isManualFallbackStatus(status?: string | null, detectionStatus?: string | null) {
  return [
    status,
    detectionStatus,
  ].some((value) => value === "oa_detection_timeout" || value === "oa_detection_conflict" || value === "oa_detection_unavailable" || value === "oa_draft_failed");
}

function createIdempotencyKey(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}:${crypto.randomUUID()}`;
  }
  return `${prefix}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
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

function BatchStatusPanel({ batch }: { batch: InputInvoiceUsageOaReverseBatch }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
      <Stack spacing={1}>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
          <Typography variant="subtitle2" fontWeight={900}>{batch.batchId}</Typography>
          <Chip size="small" label={`版本 ${batch.version}`} variant="outlined" />
          <Chip size="small" label={batch.status || "未知状态"} />
          {batch.idempotentReplay ? <Chip size="small" label="幂等重放" variant="outlined" /> : null}
        </Stack>
        <Typography variant="body2" color="text.secondary">
          合计 {batch.totalWithTax || "-"}，目标申请人 {batch.targetApplicantName || batch.targetApplicantCode || "-"}
        </Typography>
        {batch.oaDraftId ? <Typography variant="body2">OA 草稿 ID：{batch.oaDraftId}</Typography> : null}
        {batch.oaDetectionStatus ? <Typography variant="body2">OA 检测状态：{batch.oaDetectionStatus}</Typography> : null}
        {batch.nextRunAt ? <Typography variant="body2">下次检测：{batch.nextRunAt}</Typography> : null}
      </Stack>
    </Paper>
  );
}
