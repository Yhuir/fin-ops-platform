import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type FocusEvent, type FormEvent, type KeyboardEvent, type MouseEvent } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import ClickAwayListener from "@mui/material/ClickAwayListener";
import Divider from "@mui/material/Divider";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import MenuList from "@mui/material/MenuList";
import Popover from "@mui/material/Popover";
import Popper from "@mui/material/Popper";
import Paper from "@mui/material/Paper";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import RuleIcon from "@mui/icons-material/Rule";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";

import StatePanel from "../components/common/StatePanel";
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
  subscribeFinanceDomainEvent,
} from "../features/domainEvents";
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

type BankDetailsTableToolbarProps = {
  effectiveCategoryCounts: BankTransactionCategoryCounts;
  visibleCategorySummary: CategorySummaryItem[];
  rowCount: number;
  selectedCategoryFilter: BankCategoryFilter;
  onCategoryFilterChange: (filter: BankCategoryFilter) => void;
  searchKeyword: string;
  onSearchKeywordChange: (value: string) => void;
  exportMenuAnchorEl: HTMLElement | null;
  exportFeedback: string | null;
  isExporting: boolean;
  canExportCurrentAccount: boolean;
  onOpenExportMenu: (event: MouseEvent<HTMLElement>) => void;
  onCloseExportMenu: () => void;
  onExport: (mode: BankDetailExportMode) => void;
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

function dateValue(value: string) {
  return value ? dayjs(value) : null;
}

function formatPickerDate(value: Dayjs | null) {
  return value?.isValid() ? value.format("YYYY-MM-DD") : null;
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
    <Stack alignItems="center" justifyContent="center" sx={{ minHeight: 240, px: 2, textAlign: "center" }}>
      <Typography color="text.secondary">当前时间范围内没有流水。</Typography>
    </Stack>
  );
}

