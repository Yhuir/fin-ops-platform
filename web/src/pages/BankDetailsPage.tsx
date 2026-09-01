import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent, type RefObject } from "react";
import { createPortal } from "react-dom";
import {
  Button,
  Chip,
  ListBox,
  ListBoxItem,
  ListBoxSection,
  PopoverContent,
  PopoverDialog,
  PopoverRoot,
  PopoverTrigger,
} from "@heroui/react";
import { Filter, RefreshCw, Tags } from "lucide-react";

import {
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../components/common/FinanceTable";
import BusinessPeriodPicker, { nearbyBusinessYears } from "../components/common/BusinessPeriodPicker";
import PageStatisticsPopover from "../components/common/PageStatisticsPopover";
import QuerySearch from "../components/common/QuerySearch";
import StatePanel from "../components/common/StatePanel";
import { useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { currentBusinessMonth, currentBusinessYear, formatDateTimeText } from "../features/dateTime";
import { formatMoney } from "../features/money";
import BankCategoryTag from "../features/bankDetails/BankCategoryTag";
import AutoTagRulesDrawer from "../features/bankDetails/AutoTagRulesDrawer";
import {
  assignBankDetailCategory,
  clearBankDetailCategoryAssignment,
  confirmBankDetailCategory,
  downloadBankDetailTransactionsExport,
  fetchBankAutoTagRules,
  fetchBankDetailAccounts,
  fetchBankDetailTransactions,
  reapplyBankAutoTagRules,
  revokeBankDetailCategoryConfirmation,
  saveBankAutoTagRules,
} from "../features/bankDetails/api";
import type {
  BankAutoTagRulesResponse,
  BankAutoTagEditableRule,
  BankDateFilter,
  BankDetailAccount,
  BankDetailExportMode,
  BankDetailTransaction,
  BankDetailStatistics,
  BankDetailTransactionsResponse,
  BankTransactionDirection,
  BankTransactionCategoryCode,
  BankTransactionCategoryCounts,
  SaveBankAutoTagRulesRequest,
} from "../features/bankDetails/types";
import type { BankTransactionTagDefinition } from "../features/pendingInvoices/types";

const DEFAULT_BANK_YEAR = currentBusinessYear();
const DEFAULT_BANK_MONTH = currentBusinessMonth();
const DEFAULT_PAGE_SIZE = 100;
const ALL_ACCOUNTS_KEY = "__all_bank_accounts__";
const TAG_VERSION_STORAGE_KEY = "finops.bankTransactionTags.version";
const FEATURED_CATEGORY_CODES: BankTransactionCategoryCode[] = [
  "fee",
  "salary",
];
const EMPTY_CATEGORY_COUNTS: BankTransactionCategoryCounts = { uncategorized: 0 };

type CategorySummaryItem = {
  code: BankTransactionCategoryCode;
  label: string;
  primaryLabel: string;
  subLabel: string;
  count: number;
};

type CategoryTreeGroup = {
  key: string;
  label: string;
  count: number;
  directItem: CategorySummaryItem | null;
  children: CategorySummaryItem[];
};

type BankCategoryFilter =
  | { kind: "all" }
  | { kind: "uncategorized" }
  | { kind: "primary"; primaryLabel: string }
  | { kind: "tag"; code: BankTransactionCategoryCode; primaryLabel: string; subLabel: string | null };

type BankCategoryFilterRequestParams = {
  categoryCode: string | null;
  categoryPrimaryLabel: string | null;
  categorySubLabel: string | null;
  categoryThirdLabel: string | null;
};

type CategoryFilterSnapshot = {
  queryKey: string;
  totalCount: number;
  categoryCounts: BankTransactionCategoryCounts;
  tagDefinitions: BankTransactionTagDefinition[];
};

const EXTERNAL_TURNOVER_ROLE = "external_turnover";
const EXTERNAL_TURNOVER_PRIMARY_LABELS = new Set(["外部往来款付款", "外部往来款收款", "往来款付款", "往来款收款"]);
const EXTERNAL_TURNOVER_THIRD_LABELS = ["个人往来", "公司往来", "银行往来", "业务往来"];

function isExternalTurnoverPrimaryLabel(value: string | null | undefined) {
  return EXTERNAL_TURNOVER_PRIMARY_LABELS.has(String(value ?? "").trim());
}

function turnoverFamilyForThirdLabel(value: string | null | undefined) {
  switch (String(value ?? "").trim()) {
    case "个人往来":
      return "personal";
    case "公司往来":
      return "company";
    case "银行往来":
      return "bank";
    case "业务往来":
      return "business";
    default:
      return "";
  }
}

function inferTurnoverActionTypeFromRule(rule: BankAutoTagEditableRule) {
  const primary = rule.outputPrimaryLabel.trim();
  const sub = rule.outputSubLabel.trim();
  if (primary === "外部往来款付款" || primary === "往来款付款") {
    return /归还|还借款|还暂借款|偿还|还款/.test(sub) ? "repaid" : "pending_collection";
  }
  if (primary === "外部往来款收款" || primary === "往来款收款") {
    return /收回|退|退款|返还/.test(sub) ? "collected" : "pending_repayment";
  }
  return "";
}

const ALL_CATEGORY_FILTER: BankCategoryFilter = { kind: "all" };
const UNCATEGORIZED_CATEGORY_FILTER: BankCategoryFilter = { kind: "uncategorized" };

function tagDefinitionDisplayLabel(tag: BankTransactionTagDefinition) {
  const path = [tag.outputPrimaryLabel, tag.outputSubLabel, tag.outputThirdLabel ?? ""]
    .map((value) => value.trim())
    .filter(Boolean);
  if (path.length > 0) {
    return path.join(" / ");
  }
  return tag.label;
}

function tagDefinitionDisplayParts(tag: BankTransactionTagDefinition) {
  const primaryLabel = tag.outputPrimaryLabel.trim();
  const subLabel = tag.outputSubLabel.trim();
  const thirdLabel = (tag.outputThirdLabel ?? "").trim();
  if (primaryLabel && subLabel) {
    return { primaryLabel, subLabel: thirdLabel ? `${subLabel} / ${thirdLabel}` : subLabel };
  }

  const displayLabel = tagDefinitionDisplayLabel(tag);
  const slashParts = displayLabel.split(/\s*\/\s*/).map((value) => value.trim()).filter(Boolean);
  if (slashParts.length > 1) {
    return {
      primaryLabel: slashParts[0],
      subLabel: slashParts.slice(1).join(" / "),
    };
  }

  const colonIndex = displayLabel.indexOf("：");
  if (colonIndex > 0 && colonIndex < displayLabel.length - 1) {
    return {
      primaryLabel: displayLabel.slice(0, colonIndex).trim(),
      subLabel: displayLabel.slice(colonIndex + 1).trim(),
    };
  }

  return {
    primaryLabel: primaryLabel || displayLabel,
    subLabel: subLabel,
  };
}

function buildCategoryTree(items: CategorySummaryItem[]): CategoryTreeGroup[] {
  const groups = new Map<string, CategoryTreeGroup>();
  items.forEach((item) => {
    const label = item.primaryLabel || item.label;
    const key = label || item.code;
    const group = groups.get(key) ?? {
      key,
      label,
      count: 0,
      directItem: null,
      children: [],
    };
    group.count += item.count;
    if (item.subLabel) {
      group.children.push(item);
    } else {
      group.directItem = item;
    }
    groups.set(key, group);
  });
  return Array.from(groups.values());
}

function tagCategoryFilter(option: CategorySummaryItem): BankCategoryFilter {
  return {
    kind: "tag",
    code: option.code,
    primaryLabel: option.primaryLabel,
    subLabel: option.subLabel || null,
  };
}

function categoryFilterRequestParams(filter: BankCategoryFilter): BankCategoryFilterRequestParams {
  if (filter.kind === "uncategorized") {
    return {
      categoryCode: "uncategorized",
      categoryPrimaryLabel: null,
      categorySubLabel: null,
      categoryThirdLabel: null,
    };
  }
  if (filter.kind === "primary") {
    return {
      categoryCode: null,
      categoryPrimaryLabel: filter.primaryLabel,
      categorySubLabel: null,
      categoryThirdLabel: null,
    };
  }
  if (filter.kind === "tag") {
    return {
      categoryCode: filter.code,
      categoryPrimaryLabel: null,
      categorySubLabel: null,
      categoryThirdLabel: null,
    };
  }
  return {
    categoryCode: null,
    categoryPrimaryLabel: null,
    categorySubLabel: null,
    categoryThirdLabel: null,
  };
}

function hasCategoryRequestFilter(params: BankCategoryFilterRequestParams) {
  return Boolean(params.categoryCode || params.categoryPrimaryLabel || params.categorySubLabel || params.categoryThirdLabel);
}

function categoryFilterSnapshotKey({
  accountKey,
  dateFrom,
  dateTo,
  keyword,
}: {
  accountKey: string | null;
  dateFrom: string | null;
  dateTo: string | null;
  keyword: string;
}) {
  return JSON.stringify({
    accountKey: accountKey || "",
    dateFrom: dateFrom ?? "",
    dateTo: dateTo ?? "",
    keyword: keyword.trim(),
  });
}

function activeTagDefinitions(tags: BankTransactionTagDefinition[] | null | undefined) {
  return Array.isArray(tags) ? tags.filter((tag) => tag.status === "active") : [];
}

function selectedCategoryFilterLabel({
  counts,
  groups,
  selectedFilter,
  totalCount,
  visibleSummary,
}: {
  counts: BankTransactionCategoryCounts;
  groups: CategoryTreeGroup[];
  selectedFilter: BankCategoryFilter;
  totalCount: number;
  visibleSummary: CategorySummaryItem[];
}) {
  if (selectedFilter.kind === "uncategorized") {
    return `未分类 ${counts.uncategorized ?? 0}`;
  }
  if (selectedFilter.kind === "primary") {
    const group = groups.find((item) => item.label === selectedFilter.primaryLabel);
    return `${selectedFilter.primaryLabel} ${group?.count ?? 0}`;
  }
  if (selectedFilter.kind === "tag") {
    const category = visibleSummary.find((option) => option.code === selectedFilter.code);
    return category ? `${category.label} ${category.count}` : `${selectedFilter.primaryLabel} 0`;
  }
  return `全部 ${totalCount}`;
}

function selectedCategoryFilterStillExists(filter: BankCategoryFilter, options: BankTransactionTagDefinition[]) {
  if (filter.kind === "all" || filter.kind === "uncategorized") {
    return true;
  }
  return options.some((option) => {
    if (filter.kind === "tag") {
      return option.code === filter.code;
    }
    return tagDefinitionDisplayParts(option).primaryLabel === filter.primaryLabel;
  });
}

function categoryFilterKey(filter: BankCategoryFilter) {
  if (filter.kind === "all" || filter.kind === "uncategorized") {
    return filter.kind;
  }
  if (filter.kind === "primary") {
    return `primary:${filter.primaryLabel}`;
  }
  return `tag:${filter.code}`;
}

type BankCategoryFilterControlProps = {
  categoryCounts: BankTransactionCategoryCounts;
  totalCount: number;
  visibleCategorySummary: CategorySummaryItem[];
  selectedCategoryFilter: BankCategoryFilter;
  onCategoryFilterChange: (filter: BankCategoryFilter) => void;
};

type BankDetailsTableToolbarProps = {
  searchKeyword: string;
  onSearchKeywordChange: (value: string) => void;
  onSearchSubmit: () => void;
  onSearchClear: () => void;
  exportMenuOpen: boolean;
  exportFeedback: string | null;
  isExporting: boolean;
  canExportCurrentAccount: boolean;
  onOpenExportMenu: () => void;
  onCloseExportMenu: () => void;
  onExport: (mode: BankDetailExportMode) => void;
};

type BankTransactionPaginationProps = {
  page: number;
  pageSize: number;
  total: number;
  pageSizeOptions: number[];
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
};

function formatDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function endOfMonth(year: number, monthIndex: number) {
  return new Date(year, monthIndex + 1, 0);
}

function normalizeYearValue(value: string | null | undefined) {
  const year = String(value ?? "").trim();
  return /^\d{4}$/.test(year) ? year : DEFAULT_BANK_YEAR;
}

function normalizeMonthValue(value: string | null | undefined) {
  const month = String(value ?? "").trim();
  return /^\d{4}-\d{2}$/.test(month) ? month : DEFAULT_BANK_MONTH;
}

function createDateFilter(preset: BankDateFilter["preset"], value = DEFAULT_BANK_YEAR): BankDateFilter {
  if (preset === "all") {
    return { preset, dateFrom: null, dateTo: null };
  }
  if (preset === "month") {
    const monthValue = normalizeMonthValue(value);
    const [year, month] = monthValue.split("-").map(Number);
    return {
      preset,
      month: monthValue,
      dateFrom: `${monthValue}-01`,
      dateTo: formatDate(endOfMonth(year, month - 1)),
    };
  }
  const year = normalizeYearValue(value);
  return { preset: "year", year, dateFrom: `${year}-01-01`, dateTo: `${year}-12-31` };
}

function displayBalance(value: string | null) {
  return value && value.trim() ? formatMoney(value) : "余额为空";
}

function relationTagTone(tag: string) {
  return tag.startsWith("有") ? "has" : "none";
}

function relationTagColor(tag: string): "success" | "warning" {
  return tag.startsWith("有") ? "success" : "warning";
}

function directionTagColor(direction: BankTransactionDirection): "success" | "danger" {
  return direction === "income" ? "success" : "danger";
}

function readPersistedTagVersion() {
  try {
    const version = Number(window.localStorage.getItem(TAG_VERSION_STORAGE_KEY));
    return Number.isFinite(version) && version > 0 ? version : null;
  } catch {
    return null;
  }
}

function persistTagVersion(version: number | null | undefined) {
  if (typeof version !== "number" || !Number.isFinite(version) || version <= 0) {
    return;
  }
  try {
    window.localStorage.setItem(TAG_VERSION_STORAGE_KEY, String(version));
  } catch {
    // localStorage may be unavailable in restrictive embedded shells.
  }
}

function isAbortLikeError(caught: unknown) {
  if (caught instanceof DOMException && caught.name === "AbortError") {
    return true;
  }
  if (caught instanceof Error) {
    return caught.name === "AbortError" || /aborted|abort/i.test(caught.message);
  }
  return false;
}

function isBankDateFilter(value: unknown): value is BankDateFilter {
  if (!value || typeof value !== "object") {
    return false;
  }
  const filter = value as Record<string, unknown>;
  if (filter.preset === "all") {
    return filter.dateFrom === null && filter.dateTo === null;
  }
  if (filter.preset === "year") {
    return typeof filter.year === "string" && typeof filter.dateFrom === "string" && typeof filter.dateTo === "string";
  }
  if (filter.preset === "month") {
    return typeof filter.month === "string" && typeof filter.dateFrom === "string" && typeof filter.dateTo === "string";
  }
  return false;
}

function EmptyTransactionOverlay() {
  return (
    <div className="bank-empty-transaction-overlay">
      <span>当前时间范围内没有流水。</span>
    </div>
  );
}

function useCloseOnOutsidePointer(open: boolean, rootRef: RefObject<HTMLElement | null> | RefObject<HTMLElement | null>[], onClose: () => void) {
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const rootRefs = Array.isArray(rootRef) ? rootRef : [rootRef];
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && rootRefs.some((candidate) => candidate.current?.contains(target))) {
        return;
      }
      onClose();
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [onClose, open, rootRef]);
}

