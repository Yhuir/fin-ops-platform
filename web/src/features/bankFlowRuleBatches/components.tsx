import { ChevronLeft, ChevronRight } from "lucide-react";

import type { BankFlowRuleBatchStatus } from "./types";
import { cx } from "./viewModel";

type BatchStatusMeta = { label: string; color: "default" | "primary" | "success" | "warning" | "error" };

const STATUS_META: Record<BankFlowRuleBatchStatus | "unsubmitted", BatchStatusMeta> = {
  draft: { label: "待提交", color: "warning" },
  unsubmitted: { label: "待提交", color: "warning" },
  submitted: { label: "已提交", color: "success" },
  withdrawn: { label: "已撤回", color: "default" },
};

export function PageControls({
  disabled,
  label,
  onNext,
  onPrevious,
  page,
  pageSize,
  total,
}: {
  disabled?: boolean;
  label: string;
  onNext: () => void;
  onPrevious: () => void;
  page: number;
  pageSize: number;
  total: number;
}) {
  const pageCount = Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
  return (
    <div aria-label={label} className="bank-flow-rule-batches-pagination" role="group">
      <span className="bank-flow-rule-batches-pagination__summary">第 {page} / {pageCount} 页 · 每页 {pageSize} 批次</span>
      <button
        aria-label={`${label}上一页`}
        className="bank-flow-rule-batches-pagination__button"
        disabled={disabled || page <= 1}
        onClick={onPrevious}
        title={`${label}上一页`}
        type="button"
      >
        <ChevronLeft aria-hidden="true" size={15} strokeWidth={2.4} />
      </button>
      <button
        aria-label={`${label}下一页`}
        className="bank-flow-rule-batches-pagination__button"
        disabled={disabled || page >= pageCount}
        onClick={onNext}
        title={`${label}下一页`}
        type="button"
      >
        <ChevronRight aria-hidden="true" size={15} strokeWidth={2.4} />
      </button>
    </div>
  );
}

export function BatchStatusTag({ status }: { status: string }) {
  const meta = STATUS_META[status as keyof typeof STATUS_META] ?? { label: status, color: "default" as const };
  return (
    <span className={cx("bank-flow-rule-batches-status", `bank-flow-rule-batches-status--${meta.color}`)}>
      {meta.label}
    </span>
  );
}
