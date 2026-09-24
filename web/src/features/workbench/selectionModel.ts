import type {
  WorkbenchAmountDirection,
  WorkbenchRecordIdentity,
  WorkbenchRelationGroup,
  WorkbenchRecord,
  WorkbenchRecordType,
} from "./types";
import { formatMoney } from "../money";

const paneIds: WorkbenchRecordType[] = ["oa", "bank", "invoice"];

type WorkbenchSelectionAmountCents = Record<WorkbenchRecordType, number | undefined>;

export type WorkbenchSelectionSummary = {
  explicitTotal: number;
  total: number;
  oa: number;
  bank: number;
  invoice: number;
  amounts: Record<WorkbenchRecordType, string>;
};

export type WorkbenchSelectionContext = {
  explicitRows: WorkbenchRecord[];
  includedRows: WorkbenchRecord[];
  includedRowIdentities: WorkbenchRecordIdentity[];
  includedRowIdentityKeys: string[];
  selectedRelationGroupIds: string[];
  relatedRowIdentityKeySet: Set<string>;
  summary: WorkbenchSelectionSummary;
};

export function workbenchRowIdentityKey(
  row: Pick<WorkbenchRecord, "id" | "recordType">,
) {
  return `${row.recordType}\u001f${row.id}`;
}

export function buildWorkbenchSelectionContext({
  explicitRows,
  sourceGroups,
  zoneId,
}: {
  explicitRows: WorkbenchRecord[];
  sourceGroups: WorkbenchRelationGroup[];
  zoneId: "paired" | "unpaired";
}): WorkbenchSelectionContext {
  const explicitRowsByIdentity = new Map<string, WorkbenchRecord>();
  explicitRows.forEach((row) => {
    const identityKey = workbenchRowIdentityKey(row);
    if (!explicitRowsByIdentity.has(identityKey)) {
      explicitRowsByIdentity.set(identityKey, row);
    }
  });
  if (explicitRowsByIdentity.size === 0) {
    return {
      explicitRows: [],
      includedRows: [],
      includedRowIdentities: [],
      includedRowIdentityKeys: [],
      selectedRelationGroupIds: [],
      relatedRowIdentityKeySet: new Set(),
      summary: summarizeWorkbenchRows([], 0),
    };
  }

  const explicitRowIdentityKeys = Array.from(explicitRowsByIdentity.keys());
  const explicitRowIdentityKeySet = new Set(explicitRowIdentityKeys);
  const relationGroupBySelectableRowIdentity = new Map<string, WorkbenchRelationGroup>();
  const unresolvedExplicitIdentityKeys = new Set(explicitRowIdentityKeys);
  for (const group of sourceGroups) {
    for (const row of flattenWorkbenchGroupSelectionRows(group)) {
      const identityKey = workbenchRowIdentityKey(row);
      if (!unresolvedExplicitIdentityKeys.has(identityKey)) {
        continue;
      }
      explicitRowsByIdentity.set(identityKey, row);
      unresolvedExplicitIdentityKeys.delete(identityKey);
      if (group.rawGroupType === "relation") {
        relationGroupBySelectableRowIdentity.set(identityKey, group);
      }
    }
    if (unresolvedExplicitIdentityKeys.size === 0) {
      break;
    }
  }
  const includedRowsByIdentity = new Map<string, WorkbenchRecord>();
  const includedIdentitiesByKey = new Map<string, WorkbenchRecordIdentity>();
  const selectedRelationGroups = new Map<string, WorkbenchRelationGroup>();
  const independentRows: WorkbenchRecord[] = [];

  explicitRowsByIdentity.forEach((row, identityKey) => {
    const relationGroup = relationGroupBySelectableRowIdentity.get(identityKey);
    if (!relationGroup) {
      includedRowsByIdentity.set(identityKey, row);
      includedIdentitiesByKey.set(identityKey, { id: row.id, recordType: row.recordType });
      independentRows.push(row);
      return;
    }
    selectedRelationGroups.set(relationGroup.id, relationGroup);
  });

  const resolvedFormalSelections: Array<{
    group: WorkbenchRelationGroup;
    identities: WorkbenchRecordIdentity[];
    rows: WorkbenchRecord[];
  }> = [];
  selectedRelationGroups.forEach((group) => {
    const selection = resolveFormalRelationSelection(group);
    if (!selection) {
      return;
    }
    selection.identities.forEach((identity) => {
      includedIdentitiesByKey.set(workbenchRowIdentityKey(identity), identity);
    });
    selection.rows.forEach((relationRow) => {
      includedRowsByIdentity.set(workbenchRowIdentityKey(relationRow), relationRow);
    });
    resolvedFormalSelections.push({ group, ...selection });
  });

  const includedRows = Array.from(includedRowsByIdentity.values());
  const includedRowIdentities = Array.from(includedIdentitiesByKey.values());
  const includedRowIdentityKeys = Array.from(includedIdentitiesByKey.keys());
  const selectionDirection = resolveWorkbenchSelectionAmountDirection(
    includedRows,
    resolvedFormalSelections.map(({ group }) => group),
  );
  const amountCents = sumIndependentWorkbenchSelectionAmounts(
    independentRows,
    selectionDirection,
  );
  resolvedFormalSelections.forEach(({ group, identities, rows }) => {
    mergeWorkbenchSelectionAmountCents(
      amountCents,
      resolveFormalRelationAmountCents(group, identities, rows, selectionDirection),
    );
  });
  const relatedRowIdentityKeySet = new Set(
    includedRowIdentityKeys
      .filter((identityKey) => !explicitRowIdentityKeySet.has(identityKey)),
  );

  return {
    explicitRows: explicitRowIdentityKeys
      .map((identityKey) => explicitRowsByIdentity.get(identityKey))
      .filter((row): row is WorkbenchRecord => Boolean(row)),
    includedRows,
    includedRowIdentities,
    includedRowIdentityKeys,
    selectedRelationGroupIds: Array.from(selectedRelationGroups.keys()),
    relatedRowIdentityKeySet,
    summary: summarizeWorkbenchIdentities(
      includedRowIdentities,
      amountCents,
      explicitRowIdentityKeySet.size,
    ),
  };
}

