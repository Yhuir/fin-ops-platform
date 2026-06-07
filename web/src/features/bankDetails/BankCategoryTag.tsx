import { useState } from "react";

import { getBankCategoryToneClass, splitBankCategoryLabel } from "./categoryOptions";
import type { BankTransactionCategoryCode } from "./types";

type BankCategoryTagProps = {
  categoryCode: BankTransactionCategoryCode | null;
  label: string;
  count?: number;
  className?: string;
  compact?: boolean;
  hierarchyTooltip?: boolean;
};

export default function BankCategoryTag({
  categoryCode,
  label,
  count,
  className,
  compact = false,
  hierarchyTooltip = true,
}: BankCategoryTagProps) {
  const labelLines = splitBankCategoryLabel(label);
  const displayLabel = count === undefined ? label : `${label} ${count}`;
  const hierarchyParts = categoryHierarchyParts(label);
  const [tooltipOpen, setTooltipOpen] = useState(false);
  const tooltipId = `bank-category-hierarchy-${categoryCode ?? "empty"}-${displayLabel.replace(/\s+/g, "-")}`;

  const chip = (
    <span
      aria-label={displayLabel}
      className={[
        "bank-category-tag",
        "bank-chip-auto-size",
        getBankCategoryToneClass(categoryCode),
        compact ? "compact" : "",
        className ?? "",
      ].filter(Boolean).join(" ")}
    >
      <span className="bank-category-tag-label">
        {labelLines.map((line, index) => (
          <span className="bank-category-tag-line" key={`${line}-${index}`}>
            {index === labelLines.length - 1 && count !== undefined ? `${line} ${count}` : line}
          </span>
        ))}
      </span>
    </span>
  );
  if (!hierarchyTooltip || hierarchyParts.length < 2) {
    return chip;
  }
  return (
    <span
      aria-describedby={tooltipOpen ? tooltipId : undefined}
      className="bank-category-hierarchy-tooltip-anchor"
      onBlur={() => setTooltipOpen(false)}
      onFocus={() => setTooltipOpen(true)}
      onMouseEnter={() => setTooltipOpen(true)}
      onMouseLeave={() => setTooltipOpen(false)}
      tabIndex={0}
    >
      {chip}
      {tooltipOpen ? <CategoryHierarchyTooltip id={tooltipId} parts={hierarchyParts} count={count} /> : null}
    </span>
  );
}

function categoryHierarchyParts(label: string) {
  const slashParts = label.split(/\s*\/\s*/).map((part) => part.trim()).filter(Boolean);
  if (slashParts.length > 1) {
    return slashParts;
  }
  const colonIndex = label.indexOf("：");
  if (colonIndex > 0 && colonIndex < label.length - 1) {
    return [label.slice(0, colonIndex).trim(), label.slice(colonIndex + 1).trim()].filter(Boolean);
  }
  return [label.trim()].filter(Boolean);
}

function CategoryHierarchyTooltip({ id, parts, count }: { id: string; parts: string[]; count?: number }) {
  return (
    <span className="bank-category-hierarchy-tooltip" id={id} role="tooltip">
      <span className="bank-category-hierarchy-title">
        {parts.join(" / ")}{count === undefined ? "" : ` ${count}`}
      </span>
      <span className="bank-category-hierarchy-tree">
        {parts.map((part, index) => (
          <span className="bank-category-hierarchy-row" key={`${part}-${index}`}>
            <span className="bank-category-hierarchy-branch" aria-hidden="true">
              {index === 0 ? "*" : "-"}
            </span>
            <span className="bank-category-hierarchy-node">
              {part}
            </span>
          </span>
        ))}
      </span>
    </span>
  );
}
