import BankSplitChips from "../../features/bankSplits/BankSplitChips";
import {
  Checkbox,
  ListBox,
  PopoverContent,
  PopoverDialog,
  PopoverRoot,
  PopoverTrigger,
  Select,
} from "@heroui/react";
import { ArrowUpDown, Filter, Info } from "lucide-react";
import type { MutableRefObject, ReactNode } from "react";
import { Fragment, useMemo, useState } from "react";

import {
  EmptyValue,
  FinanceDirectionTag,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTablePagination,
  FinanceTableRow,
  FinanceStatusTag,
  type FinanceTone,
} from "../common/FinanceTable";
import type { InputInvoiceUsageFilterValue } from "../inputInvoiceUsage/InputInvoiceUsageFilterMenu";
import type {
  OaPendingPaymentDetailTarget,
  OaPendingPaymentFieldConfig,
  OaPendingPaymentFilter,
  OaPendingPaymentFilterOption,
  OaPendingPaymentRow,
  OaPendingPaymentSortDirection,
} from "../../features/oaPendingPayments/types";
import { formatMoney } from "../../features/money";
import { formatDateTimeText } from "../../features/dateTime";
import { RelationCountButton } from "../common/RelationCountButton";
import RelationRowsMotion from "../common/RelationRowsMotion";
import { useRelationExpansion, useRelationRowExpansion } from "../../hooks/useRelationExpansion";
import { oaPendingDisplayRows, oaPendingMembers, type OaPendingDisplayRow } from "../../features/oaPendingPayments/relationExpansion";
import OaWorkflowStatusChip from "../common/OaWorkflowStatusChip";
import BankAccountValue from "../BankAccountValue";

type OaColumnFilterValue = InputInvoiceUsageFilterValue;

type OaPendingPaymentsTableProps = {
  rows: OaPendingPaymentRow[];
  loading?: boolean;
  page: number;
  pageSize: number;
  total: number;
  oaCount?: number;
  filterConfigs: OaPendingPaymentFieldConfig[];
  filterOptions: Record<string, OaPendingPaymentFilterOption[]>;
  filters: OaPendingPaymentFilter[];
  onFilterApply: (filter: OaColumnFilterValue) => void;
  onFilterClear: (field: string) => void;
  onSortChange: (field: string, direction?: OaPendingPaymentSortDirection) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onOpenDetail: (target: OaPendingPaymentDetailTarget) => void;
  selectedOaRowIds?: Set<string>;
  onToggleOaSelection?: (row: OaPendingPaymentRow) => void;
  emptyStateMessage?: string;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
};

type OaColumnFilterField = {
  field: string;
  label: string;
};

type OaPendingPaymentColumn = {
  id: string;
  label: string;
  align?: "left" | "right";
  filterFields?: OaColumnFilterField[];
  sortField?: string;
  sortLabel?: string;
  group: "oa" | "status" | "bank" | "invoice";
};

type HeaderControlConfig = {
  label: string;
  filterFields?: OaColumnFilterField[];
  filterLabel?: string;
  sortField?: string;
  sortLabel?: string;
};

const columns: OaPendingPaymentColumn[] = [
  {
    id: "oa",
    label: "OA",
    filterFields: [
      { field: "oa_applicant", label: "OA申请人" },
      { field: "oa_application_type", label: "类型" },
      { field: "oa_project_name", label: "项目名称" },
    ],
    sortField: "oa_applicant",
    group: "oa",
  },
  {
    id: "paymentStatus",
    label: "支付状态",
    filterFields: [{ field: "payment_status", label: "支付状态" }],
    sortField: "payment_status",
    group: "status",
  },
  {
    id: "bank",
    label: "流水",
    filterFields: [
      { field: "bank_counterparty_name", label: "对方户名" },
      { field: "bank_account", label: "银行账户" },
      { field: "bank_direction", label: "收支" },
    ],
    sortField: "bank_trade_time",
    sortLabel: "交易时间",
    group: "bank",
  },
  {
    id: "invoice",
    label: "发票",
    filterFields: [
      { field: "seller_name", label: "发票方" },
      { field: "invoice_date", label: "开票日期" },
    ],
    sortField: "invoice_date",
    sortLabel: "开票日期",
    group: "invoice",
  },
];