function BankDetailsTableToolbar({
  effectiveCategoryCounts = EMPTY_CATEGORY_COUNTS,
  visibleCategorySummary = [],
  rowCount = 0,
  selectedCategoryFilter = ALL_CATEGORY_FILTER,
  onCategoryFilterChange = () => undefined,
  searchKeyword = "",
  onSearchKeywordChange = () => undefined,
  exportMenuAnchorEl = null,
  exportFeedback = null,
  isExporting = false,
  canExportCurrentAccount = false,
  onOpenExportMenu = () => undefined,
  onCloseExportMenu = () => undefined,
  onExport = () => undefined,
}: Partial<BankDetailsTableToolbarProps>) {
  const exportMenuOpen = Boolean(exportMenuAnchorEl);
  const [categoryAnchorEl, setCategoryAnchorEl] = useState<HTMLElement | null>(null);
  const categoryCloseTimerRef = useRef<number | null>(null);
  const categoryPanelOpen = Boolean(categoryAnchorEl);
  const categoryPanelId = "bank-category-filter-panel";
  const categoryGroups = useMemo(() => buildCategoryTree(visibleCategorySummary), [visibleCategorySummary]);
  const selectedCategoryLabel = useMemo(() => {
    if (selectedCategoryFilter.kind === "uncategorized") {
      return `未分类 ${effectiveCategoryCounts.uncategorized}`;
    }
    if (selectedCategoryFilter.kind === "primary") {
      const group = categoryGroups.find((item) => item.label === selectedCategoryFilter.primaryLabel);
      return `${selectedCategoryFilter.primaryLabel} ${group?.count ?? 0}`;
    }
    if (selectedCategoryFilter.kind === "tag") {
      const category = visibleCategorySummary.find((option) => option.code === selectedCategoryFilter.code);
      return category ? `${category.label} ${category.count}` : `${selectedCategoryFilter.primaryLabel} 0`;
    }
    return `全部 ${rowCount}`;
  }, [categoryGroups, effectiveCategoryCounts.uncategorized, rowCount, selectedCategoryFilter, visibleCategorySummary]);

  useEffect(() => () => {
    if (categoryCloseTimerRef.current !== null) {
      window.clearTimeout(categoryCloseTimerRef.current);
    }
  }, []);

  const clearCategoryCloseTimer = () => {
    if (categoryCloseTimerRef.current !== null) {
      window.clearTimeout(categoryCloseTimerRef.current);
      categoryCloseTimerRef.current = null;
    }
  };

  const openCategoryPanel = (event: MouseEvent<HTMLElement> | FocusEvent<HTMLElement>) => {
    clearCategoryCloseTimer();
    setCategoryAnchorEl(event.currentTarget);
  };

  const closeCategoryPanel = () => {
    clearCategoryCloseTimer();
    setCategoryAnchorEl(null);
  };

  const scheduleCategoryPanelClose = () => {
    clearCategoryCloseTimer();
    categoryCloseTimerRef.current = window.setTimeout(() => {
      setCategoryAnchorEl(null);
      categoryCloseTimerRef.current = null;
    }, 140);
  };

  const toggleCategoryPanel = (event: MouseEvent<HTMLElement>) => {
    clearCategoryCloseTimer();
    setCategoryAnchorEl((current) => (current ? null : event.currentTarget));
  };

  const handleCategoryPanelKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      closeCategoryPanel();
    }
  };

  const selectCategoryFilter = (filter: BankCategoryFilter) => {
    onCategoryFilterChange(filter);
    closeCategoryPanel();
  };

  const renderCategoryFilterButton = (
    filter: BankCategoryFilter,
    label: string,
    count: number,
    level: "root" | "primary" | "child",
    className = "",
  ) => {
    const selected = categoryFilterMatches(selectedCategoryFilter, filter);
    return (
    <ListItemButton
      aria-label={`${label} ${count}`}
      aria-current={selected ? "true" : "false"}
      className={`bank-category-filter-row ${className}`.trim()}
      component="button"
      data-level={level}
      onClick={() => selectCategoryFilter(filter)}
      role="menuitem"
      selected={selected}
    >
      <ListItemText
        disableTypography
        primary={(
          <Box className="bank-category-filter-row-content">
            <Typography className="bank-category-filter-label" component="span">{label}</Typography>
            <Typography className="bank-category-filter-count" component="span">{count}</Typography>
          </Box>
        )}
      />
    </ListItemButton>
    );
  };

  return (
    <Box className="bank-grid-toolbar">
      <Stack className="bank-grid-toolbar-content" direction="row" spacing={0.75} alignItems="center">
        <ClickAwayListener onClickAway={closeCategoryPanel}>
          <Box
            className="bank-category-filter-entry"
            onKeyDown={handleCategoryPanelKeyDown}
            onMouseEnter={clearCategoryCloseTimer}
            onMouseLeave={scheduleCategoryPanelClose}
          >
            <Button
              aria-controls={categoryPanelOpen ? categoryPanelId : undefined}
              aria-expanded={categoryPanelOpen ? "true" : undefined}
              aria-haspopup="menu"
              className="bank-category-filter-trigger"
              size="small"
              variant={selectedCategoryFilter.kind === "all" ? "outlined" : "contained"}
              onClick={toggleCategoryPanel}
              onFocus={openCategoryPanel}
              onMouseEnter={openCategoryPanel}
            >
              标签筛选：{selectedCategoryLabel}
            </Button>
            <Popper
              anchorEl={categoryAnchorEl}
              className="bank-category-filter-popper"
              disablePortal
              open={categoryPanelOpen}
              placement="bottom-start"
            >
              <Paper
                className="bank-category-filter-panel"
                elevation={8}
                onMouseEnter={clearCategoryCloseTimer}
                onMouseLeave={scheduleCategoryPanelClose}
              >
                <List
                  aria-label="银行明细标签筛选"
                  className="bank-category-filter-list"
                  dense
                  disablePadding
                  id={categoryPanelId}
                  role="menu"
                >
                  {renderCategoryFilterButton(ALL_CATEGORY_FILTER, "全部", rowCount, "root", "bank-category-filter-action")}
                  {renderCategoryFilterButton(
                    UNCATEGORIZED_CATEGORY_FILTER,
                    "未分类",
                    effectiveCategoryCounts.uncategorized,
                    "root",
                    "bank-category-filter-action",
                  )}
                  <Divider className="bank-category-filter-divider" />
                  {categoryGroups.map((group) => (
                    <Box className="bank-category-filter-group" key={group.key}>
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
                          "bank-category-filter-child-row bank-category-filter-direct-child",
                        )
                      ) : null}
                      {group.children.length > 0 ? (
                        <Box className="bank-category-filter-children" role="group">
                          {group.children.map((child) => (
                            <Fragment key={child.code}>
                              {renderCategoryFilterButton(
                                tagCategoryFilter(child),
                                child.subLabel || child.label,
                                child.count,
                                "child",
                                "bank-category-filter-child-row",
                              )}
                            </Fragment>
                          ))}
                        </Box>
                      ) : null}
                    </Box>
                  ))}
                </List>
              </Paper>
            </Popper>
          </Box>
        </ClickAwayListener>
        <Stack className="bank-grid-toolbar-actions" direction="row" spacing={0.5} alignItems="center">
          {exportFeedback ? (
            <Typography className="bank-export-feedback" color="text.secondary" variant="caption">
              {exportFeedback}
            </Typography>
          ) : null}
          <Button
            aria-controls={exportMenuOpen ? "bank-detail-export-menu" : undefined}
            aria-expanded={exportMenuOpen ? "true" : undefined}
            aria-haspopup="menu"
            className="bank-export-button"
            disabled={isExporting}
            onClick={onOpenExportMenu}
            size="small"
            variant="outlined"
          >
            {isExporting ? "导出中" : "导出"}
          </Button>
          <Menu
            id="bank-detail-export-menu"
            anchorEl={exportMenuAnchorEl}
            open={exportMenuOpen}
            onClose={onCloseExportMenu}
            MenuListProps={{ "aria-label": "导出银行明细" }}
          >
            <MenuItem onClick={() => onExport("all")} disabled={isExporting}>导出全部银行</MenuItem>
            <MenuItem onClick={() => onExport("account")} disabled={isExporting || !canExportCurrentAccount}>导出当前账户</MenuItem>
          </Menu>
          <TextField
            className="bank-grid-search-field"
            size="small"
            placeholder="搜索流水"
            value={searchKeyword}
            onChange={(event) => onSearchKeywordChange(event.target.value)}
            inputProps={{ "aria-label": "搜索流水" }}
          />
        </Stack>
      </Stack>
    </Box>
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

  if (selectionGroups.length > 0) {
    return (
      <>
        <Button
          aria-controls={anchorEl ? `bank-category-confirmation-${row.id}` : undefined}
          aria-expanded={anchorEl ? "true" : undefined}
          aria-haspopup="menu"
          className="bank-category-confirmation-trigger"
          size="small"
          variant="outlined"
          color={isManualAssignment ? "info" : "warning"}
          onClick={(event) => {
            if (!confirming) {
              setAnchorEl(event.currentTarget);
            }
          }}
          aria-disabled={confirming ? "true" : undefined}
        >
          {triggerLabel}
        </Button>
        <Popper
          anchorEl={anchorEl}
          className="bank-category-confirmation-popper"
          open={Boolean(anchorEl)}
          placement="bottom-start"
          modifiers={[
            {
              name: "preventOverflow",
              enabled: true,
              options: { padding: 8, altAxis: true },
            },
            {
              name: "flip",
              enabled: true,
              options: { padding: 8 },
            },
          ]}
        >
          <ClickAwayListener onClickAway={closeConfirmationPanel}>
            <Paper
              className="bank-category-confirmation-panel"
              elevation={8}
              id={`bank-category-confirmation-${row.id}`}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  closeConfirmationPanel();
                }
              }}
            >
              <Box className={`bank-category-confirmation-columns${selectedSubGroup?.hasThirdLevel ? " bank-category-confirmation-columns--three-level" : ""}`}>
                <MenuList
                  aria-label={`${selectionLabel}主标签`}
                  autoFocus
                  className="bank-category-confirmation-primary-list"
                  dense
                  variant="menu"
                >
                  {selectionGroups.map((group) => (
                    <ListItemButton
                      className="bank-category-confirmation-primary-item"
                      component="button"
                      key={group.key}
                      onClick={() => {
                        setSelectedPrimaryKey(group.key);
                        setSelectedSubKey("");
                        setStagedChoice(null);
                      }}
                      role="menuitem"
                      selected={group.key === selectedGroup?.key}
                    >
                      <ListItemText disableTypography primary={<Typography component="span">{group.primaryLabel}</Typography>} />
                    </ListItemButton>
                  ))}
                </MenuList>
                <Divider flexItem orientation="vertical" />
                <MenuList
                  aria-label={`${selectedGroup?.primaryLabel ?? "已选主标签"}${childLabelSuffix}`}
                  className="bank-category-confirmation-child-list"
                  dense
                  variant="menu"
                >
                  {selectedSubGroups.map((subGroup) => (
                    <ListItemButton
                      className="bank-category-confirmation-child-item"
                      component="button"
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
                      selected={subGroup.key === selectedSubGroup?.key || subGroup.choices.some((choice) => stagedChoice ? choiceKey(choice) === choiceKey(stagedChoice) : false)}
                    >
                      <ListItemText
                        disableTypography
                        primary={<Typography component="span">{subGroup.subLabel}</Typography>}
                      />
                    </ListItemButton>
                  ))}
                </MenuList>
                {selectedSubGroup?.hasThirdLevel ? (
                  <>
                    <Divider flexItem orientation="vertical" />
                    <MenuList
                      aria-label={`${selectedSubGroup.subLabel}${thirdLabelSuffix}`}
                      className="bank-category-confirmation-third-list"
                      dense
                      variant="menu"
                    >
                      {selectedSubGroup.choices.map((choice) => (
                        <ListItemButton
                          className="bank-category-confirmation-third-item"
                          component="button"
                          key={choiceKey(choice)}
                          onClick={() => stageChoice(choice)}
                          role="menuitem"
                          selected={stagedChoice ? choiceKey(choice) === choiceKey(stagedChoice) : false}
                        >
                          <ListItemText
                            disableTypography
                            primary={<Typography component="span">{choice.thirdLabel ?? choiceSubLabel(choice)}</Typography>}
                          />
                        </ListItemButton>
                      ))}
                    </MenuList>
                  </>
                ) : null}
              </Box>
              <Box className="bank-category-confirmation-footer">
                <Button size="small" variant="outlined" onClick={closeConfirmationPanel}>
                  取消
                </Button>
                <Button
                  size="small"
                  variant="contained"
                  onClick={saveStagedChoice}
                  disabled={!stagedChoice || confirming}
                >
                  {confirming ? "保存中" : "保存"}
                </Button>
              </Box>
            </Paper>
          </ClickAwayListener>
        </Popper>
      </>
    );
  }
  if (row.categoryResolutionStatus === "manual_confirmed" && row.effectiveCategoryCode) {
    const displayLabel = row.effectiveCategoryLabelPath.length
      ? row.effectiveCategoryLabelPath.join(" / ")
      : [row.effectiveCategoryPrimaryLabel, row.effectiveCategorySubLabel].filter(Boolean).join(" / ") || row.effectiveCategoryLabel || row.effectiveCategoryCode;
    return (
      <Stack spacing={0.5} alignItems="center">
        <BankCategoryTag
          categoryCode={row.effectiveCategoryCode}
          compact
          hierarchyTooltip
          label={displayLabel}
        />
        <Button
          size="small"
          variant="text"
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
        </Button>
      </Stack>
    );
  }
  if (!row.autoCategoryCode || !row.autoCategoryLabel) {
    return <Typography className="bank-auto-type-empty" component="span">-</Typography>;
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
  return (
    <Tooltip
      arrow
      placement="left"
      title={(
        <Box className="bank-internal-transfer-tooltip">
          <Typography className="bank-internal-transfer-tooltip-title" variant="caption">
            对应内部往来流水
          </Typography>
          <Box className="bank-internal-transfer-tooltip-grid">
            <Typography className="bank-internal-transfer-tooltip-label" variant="caption" color="inherit">时间</Typography>
            <Typography className="bank-internal-transfer-tooltip-value" variant="caption" color="inherit">{counterpart.tradeTime || "-"}</Typography>
            <Typography className="bank-internal-transfer-tooltip-label" variant="caption" color="inherit">账户</Typography>
            <Typography className="bank-internal-transfer-tooltip-value" variant="caption" color="inherit">{accountText}</Typography>
            <Typography className="bank-internal-transfer-tooltip-label" variant="caption" color="inherit">金额</Typography>
            <Typography className="bank-internal-transfer-tooltip-value bank-internal-transfer-tooltip-amount" variant="caption" color="inherit">{formatMoney(counterpart.amount) || "-"}</Typography>
            <Typography className="bank-internal-transfer-tooltip-label" variant="caption" color="inherit">对方户名</Typography>
            <Typography className="bank-internal-transfer-tooltip-value" variant="caption" color="inherit">{counterpart.counterpartyName || "-"}</Typography>
          </Box>
        </Box>
      )}
    >
      <Box component="span" className="bank-internal-transfer-tag-anchor">
        {categoryTag}
      </Box>
    </Tooltip>
  );
}

