import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent, type RefObject } from "react";
import { Filter, Tags } from "lucide-react";

import {
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../components/common/FinanceTable";
import StatePanel from "../components/common/StatePanel";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
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
  revokeBankDetailCategoryConfirmation,
} from "../features/bankDetails/api";
import {
  FINANCE_DOMAIN_EVENTS,
  emitFinanceDomainEvent,
  eventAffectedMonths,
} from "../features/domainEvents";
import { useActiveFinanceDomainEvent } from "../hooks/useActiveFinanceDomainEvent";
import { usePageScrollSession } from "../hooks/usePageScrollSession";
import type {
  BankAutoTagRulesResponse,
  BankAutoTagEditableRule,
  BankDateFilter,
  BankDetailAccount,
  BankDetailExportMode,
  BankDetailReadModelStatus,
  BankDetailTransaction,
  BankTransactionCategoryCode,
  BankTransactionCategoryCounts,
} from "../features/bankDetails/types";
import type { BankTransactionTagDefinition } from "../features/pendingInvoices/types";

const TODAY = new Date(2026, 4, 2);
const DEFAULT_PAGE_SIZE = 100;
const BANK_DETAIL_READ_MODEL_REFRESH_RETRY_MS = 1000;
const ALL_ACCOUNTS_KEY = "__all_bank_accounts__";
const TAG_SYNC_EVENT = "finops:bank-transaction-tags-updated";
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