function cx(...values: Array<string | false | undefined>) {
  return values.filter(Boolean).join(" ");
}

export default function OaPendingPaymentsTable({
  rows,
  loading = false,
  page,
  pageSize,
  total,
  oaCount,
  filterConfigs,
  filterOptions,
  filters,
  onFilterApply,
  onFilterClear,
  onSortChange,
  onPageChange,
  onPageSizeChange,
  onOpenDetail,
  selectedOaRowIds = new Set(),
  onToggleOaSelection,
  emptyStateMessage = "暂无 OA 待付款核对数据",
  tableWrapRef,
}: OaPendingPaymentsTableProps) {
  const expansion = useRelationExpansion(rows);
  const configsByField = useMemo(() => new Map(filterConfigs.map((config) => [config.field, config])), [filterConfigs]);

  return (
    <div
      className="finance-page-table-frame oa-pending-payments-table-frame"
      data-testid="oa-pending-payments-table-frame"
      aria-busy={loading}
    >
      <FinanceTable
        ariaLabel="OA待付款核对表格"
        className="oa-pending-payments-table oa-pending-payments-table-shell"
        footer={(
          <PaginationControls
            onPageChange={onPageChange}
            onPageSizeChange={onPageSizeChange}
            page={page}
            pageSize={pageSize}
            total={total}
            oaCount={oaCount}
          />
        )}
        minWidth={1320}
        selectableText
        scrollMode="contained"
        scrollRef={tableWrapRef}
      >
          <FinanceTableHeader>
            {columns.map((column) => (
              <FinanceTableColumn
                className={cx(
                  "oa-pending-payments-table-sub-header",
                  `oa-pending-payments-table-sub-header--${column.group}`,
                  column.align === "right" && "oa-pending-payments-table-cell--amount",
                  ["status", "bank", "invoice"].includes(column.group) && firstColumnInGroup(column.id) && "oa-pending-payments-table-cell--left-border",
                )}
                columnRole={column.group === "status" ? "status" : "identity"}
                id={column.id}
                isRowHeader={column.id === "oa"}
                key={column.id}
              >
                <span className={`oa-pending-payments-table-column-heading oa-pending-payments-table-column-heading--${column.group}`}>
                  <span className="oa-pending-payments-table-column-group">{column.label}</span>
                  <GroupedSubHeader
                    column={column}
                    configsByField={configsByField}
                    filterOptions={filterOptions}
                    filters={filters}
                    onFilterApply={onFilterApply}
                    onFilterClear={onFilterClear}
                    onSortChange={onSortChange}
                  />
                </span>
              </FinanceTableColumn>
            ))}
          </FinanceTableHeader>
          <FinanceTableBody>
            {rows.length === 0 ? (
              <FinanceTableRow id="oa-pending-payments-empty">
                <FinanceTableCell className="oa-pending-payments-table-state-cell" columnRole="identity">{emptyStateMessage}</FinanceTableCell>
                <FinanceTableCell columnRole="status"><EmptyValue /></FinanceTableCell>
                <FinanceTableCell columnRole="identity"><EmptyValue /></FinanceTableCell>
                <FinanceTableCell columnRole="identity"><EmptyValue /></FinanceTableCell>
              </FinanceTableRow>
            ) : rows.map((row) => <OaPendingTableRow key={row.id} row={row} expansion={expansion} loading={loading} selectedOaRowIds={selectedOaRowIds} onToggleOaSelection={onToggleOaSelection} onOpenDetail={onOpenDetail} />)}
          </FinanceTableBody>
      </FinanceTable>
    </div>
  );
}

