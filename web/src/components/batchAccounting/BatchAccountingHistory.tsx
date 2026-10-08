import { Button, Label, ListBox, Select } from "@heroui/react";
import { useEffect, useState } from "react";

import { fetchBatchAccountingHistory, fetchBatchAccountingHistoryDetail } from "../../features/batchAccounting/api";
import type { BatchAccountingHistoryDetail, BatchAccountingHistoryResponse } from "../../features/batchAccounting/types";
import { formatMoney } from "../../features/money";
import AppDrawer from "../common/AppDrawer";
import { FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader, FinanceTablePagination, FinanceTableRow } from "../common/FinanceTable";
import StatePanel from "../common/StatePanel";
import "./batchAccountingHistory.css";

function money(value: string | null) { return value === null ? "—" : formatMoney(value); }

export default function BatchAccountingHistory() {
  const [year, setYear] = useState("all");
  const [page, setPage] = useState(1);
  const [availableYears, setAvailableYears] = useState<string[]>([]);
  const [reload, setReload] = useState(0);
  const [data, setData] = useState<BatchAccountingHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [relationId, setRelationId] = useState<string | null>(null);
  const [detail, setDetail] = useState<BatchAccountingHistoryDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(null); setData(null);
    fetchBatchAccountingHistory({ bankYear: year, page, pageSize: 50, signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) { setData(result); setAvailableYears(result.available_years); } })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "历史记录加载失败"); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [year, page, reload]);

  useEffect(() => {
    if (relationId === null) return;
    const controller = new AbortController();
    setDetail(null); setDetailError(null); setDetailLoading(true);
    fetchBatchAccountingHistoryDetail(relationId, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setDetail(result); })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setDetailError(failure instanceof Error ? failure.message : "历史详情加载失败"); })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [relationId]);

  const invoiceRows = detail === null ? [] : Array.from(new Map(detail.invoice_rows
    .flatMap((row) => row.etc_invoice_detail_rows ?? [row]).map((row) => [row.id, row])).values());

  return <section className="batch-history" aria-label="批量账务历史">
    <div className="batch-history__toolbar">
      <span>{data ? `已提交流水 ${data.summary.transaction_count} 笔 · ${data.summary.relation_count} 条记录` : "已提交流水"}</span>
      <Select className="batch-history__year" selectedKey={year} aria-label="流水年份" isDisabled={loading}
        onSelectionChange={(key) => { if (key !== null) { setYear(String(key)); setPage(1); } }}>
        <Label>流水年份</Label><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
        <Select.Popover><ListBox><ListBox.Item id="all" textValue="全部年份">全部年份</ListBox.Item>
          {availableYears.map((value) => <ListBox.Item id={value} key={value} textValue={value}>{value}</ListBox.Item>)}
        </ListBox></Select.Popover>
      </Select>
    </div>
    {loading ? <StatePanel compact tone="loading">正在加载历史记录</StatePanel> : null}
    {error ? <StatePanel tone="error">{error}<Button size="sm" variant="secondary" onPress={() => setReload((value) => value + 1)}>重试</Button></StatePanel> : null}
    {data ? <FinanceTable ariaLabel="批量账务历史记录" minWidth={760} selectableText
      footer={<FinanceTablePagination page={data.pagination.page} pageSize={data.pagination.page_size} total={data.pagination.total} onPageChange={setPage} />}>
      <FinanceTableHeader>
        <FinanceTableColumn isRowHeader columnRole="date">交易日期</FinanceTableColumn><FinanceTableColumn columnRole="account">银行账户</FinanceTableColumn>
        <FinanceTableColumn columnRole="identity">对方户名</FinanceTableColumn><FinanceTableColumn columnRole="amount">流水金额</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">流水 / OA</FinanceTableColumn><FinanceTableColumn columnRole="action">查看</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody renderEmptyState={() => "暂无已提交记录"}>
        {data.rows.map((row) => <FinanceTableRow key={row.relation_id} id={row.relation_id}>
          <FinanceTableCell columnRole="date">{row.trade_time || "—"}</FinanceTableCell>
          <FinanceTableCell columnRole="account">{row.bank_accounts.map((account) => `${account.bank_name} ${account.account_last4}`).join("、")}</FinanceTableCell>
          <FinanceTableCell columnRole="identity">{row.counterparty_names.join("、") || "—"}</FinanceTableCell>
          <FinanceTableCell columnRole="amount">{money(row.bank_amount)}</FinanceTableCell>
          <FinanceTableCell columnRole="quantity">{row.bank_count} / {row.oa_count}</FinanceTableCell>
          <FinanceTableCell columnRole="action"><Button size="sm" variant="ghost" aria-label={`查看 ${row.counterparty_names.join("、")} 详情`} onPress={() => { setDetail(null); setDetailError(null); setDetailLoading(true); setRelationId(row.relation_id); }}>详情</Button></FinanceTableCell>
        </FinanceTableRow>)}
      </FinanceTableBody>
    </FinanceTable> : null}
    <AppDrawer open={relationId !== null} title="批量账务详情" width={800} onClose={() => setRelationId(null)}>
      {detailLoading ? <StatePanel tone="loading">正在加载历史详情</StatePanel> : null}
      {detailError ? <StatePanel tone="error">{detailError}</StatePanel> : null}
      {detail ? <div className="batch-history__detail">
        {detail.missing_member_ids.length ? <StatePanel compact tone="error">部分历史记录不可用</StatePanel> : null}
        <dl className="batch-history__amounts"><div><dt>流水金额</dt><dd>{money(detail.bank_amount)}</dd></div><div><dt>OA 金额</dt><dd>{money(detail.oa_amount)}</dd></div><div><dt>差额</dt><dd>{money(detail.amount_delta)}</dd></div></dl>
        <h3>流水 · {detail.bank_rows.length} 笔</h3>
        <FinanceTable ariaLabel="历史流水" minWidth={680} selectableText>
          <FinanceTableHeader><FinanceTableColumn isRowHeader columnRole="date">交易日期</FinanceTableColumn><FinanceTableColumn columnRole="account">银行账户</FinanceTableColumn><FinanceTableColumn columnRole="identity">对方户名</FinanceTableColumn><FinanceTableColumn columnRole="direction">方向</FinanceTableColumn><FinanceTableColumn columnRole="amount">金额</FinanceTableColumn></FinanceTableHeader>
          <FinanceTableBody renderEmptyState={() => "无可用流水"}>{detail.bank_rows.map((row) => <FinanceTableRow key={row.id} id={row.id}>
            <FinanceTableCell columnRole="date">{row.trade_time}</FinanceTableCell><FinanceTableCell columnRole="account">{row.bank_name} {row.account_last4}</FinanceTableCell><FinanceTableCell columnRole="identity">{row.counterparty_name}</FinanceTableCell><FinanceTableCell columnRole="direction">{row.direction === "outflow" ? "支出" : row.direction === "inflow" ? "收入" : row.direction}</FinanceTableCell><FinanceTableCell columnRole="amount">{money(row.amount)}</FinanceTableCell>
          </FinanceTableRow>)}</FinanceTableBody>
        </FinanceTable>
        <h3>OA · {detail.oa_rows.length} 条</h3>
        <FinanceTable ariaLabel="历史关联 OA" minWidth={680} selectableText>
          <FinanceTableHeader><FinanceTableColumn isRowHeader columnRole="identity">申请人 / 日期</FinanceTableColumn><FinanceTableColumn columnRole="description">类型</FinanceTableColumn><FinanceTableColumn columnRole="description">项目 / 事由</FinanceTableColumn><FinanceTableColumn columnRole="amount">金额</FinanceTableColumn></FinanceTableHeader>
          <FinanceTableBody renderEmptyState={() => "无可用 OA"}>{detail.oa_rows.map((row) => <FinanceTableRow key={row.id} id={row.id}>
            <FinanceTableCell columnRole="identity">{row.applicant}<br />{row.apply_time}</FinanceTableCell><FinanceTableCell columnRole="description">{row.apply_type}<br />{row.expense_type}</FinanceTableCell><FinanceTableCell columnRole="description">{row.project_name}<br />{row.reason}</FinanceTableCell><FinanceTableCell columnRole="amount">{money(row.amount)}</FinanceTableCell>
          </FinanceTableRow>)}</FinanceTableBody>
        </FinanceTable>
        {invoiceRows.length ? <><h3>发票 · {invoiceRows.length} 张</h3><FinanceTable ariaLabel="历史关联发票" minWidth={680} selectableText>
          <FinanceTableHeader><FinanceTableColumn isRowHeader columnRole="identity">发票号码</FinanceTableColumn><FinanceTableColumn columnRole="date">开票日期</FinanceTableColumn><FinanceTableColumn columnRole="identity">销方 / 购方</FinanceTableColumn><FinanceTableColumn columnRole="amount">价税合计</FinanceTableColumn></FinanceTableHeader>
          <FinanceTableBody>{invoiceRows.map((row) => <FinanceTableRow key={row.id} id={row.id}>
            <FinanceTableCell columnRole="identity">{row.digital_invoice_no || row.invoice_no || "—"}{row.invoice_code ? <><br />{row.invoice_code}</> : null}</FinanceTableCell><FinanceTableCell columnRole="date">{row.issue_date}</FinanceTableCell><FinanceTableCell columnRole="identity">{row.seller_name}<br />{row.buyer_name}</FinanceTableCell><FinanceTableCell columnRole="amount">{money(row.total_with_tax)}</FinanceTableCell>
          </FinanceTableRow>)}</FinanceTableBody></FinanceTable></> : null}
        {detail.note ? <div className="batch-history__note"><h3>备注</h3><p>{detail.note}</p></div> : null}
      </div> : null}
    </AppDrawer>
  </section>;
}