function categoryFilterMatches(selected: BankCategoryFilter, candidate: BankCategoryFilter) {
  if (selected.kind !== candidate.kind) {
    return false;
  }
  switch (selected.kind) {
    case "all":
    case "uncategorized":
      return true;
    case "primary":
      return candidate.kind === "primary" && selected.primaryLabel === candidate.primaryLabel;
    case "tag":
      return (
        candidate.kind === "tag"
        && selected.code === candidate.code
        && selected.primaryLabel === candidate.primaryLabel
        && selected.subLabel === candidate.subLabel
      );
  }
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
  dateFrom: string;
  dateTo: string;
  keyword: string;
}) {
  return JSON.stringify({
    accountKey: accountKey || "",
    dateFrom,
    dateTo,
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

function normalizeReadModelStatus(value: BankDetailReadModelStatus | null | undefined): BankDetailReadModelStatus {
  return value === "refreshing" || value === "stale" || value === "schema_mismatch" || value === "missing"
    ? value
    : "fresh";
}

function combinedReadModelStatus(
  accountsStatus: BankDetailReadModelStatus,
  transactionsStatus: BankDetailReadModelStatus,
): BankDetailReadModelStatus {
  if (accountsStatus === "refreshing" || transactionsStatus === "refreshing") {
    return "refreshing";
  }
  if (accountsStatus === "schema_mismatch" || transactionsStatus === "schema_mismatch") {
    return "schema_mismatch";
  }
  if (accountsStatus === "stale" || transactionsStatus === "stale") {
    return "stale";
  }
  if (accountsStatus === "missing" || transactionsStatus === "missing") {
    return "missing";
  }
  return "fresh";
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

function daysAgo(days: number) {
  const date = new Date(TODAY);
  date.setDate(date.getDate() - days);
  return date;
}

function endOfMonth(year: number, monthIndex: number) {
  return new Date(year, monthIndex + 1, 0);
}

function createDateFilter(preset: BankDateFilter["preset"], monthValue = "2026-05"): BankDateFilter {
  if (preset === "previous_month") {
    return { preset, dateFrom: "2026-04-01", dateTo: "2026-04-30" };
  }
  if (preset === "last_7_days") {
    return { preset, dateFrom: formatDate(daysAgo(6)), dateTo: formatDate(TODAY) };
  }
  if (preset === "last_30_days") {
    return { preset, dateFrom: formatDate(daysAgo(29)), dateTo: formatDate(TODAY) };
  }
  if (preset === "current_year") {
    return { preset, dateFrom: "2026-01-01", dateTo: "2026-12-31" };
  }
  if (preset === "month") {
    const [year, month] = monthValue.split("-").map(Number);
    return {
      preset,
      dateFrom: `${year}-${String(month).padStart(2, "0")}-01`,
      dateTo: formatDate(endOfMonth(year, month - 1)),
    };
  }
  return { preset: "current_month", dateFrom: "2026-05-01", dateTo: "2026-05-31" };
}

function displayBalance(value: string | null) {
  return value && value.trim() ? formatMoney(value) : "余额为空";
}

function formatMoney(value: string | null) {
  if (!value || !value.trim()) {
    return "";
  }
  const parsed = Number(value.replace(/,/g, ""));
  if (!Number.isFinite(parsed)) {
    return value;
  }
  return parsed.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function relationTagTone(tag: string) {
  return tag.startsWith("有") ? "has" : "none";
}

function monthIndex(value: string) {
  if (!/^\d{4}-\d{2}$/.test(value)) {
    return null;
  }
  const [year, month] = value.split("-").map(Number);
  return year * 12 + month;
}

function eventTagVersion(event: Event) {
  if (!(event instanceof CustomEvent) || !event.detail || typeof event.detail !== "object") {
    return null;
  }
  const version = Number((event.detail as { version?: unknown }).version);
  return Number.isFinite(version) ? version : null;
}

function eventActiveAutoTagRules(event: Event): BankAutoTagEditableRule[] | null {
  if (!(event instanceof CustomEvent) || !event.detail || typeof event.detail !== "object") {
    return null;
  }
  const activeRules = (event.detail as { activeRules?: unknown }).activeRules;
  return Array.isArray(activeRules) ? activeRules as BankAutoTagEditableRule[] : null;
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

function affectedMonthsHitDateFilter(affectedMonths: string[] | null, dateFilter: BankDateFilter) {
  if (!affectedMonths || affectedMonths.length === 0 || affectedMonths.includes("all")) {
    return true;
  }
  const startMonth = monthIndex(dateFilter.dateFrom.slice(0, 7));
  const endMonth = monthIndex(dateFilter.dateTo.slice(0, 7));
  if (startMonth === null || endMonth === null) {
    return true;
  }
  return affectedMonths.some((month) => {
    const index = monthIndex(month);
    return index === null || (index >= startMonth && index <= endMonth);
  });
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
  return (
    typeof filter.preset === "string"
    && typeof filter.dateFrom === "string"
    && typeof filter.dateTo === "string"
  );
}

function EmptyTransactionOverlay() {
  return (
    <div className="bank-empty-transaction-overlay">
      <span>当前时间范围内没有流水。</span>
    </div>
  );
}

function useCloseOnOutsidePointer(open: boolean, rootRef: RefObject<HTMLElement | null>, onClose: () => void) {
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && rootRef.current?.contains(target)) {
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
  const [categoryAnchorEl, setCategoryAnchorEl] = useState<HTMLElement | null>(null);
  const categoryPanelOpen = Boolean(categoryAnchorEl);
  const categoryPanelId = "bank-category-filter-panel";
  const categoryFilterRef = useRef<HTMLDivElement | null>(null);
  const categoryGroups = useMemo(() => buildCategoryTree(visibleCategorySummary), [visibleCategorySummary]);
  const selectedCategoryLabel = selectedCategoryFilterLabel({
    counts: categoryCounts,
    groups: categoryGroups,
    selectedFilter: selectedCategoryFilter,
    totalCount,
    visibleSummary: visibleCategorySummary,
  });

  const closeCategoryPanel = () => {
    setCategoryAnchorEl(null);
  };

  const toggleCategoryPanel = (event: MouseEvent<HTMLElement>) => {
    setCategoryAnchorEl((current) => (current ? null : event.currentTarget));
  };

  const handleCategoryPanelKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      closeCategoryPanel();
    }
  };

  const selectCategoryFilter = (filter: BankCategoryFilter) => {
    onCategoryFilterChange(filter);
  };

  useCloseOnOutsidePointer(categoryPanelOpen, categoryFilterRef, closeCategoryPanel);

  const renderCategoryFilterButton = (
    filter: BankCategoryFilter,
    label: string,
    count: number,
    level: "root" | "primary" | "child",
    className = "",
  ) => {
    const selected = categoryFilterMatches(selectedCategoryFilter, filter);
    return (
      <button
        aria-label={`${label} ${count}`}
        aria-current={selected ? "true" : "false"}
        className={`bank-category-filter-row ${className}`.trim()}
        data-level={level}
        onClick={() => selectCategoryFilter(filter)}
        role="menuitem"
        type="button"
      >
        <span className="bank-category-filter-row-content">
          <span className="bank-category-filter-label">{label}</span>
          <span className="bank-category-filter-count">{count}</span>
        </span>
      </button>
    );
  };

  return (
    <div ref={categoryFilterRef} className="bank-category-filter-float" onKeyDown={handleCategoryPanelKeyDown}>
      <button
        aria-controls={categoryPanelOpen ? categoryPanelId : undefined}
        aria-expanded={categoryPanelOpen ? "true" : undefined}
        aria-haspopup="menu"
        aria-label={`标签筛选：${selectedCategoryLabel}`}
        className={`bank-category-filter-icon-button${selectedCategoryFilter.kind === "all" ? "" : " active"}`}
        onClick={toggleCategoryPanel}
        title={selectedCategoryLabel}
        type="button"
      >
        <Filter size={14} strokeWidth={2.2} />
        {selectedCategoryFilter.kind === "all" ? null : <span className="bank-category-filter-active-dot" aria-hidden="true" />}
      </button>
      {categoryPanelOpen ? (
        <div className="bank-category-filter-popper">
          <div className="bank-category-filter-panel">
            <div
              aria-label="银行明细标签筛选"
              className="bank-category-filter-list"
              id={categoryPanelId}
              role="menu"
            >
              <div className="bank-category-filter-actions" role="group">
                {renderCategoryFilterButton(ALL_CATEGORY_FILTER, "全部", totalCount, "root", "bank-category-filter-action")}
                {renderCategoryFilterButton(
                  UNCATEGORIZED_CATEGORY_FILTER,
                  "未分类",
                  categoryCounts.uncategorized ?? 0,
                  "root",
                  "bank-category-filter-action",
                )}
              </div>
              <div className="bank-category-filter-divider" aria-hidden="true" role="separator" />
              <div className="bank-category-filter-sections" role="group">
                {categoryGroups.map((group, groupIndex) => (
                  <div
                    className={`bank-category-filter-group bank-category-filter-hierarchy-group bank-category-filter-tone-${groupIndex % 6}`}
                    key={group.key}
                  >
                    {renderCategoryFilterButton(
                      group.directItem && group.children.length === 0
                        ? tagCategoryFilter(group.directItem)
                        : { kind: "primary", primaryLabel: group.label },
                      group.label,
                      group.count,
                      "primary",
                      "bank-category-filter-primary-row",
                    )}
                    {group.directItem && group.children.length > 0 ? (
                      renderCategoryFilterButton(
                        tagCategoryFilter(group.directItem),
                        group.label,
                        group.directItem.count,
                        "child",
                        "bank-category-filter-child-row bank-category-filter-hierarchy-item bank-category-filter-direct-child",
                      )
                    ) : null}
                    {group.children.length > 0 ? (
                      <div className="bank-category-filter-children" role="group">
                        {group.children.map((child) => (
                          <Fragment key={child.code}>
                            {renderCategoryFilterButton(
                              tagCategoryFilter(child),
                              child.subLabel || child.label,
                              child.count,
                              "child",
                              "bank-category-filter-child-row bank-category-filter-hierarchy-item",
                            )}
                          </Fragment>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function BankDetailsTableToolbar({
  searchKeyword = "",
  onSearchKeywordChange = () => undefined,
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
          {exportFeedback ? (
            <span className="bank-export-feedback">
              {exportFeedback}
            </span>
          ) : null}
          <div className="bank-export-menu-host">
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
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    onCloseExportMenu();
                  }
                }}
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
          <input
            aria-label="搜索流水"
            className="bank-grid-search-field"
            placeholder="搜索流水"
            value={searchKeyword}
            onChange={(event) => onSearchKeywordChange(event.target.value)}
          />
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
  return buildConfirmationChoiceGroupsFromChoices(activeRules.flatMap(confirmationChoicesFromAutoTagRule));
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
  return buildConfirmationChoiceGroupsFromChoices(candidates.map((candidate) => {
    const candidateChoice = confirmationChoiceFromCandidate(candidate);
    if (!candidateChoice) {
      return null;
    }
    return activeChoiceKeys.has(choiceKey(candidateChoice)) || activeChoiceKeys.has(`${candidateChoice.categoryCode}\u0000`)
      ? candidateChoice
      : null;
  }));
}

function TypeCell({
  row,
  autoTagRules,
  confirming,
  onConfirm,
  onAssign,
  onRevoke,
  onClearAssignment,
}: {
  row: BankDetailTransaction;
  autoTagRules: BankAutoTagEditableRule[];
  confirming: boolean;
  onConfirm: (row: BankDetailTransaction, choice: ConfirmationChoice) => Promise<void>;
  onAssign: (row: BankDetailTransaction, choice: ConfirmationChoice) => Promise<void>;
  onRevoke: (row: BankDetailTransaction) => void;
  onClearAssignment: (row: BankDetailTransaction) => void;
}) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const [stagedChoice, setStagedChoice] = useState<ConfirmationChoice | null>(null);
  const [internalTooltipOpen, setInternalTooltipOpen] = useState(false);
  const confirmationRef = useRef<HTMLSpanElement | null>(null);
  const confirmationGroups = useMemo(
    () => (row.categoryResolutionStatus === "needs_confirmation"
      ? buildConfirmationChoiceGroups(row.autoCandidateCategories, autoTagRules)
      : []),
    [autoTagRules, row.autoCandidateCategories, row.categoryResolutionStatus],
  );
  const assignmentGroups = useMemo(
    () => (row.categoryResolutionStatus === "unmatched" && !row.effectiveCategoryCode
      ? buildAssignmentChoiceGroups(autoTagRules)
      : []),
    [autoTagRules, row.categoryResolutionStatus, row.effectiveCategoryCode],
  );
  const isManualAssignment = assignmentGroups.length > 0;
  const selectionGroups = confirmationGroups.length > 0 ? confirmationGroups : assignmentGroups;
  const selectionLabel = confirmationGroups.length > 0 ? "待确认" : "待分类";
  const triggerLabel = stagedChoice ? choiceDisplayLabel(stagedChoice) : selectionLabel;
  const childLabelSuffix = confirmationGroups.length > 0 ? "候选标签" : "可选标签";
  const thirdLabelSuffix = confirmationGroups.length > 0 ? "候选业务类型" : "可选业务类型";
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

  const closeConfirmationPanel = () => {
    if (confirming) {
      return;
    }
    setAnchorEl(null);
    setStagedChoice(null);
  };
  const stageChoice = (choice: ConfirmationChoice) => {
    if (confirming) {
      return;
    }
    setStagedChoice(choice);
  };
  const saveStagedChoice = () => {
    if (!stagedChoice || confirming) {
      return;
    }
    const choice = stagedChoice;
    setAnchorEl(null);
    const request = isManualAssignment ? onAssign(row, choice) : onConfirm(row, choice);
    request
      .then(() => setStagedChoice(null))
      .catch(() => setStagedChoice(null));
  };
  useCloseOnOutsidePointer(Boolean(anchorEl), confirmationRef, closeConfirmationPanel);

  if (selectionGroups.length > 0) {
    return (
      <span ref={confirmationRef} className="bank-category-confirmation-host">
        <button
          aria-controls={anchorEl ? `bank-category-confirmation-${row.id}` : undefined}
          aria-expanded={anchorEl ? "true" : undefined}
          aria-haspopup="menu"
          className="bank-category-confirmation-trigger"
          onClick={(event) => {
            if (!confirming) {
              setAnchorEl(event.currentTarget);
            }
          }}
          aria-disabled={confirming ? "true" : undefined}
          data-tone={isManualAssignment ? "info" : "warning"}
          type="button"
        >
          {triggerLabel}
        </button>
        {anchorEl ? (
          <div className="bank-category-confirmation-popper">
            <div
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
                  disabled={!stagedChoice || confirming}
                  type="button"
                >
                  {confirming ? "保存中" : "保存"}
                </button>
              </div>
            </div>
          </div>
        ) : null}
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
            if (row.effectiveCategorySource === "manual") {
              onClearAssignment(row);
            } else {
              onRevoke(row);
            }
          }}
          disabled={confirming}
        >
          撤销
        </button>
      </span>
    );
  }
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
          <span className="bank-internal-transfer-tooltip-title">
            对应内部往来流水
          </span>
          <span className="bank-internal-transfer-tooltip-grid">
            <span className="bank-internal-transfer-tooltip-label">时间</span>
            <span className="bank-internal-transfer-tooltip-value">{counterpart.tradeTime || "-"}</span>
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
  const pageActiveRef = useRef(active);
  const pendingTagRefreshRef = useRef(false);
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
    version: 2,
    initialValue: createDateFilter("current_year"),
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: isBankDateFilter,
  });
  const monthValueSession = usePageSessionState<string>({
    pageKey: "bank-details",
    stateKey: "monthValue",
    version: 1,
    initialValue: "2026-05",
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: (value): value is string => typeof value === "string" && /^\d{4}-\d{2}$/.test(value),
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
  const monthValue = monthValueSession.value;
  const setMonthValue = monthValueSession.setValue;
  const [rows, setRows] = useState<BankDetailTransaction[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [paginationModel, setPaginationModel] = useState({
    page: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  });
  const [searchInput, setSearchInput] = useState("");
  const [searchKeyword, setSearchKeyword] = useState("");
  const [accountsReadModelStatus, setAccountsReadModelStatus] = useState<BankDetailReadModelStatus>("fresh");
  const [transactionsReadModelStatus, setTransactionsReadModelStatus] = useState<BankDetailReadModelStatus>("fresh");
  const [loading, setLoading] = useState(true);
  const [rowLoading, setRowLoading] = useState(false);
  const [accountRequestPending, setAccountRequestPending] = useState(false);
  const [transactionRequestPending, setTransactionRequestPending] = useState(false);
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
  const [dateFilterAnchorEl, setDateFilterAnchorEl] = useState<HTMLElement | null>(null);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [exportFeedback, setExportFeedback] = useState<string | null>(null);
  const [rulesDrawerOpen, setRulesDrawerOpen] = useState(false);
  const [rulesFeedback, setRulesFeedback] = useState<string | null>(null);
  const [rulesRefreshStatus, setRulesRefreshStatus] = useState<"idle" | "refreshing" | "fresh">("idle");
  const [categoryMutationId, setCategoryMutationId] = useState<string | null>(null);
  const rulesRefreshPendingRef = useRef(false);
  const rulesRefreshFeedbackRef = useRef({
    refreshing: "规则已保存，银行明细正在刷新。",
    fresh: "规则已保存，银行明细已刷新。",
  });
  const hasAccountPayloadRef = useRef(false);
  const hasTransactionPayloadRef = useRef(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const transactionTableWrapRef = usePageScrollSession<HTMLDivElement>({
    pageKey: "bank-details",
    scrollKey: "transactions-table",
  });
  const readModelStatus = combinedReadModelStatus(accountsReadModelStatus, transactionsReadModelStatus);
  const readModelNeedsRefresh = readModelStatus !== "fresh";
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

  const refreshAutoTagRules = useCallback(() => {
    fetchBankAutoTagRules()
      .then((payload) => {
        setActiveAutoTagRules(payload.activeRules);
      })
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setError(caught instanceof Error ? caught.message : "自动标签规则加载失败。");
        }
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setAccountRequestPending(true);
    setLoading(!hasAccountPayloadRef.current);
    setError(null);
    fetchBankDetailAccounts({
      dateFrom: dateFilter.dateFrom,
      dateTo: dateFilter.dateTo,
      signal: controller.signal,
    })
      .then((payload) => {
        const nextReadModelStatus = normalizeReadModelStatus(payload.readModelStatus);
        setAccountsReadModelStatus(nextReadModelStatus);
        if (nextReadModelStatus !== "fresh" && hasAccountPayloadRef.current) {
          return;
        }
        if (nextReadModelStatus !== "fresh" && payload.accounts.length === 0) {
          return;
        }
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
          setAccountRequestPending(false);
        }
      });
    return () => controller.abort();
  }, [dateFilter.dateFrom, dateFilter.dateTo, setSelectedAccountKey]);

  useEffect(() => {
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
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearchKeyword(searchInput.trim());
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    if (!selectedAccountKey) {
      setRows([]);
      setRowCount(0);
      setCategoryFilterSnapshot({
        queryKey: "",
        totalCount: 0,
        categoryCounts: EMPTY_CATEGORY_COUNTS,
        tagDefinitions: [],
      });
      return;
    }
    const controller = new AbortController();
    setTransactionRequestPending(true);
    setRowLoading(!hasTransactionPayloadRef.current);
    setError(null);
    const accountKey = selectedTransactionAccountKey;
    const snapshotQueryKey = categoryFilterQueryKey;
    const requestHasCategoryFilter = hasCategoryRequestFilter(selectedCategoryRequestParams);
    const updateSnapshotFromPayload = (payload: Awaited<ReturnType<typeof fetchBankDetailTransactions>>) => {
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
    };

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
          const nextReadModelStatus = normalizeReadModelStatus(payload.readModelStatus);
          if (nextReadModelStatus !== "fresh" && payload.rows.length === 0) {
            return;
          }
          updateSnapshotFromPayload(payload);
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
        const nextReadModelStatus = normalizeReadModelStatus(payload.readModelStatus);
        setTransactionsReadModelStatus(nextReadModelStatus);
        if (nextReadModelStatus !== "fresh" && payload.rows.length === 0) {
          return;
        }
        hasTransactionPayloadRef.current = true;
        setRows(payload.rows);
        setRowCount(payload.pagination.total);
        if (!requestHasCategoryFilter) {
          updateSnapshotFromPayload(payload);
        }
        if (typeof payload.tagDictionary?.version === "number" && payload.tagDictionary.version > 0) {
          tagVersionRef.current = payload.tagDictionary.version;
          persistTagVersion(payload.tagDictionary.version);
        }
      })
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setError(caught instanceof Error ? caught.message : "银行流水加载失败。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setRowLoading(false);
          setTransactionRequestPending(false);
        }
      });
    return () => controller.abort();
  }, [
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

  useEffect(() => {
    if (!rulesRefreshPendingRef.current) {
      return;
    }
    if (readModelNeedsRefresh) {
      setRulesRefreshStatus("refreshing");
      setRulesFeedback(rulesRefreshFeedbackRef.current.refreshing);
      return;
    }
    rulesRefreshPendingRef.current = false;
    setRulesRefreshStatus("fresh");
    setRulesFeedback(rulesRefreshFeedbackRef.current.fresh);
  }, [readModelNeedsRefresh]);

  useEffect(() => {
    if (!active || !readModelNeedsRefresh || loading || rowLoading || accountRequestPending || transactionRequestPending) {
      return undefined;
    }
    const retryId = window.setTimeout(() => {
      setRefreshToken((current) => current + 1);
    }, BANK_DETAIL_READ_MODEL_REFRESH_RETRY_MS);
    return () => window.clearTimeout(retryId);
  }, [accountRequestPending, active, loading, readModelNeedsRefresh, refreshToken, rowLoading, transactionRequestPending]);

  const handleWorkbenchRelationUpdated = useCallback((event: Event) => {
    const affectedMonths = eventAffectedMonths(event);
    if (!affectedMonthsHitDateFilter(affectedMonths, dateFilter)) {
      return;
    }
    setRefreshToken((current) => current + 1);
  }, [dateFilter]);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, handleWorkbenchRelationUpdated);

  useEffect(() => {
    pageActiveRef.current = active;
    if (!active || !pendingTagRefreshRef.current) {
      return;
    }
    pendingTagRefreshRef.current = false;
    refreshAutoTagRules();
    setRefreshToken((current) => current + 1);
  }, [active, activationGeneration, refreshAutoTagRules]);

  useEffect(() => {
    const handleTagUpdate = (event: Event) => {
      const version = eventTagVersion(event);
      if (version !== null) {
        tagVersionRef.current = version;
        persistTagVersion(version);
      }
      if (!pageActiveRef.current) {
        pendingTagRefreshRef.current = true;
        return;
      }
      const activeRules = eventActiveAutoTagRules(event);
      if (activeRules) {
        setActiveAutoTagRules(activeRules);
      } else {
        refreshAutoTagRules();
      }
      setRefreshToken((current) => current + 1);
    };
    window.addEventListener(TAG_SYNC_EVENT, handleTagUpdate);

    let channel: BroadcastChannel | null = null;
    if (typeof BroadcastChannel !== "undefined") {
      channel = new BroadcastChannel(TAG_SYNC_EVENT);
      channel.onmessage = (message) => {
        const version = Number((message.data as { version?: unknown } | undefined)?.version);
        const activeRules = (message.data as { activeRules?: unknown } | undefined)?.activeRules;
        window.dispatchEvent(new CustomEvent(TAG_SYNC_EVENT, {
          detail: {
            version: Number.isFinite(version) ? version : undefined,
            activeRules: Array.isArray(activeRules) ? activeRules : undefined,
          },
        }));
      };
    }

    const handleFocus = () => {
      if (!pageActiveRef.current) {
        return;
      }
      const persistedVersion = readPersistedTagVersion();
      if (persistedVersion !== null && persistedVersion !== tagVersionRef.current) {
        tagVersionRef.current = persistedVersion;
      }
      refreshAutoTagRules();
      setRefreshToken((current) => current + 1);
    };
    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener(TAG_SYNC_EVENT, handleTagUpdate);
      window.removeEventListener("focus", handleFocus);
      channel?.close();
    };
  }, [refreshAutoTagRules]);

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
  const dateFilterOpen = Boolean(dateFilterAnchorEl);

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
    resetToFirstPage();
    setSearchInput(value);
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

  const handleConfirmCategory = (row: BankDetailTransaction, choice: ConfirmationChoice) => {
    setCategoryMutationId(row.id);
    setError(null);
    return confirmBankDetailCategory(row.id, choice.categoryCode, choice.thirdLabel)
      .then(() => {
        applyOptimisticCategoryChoice(row, choice);
        emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, {
          affectedRowIds: [row.id],
          action: "bank_detail_category_confirmed",
        });
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
        emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, {
          affectedRowIds: [row.id],
          action: "bank_detail_category_manually_assigned",
        });
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
      .then(() => setRefreshToken((current) => current + 1))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "银行明细标签撤销失败。"))
      .finally(() => setCategoryMutationId(null));
  };

  const handleClearCategoryAssignment = (row: BankDetailTransaction) => {
    setCategoryMutationId(row.id);
    setError(null);
    clearBankDetailCategoryAssignment(row.id)
      .then(() => setRefreshToken((current) => current + 1))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "银行明细标签撤销失败。"))
      .finally(() => setCategoryMutationId(null));
  };

  const handleCategoryFilterChange = (filter: BankCategoryFilter) => {
    resetToFirstPage();
    setSelectedCategoryFilter(filter);
  };

  const applyPreset = (preset: BankDateFilter["preset"]) => {
    applyDateFilter(createDateFilter(preset, monthValue));
  };

  const openDateFilterPopover = (event: MouseEvent<HTMLElement>) => {
    setDateFilterAnchorEl(event.currentTarget);
  };

  const closeDateFilterPopover = () => {
    setDateFilterAnchorEl(null);
  };

  const openExportMenu = () => {
    setExportMenuOpen((current) => !current);
  };

  const closeExportMenu = () => {
    setExportMenuOpen(false);
  };

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

  const handleAutoTagRulesSaved = (payload: BankAutoTagRulesResponse) => {
    persistTagVersion(payload.version);
    tagVersionRef.current = payload.version;
    setActiveAutoTagRules(payload.activeRules);
    window.dispatchEvent(new CustomEvent(TAG_SYNC_EVENT, {
      detail: { version: payload.version, activeRules: payload.activeRules },
    }));
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankAutoTagRulesUpdated, {
      version: payload.version,
      activeRules: payload.activeRules,
      source: "bank_details_auto_tag_rules",
      action: payload.refreshReason === "reapplied" ? "reapplied" : "saved",
    });
    if (typeof BroadcastChannel !== "undefined") {
      const channel = new BroadcastChannel(TAG_SYNC_EVENT);
      channel.postMessage({ version: payload.version, activeRules: payload.activeRules });
      channel.close();
    }
    rulesRefreshPendingRef.current = true;
    rulesRefreshFeedbackRef.current = payload.refreshReason === "reapplied"
      ? {
        refreshing: "已提交重新应用，银行明细正在刷新。",
        fresh: "重新应用已完成，银行明细已刷新。",
      }
      : {
        refreshing: "规则已保存，银行明细正在刷新。",
        fresh: "规则已保存，银行明细已刷新。",
      };
    setRulesRefreshStatus("refreshing");
    setRulesFeedback(rulesRefreshFeedbackRef.current.refreshing);
    setTransactionsReadModelStatus("refreshing");
    setRefreshToken((current) => current + 1);
  };

  const handleMonthChange = (value: string) => {
    if (!value) {
      setMonthValue(value);
      return;
    }
    setMonthValue(value);
    resetToFirstPage();
    setDateFilter(createDateFilter("month", value));
  };

  const handleCustomDateChange = (key: "dateFrom" | "dateTo", value: string) => {
    applyDateFilter((current) => ({
      preset: "custom",
      dateFrom: key === "dateFrom" ? value : current.dateFrom,
      dateTo: key === "dateTo" ? value : current.dateTo,
    }));
  };

  const handleCustomDateTextChange = (key: "dateFrom" | "dateTo", value: string) => {
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      handleCustomDateChange(key, value);
    }
  };

  return (
    <div className="bank-details-page" data-testid="bank-details-page">
      <div className="bank-details-workbench">
        {error ? <StatePanel tone="error">{error}</StatePanel> : null}
        {loading ? <StatePanel tone="loading" compact>正在加载银行明细。</StatePanel> : null}
        {rulesFeedback ? <StatePanel tone="success" compact>{rulesFeedback}</StatePanel> : null}
        {!loading && !readModelNeedsRefresh && accountsData.accounts.length === 0 ? (
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
                  <div className="bank-date-toolbar">
                    <div
                      aria-label="日期快捷筛选"
                      className="bank-date-presets"
                      role="group"
                    >
                      {[
                        ["current_month", "本月"],
                        ["previous_month", "上月"],
                        ["last_7_days", "近7天"],
                        ["last_30_days", "近30天"],
                        ["current_year", "今年"],
                      ].map(([preset, label]) => (
                        <button
                          aria-pressed={dateFilter.preset === preset}
                          className={dateFilter.preset === preset ? "active" : ""}
                          key={preset}
                          onClick={() => applyPreset(preset as BankDateFilter["preset"])}
                          type="button"
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <button
                      aria-describedby={dateFilterOpen ? "bank-date-filter-popover" : undefined}
                      className="bank-date-range-button"
                      onClick={openDateFilterPopover}
                      type="button"
                    >
                      {dateFilter.dateFrom} - {dateFilter.dateTo}
                    </button>
                  </div>
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
                exportMenuOpen={exportMenuOpen}
                exportFeedback={exportFeedback}
                isExporting={isExporting}
                canExportCurrentAccount={!isAllAccountsSelected}
                onOpenExportMenu={openExportMenu}
                onCloseExportMenu={closeExportMenu}
                onExport={handleExport}
              />
              <div ref={transactionTableWrapRef} className="bank-transaction-table-container">
                <FinanceTable ariaLabel="交易流水" className="bank-transaction-table" minWidth={980}>
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
                            <div className="bank-relation-time-row">
                              <span className="bank-trade-time-chip bank-trade-time-chip-full bank-chip-auto-size">
                                <span className="bank-chip-label">{row.tradeTime}</span>
                              </span>
                            </div>
                            <div className="bank-relation-chip-row">
                              {row.relationTags.map((tag) => (
                                <span
                                  key={`${row.id}-${tag}`}
                                  className={`bank-relation-tag bank-relation-tag-${relationTagTone(tag)} bank-chip-auto-size`}
                                >
                                  <span className="bank-chip-label">{tag}</span>
                                </span>
                              ))}
                            </div>
                          </div>
                        </FinanceTableCell>
                        <FinanceTableCell className="bank-col-type" columnRole="status" textValue={row.effectiveCategoryLabel || row.autoCategoryLabel || row.categoryResolutionStatus}>
                          <TypeCell
                            row={row}
                            autoTagRules={activeAutoTagRules}
                            confirming={categoryMutationId === row.id}
                            onConfirm={handleConfirmCategory}
                            onAssign={handleAssignCategory}
                            onRevoke={handleRevokeCategoryConfirmation}
                            onClearAssignment={handleClearCategoryAssignment}
                          />
                        </FinanceTableCell>
                        <FinanceTableCell className="bank-col-amount" columnRole="amount" textValue={formatMoney(row.amount)}>
                          <div className="bank-amount-cell">
                            <div className="bank-amount-line">
                              <span className={`direction-tag bank-direction-tag-centered bank-chip-auto-size ${row.direction}`}>
                                <span className="bank-chip-label">{row.directionLabel}</span>
                              </span>
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
        onSaved={handleAutoTagRulesSaved}
        refreshScope={{ dateFrom: dateFilter.dateFrom, dateTo: dateFilter.dateTo }}
        refreshStatus={rulesRefreshStatus}
      />
      {dateFilterOpen ? (
        <div
          className="bank-date-filter-popover"
          id="bank-date-filter-popover"
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              closeDateFilterPopover();
            }
          }}
          role="dialog"
        >
          <div className="bank-date-filter">
            <label className="bank-date-filter-field">
              <span>年月</span>
              <input
                aria-label="年月筛选"
                type="month"
                value={monthValue}
                onChange={(event) => handleMonthChange(event.target.value)}
              />
            </label>
            <label className="bank-date-filter-field">
              <span>开始</span>
              <input
                aria-label="开始日期"
                type="date"
                value={dateFilter.dateFrom}
                onBlur={(event) => handleCustomDateTextChange("dateFrom", event.currentTarget.value)}
                onChange={(event) => handleCustomDateChange("dateFrom", event.currentTarget.value)}
                onInput={(event) => handleCustomDateTextChange("dateFrom", event.currentTarget.value)}
              />
            </label>
            <label className="bank-date-filter-field">
              <span>结束</span>
              <input
                aria-label="结束日期"
                type="date"
                value={dateFilter.dateTo}
                onBlur={(event) => handleCustomDateTextChange("dateTo", event.currentTarget.value)}
                onChange={(event) => handleCustomDateChange("dateTo", event.currentTarget.value)}
                onInput={(event) => handleCustomDateTextChange("dateTo", event.currentTarget.value)}
              />
            </label>
          </div>
        </div>
      ) : null}
    </div>
  );
}
