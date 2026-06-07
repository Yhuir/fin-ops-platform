import type { ChangeEvent, ReactNode } from "react";

import AppDrawer from "../common/AppDrawer";
import type {
  TurnoverLedgerExtra,
  TurnoverLedgerGroupedRow,
  TurnoverRelationDetail,
} from "../../features/turnoverLedger/types";
import { formatMoney, formatNullable } from "./TurnoverLedgerGroupedTable";

function DetailField({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="turnover-ledger-extra-field">
      <span className="turnover-ledger-extra-field__label">{label}</span>
      <span className="turnover-ledger-extra-field__value">{formatNullable(value)}</span>
    </div>
  );
}

function cleanText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function flowDate(row: TurnoverLedgerGroupedRow | null) {
  return cleanText(row?.transactionAt) || cleanText(row?.borrowDate) || cleanText(row?.repaymentDate) || "";
}

function flowDirectionLabel(row: TurnoverLedgerGroupedRow | null) {
  const direction = cleanText(row?.flowDirection);
  if (direction === "income") {
    return "收";
  }
  if (direction === "expense") {
    return "支";
  }
  const borrowAmount = Number(String(row?.borrowAmount ?? "0").replace(/,/g, ""));
  const repaymentAmount = Number(String(row?.repaymentAmount ?? "0").replace(/,/g, ""));
  if (borrowAmount > 0 && repaymentAmount <= 0) {
    return cleanText(row?.borrowDirection) === "expense" ? "支" : "收";
  }
  if (repaymentAmount > 0 && borrowAmount <= 0) {
    return cleanText(row?.repaymentDirection) === "income" ? "收" : "支";
  }
  return "流水";
}

function flowAmount(row: TurnoverLedgerGroupedRow | null) {
  const amount = cleanText(row?.flowAmount);
  if (amount && amount !== "0.00") {
    return amount;
  }
  const borrowAmount = Number(String(row?.borrowAmount ?? "0").replace(/,/g, ""));
  if (borrowAmount > 0) {
    return row?.borrowAmount ?? "0.00";
  }
  return row?.repaymentAmount ?? "0.00";
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <h3 className="turnover-ledger-extra-section__title">{children}</h3>;
}