function OaPendingTableRow({
  row, expansion, loading, selectedOaRowIds, onToggleOaSelection, onOpenDetail,
}: Pick<OaPendingPaymentsTableProps, 'onToggleOaSelection' | 'onOpenDetail'> & {
  row: OaPendingPaymentRow;
  expansion: ReturnType<typeof useRelationExpansion>;
  loading: boolean;
  selectedOaRowIds: Set<string>;
}) {
  const presence = useRelationRowExpansion(row.id, expansion);
  const members = oaPendingMembers(row);
  const ownerOaId = !row.oa.hasMultiple && (row.oa.relationCount ?? 1) <= 1 && members.oa.length === 1
    ? row.oa.primaryOaId || row.oa.id : null;
  const displayRows = oaPendingDisplayRows(presence.view ?? 'oa', members, ownerOaId);
  const selectable = Boolean(onToggleOaSelection) && canSelectOa(row);
  const rowOaIds = oaRowIds(row);
  const selected = rowOaIds.length > 0 && rowOaIds.every(id => selectedOaRowIds.has(id));
  const outflowSummaries = row.bankTransaction.summaries;
  const outflowCount = new Set(outflowSummaries?.map(member => member.parent_row_id || member.bankTransactionId)).size;
  const bankComplete = outflowSummaries ? outflowCount === row.bankTransaction.original_transaction_count
    : row.bankTransaction.original_transaction_count <= 1 && !row.bankTransaction.hasMultiple;
  const oaComplete = row.oa.hasMultiple || (row.oa.relationCount ?? 0) > 1
    ? row.oa.relationCount === members.oa.length : members.oa.length === 1;
  const bankIdsComplete = [...(outflowSummaries ?? []), ...(row.bankTransaction.nonOutflowRelationEdges ?? [])]
    .every(member => Boolean(member.bankTransactionId));
  const complete = oaComplete && bankIdsComplete
    && bankComplete && row.invoice.relationCount === members.invoice.length
    && Object.values(members).every(items => items.every(item => Boolean(item.id))
      && new Set(items.map(item => item.id)).size === items.length);
  if (!complete) return <FinanceTableRow id={row.id} className="oa-pending-payments-table-row">
    <FinanceTableCell columnRole="identity"><span role="alert">关系摘要不完整</span></FinanceTableCell>
    {Array.from({ length: 3 }, (_, index) => <FinanceTableCell columnRole="description" key={index}><EmptyValue /></FinanceTableCell>)}
  </FinanceTableRow>;
  const renderRow = (display: OaPendingDisplayRow, index: number) => {
    const oa = display.oa;
    const bank = display.bank;
    const invoice = display.invoice;
    const countButton = (kind: 'oa' | 'bank' | 'invoice') => index === 0 && members[kind].length > 1
      ? <RelationCountButton kind={kind} count={members[kind].length} expanded={expansion.rowId === row.id && expansion.view === kind && expansion.expanded} onClick={() => expansion.toggle(row.id, kind)} />
      : null;
    return <FinanceTableRow className="oa-pending-payments-table-row" dataRelationGroup={presence.view ? row.id : undefined} id={index === 0 ? row.id : `${row.id}:${presence.view}:${display.id}`} key={`${presence.view}:${display.id}`}>
      <FinanceTableCell className="oa-pending-payments-table-cell oa-pending-payments-table-cell--oa" columnRole="identity">
        {oa ? <div className="oa-pending-payments-oa-grid">
          <div className="oa-pending-payments-oa-grid__applicant">
            <span className="oa-pending-payments-inline-row">
              {index === 0 && selectable ? <Checkbox aria-label={`选择 OA ${row.oa.applicantName || '未填写申请人'}`} className="oa-pending-payments-row-checkbox" isDisabled={loading} isSelected={selected} onChange={() => onToggleOaSelection?.(row)} /> : null}
              <TextLine strong value={oa.applicantName} />
              <DetailButton disabled={!oa.detailAvailable} label={`查看 OA ${oa.applicantName || oa.id} 详情`} onClick={() => onOpenDetail({ kind: 'oa', id: oa.id, rowId: row.id })} />
            </span>
            <span className="oa-pending-payments-tag-row"><FinanceStatusTag>{oa.applicationType || '类型为空'}</FinanceStatusTag><OaWorkflowStatusChip status={oa.workflowStatus} /></span>
          </div>
          <div className="oa-pending-payments-oa-grid__project"><TextLine value={oa.projectName} />{oa.applicationTime ? <span className="oa-pending-payments-tag-row"><TableTag>{formatDateTimeText(oa.applicationTime)}</TableTag></span> : null}</div>
          <div className="oa-pending-payments-oa-grid__reason"><TextLine value={oa.reason} /></div>
          <div className="oa-pending-payments-oa-grid__counterparty"><TextLine value={oa.counterpartyName} /></div>
          <div className="oa-pending-payments-oa-grid__amount"><span className="oa-pending-payments-oa-amount-row"><TextLine numeric strong value={oa.amount} />{countButton('oa')}</span></div>
        </div> : <span className="oa-pending-payments-inline-row">{index === 0 && selectable ? <Checkbox aria-label={`选择 OA ${row.oa.applicantName || '未填写申请人'}`} className="oa-pending-payments-row-checkbox" isDisabled={loading} isSelected={selected} onChange={() => onToggleOaSelection?.(row)} /> : null}<EmptyValue />{countButton('oa')}</span>}
      </FinanceTableCell>
      <FinanceTableCell className="oa-pending-payments-table-cell oa-pending-payments-table-cell--status oa-pending-payments-table-cell--left-border oa-pending-payment-status-cell" columnRole="status">
        <span className="oa-pending-payments-status-stack"><span className="oa-pending-payments-status-action-line"><FinanceStatusTag tone={statusTone(row.paymentStatus.severity)}>{paymentStatusLabel(row)}</FinanceStatusTag></span></span>
      </FinanceTableCell>
      <FinanceTableCell className="oa-pending-payments-table-cell oa-pending-payments-table-cell--bank oa-pending-payments-table-cell--left-border" columnRole="identity">
        {bank ? <div className="oa-pending-payments-bank-grid">
          <div className="oa-pending-payments-bank-grid__counterparty"><span className="oa-pending-payments-inline-row"><TextLine strong value={bank.counterpartyName} />{countButton('bank')}<DetailButton disabled={!bank.id} label={`查看流水 ${index === 0 ? oa?.applicantName || bank.counterpartyName || bank.id : bank.counterpartyName || bank.id} 详情`} onClick={() => onOpenDetail({ kind: 'bank', id: bank.id, rowId: row.id })} /></span>{bank.tradeTime ? <span className="oa-pending-payments-tag-row"><TableTag>{formatDateTimeText(bank.tradeTime)}</TableTag></span> : null}</div>
          <div className="oa-pending-payments-bank-grid__amount"><span className="oa-pending-payments-bank-amount-line"><TextLine numeric strong value={bank.original_amount} /></span><span className="oa-pending-payments-bank-metadata"><FinanceDirectionTag direction={bank.directionLabel || '支出'}>{bank.directionLabel || '支出'}</FinanceDirectionTag><BankAccountValue value={bankAccountLabel(bank)} /></span>{bank.bank_split_parts?.length ? <BankSplitChips parts={bank.bank_split_parts} /> : null}</div>
          <div className="oa-pending-payments-bank-grid__summary"><MultiLineValue value={[bank.summary, bank.remark].filter(Boolean).join('\n')} /></div>
        </div> : <span className="oa-pending-payments-empty-bank-cell"><EmptyValue />{countButton('bank')}</span>}
      </FinanceTableCell>
      <FinanceTableCell className="oa-pending-payments-table-cell oa-pending-payments-table-cell--invoice oa-pending-payments-table-cell--left-border" columnRole="identity">
        {invoice ? <div className="oa-pending-payments-invoice-stack"><span className="oa-pending-payments-inline-row"><TextLine strong value={invoice.digitalInvoiceNo} />{countButton('invoice')}<DetailButton disabled={!invoice.id} label={`查看发票 ${index === 0 ? oa?.applicantName || invoice.digitalInvoiceNo || invoice.id : invoice.digitalInvoiceNo || invoice.id} 详情`} onClick={() => onOpenDetail({ kind: 'invoice', id: invoice.id, rowId: row.id })} /></span>{invoice.sellerName ? <TextLine value={invoice.sellerName} /> : null}<span className="oa-pending-payments-invoice-metadata">{invoice.invoiceDate ? <TableTag>{invoice.invoiceDate}</TableTag> : null}<span className="oa-pending-payments-invoice-amount-line"><TextLine numeric strong value={invoice.totalWithTax} /></span></span></div> : <span className="oa-pending-payments-empty-invoice-cell"><EmptyValue />{countButton('invoice')}</span>}
      </FinanceTableCell>
    </FinanceTableRow>;
  };
  return <Fragment>
    {displayRows[0] ? renderRow(displayRows[0], 0) : null}
    {presence.view ? <RelationRowsMotion key={presence.view} expanded={presence.expanded} onExited={presence.onExited}>{displayRows.slice(1).map((display, index) => renderRow(display, index + 1))}</RelationRowsMotion> : null}
  </Fragment>;
}