export function summarizeWorkbenchRows(rows: WorkbenchRecord[], explicitTotal = rows.length): WorkbenchSelectionSummary {
  const byType = {
    oa: rows.filter((row) => row.recordType === "oa"),
    bank: rows.filter((row) => row.recordType === "bank"),
    invoice: rows.filter((row) => row.recordType === "invoice"),
  };

  return {
    explicitTotal,
    total: rows.length,
    oa: byType.oa.length,
    bank: byType.bank.length,
    invoice: byType.invoice.length,
    amounts: {
      oa: formatWorkbenchAmountCents(sumWorkbenchAmountCents(byType.oa)),
      bank: formatWorkbenchAmountCents(sumWorkbenchAmountCents(byType.bank)),
      invoice: formatWorkbenchAmountCents(sumWorkbenchAmountCents(byType.invoice)),
    },
  };
}

export function parseWorkbenchAmountCents(value: string): number {
  const normalized = value.replace(/,/g, "").trim();
  if (!normalized || normalized === "--" || normalized === "—") {
    return 0;
  }
  const amount = Number(normalized);
  if (!Number.isFinite(amount)) {
    return 0;
  }
  return Math.round(amount * 100);
}

export function formatWorkbenchAmountCents(cents: number): string {
  return formatMoney((cents / 100).toFixed(2));
}

function sumWorkbenchAmountCents(rows: WorkbenchRecord[]) {
  return rows.reduce((total, row) => total + workbenchComparableAmountCents(row), 0);
}

function sumIndependentWorkbenchSelectionAmounts(
  rows: WorkbenchRecord[],
  direction: WorkbenchAmountDirection | undefined,
): WorkbenchSelectionAmountCents {
  const oaRows = rows.filter((row) => row.recordType === "oa");
  const bankRows = rows.filter((row) => row.recordType === "bank");
  const invoiceRows = rows.filter((row) => row.recordType === "invoice");
  return {
    oa: sumWorkbenchAmountCents(oaRows),
    bank: sumWorkbenchBankComparisonAmountCents(bankRows, direction),
    invoice: sumWorkbenchAmountCents(invoiceRows),
  };
}

function sumWorkbenchBankComparisonAmountCents(
  bankRows: WorkbenchRecord[],
  direction: WorkbenchAmountDirection | undefined,
): number | undefined {
  if (bankRows.length === 0) {
    return 0;
  }
  if (bankRows.some((row) => row.amountDirection === undefined)) {
    return undefined;
  }
  if (!direction) {
    return undefined;
  }
  let gross = 0;
  let contra = 0;
  bankRows.forEach((row) => {
    if (row.amountDirection === direction) {
      gross += workbenchComparableAmountCents(row);
    } else {
      contra += workbenchComparableAmountCents(row);
    }
  });
  return gross - contra;
}

