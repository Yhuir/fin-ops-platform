import ArrowForwardOutlinedIcon from "@mui/icons-material/ArrowForwardOutlined";
import PlaylistAddOutlinedIcon from "@mui/icons-material/PlaylistAddOutlined";
import RemoveCircleOutlineOutlinedIcon from "@mui/icons-material/RemoveCircleOutlineOutlined";
import UndoOutlinedIcon from "@mui/icons-material/UndoOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link as RouterLink } from "react-router-dom";

import AppDialog from "../components/common/AppDialog";
import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import {
  confirmEtcBatchSubmitted,
  createEtcOaDraft,
  fetchEtcInvoices,
  markEtcBatchNotSubmitted,
  revokeEtcSubmittedInvoices,
} from "../features/etc/api";
import { useBackgroundJobProgress } from "../features/backgroundJobs/BackgroundJobProgressProvider";
import { buildEtcOaDraftReviewUrl } from "../features/etc/oaNavigation";
import type { EtcInvoice, EtcInvoiceCounts, EtcInvoiceStatus, EtcOaDraftPayload } from "../features/etc/types";

const initialCounts: EtcInvoiceCounts = {
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

function attachmentLabel(invoice: EtcInvoice) {
  if (invoice.hasPdf && invoice.hasXml) {
    return "PDF/XML完整";
  }
  if (!invoice.hasPdf && !invoice.hasXml) {
    return "缺PDF/XML";
  }
  return invoice.hasPdf ? "缺XML" : "缺PDF";
}

function invoiceMatchesBasket(invoice: EtcInvoice, basket: EtcInvoice[]) {
  return basket.some((item) => item.id === invoice.id);
}

export default function EtcTicketManagementPage() {
  const { jobs } = useBackgroundJobProgress();
  const [activeStatus, setActiveStatus] = useState<EtcInvoiceStatus>("unsubmitted");
  const [month, setMonth] = useState("");
  const [plate, setPlate] = useState("");
  const [keyword, setKeyword] = useState("");
  const [counts, setCounts] = useState(initialCounts);
  const [invoices, setInvoices] = useState<EtcInvoice[]>([]);
  const [selectedInvoiceIds, setSelectedInvoiceIds] = useState<string[]>([]);
  const [basket, setBasket] = useState<EtcInvoice[]>([]);
  const [selectedBasketIds, setSelectedBasketIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [revokeDialogOpen, setRevokeDialogOpen] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [draftCreating, setDraftCreating] = useState(false);
  const [draftResult, setDraftResult] = useState<EtcOaDraftPayload | null>(null);
  const refreshedImportJobIdsRef = useRef<Set<string>>(new Set());

  const loadInvoices = async (signal?: AbortSignal) => {
    setLoading(true);
    setActionError(null);
    try {
      const payload = await fetchEtcInvoices({
        status: activeStatus,
        month,
        plate: plate.trim(),
        keyword: keyword.trim(),
        signal,
      });
      setCounts(payload.counts);
      setInvoices(payload.items);
      setSelectedInvoiceIds([]);
      setBasket((current) => current.filter((item) => item.status === "unsubmitted"));
      setSelectedBasketIds([]);
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setActionError(caught instanceof Error ? caught.message : "ETC发票加载失败。");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void loadInvoices(controller.signal);
    return () => controller.abort();
  }, [activeStatus, month, plate, keyword]);

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
    void loadInvoices();
  }, [jobs]);

  const basketTotal = useMemo(
    () => basket.reduce((sum, invoice) => sum + Number(invoice.totalAmount || 0), 0),
    [basket],
  );

  const selectedInvoices = useMemo(
    () => invoices.filter((invoice) => selectedInvoiceIds.includes(invoice.id)),
    [invoices, selectedInvoiceIds],
  );
  const hasBasketAttachmentGap = basket.some((invoice) => !invoice.hasPdf || !invoice.hasXml);

  const selectedSubmittedCount = selectedInvoices.filter((invoice) => invoice.status === "submitted").length;
  const canAddToBasket = activeStatus === "unsubmitted" && selectedInvoices.some((invoice) => invoice.status === "unsubmitted");

  const toggleInvoice = (invoiceId: string) => {
    setSelectedInvoiceIds((current) =>
      current.includes(invoiceId)
        ? current.filter((id) => id !== invoiceId)
        : [...current, invoiceId],
    );
  };

  const toggleBasketInvoice = (invoiceId: string) => {
    setSelectedBasketIds((current) =>
      current.includes(invoiceId)
        ? current.filter((id) => id !== invoiceId)
        : [...current, invoiceId],
    );
  };

  const addSelectedToBasket = () => {
    setBasket((current) => {
      const existingIds = new Set(current.map((invoice) => invoice.id));
      const additions = selectedInvoices.filter(
        (invoice) => invoice.status === "unsubmitted" && !existingIds.has(invoice.id),
      );
      return [...current, ...additions];
    });
  };

  const removeSelectedFromBasket = () => {
    setBasket((current) => current.filter((invoice) => !selectedBasketIds.includes(invoice.id)));
    setSelectedBasketIds([]);
  };

  const handleRevoke = async () => {
    const invoiceIds = selectedInvoices.filter((invoice) => invoice.status === "submitted").map((invoice) => invoice.id);
    if (invoiceIds.length === 0) {
      return;
    }
    setActionError(null);
    await revokeEtcSubmittedInvoices(invoiceIds);
    setRevokeDialogOpen(false);
    await loadInvoices();
  };

  const handleCreateDraft = async () => {
    setActionError(null);
    setDraftCreating(true);
    const draftWindow = window.open("about:blank", "_blank");
    if (draftWindow) {
      draftWindow.opener = null;
    }
    try {
      const result = await createEtcOaDraft(basket.map((invoice) => invoice.id));
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
    setBasket([]);
    setSelectedBasketIds([]);
    await loadInvoices();
  };

  const listTitle = activeStatus === "unsubmitted"
    ? `未提交发票 ${invoices.length} 张`
    : `已提交发票 ${invoices.length} 张`;

  return (
    <Box data-testid="etc-ticket-management-page">
      <PageScaffold
        className="etc-page"
        title="ETC票据管理"
        description="ETC批量提交"
        actions={
          <Button
            component={RouterLink}
            to="/imports?intent=etc_invoice"
            variant="outlined"
            endIcon={<ArrowForwardOutlinedIcon />}
          >
            去导入中心导入 ETC 发票
          </Button>
        }
      >
        <Stack spacing={2}>
          {actionError ? <StatePanel tone="error">{actionError}</StatePanel> : null}

          <Paper className="etc-filter-bar" variant="outlined" aria-label="ETC筛选">
            <FormControl size="small" sx={{ minWidth: 128 }}>
              <InputLabel id="etc-status-filter-label">状态筛选</InputLabel>
              <Select
                labelId="etc-status-filter-label"
                label="状态筛选"
                value={activeStatus}
                onChange={(event) => setActiveStatus(event.target.value as EtcInvoiceStatus)}
              >
                <MenuItem value="unsubmitted">未提交</MenuItem>
                <MenuItem value="submitted">已提交</MenuItem>
              </Select>
            </FormControl>
            <TextField
              label="月份筛选"
              size="small"
              type="month"
              value={month}
              InputLabelProps={{ shrink: true }}
              onChange={(event) => setMonth(event.target.value)}
            />
            <TextField
              label="车牌筛选"
              size="small"
              value={plate}
              placeholder="云ADA0381"
              onChange={(event) => setPlate(event.target.value)}
            />
            <TextField
              label="keyword 搜索"
              size="small"
              value={keyword}
              placeholder="发票号/销方/购方"
              onChange={(event) => setKeyword(event.target.value)}
            />
          </Paper>

          <Box className="etc-layout">
            <Box className="etc-left-layout" component="section" aria-label="ETC发票区">
              <Paper className="etc-status-groups" variant="outlined" aria-label="状态分组">
                <Button
                  type="button"
                  variant={activeStatus === "unsubmitted" ? "contained" : "outlined"}
                  onClick={() => setActiveStatus("unsubmitted")}
                >
                  未提交 {counts.unsubmitted}
                </Button>
                <Button
                  type="button"
                  variant={activeStatus === "submitted" ? "contained" : "outlined"}
                  onClick={() => setActiveStatus("submitted")}
                >
                  已提交 {counts.submitted}
                </Button>
              </Paper>

              <Paper className="etc-invoice-panel" variant="outlined">
                <Stack className="etc-panel-heading" direction={{ xs: "column", sm: "row" }} alignItems={{ xs: "stretch", sm: "center" }} spacing={1.5}>
                  <Typography component="h2" variant="h6" fontWeight={800}>
                    {listTitle}
                  </Typography>
                  {activeStatus === "unsubmitted" ? (
                    <Button
                      type="button"
                      variant="contained"
                      startIcon={<PlaylistAddOutlinedIcon />}
                      disabled={!canAddToBasket}
                      onClick={addSelectedToBasket}
                    >
                      加入提交篮子
                    </Button>
                  ) : (
                    <Button
                      type="button"
                      variant="outlined"
                      color="warning"
                      startIcon={<UndoOutlinedIcon />}
                      disabled={selectedSubmittedCount === 0}
                      onClick={() => setRevokeDialogOpen(true)}
                    >
                      撤销提交状态
                    </Button>
                  )}
                </Stack>
                {loading ? <StatePanel tone="loading" compact>正在加载ETC发票。</StatePanel> : null}
                {!loading && invoices.length === 0 ? <StatePanel tone="empty" compact>当前筛选下没有ETC发票。</StatePanel> : null}
                <List className="etc-invoice-list" aria-label="ETC发票列表" disablePadding>
                  {invoices.map((invoice) => {
                    const inBasket = invoiceMatchesBasket(invoice, basket);
                    return (
                      <ListItem
                        key={invoice.id}
                        className={`etc-ticket-row ${invoice.status}${inBasket ? " in-basket" : ""}`}
                        data-testid={`etc-invoice-row-${invoice.id}`}
                        disablePadding
                      >
                        <ListItemButton
                          selected={selectedInvoiceIds.includes(invoice.id)}
                          onClick={() => toggleInvoice(invoice.id)}
                        >
                          <Checkbox
                            edge="start"
                            inputProps={{ "aria-label": `选择发票 ${invoice.invoiceNumber}` }}
                            checked={selectedInvoiceIds.includes(invoice.id)}
                            tabIndex={-1}
                            disableRipple
                            onClick={(event) => event.stopPropagation()}
                            onChange={() => toggleInvoice(invoice.id)}
                          />
                          <ListItemText
                            primaryTypographyProps={{ component: "div" }}
                            secondaryTypographyProps={{ component: "div" }}
                            primary={
                              <Stack className="etc-row-title" direction="row" alignItems="center" spacing={1} flexWrap="wrap">
                                <Typography component="strong" fontWeight={800}>
                                  {invoice.invoiceNumber}
                                </Typography>
                                {inBasket ? <Chip label="已在篮子" size="small" color="primary" variant="outlined" /> : null}
                                <Chip label={attachmentLabel(invoice)} size="small" color={invoice.hasPdf && invoice.hasXml ? "success" : "warning"} variant="outlined" />
                              </Stack>
                            }
                            secondary={
                              <Box className="etc-row-fields">
                                <span>开票 {invoice.issueDate}</span>
                                <span>通行 {invoice.passageStartDate ?? "-"} 至 {invoice.passageEndDate ?? "-"}</span>
                                <span>车牌 {invoice.plateNumber}</span>
                                <span>金额 {formatMoney(invoice.totalAmount)}</span>
                                <span>税额 {formatMoney(invoice.taxAmount)}</span>
                                <span>销方 {invoice.sellerName}</span>
                                <span>购方 {invoice.buyerName}</span>
                              </Box>
                            }
                          />
                        </ListItemButton>
                      </ListItem>
                    );
                  })}
                </List>
              </Paper>
            </Box>

            <Paper className="etc-basket" variant="outlined" component="aside" aria-label="提交篮子">
              <Stack className="etc-panel-heading" direction={{ xs: "column", sm: "row" }} alignItems={{ xs: "stretch", sm: "center" }} spacing={1.5}>
                <Box>
                  <Typography component="h2" variant="h6" fontWeight={800}>
                    待提交 {basket.length} 张
                  </Typography>
                  <Typography color="text.secondary" fontWeight={800} variant="body2">
                    合计金额 {formatMoney(basketTotal)}
                  </Typography>
                </Box>
                <Button
                  type="button"
                  variant="outlined"
                  startIcon={<RemoveCircleOutlineOutlinedIcon />}
                  disabled={selectedBasketIds.length === 0}
                  onClick={removeSelectedFromBasket}
                >
                  移回未提交
                </Button>
              </Stack>
              {basket.length === 0 ? <StatePanel tone="empty" compact>提交篮子为空。</StatePanel> : null}
              {hasBasketAttachmentGap ? (
                <Alert severity="error">提交篮子存在缺PDF或缺XML的发票，补齐附件后才能创建 OA 草稿。</Alert>
              ) : null}
              <List className="etc-basket-list" aria-label="提交篮子发票列表" disablePadding>
                {basket.map((invoice) => (
                  <ListItem key={invoice.id} className="etc-basket-row" disablePadding>
                    <ListItemButton
                      selected={selectedBasketIds.includes(invoice.id)}
                      onClick={() => toggleBasketInvoice(invoice.id)}
                    >
                      <Checkbox
                        edge="start"
                        inputProps={{ "aria-label": `从提交篮子选择发票 ${invoice.invoiceNumber}` }}
                        checked={selectedBasketIds.includes(invoice.id)}
                        tabIndex={-1}
                        disableRipple
                        onClick={(event) => event.stopPropagation()}
                        onChange={() => toggleBasketInvoice(invoice.id)}
                      />
                      <ListItemText primary={invoice.invoiceNumber} secondary={attachmentLabel(invoice)} />
                      <Typography fontWeight={800}>{formatMoney(invoice.totalAmount)}</Typography>
                    </ListItemButton>
                  </ListItem>
                ))}
              </List>
              <Divider />
              <Button
                type="button"
                variant="contained"
                size="large"
                disabled={basket.length === 0 || hasBasketAttachmentGap}
                onClick={() => setCreateDialogOpen(true)}
              >
                提交OA支付申请
              </Button>
            </Paper>
          </Box>
        </Stack>

        <AppDialog
          open={revokeDialogOpen}
          title="撤销提交状态"
          description="只修改 fin-ops 内部 ETC 发票状态，不删除 OA 草稿，不撤回 OA 流程，不修改 OA 数据。"
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
              <Typography>请在 OA 中检查当前 ETC 批次草稿，确认无误后手动提交。</Typography>
              <Typography>批次号：{draftResult.etcBatchId}</Typography>
            </Stack>
          ) : (
            <Stack spacing={1}>
              <Typography>将创建 OA 支付申请草稿，并打开 OA 支付申请列表。</Typography>
              <Typography>app 不会自动提交 OA。</Typography>
              <Typography>需要在 OA 中检查当前 ETC 批次草稿并手动提交。</Typography>
            </Stack>
          )}
        </AppDialog>
      </PageScaffold>
    </Box>
  );
}
