import { useMemo, useState } from "react";

import type { WorkbenchRecord } from "../../features/workbench/types";
import { buildOaBankExceptionOptions } from "../../features/workbench/oaBankExceptionOptions";

type OaBankExceptionModalProps = {
  rows: WorkbenchRecord[];
  onClose: () => void;
  onConfirmLink: () => void;
  onSubmitException: (payload: {
    exceptionCode: string;
    exceptionLabel: string;
    comment: string;
  }) => void;
};

export default function OaBankExceptionModal({
  rows,
  onClose,
  onConfirmLink,
  onSubmitException,
}: OaBankExceptionModalProps) {
  const [selectedCode, setSelectedCode] = useState("");
  const [comment, setComment] = useState("");

  const summary = useMemo(() => {
    const oaRows = rows.filter((row) => row.recordType === "oa");
    const bankRows = rows.filter((row) => row.recordType === "bank");
    const invoiceRows = rows.filter((row) => row.recordType === "invoice");
    const oaTotal = oaRows.reduce((total, row) => total + parseAmount(row.amount), 0);
    const bankTotal = bankRows.reduce((total, row) => total + parseAmount(row.amount), 0);
    return {
      oaCount: oaRows.length,
      bankCount: bankRows.length,
      invoiceCount: invoiceRows.length,
      oaTotal,
      bankTotal,
      differenceAmount: oaTotal - bankTotal,
    };
  }, [rows]);

  const optionState = useMemo(
    () =>
      buildOaBankExceptionOptions({
        oaCount: summary.oaCount,
        bankCount: summary.bankCount,
        invoiceCount: summary.invoiceCount,
      }),
    [summary.bankCount, summary.invoiceCount, summary.oaCount],
  );

  const selectedOption = optionState.options.find((option) => option.code === selectedCode) ?? null;
  const showEquation = summary.oaCount > 0 && summary.bankCount > 0;
  const submitLabel = showEquation ? "继续报异常" : "提交异常";

  return (
    <div aria-label="OA流水异常处理弹窗" aria-modal="true" className="detail-modal-backdrop" role="dialog">
      <div className="detail-modal oa-bank-exception-modal" onClick={(event) => event.stopPropagation()}>
        <header className="detail-modal-header">
          <div>
            <h2>OA/流水异常处理</h2>
            <p>为当前选中的 OA 与银行流水记录选择异常类型，并决定继续异常还是直接配对。</p>
          </div>
          <button aria-label="关闭OA流水异常处理弹窗" className="detail-close-btn" type="button" onClick={onClose}>
            关闭
          </button>
        </header>

        <div className="detail-modal-body">
          <div className="oa-bank-exception-summary">
            <span className="zone-selection-pill">OA {summary.oaCount}</span>
            <span className="zone-selection-pill">流水 {summary.bankCount}</span>
          </div>

          {showEquation ? (
            <div className="oa-bank-equation-card">
              <div className="oa-bank-equation-row">
                <span>OA合计</span>
                <strong>{formatAmount(summary.oaTotal)}</strong>
              </div>
              <div className="oa-bank-equation-row">
                <span>流水合计</span>
                <strong>{formatAmount(summary.bankTotal)}</strong>
              </div>
              <div className="oa-bank-equation-row">
                <span>差额</span>
                <strong>{formatAmount(summary.differenceAmount)}</strong>
              </div>
            </div>
          ) : null}

          <label className="field-block">
            <span className="field-label">异常情况</span>
            <select
              aria-label="异常情况"
              className="field-select"
              value={selectedCode}
              onChange={(event) => setSelectedCode(event.target.value)}
            >
              <option value="">请选择异常情况</option>
              {optionState.options.map((option) => (
                <option key={option.code} value={option.code}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field-block">
            <span className="field-label">备注</span>
            <textarea
              aria-label="备注"
              className="field-textarea"
              placeholder="可补充金额差异原因、拆分/合并说明、后续跟进意见"
              rows={3}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
        </div>

        <div className="detail-modal-footer">
          <button className="secondary-button" type="button" onClick={onClose}>
            取消
          </button>
          {selectedOption?.flow === "split_merge" ? (
            <>
              <button
                className="secondary-button warning-button"
                type="button"
                onClick={() =>
                  onSubmitException({
                    exceptionCode: selectedOption.code,
                    exceptionLabel: selectedOption.label,
                    comment,
                  })
                }
              >
                继续报异常
              </button>
              <button className="primary-button" type="button" onClick={onConfirmLink}>
                确认配对
              </button>
            </>
          ) : (
            <button
              className="primary-button"
              disabled={selectedOption === null}
              type="button"
              onClick={() =>
                selectedOption
                  ? onSubmitException({
                      exceptionCode: selectedOption.code,
                      exceptionLabel: selectedOption.label,
                      comment,
                    })
                  : undefined
              }
            >
              {submitLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function parseAmount(rawValue: string) {
  const normalized = rawValue.replace(/,/g, "").trim();
  const value = Number(normalized);
  return Number.isFinite(value) ? value : 0;
}

function formatAmount(value: number) {
  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}
