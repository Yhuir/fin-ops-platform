import { describe, expect, test } from "vitest";

import { buildWorkbenchSelectionContext } from "../features/workbench/selectionModel";
import type { WorkbenchRelationGroup, WorkbenchRecord } from "../features/workbench/types";

function row(id: string, recordType: WorkbenchRecord["recordType"], amount = "100.00"): WorkbenchRecord {
  return {
    id,
    caseId: "",
    recordType,
    label: id,
    status: "待关联",
    statusCode: "pending_match",
    statusTone: "warn",
    exceptionHandled: false,
    amount,
    counterparty: "测试往来",
    tableValues: {},
    detailFields: [],
    actionVariant: "detail-only",
    availableActions: [],
  };
}

function group(id: string): WorkbenchRelationGroup {
  return {
    id,
    groupType: "unpaired",
    rawGroupType: "unpaired",
    matchConfidence: "low",
    reason: "unpaired_fact",
    rows: {
      bank: [row(`${id}-bank`, "bank")],
      oa: [],
      invoice: [],
    },
  };
}

describe("buildWorkbenchSelectionContext", () => {
  test("unpaired zone selection keeps a singleton fact independent", () => {
    const sourceGroup = group("unpaired-1");
    const selectedBankRow = sourceGroup.rows.bank[0];

    const context = buildWorkbenchSelectionContext({
      explicitRows: [selectedBankRow],
      sourceGroups: [sourceGroup],
      zoneId: "unpaired",
    });

    expect(context.explicitRows.map((record) => record.id)).toEqual(["unpaired-1-bank"]);
    expect(context.includedRowIds).toEqual(["unpaired-1-bank"]);
    expect([...context.relatedRowIdSet]).toEqual([]);
    expect(context.summary).toMatchObject({
      explicitTotal: 1,
      total: 1,
      oa: 0,
      bank: 1,
      invoice: 0,
    });
  });

  test("paired zone selection keeps a formal two-pane relation as one selectable group", () => {
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:CASE-PARTIAL",
      groupType: "paired",
      rawGroupType: "relation",
      relationMode: "manual_confirmed",
      matchConfidence: "medium",
      reason: "active_formal_relation",
      rows: {
        oa: [row("oa-partial", "oa")],
        bank: [row("bank-partial", "bank")],
        invoice: [],
      },
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [sourceGroup.rows.bank[0]],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.explicitRows.map((record) => record.id)).toEqual(["bank-partial"]);
    expect(context.includedRowIds).toEqual(["bank-partial", "oa-partial"]);
    expect([...context.relatedRowIdSet]).toEqual(["oa-partial"]);
    expect(context.summary).toMatchObject({
      explicitTotal: 1,
      total: 2,
      oa: 1,
      bank: 1,
      invoice: 0,
    });
  });
});
