import type { KeyboardEvent } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import StatePanel from "../../components/common/StatePanel";
import type { BankFlowRuleBatchStatus } from "./types";
import { cx, formatCountMeta, pageRange } from "./viewModel";

type BatchStatusMeta = { label: string; color: "default" | "primary" | "success" | "warning" | "error" };

const STATUS_META: Record<BankFlowRuleBatchStatus | "unsubmitted", BatchStatusMeta> = {
  draft: { label: "待提交", color: "warning" },
  unsubmitted: { label: "待提交", color: "warning" },
  submitted: { label: "已提交", color: "success" },
  withdrawn: { label: "已撤回", color: "default" },
};

function handleButtonKeyDown(event: KeyboardEvent<HTMLElement>, action: () => void) {
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }
  event.preventDefault();
  action();
}

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
      <span className="bank-flow-rule-batches-pagination__summary">{pageRange(page, pageSize, total)}</span>
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

export type LabelRailGroup = {
  key: string;
  label: string;
  batchCount: number;
  rowCount: number;
};

export function LabelRail({
  title,
  subtitle,
  ariaLabel,
  emptyTitle,
  groups,
  selectedKey,
  onSelect,
}: {
  title: string;
  subtitle?: string;
  ariaLabel: string;
  emptyTitle: string;
  groups: LabelRailGroup[];
  selectedKey: string;
  onSelect: (key: string) => void;
}) {
  return (
    <section aria-label={ariaLabel} className="bank-flow-rule-batches-rail" role="region">
      <header className="bank-flow-rule-batches-rail__header">
        <h2 className="bank-flow-rule-batches-rail__title">{title}</h2>
        {subtitle ? <p className="bank-flow-rule-batches-rail__subtitle">{subtitle}</p> : null}
      </header>
      {groups.length === 0 ? (
        <div className="bank-flow-rule-batches-rail__empty">
          <StatePanel compact tone="empty" title={emptyTitle} />
        </div>
      ) : (
        <div className="bank-flow-rule-batches-rail__list">
          {groups.map((group) => {
            const selected = selectedKey === group.key;
            const countMeta = formatCountMeta(group.batchCount, group.rowCount);
            const isEmpty = group.batchCount === 0 && group.rowCount === 0;
            return (
              <button
                aria-label={`${group.label} ${countMeta}`}
                aria-pressed={selected}
                className={cx(
                  "bank-flow-rule-batches-rail__item",
                  selected && "bank-flow-rule-batches-rail__item--active",
                )}
                key={group.key}
                onClick={() => onSelect(group.key)}
                onKeyDown={(event) => handleButtonKeyDown(event, () => onSelect(group.key))}
                type="button"
              >
                <span className="bank-flow-rule-batches-rail__item-label" title={group.label}>
                  {group.label}
                </span>
                <span
                  className={cx(
                    "bank-flow-rule-batches-rail__item-count",
                    isEmpty && "bank-flow-rule-batches-rail__item-count--empty",
                  )}
                >
                  {countMeta}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