function BankCategoryFilterControl({
  categoryCounts = EMPTY_CATEGORY_COUNTS,
  totalCount = 0,
  visibleCategorySummary = [],
  selectedCategoryFilter = ALL_CATEGORY_FILTER,
  onCategoryFilterChange = () => undefined,
}: Partial<BankCategoryFilterControlProps>) {
  const [categoryPanelOpen, setCategoryPanelOpen] = useState(false);
  const categoryFilterTriggerRef = useRef<HTMLDivElement>(null);
  const categoryGroups = useMemo(() => buildCategoryTree(visibleCategorySummary), [visibleCategorySummary]);
  const categoryFiltersByKey = useMemo(() => {
    const filters = new Map<string, BankCategoryFilter>([
      [categoryFilterKey(ALL_CATEGORY_FILTER), ALL_CATEGORY_FILTER],
      [categoryFilterKey(UNCATEGORIZED_CATEGORY_FILTER), UNCATEGORIZED_CATEGORY_FILTER],
    ]);
    categoryGroups.forEach((group) => {
      const primaryFilter = group.directItem && group.children.length === 0
        ? tagCategoryFilter(group.directItem)
        : { kind: "primary", primaryLabel: group.label } satisfies BankCategoryFilter;
      filters.set(categoryFilterKey(primaryFilter), primaryFilter);
      if (group.directItem && group.children.length > 0) {
        const directFilter = tagCategoryFilter(group.directItem);
        filters.set(categoryFilterKey(directFilter), directFilter);
      }
      group.children.forEach((child) => {
        const childFilter = tagCategoryFilter(child);
        filters.set(categoryFilterKey(childFilter), childFilter);
      });
    });
    return filters;
  }, [categoryGroups]);
  const selectedCategoryLabel = selectedCategoryFilterLabel({
    counts: categoryCounts,
    groups: categoryGroups,
    selectedFilter: selectedCategoryFilter,
    totalCount,
    visibleSummary: visibleCategorySummary,
  });

  const renderCategoryFilterItem = (
    filter: BankCategoryFilter,
    label: string,
    count: number,
    level: "root" | "primary" | "child",
    className = "",
  ) => {
    return (
      <ListBoxItem
        aria-label={`${label} ${count}`}
        className={`bank-category-filter-row ${className}`.trim()}
        data-level={level}
        id={categoryFilterKey(filter)}
      >
        <span className="bank-category-filter-row-content">
          <span className="bank-category-filter-label">{label}</span>
          <span className="bank-category-filter-count">{count}</span>
        </span>
      </ListBoxItem>
    );
  };

  return (
    <div className="bank-category-filter-float">
      <PopoverRoot isOpen={categoryPanelOpen} onOpenChange={setCategoryPanelOpen}>
        <PopoverTrigger
          aria-label={`标签筛选：${selectedCategoryLabel}`}
          className={`bank-category-filter-icon-button${selectedCategoryFilter.kind === "all" ? "" : " active"}`}
          ref={categoryFilterTriggerRef}
          title={selectedCategoryLabel}
        >
          <Filter aria-hidden="true" size={18} strokeWidth={2.2} />
          {selectedCategoryFilter.kind === "all" ? null : <span className="bank-category-filter-active-dot" aria-hidden="true" />}
        </PopoverTrigger>
        <PopoverContent
          className="bank-category-filter-panel"
          containerPadding={12}
          isNonModal
          maxHeight={720}
          offset={8}
          placement="bottom start"
          shouldCloseOnInteractOutside={(element) => !categoryFilterTriggerRef.current?.contains(element)}
        >
          <PopoverDialog aria-label="银行明细标签筛选" className="bank-category-filter-dialog">
            <ListBox
              aria-label="银行明细标签筛选"
              className="bank-category-filter-list"
              disallowEmptySelection
              onSelectionChange={(keys) => {
                const key = keys === "all" ? null : Array.from(keys)[0];
                const nextFilter = key === null || key === undefined ? null : categoryFiltersByKey.get(String(key));
                if (nextFilter) {
                  onCategoryFilterChange(nextFilter);
                }
              }}
              selectedKeys={new Set([categoryFilterKey(selectedCategoryFilter)])}
              selectionMode="single"
            >
              <ListBoxSection className="bank-category-filter-actions">
                {renderCategoryFilterItem(ALL_CATEGORY_FILTER, "全部", totalCount, "root", "bank-category-filter-action")}
                {renderCategoryFilterItem(
                  UNCATEGORIZED_CATEGORY_FILTER,
                  "未分类",
                  categoryCounts.uncategorized ?? 0,
                  "root",
                  "bank-category-filter-action",
                )}
              </ListBoxSection>
              {categoryGroups.map((group, groupIndex) => (
                <ListBoxSection
                  className={`bank-category-filter-group bank-category-filter-hierarchy-group bank-category-filter-tone-${groupIndex % 6}`}
                  key={group.key}
                >
                  {renderCategoryFilterItem(
                    group.directItem && group.children.length === 0
                      ? tagCategoryFilter(group.directItem)
                      : { kind: "primary", primaryLabel: group.label },
                    group.label,
                    group.count,
                    "primary",
                    "bank-category-filter-primary-row",
                  )}
                  {group.directItem && group.children.length > 0 ? (
                    renderCategoryFilterItem(
                      tagCategoryFilter(group.directItem),
                      group.label,
                      group.directItem.count,
                      "child",
                      "bank-category-filter-child-row bank-category-filter-hierarchy-item bank-category-filter-direct-child",
                    )
                  ) : null}
                  {group.children.map((child) => (
                    <Fragment key={child.code}>
                      {renderCategoryFilterItem(
                        tagCategoryFilter(child),
                        child.subLabel || child.label,
                        child.count,
                        "child",
                        "bank-category-filter-child-row bank-category-filter-hierarchy-item",
                      )}
                    </Fragment>
                  ))}
                </ListBoxSection>
              ))}
            </ListBox>
          </PopoverDialog>
        </PopoverContent>
      </PopoverRoot>
    </div>
  );
}