function GroupedSubHeader({
  column,
  configsByField,
  filterOptions,
  filters,
  onFilterApply,
  onFilterClear,
  onSortChange,
}: {
  column: OaPendingPaymentColumn;
  configsByField: Map<string, OaPendingPaymentFieldConfig>;
  filterOptions: Record<string, OaPendingPaymentFilterOption[]>;
  filters: OaPendingPaymentFilter[];
  onFilterApply: (filter: OaColumnFilterValue) => void;
  onFilterClear: (field: string) => void;
  onSortChange: (field: string, direction?: OaPendingPaymentSortDirection) => void;
}) {
  const control = (config: HeaderControlConfig) => (
    <HeaderCell
      column={column}
      configsByField={configsByField}
      displayLabel={config.label}
      filterFields={config.filterFields}
      filterLabel={config.filterLabel}
      filterOptions={filterOptions}
      filters={filters}
      onFilterApply={onFilterApply}
      onFilterClear={onFilterClear}
      onSortChange={onSortChange}
      sortField={config.sortField}
      sortLabel={config.sortLabel}
    />
  );

  if (column.group === "oa") {
    return (
      <span className="oa-pending-payments-subheader-grid oa-pending-payments-subheader-grid--oa">
        <span>{control({
          label: "申请人",
          filterFields: [
            { field: "oa_applicant", label: "OA申请人" },
            { field: "oa_application_type", label: "类型" },
          ],
          filterLabel: "申请人",
          sortField: "oa_applicant",
          sortLabel: "申请人",
        })}</span>
        <span>{control({
          label: "项目",
          filterFields: [{ field: "oa_project_name", label: "项目名称" }],
          filterLabel: "项目",
        })}</span>
        <span>申请事由</span>
        <span>对方户名</span>
        <span className="oa-pending-payments-subheader-grid__amount">金额</span>
      </span>
    );
  }

  if (column.group === "status") {
    return (
      <span className="oa-pending-payments-subheader-grid oa-pending-payments-subheader-grid--status">
        <span>{control({
          label: "状态",
          filterFields: [{ field: "payment_status", label: "支付状态" }],
          filterLabel: "支付状态",
          sortField: "payment_status",
          sortLabel: "支付状态",
        })}</span>
      </span>
    );
  }

  if (column.group === "bank") {
    return (
      <span className="oa-pending-payments-subheader-grid oa-pending-payments-subheader-grid--bank">
        <span>{control({
          label: "对方户名",
          filterFields: [{ field: "bank_counterparty_name", label: "对方户名" }],
          filterLabel: "对方户名",
          sortField: "bank_trade_time",
          sortLabel: "交易时间",
        })}</span>
        <span className="oa-pending-payments-subheader-grid__amount">{control({
          label: "金额",
          filterFields: [
            { field: "bank_account", label: "银行账户" },
            { field: "bank_direction", label: "收支" },
          ],
          filterLabel: "流水金额",
        })}</span>
        <span>流水摘要</span>
      </span>
    );
  }

  return (
    <span className="oa-pending-payments-subheader-grid oa-pending-payments-subheader-grid--invoice">
      <span className="oa-pending-payments-subheader-grid__invoice-number">{control({ label: "发票号" })}</span>
      <span className="oa-pending-payments-subheader-grid__invoice-details">{control({
        label: "发票方",
        filterFields: [{ field: "seller_name", label: "发票方" }],
        filterLabel: "发票方",
      })}{control({
        label: "日期",
        sortField: "invoice_date",
        sortLabel: "开票日期",
      })}</span>
      <span className="oa-pending-payments-subheader-grid__amount">金额</span>
    </span>
  );
}

