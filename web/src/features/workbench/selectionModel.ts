import type {
  WorkbenchRecordIdentity,
  WorkbenchRelationGroup,
  WorkbenchRecord,
  WorkbenchRecordType,
} from "./types";
import { formatMoney } from "../money";

const paneIds: WorkbenchRecordType[] = ["oa", "bank", "invoice"];

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
  const amountCents: Record<WorkbenchRecordType, number> = { oa: 0, bank: 0, invoice: 0 };

  explicitRowsByIdentity.forEach((row, identityKey) => {
    const relationGroup = relationGroupBySelectableRowIdentity.get(identityKey);
    if (!relationGroup) {
      includedRowsByIdentity.set(identityKey, row);
      includedIdentitiesByKey.set(identityKey, { id: row.id, recordType: row.recordType });
      amountCents[row.recordType] += workbenchComparableAmountCents(row);
      return;
    }
    selectedRelationGroups.set(relationGroup.id, relationGroup);
  });

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
    paneIds.forEach((paneId) => {
      amountCents[paneId] += selection.amountCents[paneId];
    });
  });

  const includedRows = Array.from(includedRowsByIdentity.values());
  const includedRowIdentities = Array.from(includedIdentitiesByKey.values());
  const includedRowIdentityKeys = Array.from(includedIdentitiesByKey.keys());
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
  amountCents: Record<WorkbenchRecordType, number>;
} | undefined {
  const identities = group.formalMemberIdentities;
  if (!Array.isArray(identities) || identities.length === 0) {
    return undefined;
  }
  const rowsByIdentity = new Map(
    flattenWorkbenchGroup(group).map((row) => [workbenchRowIdentityKey(row), row]),
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
  const resolvedAmountCents = resolvedRows.length === identities.length
    ? sumWorkbenchAmountsByType(resolvedRows)
    : resolveAuthoritativeRelationAmountCents(group, identities);
  if (!resolvedAmountCents) {
    return undefined;
  }
  return { identities, rows: resolvedRows, amountCents: resolvedAmountCents };
}

function resolveAuthoritativeRelationAmountCents(
  group: WorkbenchRelationGroup,
  identities: WorkbenchRecordIdentity[],
): Record<WorkbenchRecordType, number> | undefined {
  const counts = countWorkbenchIdentitiesByType(identities);
  const amountValues: Partial<Record<WorkbenchRecordType, string>> = {
    oa: group.amountCheck?.oaTotal,
    bank: group.amountCheck?.bankTotal,
    invoice: group.amountCheck?.invoiceTotal,
  };
  const summaryRow = group.summaryRow;
  const isExactSinglePaneSummary = Boolean(
    summaryRow
    && identities.every((identity) => identity.recordType === summaryRow.recordType)
    && (
      summaryRow.sourceKind === "bank_flow_rule_batch_summary"
      || summaryRow.sourceKind === "etc_invoice_summary"
    ),
  );
  const resolved: Record<WorkbenchRecordType, number> = { oa: 0, bank: 0, invoice: 0 };
  for (const paneId of paneIds) {
    if (counts[paneId] === 0) {
      continue;
    }
    const exactAmount = parseExactWorkbenchAmountCents(amountValues[paneId]);
    if (exactAmount !== undefined) {
      resolved[paneId] = exactAmount;
      continue;
    }
    if (isExactSinglePaneSummary && summaryRow?.recordType === paneId) {
      resolved[paneId] = workbenchComparableAmountCents(summaryRow);
      continue;
    }
    return undefined;
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

function sumWorkbenchAmountsByType(rows: WorkbenchRecord[]) {
  return {
    oa: sumWorkbenchAmountCents(rows.filter((row) => row.recordType === "oa")),
    bank: sumWorkbenchAmountCents(rows.filter((row) => row.recordType === "bank")),
    invoice: sumWorkbenchAmountCents(rows.filter((row) => row.recordType === "invoice")),
  };
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
  amountCents: Record<WorkbenchRecordType, number>,
  explicitTotal: number,
): WorkbenchSelectionSummary {
  const counts = countWorkbenchIdentitiesByType(identities);
  return {
    explicitTotal,
    total: identities.length,
    ...counts,
    amounts: {
      oa: formatWorkbenchAmountCents(amountCents.oa),
      bank: formatWorkbenchAmountCents(amountCents.bank),
      invoice: formatWorkbenchAmountCents(amountCents.invoice),
    },
  };
}

function flattenWorkbenchGroupSelectionRows(group: WorkbenchRelationGroup) {
  return [
    ...flattenWorkbenchGroup(group),
    ...(group.summaryRow ? [group.summaryRow] : []),
    ...paneIds.flatMap((paneId) => group.collapsedRows?.[paneId] ?? []),
  ];
}
