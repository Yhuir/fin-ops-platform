import type { WorkbenchCandidateGroup, WorkbenchRecord, WorkbenchRecordType } from "./types";

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
  includedRowIds: string[];
  relatedRowIdSet: Set<string>;
  summary: WorkbenchSelectionSummary;
};

export function buildWorkbenchSelectionContext({
  explicitRows,
  sourceGroups,
  zoneId,
}: {
  explicitRows: WorkbenchRecord[];
  sourceGroups: WorkbenchCandidateGroup[];
  zoneId: "paired" | "open";
}): WorkbenchSelectionContext {
  const sourceRowsById = new Map(flattenWorkbenchGroups(sourceGroups).map((row) => [row.id, row]));
  const explicitRowIds = explicitRows.map((row) => row.id);
  const explicitRowIdSet = new Set(explicitRowIds);
  const includedRowsById = new Map<string, WorkbenchRecord>();

  explicitRows.forEach((row) => {
    includedRowsById.set(row.id, sourceRowsById.get(row.id) ?? row);
  });

  sourceGroups.forEach((group) => {
    const groupRows = flattenWorkbenchGroup(group);
    if (!groupRows.some((row) => explicitRowIdSet.has(row.id))) {
      return;
    }

    groupRows.forEach((row) => includedRowsById.set(row.id, row));
  });

  const includedRows = Array.from(includedRowsById.values());
  const relatedRowIdSet = new Set(
    includedRows.map((row) => row.id).filter((rowId) => !explicitRowIdSet.has(rowId)),
  );

  return {
    explicitRows: explicitRowIds
      .map((rowId) => includedRowsById.get(rowId))
      .filter((row): row is WorkbenchRecord => Boolean(row)),
    includedRows,
    includedRowIds: includedRows.map((row) => row.id),
    relatedRowIdSet,
    summary: summarizeWorkbenchRows(includedRows, explicitRowIdSet.size),
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
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

function sumWorkbenchAmountCents(rows: WorkbenchRecord[]) {
  return rows.reduce((total, row) => total + parseWorkbenchAmountCents(workbenchSummaryAmount(row)), 0);
}

function workbenchSummaryAmount(row: WorkbenchRecord) {
  if (row.recordType === "invoice") {
    const grossAmount = row.tableValues.grossAmount?.trim();
    if (grossAmount && grossAmount !== "--" && grossAmount !== "—") {
      return grossAmount;
    }
  }
  return row.amount;
}

function flattenWorkbenchGroups(groups: WorkbenchCandidateGroup[]) {
  return groups.flatMap(flattenWorkbenchGroup);
}

function flattenWorkbenchGroup(group: WorkbenchCandidateGroup) {
  return paneIds.flatMap((paneId) => group.rows[paneId]);
}
