import { describe, expect, test } from "vitest";

import {
  buildWorkbenchSelectionContext,
  workbenchComparableAmountCents,
  workbenchRowIdentityKey,
} from "../features/workbench/selectionModel";
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
  test("uses invoice gross amount as the comparable business amount", () => {
    const invoice = row("invoice-gross", "invoice", "99.01");
    invoice.tableValues.grossAmount = "100.00";

    expect(workbenchComparableAmountCents(invoice)).toBe(10_000);
  });

  test("unpaired zone selection keeps a singleton fact independent", () => {
    const sourceGroup = group("unpaired-1");
    const selectedBankRow = sourceGroup.rows.bank[0];

    const context = buildWorkbenchSelectionContext({
      explicitRows: [selectedBankRow],
      sourceGroups: [sourceGroup],
      zoneId: "unpaired",
    });

    expect(context.explicitRows.map((record) => record.id)).toEqual(["unpaired-1-bank"]);
    expect(context.includedRowIdentityKeys).toEqual([workbenchRowIdentityKey(selectedBankRow)]);
    expect([...context.relatedRowIdentityKeySet]).toEqual([]);
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
    expect(context.includedRowIdentityKeys).toEqual([
      "bank\u001fbank-partial",
      "oa\u001foa-partial",
    ]);
    expect([...context.relatedRowIdentityKeySet]).toEqual(["oa\u001foa-partial"]);
    expect(context.summary).toMatchObject({
      explicitTotal: 1,
      total: 2,
      oa: 1,
      bank: 1,
      invoice: 0,
    });
  });

  test("keeps records with the same source id distinct across panes", () => {
    const sharedBankRow = row("shared-source-id", "bank");
    const sharedOaRow = row("shared-source-id", "oa");
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:typed-collision",
      groupType: "paired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "active_formal_relation",
      rows: {
        oa: [sharedOaRow],
        bank: [sharedBankRow],
        invoice: [],
      },
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [sharedBankRow],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.explicitRows).toEqual([sharedBankRow]);
    expect(context.includedRows).toEqual([sharedBankRow, sharedOaRow]);
    expect(context.includedRowIdentityKeys).toEqual([
      "bank\u001fshared-source-id",
      "oa\u001fshared-source-id",
    ]);
    expect([...context.relatedRowIdentityKeySet]).toEqual(["oa\u001fshared-source-id"]);
    expect(context.summary).toMatchObject({ explicitTotal: 1, total: 2, oa: 1, bank: 1 });
  });
});