function BankTextCell({ value }: { value: string }) {
  return (
    <Typography className="bank-table-text-cell" component="span" variant="body2">
      {value.trim() || "-"}
    </Typography>
  );
}

export default function BankDetailsPage() {
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
  const [categoryCounts, setCategoryCounts] = useState<BankTransactionCategoryCounts>(EMPTY_CATEGORY_COUNTS);
  const [categoryOptions, setCategoryOptions] = useState<BankTransactionTagDefinition[]>([]);
  const [activeAutoTagRules, setActiveAutoTagRules] = useState<BankAutoTagEditableRule[]>([]);
  const [selectedCategoryFilter, setSelectedCategoryFilter] = useState<BankCategoryFilter>(ALL_CATEGORY_FILTER);
  const selectedCategoryRequestParams = useMemo(
    () => categoryFilterRequestParams(selectedCategoryFilter),
    [selectedCategoryFilter],
  );
  const tagVersionRef = useRef<number | null>(readPersistedTagVersion());
  const [dateFilterAnchorEl, setDateFilterAnchorEl] = useState<HTMLElement | null>(null);
  const [exportMenuAnchorEl, setExportMenuAnchorEl] = useState<HTMLElement | null>(null);
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
  const readModelStatus = combinedReadModelStatus(accountsReadModelStatus, transactionsReadModelStatus);
  const readModelNeedsRefresh = readModelStatus !== "fresh";

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
      setCategoryCounts(EMPTY_CATEGORY_COUNTS);
      return;
    }
    const controller = new AbortController();
    setTransactionRequestPending(true);
    setRowLoading(!hasTransactionPayloadRef.current);
    setError(null);
    const accountKey = selectedAccountKey === ALL_ACCOUNTS_KEY ? null : selectedAccountKey;
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
        setCategoryCounts((current) => (
          selectedCategoryRequestParams.categoryCode
            || selectedCategoryRequestParams.categoryPrimaryLabel
            || selectedCategoryRequestParams.categorySubLabel
            || selectedCategoryRequestParams.categoryThirdLabel
            ? current
            : payload.categoryCounts
        ));
        if (payload.tagDictionary?.tags) {
          setCategoryOptions(payload.tagDictionary.tags.filter((tag) => tag.status === "active"));
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
    dateFilter.dateFrom,
    dateFilter.dateTo,
    paginationModel.page,
    paginationModel.pageSize,
    refreshToken,
    searchKeyword,
    selectedAccountKey,
    selectedCategoryRequestParams.categoryCode,
    selectedCategoryRequestParams.categoryPrimaryLabel,
    selectedCategoryRequestParams.categorySubLabel,
    selectedCategoryRequestParams.categoryThirdLabel,
  ]);

  useEffect(() => {
    if (!selectedCategoryFilterStillExists(selectedCategoryFilter, categoryOptions)) {
      setSelectedCategoryFilter(ALL_CATEGORY_FILTER);
    }
  }, [categoryOptions, selectedCategoryFilter]);

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
    if (!readModelNeedsRefresh || loading || rowLoading || accountRequestPending || transactionRequestPending) {
      return undefined;
    }
    const retryId = window.setTimeout(() => {
      setRefreshToken((current) => current + 1);
    }, BANK_DETAIL_READ_MODEL_REFRESH_RETRY_MS);
    return () => window.clearTimeout(retryId);
  }, [accountRequestPending, loading, readModelNeedsRefresh, refreshToken, rowLoading, transactionRequestPending]);

  useEffect(() => {
    const handleWorkbenchRelationUpdated = (event: Event) => {
      const affectedMonths = eventAffectedMonths(event);
      if (!affectedMonthsHitDateFilter(affectedMonths, dateFilter)) {
        return;
      }
      setRefreshToken((current) => current + 1);
    };
    return subscribeFinanceDomainEvent(
      FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated,
      handleWorkbenchRelationUpdated,
    );
  }, [dateFilter]);

  useEffect(() => {
    const handleTagUpdate = (event: Event) => {
      const version = eventTagVersion(event);
      if (version !== null) {
        tagVersionRef.current = version;
        persistTagVersion(version);
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
    setCategoryCounts((current) => ({
      ...current,
      uncategorized: Math.max(0, Number(current.uncategorized ?? 0) - 1),
      [choice.categoryCode]: Number(current[choice.categoryCode] ?? 0) + 1,
    }));
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

  const handlePresetChange = (_event: MouseEvent<HTMLElement>, preset: BankDateFilter["preset"] | null) => {
    if (preset) {
      applyPreset(preset);
    }
  };

  const openDateFilterPopover = (event: MouseEvent<HTMLElement>) => {
    setDateFilterAnchorEl(event.currentTarget);
  };

  const closeDateFilterPopover = () => {
    setDateFilterAnchorEl(null);
  };

  const openExportMenu = (event: MouseEvent<HTMLElement>) => {
    setExportMenuAnchorEl(event.currentTarget);
  };

  const closeExportMenu = () => {
    setExportMenuAnchorEl(null);
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
    <Box className="bank-details-page" data-testid="bank-details-page">
      <Stack className="bank-details-workbench" spacing={1}>
        {error ? <StatePanel tone="error">{error}</StatePanel> : null}
        {loading ? <StatePanel tone="loading" compact>正在加载银行明细。</StatePanel> : null}
        {rulesFeedback ? <StatePanel tone="success" compact>{rulesFeedback}</StatePanel> : null}
        {!loading && !readModelNeedsRefresh && accountsData.accounts.length === 0 ? (
          <StatePanel tone="empty">暂无银行流水，请先在银行流水导入页面导入。</StatePanel>
        ) : null}

        <Box className="bank-details-layout">
          <Paper component="aside" className="bank-account-tree" elevation={0}>
            <Stack className="bank-account-summary" spacing={0.75}>
              <Typography color="text.secondary" variant="caption">总余额</Typography>
              <Typography className="bank-balance-value bank-total-balance" component="strong" variant="h6" fontWeight={850}>
                {displayBalance(accountsData.totalBalance)}
              </Typography>
              <Stack direction="row" flexWrap="wrap" gap={0.75}>
                <Chip className="bank-account-total-chip" label={`${accountsData.accounts.length} 个账户`} size="small" variant="outlined" />
                {accountsData.missingBalanceAccountCount > 0 ? (
                  <Chip label={`${accountsData.missingBalanceAccountCount} 个无余额`} size="small" color="warning" variant="outlined" />
                ) : null}
              </Stack>
            </Stack>
            <List aria-label="银行账户" dense disablePadding>
              <ListItem disablePadding>
                <ListItemButton
                  aria-current={isAllAccountsSelected ? "true" : undefined}
                  aria-label={`全部流水 ${totalTransactionCount} 条`}
                  className={`bank-account-node bank-account-all-node${isAllAccountsSelected ? " active" : ""}`}
                  component="button"
                  onClick={() => handleAccountSelect(ALL_ACCOUNTS_KEY)}
                >
                  <ListItemText
                    disableTypography
                    primary={(
                      <Box className="bank-account-title-row">
                        <Box className="bank-account-identity">
                          <Typography className="bank-account-name" component="span">全部</Typography>
                        </Box>
                        <Chip className="bank-account-count-chip bank-account-title-count" label={`${totalTransactionCount} 条`} size="small" variant="outlined" />
                      </Box>
                    )}
                    secondary={(
                      <Typography className="bank-account-inline-balance bank-account-secondary-balance bank-balance-value" component="span">
                        {displayBalance(accountsData.totalBalance)}
                      </Typography>
                    )}
                  />
                </ListItemButton>
              </ListItem>
              {accountsData.accounts.length > 0 ? (
                <Divider className="bank-account-divider" component="li" aria-hidden="true" />
              ) : null}
              {accountsData.accounts.map((account, index) => {
                const selected = account.accountKey === selectedAccountKey;
                const showDivider = index < accountsData.accounts.length - 1;
                return (
                  <Fragment key={account.accountKey}>
                    <ListItem disablePadding>
                      <ListItemButton
                        aria-current={selected ? "true" : undefined}
                        aria-label={`${account.displayName} 余额 ${displayBalance(account.latestBalance)} ${account.transactionCount} 条`}
                        className={`bank-account-node${selected ? " active" : ""}`}
                        component="button"
                        onClick={() => handleAccountSelect(account.accountKey)}
                      >
                        <ListItemText
                          disableTypography
                          primary={(
                            <Box className="bank-account-title-row">
                              <Box className="bank-account-identity">
                                <Typography className="bank-account-name" component="span">{account.bankName}</Typography>
                                <Typography className="bank-account-last4" component="span">{account.accountLast4}</Typography>
                              </Box>
                              <Chip className="bank-account-count-chip bank-account-title-count" label={`${account.transactionCount} 条`} size="small" variant="outlined" />
                            </Box>
                          )}
                          secondary={(
                            <Stack className="bank-account-metric-row" direction="row" alignItems="center" spacing={0.75} minWidth={0}>
                              {account.hasBalance ? (
                                <Typography className="bank-account-inline-balance bank-account-secondary-balance bank-balance-value" component="span">
                                  {displayBalance(account.latestBalance)}
                                </Typography>
                              ) : null}
                              {!account.hasBalance ? (
                                <Chip className="bank-account-empty-chip" label="余额为空" size="small" variant="outlined" />
                              ) : null}
                            </Stack>
                          )}
                        />
                      </ListItemButton>
                    </ListItem>
                    {showDivider ? <Divider className="bank-account-divider" component="li" aria-hidden="true" /> : null}
                  </Fragment>
                );
              })}
            </List>
          </Paper>

          <Paper component="section" className="bank-transaction-panel" elevation={0}>
            <Stack className="bank-transaction-toolbar" spacing={0.75}>
              <Stack className="bank-transaction-header" direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1}>
                <Stack className="bank-transaction-title-row" direction="row" alignItems="center" spacing={1}>
                  <Typography className="bank-transaction-title" component="h2" variant="subtitle1" fontWeight={850} noWrap>
                    {currentViewTitle}
                  </Typography>
                </Stack>

                <Stack className="bank-header-controls" direction="row" spacing={0.75} alignItems="center">
                  <Button
                    startIcon={<RuleIcon />}
                    size="small"
                    variant="outlined"
                    onClick={() => setRulesDrawerOpen(true)}
                  >
                    自动标签规则
                  </Button>
                  <Stack className="bank-date-toolbar" spacing={0.5} alignItems="flex-end">
                    <ToggleButtonGroup
                      aria-label="日期快捷筛选"
                      className="bank-date-presets"
                      exclusive
                      size="small"
                      value={dateFilter.preset === "custom" || dateFilter.preset === "month" ? null : dateFilter.preset}
                      onChange={handlePresetChange}
                    >
                      <ToggleButton value="current_month">本月</ToggleButton>
                      <ToggleButton value="previous_month">上月</ToggleButton>
                      <ToggleButton value="last_7_days">近7天</ToggleButton>
                      <ToggleButton value="last_30_days">近30天</ToggleButton>
                      <ToggleButton value="current_year">今年</ToggleButton>
                    </ToggleButtonGroup>
                    <Button
                      aria-describedby={dateFilterOpen ? "bank-date-filter-popover" : undefined}
                      className="bank-date-range-button"
                      size="small"
                      variant="outlined"
                      onClick={openDateFilterPopover}
                    >
                      {dateFilter.dateFrom} - {dateFilter.dateTo}
                    </Button>
                  </Stack>
                </Stack>
              </Stack>
            </Stack>

            <Divider />

            <Box className="bank-transaction-grid bank-transaction-grid-readable">
              <BankDetailsTableToolbar
                effectiveCategoryCounts={effectiveCategoryCounts}
                visibleCategorySummary={visibleCategorySummary}
                rowCount={rowCount}
                selectedCategoryFilter={selectedCategoryFilter}
                onCategoryFilterChange={handleCategoryFilterChange}
                searchKeyword={searchInput}
                onSearchKeywordChange={handleSearchKeywordChange}
                exportMenuAnchorEl={exportMenuAnchorEl}
                exportFeedback={exportFeedback}
                isExporting={isExporting}
                canExportCurrentAccount={!isAllAccountsSelected}
                onOpenExportMenu={openExportMenu}
                onCloseExportMenu={closeExportMenu}
                onExport={handleExport}
              />
              <TableContainer className="bank-transaction-table-container">
                <Table aria-label="交易流水" className="bank-transaction-table" size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell className="bank-col-counterparty">对方户名</TableCell>
                      <TableCell align="center" className="bank-col-type">类型</TableCell>
                      <TableCell align="right" className="bank-col-amount">金额</TableCell>
                      <TableCell align="right" className="bank-col-balance">余额</TableCell>
                      <TableCell className="bank-col-purpose">用途/交易用途</TableCell>
                      <TableCell className="bank-col-summary">摘要</TableCell>
                      <TableCell className="bank-col-note">备注/附言/客户附言</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rowLoading ? (
                      <TableRow>
                        <TableCell colSpan={7}>
                          <Stack alignItems="center" justifyContent="center" sx={{ minHeight: 220 }}>
                            <Typography color="text.secondary">正在加载流水。</Typography>
                          </Stack>
                        </TableCell>
                      </TableRow>
                    ) : null}
                    {!rowLoading && rows.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7}>
                          <EmptyTransactionOverlay />
                        </TableCell>
                      </TableRow>
                    ) : null}
                    {!rowLoading && rows.map((row, index) => (
                      <TableRow
                        className={index % 2 === 0 ? "bank-grid-row-even" : "bank-grid-row-odd"}
                        hover
                        key={row.id}
                      >
                        <TableCell className="bank-col-counterparty">
                          <Stack className="bank-counterparty-cell" justifyContent="center" spacing={0.5} sx={{ minWidth: 0, width: "100%" }}>
                            <Typography
                              className={`bank-counterparty-name ${counterpartyNameDensity(row.counterpartyName)}`}
                              component="span"
                              variant="body2"
                              fontWeight={750}
                            >
                              {row.counterpartyName}
                            </Typography>
                            <Stack className="bank-relation-time-row" direction="row" spacing={0.5} sx={{ minWidth: 0, maxWidth: "100%" }}>
                              <Chip className="bank-trade-time-chip bank-trade-time-chip-full bank-chip-auto-size" label={row.tradeTime} size="small" variant="outlined" />
                            </Stack>
                            <Stack className="bank-relation-chip-row" direction="row" spacing={0.5} sx={{ minWidth: 0, maxWidth: "100%" }}>
                              {row.relationTags.map((tag) => (
                                <Chip
                                  key={`${row.id}-${tag}`}
                                  className={`bank-relation-tag bank-relation-tag-${relationTagTone(tag)} bank-chip-auto-size`}
                                  label={tag}
                                  size="small"
                                  variant="outlined"
                                />
                              ))}
                            </Stack>
                          </Stack>
                        </TableCell>
                        <TableCell align="center" className="bank-col-type">
                          <TypeCell
                            row={row}
                            autoTagRules={activeAutoTagRules}
                            confirming={categoryMutationId === row.id}
                            onConfirm={handleConfirmCategory}
                            onAssign={handleAssignCategory}
                            onRevoke={handleRevokeCategoryConfirmation}
                            onClearAssignment={handleClearCategoryAssignment}
                          />
                        </TableCell>
                        <TableCell align="right" className="bank-col-amount">
                          <Stack className="bank-amount-cell" alignItems="stretch" justifyContent="center" spacing={0.5} sx={{ width: "100%" }}>
                            <Stack className="bank-amount-line" direction="row" alignItems="center" justifyContent="flex-end" spacing={0.75}>
                              <Chip
                                className={`direction-tag bank-direction-tag-centered bank-chip-auto-size ${row.direction}`}
                                label={row.directionLabel}
                                size="small"
                                variant="filled"
                              />
                              <Typography component="span" variant="body2" fontWeight={800} sx={{ fontVariantNumeric: "tabular-nums" }}>
                                {formatMoney(row.amount)}
                              </Typography>
                            </Stack>
                            <Chip className="bank-source-chip bank-chip-auto-size" label={`${row.bankName} ${row.accountLast4}`} size="small" variant="outlined" />
                          </Stack>
                        </TableCell>
                        <TableCell align="right" className="bank-col-balance">
                          <Typography component="span" variant="body2" sx={{ fontVariantNumeric: "tabular-nums" }}>
                            {formatMoney(row.balance)}
                          </Typography>
                        </TableCell>
                        <TableCell className="bank-col-purpose"><BankTextCell value={row.purposeText} /></TableCell>
                        <TableCell className="bank-col-summary"><BankTextCell value={row.summaryText} /></TableCell>
                        <TableCell className="bank-col-note"><BankTextCell value={row.noteText} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              <TablePagination
                className="bank-transaction-pagination"
                component="div"
                count={rowCount}
                labelDisplayedRows={({ from, to, count }) => `${from}-${to} / ${count === -1 ? `超过 ${to}` : count}`}
                labelRowsPerPage="每页行数"
                onPageChange={(_event, page) => setPaginationModel((current) => ({ ...current, page }))}
                onRowsPerPageChange={(event) => {
                  setPaginationModel({ page: 0, pageSize: Number(event.target.value) });
                }}
                page={paginationModel.page}
                rowsPerPage={paginationModel.pageSize}
                rowsPerPageOptions={[25, 50, 100]}
              />
            </Box>
          </Paper>
        </Box>
      </Stack>
      <AutoTagRulesDrawer
        open={rulesDrawerOpen}
        onClose={() => setRulesDrawerOpen(false)}
        onSaved={handleAutoTagRulesSaved}
        refreshScope={{ dateFrom: dateFilter.dateFrom, dateTo: dateFilter.dateTo }}
        refreshStatus={rulesRefreshStatus}
      />
      <Popover
        id="bank-date-filter-popover"
        open={dateFilterOpen}
        anchorEl={dateFilterAnchorEl}
        onClose={closeDateFilterPopover}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { className: "bank-date-filter-popover" } }}
      >
        <Stack className="bank-date-filter" spacing={1.25}>
          <TextField
            label="年月"
            type="month"
            size="small"
            value={monthValue}
            onChange={(event) => handleMonthChange(event.target.value)}
            InputLabelProps={{ shrink: true }}
            inputProps={{ "aria-label": "年月筛选" }}
          />
          <DatePicker
            enableAccessibleFieldDOMStructure={false}
            label="开始"
            format="YYYY-MM-DD"
            value={dateValue(dateFilter.dateFrom)}
            onChange={(value) => {
              if (!value) {
                handleCustomDateChange("dateFrom", "");
                return;
              }
              const nextValue = formatPickerDate(value);
              if (nextValue) {
                handleCustomDateChange("dateFrom", nextValue);
              }
            }}
            slotProps={{
              textField: {
                size: "small",
                inputProps: {
                  "aria-label": "开始日期",
                  onInput: (event: FormEvent<HTMLInputElement>) => {
                    if (event.currentTarget instanceof HTMLInputElement) {
                      handleCustomDateTextChange("dateFrom", event.currentTarget.value);
                    }
                  },
                },
                onBlur: (event: FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => handleCustomDateTextChange("dateFrom", event.target.value),
              },
            }}
          />
          <DatePicker
            enableAccessibleFieldDOMStructure={false}
            label="结束"
            format="YYYY-MM-DD"
            value={dateValue(dateFilter.dateTo)}
            onChange={(value) => {
              if (!value) {
                handleCustomDateChange("dateTo", "");
                return;
              }
              const nextValue = formatPickerDate(value);
              if (nextValue) {
                handleCustomDateChange("dateTo", nextValue);
              }
            }}
            slotProps={{
              textField: {
                size: "small",
                inputProps: {
                  "aria-label": "结束日期",
                  onInput: (event: FormEvent<HTMLInputElement>) => {
                    if (event.currentTarget instanceof HTMLInputElement) {
                      handleCustomDateTextChange("dateTo", event.currentTarget.value);
                    }
                  },
                },
                onBlur: (event: FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => handleCustomDateTextChange("dateTo", event.target.value),
              },
            }}
          />
        </Stack>
      </Popover>
    </Box>
  );
}