function BankDetailsTableToolbar({
  searchKeyword = "",
  onSearchKeywordChange = () => undefined,
  onSearchSubmit = () => undefined,
  onSearchClear = () => undefined,
  exportMenuOpen = false,
  exportFeedback = null,
  isExporting = false,
  canExportCurrentAccount = false,
  onOpenExportMenu = () => undefined,
  onCloseExportMenu = () => undefined,
  onExport = () => undefined,
}: Partial<BankDetailsTableToolbarProps>) {
  return (
    <div className="bank-grid-toolbar">
      <div className="bank-grid-toolbar-content">
        <div className="bank-grid-toolbar-actions">
          <QuerySearch
            ariaLabel="搜索流水"
            className="bank-grid-search"
            onChange={onSearchKeywordChange}
            onClear={onSearchClear}
            onSubmit={onSearchSubmit}
            placeholder="搜索流水"
            value={searchKeyword}
          />
          {exportFeedback ? (
            <span className="bank-export-feedback">
              {exportFeedback}
            </span>
          ) : null}
          <div
            className="bank-export-menu-host"
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                onCloseExportMenu();
              }
            }}
          >
            <button
              aria-controls={exportMenuOpen ? "bank-detail-export-menu" : undefined}
              aria-expanded={exportMenuOpen ? "true" : undefined}
              aria-haspopup="menu"
              className="bank-export-button"
              disabled={isExporting}
              onClick={onOpenExportMenu}
              type="button"
            >
              {isExporting ? "导出中" : "导出"}
            </button>
            {exportMenuOpen ? (
              <div
                aria-label="导出银行明细"
                className="bank-export-menu"
                id="bank-detail-export-menu"
                role="menu"
              >
                <button disabled={isExporting} onClick={() => onExport("all")} role="menuitem" type="button">
                  导出全部银行
                </button>
                <button disabled={isExporting || !canExportCurrentAccount} onClick={() => onExport("account")} role="menuitem" type="button">
                  导出当前账户
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function displayedTransactionRange(page: number, pageSize: number, total: number) {
  if (total <= 0) {
    return "0-0 / 0";
  }
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const currentPage = Math.min(Math.max(page, 0), totalPages - 1);
  const from = currentPage * pageSize + 1;
  const to = Math.min((currentPage + 1) * pageSize, total);
  return `${from}-${to} / ${total}`;
}

function BankTransactionPagination({
  page,
  pageSize,
  total,
  pageSizeOptions,
  onPageChange,
  onPageSizeChange,
}: BankTransactionPaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const currentPage = Math.min(Math.max(page, 0), totalPages - 1);

  return (
    <div className="bank-transaction-pagination">
      <label className="bank-transaction-pagination-size">
        <span>每页行数</span>
        <select
          aria-label="每页行数"
          value={pageSize}
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
        >
          {pageSizeOptions.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </label>
      <span className="bank-transaction-pagination-range">
        {displayedTransactionRange(currentPage, pageSize, total)}
      </span>
      <div className="bank-transaction-pagination-actions">
        <button
          aria-label="上一页"
          disabled={currentPage <= 0}
          onClick={() => onPageChange(currentPage - 1)}
          type="button"
        >
          上一页
        </button>
        <button
          aria-label="下一页"
          disabled={currentPage >= totalPages - 1}
          onClick={() => onPageChange(currentPage + 1)}
          type="button"
        >
          下一页
        </button>
      </div>
    </div>
  );
}

function counterpartyNameDensity(name: string) {
  const length = name.trim().length;
  if (length >= 28) {
    return "dense";
  }
  if (length >= 20) {
    return "compact";
  }
  return "regular";
}

type ConfirmationChoice = {
  categoryCode: BankTransactionCategoryCode;
  primaryLabel: string;
  subLabel: string | null;
  thirdLabel: string | null;
  labelPath: string[];
  turnoverActionType: string | null;
  turnoverFamily: string | null;
};

type ConfirmationChoiceGroup = {
  key: string;
  primaryLabel: string;
  choices: ConfirmationChoice[];
};

const INTERNAL_TRANSFER_MANUAL_CHOICE: ConfirmationChoice = {
  categoryCode: "internal_transfer",
  primaryLabel: "内部往来款",
  subLabel: null,
  thirdLabel: null,
  labelPath: ["内部往来款"],
  turnoverActionType: null,
  turnoverFamily: null,
};

type ConfirmationChoiceSubGroup = {
  key: string;
  subLabel: string;
  choices: ConfirmationChoice[];
  hasThirdLevel: boolean;
};

function candidateLabelPart(value: string | null | undefined) {
  return String(value ?? "").trim();
}

function confirmationChoiceFromCandidate(
  candidate: BankDetailTransaction["autoCandidateCategories"][number],
): ConfirmationChoice | null {
  const categoryCode = candidateLabelPart(candidate.categoryCode);
  if (!categoryCode) {
    return null;
  }
  const labelPath = candidate.categoryLabelPath.map(candidateLabelPart).filter(Boolean);
  const primaryLabel = candidateLabelPart(candidate.categoryPrimaryLabel)
    || labelPath[0]
    || candidateLabelPart(candidate.categoryLabel)
    || categoryCode;
  const subLabel = candidateLabelPart(candidate.categorySubLabel)
    || labelPath.slice(1).find(Boolean)
    || null;
  const thirdLabel = candidateLabelPart(candidate.categoryThirdLabel)
    || labelPath.slice(2).find(Boolean)
    || null;
  return {
    categoryCode,
    primaryLabel,
    subLabel,
    thirdLabel,
    labelPath: labelPath.length ? labelPath : [primaryLabel, subLabel, thirdLabel].filter((value): value is string => Boolean(value)),
    turnoverActionType: candidate.turnoverActionType,
    turnoverFamily: candidate.turnoverFamily,
  };
}

function confirmationChoicesFromAutoTagRule(rule: BankAutoTagEditableRule): ConfirmationChoice[] {
  if (rule.status !== "active") {
    return [];
  }
  const categoryCode = candidateLabelPart(rule.code);
  if (!categoryCode) {
    return [];
  }
  const primaryLabel = candidateLabelPart(rule.outputPrimaryLabel)
    || candidateLabelPart(rule.label)
    || categoryCode;
  const subLabel = candidateLabelPart(rule.outputSubLabel)
    || candidateLabelPart(rule.label)
    || primaryLabel;
  const actionType = rule.turnoverActionType || (isExternalTurnoverPrimaryLabel(primaryLabel) ? inferTurnoverActionTypeFromRule(rule) : "");
  const baseChoice = {
    categoryCode,
    primaryLabel,
    subLabel,
    turnoverActionType: actionType || null,
  };
  if (isExternalTurnoverPrimaryLabel(primaryLabel)) {
    return EXTERNAL_TURNOVER_THIRD_LABELS.map((thirdLabel) => ({
      ...baseChoice,
      thirdLabel,
      labelPath: [primaryLabel, subLabel, thirdLabel].filter(Boolean),
      turnoverFamily: turnoverFamilyForThirdLabel(thirdLabel) || null,
    }));
  }
  return [{
    ...baseChoice,
    thirdLabel: null,
    labelPath: [primaryLabel, subLabel].filter((value): value is string => Boolean(value)),
    turnoverFamily: null,
  }];
}

function choiceKey(choice: ConfirmationChoice) {
  return `${choice.categoryCode}\u0000${choice.thirdLabel ?? ""}`;
}

function choiceSubLabel(choice: ConfirmationChoice) {
  return choice.subLabel || choice.primaryLabel;
}

function choiceDisplayLabel(choice: ConfirmationChoice) {
  const labelPath = choice.labelPath.length
    ? choice.labelPath
    : [choice.primaryLabel, choice.subLabel, choice.thirdLabel].filter((value): value is string => Boolean(value));
  return labelPath.join(" / ") || choice.categoryCode;
}

function buildChoiceSubGroups(group: ConfirmationChoiceGroup | null): ConfirmationChoiceSubGroup[] {
  if (!group) {
    return [];
  }
  const subGroups: ConfirmationChoiceSubGroup[] = [];
  const subGroupsByKey = new Map<string, ConfirmationChoiceSubGroup>();
  group.choices.forEach((choice) => {
    const subLabel = choiceSubLabel(choice);
    const key = subLabel;
    let subGroup = subGroupsByKey.get(key);
    if (!subGroup) {
      subGroup = { key, subLabel, choices: [], hasThirdLevel: false };
      subGroupsByKey.set(key, subGroup);
      subGroups.push(subGroup);
    }
    subGroup.choices.push(choice);
    if (choice.thirdLabel) {
      subGroup.hasThirdLevel = true;
    }
  });
  return subGroups;
}

function activeAutoRuleChoiceKeySet(rules: BankAutoTagEditableRule[]) {
  const keys = new Set<string>();
  rules.forEach((rule) => {
    confirmationChoicesFromAutoTagRule(rule).forEach((choice) => {
      keys.add(choiceKey(choice));
      keys.add(`${choice.categoryCode}\u0000`);
    });
  });
  return keys;
}

function buildAssignmentChoiceGroups(
  activeRules: BankAutoTagEditableRule[],
): ConfirmationChoiceGroup[] {
  return buildConfirmationChoiceGroupsFromChoices([
    ...activeRules.flatMap(confirmationChoicesFromAutoTagRule),
    INTERNAL_TRANSFER_MANUAL_CHOICE,
  ]);
}

function buildConfirmationChoiceGroupsFromChoices(
  choices: Array<ConfirmationChoice | null>,
): ConfirmationChoiceGroup[] {
  const groups: ConfirmationChoiceGroup[] = [];
  const groupsByKey = new Map<string, ConfirmationChoiceGroup>();
  const seenChoices = new Set<string>();
  choices.forEach((choice) => {
    if (!choice || seenChoices.has(choiceKey(choice))) {
      return;
    }
    seenChoices.add(choiceKey(choice));
    const key = choice.primaryLabel;
    let group = groupsByKey.get(key);
    if (!group) {
      group = { key, primaryLabel: choice.primaryLabel, choices: [] };
      groupsByKey.set(key, group);
      groups.push(group);
    }
    group.choices.push(choice);
  });
  return groups;
}

function buildConfirmationChoiceGroups(
  candidates: BankDetailTransaction["autoCandidateCategories"],
  activeRules: BankAutoTagEditableRule[],
): ConfirmationChoiceGroup[] {
  const activeChoiceKeys = activeAutoRuleChoiceKeySet(activeRules);
  return buildConfirmationChoiceGroupsFromChoices([...candidates.map((candidate) => {
    const candidateChoice = confirmationChoiceFromCandidate(candidate);
    if (!candidateChoice) {
      return null;
    }
    return activeChoiceKeys.has(choiceKey(candidateChoice)) || activeChoiceKeys.has(`${candidateChoice.categoryCode}\u0000`)
      ? candidateChoice
      : null;
  }), INTERNAL_TRANSFER_MANUAL_CHOICE]);
}

function TypeCell({
  row,
  autoTagRules,
  confirming,
  canOperateData,
  onConfirm,
  onAssign,
  onRevoke,
  onClearAssignment,
}: {
  row: BankDetailTransaction;
  autoTagRules: BankAutoTagEditableRule[];
  confirming: boolean;
  canOperateData: boolean;
  onConfirm: (row: BankDetailTransaction, choice: ConfirmationChoice) => Promise<void>;
  onAssign: (row: BankDetailTransaction, choice: ConfirmationChoice) => Promise<void>;
  onRevoke: (row: BankDetailTransaction) => void;
  onClearAssignment: (row: BankDetailTransaction) => void;
}) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const [stagedChoice, setStagedChoice] = useState<ConfirmationChoice | null>(null);
  const [confirmationPanelPosition, setConfirmationPanelPosition] = useState<{
    left: number;
    top: number;
    maxHeight: number;
    panelWidth: number;
    placement: "bottom" | "top";
  } | null>(null);
  const [internalTooltipOpen, setInternalTooltipOpen] = useState(false);
  const confirmationRef = useRef<HTMLSpanElement | null>(null);
  const confirmationPanelRef = useRef<HTMLDivElement | null>(null);
  const confirmationGroups = useMemo(
    () => (row.categoryResolutionStatus === "needs_confirmation"
      ? buildConfirmationChoiceGroups(row.autoCandidateCategories, autoTagRules)
      : []),
    [autoTagRules, row.autoCandidateCategories, row.categoryResolutionStatus],
  );
  const assignmentGroups = useMemo(
    () => ((row.categoryResolutionStatus === "unmatched" && !row.effectiveCategoryCode) || row.effectiveCategorySource === "auto"
      ? buildAssignmentChoiceGroups(autoTagRules)
      : []),
    [autoTagRules, row.categoryResolutionStatus, row.effectiveCategoryCode, row.effectiveCategorySource],
  );
  const confirmationChoiceKeys = useMemo(() => new Set(
    row.autoCandidateCategories
      .map(confirmationChoiceFromCandidate)
      .filter((choice): choice is ConfirmationChoice => Boolean(choice))
      .map(choiceKey),
  ), [row.autoCandidateCategories]);
  const selectionGroups = confirmationGroups.length > 0 ? confirmationGroups : assignmentGroups;
  const autoCategoryCanBeReassigned = row.effectiveCategorySource === "auto" && Boolean(row.effectiveCategoryCode);
  const selectionLabel = autoCategoryCanBeReassigned ? "重新分类" : confirmationGroups.length > 0 ? "待确认" : "待分类";
  const triggerLabel = stagedChoice ? choiceDisplayLabel(stagedChoice) : selectionLabel;
  const childLabelSuffix = "可选标签";
  const thirdLabelSuffix = "可选业务类型";
  const [selectedPrimaryKey, setSelectedPrimaryKey] = useState("");
  const [selectedSubKey, setSelectedSubKey] = useState("");
  const selectedGroup = selectionGroups.find((group) => group.key === selectedPrimaryKey) ?? selectionGroups[0] ?? null;
  const selectedSubGroups = useMemo(() => buildChoiceSubGroups(selectedGroup), [selectedGroup]);
  const selectedSubGroup = selectedSubGroups.find((group) => group.key === selectedSubKey) ?? selectedSubGroups[0] ?? null;

  useEffect(() => {
    if (!selectionGroups.length) {
      if (selectedPrimaryKey) {
        setSelectedPrimaryKey("");
      }
      return;
    }
    if (!selectionGroups.some((group) => group.key === selectedPrimaryKey)) {
      setSelectedPrimaryKey(selectionGroups[0].key);
      setStagedChoice(null);
    }
  }, [selectionGroups, selectedPrimaryKey]);

  useEffect(() => {
    if (!selectedSubGroups.length) {
      if (selectedSubKey) {
        setSelectedSubKey("");
      }
      return;
    }
    if (!selectedSubGroups.some((group) => group.key === selectedSubKey)) {
      setSelectedSubKey(selectedSubGroups[0].key);
      setStagedChoice(null);
    }
  }, [selectedSubGroups, selectedSubKey]);

  useEffect(() => {
    setStagedChoice(null);
  }, [row.id, row.categoryResolutionStatus, row.effectiveCategoryCode]);

  const updateConfirmationPanelPosition = useCallback((target: HTMLElement | null = anchorEl) => {
    if (!target || typeof window === "undefined") {
      setConfirmationPanelPosition(null);
      return;
    }
    const viewportMargin = 12;
    const triggerGap = 8;
    const minPanelHeight = 220;
    const maxPanelHeight = 360;
    const preferredWidth = selectedSubGroup?.hasThirdLevel ? 680 : 580;
    const panelWidth = Math.max(280, Math.min(preferredWidth, window.innerWidth - viewportMargin * 2));
    const rect = target.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom - triggerGap - viewportMargin;
    const spaceAbove = rect.top - triggerGap - viewportMargin;
    const placement = spaceBelow >= minPanelHeight || spaceBelow >= spaceAbove ? "bottom" : "top";
    const availableHeight = Math.max(
      minPanelHeight,
      placement === "bottom" ? spaceBelow : spaceAbove,
    );
    const maxHeight = Math.min(maxPanelHeight, availableHeight);
    const left = Math.min(
      Math.max(viewportMargin, rect.left),
      Math.max(viewportMargin, window.innerWidth - panelWidth - viewportMargin),
    );
    const top = placement === "bottom"
      ? Math.min(rect.bottom + triggerGap, window.innerHeight - viewportMargin)
      : Math.max(viewportMargin, rect.top - triggerGap);
    setConfirmationPanelPosition({ left, top, maxHeight, panelWidth, placement });
  }, [anchorEl, selectedSubGroup?.hasThirdLevel]);

  useEffect(() => {
    if (!anchorEl) {
      return undefined;
    }
    updateConfirmationPanelPosition(anchorEl);
    const handleViewportChange = () => updateConfirmationPanelPosition(anchorEl);
    window.addEventListener("resize", handleViewportChange);
    window.addEventListener("scroll", handleViewportChange, true);
    return () => {
      window.removeEventListener("resize", handleViewportChange);
      window.removeEventListener("scroll", handleViewportChange, true);
    };
  }, [anchorEl, updateConfirmationPanelPosition]);

  const closeConfirmationPanel = () => {
    if (!canOperateData || confirming) {
      return;
    }
    setAnchorEl(null);
    setConfirmationPanelPosition(null);
    setStagedChoice(null);
  };
  const stageChoice = (choice: ConfirmationChoice) => {
    if (!canOperateData || confirming) {
      return;
    }
    setStagedChoice(choice);
  };
  const saveStagedChoice = () => {
    if (!canOperateData || !stagedChoice || confirming) {
      return;
    }
    const choice = stagedChoice;
    setAnchorEl(null);
    const request = row.categoryResolutionStatus === "needs_confirmation" && confirmationChoiceKeys.has(choiceKey(choice))
      ? onConfirm(row, choice)
      : onAssign(row, choice);
    request
      .then(() => setStagedChoice(null))
      .catch(() => setStagedChoice(null));
  };
  useCloseOnOutsidePointer(Boolean(anchorEl), [confirmationRef, confirmationPanelRef], closeConfirmationPanel);

  const autoCategoryDisplay = (() => {
    if (!row.autoCategoryCode || !row.autoCategoryLabel) {
      return <span className="bank-auto-type-empty">-</span>;
    }
    const structuredLabelPath = [row.autoCategoryPrimaryLabel, row.autoCategorySubLabel]
      .map((value) => value?.trim() ?? "")
      .filter(Boolean);
    const effectiveStructuredLabelPath = [row.effectiveCategoryPrimaryLabel, row.effectiveCategorySubLabel]
      .map((value) => value?.trim() ?? "")
      .filter(Boolean);
    const displayLabel = structuredLabelPath.length > 0
      ? structuredLabelPath.join(" / ")
      : row.autoCategoryLabelPath.length > 0
      ? row.autoCategoryLabelPath.join(" / ")
      : effectiveStructuredLabelPath.length > 0
      ? effectiveStructuredLabelPath.join(" / ")
      : row.autoCategoryLabel;
    const counterpart = row.autoCategoryCode === "internal_transfer" ? row.internalTransferCounterpart : null;
    const categoryTag = (
      <BankCategoryTag
        categoryCode={row.autoCategoryCode}
        compact
        hierarchyTooltip={!counterpart}
        label={displayLabel}
      />
    );
    if (!counterpart) {
      return categoryTag;
    }
    const accountText = [counterpart.bankName, counterpart.accountLast4].filter(Boolean).join(" ") || "-";
    const tooltipId = `bank-internal-transfer-tooltip-${row.id}`;
    return (
      <span
        aria-describedby={internalTooltipOpen ? tooltipId : undefined}
        className="bank-internal-transfer-tag-anchor"
        onBlur={() => setInternalTooltipOpen(false)}
        onFocus={() => setInternalTooltipOpen(true)}
        onMouseEnter={() => setInternalTooltipOpen(true)}
        onMouseLeave={() => setInternalTooltipOpen(false)}
        tabIndex={0}
      >
        {categoryTag}
        {internalTooltipOpen ? (
          <span className="bank-internal-transfer-tooltip" id={tooltipId} role="tooltip">
            <span className="bank-internal-transfer-tooltip-title">对应内部往来流水</span>
            <span className="bank-internal-transfer-tooltip-grid">
              <span className="bank-internal-transfer-tooltip-label">时间</span>
              <span className="bank-internal-transfer-tooltip-value">{formatDateTimeText(counterpart.tradeTime)}</span>
              <span className="bank-internal-transfer-tooltip-label">账户</span>
              <span className="bank-internal-transfer-tooltip-value">{accountText}</span>
              <span className="bank-internal-transfer-tooltip-label">金额</span>
              <span className="bank-internal-transfer-tooltip-value bank-internal-transfer-tooltip-amount">{formatMoney(counterpart.amount) || "-"}</span>
              <span className="bank-internal-transfer-tooltip-label">对方户名</span>
              <span className="bank-internal-transfer-tooltip-value">{counterpart.counterpartyName || "-"}</span>
            </span>
          </span>
        ) : null}
      </span>
    );
  })();

  if (selectionGroups.length > 0) {
    const confirmationPanelStyle = confirmationPanelPosition ? ({
      "--bank-category-confirmation-left": `${confirmationPanelPosition.left}px`,
      "--bank-category-confirmation-top": `${confirmationPanelPosition.top}px`,
      "--bank-category-confirmation-max-height": `${confirmationPanelPosition.maxHeight}px`,
      "--bank-category-confirmation-width": `${confirmationPanelPosition.panelWidth}px`,
    } as CSSProperties) : undefined;
    const confirmationPanel = anchorEl && confirmationPanelPosition && typeof document !== "undefined" ? createPortal(
      <div
        className="bank-category-confirmation-popper"
        data-placement={confirmationPanelPosition.placement}
        style={confirmationPanelStyle}
      >
        <div
          ref={confirmationPanelRef}
          className="bank-category-confirmation-panel"
          id={`bank-category-confirmation-${row.id}`}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              closeConfirmationPanel();
            }
          }}
        >
          <div className={`bank-category-confirmation-columns${selectedSubGroup?.hasThirdLevel ? " bank-category-confirmation-columns--three-level" : ""}`}>
            <div
              aria-label={`${selectionLabel}主标签`}
              className="bank-category-confirmation-primary-list"
              role="menu"
            >
              {selectionGroups.map((group) => (
                <button
                  aria-current={group.key === selectedGroup?.key ? "true" : "false"}
                  className="bank-category-confirmation-primary-item"
                  key={group.key}
                  onClick={() => {
                    setSelectedPrimaryKey(group.key);
                    setSelectedSubKey("");
                    setStagedChoice(null);
                  }}
                  role="menuitem"
                  type="button"
                >
                  <span>{group.primaryLabel}</span>
                </button>
              ))}
            </div>
            <div className="bank-category-confirmation-divider" aria-hidden="true" role="separator" />
            <div
              aria-label={`${selectedGroup?.primaryLabel ?? "已选主标签"}${childLabelSuffix}`}
              className="bank-category-confirmation-child-list"
              role="menu"
            >
              {selectedSubGroups.map((subGroup) => (
                <button
                  aria-current={subGroup.key === selectedSubGroup?.key || subGroup.choices.some((choice) => stagedChoice ? choiceKey(choice) === choiceKey(stagedChoice) : false) ? "true" : "false"}
                  className="bank-category-confirmation-child-item"
                  key={subGroup.key}
                  onClick={() => {
                    if (subGroup.hasThirdLevel) {
                      setSelectedSubKey(subGroup.key);
                      return;
                    }
                    const choice = subGroup.choices[0];
                    if (choice) {
                      stageChoice(choice);
                    }
                  }}
                  role="menuitem"
                  type="button"
                >
                  <span>{subGroup.subLabel}</span>
                </button>
              ))}
            </div>
            {selectedSubGroup?.hasThirdLevel ? (
              <>
                <div className="bank-category-confirmation-divider" aria-hidden="true" role="separator" />
                <div
                  aria-label={`${selectedSubGroup.subLabel}${thirdLabelSuffix}`}
                  className="bank-category-confirmation-third-list"
                  role="menu"
                >
                  {selectedSubGroup.choices.map((choice) => (
                    <button
                      aria-current={stagedChoice ? choiceKey(choice) === choiceKey(stagedChoice) ? "true" : "false" : "false"}
                      className="bank-category-confirmation-third-item"
                      key={choiceKey(choice)}
                      onClick={() => stageChoice(choice)}
                      role="menuitem"
                      type="button"
                    >
                      <span>{choice.thirdLabel ?? choiceSubLabel(choice)}</span>
                    </button>
                  ))}
                </div>
              </>
            ) : null}
          </div>
          <div className="bank-category-confirmation-footer">
            <button className="bank-category-confirmation-cancel" type="button" onClick={closeConfirmationPanel}>
              取消
            </button>
            <button
              className="bank-category-confirmation-save"
              onClick={saveStagedChoice}
              disabled={!canOperateData || !stagedChoice || confirming}
              type="button"
            >
              {confirming ? "保存中" : "保存"}
            </button>
          </div>
        </div>
      </div>,
      document.body,
    ) : null;
    const openSelection = (event: MouseEvent<HTMLButtonElement>) => {
      if (canOperateData && !confirming) {
        setAnchorEl(event.currentTarget);
        updateConfirmationPanelPosition(event.currentTarget);
      }
    };
    if (autoCategoryCanBeReassigned) {
      return (
        <span ref={confirmationRef} className="bank-manual-category-stack">
          {autoCategoryDisplay}
          <button
            aria-controls={anchorEl ? `bank-category-confirmation-${row.id}` : undefined}
            aria-expanded={anchorEl ? "true" : undefined}
            aria-haspopup="menu"
            className="bank-manual-category-revoke"
            disabled={!canOperateData || confirming}
            onClick={openSelection}
            type="button"
          >
            撤销
          </button>
          {confirmationPanel}
        </span>
      );
    }
    return (
      <span ref={confirmationRef} className="bank-category-confirmation-host">
        <button
          aria-controls={anchorEl ? `bank-category-confirmation-${row.id}` : undefined}
          aria-expanded={anchorEl ? "true" : undefined}
          aria-haspopup="menu"
          className="bank-category-confirmation-trigger"
          onClick={openSelection}
          aria-disabled={!canOperateData || confirming ? "true" : undefined}
          data-tone={confirmationGroups.length > 0 ? "warning" : "info"}
          disabled={!canOperateData || confirming}
          type="button"
        >
          {triggerLabel}
        </button>
        {confirmationPanel}
      </span>
    );
  }
  if (row.categoryResolutionStatus === "manual_confirmed" && row.effectiveCategoryCode) {
    const displayLabel = row.effectiveCategoryLabelPath.length
      ? row.effectiveCategoryLabelPath.join(" / ")
      : [row.effectiveCategoryPrimaryLabel, row.effectiveCategorySubLabel].filter(Boolean).join(" / ") || row.effectiveCategoryLabel || row.effectiveCategoryCode;
    return (
      <span className="bank-manual-category-stack">
        <BankCategoryTag
          categoryCode={row.effectiveCategoryCode}
          compact
          hierarchyTooltip
          label={displayLabel}
        />
        <button
          type="button"
          className="bank-manual-category-revoke"
          onClick={() => {
            if (!canOperateData) {
              return;
            }
            if (row.effectiveCategorySource === "manual") {
              onClearAssignment(row);
            } else {
              onRevoke(row);
            }
          }}
          disabled={!canOperateData || confirming}
        >
          撤销
        </button>
      </span>
    );
  }
  return autoCategoryDisplay;
}

