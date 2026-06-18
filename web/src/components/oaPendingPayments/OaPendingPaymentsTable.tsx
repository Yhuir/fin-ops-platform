import { ArrowUpDown, CheckCircle2, Filter, Info, Search } from "lucide-react";
import type { MutableRefObject, ReactNode } from "react";
import { useEffect, useId, useMemo, useState } from "react";

import {
  EmptyValue,
  FinanceDirectionTag,
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
  OaPendingPaymentViewMode,
} from "../../features/oaPendingPayments/types";

type OaColumnFilterValue = InputInvoiceUsageFilterValue;

type OaPendingPaymentsTableProps = {
  rows: OaPendingPaymentRow[];
  page: number;
  pageSize: number;
  total: number;
  keywordDraft: string;
  filterConfigs: OaPendingPaymentFieldConfig[];
  filterOptions: Record<string, OaPendingPaymentFilterOption[]>;
  filters: OaPendingPaymentFilter[];
  onKeywordDraftChange: (value: string) => void;
  onKeywordSubmit: () => void;
  onFilterApply: (filter: OaColumnFilterValue) => void;
  onFilterClear: (field: string) => void;
  onSortChange: (field: string, direction?: OaPendingPaymentSortDirection) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onOpenDetail: (target: OaPendingPaymentDetailTarget) => void;
  onConfirmPaid?: (row: OaPendingPaymentRow) => void;
  confirmingRowIds?: Set<string>;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
  viewMode: OaPendingPaymentViewMode;
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
    label: "发票号码/发票方",
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
  page,
  pageSize,
  total,
  keywordDraft,
  filterConfigs,
  filterOptions,
  filters,
  onKeywordDraftChange,
  onKeywordSubmit,
  onFilterApply,
  onFilterClear,
  onSortChange,
  onPageChange,
  onPageSizeChange,
  onOpenDetail,
  onConfirmPaid,
  confirmingRowIds = new Set(),
  tableWrapRef,
  viewMode,
}: OaPendingPaymentsTableProps) {
  const configsByField = useMemo(() => new Map(filterConfigs.map((config) => [config.field, config])), [filterConfigs]);
  const showInvoiceColumn = viewMode === "completed";
  const visibleColumns = useMemo(
    () => showInvoiceColumn ? columns : columns.filter((column) => column.group !== "invoice"),
    [showInvoiceColumn],
  );

  return (
    <div className="oa-pending-payments-table-frame" data-testid="oa-pending-payments-table-frame">
      <div className="oa-pending-payments-table-toolbar">
        <label className="oa-pending-payments-table-search">
          <Search aria-hidden="true" size={15} strokeWidth={2.2} />
          <input
            aria-label="搜索OA待付款核对"
            placeholder="搜索 OA / 流水 / 发票"
            value={keywordDraft}
            onChange={(event) => onKeywordDraftChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                onKeywordSubmit();
              }
            }}
          />
        </label>
        <button className="oa-pending-payments-button oa-pending-payments-table-search-button" onClick={onKeywordSubmit} type="button">
          查询
        </button>
      </div>
      <div ref={tableWrapRef} className="oa-pending-payments-table-shell" data-testid="oa-pending-payments-table-shell">
        <table aria-label="OA待付款核对表格" className="oa-pending-payments-table">
          <colgroup>
            {visibleColumns.map((column) => (
              <col className={`oa-pending-payments-col-${column.id}`} key={column.id} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <GroupHeader group="oa" label="OA" span={1} />
              <GroupHeader group="status" label="支付状态" span={1} />
              <GroupHeader group="bank" label="流水" span={1} />
              {showInvoiceColumn ? <GroupHeader group="invoice" label="发票情况" span={1} /> : null}
            </tr>
            <tr>
              {visibleColumns.map((column) => (
                <th
                  className={cx(
                    "oa-pending-payments-table-sub-header",
                    `oa-pending-payments-table-sub-header--${column.group}`,
                    column.align === "right" && "oa-pending-payments-table-cell--amount",
                    ["status", "bank", "invoice"].includes(column.group) && firstColumnInGroup(column.id) && "oa-pending-payments-table-cell--left-border",
                  )}
                  key={column.id}
                  scope="col"
                >
                  <HeaderCell
                    column={column}
                    configsByField={configsByField}
                    filterOptions={filterOptions}
                    filters={filters}
                    onFilterApply={onFilterApply}
                    onFilterClear={onFilterClear}
                    onSortChange={onSortChange}
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className="oa-pending-payments-table-state-cell" colSpan={visibleColumns.length}>
                  暂无 OA 待付款核对数据
                </td>
              </tr>
            ) : rows.map((row) => {
              const hasBank = hasBankTransaction(row);
              const bankTarget = bankDetailTarget(row);
              const confirming = confirmingRowIds.has(row.id);
              const canConfirm = Boolean(onConfirmPaid) && canConfirmPaid(row);
              return (
                <tr className="oa-pending-payments-table-row" key={row.id}>
                  <td className="oa-pending-payments-table-cell oa-pending-payments-table-cell--oa" data-column-role="identity">
                    <div className="oa-pending-payments-oa-grid">
                      <div className="oa-pending-payments-oa-grid__applicant">
                        <span className="oa-pending-payments-inline-row">
                          <TextLine strong value={row.oa.applicantName} />
                          <DetailButton
                            disabled={!row.oa.detailAvailable}
                            label={`查看 OA ${row.oa.applicantName} 详情`}
                            onClick={() => onOpenDetail({ kind: "oa", id: row.oa.id })}
                          />
                        </span>
                        <span className="oa-pending-payments-tag-row">
                          <TableTag>{row.oa.applicationType || "类型为空"}</TableTag>
                          <TableTag>{workflowStatusTagLabel(row)}</TableTag>
                          {hasCandidateOaRelation(row) ? <RelationStatusTag status="candidate" /> : null}
                        </span>
                      </div>
                      <div className="oa-pending-payments-oa-grid__project">
                        <TextLine value={row.oa.projectName} />
                        {row.oa.applicationTime ? (
                          <span className="oa-pending-payments-tag-row">
                            <TableTag>{row.oa.applicationTime}</TableTag>
                          </span>
                        ) : null}
                      </div>
                      <div className="oa-pending-payments-oa-grid__amount">
                        <span className="oa-pending-payments-oa-amount-row">
                          <TextLine numeric strong value={row.oa.amount} />
                          {oaRelationDetailTarget(row) ? (
                            <DetailButton
                              disabled={false}
                              label={oaRelationDetailLabel(row)}
                              onClick={() => {
                                const target = oaRelationDetailTarget(row);
                                if (target) {
                                  onOpenDetail(target);
                                }
                              }}
                              text={`+${extraRelationCount(row.oa.relationCount)}`}
                            />
                          ) : null}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td
                    className="oa-pending-payments-table-cell oa-pending-payments-table-cell--status oa-pending-payments-table-cell--left-border oa-pending-payment-status-cell"
                    data-column-role="status"
                  >
                    <span className="oa-pending-payments-status-stack">
                      <span className="oa-pending-payments-status-action-line">
                        <FinanceStatusTag tone={statusTone(row.paymentStatus.severity)}>
                          {paymentStatusLabel(row)}
                        </FinanceStatusTag>
                        {canConfirm ? (
                          <button
                            className="oa-pending-payments-confirm-paid-button"
                            disabled={confirming}
                            onClick={() => onConfirmPaid?.(row)}
                            type="button"
                          >
                            <CheckCircle2 aria-hidden="true" size={14} strokeWidth={2.2} />
                            {confirming ? "确认中" : "确认已支付"}
                          </button>
                        ) : null}
                      </span>
                      <span className="oa-pending-payments-writeback-line">
                        <TableTag>{writebackLabel(row)}</TableTag>
                      </span>
                      {writebackSyncStatus(row) === "unavailable" ? (
                        <span className="oa-pending-payments-writeback-sync">同步状态异常</span>
                      ) : null}
                    </span>
                  </td>
                  <td className="oa-pending-payments-table-cell oa-pending-payments-table-cell--bank oa-pending-payments-table-cell--left-border" data-column-role="identity">
                    {hasBank ? (
                      <div className="oa-pending-payments-bank-grid">
                        <div className="oa-pending-payments-bank-grid__counterparty">
                          <span className="oa-pending-payments-inline-row">
                            <TextLine strong value={counterpartyDisplay(row)} />
                            <DetailButton
                              disabled={!bankTarget}
                              label={bankDetailLabel(row)}
                              onClick={() => {
                                if (bankTarget) {
                                  onOpenDetail(bankTarget);
                                }
                              }}
                              text={bankRelationButtonText(row)}
                            />
                          </span>
                          <span className="oa-pending-payments-tag-row">
                            {row.bankTransaction.tradeTime ? <TableTag>{row.bankTransaction.tradeTime}</TableTag> : null}
                            {hasCandidateBankRelation(row) ? <RelationStatusTag status="candidate" /> : null}
                          </span>
                        </div>
                        <div className="oa-pending-payments-bank-grid__amount">
                          <span className="oa-pending-payments-bank-amount-line">
                            <TextLine numeric strong value={bankAmount(row)} />
                            <TableTag>{bankAccountLabel(row)}</TableTag>
                            <FinanceDirectionTag direction={row.bankTransaction.directionLabel || "支出"}>
                              {row.bankTransaction.directionLabel || "支出"}
                            </FinanceDirectionTag>
                          </span>
                        </div>
                        <div className="oa-pending-payments-bank-grid__summary">
                          <MultiLineValue value={combinedBankSummaryRemark(row)} />
                        </div>
                      </div>
                    ) : (
                      <span className="oa-pending-payments-empty-bank-cell">
                        <EmptyValue />
                      </span>
                    )}
                  </td>
                  {showInvoiceColumn ? (
                    <td className="oa-pending-payments-table-cell oa-pending-payments-table-cell--invoice oa-pending-payments-table-cell--left-border" data-column-role="identity">
                      <InvoiceCell row={row} onOpenDetail={onOpenDetail} />
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <PaginationControls
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
        page={page}
        pageSize={pageSize}
        total={total}
      />
    </div>
  );
}

function InvoiceCell({
  row,
  onOpenDetail,
}: {
  row: OaPendingPaymentRow;
  onOpenDetail: (target: OaPendingPaymentDetailTarget) => void;
}) {
  if (!hasInvoice(row)) {
    return (
      <span className="oa-pending-payments-empty-invoice-cell">
        <EmptyValue />
      </span>
    );
  }
  const invoiceTarget = invoiceDetailTarget(row);
  return (
    <>
      <span className="oa-pending-payments-inline-row">
        <TextLine strong value={invoiceDisplayNo(row)} />
        <DetailButton
          disabled={!invoiceTarget}
          label={invoiceDetailLabel(row)}
          onClick={() => {
            if (invoiceTarget) {
              onOpenDetail(invoiceTarget);
            }
          }}
          text={invoiceRelationButtonText(row)}
        />
      </span>
      <span className="oa-pending-payments-tag-row">
        {row.invoice.sellerName ? <TableTag>{row.invoice.sellerName}</TableTag> : null}
        {row.invoice.invoiceDate ? <TableTag>{row.invoice.invoiceDate}</TableTag> : null}
        {hasCandidateInvoiceRelation(row) ? <RelationStatusTag status="candidate" /> : null}
      </span>
      <span className="oa-pending-payments-invoice-amount-line">
        <TextLine numeric strong value={invoiceAmount(row)} />
        <TableTag>价税合计</TableTag>
      </span>
    </>
  );
}

function HeaderCell({
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
  return (
    <span className="oa-pending-payments-header-control">
      <span className="oa-pending-payments-header-control__label">{column.label}</span>
      {column.sortField ? (
        <SortButton
          label={column.sortLabel ?? column.label}
          onClick={() => column.sortField && onSortChange(column.sortField)}
        />
      ) : null}
      {column.filterFields ? (
        <OaColumnFilterMenu
          columnLabel={column.label}
          configsByField={configsByField}
          fieldRefs={column.filterFields}
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
  const menuId = useId();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Record<string, string[]>>(() => selectedValuesByField(filters, fieldRefs));
  const active = fieldRefs.some((fieldRef) => selectedValues(filters, fieldRef.field).length > 0);

  useEffect(() => {
    if (open) {
      setDraft(selectedValuesByField(filters, fieldRefs));
    }
  }, [fieldRefs, filters, open]);

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
    <span className="oa-pending-payments-column-filter">
      <button
        aria-controls={open ? menuId : undefined}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`筛选 ${columnLabel}`}
        className={cx(
          "oa-pending-payments-column-filter__trigger",
          active && "oa-pending-payments-column-filter__trigger--active",
        )}
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <Filter aria-hidden="true" size={13} strokeWidth={2.4} />
      </button>
      {open ? (
        <div
          aria-label={`${columnLabel}筛选`}
          className="oa-pending-payments-column-filter__panel"
          id={menuId}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setOpen(false);
            }
          }}
          role="menu"
        >
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
          <div className="oa-pending-payments-column-filter__actions">
            <button onClick={clear} type="button">清除</button>
            <button className="oa-pending-payments-column-filter__apply" onClick={apply} type="button">应用筛选</button>
          </div>
        </div>
      ) : null}
    </span>
  );
}

function GroupHeader({ label, span, group }: { label: string; span: number; group: "oa" | "status" | "bank" | "invoice" }) {
  return (
    <th
      className={cx(
        "oa-pending-payments-table-group-header",
        `oa-pending-payments-table-group-header--${group}`,
        group !== "oa" && "oa-pending-payments-table-cell--left-border",
      )}
      colSpan={span}
      scope="colgroup"
    >
      {label}
    </th>
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
  const text = value == null || value === "" ? "-" : String(value);
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

function RelationStatusTag({ status }: { status: string }) {
  if (status !== "candidate") {
    return null;
  }
  return <span className="oa-pending-payments-table-tag oa-pending-payments-table-tag--candidate">候选</span>;
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
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  return (
    <div className="oa-pending-payments-pagination">
      <label className="oa-pending-payments-pagination-size">
        <span>每页</span>
        <select
          aria-label="每页"
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
          value={pageSize}
        >
          {[20, 50, 100].map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </label>
      <span className="oa-pending-payments-pagination-range">{displayedRange(currentPage, pageSize, total)}</span>
      <span className="oa-pending-payments-pagination-actions">
        <button disabled={currentPage <= 1} onClick={() => onPageChange(currentPage - 1)} type="button">上一页</button>
        <button disabled={currentPage >= totalPages} onClick={() => onPageChange(currentPage + 1)} type="button">下一页</button>
      </span>
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

function displayedRange(page: number, pageSize: number, total: number) {
  if (total <= 0) {
    return "0-0 / 0";
  }
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  const from = (currentPage - 1) * pageSize + 1;
  const to = Math.min(currentPage * pageSize, total);
  return `${from}-${to} / ${total}`;
}

function firstColumnInGroup(columnId: string) {
  return columnId === "paymentStatus" || columnId === "bank" || columnId === "invoice";
}

function paymentStatusLabel(row: OaPendingPaymentRow): string {
  if (row.paymentStatus.code === "unpaid") {
    return "待支付";
  }
  return row.paymentStatus.label || "-";
}

function writebackLabel(row: OaPendingPaymentRow): string {
  return row.oaPaymentWriteback?.code === "written" ? "已写回" : "未写回";
}

function writebackSyncStatus(row: OaPendingPaymentRow): string {
  return row.oaPaymentWriteback?.syncStatus || "not_required";
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

function workflowStatusTagLabel(row: OaPendingPaymentRow): string {
  return `流程状态：${workflowStatusLabel(row)}`;
}

function counterpartyDisplay(row: OaPendingPaymentRow): string {
  const counterparty = String(row.bankTransaction.counterpartyName || "").trim();
  return counterparty ? `对方户名：${counterparty}` : "";
}

function confirmBankTransactionId(row: OaPendingPaymentRow): string {
  if (row.bankTransaction.primaryBankTransactionId) {
    return row.bankTransaction.primaryBankTransactionId;
  }
  return row.bankTransaction.summaries?.find((summary) => summary.bankTransactionId)?.bankTransactionId || "";
}

function canConfirmPaid(row: OaPendingPaymentRow): boolean {
  return row.paymentStatus.code !== "paid" && hasCandidateBankRelation(row) && Boolean(confirmBankTransactionId(row));
}

function hasInvoice(row: OaPendingPaymentRow): boolean {
  return Boolean(
    (row.invoice.detailMode === "single" && row.invoice.primaryInvoiceId)
    || (row.invoice.detailMode === "list" && row.invoice.relationCount > 0)
    || row.invoice.digitalInvoiceNo
    || row.invoice.sellerName
    || row.invoice.invoiceDate,
  );
}

function bankAmount(row: OaPendingPaymentRow): string {
  if (row.bankTransaction.detailMode === "list" && row.bankTransaction.paidTotal) {
    return row.bankTransaction.paidTotal;
  }
  return row.bankTransaction.amount || row.bankTransaction.paidTotal || row.bankTransaction.debitAmount || row.bankTransaction.creditAmount || "";
}

function invoiceAmount(row: OaPendingPaymentRow): string {
  return row.invoice.totalWithTax || "";
}

function invoiceDisplayNo(row: OaPendingPaymentRow): string {
  return row.invoice.digitalInvoiceNo || row.invoice.primaryInvoiceId || "";
}

function bankAccountLabel(row: OaPendingPaymentRow): string {
  if (row.bankTransaction.bankAccount) {
    return row.bankTransaction.bankAccount;
  }
  const bankName = row.bankTransaction.bankName || "银行";
  const last4 = row.bankTransaction.accountLast4 || accountLast4(row.bankTransaction.accountNo);
  return [bankName, last4].filter(Boolean).join(" ") || "-";
}

function accountLast4(value: string | undefined): string {
  const text = String(value || "").trim();
  return text.length >= 4 ? text.slice(-4) : "";
}

function combinedBankSummaryRemark(row: OaPendingPaymentRow): string {
  const summaries = row.bankTransaction.summaries?.length
    ? row.bankTransaction.summaries
    : [{
      summary: row.bankTransaction.summary,
      remark: row.bankTransaction.remark,
    }];
  const seen = new Set<string>();
  const lines: string[] = [];
  summaries.forEach((summary) => {
    [summary.summary, summary.remark].forEach((part) => {
      const text = String(part || "").trim();
      if (!text || seen.has(text)) {
        return;
      }
      seen.add(text);
      lines.push(text);
    });
  });
  return lines.join("\n");
}

function hasBankTransaction(row: OaPendingPaymentRow): boolean {
  return Boolean(
    (row.bankTransaction.detailMode === "single" && row.bankTransaction.primaryBankTransactionId)
    || (row.bankTransaction.detailMode === "list" && row.bankTransaction.relationCount > 0)
    || row.bankTransaction.counterpartyName
    || row.bankTransaction.tradeTime,
  );
}

function bankDetailTarget(row: OaPendingPaymentRow): OaPendingPaymentDetailTarget | null {
  if (row.bankTransaction.detailMode === "single" && row.bankTransaction.primaryBankTransactionId) {
    return { kind: "bank", id: row.bankTransaction.primaryBankTransactionId };
  }
  if (row.bankTransaction.detailMode === "list") {
    return { kind: "relationList", id: row.id, rowId: row.id, relationKind: "bank" };
  }
  return null;
}

function invoiceDetailTarget(row: OaPendingPaymentRow): OaPendingPaymentDetailTarget | null {
  if (row.invoice.detailMode === "single" && row.invoice.primaryInvoiceId) {
    return { kind: "invoice", id: row.invoice.primaryInvoiceId };
  }
  if (row.invoice.detailMode === "list") {
    return { kind: "relationList", id: row.id, rowId: row.id, relationKind: "invoice" };
  }
  return null;
}

function oaRelationDetailTarget(row: OaPendingPaymentRow): OaPendingPaymentDetailTarget | null {
  if (row.oa.detailMode === "list" && Number(row.oa.relationCount ?? 0) > 1) {
    return { kind: "relationList", id: row.id, rowId: row.id, relationKind: "oa" };
  }
  return null;
}

function extraRelationCount(relationCount: number | undefined): number {
  return Math.max(0, Number(relationCount ?? 0) - 1);
}

function bankDetailLabel(row: OaPendingPaymentRow): string {
  const applicant = row.oa.applicantName || "该OA";
  if (row.bankTransaction.detailMode === "list") {
    return `查看${applicant}关联流水 ${row.bankTransaction.relationCount} 条`;
  }
  return `查看流水 ${applicant} 详情`;
}

function isCandidateStatus(value: unknown): boolean {
  return typeof value === "string" && value.trim() === "candidate";
}

function hasCandidateOaRelation(row: OaPendingPaymentRow): boolean {
  return isCandidateStatus(row.oa.relationStatus)
    || Boolean(row.oa.summaries?.some((summary) => isCandidateStatus(summary.relationStatus)));
}

function hasCandidateBankRelation(row: OaPendingPaymentRow): boolean {
  return isCandidateStatus(row.bankTransaction.relationStatus)
    || Boolean(row.bankTransaction.summaries?.some((summary) => isCandidateStatus(summary.relationStatus)));
}

function hasCandidateInvoiceRelation(row: OaPendingPaymentRow): boolean {
  return isCandidateStatus(row.invoice.relationStatus)
    || Boolean(row.invoice.summaries?.some((summary) => isCandidateStatus(summary.relationStatus)));
}

function bankRelationButtonText(row: OaPendingPaymentRow): string | undefined {
  const extraCount = extraRelationCount(row.bankTransaction.relationCount);
  return row.bankTransaction.detailMode === "list" && extraCount > 0 ? `+${extraCount}` : undefined;
}

function invoiceRelationButtonText(row: OaPendingPaymentRow): string | undefined {
  const extraCount = extraRelationCount(row.invoice.relationCount);
  return row.invoice.detailMode === "list" && extraCount > 0 ? `+${extraCount}` : undefined;
}

function oaRelationDetailLabel(row: OaPendingPaymentRow): string {
  const applicant = row.oa.applicantName || "该OA";
  return `查看${applicant}关联OA ${row.oa.relationCount ?? 0} 条`;
}

function invoiceDetailLabel(row: OaPendingPaymentRow): string {
  const applicant = row.oa.applicantName || "该OA";
  if (row.invoice.detailMode === "list") {
    return `查看${applicant}关联发票 ${row.invoice.relationCount ?? 0} 张`;
  }
  return `查看发票 ${applicant} 详情`;
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
