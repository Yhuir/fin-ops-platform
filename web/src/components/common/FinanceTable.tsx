import { Chip, Pagination, Table, Tooltip } from "@heroui/react";
import type { CSSProperties, ReactNode, Ref } from "react";

export type FinanceTableColumnRole =
  | "identity"
  | "amount"
  | "quantity"
  | "date"
  | "status"
  | "direction"
  | "account"
  | "description"
  | "selection"
  | "action"
  | "audit-meta";

export type FinanceTone = "neutral" | "info" | "success" | "warning" | "danger";

type FinanceTableStyle = CSSProperties & {
  "--finance-table-min-width"?: string;
};

function cx(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
}

function toneToChipColor(tone: FinanceTone) {
  if (tone === "info") {
    return "accent";
  }
  if (tone === "danger") {
    return "danger";
  }
  if (tone === "success") {
    return "success";
  }
  if (tone === "warning") {
    return "warning";
  }
  return "default";
}

type FinanceTableProps = {
  ariaLabel: string;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  minWidth?: number | string;
  scrollRef?: Ref<HTMLDivElement>;
};

export function FinanceTable({ ariaLabel, children, footer, className, minWidth = 720, scrollRef }: FinanceTableProps) {
  const style: FinanceTableStyle = {
    "--finance-table-min-width": typeof minWidth === "number" ? `${minWidth}px` : minWidth,
  };

  return (
    <Table className={cx("finance-table", className)}>
      <Table.ScrollContainer ref={scrollRef} className="finance-table__scroll">
        <Table.Content aria-label={ariaLabel} className="finance-table__content" style={style}>
          {children}
        </Table.Content>
      </Table.ScrollContainer>
      {footer ? <Table.Footer className="finance-table__footer">{footer}</Table.Footer> : null}
    </Table>
  );
}

type FinanceTableColumnProps = {
  children: ReactNode;
  columnRole?: FinanceTableColumnRole;
  className?: string;
  id?: string;
  isRowHeader?: boolean;
  allowsSorting?: boolean;
};

export function FinanceTableColumn({
  children,
  columnRole,
  className,
  id,
  isRowHeader,
  allowsSorting,
}: FinanceTableColumnProps) {
  return (
    <Table.Column
      allowsSorting={allowsSorting}
      className={cx("finance-table__column", columnRole && "finance-table__column--role", className)}
      data-column-role={columnRole}
      id={id}
      isRowHeader={isRowHeader}
    >
      {children}
    </Table.Column>
  );
}

type FinanceTableCellProps = {
  children: ReactNode;
  columnRole: FinanceTableColumnRole;
  className?: string;
  dataTone?: string;
  textValue?: string;
};

export function FinanceTableCell({ children, columnRole, className, dataTone, textValue }: FinanceTableCellProps) {
  return (
    <Table.Cell
      className={cx("finance-table__cell", className)}
      data-column-role={columnRole}
      data-tone={dataTone}
      textValue={textValue}
    >
      {children}
    </Table.Cell>
  );
}

export const FinanceTableHeader = Table.Header;
export const FinanceTableBody = Table.Body;

type FinanceTableRowProps = {
  children: ReactNode;
  id?: string | number;
  className?: string;
  dataCertifiedHighlighted?: boolean;
  textValue?: string;
};

export function FinanceTableRow({ children, id, className, dataCertifiedHighlighted, textValue }: FinanceTableRowProps) {
  return (
    <Table.Row
      className={cx("finance-table__row", className)}
      data-certified-highlighted={dataCertifiedHighlighted === undefined ? undefined : String(dataCertifiedHighlighted)}
      id={id}
      textValue={textValue}
    >
      {children}
    </Table.Row>
  );
}

type FinanceTablePaginationProps = {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  className?: string;
};