export default function TurnoverLedgerExtraDrawer({
  open,
  row,
  detail,
  extra,
  dirty,
  canMutateData,
  loading,
  saving,
  mutating,
  error,
  onClose,
  onExtraChange,
  onSave,
  onConfirm,
  onWithdraw,
}: {
  open: boolean;
  row: TurnoverLedgerGroupedRow | null;
  detail: TurnoverRelationDetail | null;
  extra: TurnoverLedgerExtra;
  dirty: boolean;
  canMutateData: boolean;
  loading: boolean;
  saving: boolean;
  mutating: boolean;
  error: string | null;
  onClose: () => void;
  onExtraChange: (next: TurnoverLedgerExtra) => void;
  onSave: () => void;
  onConfirm: () => void;
  onWithdraw: () => void;
}) {
  const relation = row;
  const canConfirm = canMutateData && relation?.status === "suggested";
  const canWithdraw = canMutateData && relation?.status === "confirmed";
  const counterpartyName = cleanText(row?.counterpartyName) || cleanText(detail?.bankRows[0]?.counterpartyName) || "-";
  const familyLabel = cleanText(row?.familyLabel) || "-";
  const dateText = flowDate(row);
  const subtitle = [counterpartyName, familyLabel, dateText].filter(Boolean).join(" / ");
  const bankAccountLabels = row?.bankAccountLabels?.length ? row.bankAccountLabels : (
    detail?.bankRows.map((bankRow) => bankRow.bankAccountLabel).filter(Boolean) ?? []
  );
  const primaryBankRowId = cleanText(row?.sourceBankRowId) || cleanText(row?.bankRowIds?.[0]) || cleanText(detail?.bankRows[0]?.id);
  const handleTextChange = (field: keyof TurnoverLedgerExtra) => (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    onExtraChange({ ...extra, [field]: event.target.value });
  };
  const handleRateTypeChange = (event: ChangeEvent<HTMLSelectElement>) => {
    onExtraChange({ ...extra, interestRateType: event.target.value });
  };

  return (
    <AppDrawer
      className="turnover-ledger-drawer"
      closeLabel="关闭"
      open={open}
      subtitle={subtitle || "未选择流水"}
      title="编辑流水补充信息"
      width={640}
      onClose={onClose}
      footer={(
        <div className="turnover-ledger-extra-footer">
          <div className="turnover-ledger-extra-footer__group">
            <button className="turnover-ledger-button" disabled={!canConfirm || mutating || Boolean(error)} onClick={onConfirm} type="button">
              确认归并
            </button>
            <button className="turnover-ledger-button turnover-ledger-button--warning" disabled={!canWithdraw || mutating || Boolean(error)} onClick={onWithdraw} type="button">
              撤销归并
            </button>
          </div>
          <button className="turnover-ledger-button turnover-ledger-button--primary" disabled={!dirty || saving || !canMutateData || Boolean(error)} onClick={onSave} type="button">
            保存补充信息
          </button>
        </div>
      )}
    >
        <div className="turnover-ledger-drawer__content turnover-ledger-extra-drawer__content">
          {loading ? (
            <div className="turnover-ledger-drawer__notice turnover-ledger-drawer__notice--info" role="status">正在加载关系详情和补充信息。</div>
          ) : null}
          {error ? <div className="turnover-ledger-drawer__notice turnover-ledger-drawer__notice--danger" role="alert">{error}</div> : null}
          {relation ? (
            <>
              <div className="turnover-ledger-chip-row turnover-ledger-extra-chip-row">
                <span className="turnover-ledger-chip turnover-ledger-chip--filled">{relation.statusLabel || relation.status || "-"}</span>
                <span className={`turnover-ledger-chip turnover-ledger-chip--outline ${flowDirectionLabel(row) === "支" ? "turnover-ledger-chip--expense" : "turnover-ledger-chip--income"}`}>
                  {flowDirectionLabel(row)}
                </span>
                <span className="turnover-ledger-chip turnover-ledger-chip--outline turnover-ledger-chip--amount">{formatMoney(flowAmount(row))}</span>
                {bankAccountLabels.map((label) => (
                  <span className="turnover-ledger-chip turnover-ledger-chip--outline" key={label}>{label}</span>
                ))}
              </div>

              <section className="turnover-ledger-extra-section">
                <SectionTitle>流水概览</SectionTitle>
                <div className="turnover-ledger-extra-grid">
                  <DetailField label="对方户名" value={counterpartyName} />
                  <DetailField label="往来类别" value={familyLabel} />
                  <DetailField label="流水编号" value={primaryBankRowId} />
                  <DetailField label="流水日期" value={dateText} />
                  <DetailField label="往来发生" value={formatMoney(relation.borrowAmount)} />
                  <DetailField label="结清发生" value={formatMoney(relation.repaymentAmount)} />
                  <DetailField label="借款天数" value={relation.loanDays} />
                  <DetailField label="应还利息" value={relation.accruedInterest ? formatMoney(relation.accruedInterest) : "-"} />
                </div>
                {(detail?.bankRows ?? []).length > 0 ? (
                  <div className="turnover-ledger-extra-bank-list">
                    {detail?.bankRows.map((bankRow) => (
                      <article className="turnover-ledger-extra-bank-card" key={bankRow.id}>
                        <div className="turnover-ledger-extra-bank-card__chips">
                          <strong>{bankRow.id}</strong>
                          <span className="turnover-ledger-chip turnover-ledger-chip--filled">{bankRow.directionLabel || "-"}</span>
                          <span className="turnover-ledger-chip turnover-ledger-chip--outline turnover-ledger-chip--amount">{formatMoney(bankRow.amount)}</span>
                          <span className="turnover-ledger-chip turnover-ledger-chip--outline">{bankRow.bankAccountLabel || "-"}</span>
                        </div>
                        <p>{bankRow.summary || "-"}</p>
                      </article>
                    ))}
                  </div>
                ) : null}
              </section>

              <section className="turnover-ledger-extra-section">
                <SectionTitle>补充信息</SectionTitle>
                <div className="turnover-ledger-extra-form">
                  <label className="turnover-ledger-extra-control">
                    <span>利率类型</span>
                    <select value={extra.interestRateType} onChange={handleRateTypeChange}>
                      <option value="none">不计息</option>
                      <option value="annual">年息</option>
                      <option value="monthly">月息</option>
                    </select>
                  </label>
                  <label className="turnover-ledger-extra-control">
                    <span>利率值</span>
                    <input value={extra.interestRateValue} onChange={handleTextChange("interestRateValue")} type="text" />
                  </label>
                  <label className="turnover-ledger-extra-control">
                    <span>已还利息额</span>
                    <input value={extra.interestPaidAmount} onChange={handleTextChange("interestPaidAmount")} type="text" />
                  </label>
                  <label className="turnover-ledger-extra-control">
                    <span>还利息日期</span>
                    <input placeholder="YYYY-MM-DD" value={extra.interestPaidDate ?? ""} onChange={handleTextChange("interestPaidDate")} type="text" />
                  </label>
                  <label className="turnover-ledger-extra-control">
                    <span>还利息方式</span>
                    <input value={extra.interestPaymentMethod} onChange={handleTextChange("interestPaymentMethod")} type="text" />
                  </label>
                  <label className="turnover-ledger-extra-control turnover-ledger-extra-control--wide">
                    <span>备注</span>
                    <textarea rows={2} value={extra.note} onChange={handleTextChange("note")} />
                  </label>
                </div>
              </section>

              <section className="turnover-ledger-extra-section">
                <SectionTitle>操作记录 / 关系操作</SectionTitle>
                <div className="turnover-ledger-chip-row turnover-ledger-extra-chip-row">
                  <span className="turnover-ledger-chip turnover-ledger-chip--outline">{`审计记录 ${detail?.auditHistory.length ?? 0} 条`}</span>
                  {extra.updatedAt ? <span className="turnover-ledger-chip turnover-ledger-chip--outline">{`更新于 ${extra.updatedAt}`}</span> : null}
                  {extra.updatedBy ? <span className="turnover-ledger-chip turnover-ledger-chip--outline">{`更新人 ${extra.updatedBy}`}</span> : null}
                </div>
              </section>
            </>
          ) : null}
        </div>
    </AppDrawer>
  );
}