function resolveWorkbenchSelectionAmountDirection(
  rows: WorkbenchRecord[],
  formalGroups: WorkbenchRelationGroup[],
): WorkbenchAmountDirection | undefined {
  const nonBankDirections = new Set(
    rows
      .filter((row) => row.recordType !== "bank")
      .map((row) => row.amountDirection)
      .filter((direction): direction is WorkbenchAmountDirection => direction !== undefined),
  );
  if (nonBankDirections.size === 1) {
    return nonBankDirections.values().next().value;
  }
  if (nonBankDirections.size > 1) {
    return undefined;
  }
  const formalDirections = new Set(
    formalGroups
      .map((group) => group.amountCheck?.direction)
      .filter((direction): direction is WorkbenchAmountDirection => (
        direction === "payment" || direction === "receipt"
      )),
  );
  if (formalDirections.size === 1) {
    return formalDirections.values().next().value;
  }
  if (formalDirections.size > 1) {
    return undefined;
  }
  const directions = new Set(
    rows
      .map((row) => row.amountDirection)
      .filter((direction): direction is WorkbenchAmountDirection => direction !== undefined),
  );
  return directions.size === 1 ? directions.values().next().value : undefined;
}

function mergeWorkbenchSelectionAmountCents(
  target: WorkbenchSelectionAmountCents,
  source: WorkbenchSelectionAmountCents,
) {
  paneIds.forEach((paneId) => {
    const targetValue = target[paneId];
    const sourceValue = source[paneId];
    target[paneId] = targetValue === undefined || sourceValue === undefined
      ? undefined
      : targetValue + sourceValue;
  });
}

export function workbenchComparableAmountCents(row: WorkbenchRecord): number {
  if (row.recordType === "invoice") {
    const grossAmount = row.tableValues.grossAmount?.trim();
    if (grossAmount && grossAmount !== "--" && grossAmount !== "—") {
      return parseWorkbenchAmountCents(grossAmount);
    }
  }
  return parseWorkbenchAmountCents(row.amount);
}

function flattenWorkbenchGroup(group: WorkbenchRelationGroup) {
  return paneIds.flatMap((paneId) => group.rows[paneId]);
}

function resolveFormalRelationSelection(group: WorkbenchRelationGroup): {
  identities: WorkbenchRecordIdentity[];
  rows: WorkbenchRecord[];
} | undefined {
  const identities = group.formalMemberIdentities;
  if (!Array.isArray(identities) || identities.length === 0) {
    return undefined;
  }
  const rowsByIdentity = new Map(
    flattenWorkbenchGroupSelectionRows(group).map((row) => [workbenchRowIdentityKey(row), row]),
  );
  const resolvedRows: WorkbenchRecord[] = [];
  const seen = new Set<string>();
  for (const identity of identities) {
    const identityKey = workbenchRowIdentityKey(identity);
    if (seen.has(identityKey)) {
      return undefined;
    }
    const row = rowsByIdentity.get(identityKey);
    if (row) {
      resolvedRows.push(row);
    }
    seen.add(identityKey);
  }
  return { identities, rows: resolvedRows };
}

function resolveFormalRelationAmountCents(
  group: WorkbenchRelationGroup,
  identities: WorkbenchRecordIdentity[],
  rows: WorkbenchRecord[],
  selectionDirection: WorkbenchAmountDirection | undefined,
): WorkbenchSelectionAmountCents {
  const counts = countWorkbenchIdentitiesByType(identities);
  const amountValues: Partial<Record<WorkbenchRecordType, string>> = {
    oa: group.amountCheck?.oaTotal,
    bank: group.relationMode === "turnover_manual_closure"
      ? group.amountCheck?.bankTotal
      : group.amountCheck?.bankRelatedTotal,
    invoice: group.amountCheck?.invoiceTotal,
  };
  const resolved: WorkbenchSelectionAmountCents = { oa: 0, bank: 0, invoice: 0 };
  for (const paneId of paneIds) {
    if (counts[paneId] === 0) {
      continue;
    }
    const exactAmount = parseExactWorkbenchAmountCents(amountValues[paneId]);
    if (exactAmount !== undefined) {
      resolved[paneId] = exactAmount;
      continue;
    }
    resolved[paneId] = undefined;
  }
  if (counts.bank > 0 && group.amountCheck?.direction === "unknown") {
    const bankRows = rows.filter((row) => row.recordType === "bank");
    resolved.bank = bankRows.length === counts.bank
      ? sumWorkbenchBankComparisonAmountCents(bankRows, selectionDirection)
      : undefined;
  }
  return resolved;
}

