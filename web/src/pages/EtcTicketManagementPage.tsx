import ArrowForwardOutlinedIcon from "@mui/icons-material/ArrowForwardOutlined";
import UndoOutlinedIcon from "@mui/icons-material/UndoOutlined";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { Link as RouterLink } from "react-router-dom";

import AppDialog from "../components/common/AppDialog";
import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import { useBackgroundJobProgress } from "../features/backgroundJobs/BackgroundJobProgressProvider";
import {
  confirmEtcBatchSubmitted,
  createEtcOaDraftForBatch,
  fetchEtcBatchDetail,
  fetchEtcBatches,
  markEtcBatchNotSubmitted,
} from "../features/etc/api";
import { buildEtcOaDraftReviewUrl } from "../features/etc/oaNavigation";
import type { EtcBatchCounts, EtcBatchDetail, EtcBatchStatus, EtcBatchSummary, EtcInvoice, EtcOaDraftPayload } from "../features/etc/types";

const initialCounts: EtcBatchCounts = {
  unsubmitted: 0,
  submitted: 0,
};

function formatMoney(value: string | number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return String(value);
  }
  return parsed.toFixed(2);
}

function formatDateRange(startDate: string | null, endDate: string | null) {
  if (!startDate && !endDate) {
    return "-";
  }
  if (!endDate || startDate === endDate) {
    return startDate ?? endDate ?? "-";
  }
  if (!startDate) {
    return endDate;
  }
  return `${startDate} 至 ${endDate}`;
}

function formatShortDateRange(startDate: string | null, endDate: string | null) {
  const compact = (value: string | null) => {
    if (!value) {
      return "";
    }
    const [, month = "", day = ""] = value.split("-");
    return month && day ? `${Number(month)}.${Number(day)}` : value;
  };
  const start = compact(startDate);
  const end = compact(endDate);
  if (!start && !end) {
    return "未记录日期";
  }
  if (!end || start === end) {
    return start || end;
  }
  return `${start}-${end}`;
}

function attachmentLabel(invoice: EtcInvoice) {
  if (invoice.hasPdf && invoice.hasXml) {
    return "PDF/XML完整";
  }
  if (!invoice.hasPdf && !invoice.hasXml) {
    return "缺PDF/XML";
  }
  return invoice.hasPdf ? "缺XML" : "缺PDF";
}

function batchStatusLabel(status: EtcBatchStatus) {
  return status === "submitted" ? "已提交" : "未提交";
}

function batchOaLabel(batch: EtcBatchSummary) {
  const parts = [
    batch.linkedOaApplicant,
    batch.linkedOaApplyDate,
    batch.linkedOaAmount ? `OA ${formatMoney(batch.linkedOaAmount)}` : "",
  ].filter(Boolean);
  return parts.join(" / ");
}

const invoiceColumns: GridColDef<EtcInvoice>[] = [
  { field: "invoiceNumber", headerName: "发票号码", minWidth: 150, flex: 1.2 },
  { field: "issueDate", headerName: "开票日期", minWidth: 112, flex: 0.8 },
  {
    field: "passageDate",
    headerName: "通行日期",
    minWidth: 180,
    flex: 1.1,
    valueGetter: (_value, row) => formatDateRange(row.passageStartDate, row.passageEndDate),
  },
  { field: "plateNumber", headerName: "车牌", minWidth: 112, flex: 0.7 },
  { field: "sellerName", headerName: "销方", minWidth: 180, flex: 1.2 },
  {
    field: "totalAmount",
    headerName: "金额",
    type: "number",
    minWidth: 100,
    align: "right",
    headerAlign: "right",
    valueFormatter: (value) => formatMoney(value),
  },
  {
    field: "taxAmount",
    headerName: "税额",
    type: "number",
    minWidth: 92,
    align: "right",
    headerAlign: "right",
    valueFormatter: (value) => formatMoney(value),
  },
  {
    field: "attachments",
    headerName: "附件状态",
    minWidth: 118,
    flex: 0.7,
    valueGetter: (_value, row) => attachmentLabel(row),
  },
];

