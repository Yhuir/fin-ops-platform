import { Alert, Button, Checkbox } from "@heroui/react";
import { useEffect, useMemo, useRef, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import {
  fetchWorkbenchReceiptDraft,
  printWorkbenchReceipt,
  resolveWorkbenchActionErrorMessage,
} from "../../features/workbench/api";
import type {
  WorkbenchReceiptDraft,
  WorkbenchReceiptDraftReceipt,
  WorkbenchReceiptLine,
} from "../../features/workbench/types";

type WorkbenchReceiptDrawerProps = {
  open: boolean;
  caseId: string | null;
  disabled?: boolean;
  onClose: () => void;
};

const receiptColumns = "8fr 7.125fr 9fr 3.5fr 7.5fr 3.625fr 8.5fr 7fr 18.25fr 13.5fr";

function cloneReceipts(receipts: WorkbenchReceiptDraftReceipt[]) {
  return receipts.map((receipt) => ({
    ...receipt,
    bankTransactionIds: [...receipt.bankTransactionIds],
    lines: receipt.lines.map((line) => ({
      ...line,
      sourceInvoiceIds: line.sourceInvoiceIds ? [...line.sourceInvoiceIds] : undefined,
    })),
  }));
}

function amountToCents(value: string) {
  const normalized = value.replace(/,/g, "").trim();
  if (!/^-?\d+(?:\.\d{1,2})?$/.test(normalized)) {
    return null;
  }
  const negative = normalized.startsWith("-");
  const unsigned = negative ? normalized.slice(1) : normalized;
  const [integer, fraction = ""] = unsigned.split(".");
  const cents = Number(integer) * 100 + Number(fraction.padEnd(2, "0"));
  if (!Number.isSafeInteger(cents)) {
    return null;
  }
  return negative ? -cents : cents;
}

function formatCents(cents: number) {
  return `${cents < 0 ? "-" : ""}${(Math.abs(cents) / 100).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function uppercaseRmb(cents: number) {
  if (!Number.isSafeInteger(cents) || cents < 0) {
    return "金额无效";
  }
  const digits = "零壹贰叁肆伍陆柒捌玖";
  const smallUnits = ["", "拾", "佰", "仟"];
  const largeUnits = ["", "万", "亿"];
  const integer = String(Math.floor(cents / 100));
  if (integer.length > 12) {
    return "金额超出范围";
  }
  const chunks: string[] = [];
  for (let end = integer.length; end > 0; end -= 4) {
    chunks.push(integer.slice(Math.max(0, end - 4), end));
  }
  const fourDigitText = (chunk: string) => {
    const padded = chunk.padStart(4, "0");
    const parts: string[] = [];
    let pendingZero = false;
    Array.from(padded).forEach((character, index) => {
      const digit = Number(character);
      const unitIndex = 3 - index;
      if (digit === 0) {
        pendingZero = parts.length > 0;
        return;
      }
      if (pendingZero) {
        parts.push("零");
        pendingZero = false;
      }
      parts.push(digits[digit], smallUnits[unitIndex]);
    });
    return parts.join("");
  };
  const integerParts: string[] = [];
  let zeroBetween = false;
  for (let groupIndex = chunks.length - 1; groupIndex >= 0; groupIndex -= 1) {
    const chunkValue = Number(chunks[groupIndex]);
    if (chunkValue === 0) {
      if (integerParts.length > 0) zeroBetween = true;
      continue;
    }
    if (integerParts.length > 0 && (zeroBetween || chunkValue < 1000)) {
      integerParts.push("零");
    }
    integerParts.push(`${fourDigitText(chunks[groupIndex])}${largeUnits[groupIndex]}`);
    zeroBetween = false;
  }
  const integerText = integerParts.join("") || "零";
  const jiao = Math.floor((cents % 100) / 10);
  const fen = cents % 10;
  const fraction = `${jiao ? `${digits[jiao]}角` : ""}${fen ? `${jiao ? "" : "零"}${digits[fen]}分` : ""}`;
  return `${integerText}元${fraction || "整"}`;
}

function validIsoDate(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime())
    && parsed.getUTCFullYear() === Number(match[1])
    && parsed.getUTCMonth() + 1 === Number(match[2])
    && parsed.getUTCDate() === Number(match[3]);
}

function receiptLineChunks(lines: WorkbenchReceiptLine[]) {
  const chunks: Array<Array<WorkbenchReceiptLine | null>> = [];
  const count = Math.max(1, Math.ceil(lines.length / 5));
  for (let pageIndex = 0; pageIndex < count; pageIndex += 1) {
    const chunk: Array<WorkbenchReceiptLine | null> = lines.slice(pageIndex * 5, pageIndex * 5 + 5);
    while (chunk.length < 5) chunk.push(null);
    chunks.push(chunk);
  }
  return chunks;
}

export default function WorkbenchReceiptDrawer({
  open,
  caseId,
  disabled = false,
  onClose,
}: WorkbenchReceiptDrawerProps) {
  const [draft, setDraft] = useState<WorkbenchReceiptDraft | null>(null);
  const [receipts, setReceipts] = useState<WorkbenchReceiptDraftReceipt[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [issuesAcknowledged, setIssuesAcknowledged] = useState(false);
  const requestSequenceRef = useRef(0);

  async function loadDraft() {
    if (!caseId) return;
    const sequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = sequence;
    setLoading(true);
    setDraft(null);
    setReceipts([]);
    setErrorMessage(null);
    setDirty(false);
    setIssuesAcknowledged(false);
    try {
      const result = await fetchWorkbenchReceiptDraft(caseId);
      if (requestSequenceRef.current !== sequence) return;
      setDraft(result);
      setReceipts(cloneReceipts(result.receipts));
    } catch (error) {
      if (requestSequenceRef.current !== sequence) return;
      setErrorMessage(resolveWorkbenchActionErrorMessage(error, "收据草稿加载失败，请稍后重试。"));
    } finally {
      if (requestSequenceRef.current === sequence) setLoading(false);
    }
  }

  useEffect(() => {
    if (!open || !caseId) {
      requestSequenceRef.current += 1;
      return;
    }
    void loadDraft();
  }, [caseId, open]);

  const validations = useMemo(() => receipts.map((receipt) => {
    const incomeCents = amountToCents(receipt.incomeAmount);
    const lineCents = receipt.lines.map((line) => amountToCents(line.amount));
    const totalCents = lineCents.every((value) => value !== null)
      ? lineCents.reduce<number>((total, value) => total + (value ?? 0), 0)
      : null;
    const fieldsValid = receipt.payer.trim().length > 0
      && validIsoDate(receipt.date)
      && receipt.lines.length > 0
      && receipt.lines.every((line, index) => (
        line.summary.trim().length > 0 && (lineCents[index] ?? 0) > 0
      ));
    return {
      incomeCents,
      totalCents,
      balanced: incomeCents !== null && totalCents === incomeCents,
      fieldsValid,
    };
  }), [receipts]);
  const issuesReady = !draft?.issues.length || issuesAcknowledged;
  const canPrint = Boolean(draft)
    && !disabled
    && !loading
    && !submitting
    && issuesReady
    && validations.length > 0
    && validations.every((validation) => validation.fieldsValid && validation.balanced);

  function updateReceipt(receiptIndex: number, update: (receipt: WorkbenchReceiptDraftReceipt) => WorkbenchReceiptDraftReceipt) {
    setReceipts((current) => current.map((receipt, index) => (
      index === receiptIndex ? update(receipt) : receipt
    )));
    setDirty(true);
    setErrorMessage(null);
  }

  function updateLine(receiptIndex: number, lineIndex: number, field: "summary" | "amount" | "note", value: string) {
    updateReceipt(receiptIndex, (receipt) => ({
      ...receipt,
      lines: receipt.lines.map((line, index) => index === lineIndex ? { ...line, [field]: value } : line),
    }));
  }

  function closeDrawer() {
    if (submitting) return;
    if (dirty && !window.confirm("收据内容尚未打印，确认关闭并放弃本次修改吗？")) {
      return;
    }
    onClose();
  }

  async function submitPrint() {
    if (!draft || !canPrint) return;
    const printWindow = window.open("", "_blank");
    if (!printWindow) {
      setErrorMessage("浏览器阻止了打印窗口，请允许此站点打开弹窗后重试。");
      return;
    }
    printWindow.document.write("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>正在生成收据</title><style>html,body{height:100%;margin:0;font-family:system-ui,sans-serif;color:#334155}body{display:grid;place-items:center;background:#f8fafc}</style></head><body>正在生成收据…</body></html>");
    printWindow.document.close();
    setSubmitting(true);
    setErrorMessage(null);
    try {
      const pdf = await printWorkbenchReceipt({
        caseId: draft.caseId,
        relationVersion: draft.relationVersion,
        sourceFingerprint: draft.sourceFingerprint,
        issuesAcknowledged,
        receipts: receipts.map((receipt) => ({
          receiptKey: receipt.receiptKey,
          payer: receipt.payer.trim(),
          date: receipt.date,
          handler: receipt.handler.trim(),
          supervisor: receipt.supervisor.trim(),
          lines: receipt.lines.map((line) => ({
            summary: line.summary.trim(),
            amount: line.amount.trim(),
            note: line.note.trim(),
          })),
        })),
      });
      const pdfUrl = URL.createObjectURL(pdf);
      printWindow.document.open();
      printWindow.document.write("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>打印收据</title><style>html,body,iframe{width:100%;height:100%;margin:0;border:0;overflow:hidden}</style></head><body><iframe id=\"receipt-pdf\" title=\"收据 PDF\"></iframe></body></html>");
      printWindow.document.close();
      const frame = printWindow.document.getElementById("receipt-pdf") as HTMLIFrameElement | null;
      if (!frame) throw new Error("打印窗口初始化失败。");
      frame.addEventListener("load", () => {
        window.setTimeout(() => {
          frame.contentWindow?.focus();
          frame.contentWindow?.print();
        }, 100);
      }, { once: true });
      frame.src = pdfUrl;
      printWindow.addEventListener("beforeunload", () => URL.revokeObjectURL(pdfUrl), { once: true });
      setDirty(false);
    } catch (error) {
      printWindow.close();
      setErrorMessage(resolveWorkbenchActionErrorMessage(error, "收据生成失败，请稍后重试。"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppDrawer
      ariaBusy={loading || submitting}
      className="workbench-receipt-drawer"
      closeDisabled={submitting}
      closeLabel="关闭收据编辑"
      footer={(
        <>
          <span className="workbench-receipt-drawer__footer-status">
            {submitting ? "正在生成 PDF…" : canPrint ? "金额已核对，可以打印" : "请完成收据核对"}
          </span>
          <Button isDisabled={submitting} onPress={closeDrawer} size="sm" variant="secondary">
            取消
          </Button>
          <Button isDisabled={!canPrint} isPending={submitting} onPress={() => { void submitPrint(); }} size="sm" variant="primary">
            打印收据
          </Button>
        </>
      )}
      onClose={closeDrawer}
      open={open}
      title="编辑收据"
      width="min(1120px, 100vw)"
    >
      <div className="workbench-receipt-drawer__body">
        {loading ? <div className="workbench-receipt-drawer__state" role="status">正在读取收据草稿…</div> : null}
        {!loading && errorMessage ? (
          <Alert className="workbench-receipt-drawer__alert" color="danger" role="alert">
            <span>{errorMessage}</span>
            {!draft ? <Button onPress={() => { void loadDraft(); }} size="sm" variant="secondary">重新加载</Button> : null}
          </Alert>
        ) : null}
        {draft?.reversalAdjustments.length ? (
          <Alert className="workbench-receipt-drawer__alert" color="success" role="status">
            已依据红票备注中的明确蓝票号码处理 {draft.reversalAdjustments.length} 组冲销；完全冲销不进入明细，部分冲销仅保留净额。
          </Alert>
        ) : null}
        {draft?.issues.length ? (
          <Alert className="workbench-receipt-drawer__alert" color="warning" role="alert">
            <div className="workbench-receipt-drawer__issues">
              {draft.issues.map((issue) => <p key={`${issue.code}-${issue.message}`}>{issue.message}</p>)}
              <Checkbox
                isSelected={issuesAcknowledged}
                onChange={(selected) => {
                  setIssuesAcknowledged(selected);
                  setDirty(true);
                }}
              >
                <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                我已人工核对并修正上述冲销异常
              </Checkbox>
            </div>
          </Alert>
        ) : null}

        {draft ? receipts.map((receipt, receiptIndex) => {
          const validation = validations[receiptIndex];
          const dateParts = receipt.date.split("-");
          const chunks = receiptLineChunks(receipt.lines);
          const difference = validation.incomeCents !== null && validation.totalCents !== null
            ? validation.incomeCents - validation.totalCents
            : null;
          return (
            <section className="workbench-receipt-editor" key={receipt.receiptKey}>
              <header className="workbench-receipt-editor__toolbar">
                <div>
                  <strong>{receipts.length > 1 ? `第 ${receiptIndex + 1} 张收据` : "收据预览"}</strong>
                  <span>收入金额 ¥{receipt.incomeAmount}</span>
                </div>
                <Button
                  onPress={() => updateReceipt(receiptIndex, (current) => ({
                    ...current,
                    lines: [...current.lines, { summary: "", amount: "", note: "" }],
                  }))}
                  size="sm"
                  variant="secondary"
                >
                  添加明细
                </Button>
              </header>

              {chunks.map((chunk, pageIndex) => (
                <div className="receipt-paper" key={`${receipt.receiptKey}-page-${pageIndex + 1}`}>
                  <div className="receipt-paper__grid" style={{ gridTemplateColumns: receiptColumns }}>
                    <div className="receipt-paper__cell receipt-paper__title" style={{ gridColumn: "1 / 11", gridRow: 1 }}>云南溯源科技有限公司</div>
                    <div className="receipt-paper__cell receipt-paper__title" style={{ gridColumn: "1 / 11", gridRow: 2 }}>收&nbsp;&nbsp;&nbsp;&nbsp;据</div>
                    <div className="receipt-paper__cell receipt-paper__date" style={{ gridColumn: 3, gridRow: 3 }}>
                      <input aria-label={`收据 ${receiptIndex + 1} 年`} inputMode="numeric" maxLength={4} value={dateParts[0] ?? ""} onChange={(event) => {
                        const next = [event.target.value.replace(/\D/g, "").slice(0, 4), dateParts[1] ?? "", dateParts[2] ?? ""];
                        updateReceipt(receiptIndex, (current) => ({ ...current, date: next.join("-") }));
                      }} />
                    </div>
                    <div className="receipt-paper__cell receipt-paper__date" style={{ gridColumn: 4, gridRow: 3 }}>年</div>
                    <div className="receipt-paper__cell receipt-paper__date" style={{ gridColumn: 5, gridRow: 3 }}>
                      <input aria-label={`收据 ${receiptIndex + 1} 月`} inputMode="numeric" maxLength={2} value={dateParts[1] ?? ""} onChange={(event) => {
                        const next = [dateParts[0] ?? "", event.target.value.replace(/\D/g, "").slice(0, 2), dateParts[2] ?? ""];
                        updateReceipt(receiptIndex, (current) => ({ ...current, date: next.join("-") }));
                      }} />
                    </div>
                    <div className="receipt-paper__cell receipt-paper__date" style={{ gridColumn: 6, gridRow: 3 }}>月</div>
                    <div className="receipt-paper__cell receipt-paper__date" style={{ gridColumn: 7, gridRow: 3 }}>
                      <input aria-label={`收据 ${receiptIndex + 1} 日`} inputMode="numeric" maxLength={2} value={dateParts[2] ?? ""} onChange={(event) => {
                        const next = [dateParts[0] ?? "", dateParts[1] ?? "", event.target.value.replace(/\D/g, "").slice(0, 2)];
                        updateReceipt(receiptIndex, (current) => ({ ...current, date: next.join("-") }));
                      }} />
                    </div>
                    <div className="receipt-paper__cell receipt-paper__date" style={{ gridColumn: 8, gridRow: 3 }}>日</div>
                    {chunks.length > 1 ? <div className="receipt-paper__page-number" style={{ gridColumn: "9 / 11", gridRow: 3 }}>第 {pageIndex + 1}/{chunks.length} 页</div> : null}

                    <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--top receipt-paper__table--left" style={{ gridColumn: 1, gridRow: 4 }}>兹收到</div>
                    <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--top" style={{ gridColumn: "2 / 9", gridRow: 4 }}>
                      <input aria-label={`收据 ${receiptIndex + 1} 付款单位`} value={receipt.payer} onChange={(event) => updateReceipt(receiptIndex, (current) => ({ ...current, payer: event.target.value }))} />
                    </div>
                    <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--top receipt-paper__table--right" style={{ gridColumn: "9 / 11", gridRow: 4 }}>交来下列款项</div>
                    <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--left receipt-paper__heading" style={{ gridColumn: "1 / 9", gridRow: 5 }}>摘&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;要</div>
                    <div className="receipt-paper__cell receipt-paper__table receipt-paper__heading" style={{ gridColumn: 9, gridRow: 5 }}>金额</div>
                    <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--right receipt-paper__heading" style={{ gridColumn: 10, gridRow: 5 }}>备注</div>

                    {chunk.map((line, chunkIndex) => {
                      const lineIndex = pageIndex * 5 + chunkIndex;
                      const row = 6 + chunkIndex;
                      return line ? [
                        <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--left receipt-paper__editable-cell" key={`summary-${lineIndex}`} style={{ gridColumn: "1 / 9", gridRow: row }}>
                          <input aria-label={`收据 ${receiptIndex + 1} 明细 ${lineIndex + 1} 摘要`} value={line.summary} onChange={(event) => updateLine(receiptIndex, lineIndex, "summary", event.target.value)} />
                          <button aria-label={`删除收据 ${receiptIndex + 1} 明细 ${lineIndex + 1}`} className="receipt-paper__remove-line" onClick={() => updateReceipt(receiptIndex, (current) => ({ ...current, lines: current.lines.filter((_, index) => index !== lineIndex) }))} type="button">×</button>
                        </div>,
                        <div className="receipt-paper__cell receipt-paper__table" key={`amount-${lineIndex}`} style={{ gridColumn: 9, gridRow: row }}>
                          <input aria-label={`收据 ${receiptIndex + 1} 明细 ${lineIndex + 1} 金额`} className="receipt-paper__money-input" inputMode="decimal" value={line.amount} onChange={(event) => updateLine(receiptIndex, lineIndex, "amount", event.target.value)} />
                        </div>,
                        <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--right" key={`note-${lineIndex}`} style={{ gridColumn: 10, gridRow: row }}>
                          <input aria-label={`收据 ${receiptIndex + 1} 明细 ${lineIndex + 1} 备注`} value={line.note} onChange={(event) => updateLine(receiptIndex, lineIndex, "note", event.target.value)} />
                        </div>,
                      ] : [
                        <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--left" key={`empty-summary-${chunkIndex}`} style={{ gridColumn: "1 / 9", gridRow: row }} />,
                        <div className="receipt-paper__cell receipt-paper__table" key={`empty-amount-${chunkIndex}`} style={{ gridColumn: 9, gridRow: row }} />,
                        <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--right" key={`empty-note-${chunkIndex}`} style={{ gridColumn: 10, gridRow: row }} />,
                      ];
                    })}

                    <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--left receipt-paper__table--bottom receipt-paper__total-label" style={{ gridColumn: 1, gridRow: 11 }}>{pageIndex === chunks.length - 1 ? "合计：" : "续页："}</div>
                    {pageIndex === chunks.length - 1 ? <>
                      <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--bottom" style={{ gridColumn: 2, gridRow: 11 }}>人民币</div>
                      <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--bottom receipt-paper__uppercase" style={{ gridColumn: "3 / 9", gridRow: 11 }}>{validation.totalCents === null ? "金额无效" : uppercaseRmb(validation.totalCents)}</div>
                      <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--bottom receipt-paper__total-money" style={{ gridColumn: 9, gridRow: 11 }}>¥{validation.totalCents === null ? "—" : formatCents(validation.totalCents)}</div>
                      <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--right receipt-paper__table--bottom" style={{ gridColumn: 10, gridRow: 11 }} />
                    </> : <div className="receipt-paper__cell receipt-paper__table receipt-paper__table--right receipt-paper__table--bottom" style={{ gridColumn: "2 / 11", gridRow: 11 }} />}
                    <div className="receipt-paper__cell receipt-paper__signature" style={{ gridColumn: "1 / 5", gridRow: 12 }}>
                      <span>主管：</span><input aria-label={`收据 ${receiptIndex + 1} 主管`} value={receipt.supervisor} onChange={(event) => updateReceipt(receiptIndex, (current) => ({ ...current, supervisor: event.target.value }))} />
                    </div>
                    <div className="receipt-paper__cell receipt-paper__signature" style={{ gridColumn: "7 / 11", gridRow: 12 }}>
                      <span>经手人：</span><input aria-label={`收据 ${receiptIndex + 1} 经手人`} value={receipt.handler} onChange={(event) => updateReceipt(receiptIndex, (current) => ({ ...current, handler: event.target.value }))} />
                    </div>
                  </div>
                </div>
              ))}

              <div className={`workbench-receipt-editor__balance ${validation.balanced && validation.fieldsValid ? "is-balanced" : "is-unbalanced"}`} role="status">
                {validation.totalCents === null || validation.incomeCents === null
                  ? "请输入有效金额（最多两位小数）。"
                  : validation.balanced
                    ? `明细合计 ¥${formatCents(validation.totalCents)}，与收入金额一致。`
                    : `明细与收入相差 ¥${formatCents(difference ?? 0)}，调整一致后才能打印。`}
              </div>
            </section>
          );
        }) : null}
      </div>
    </AppDrawer>
  );
}