function parseExactWorkbenchAmountCents(value: string | undefined) {
  if (typeof value !== "string") {
    return undefined;
  }
  const normalized = value.replace(/,/g, "").trim();
  if (!normalized || normalized === "--" || normalized === "—") {
    return undefined;
  }
  const amount = Number(normalized);
  return Number.isFinite(amount) ? Math.round(amount * 100) : undefined;
}

function countWorkbenchIdentitiesByType(identities: WorkbenchRecordIdentity[]) {
  return {
    oa: identities.filter((identity) => identity.recordType === "oa").length,
    bank: identities.filter((identity) => identity.recordType === "bank").length,
    invoice: identities.filter((identity) => identity.recordType === "invoice").length,
  };
}

function summarizeWorkbenchIdentities(
  identities: WorkbenchRecordIdentity[],
  amountCents: WorkbenchSelectionAmountCents,
  explicitTotal: number,
): WorkbenchSelectionSummary {
  const counts = countWorkbenchIdentitiesByType(identities);
  return {
    explicitTotal,
    total: identities.length,
    ...counts,
    amounts: {
      oa: formatWorkbenchSelectionAmountCents(amountCents.oa),
      bank: formatWorkbenchSelectionAmountCents(amountCents.bank),
      invoice: formatWorkbenchSelectionAmountCents(amountCents.invoice),
    },
  };
}

function formatWorkbenchSelectionAmountCents(cents: number | undefined) {
  return cents === undefined ? "--" : formatWorkbenchAmountCents(cents);
}

function flattenWorkbenchGroupSelectionRows(group: WorkbenchRelationGroup) {
  return [
    ...flattenWorkbenchGroup(group),
    ...(group.summaryRow ? [group.summaryRow] : []),
    ...(group.bankFolds ?? []).map((batch) => batch.summaryRow),
    ...paneIds.flatMap((paneId) => group.collapsedRows?.[paneId] ?? []),
  ];
}


/** Select the full requested set atomically; a partial selection is completed, never inverted. */
export function toggleWorkbenchSelectionRows(current: WorkbenchRecord[], requested: WorkbenchRecord[]) {
  const next = new Map(current.map(row => [workbenchRowIdentityKey(row), row]));
  const allSelected = requested.every(row => next.has(workbenchRowIdentityKey(row)));
  for (const row of requested) {
    const key = workbenchRowIdentityKey(row);
    if (allSelected) next.delete(key);
    else next.set(key, row);
  }
  return [...next.values()];
}

/** Split amounts and ownership come from canonical sibling DTOs, never from visible/filter rows. */
export function resolveWorkbenchBankSelection(row: WorkbenchRecord, unitId?: string): WorkbenchRecord[] {
  if (row.recordType !== "bank" || !row.isSplit) return [row];
  const parts = row.bankSplitParts;
  if (!parts?.length || !row.parentRowId || !parts.some(part => part.id === row.id)) {
    throw new Error("流水拆分信息不完整，请刷新后重试。");
  }
  const selected = unitId === undefined ? parts : parts.filter(part => part.id === unitId);
  if (!selected.length || selected.some(part => part.relation_case_id === undefined)) {
    throw new Error("流水子项关联状态不完整，请刷新后重试。");
  }
  if (selected.some(part => part.relation_case_id !== null && part.relation_case_id !== row.caseId)) {
    throw new Error("部分子项已属于其他关联，请打开流水详情选择可用子项，或先处理已有关系。");
  }
  return selected.map(part => ({
    ...row,
    id: part.id,
    caseId: part.relation_case_id ?? undefined,
    amount: part.amount,
    categoryCode: part.category_code,
    categoryLabel: part.category_label,
    categoryPath: part.category_path,
    categoryPrimaryLabel: part.category_path[0],
    categorySubLabel: part.category_path[1],
    categoryLabelPath: part.category_path,
    sourceOaId: undefined,
    sourceExpenseItemIds: undefined,
    workbenchAnomalies: undefined,
    tableValues: { ...row.tableValues, amount: part.amount },
  }));
}