function BankTextCell({ value }: { value: string }) {
  return (
    <span className="bank-table-text-cell">
      {value.trim() || "-"}
    </span>
  );
}

export default function BankDetailsPage() {
  const { active, activationGeneration } = useOptionalPageActivation("bank-details");
  const { runOperation } = useGlobalOperationOverlay();
  const { canOperateData } = useSessionPermissions();
  const selectedAccountSession = usePageSessionState<string | null>({
    pageKey: "bank-details",
    stateKey: "selectedAccountKey",
    version: 2,
    initialValue: ALL_ACCOUNTS_KEY,
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: (value): value is string | null => value === null || typeof value === "string",
  });
  const dateFilterSession = usePageSessionState<BankDateFilter>({
    pageKey: "bank-details",
    stateKey: "dateFilter",
    version: 4,
    initialValue: createDateFilter("year", DEFAULT_BANK_YEAR),
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: isBankDateFilter,
  });
  const [accountsData, setAccountsData] = useState<{
    accounts: BankDetailAccount[];
    totalBalance: string | null;
    missingBalanceAccountCount: number;
  }>({ accounts: [], totalBalance: null, missingBalanceAccountCount: 0 });
  const selectedAccountKey = selectedAccountSession.value;
  const setSelectedAccountKey = selectedAccountSession.setValue;
  const dateFilter = dateFilterSession.value;
  const setDateFilter = dateFilterSession.setValue;
  const [rows, setRows] = useState<BankDetailTransaction[]>([]);
  const [statistics, setStatistics] = useState<BankDetailStatistics | null>(null);
  const [rowCount, setRowCount] = useState(0);
  const [paginationModel, setPaginationModel] = useState({
    page: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  });
  const [searchInput, setSearchInput] = useState("");
  const [searchKeyword, setSearchKeyword] = useState("");
  const [loading, setLoading] = useState(true);
  const [rowLoading, setRowLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [categoryFilterSnapshot, setCategoryFilterSnapshot] = useState<CategoryFilterSnapshot>({
    queryKey: "",
    totalCount: 0,
    categoryCounts: EMPTY_CATEGORY_COUNTS,
    tagDefinitions: [],
  });
  const [activeAutoTagRules, setActiveAutoTagRules] = useState<BankAutoTagEditableRule[]>([]);
  const [selectedCategoryFilter, setSelectedCategoryFilter] = useState<BankCategoryFilter>(ALL_CATEGORY_FILTER);
  const selectedCategoryRequestParams = useMemo(
    () => categoryFilterRequestParams(selectedCategoryFilter),
    [selectedCategoryFilter],
  );
  const tagVersionRef = useRef<number | null>(readPersistedTagVersion());
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [exportFeedback, setExportFeedback] = useState<string | null>(null);
  const [rulesDrawerOpen, setRulesDrawerOpen] = useState(false);
  const [rulesFeedback, setRulesFeedback] = useState<string | null>(null);
  const [categoryMutationId, setCategoryMutationId] = useState<string | null>(null);
  const hasAccountPayloadRef = useRef(false);
  const hasTransactionPayloadRef = useRef(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const selectedTransactionAccountKey = selectedAccountKey === ALL_ACCOUNTS_KEY ? null : selectedAccountKey || null;
  const categoryFilterQueryKey = useMemo(() => categoryFilterSnapshotKey({
    accountKey: selectedTransactionAccountKey,
    dateFrom: dateFilter.dateFrom,
    dateTo: dateFilter.dateTo,
    keyword: searchKeyword,
  }), [dateFilter.dateFrom, dateFilter.dateTo, searchKeyword, selectedTransactionAccountKey]);
  const categorySnapshotCurrent = categoryFilterSnapshot.queryKey === categoryFilterQueryKey;
  const categoryCounts = categorySnapshotCurrent ? categoryFilterSnapshot.categoryCounts : EMPTY_CATEGORY_COUNTS;
  const categoryOptions = categorySnapshotCurrent ? categoryFilterSnapshot.tagDefinitions : [];
  const categoryFilterTotalCount = categorySnapshotCurrent ? categoryFilterSnapshot.totalCount : 0;

  const applyCategorySnapshotPayload = useCallback((payload: BankDetailTransactionsResponse, snapshotQueryKey: string) => {
    setCategoryFilterSnapshot((current) => ({
      queryKey: snapshotQueryKey,
      totalCount: payload.pagination.total,
      categoryCounts: payload.categoryCounts,
      tagDefinitions: payload.tagDictionary?.tags
        ? activeTagDefinitions(payload.tagDictionary.tags)
        : current.queryKey === snapshotQueryKey
        ? current.tagDefinitions
        : [],
    }));
    if (typeof payload.tagDictionary?.version === "number" && payload.tagDictionary.version > 0) {
      tagVersionRef.current = payload.tagDictionary.version;
      persistTagVersion(payload.tagDictionary.version);
    }
  }, []);

  const applyTransactionsPayload = useCallback((
    payload: BankDetailTransactionsResponse,
    {
      snapshotQueryKey,
      requestHasCategoryFilter,
    }: {
      snapshotQueryKey: string;
      requestHasCategoryFilter: boolean;
    },
  ) => {
    setStatistics(payload.statistics ?? null);
    hasTransactionPayloadRef.current = true;
    setRows(payload.rows);
    setRowCount(payload.pagination.total);
    if (!requestHasCategoryFilter) {
      applyCategorySnapshotPayload(payload, snapshotQueryKey);
    }
    if (typeof payload.tagDictionary?.version === "number" && payload.tagDictionary.version > 0) {
      tagVersionRef.current = payload.tagDictionary.version;
      persistTagVersion(payload.tagDictionary.version);
    }
  }, [applyCategorySnapshotPayload]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    const controller = new AbortController();
    setLoading(!hasAccountPayloadRef.current);
    setError(null);
    fetchBankDetailAccounts({
      dateFrom: dateFilter.dateFrom,
      dateTo: dateFilter.dateTo,
      signal: controller.signal,
    })
      .then((payload) => {
        hasAccountPayloadRef.current = true;
        setAccountsData({
          accounts: payload.accounts,
          totalBalance: payload.totalBalance,
          missingBalanceAccountCount: payload.missingBalanceAccountCount,
        });
        setSelectedAccountKey((current) => (
          current && (current === ALL_ACCOUNTS_KEY || payload.accounts.some((account) => account.accountKey === current))
            ? current
            : ALL_ACCOUNTS_KEY
        ));
      })
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setError(caught instanceof Error ? caught.message : "银行明细加载失败。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [activationGeneration, active, dateFilter.dateFrom, dateFilter.dateTo, refreshToken, setSelectedAccountKey]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    const controller = new AbortController();
    fetchBankAutoTagRules({ signal: controller.signal })
      .then((payload) => {
        setActiveAutoTagRules(payload.activeRules);
      })
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setError(caught instanceof Error ? caught.message : "自动标签规则加载失败。");
        }
      });
    return () => controller.abort();
  }, [active, activationGeneration, refreshToken]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    if (!selectedAccountKey) {
      setRows([]);
      setRowCount(0);
      setStatistics(null);
      setCategoryFilterSnapshot({
        queryKey: "",
        totalCount: 0,
        categoryCounts: EMPTY_CATEGORY_COUNTS,
        tagDefinitions: [],
      });
      return;
    }
    const controller = new AbortController();
    setRowLoading(!hasTransactionPayloadRef.current);
    setError(null);
    const accountKey = selectedTransactionAccountKey;
    const snapshotQueryKey = categoryFilterQueryKey;
    const requestHasCategoryFilter = hasCategoryRequestFilter(selectedCategoryRequestParams);

    if (requestHasCategoryFilter) {
      fetchBankDetailTransactions({
        accountKey,
        dateFrom: dateFilter.dateFrom,
        dateTo: dateFilter.dateTo,
        keyword: searchKeyword,
        page: 1,
        pageSize: 1,
        signal: controller.signal,
      })
        .then((payload) => {
          applyCategorySnapshotPayload(payload, snapshotQueryKey);
        })
        .catch((caught) => {
          if (!isAbortLikeError(caught)) {
            setError(caught instanceof Error ? caught.message : "银行流水标签统计加载失败。");
          }
        });
    }

    fetchBankDetailTransactions({
      accountKey,
      dateFrom: dateFilter.dateFrom,
      dateTo: dateFilter.dateTo,
      keyword: searchKeyword,
      categoryCode: selectedCategoryRequestParams.categoryCode,
      categoryPrimaryLabel: selectedCategoryRequestParams.categoryPrimaryLabel,
      categorySubLabel: selectedCategoryRequestParams.categorySubLabel,
      categoryThirdLabel: selectedCategoryRequestParams.categoryThirdLabel,
      page: paginationModel.page + 1,
      pageSize: paginationModel.pageSize,
      signal: controller.signal,
    })
      .then((payload) => {
        applyTransactionsPayload(payload, { snapshotQueryKey, requestHasCategoryFilter });
      })
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setStatistics(null);
          setError(caught instanceof Error ? caught.message : "银行流水加载失败。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setRowLoading(false);
        }
      });
    return () => controller.abort();
  }, [
    applyCategorySnapshotPayload,
    applyTransactionsPayload,
    activationGeneration,
    active,
    categoryFilterQueryKey,
    dateFilter.dateFrom,
    dateFilter.dateTo,
    paginationModel.page,
    paginationModel.pageSize,
    refreshToken,
    searchKeyword,
    selectedAccountKey,
    selectedTransactionAccountKey,
    selectedCategoryRequestParams.categoryCode,
    selectedCategoryRequestParams.categoryPrimaryLabel,
    selectedCategoryRequestParams.categorySubLabel,
    selectedCategoryRequestParams.categoryThirdLabel,
  ]);

  useEffect(() => {
    if (!categorySnapshotCurrent) {
      return;
    }
    if (!selectedCategoryFilterStillExists(selectedCategoryFilter, categoryOptions)) {
      setSelectedCategoryFilter(ALL_CATEGORY_FILTER);
    }
  }, [categoryOptions, categorySnapshotCurrent, selectedCategoryFilter]);

  const effectiveCategoryCounts = categoryCounts;
  const visibleCategorySummary = useMemo<CategorySummaryItem[]>(() => {
    const optionByCode = new Map(categoryOptions.map((option) => [option.code, option]));
    const selectedTagCode = selectedCategoryFilter.kind === "tag" ? selectedCategoryFilter.code : null;
    const toSummaryItem = (option: BankTransactionTagDefinition): CategorySummaryItem => {
      const displayParts = tagDefinitionDisplayParts(option);
      return {
        code: option.code,
        label: tagDefinitionDisplayLabel(option),
        primaryLabel: displayParts.primaryLabel,
        subLabel: displayParts.subLabel,
        count: effectiveCategoryCounts[option.code] ?? 0,
      };
    };
    const featured = FEATURED_CATEGORY_CODES
      .map((code) => optionByCode.get(code))
      .filter((option): option is BankTransactionTagDefinition => Boolean(option))
      .map(toSummaryItem);
    const active = categoryOptions
      .filter((option) => (
        !FEATURED_CATEGORY_CODES.includes(option.code)
        && ((effectiveCategoryCounts[option.code] ?? 0) > 0 || option.code === selectedTagCode)
      ))
      .map(toSummaryItem);
    return [...featured, ...active];
  }, [categoryOptions, effectiveCategoryCounts, selectedCategoryFilter]);

  const selectedAccount = useMemo(
    () => accountsData.accounts.find((account) => account.accountKey === selectedAccountKey) ?? null,
    [accountsData.accounts, selectedAccountKey],
  );
  const isAllAccountsSelected = selectedAccountKey === ALL_ACCOUNTS_KEY;
  const totalTransactionCount = useMemo(
    () => accountsData.accounts.reduce((sum, account) => sum + account.transactionCount, 0),
    [accountsData.accounts],
  );
  const currentViewTitle = isAllAccountsSelected ? "全部流水" : selectedAccount?.displayName ?? "账户流水";

  const resetToFirstPage = () => {
    setPaginationModel((current) => (
      current.page === 0 ? current : { ...current, page: 0 }
    ));
  };

  const applyDateFilter = (nextFilter: BankDateFilter | ((current: BankDateFilter) => BankDateFilter)) => {
    resetToFirstPage();
    setDateFilter(nextFilter);
  };

  const handleAccountSelect = (accountKey: string) => {
    if (accountKey === selectedAccountKey) {
      return;
    }
    resetToFirstPage();
    setSelectedAccountKey(accountKey);
  };

  const handleSearchKeywordChange = (value: string) => {
    setSearchInput(value);
  };

  const handleSearchSubmit = () => {
    resetToFirstPage();
    setSearchKeyword(searchInput.trim());
  };

  const handleSearchClear = () => {
    resetToFirstPage();
    setSearchInput("");
    setSearchKeyword("");
  };

  const applyOptimisticCategoryChoice = (row: BankDetailTransaction, choice: ConfirmationChoice) => {
    const labelPath = choice.labelPath.length
      ? choice.labelPath
      : [choice.primaryLabel, choice.subLabel, choice.thirdLabel].filter((value): value is string => Boolean(value));
    const categoryLabel = labelPath.join(" / ") || choice.categoryCode;
    const nextRow: BankDetailTransaction = {
      ...row,
      categoryCode: choice.categoryCode,
      categoryLabel,
      categoryPath: labelPath,
      categoryPrimaryLabel: choice.primaryLabel,
      categorySubLabel: choice.subLabel,
      categoryThirdLabel: choice.thirdLabel,
      categoryLabelPath: labelPath,
      categorySource: "manual",
      categoryResolutionStatus: "manual_confirmed",
      manualConfirmedCategoryCode: choice.categoryCode,
      effectiveCategoryCode: choice.categoryCode,
      effectiveCategoryLabel: categoryLabel,
      effectiveCategoryPath: labelPath,
      effectiveCategoryPrimaryLabel: choice.primaryLabel,
      effectiveCategorySubLabel: choice.subLabel,
      effectiveCategoryThirdLabel: choice.thirdLabel,
      effectiveCategoryLabelPath: labelPath,
      effectiveCategorySource: "manual",
    };
    const rowStillVisible = (() => {
      if (selectedCategoryFilter.kind === "uncategorized") {
        return false;
      }
      if (selectedCategoryFilter.kind === "tag") {
        return selectedCategoryFilter.code === choice.categoryCode;
      }
      if (selectedCategoryFilter.kind === "primary") {
        return selectedCategoryFilter.primaryLabel === choice.primaryLabel;
      }
      return true;
    })();
    setRows((currentRows) => (
      rowStillVisible
        ? currentRows.map((currentRow) => (currentRow.id === row.id ? nextRow : currentRow))
        : currentRows.filter((currentRow) => currentRow.id !== row.id)
    ));
    setRowCount((current) => (rowStillVisible ? current : Math.max(0, current - 1)));
    setCategoryFilterSnapshot((current) => (
      current.queryKey === categoryFilterQueryKey
        ? {
          ...current,
          categoryCounts: {
            ...current.categoryCounts,
            uncategorized: Math.max(0, Number(current.categoryCounts.uncategorized ?? 0) - 1),
            [choice.categoryCode]: Number(current.categoryCounts[choice.categoryCode] ?? 0) + 1,
          },
        }
        : current
    ));
  };

  const applyOptimisticManualCategoryClear = (row: BankDetailTransaction) => {
    const nextRow: BankDetailTransaction = {
      ...row,
      categoryCode: null,
      categoryLabel: null,
      categoryPath: [],
      categoryPrimaryLabel: null,
      categorySubLabel: null,
      categoryThirdLabel: null,
      categoryLabelPath: [],
      categorySource: "",
      categoryResolutionStatus: "unmatched",
      manualConfirmedCategoryCode: null,
      effectiveCategoryCode: null,
      effectiveCategoryLabel: null,
      effectiveCategoryPath: [],
      effectiveCategoryPrimaryLabel: null,
      effectiveCategorySubLabel: null,
      effectiveCategoryThirdLabel: null,
      effectiveCategoryLabelPath: [],
      effectiveCategorySource: "",
    };
    const rowStillVisible = selectedCategoryFilter.kind === "all"
      || selectedCategoryFilter.kind === "uncategorized";
    setRows((currentRows) => (
      rowStillVisible
        ? currentRows.map((currentRow) => (currentRow.id === row.id ? nextRow : currentRow))
        : currentRows.filter((currentRow) => currentRow.id !== row.id)
    ));
    setRowCount((current) => (rowStillVisible ? current : Math.max(0, current - 1)));
    setCategoryFilterSnapshot((current) => (
      current.queryKey === categoryFilterQueryKey
        ? {
          ...current,
          categoryCounts: {
            ...current.categoryCounts,
            uncategorized: Number(current.categoryCounts.uncategorized ?? 0) + 1,
            ...(row.effectiveCategoryCode
              ? {
                [row.effectiveCategoryCode]: Math.max(
                  0,
                  Number(current.categoryCounts[row.effectiveCategoryCode] ?? 0) - 1,
                ),
              }
              : {}),
          },
        }
        : current
    ));
  };

  const handleConfirmCategory = (row: BankDetailTransaction, choice: ConfirmationChoice) => {
    setCategoryMutationId(row.id);
    setError(null);
    return confirmBankDetailCategory(row.id, choice.categoryCode, choice.thirdLabel)
      .then(() => {
        applyOptimisticCategoryChoice(row, choice);
        setRefreshToken((current) => current + 1);
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "银行明细标签确认失败。");
        throw caught;
      })
      .finally(() => setCategoryMutationId(null));
  };

  const handleAssignCategory = (row: BankDetailTransaction, choice: ConfirmationChoice) => {
    setCategoryMutationId(row.id);
    setError(null);
    const structuredSelection = choice.thirdLabel || choice.turnoverActionType
      ? {
        categoryPrimaryLabel: choice.primaryLabel,
        categorySubLabel: choice.subLabel,
        categoryThirdLabel: choice.thirdLabel,
        categoryLabelPath: choice.labelPath,
        turnoverActionType: choice.turnoverActionType,
        turnoverFamily: choice.turnoverFamily,
      }
      : {};
    return assignBankDetailCategory(row.id, choice.categoryCode, structuredSelection)
      .then(() => {
        applyOptimisticCategoryChoice(row, choice);
        setRefreshToken((current) => current + 1);
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "银行明细标签设置失败。");
        throw caught;
      })
      .finally(() => setCategoryMutationId(null));
  };

  const handleRevokeCategoryConfirmation = (row: BankDetailTransaction) => {
    setCategoryMutationId(row.id);
    setError(null);
    revokeBankDetailCategoryConfirmation(row.id)
      .then(() => {
        setRefreshToken((current) => current + 1);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "银行明细标签撤销失败。"))
      .finally(() => setCategoryMutationId(null));
  };

  const handleClearCategoryAssignment = (row: BankDetailTransaction) => {
    setCategoryMutationId(row.id);
    setError(null);
    clearBankDetailCategoryAssignment(row.id)
      .then(() => {
        applyOptimisticManualCategoryClear(row);
        setRefreshToken((current) => current + 1);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "银行明细标签撤销失败。"))
      .finally(() => setCategoryMutationId(null));
  };

  const handleCategoryFilterChange = (filter: BankCategoryFilter) => {
    resetToFirstPage();
    setSelectedCategoryFilter(filter);
  };

  const openExportMenu = () => {
    setExportMenuOpen((current) => !current);
  };

  const closeExportMenu = () => {
    setExportMenuOpen(false);
  };

  const reloadTransactionsAfterRulesMutation = useCallback(async () => {
    const accountKey = selectedTransactionAccountKey;
    const snapshotQueryKey = categoryFilterQueryKey;
    const requestHasCategoryFilter = hasCategoryRequestFilter(selectedCategoryRequestParams);
    setRowLoading(true);
    setError(null);
    try {
      if (requestHasCategoryFilter) {
        const snapshotPayload = await fetchBankDetailTransactions({
          accountKey,
          dateFrom: dateFilter.dateFrom,
          dateTo: dateFilter.dateTo,
          keyword: searchKeyword,
          page: 1,
          pageSize: 1,
        });
        applyCategorySnapshotPayload(snapshotPayload, snapshotQueryKey);
      }

      const latestPayload = await fetchBankDetailTransactions({
        accountKey,
        dateFrom: dateFilter.dateFrom,
        dateTo: dateFilter.dateTo,
        keyword: searchKeyword,
        categoryCode: selectedCategoryRequestParams.categoryCode,
        categoryPrimaryLabel: selectedCategoryRequestParams.categoryPrimaryLabel,
        categorySubLabel: selectedCategoryRequestParams.categorySubLabel,
        categoryThirdLabel: selectedCategoryRequestParams.categoryThirdLabel,
        page: paginationModel.page + 1,
        pageSize: paginationModel.pageSize,
      });
      applyTransactionsPayload(latestPayload, { snapshotQueryKey, requestHasCategoryFilter });
      return latestPayload;
    } finally {
      setRowLoading(false);
    }
  }, [
    applyCategorySnapshotPayload,
    applyTransactionsPayload,
    categoryFilterQueryKey,
    dateFilter.dateFrom,
    dateFilter.dateTo,
    paginationModel.page,
    paginationModel.pageSize,
    searchKeyword,
    selectedCategoryRequestParams.categoryCode,
    selectedCategoryRequestParams.categoryPrimaryLabel,
    selectedCategoryRequestParams.categorySubLabel,
    selectedCategoryRequestParams.categoryThirdLabel,
    selectedTransactionAccountKey,
  ]);

  const handleExport = (mode: BankDetailExportMode) => {
    closeExportMenu();
    const accountKey = selectedAccountKey === ALL_ACCOUNTS_KEY ? null : selectedAccountKey;
    if (mode === "account" && !accountKey) {
      setExportFeedback("请选择具体银行账户");
      return;
    }
    setIsExporting(true);
    setExportFeedback(null);
    downloadBankDetailTransactionsExport({
      mode,
      accountKey,
      dateFrom: dateFilter.dateFrom,
      dateTo: dateFilter.dateTo,
      keyword: searchKeyword,
      categoryCode: selectedCategoryRequestParams.categoryCode,
      categoryPrimaryLabel: selectedCategoryRequestParams.categoryPrimaryLabel,
      categorySubLabel: selectedCategoryRequestParams.categorySubLabel,
      categoryThirdLabel: selectedCategoryRequestParams.categoryThirdLabel,
    })
      .then(({ blob, fileName }) => {
        const objectUrl = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = fileName;
        link.rel = "noopener";
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(objectUrl);
        setExportFeedback("已开始下载");
      })
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setExportFeedback(caught instanceof Error ? caught.message : "银行明细导出失败。");
        }
      })
      .finally(() => {
        setIsExporting(false);
      });
  };

  const publishAutoTagRulesSaved = useCallback((payload: BankAutoTagRulesResponse) => {
    persistTagVersion(payload.version);
    tagVersionRef.current = payload.version;
    setActiveAutoTagRules(payload.activeRules);
    return payload.refreshReason === "reapplied" ? "重新应用已完成。" : "规则已保存。";
  }, []);

  const saveAutoTagRulesWithRefresh = useCallback(async (request: SaveBankAutoTagRulesRequest) => {
    const result = await runOperation({
      loadingMessage: "正在保存自动标签规则...",
      action: async () => {
        const payload = await saveBankAutoTagRules(request);
        const feedback = publishAutoTagRulesSaved(payload);
        await reloadTransactionsAfterRulesMutation();
        setRulesFeedback(feedback);
        return payload;
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "自动标签规则保存失败。",
    });
    if (result.status === "success") {
      return result.value;
    }
    throw result.error;
  }, [publishAutoTagRulesSaved, reloadTransactionsAfterRulesMutation, runOperation]);

  const reapplyAutoTagRulesWithRefresh = useCallback(async () => {
    const result = await runOperation({
      loadingMessage: "正在重新应用自动标签规则...",
      action: async ({ setMessage }) => {
        const payload = await reapplyBankAutoTagRules();
        const feedback = publishAutoTagRulesSaved(payload);
        setMessage("正在重新读取银行流水...");
        await reloadTransactionsAfterRulesMutation();
        setRulesFeedback(feedback);
        return payload;
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "自动标签规则重新应用失败。",
    });
    if (result.status === "success") {
      return result.value;
    }
    throw result.error;
  }, [publishAutoTagRulesSaved, reloadTransactionsAfterRulesMutation, runOperation]);

  const selectedDateFilterYear = dateFilter.preset === "month"
    ? dateFilter.month.slice(0, 4)
    : dateFilter.preset === "year"
      ? dateFilter.year
      : DEFAULT_BANK_YEAR;
  const visibleStatistics = statistics;
  const titleAccessory = (
    <div className="page-title-accessory-group">
      <PageStatisticsPopover
        ariaLabel="银行明细数据统计"
        loading={loading && !hasTransactionPayloadRef.current}
        coreItems={[
          { label: "流水", value: visibleStatistics?.transactionCount, unit: "笔" },
          { label: "支出", value: visibleStatistics?.expenseTransactionCount, unit: "笔", tone: "expense" },
          { label: "收入", value: visibleStatistics?.incomeTransactionCount, unit: "笔", tone: "income" },
        ]}
        detailItems={[
          { label: "已分类", value: visibleStatistics?.classifiedTransactionCount, unit: "笔" },
          { label: "未分类", value: visibleStatistics?.unclassifiedTransactionCount, unit: "笔", tone: "warning" },
        ]}
      />
    </div>
  );

  return (
    <div className="bank-details-page" data-testid="bank-details-page">
      <header className="page-header bank-details-page-header">
        <div className="page-title-row">
          <h1 className="page-title">银行明细</h1>
          {titleAccessory ? <div className="page-title-accessory">{titleAccessory}</div> : null}
        </div>
        <div className="page-header-actions">
          <Button
            aria-label="刷新银行明细"
            isDisabled={loading || rowLoading}
            onPress={() => setRefreshToken((current) => current + 1)}
            size="sm"
            variant="secondary"
          >
            <RefreshCw aria-hidden="true" size={16} />
            刷新
          </Button>
        </div>
      </header>
      <div className="bank-details-workbench">
        {error ? (
          <div className="bank-details-error-live" role="alert" aria-live="polite">
            {error}
          </div>
        ) : null}
        {loading ? <StatePanel tone="loading" compact>正在加载银行明细。</StatePanel> : null}
        {rulesFeedback ? (
          <StatePanel tone="success" compact>
            {rulesFeedback}
          </StatePanel>
        ) : null}
        {!loading && accountsData.accounts.length === 0 ? (
          <StatePanel tone="empty">暂无银行流水，请先在银行流水导入页面导入。</StatePanel>
        ) : null}

        <div className="bank-details-layout">
          <aside className="bank-account-tree">
            <div className="bank-account-summary">
              <span className="bank-account-summary-label">总余额</span>
              <strong className="bank-balance-value bank-total-balance">
                {displayBalance(accountsData.totalBalance)}
              </strong>
              <div className="bank-account-summary-tags">
                <span className="bank-account-total-chip bank-chip-auto-size">{accountsData.accounts.length} 个账户</span>
                {accountsData.missingBalanceAccountCount > 0 ? (
                  <span className="bank-account-empty-chip bank-chip-auto-size">{accountsData.missingBalanceAccountCount} 个无余额</span>
                ) : null}
              </div>
            </div>
            <ul aria-label="银行账户" className="bank-account-list">
              <li>
                <button
                  aria-current={isAllAccountsSelected ? "true" : undefined}
                  aria-label={`全部流水 ${totalTransactionCount} 条`}
                  className={`bank-account-node bank-account-all-node${isAllAccountsSelected ? " active" : ""}`}
                  onClick={() => handleAccountSelect(ALL_ACCOUNTS_KEY)}
                  type="button"
                >
                  <span className="bank-account-title-row">
                    <span className="bank-account-identity">
                      <span className="bank-account-name">全部</span>
                    </span>
                    <span className="bank-account-count-chip bank-account-title-count bank-chip-auto-size">{totalTransactionCount} 条</span>
                  </span>
                  <span className="bank-account-inline-balance bank-account-secondary-balance bank-balance-value">
                    {displayBalance(accountsData.totalBalance)}
                  </span>
                </button>
              </li>
              {accountsData.accounts.length > 0 ? (
                <li className="bank-account-divider" aria-hidden="true" role="separator" />
              ) : null}
              {accountsData.accounts.map((account, index) => {
                const selected = account.accountKey === selectedAccountKey;
                const showDivider = index < accountsData.accounts.length - 1;
                return (
                  <Fragment key={account.accountKey}>
                    <li>
                      <button
                        aria-current={selected ? "true" : undefined}
                        aria-label={`${account.displayName} 余额 ${displayBalance(account.latestBalance)} ${account.transactionCount} 条`}
                        className={`bank-account-node${selected ? " active" : ""}`}
                        onClick={() => handleAccountSelect(account.accountKey)}
                        type="button"
                      >
                        <span className="bank-account-title-row">
                          <span className="bank-account-identity">
                            <span className="bank-account-name">{account.bankName}</span>
                            <span className="bank-account-last4">{account.accountLast4}</span>
                          </span>
                          <span className="bank-account-count-chip bank-account-title-count bank-chip-auto-size">{account.transactionCount} 条</span>
                        </span>
                        <span className="bank-account-metric-row">
                          {account.hasBalance ? (
                            <span className="bank-account-inline-balance bank-account-secondary-balance bank-balance-value">
                              {displayBalance(account.latestBalance)}
                            </span>
                          ) : null}
                          {!account.hasBalance ? (
                            <span className="bank-account-empty-chip bank-chip-auto-size">余额为空</span>
                          ) : null}
                        </span>
                      </button>
                    </li>
                    {showDivider ? <li className="bank-account-divider" aria-hidden="true" role="separator" /> : null}
                  </Fragment>
                );
              })}
            </ul>
          </aside>

          <section className="bank-transaction-panel">
            <div className="bank-transaction-toolbar">
              <div className="bank-transaction-header">
                <div className="bank-transaction-title-row">
                  <h2 className="bank-transaction-title">
                    {currentViewTitle}
                  </h2>
                </div>

                <div className="bank-header-controls">
                  <button
                    className="bank-auto-rules-button"
                    onClick={() => setRulesDrawerOpen(true)}
                    type="button"
                  >
                    <Tags aria-hidden="true" size={14} />
                    自动标签规则
                  </button>
                  <BusinessPeriodPicker
                    ariaLabel="银行明细时间范围"
                    onChange={(selection) => applyDateFilter(createDateFilter(
                      selection.mode,
                      selection.mode === "month" ? selection.month : selection.year,
                    ))}
                    selection={{
                      mode: dateFilter.preset,
                      year: selectedDateFilterYear,
                      month: dateFilter.preset === "month" ? dateFilter.month : `${selectedDateFilterYear}-01`,
                    }}
                    years={nearbyBusinessYears(selectedDateFilterYear)}
                  />
                </div>
              </div>
            </div>

            <hr className="bank-transaction-divider" />

            <div className="bank-transaction-grid bank-transaction-grid-readable">
              <BankCategoryFilterControl
                categoryCounts={effectiveCategoryCounts}
                totalCount={categoryFilterTotalCount}
                visibleCategorySummary={visibleCategorySummary}
                selectedCategoryFilter={selectedCategoryFilter}
                onCategoryFilterChange={handleCategoryFilterChange}
              />
              <BankDetailsTableToolbar
                searchKeyword={searchInput}
                onSearchKeywordChange={handleSearchKeywordChange}
                onSearchSubmit={handleSearchSubmit}
                onSearchClear={handleSearchClear}
                exportMenuOpen={exportMenuOpen}
                exportFeedback={exportFeedback}
                isExporting={isExporting}
                canExportCurrentAccount={!isAllAccountsSelected}
                onOpenExportMenu={openExportMenu}
                onCloseExportMenu={closeExportMenu}
                onExport={handleExport}
              />
              <div className="bank-transaction-table-container">
                <FinanceTable ariaLabel="交易流水" className="bank-transaction-table" minWidth={980} scrollMode="contained">
                  <FinanceTableHeader>
                    <FinanceTableColumn className="bank-col-counterparty" columnRole="identity" id="counterparty" isRowHeader>对方户名</FinanceTableColumn>
                    <FinanceTableColumn className="bank-col-type" columnRole="status" id="type">类型</FinanceTableColumn>
                    <FinanceTableColumn className="bank-col-amount" columnRole="amount" id="amount">金额</FinanceTableColumn>
                    <FinanceTableColumn className="bank-col-balance" columnRole="amount" id="balance">余额</FinanceTableColumn>
                    <FinanceTableColumn className="bank-col-purpose" columnRole="description" id="purpose">用途/交易用途</FinanceTableColumn>
                    <FinanceTableColumn className="bank-col-summary" columnRole="description" id="summary">摘要</FinanceTableColumn>
                    <FinanceTableColumn className="bank-col-note" columnRole="description" id="note">备注/附言/客户附言</FinanceTableColumn>
                  </FinanceTableHeader>
                  <FinanceTableBody>
                    {rowLoading ? (
                      <FinanceTableRow id="loading" className="bank-transaction-state-row" textValue="正在加载流水。">
                        <FinanceTableCell columnRole="identity" textValue="正在加载流水。">
                          <span className="bank-transaction-state-message">正在加载流水。</span>
                        </FinanceTableCell>
                        <FinanceTableCell columnRole="status" textValue="loading">-</FinanceTableCell>
                        <FinanceTableCell columnRole="amount" textValue="loading">-</FinanceTableCell>
                        <FinanceTableCell columnRole="amount" textValue="loading">-</FinanceTableCell>
                        <FinanceTableCell columnRole="description" textValue="loading">-</FinanceTableCell>
                        <FinanceTableCell columnRole="description" textValue="loading">-</FinanceTableCell>
                        <FinanceTableCell columnRole="description" textValue="loading">-</FinanceTableCell>
                      </FinanceTableRow>
                    ) : null}
                    {!rowLoading && rows.length === 0 ? (
                      <FinanceTableRow id="empty" className="bank-transaction-state-row" textValue="当前时间范围内没有流水。">
                        <FinanceTableCell columnRole="identity" textValue="当前时间范围内没有流水。">
                          <EmptyTransactionOverlay />
                        </FinanceTableCell>
                        <FinanceTableCell columnRole="status" textValue="empty">-</FinanceTableCell>
                        <FinanceTableCell columnRole="amount" textValue="empty">-</FinanceTableCell>
                        <FinanceTableCell columnRole="amount" textValue="empty">-</FinanceTableCell>
                        <FinanceTableCell columnRole="description" textValue="empty">-</FinanceTableCell>
                        <FinanceTableCell columnRole="description" textValue="empty">-</FinanceTableCell>
                        <FinanceTableCell columnRole="description" textValue="empty">-</FinanceTableCell>
                      </FinanceTableRow>
                    ) : null}
                    {!rowLoading && rows.map((row, index) => (
                      <FinanceTableRow
                        className={index % 2 === 0 ? "bank-grid-row-even" : "bank-grid-row-odd"}
                        id={row.id}
                        key={row.id}
                        textValue={row.counterpartyName}
                      >
                        <FinanceTableCell className="bank-col-counterparty" columnRole="identity" textValue={row.counterpartyName}>
                          <div className="bank-counterparty-cell">
                            <span className={`bank-counterparty-name ${counterpartyNameDensity(row.counterpartyName)}`}>
                              {row.counterpartyName}
                            </span>
                            <div className="bank-counterparty-meta-row">
                              <span className="bank-trade-time-text">{formatDateTimeText(row.tradeTime)}</span>
                              <div className="bank-relation-chip-row">
                                {row.relationTags.map((tag) => (
                                  <Chip
                                    key={`${row.id}-${tag}`}
                                    className={`bank-relation-tag bank-relation-tag-${relationTagTone(tag)} bank-chip-auto-size`}
                                    color={relationTagColor(tag)}
                                    size="sm"
                                    variant="soft"
                                  >
                                    <Chip.Label className="bank-chip-label">{tag}</Chip.Label>
                                  </Chip>
                                ))}
                              </div>
                            </div>
                          </div>
                        </FinanceTableCell>
                        <FinanceTableCell className="bank-col-type" columnRole="status" textValue={row.effectiveCategoryLabel || row.autoCategoryLabel || row.categoryResolutionStatus}>
                          <TypeCell
                            row={row}
                            autoTagRules={activeAutoTagRules}
                            confirming={categoryMutationId === row.id}
                            canOperateData={canOperateData}
                            onConfirm={handleConfirmCategory}
                            onAssign={handleAssignCategory}
                            onRevoke={handleRevokeCategoryConfirmation}
                            onClearAssignment={handleClearCategoryAssignment}
                          />
                        </FinanceTableCell>
                        <FinanceTableCell className="bank-col-amount" columnRole="amount" textValue={formatMoney(row.amount)}>
                          <div className="bank-amount-cell">
                            <div className="bank-amount-line">
                              <Chip
                                className={`direction-tag bank-direction-tag-centered bank-chip-auto-size ${row.direction}`}
                                color={directionTagColor(row.direction)}
                                size="sm"
                                variant="soft"
                              >
                                <Chip.Label className="bank-chip-label">{row.directionLabel}</Chip.Label>
                              </Chip>
                              <span className="bank-amount-value">
                                {formatMoney(row.amount)}
                              </span>
                            </div>
                            <span className="bank-source-chip bank-chip-auto-size">
                              <span className="bank-chip-label">{`${row.bankName} ${row.accountLast4}`}</span>
                            </span>
                          </div>
                        </FinanceTableCell>
                        <FinanceTableCell className="bank-col-balance" columnRole="amount" textValue={formatMoney(row.balance)}>
                          <span className="bank-balance-value">
                            {formatMoney(row.balance)}
                          </span>
                        </FinanceTableCell>
                        <FinanceTableCell className="bank-col-purpose" columnRole="description" textValue={row.purposeText}><BankTextCell value={row.purposeText} /></FinanceTableCell>
                        <FinanceTableCell className="bank-col-summary" columnRole="description" textValue={row.summaryText}><BankTextCell value={row.summaryText} /></FinanceTableCell>
                        <FinanceTableCell className="bank-col-note" columnRole="description" textValue={row.noteText}><BankTextCell value={row.noteText} /></FinanceTableCell>
                      </FinanceTableRow>
                    ))}
                  </FinanceTableBody>
                </FinanceTable>
              </div>
              <BankTransactionPagination
                page={paginationModel.page}
                pageSize={paginationModel.pageSize}
                pageSizeOptions={[25, 50, 100]}
                total={rowCount}
                onPageChange={(page) => setPaginationModel((current) => ({ ...current, page }))}
                onPageSizeChange={(pageSize) => {
                  setPaginationModel({ page: 0, pageSize });
                }}
              />
            </div>
          </section>
        </div>
      </div>
      <AutoTagRulesDrawer
        open={rulesDrawerOpen}
        onClose={() => setRulesDrawerOpen(false)}
        onSaved={() => undefined}
        canOperateData={canOperateData}
        saveAutoTagRules={saveAutoTagRulesWithRefresh}
        reapplyAutoTagRules={reapplyAutoTagRulesWithRefresh}
      />
    </div>
  );
}
