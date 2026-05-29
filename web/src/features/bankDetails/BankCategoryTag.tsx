import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

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

  const chip = (
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
  if (!hierarchyTooltip || hierarchyParts.length < 2) {
    return chip;
  }
  return (
    <Tooltip
      arrow
      placement="top"
      title={<CategoryHierarchyTooltip parts={hierarchyParts} count={count} />}
    >
      {chip}
    </Tooltip>
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

function CategoryHierarchyTooltip({ parts, count }: { parts: string[]; count?: number }) {
  return (
    <Box className="bank-category-hierarchy-tooltip">
      <Typography className="bank-category-hierarchy-title" variant="caption" color="inherit">
        {parts.join(" / ")}{count === undefined ? "" : ` ${count}`}
      </Typography>
      <Box className="bank-category-hierarchy-tree">
        {parts.map((part, index) => (
          <Box className="bank-category-hierarchy-row" key={`${part}-${index}`}>
            <Box className="bank-category-hierarchy-branch" aria-hidden="true">
              {index === 0 ? "*" : "-"}
            </Box>
            <Typography className="bank-category-hierarchy-node" variant="caption" color="inherit">
              {part}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
