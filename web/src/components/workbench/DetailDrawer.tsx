import { useEffect } from "react";
import { createPortal } from "react-dom";

import BankAccountValue from "../BankAccountValue";
import DirectionTag from "../DirectionTag";
import type { WorkbenchRecord } from "../../features/workbench/types";
import { workbenchColumns } from "../../features/workbench/tableConfig";

type DetailDrawerProps = {
  row: WorkbenchRecord | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
};

const drawerTitles: Record<WorkbenchRecord["recordType"], string> = {
  oa: "OA详情",
  bank: "银行流水详情",
  invoice: "发票详情",
};

export default function DetailDrawer({ row, loading, error, onClose }: DetailDrawerProps) {
  useEffect(() => {
    if (!row) {
      return undefined;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [row, onClose]);

  if (!row) {
    return null;
  }

  const summaryColumns = workbenchColumns[row.recordType];
  const content = (
    <div
      aria-label="详情弹窗"
      aria-modal="true"
      className="detail-modal-backdrop detail-modal-backdrop-foreground"
      role="dialog"
      onClick={onClose}
    >
      <div className="detail-modal" onClick={(event) => event.stopPropagation()}>
        <div className="detail-drawer-header">
          <div>
            <div className="detail-drawer-title">{drawerTitles[row.recordType]}</div>
            <div className="detail-drawer-subtitle">
              记录编号：{row.id}
              {row.caseId ? ` ｜ 案例：${row.caseId}` : ""}
            </div>
          </div>
          <button className="detail-close-btn" type="button" onClick={onClose} aria-label="关闭详情">
            关闭
          </button>
        </div>

        <div className="detail-drawer-body">
          {loading ? <div className="detail-state-panel">正在加载详情...</div> : null}
          {error ? <div className="detail-state-panel error">{error}</div> : null}
          <div className="detail-summary">
            <div className="detail-summary-label">主表字段</div>
            <dl className="detail-list">
              <div>
                <dt>记录类型</dt>
                <dd>{row.label}</dd>
              </div>
              <div>
                <dt>当前状态</dt>
                <dd>{row.status}</dd>
              </div>
              {summaryColumns.map((column) => (
                <div key={column.key}>
                  <dt>{column.label}</dt>
                  <dd>{renderSummaryValue(row, column.key)}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="detail-summary">
            <div className="detail-summary-label">详情字段</div>
            <dl className="detail-list">
              {row.detailFields.length === 0 ? (
                <div>
                  <dt>详情状态</dt>
                  <dd>{loading ? "详情加载中" : error ? "详情加载失败" : "暂无更多详情"}</dd>
                </div>
              ) : (
                row.detailFields.map((field) => (
                  <div key={field.label}>
                    <dt>{field.label}</dt>
                    <dd>{renderDetailFieldValue(field.label, field.value)}</dd>
                  </div>
                ))
              )}
            </dl>
          </div>
        </div>
      </div>
    </div>
  );

  if (typeof document === "undefined") {
    return content;
  }

  return createPortal(content, document.body);
}

function renderSummaryValue(row: WorkbenchRecord, key: string) {
  const value = row.tableValues[key] ?? "--";
  if (row.recordType === "bank" && key === "amount") {
    const direction = resolveDirectionForMoneyCell(row.tableValues.direction ?? "", value);
    const hasValue = value !== "--" && value !== "—" && value !== "";
    const paymentAccount = row.tableValues.paymentAccount ?? "";
    const shouldShowAccount = hasValue && paymentAccount !== "--" && paymentAccount !== "—" && paymentAccount !== "";
    return (
      <span className="money-cell-stack money-detail-stack">
        <span className="money-detail-value">
          <span>{hasValue ? value : "--"}</span>
        </span>
        {(Boolean(hasValue && direction) || shouldShowAccount) ? (
          <span className="money-cell-meta-row">
            {hasValue && direction ? <DirectionTag direction={direction} /> : null}
            {shouldShowAccount ? (
              <span className="money-cell-account">
                <BankAccountValue value={paymentAccount} variant="tag" />
              </span>
            ) : null}
          </span>
        ) : null}
      </span>
    );
  }
  return value;
}

function renderDetailFieldValue(label: string, value: string) {
  if (label === "支付账户" || label === "收款账户") {
    return <BankAccountValue value={value} variant="tag" />;
  }
  return value;
}

function resolveDirectionForMoneyCell(direction: string, value: string) {
  const hasValue = value !== "--" && value !== "—" && value !== "";
  if (!hasValue) {
    return null;
  }
  if (direction === "支出" || direction === "收入") {
    return direction;
  }
  return null;
}