function HeaderCell({
  column,
  displayLabel,
  filterFields,
  filterLabel,
  configsByField,
  filterOptions,
  filters,
  onFilterApply,
  onFilterClear,
  onSortChange,
  sortField,
  sortLabel,
}: {
  column: OaPendingPaymentColumn;
  displayLabel?: ReactNode;
  filterFields?: OaColumnFilterField[];
  filterLabel?: string;
  configsByField: Map<string, OaPendingPaymentFieldConfig>;
  filterOptions: Record<string, OaPendingPaymentFilterOption[]>;
  filters: OaPendingPaymentFilter[];
  onFilterApply: (filter: OaColumnFilterValue) => void;
  onFilterClear: (field: string) => void;
  onSortChange: (field: string, direction?: OaPendingPaymentSortDirection) => void;
  sortField?: string;
  sortLabel?: string;
}) {
  const effectiveSortField = sortField;
  const effectiveSortLabel = sortLabel ?? column.sortLabel ?? column.label;
  const effectiveFilterFields = filterFields;
  const effectiveFilterLabel = filterLabel ?? column.label;

  return (
    <span className="oa-pending-payments-header-control">
      <span className="oa-pending-payments-header-control__label">{displayLabel ?? column.label}</span>
      {effectiveSortField ? (
        <SortButton
          label={effectiveSortLabel}
          onClick={() => onSortChange(effectiveSortField)}
        />
      ) : null}
      {effectiveFilterFields ? (
        <OaColumnFilterMenu
          columnLabel={effectiveFilterLabel}
          configsByField={configsByField}
          fieldRefs={effectiveFilterFields}
          filterOptions={filterOptions}
          filters={filters}
          onApply={onFilterApply}
          onClear={onFilterClear}
        />
      ) : null}
    </span>
  );
}

