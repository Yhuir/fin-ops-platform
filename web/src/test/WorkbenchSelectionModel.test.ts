import { describe, expect, test } from "vitest";

import { buildWorkbenchSelectionContext } from "../features/workbench/selectionModel";
import type { WorkbenchCandidateGroup, WorkbenchRecord } from "../features/workbench/types";

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
    actionVariant: "open",
    availableActions: [],
  };
}

function group(id: string): WorkbenchCandidateGroup {
  return {
    id,
    groupType: "open",
    rawGroupType: "candidate",
    matchConfidence: "medium",
    reason: "automatic_candidate",
    rows: {
      oa: [row(`${id}-oa`, "oa")],
      bank: [row(`${id}-bank`, "bank")],
      invoice: [row(`${id}-invoice`, "invoice")],
    },
  };
}

describe("buildWorkbenchSelectionContext", () => {
  test("open zone selection brings in the whole candidate group when any row is selected", () => {
    const sourceGroup = group("candidate-1");
    const selectedBankRow = sourceGroup.rows.bank[0];

    const context = buildWorkbenchSelectionContext({
      explicitRows: [selectedBankRow],
      sourceGroups: [sourceGroup],
      zoneId: "open",
    });

    expect(context.explicitRows.map((record) => record.id)).toEqual(["candidate-1-bank"]);
    expect(context.includedRowIds).toEqual(["candidate-1-bank", "candidate-1-oa", "candidate-1-invoice"]);
    expect([...context.relatedRowIdSet].sort()).toEqual(["candidate-1-invoice", "candidate-1-oa"]);
    expect(context.summary).toMatchObject({
      explicitTotal: 1,
      total: 3,
      oa: 1,
      bank: 1,
      invoice: 1,
    });
  });
});
