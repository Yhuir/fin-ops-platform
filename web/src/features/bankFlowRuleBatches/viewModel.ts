import { operationBarrierTargetsFromMonths } from "../operationBarrier/api";
import type { OperationBarrierTarget } from "../operationBarrier/api";
import type {
  BankFlowRuleBatch,
  BankFlowRuleBatchDetailRow,
  BankFlowRuleBatchSummaryCategory,
  BankFlowRuleBatchStatusBucket,
  BankFlowRuleBatchTagDefinition,
  BankFlowRuleBatchTagSelection,
} from "./types";

export const SELF_SUB_LABEL = "主标签本身";
export const BANK_FLOW_RULE_BATCH_READ_MODEL_KEY = "bank_flow_rule_batch";

export type BankFlowRuleTagNode = {
  code: string;
  label: string;
  primaryLabel: string;
  subLabel: string;
};

export type BankFlowRuleDraftRequirements = Record<string, { requiresOa: boolean; requiresInvoice: boolean }>;

export type TagDrawerRow = {
  tag: BankFlowRuleBatchTagDefinition;
  direction: string;
  directionKey: string;
  directionRowSpan: number;
  isDirectionStart: boolean;
  primaryLabel: string;
  primaryKey: string;
  primaryRowSpan: number;
  primaryGroupIndex: number;
  isPrimaryStart: boolean;
  subLabel: string;
};

