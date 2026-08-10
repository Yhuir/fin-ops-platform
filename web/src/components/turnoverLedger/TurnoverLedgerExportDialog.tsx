import { Button, ListBox, Select } from "@heroui/react";

import AppDialog from "../common/AppDialog";
import {
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../common/FinanceTable";
import type {
  TurnoverLedgerExportPreview,
  TurnoverLedgerExportRow,
  TurnoverLedgerFamily,
} from "../../features/turnoverLedger/types";
import { formatMoney, formatNullable } from "./TurnoverLedgerGroupedTable";

const FAMILY_OPTIONS: Array<{ value: TurnoverLedgerFamily; label: string }> = [
  { value: "all", label: "全部" },
  { value: "personal", label: "个人往来" },
  { value: "company", label: "公司往来" },
  { value: "bank", label: "银行往来" },
  { value: "business", label: "业务往来" },
];

const PREVIEW_COLUMNS: Array<{ key: keyof TurnoverLedgerExportRow; label: string; money?: boolean }> = [
  { key: "sequenceNo", label: "序号" },
  { key: "rowType", label: "行类型" },
  { key: "familyLabel", label: "往来大类" },
  { key: "counterpartyName", label: "对方户名" },
  { key: "pendingRepaymentAmount", label: "待还款金额", money: true },
  { key: "pendingCollectionAmount", label: "待收款金额", money: true },
  { key: "balanceAmount", label: "余额", money: true },
  { key: "borrowAmount", label: "借款金额", money: true },
  { key: "borrowDate", label: "借款日" },
  { key: "repaymentAmount", label: "还款金额", money: true },
  { key: "repaymentDate", label: "还款日" },
  { key: "counterpartyBankName", label: "对方开户机构" },
  { key: "repaymentRemark", label: "还款备注" },
  { key: "interestRateType", label: "利率类型" },
  { key: "interestRateValue", label: "利率值" },
  { key: "interestPaidAmount", label: "已还利息额", money: true },
  { key: "loanDays", label: "借款天数" },
  { key: "accruedInterest", label: "应还利息", money: true },
  { key: "interestPaidDate", label: "还利息日期" },
  { key: "interestPaymentMethod", label: "还利息方式" },
  { key: "note", label: "备注" },
  { key: "statusLabel", label: "关系状态" },
];

function formatPreviewValue(row: TurnoverLedgerExportRow, column: { key: keyof TurnoverLedgerExportRow; money?: boolean }) {
  const rawValue = row[column.key];
  if (column.key === "rowType") {
    if (rawValue === "summary") {
      return "合计";
    }
    if (rawValue === "lot") {
      return "明细";
    }
    if (rawValue === "flow") {
      return "真实流水";
    }
  }
  return column.money ? formatMoney(String(rawValue ?? "")) : formatNullable(rawValue);
}

export default function TurnoverLedgerExportDialog({
  open,
  family,
  preview,
  loading,
  downloading,
  error,
  onClose,
  onFamilyChange,
  onDownload,
}: {
  open: boolean;
  family: TurnoverLedgerFamily;
  preview: TurnoverLedgerExportPreview | null;
  loading: boolean;
  downloading: boolean;
  error: string | null;
  onClose: () => void;
  onFamilyChange: (family: TurnoverLedgerFamily) => void;
  onDownload: () => void;
}) {
  return (
    <AppDialog
      actions={(
        <>
          <Button onPress={onClose} variant="secondary">
            取消
          </Button>
          <Button isDisabled={loading || downloading} isPending={downloading} onPress={onDownload} variant="primary">
            确认下载
          </Button>
        </>
      )}
      maxWidth="xl"
      open={open}
      title="下载往来款台账"
      onClose={onClose}
    >
      <div className="turnover-ledger-export-dialog">
        <div className="turnover-ledger-extra-control turnover-ledger-export-dialog__range">
          <span>下载范围</span>
          <Select
            aria-label="下载范围"
            selectedKey={family}
            onSelectionChange={(key) => onFamilyChange(String(key) as TurnoverLedgerFamily)}
          >
            <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
            <Select.Popover>
              <ListBox>
                {FAMILY_OPTIONS.map((option) => (
                  <ListBox.Item id={option.value} key={option.value} textValue={option.label}>{option.label}</ListBox.Item>
                ))}
              </ListBox>
            </Select.Popover>
          </Select>
        </div>
        {error ? <div className="turnover-ledger-drawer__notice turnover-ledger-drawer__notice--danger" role="alert">{error}</div> : null}
        <h3 className="turnover-ledger-extra-section__title">正式字段预览</h3>
        <div className="turnover-ledger-export-dialog__table-wrap">
          <FinanceTable ariaLabel="往来款导出预览" className="turnover-ledger-export-dialog__table" minWidth={2200} scrollMode="contained">
            <FinanceTableHeader>
              {PREVIEW_COLUMNS.map((column, index) => (
                <FinanceTableColumn id={column.key} isRowHeader={index === 0} key={column.key} columnRole={column.money ? "amount" : index === 0 ? "identity" : "description"}>
                  {column.label}
                </FinanceTableColumn>
              ))}
            </FinanceTableHeader>
            <FinanceTableBody>
              {loading ? (
                <FinanceTableRow id="loading">
                  {PREVIEW_COLUMNS.map((column, index) => <FinanceTableCell className={index === 0 ? "turnover-ledger-export-dialog__state-cell" : undefined} columnRole={column.money ? "amount" : index === 0 ? "identity" : "description"} key={column.key}>{index === 0 ? "正在加载导出预览" : "-"}</FinanceTableCell>)}
                </FinanceTableRow>
              ) : null}
              {!loading && (preview?.rows.length ?? 0) === 0 ? (
                <FinanceTableRow id="empty">
                  {PREVIEW_COLUMNS.map((column, index) => <FinanceTableCell className={index === 0 ? "turnover-ledger-export-dialog__state-cell" : undefined} columnRole={column.money ? "amount" : index === 0 ? "identity" : "description"} key={column.key}>{index === 0 ? "当前范围没有可导出的台账行" : "-"}</FinanceTableCell>)}
                </FinanceTableRow>
              ) : null}
              {!loading
                ? (preview?.rows ?? []).map((row) => (
                    <FinanceTableRow id={`${row.sequenceNo}-${row.rowType}-${row.lotId}-${row.counterpartyName}`} key={`${row.sequenceNo}-${row.rowType}-${row.lotId}-${row.counterpartyName}`}>
                      {PREVIEW_COLUMNS.map((column, index) => {
                        const value = formatPreviewValue(row, column);
                        return (
                          <FinanceTableCell className={column.money ? "turnover-ledger-export-dialog__money-cell" : undefined} columnRole={column.money ? "amount" : index === 0 ? "identity" : "description"} key={column.key}>
                            {value}
                          </FinanceTableCell>
                        );
                      })}
                    </FinanceTableRow>
                  ))
                : null}
            </FinanceTableBody>
          </FinanceTable>
        </div>
          {preview ? (
            <p className="turnover-ledger-export-dialog__summary">
              合计：待还款 {formatMoney(preview.summary.pendingRepaymentAmount)}，待收款{" "}
              {formatMoney(preview.summary.pendingCollectionAmount)}，应还利息{" "}
              {formatMoney(preview.summary.accruedInterest)}
            </p>
          ) : null}
      </div>
    </AppDialog>
  );
}
