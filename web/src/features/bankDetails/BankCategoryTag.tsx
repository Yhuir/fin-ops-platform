import Chip from "@mui/material/Chip";

import { getBankCategoryToneClass, splitBankCategoryLabel } from "./categoryOptions";
import type { BankTransactionCategoryCode } from "./types";

type BankCategoryTagProps = {
  categoryCode: BankTransactionCategoryCode | null;
  label: string;
  count?: number;
  className?: string;
  compact?: boolean;
};

export default function BankCategoryTag({
  categoryCode,
  label,
  count,
  className,
  compact = false,
}: BankCategoryTagProps) {
  const labelLines = splitBankCategoryLabel(label);
  const displayLabel = count === undefined ? label : `${label} ${count}`;

  return (
    <Chip
      className={[
        "bank-category-tag",
        "bank-chip-auto-size",
        getBankCategoryToneClass(categoryCode),
        compact ? "compact" : "",
        className ?? "",
      ].filter(Boolean).join(" ")}
      label={(
        <span className="bank-category-tag-label" aria-label={displayLabel}>
          {labelLines.map((line, index) => (
            <span className="bank-category-tag-line" key={`${line}-${index}`}>
              {index === labelLines.length - 1 && count !== undefined ? `${line} ${count}` : line}
            </span>
          ))}
        </span>
      )}
      size="small"
      variant="outlined"
    />
  );
}