export function cx(...values: Array<string | false | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function currentMonth() {
  const now = new Date();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}

export function isAbortLikeError(caught: unknown) {
  if (caught instanceof DOMException && caught.name === "AbortError") {
    return true;
  }
  return caught instanceof Error && (caught.name === "AbortError" || /aborted|abort/i.test(caught.message));
}

export function formatMoney(value: string | number | null | undefined) {
  const numeric = Number(String(value ?? "0").replace(/,/g, "").trim());
  if (!Number.isFinite(numeric)) {
    return String(value ?? "0.00");
  }
  return numeric.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function accountLabel(batch: BankFlowRuleBatch) {
  const account = batch.accountLast4 ? `${batch.bankName || "多账户"}${batch.accountLast4}` : batch.bankName || "多账户";
  return account || "多账户";
}

export function pageRange(page: number, pageSize: number, total: number) {
  if (total <= 0) {
    return "0-0 / 0";
  }
  const start = (page - 1) * pageSize + 1;
  if (start > total) {
    return `0-0 / ${total}`;
  }
  const end = Math.min(total, page * pageSize);
  return `${start}-${end} / ${total}`;
}

export function bankTagLabel(row: { bankName?: string; accountLast4?: string; accountKey?: string }) {
  if (row.accountLast4) {
    return `${row.bankName || "银行"}${row.accountLast4}`;
  }
  return row.bankName || row.accountKey || "-";
}

export function directionTagLabel(row: { direction?: string; directionLabel?: string }) {
  return row.directionLabel || (row.direction === "income" ? "收" : row.direction === "expense" ? "支" : "-");
}

export function batchBlockingReason(_batch: BankFlowRuleBatch) {
  return "";
}

export function mutationEventDetail(result: {
  affectedMonths?: string[];
  affectedScopeKeys?: string[];
  operationBarrierTargets?: OperationBarrierTarget[];
}) {
  return {
    affectedMonths: result.affectedMonths ?? [],
    affectedScopeKeys: result.affectedScopeKeys ?? [],
    operationBarrierTargets: result.operationBarrierTargets ?? [],
  };
}

export function mutationBarrierTargets(
  result: {
    affectedMonths?: string[];
    freshnessTargets?: OperationBarrierTarget[];
    operationBarrierTargets?: OperationBarrierTarget[];
  },
  fallbackScopeKey: string,
) {
  const selfTargets = [
    ...(result.operationBarrierTargets ?? []),
    ...(result.freshnessTargets ?? []),
  ].filter((target) => target.readModelKey === BANK_FLOW_RULE_BATCH_READ_MODEL_KEY);
  return selfTargets.length > 0
    ? dedupeOperationTargets(selfTargets)
    : operationBarrierTargetsFromMonths(BANK_FLOW_RULE_BATCH_READ_MODEL_KEY, result.affectedMonths ?? [], fallbackScopeKey);
}

function dedupeOperationTargets(targets: OperationBarrierTarget[]) {
  const seen = new Set<string>();
  return targets.filter((target) => {
    const key = `${target.readModelKey}\u0000${target.scopeKey}\u0000${target.scopeType ?? ""}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export function cleanText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

export function tagPrimaryLabel(tag: BankFlowRuleBatchTagDefinition | BankFlowRuleBatchSummaryCategory | BankFlowRuleBatch) {
  if ("outputPrimaryLabel" in tag) {
    return cleanText(tag.outputPrimaryLabel) || cleanText(tag.label) || cleanText(tag.code);
  }
  if ("primaryLabel" in tag) {
    return cleanText(tag.primaryLabel) || cleanText(tag.label) || cleanText(tag.code);
  }
  if ("batchType" in tag) {
    return cleanText(tag.categoryPrimaryLabel) || cleanText(tag.batchLabel) || cleanText(tag.batchType);
  }
  return cleanText(tag.label) || cleanText(tag.code);
}

export function tagSubLabel(tag: BankFlowRuleBatchTagDefinition | BankFlowRuleBatchSummaryCategory | BankFlowRuleBatch) {
  if ("outputSubLabel" in tag) {
    return cleanText(tag.outputSubLabel);
  }
  if ("subLabel" in tag) {
    return cleanText(tag.subLabel);
  }
  return "batchType" in tag ? cleanText(tag.categorySubLabel) : "";
}

function normalizeDrawerDirection(value: string) {
  const normalized = cleanText(value).toLowerCase();
  if (normalized === "income" || normalized === "inflow" || normalized === "credit" || value === "收入" || value === "收") {
    return "income";
  }
  if (normalized === "expense" || normalized === "outflow" || normalized === "debit" || value === "支出" || value === "支") {
    return "expense";
  }
  return "any";
}

function directionLabel(value: string) {
  const normalized = normalizeDrawerDirection(value);
  if (normalized === "income") {
    return "收入";
  }
  if (normalized === "expense") {
    return "支出";
  }
  return "全部";
}

function drawerDirectionSortKey(value: string) {
  if (value === "expense") {
    return 0;
  }
  if (value === "income") {
    return 1;
  }
  if (value === "any") {
    return 2;
  }
  return 3;
}

export function tagDrawerGroupColor(index: number) {
  return `hsl(${(198 + index * 43) % 360} 56% 94%)`;
}

export function buildTagDrawerRows(tags: BankFlowRuleBatchTagDefinition[]): TagDrawerRow[] {
  const baseRows = tags.map((tag, index) => {
    const directionKey = normalizeDrawerDirection(tag.direction);
    const primaryLabel = tagPrimaryLabel(tag) || tag.label || tag.code;
    return {
      tag,
      index,
      direction: directionLabel(directionKey),
      directionKey,
      primaryLabel,
      primaryKey: `${directionKey}\u0000${primaryLabel}`,
      subLabel: tagSubLabel(tag) || SELF_SUB_LABEL,
    };
  });
  const firstPrimaryIndexByKey = new Map<string, number>();
  baseRows.forEach((row) => {
    if (!firstPrimaryIndexByKey.has(row.primaryKey)) {
      firstPrimaryIndexByKey.set(row.primaryKey, row.index);
    }
  });

  const primaryColorIndexByLabel = new Map<string, number>();
  const sortedRows = [...baseRows].sort((left, right) => {
    const directionDelta = drawerDirectionSortKey(left.directionKey) - drawerDirectionSortKey(right.directionKey);
    if (directionDelta !== 0) {
      return directionDelta;
    }
    const primaryDelta = (firstPrimaryIndexByKey.get(left.primaryKey) ?? left.index)
      - (firstPrimaryIndexByKey.get(right.primaryKey) ?? right.index);
    return primaryDelta !== 0 ? primaryDelta : left.index - right.index;
  });
  const rows: TagDrawerRow[] = sortedRows.map((row) => {
    if (!primaryColorIndexByLabel.has(row.primaryLabel)) {
      primaryColorIndexByLabel.set(row.primaryLabel, primaryColorIndexByLabel.size);
    }
    return {
      tag: row.tag,
      direction: row.direction,
      directionKey: row.directionKey,
      directionRowSpan: 0,
      isDirectionStart: false,
      primaryLabel: row.primaryLabel,
      primaryKey: row.primaryKey,
      primaryRowSpan: 0,
      primaryGroupIndex: primaryColorIndexByLabel.get(row.primaryLabel) ?? 0,
      isPrimaryStart: false,
      subLabel: row.subLabel,
    };
  });

  rows.forEach((row, index) => {
    if (index === 0 || rows[index - 1].directionKey !== row.directionKey) {
      row.isDirectionStart = true;
      row.directionRowSpan = rows.slice(index).findIndex((candidate) => candidate.directionKey !== row.directionKey);
      if (row.directionRowSpan === -1) {
        row.directionRowSpan = rows.length - index;
      }
    }
    if (index === 0 || rows[index - 1].primaryKey !== row.primaryKey) {
      row.isPrimaryStart = true;
      row.primaryRowSpan = rows.slice(index).findIndex((candidate) => candidate.primaryKey !== row.primaryKey);
      if (row.primaryRowSpan === -1) {
        row.primaryRowSpan = rows.length - index;
      }
    }
  });
  return rows;
}

export function requirementsFromSelection(selection: BankFlowRuleBatchTagSelection): BankFlowRuleDraftRequirements {
  return Object.fromEntries(selection.rules.map((rule) => [
    rule.tagCode,
    { requiresOa: rule.requiresOa, requiresInvoice: rule.requiresInvoice },
  ]));
}

export function requirementFor(requirements: BankFlowRuleDraftRequirements, tagCode: string) {
  return requirements[tagCode] ?? { requiresOa: true, requiresInvoice: true };
}

export function formatCountMeta(batchCount: number, rowCount: number) {
  if (batchCount === 0 && rowCount === 0) {
    return "暂无";
  }
  return `${batchCount}批 · ${rowCount}条`;
}

export function isUnsubmittedEligible(
  requirements: BankFlowRuleDraftRequirements,
  tagCode: string,
) {
  const requirement = requirementFor(requirements, tagCode);
  return !requirement.requiresOa && !requirement.requiresInvoice;
}

export function categoryCountForBucket(
  category: BankFlowRuleBatchSummaryCategory,
  bucket: BankFlowRuleBatchStatusBucket,
) {
  if (bucket === "unsubmitted") return category.draft;
  if (bucket === "submitted") return category.submitted;
  if (bucket === "withdrawn") return category.withdrawn;
  return category.total;
}

export function categoryRowCountForBucket(
  category: BankFlowRuleBatchSummaryCategory,
  bucket: BankFlowRuleBatchStatusBucket,
) {
  if (bucket === "unsubmitted") return category.draftRowCount;
  if (bucket === "submitted") return category.submittedRowCount;
  if (bucket === "withdrawn") return category.withdrawnRowCount;
  return category.totalRowCount;
}

export function relationContextLabels(row: BankFlowRuleBatchDetailRow) {
  if (row.relationStatus !== "linked" && row.relationCaseIds.length === 0) {
    return [];
  }
  const relationLabel = row.relationCaseIds[0] ? `关联 ${row.relationCaseIds[0]}` : "已有未撤回关联";
  return [relationLabel, `OA ${row.linkedOaCount}`, `发票 ${row.linkedInvoiceCount}`];
}

export function bankDetailTagLabels(row: BankFlowRuleBatchDetailRow) {
  const labelPath = row.categoryLabelPath.map((label) => label.trim()).filter(Boolean);
  if (labelPath.length > 0) {
    return Array.from(new Set(labelPath));
  }
  const fallbackLabels = [
    row.categoryPrimaryLabel,
    row.categorySubLabel,
    row.categoryLabel,
    row.categoryCode,
  ].map((label) => label.trim()).filter(Boolean);
  return Array.from(new Set(fallbackLabels));
}
