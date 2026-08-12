import type { WorkbenchRelationGroup, WorkbenchRecord, WorkbenchRecordType } from "./types";
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
  includedRowIdentityKeys: string[];
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
  const sourceRowsByIdentity = new Map(
    flattenWorkbenchGroups(sourceGroups).map((row) => [workbenchRowIdentityKey(row), row]),
  );
  const explicitRowIdentityKeys = explicitRows.map(workbenchRowIdentityKey);
  const explicitRowIdentityKeySet = new Set(explicitRowIdentityKeys);
  const includedRowsByIdentity = new Map<string, WorkbenchRecord>();

  explicitRows.forEach((row) => {
    const identityKey = workbenchRowIdentityKey(row);
    includedRowsByIdentity.set(identityKey, sourceRowsByIdentity.get(identityKey) ?? row);
  });

  sourceGroups.forEach((group) => {
    const groupRows = flattenWorkbenchGroup(group);
    if (!groupRows.some((row) => explicitRowIdentityKeySet.has(workbenchRowIdentityKey(row)))) {
      return;
    }

    groupRows.forEach((row) => includedRowsByIdentity.set(workbenchRowIdentityKey(row), row));
  });

  const includedRows = Array.from(includedRowsByIdentity.values());
  const relatedRowIdentityKeySet = new Set(
    includedRows
      .map(workbenchRowIdentityKey)
      .filter((identityKey) => !explicitRowIdentityKeySet.has(identityKey)),
  );

  return {
    explicitRows: explicitRowIdentityKeys
      .map((identityKey) => includedRowsByIdentity.get(identityKey))
      .filter((row): row is WorkbenchRecord => Boolean(row)),
    includedRows,
    includedRowIdentityKeys: includedRows.map(workbenchRowIdentityKey),
    relatedRowIdentityKeySet,
    summary: summarizeWorkbenchRows(includedRows, explicitRowIdentityKeySet.size),
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

function flattenWorkbenchGroups(groups: WorkbenchRelationGroup[]) {
  return groups.flatMap(flattenWorkbenchGroup);
}

function flattenWorkbenchGroup(group: WorkbenchRelationGroup) {
  return paneIds.flatMap((paneId) => group.rows[paneId]);
}