export function FinanceTablePagination({
  page,
  pageSize,
  total,
  onPageChange,
  className,
}: FinanceTablePaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  const start = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const end = Math.min(currentPage * pageSize, total);
  const pages = Array.from({ length: totalPages }, (_, index) => index + 1);

  return (
    <Pagination className={cx("finance-table-pagination", className)} size="sm">
      <Pagination.Summary className="finance-table-pagination__summary">
        显示 {start}-{end} / {total}
      </Pagination.Summary>
      <Pagination.Content>
        <Pagination.Item>
          <Pagination.Previous isDisabled={currentPage <= 1} onPress={() => onPageChange(currentPage - 1)}>
            <Pagination.PreviousIcon />
            <span>上一页</span>
          </Pagination.Previous>
        </Pagination.Item>
        {pages.map((item) => (
          <Pagination.Item key={item}>
            <Pagination.Link isActive={item === currentPage} onPress={() => onPageChange(item)}>
              {item}
            </Pagination.Link>
          </Pagination.Item>
        ))}
        <Pagination.Item>
          <Pagination.Next isDisabled={currentPage >= totalPages} onPress={() => onPageChange(currentPage + 1)}>
            <span>下一页</span>
            <Pagination.NextIcon />
          </Pagination.Next>
        </Pagination.Item>
      </Pagination.Content>
    </Pagination>
  );
}

type TableCellStackProps = {
  primary: ReactNode;
  secondary?: ReactNode;
  meta?: ReactNode;
  className?: string;
};

export function TableCellStack({ primary, secondary, meta, className }: TableCellStackProps) {
  return (
    <span className={cx("finance-cell-stack", className)}>
      <span className="finance-cell-stack__primary">{primary}</span>
      {secondary ? <span className="finance-cell-stack__secondary">{secondary}</span> : null}
      {meta ? <span className="finance-cell-stack__meta">{meta}</span> : null}
    </span>
  );
}

type AmountCellProps = {
  amount: ReactNode;
  direction?: ReactNode;
  account?: ReactNode;
  className?: string;
};

export function AmountCell({ amount, direction, account, className }: AmountCellProps) {
  return (
    <span className={cx("finance-amount-cell", className)}>
      <span className="finance-amount-cell__value">{amount}</span>
      {direction || account ? (
        <span className="finance-amount-cell__meta">
          {direction ? <span className="finance-amount-cell__direction">{direction}</span> : null}
          {account ? <span className="finance-amount-cell__account">{account}</span> : null}
        </span>
      ) : null}
    </span>
  );
}

type FinanceDirectionTagProps = {
  direction: "income" | "expense" | "neutral" | string;
  children?: ReactNode;
};

export function FinanceDirectionTag({ direction, children }: FinanceDirectionTagProps) {
  const normalizedDirection = direction === "income" || direction === "收入"
    ? "income"
    : direction === "expense" || direction === "支出"
      ? "expense"
      : "neutral";
  const label = children ?? (normalizedDirection === "income" ? "收入" : normalizedDirection === "expense" ? "支出" : String(direction || "-"));
  const tone: FinanceTone = normalizedDirection === "income" ? "success" : normalizedDirection === "expense" ? "warning" : "neutral";

  return (
    <Chip
      className="finance-direction-tag"
      color={toneToChipColor(tone)}
      data-direction={normalizedDirection}
      size="sm"
      variant="soft"
    >
      {label}
    </Chip>
  );
}

type FinanceStatusTagProps = {
  children: ReactNode;
  tone?: FinanceTone;
};

export function FinanceStatusTag({ children, tone = "neutral" }: FinanceStatusTagProps) {
  return (
    <Chip className="finance-status-tag" color={toneToChipColor(tone)} data-tone={tone} size="sm" variant="soft">
      {children}
    </Chip>
  );
}

type EmptyValueProps = {
  value?: ReactNode;
};

export function EmptyValue({ value = "-" }: EmptyValueProps) {
  return <span className="finance-empty-value">{value}</span>;
}

type TruncatedCellTextProps = {
  value: string;
  emptyLabel?: string;
};

export function TruncatedCellText({ value, emptyLabel = "-" }: TruncatedCellTextProps) {
  if (!value) {
    return <EmptyValue value={emptyLabel} />;
  }

  return (
    <Tooltip delay={500}>
      <Tooltip.Trigger className="finance-truncated-text">{value}</Tooltip.Trigger>
      <Tooltip.Content>{value}</Tooltip.Content>
    </Tooltip>
  );
}