function OaColumnFilterMenu({
  columnLabel,
  fieldRefs,
  configsByField,
  filterOptions,
  filters,
  onApply,
  onClear,
}: {
  columnLabel: string;
  fieldRefs: OaColumnFilterField[];
  configsByField: Map<string, OaPendingPaymentFieldConfig>;
  filterOptions: Record<string, OaPendingPaymentFilterOption[]>;
  filters: OaPendingPaymentFilter[];
  onApply: (filter: OaColumnFilterValue) => void;
  onClear: (field: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Record<string, string[]>>(() => selectedValuesByField(filters, fieldRefs));
  const active = fieldRefs.some((fieldRef) => selectedValues(filters, fieldRef.field).length > 0);

  const handleOpenChange = (nextOpen: boolean) => {
    if (nextOpen) {
      setDraft(selectedValuesByField(filters, fieldRefs));
    }
    setOpen(nextOpen);
  };

  const toggleValue = (field: string, value: string) => {
    setDraft((current) => {
      const values = current[field] ?? [];
      const nextValues = values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
      return { ...current, [field]: nextValues };
    });
  };

  const apply = () => {
    fieldRefs.forEach((fieldRef) => {
      onClear(fieldRef.field);
    });
    fieldRefs.forEach((fieldRef) => {
      const values = draft[fieldRef.field] ?? [];
      if (values.length > 0) {
        onApply({ field: fieldRef.field, operator: "in", values });
      }
    });
    setOpen(false);
  };

  const clear = () => {
    fieldRefs.forEach((fieldRef) => {
      onClear(fieldRef.field);
    });
    setDraft({});
    setOpen(false);
  };

  return (
    <PopoverRoot isOpen={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger
        aria-label={`筛选 ${columnLabel}`}
        className={cx(
          "oa-pending-payments-column-filter__trigger",
          active && "oa-pending-payments-column-filter__trigger--active",
        )}
      >
        <Filter aria-hidden="true" size={13} strokeWidth={2.4} />
      </PopoverTrigger>
      <PopoverContent
        className="oa-pending-payments-column-filter__panel"
        containerPadding={12}
        maxHeight={360}
        offset={8}
        placement="bottom start"
      >
        <PopoverDialog aria-label={`${columnLabel}筛选`} className="oa-pending-payments-column-filter__dialog">
          <div aria-label={`${columnLabel}筛选`} className="oa-pending-payments-column-filter__menu" role="menu">
            <div className="oa-pending-payments-column-filter__title">{columnLabel}</div>
            {fieldRefs.map((fieldRef) => {
              const config = configsByField.get(fieldRef.field);
              const options = filterOptions[fieldRef.field] ?? [];
              const selected = new Set(draft[fieldRef.field] ?? []);
              return (
                <div className="oa-pending-payments-column-filter__section" key={fieldRef.field}>
                  <div className="oa-pending-payments-column-filter__section-title">{fieldRef.label}</div>
                  {config && config.mode !== "enum_multi" ? (
                    <DisabledChoice>该字段暂不支持枚举筛选</DisabledChoice>
                  ) : null}
                  {options.length === 0 ? <DisabledChoice>暂无可选项</DisabledChoice> : null}
                  {options.map((option) => (
                    <button
                      key={option.value}
                      aria-checked={selected.has(option.value)}
                      className="oa-pending-payments-column-filter__item"
                      onClick={() => toggleValue(fieldRef.field, option.value)}
                      role="menuitemcheckbox"
                      type="button"
                    >
                      <span aria-hidden="true" className="oa-pending-payments-column-filter__checkmark">
                        {selected.has(option.value) ? "✓" : ""}
                      </span>
                      <span>{fieldRef.label}：{optionLabel(option)}</span>
                    </button>
                  ))}
                </div>
              );
            })}
          </div>
          <div className="oa-pending-payments-column-filter__actions">
            <button onClick={clear} type="button">清除</button>
            <button className="oa-pending-payments-column-filter__apply" onClick={apply} type="button">应用筛选</button>
          </div>
        </PopoverDialog>
      </PopoverContent>
    </PopoverRoot>
  );
}

function SortButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      aria-label={`${label} 排序`}
      className="oa-pending-payments-sort-button"
      onClick={onClick}
      type="button"
    >
      <ArrowUpDown aria-hidden="true" size={13} strokeWidth={2.3} />
    </button>
  );
}

function TextLine({
  value,
  strong = false,
  numeric = false,
}: {
  value: string | number | null | undefined;
  strong?: boolean;
  numeric?: boolean;
}) {
  const text = value == null || value === "" ? "-" : numeric ? formatMoney(value, "-") : String(value);
  if (text === "-") {
    return <EmptyValue />;
  }
  return (
    <span
      className={cx(
        "oa-pending-payments-table-text",
        strong && "oa-pending-payments-table-text--strong",
        numeric && "oa-pending-payments-table-text--numeric",
      )}
      title={text}
    >
      {text}
    </span>
  );
}

function MultiLineValue({ value }: { value: string }) {
  const text = value || "-";
  if (text === "-") {
    return <EmptyValue />;
  }
  return (
    <span className="oa-pending-payments-table-multiline" title={text}>
      {text}
    </span>
  );
}

function TableTag({ children }: { children: ReactNode }) {
  return <span className="oa-pending-payments-table-tag">{children}</span>;
}

function DisabledChoice({ children }: { children: ReactNode }) {
  return (
    <div aria-disabled="true" className="oa-pending-payments-column-filter__item oa-pending-payments-column-filter__item--disabled" role="menuitem">
      {children}
    </div>
  );
}

function DetailButton({
  label,
  disabled,
  onClick,
  text,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  text?: string;
}) {
  return (
    <button
      aria-label={label}
      className={cx(
        "oa-pending-payments-detail-button",
        text && "oa-pending-payments-detail-button--count",
      )}
      disabled={disabled}
      onClick={onClick}
      title={label}
      type="button"
    >
      {text ?? <Info aria-hidden="true" size={14} strokeWidth={2.3} />}
    </button>
  );
}

function PaginationControls({
  page,
  pageSize,
  total,
  oaCount,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  oaCount?: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}) {
  const safeTotal = safeCount(total);
  const totalPages = Math.max(1, Math.ceil(safeTotal / Math.max(pageSize, 1)));
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  return (
    <div className="oa-pending-payments-pagination">
      <Select
        aria-label="每页"
        className="oa-pending-payments-pagination-size"
        onChange={(key) => onPageSizeChange(Number(key))}
        placeholder="每页"
        value={String(pageSize)}
      >
        <Select.Trigger><Select.Value /></Select.Trigger>
        <Select.Popover><ListBox>{[20, 50, 100].map((option) => <ListBox.Item id={String(option)} key={option} textValue={`${option} 行/页`}>{option} 行/页</ListBox.Item>)}</ListBox></Select.Popover>
      </Select>
      <FinanceTablePagination summary={`符合条件 ${oaCount ?? "—"} 条 OA · 第 ${currentPage}/${totalPages} 页`} compact onPageChange={onPageChange} page={currentPage} pageSize={pageSize} total={safeTotal} />
    </div>
  );
}

function selectedValuesByField(filters: OaPendingPaymentFilter[], fieldRefs: OaColumnFilterField[]) {
  return fieldRefs.reduce<Record<string, string[]>>((accumulator, fieldRef) => {
    accumulator[fieldRef.field] = selectedValues(filters, fieldRef.field);
    return accumulator;
  }, {});
}

function selectedValues(filters: OaPendingPaymentFilter[], field: string) {
  const filter = filters.find((item) => item.field === field);
  if (!filter) {
    return [];
  }
  if (Array.isArray(filter.values)) {
    return filter.values;
  }
  if (Array.isArray(filter.value)) {
    return filter.value.map(String);
  }
  if (typeof filter.value === "string" && filter.value) {
    return [filter.value];
  }
  return [];
}

function optionLabel(option: OaPendingPaymentFilterOption) {
  return option.count === undefined ? option.label : `${option.label} ${option.count}`;
}

function safeCount(value: number) {
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function firstColumnInGroup(columnId: string) {
  return columnId === "paymentStatus" || columnId === "bank" || columnId === "invoice";
}

function paymentStatusLabel(row: OaPendingPaymentRow): string {
  return row.paymentStatus.label || "-";
}

function workflowStatusLabel(row: OaPendingPaymentRow): string {
  const status = String(row.oa.workflowStatus || "").trim();
  if (status === "in_progress") {
    return "进行中";
  }
  if (status === "completed" || !status) {
    return "已完成";
  }
  return status;
}

function canSelectOa(row: OaPendingPaymentRow): boolean {
  return workflowStatusLabel(row) === "进行中";
}

function oaRowIds(row: OaPendingPaymentRow): string[] {
  const ids: string[] = [];
  const primary = row.oa.primaryOaId || row.oa.id;
  if (primary) {
    ids.push(primary);
  }
  row.oa.summaries?.forEach((summary) => {
    if (summary.oaId && !ids.includes(summary.oaId)) {
      ids.push(summary.oaId);
    }
  });
  return ids;
}

function bankAccountLabel(bank: NonNullable<OaPendingDisplayRow['bank']>): string {
  const last4 = bank.accountLast4 || accountLast4(bank.accountNo);
  if (bank.bankShortName) return [bank.bankShortName, last4].filter(Boolean).join(' ');
  if (bank.bankAccount) return bank.bankAccount;
  return [bank.bankName, last4].filter(Boolean).join(' ') || '—';
}

function accountLast4(value: string | undefined): string {
  const text = String(value || "").trim();
  return text.length >= 4 ? text.slice(-4) : "";
}

function statusTone(severity: string | undefined): FinanceTone {
  if (severity === "success") {
    return "success";
  }
  if (severity === "error") {
    return "danger";
  }
  if (severity === "warning") {
    return "warning";
  }
  return "neutral";
}