export default function EtcTicketManagementPage() {
  const { jobs } = useBackgroundJobProgress();
  const [activeStatus, setActiveStatus] = useState<EtcBatchStatus>("unsubmitted");
  const [month, setMonth] = useState("");
  const [plate, setPlate] = useState("");
  const [keyword, setKeyword] = useState("");
  const [counts, setCounts] = useState(initialCounts);
  const [batches, setBatches] = useState<EtcBatchSummary[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [batchDetail, setBatchDetail] = useState<EtcBatchDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [revokeDialogOpen, setRevokeDialogOpen] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [draftCreating, setDraftCreating] = useState(false);
  const [draftResult, setDraftResult] = useState<EtcOaDraftPayload | null>(null);
  const refreshedImportJobIdsRef = useRef<Set<string>>(new Set());

  const loadBatches = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setActionError(null);
    try {
      const payload = await fetchEtcBatches({
        status: activeStatus,
        month,
        plate: plate.trim(),
        keyword: keyword.trim(),
        signal,
      });
      setCounts(payload.counts);
      setBatches(payload.items);
      setSelectedBatchId((current) => {
        if (payload.items.some((batch) => batch.id === current)) {
          return current;
        }
        return payload.items[0]?.id ?? "";
      });
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setActionError(caught instanceof Error ? caught.message : "ETC批次加载失败。");
      }
    } finally {
      setLoading(false);
    }
  }, [activeStatus, keyword, month, plate]);

  useEffect(() => {
    const controller = new AbortController();
    void loadBatches(controller.signal);
    return () => controller.abort();
  }, [loadBatches]);

  useEffect(() => {
    if (!selectedBatchId) {
      setBatchDetail(null);
      return undefined;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    setActionError(null);
    void fetchEtcBatchDetail(selectedBatchId, controller.signal)
      .then((detail) => {
        if (!controller.signal.aborted) {
          setBatchDetail(detail);
        }
      })
      .catch((caught) => {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setActionError(caught instanceof Error ? caught.message : "ETC批次明细加载失败。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setDetailLoading(false);
        }
      });
    return () => controller.abort();
  }, [selectedBatchId]);

  useEffect(() => {
    const completedImportJobs = jobs.filter(
      (job) =>
        job.type === "etc_invoice_import"
        && (job.status === "succeeded" || job.status === "partial_success")
        && !refreshedImportJobIdsRef.current.has(job.jobId),
    );
    if (completedImportJobs.length === 0) {
      return;
    }
    completedImportJobs.forEach((job) => refreshedImportJobIdsRef.current.add(job.jobId));
    void loadBatches();
  }, [jobs, loadBatches]);

  const selectedBatch = useMemo(
    () => batchDetail ?? batches.find((batch) => batch.id === selectedBatchId) ?? null,
    [batchDetail, batches, selectedBatchId],
  );

  const invoiceRows = batchDetail?.invoiceItems ?? [];
  const canSubmitCurrentBatch = activeStatus === "unsubmitted" && Boolean(selectedBatchId) && !detailLoading;
  const canRevokeCurrentBatch = activeStatus === "submitted" && Boolean(selectedBatchId) && !detailLoading;

  const handleStatusChange = (_event: MouseEvent<HTMLElement>, nextStatus: EtcBatchStatus | null) => {
    if (!nextStatus || nextStatus === activeStatus) {
      return;
    }
    setActiveStatus(nextStatus);
    setSelectedBatchId("");
    setBatchDetail(null);
  };

  const handleCreateDraft = async () => {
    if (!selectedBatchId) {
      return;
    }
    setActionError(null);
    setDraftCreating(true);
    const draftWindow = window.open("about:blank", "_blank");
    if (draftWindow) {
      draftWindow.opener = null;
    }
    try {
      const result = await createEtcOaDraftForBatch(selectedBatchId);
      setDraftResult(result);
      if (!result.oaDraftUrl) {
        throw new Error("OA 草稿地址为空，请在 OA 系统中手动查找刚创建的草稿。");
      }
      const reviewUrl = buildEtcOaDraftReviewUrl(result.oaDraftUrl);
      if (draftWindow && !draftWindow.closed) {
        draftWindow.location.href = reviewUrl;
      } else {
        window.location.assign(reviewUrl);
      }
    } catch (caught) {
      if (draftWindow && !draftWindow.closed) {
        draftWindow.close();
      }
      setActionError(caught instanceof Error ? caught.message : "OA 草稿创建失败。");
    } finally {
      setDraftCreating(false);
    }
  };

  const handleResultConfirmation = async (submitted: boolean) => {
    if (!draftResult?.batchId) {
      return;
    }
    setActionError(null);
    if (submitted) {
      await confirmEtcBatchSubmitted(draftResult.batchId);
    } else {
      await markEtcBatchNotSubmitted(draftResult.batchId);
    }
    setCreateDialogOpen(false);
    setDraftResult(null);
    await loadBatches();
  };

  const handleRevoke = async () => {
    if (!selectedBatchId) {
      return;
    }
    setActionError(null);
    await markEtcBatchNotSubmitted(selectedBatchId);
    setRevokeDialogOpen(false);
    await loadBatches();
  };

  return (
    <Box data-testid="etc-ticket-management-page">
      <PageScaffold
        className="etc-page"
        title="ETC票据管理"
        actions={
          <Button
            component={RouterLink}
            to="/imports/etc-invoices"
            variant="outlined"
            endIcon={<ArrowForwardOutlinedIcon />}
          >
            导入 ETC 发票
          </Button>
        }
      >
        <Stack spacing={2}>
          {actionError ? <StatePanel tone="error">{actionError}</StatePanel> : null}

          <Paper className="etc-filter-bar" variant="outlined" aria-label="ETC筛选">
            <ToggleButtonGroup
              color="primary"
              size="small"
              exclusive
              value={activeStatus}
              onChange={handleStatusChange}
              aria-label="ETC批次状态"
            >
              <ToggleButton value="unsubmitted">
                未提交 {counts.unsubmitted}
              </ToggleButton>
              <ToggleButton value="submitted">
                已提交 {counts.submitted}
              </ToggleButton>
            </ToggleButtonGroup>
            <TextField
              label="月份"
              size="small"
              type="month"
              value={month}
              InputLabelProps={{ shrink: true }}
              onChange={(event) => setMonth(event.target.value)}
            />
            <TextField
              label="车牌"
              size="small"
              value={plate}
              placeholder="云ADA0381"
              onChange={(event) => setPlate(event.target.value)}
            />
            <TextField
              label="关键词"
              size="small"
              value={keyword}
              placeholder="批次号/OA/发票号"
              onChange={(event) => setKeyword(event.target.value)}
            />
            {activeStatus === "unsubmitted" ? (
              <Button
                type="button"
                variant="contained"
                disabled={!canSubmitCurrentBatch || draftCreating}
                onClick={() => setCreateDialogOpen(true)}
              >
                提交OA支付申请
              </Button>
            ) : null}
          </Paper>

          <Box className="etc-layout">
            <Paper className="etc-batch-list-panel" variant="outlined" component="section" aria-label="ETC批次列表区">
              <Stack className="etc-panel-heading" direction="row" alignItems="center" spacing={1.5}>
                <Typography component="h2" variant="h6" fontWeight={800}>
                  批次列表
                </Typography>
                <Chip label={`${batches.length} 批`} size="small" variant="outlined" />
              </Stack>
              {loading ? <StatePanel tone="loading" compact>正在加载ETC批次。</StatePanel> : null}
              {!loading && batches.length === 0 ? <StatePanel tone="empty" compact>当前筛选下没有ETC批次。</StatePanel> : null}
              <List className="etc-batch-list" aria-label="ETC批次列表" disablePadding>
                {batches.map((batch) => (
                  <ListItem
                    key={batch.id}
                    className={`etc-batch-row ${batch.status}`}
                    data-testid={`etc-batch-row-${batch.id}`}
                    disablePadding
                  >
                    <ListItemButton
                      selected={selectedBatchId === batch.id}
                      onClick={() => {
                        setBatchDetail(null);
                        setSelectedBatchId(batch.id);
                      }}
                    >
                      <ListItemText
                        primaryTypographyProps={{ component: "div" }}
                        secondaryTypographyProps={{ component: "div" }}
                        primary={
                          <Stack className="etc-row-title" direction="row" alignItems="center" spacing={1} flexWrap="wrap">
                            <Typography component="strong" fontWeight={800}>
                              {formatShortDateRange(batch.passageStartDate, batch.passageEndDate)}
                            </Typography>
                            <Chip
                              label={batchStatusLabel(batch.status)}
                              size="small"
                              color={batch.status === "submitted" ? "success" : "primary"}
                              variant="outlined"
                            />
                          </Stack>
                        }
                        secondary={
                          <Box className="etc-batch-fields">
                            <span>{batch.externalBatchId || batch.etcBatchId}</span>
                            <span>{batch.invoiceCount} 张 / {formatMoney(batch.totalAmount)} 元</span>
                            <span>{batch.plateCount} 个车牌</span>
                            {batch.status === "submitted" && batchOaLabel(batch) ? <span>{batchOaLabel(batch)}</span> : null}
                          </Box>
                        }
                      />
                    </ListItemButton>
                  </ListItem>
                ))}
              </List>
            </Paper>

            <Paper className="etc-batch-detail-panel" variant="outlined" component="section" aria-label="ETC批次详情">
              {!selectedBatch ? (
                <StatePanel tone="empty">请选择左侧批次。</StatePanel>
              ) : (
                <Stack spacing={2}>
                  <Stack className="etc-detail-heading" direction={{ xs: "column", md: "row" }} alignItems={{ xs: "stretch", md: "flex-start" }} spacing={1.5}>
                    <Box>
                      <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap">
                        <Typography component="h2" variant="h6" fontWeight={800}>
                          {selectedBatch.externalBatchId || selectedBatch.etcBatchId}
                        </Typography>
                        <Chip
                          label={batchStatusLabel(selectedBatch.status)}
                          size="small"
                          color={selectedBatch.status === "submitted" ? "success" : "primary"}
                          variant="outlined"
                        />
                      </Stack>
                      {selectedBatch.status === "submitted" && batchOaLabel(selectedBatch) ? (
                        <Typography color="text.secondary" variant="body2" fontWeight={700} sx={{ mt: 0.75 }}>
                          {batchOaLabel(selectedBatch)}
                        </Typography>
                      ) : null}
                    </Box>
                    {activeStatus === "submitted" ? (
                      <Button
                        type="button"
                        variant="outlined"
                        color="warning"
                        startIcon={<UndoOutlinedIcon />}
                        disabled={!canRevokeCurrentBatch}
                        onClick={() => setRevokeDialogOpen(true)}
                      >
                        撤销提交状态
                      </Button>
                    ) : null}
                  </Stack>

                  <Box className="etc-detail-metrics" aria-label="批次指标">
                    <Box>
                      <Typography variant="caption" color="text.secondary">总金额</Typography>
                      <Typography fontWeight={800}>{formatMoney(selectedBatch.totalAmount)}</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary">发票数</Typography>
                      <Typography fontWeight={800}>{selectedBatch.invoiceCount} 张</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary">开票日期</Typography>
                      <Typography fontWeight={800}>{formatDateRange(selectedBatch.issueStartDate, selectedBatch.issueEndDate)}</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary">通行日期</Typography>
                      <Typography fontWeight={800}>{formatDateRange(selectedBatch.passageStartDate, selectedBatch.passageEndDate)}</Typography>
                    </Box>
                  </Box>

                  <Box className="etc-plate-summary" aria-label="车牌汇总">
                    {selectedBatch.plateSummary.map((item) => (
                      <Box key={item.plateNumber} className="etc-plate-summary-item">
                        <Typography fontWeight={800}>{item.plateNumber || "未记录车牌"}</Typography>
                        <Typography color="text.secondary" variant="body2">{item.invoiceCount} 张</Typography>
                        <Typography fontWeight={800}>{formatMoney(item.totalAmount)}</Typography>
                      </Box>
                    ))}
                  </Box>

                  <Divider />

                  {detailLoading ? <StatePanel tone="loading" compact>正在加载批次明细。</StatePanel> : null}
                  <Box className="etc-invoice-grid" sx={{ height: 460, width: "100%" }}>
                    <DataGrid
                      key={selectedBatchId}
                      aria-label="ETC发票明细"
                      columns={invoiceColumns}
                      rows={invoiceRows}
                      loading={detailLoading}
                      disableRowSelectionOnClick
                      hideFooter={invoiceRows.length <= 100}
                      pageSizeOptions={[25, 50, 100]}
                      initialState={{ pagination: { paginationModel: { page: 0, pageSize: 25 } } }}
                      sx={{
                        height: "100%",
                        borderColor: "#d5dde8",
                        "& .MuiDataGrid-columnHeaders": {
                          backgroundColor: "#f4f7fb",
                        },
                        "& .MuiDataGrid-columnHeaderTitle": {
                          color: "#243b53",
                          fontWeight: 800,
                        },
                      }}
                    />
                  </Box>
                </Stack>
              )}
            </Paper>
          </Box>
        </Stack>

        <AppDialog
          open={revokeDialogOpen}
          title="撤销提交状态"
          description="只修改 fin-ops 内部 ETC 批次状态，不撤回 OA 流程，不修改 OA 数据。"
          onClose={() => setRevokeDialogOpen(false)}
          actions={
            <>
              <Button type="button" onClick={() => setRevokeDialogOpen(false)}>取消</Button>
              <Button type="button" variant="contained" color="warning" onClick={handleRevoke}>确认撤销</Button>
            </>
          }
        />

        <AppDialog
          open={createDialogOpen}
          title={draftResult ? "OA提交结果确认" : "创建OA支付申请草稿"}
          onClose={() => setCreateDialogOpen(false)}
          actions={
            draftResult ? (
              <>
                <Button type="button" variant="contained" onClick={() => handleResultConfirmation(true)}>确认已提交OA</Button>
                <Button type="button" onClick={() => handleResultConfirmation(false)}>未提交OA</Button>
              </>
            ) : (
              <>
                <Button type="button" onClick={() => setCreateDialogOpen(false)}>取消</Button>
                <Button type="button" variant="contained" onClick={handleCreateDraft} disabled={draftCreating}>
                  {draftCreating ? "正在创建..." : "确认创建草稿"}
                </Button>
              </>
            )
          }
        >
          {draftResult ? (
            <Stack spacing={1}>
              <Typography>OA 草稿已创建，并已打开支付申请列表。</Typography>
              <Typography>批次号：{draftResult.etcBatchId}</Typography>
            </Stack>
          ) : (
            <Stack spacing={1}>
              <Typography>将为当前 ETC 批次创建 OA 支付申请草稿。</Typography>
              <Typography>当前批次：{selectedBatch?.externalBatchId || selectedBatch?.etcBatchId || "-"}</Typography>
            </Stack>
          )}
        </AppDialog>
      </PageScaffold>
    </Box>
  );
}
