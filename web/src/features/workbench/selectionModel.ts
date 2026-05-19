import type { WorkbenchCandidateGroup, WorkbenchRecord, WorkbenchRecordType } from "./types";

const paneIds: WorkbenchRecordType[] = ["oa", "bank", "invoice"];

export type WorkbenchSelectionSummary = {
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

  const selectedOaIds = new Set(
    explicitRows
      .map((row) => sourceRowsById.get(row.id) ?? row)
      .filter((row) => row.recordType === "oa")
      .map((row) => row.id),
  );
  sourceGroups.forEach((group) => {
    const groupRows = flattenWorkbenchGroup(group);
    if (!groupRows.some((row) => explicitRowIdSet.has(row.id))) {
      return;
    }

    if (zoneId === "paired" || groupPreservesExistingContext(group)) {
      groupRows.forEach((row) => includedRowsById.set(row.id, row));
      return;
    }

    groupRows.forEach((row) => {
      const sourceOaId = readOaSourceId(row);
      if (sourceOaId && selectedOaIds.has(sourceOaId)) {
        includedRowsById.set(row.id, row);
      }
    });
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
    summary: summarizeWorkbenchRows(includedRows),
  };
}

export function summarizeWorkbenchRows(rows: WorkbenchRecord[]): WorkbenchSelectionSummary {
  const byType = {
    oa: rows.filter((row) => row.recordType === "oa"),
    bank: rows.filter((row) => row.recordType === "bank"),
    invoice: rows.filter((row) => row.recordType === "invoice"),
  };

  return {
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

function readOaSourceId(row: WorkbenchRecord) {
  if (
    row.sourceKind !== "oa_attachment_invoice"
    && row.sourceKind !== "oa_attachment_payment_receipt"
    && row.sourceKind !== "oa_attachment_unknown"
  ) {
    return null;
  }

  const sourceField = row.detailFields.find((field) =>
    field.label === "来源OA单号" || field.label === "derived_from_oa_id" || field.label === "source_oa_id",
  );
  const sourceId = sourceField?.value.trim();
  return sourceId && sourceId !== "--" && sourceId !== "—" ? sourceId : null;
}

function groupPreservesExistingContext(group: WorkbenchCandidateGroup) {
  return group.canWithdraw
    || group.reason === "relation_snapshot"
    || group.reason === "oa_attachment_source_relation";
}
