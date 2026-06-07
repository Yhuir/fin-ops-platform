import AppDialog from "../common/AppDialog";
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
  { key: "lotId", label: "批次 ID" },
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
          <button className="turnover-ledger-button" onClick={onClose} type="button">
            取消
          </button>
          <button className="turnover-ledger-button turnover-ledger-button--primary" disabled={loading || downloading} onClick={onDownload} type="button">
            确认下载
          </button>
        </>
      )}
      maxWidth="xl"
      open={open}
      title="下载往来款台账"
      onClose={onClose}
    >
      <div className="turnover-ledger-export-dialog">
        <label className="turnover-ledger-extra-control turnover-ledger-export-dialog__range">
          <span>下载范围</span>
          <select
            value={family}
            onChange={(event) => onFamilyChange(event.target.value as TurnoverLedgerFamily)}
          >
            {FAMILY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        {error ? <div className="turnover-ledger-drawer__notice turnover-ledger-drawer__notice--danger" role="alert">{error}</div> : null}
        <h3 className="turnover-ledger-extra-section__title">正式字段预览</h3>
        <div className="turnover-ledger-export-dialog__table-wrap">
          <table aria-label="往来款导出预览" className="turnover-ledger-export-dialog__table">
            <thead>
              <tr>
                {PREVIEW_COLUMNS.map((column) => (
                  <th key={column.key} scope="col">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="turnover-ledger-export-dialog__state-cell" colSpan={PREVIEW_COLUMNS.length}>
                    正在加载导出预览
                  </td>
                </tr>
              ) : null}
              {!loading && (preview?.rows.length ?? 0) === 0 ? (
                <tr>
                  <td className="turnover-ledger-export-dialog__state-cell" colSpan={PREVIEW_COLUMNS.length}>
                    当前范围没有可导出的台账行
                  </td>
                </tr>
              ) : null}
              {!loading
                ? (preview?.rows ?? []).map((row) => (
                    <tr key={`${row.sequenceNo}-${row.rowType}-${row.lotId}-${row.counterpartyName}`}>
                      {PREVIEW_COLUMNS.map((column) => {
                        const value = formatPreviewValue(row, column);
                        return (
                          <td className={column.money ? "turnover-ledger-export-dialog__money-cell" : undefined} key={column.key}>
                            {value}
                          </td>
                        );
                      })}
                    </tr>
                  ))
                : null}
            </tbody>
          </table>
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
