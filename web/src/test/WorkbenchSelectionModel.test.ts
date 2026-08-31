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

function directionalRow(
  id: string,
  recordType: WorkbenchRecord["recordType"],
  amount: string,
  amountDirection: "payment" | "receipt",
): WorkbenchRecord {
  return Object.assign(row(id, recordType, amount), { amountDirection });
}

function authoritativeAmountCheck(
  oaTotal: string,
  bankTotal: string,
  invoiceTotal: string,
): NonNullable<WorkbenchRelationGroup["amountCheck"]> {
  return {
    status: "matched",
    direction: "payment",
    bankAmount: bankTotal,
    oaAmount: oaTotal,
    oaTotal,
    bankTotal,
    invoiceTotal,
    amountDelta: "0.00",
    requiresNote: false,
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

  test("nets refund receipts against payment bank rows without changing the selected row count", () => {
    const selectedRows = [
      directionalRow("oa-payment", "oa", "2100.00", "payment"),
      directionalRow("bank-payment-1", "bank", "2100.00", "payment"),
      directionalRow("bank-refund", "bank", "2100.00", "receipt"),
      directionalRow("bank-payment-2", "bank", "2100.00", "payment"),
    ];

    const context = buildWorkbenchSelectionContext({
      explicitRows: selectedRows,
      sourceGroups: [],
      zoneId: "unpaired",
    });

    expect(context.summary).toMatchObject({
      explicitTotal: 4,
      total: 4,
      oa: 1,
      bank: 3,
      invoice: 0,
      amounts: { oa: "2100.00", bank: "2100.00", invoice: "0.00" },
    });
  });

  test("nets payment reversals against receipt bank rows", () => {
    const selectedRows = [
      directionalRow("oa-receipt", "oa", "2100.00", "receipt"),
      directionalRow("bank-receipt-1", "bank", "2100.00", "receipt"),
      directionalRow("bank-reversal", "bank", "600.00", "payment"),
      directionalRow("bank-receipt-2", "bank", "600.00", "receipt"),
    ];

    const context = buildWorkbenchSelectionContext({
      explicitRows: selectedRows,
      sourceGroups: [],
      zoneId: "unpaired",
    });

    expect(context.summary.amounts.bank).toBe("2100.00");
  });

  test("does not guess a comparison amount for mixed bank directions without a principal direction", () => {
    const selectedRows = [
      directionalRow("bank-payment", "bank", "2100.00", "payment"),
      directionalRow("bank-receipt", "bank", "2100.00", "receipt"),
    ];

    const context = buildWorkbenchSelectionContext({
      explicitRows: selectedRows,
      sourceGroups: [],
      zoneId: "unpaired",
    });

    expect(context.summary).toMatchObject({
      total: 2,
      bank: 2,
      amounts: { bank: "--" },
    });
  });

  test("does not guess a comparison amount when non-bank rows disagree on the principal direction", () => {
    const selectedRows = [
      directionalRow("oa-payment-conflict", "oa", "2100.00", "payment"),
      directionalRow("invoice-receipt-conflict", "invoice", "2100.00", "receipt"),
      directionalRow("bank-payment-conflict", "bank", "2100.00", "payment"),
    ];

    const context = buildWorkbenchSelectionContext({
      explicitRows: selectedRows,
      sourceGroups: [],
      zoneId: "unpaired",
    });

    expect(context.summary).toMatchObject({
      total: 3,
      bank: 1,
      amounts: { bank: "--" },
    });
  });

  test("nets an unknown-direction bank-only formal relation inside a payment selection", () => {
    const formalBankRows = [
      directionalRow("turnover-payment", "bank", "2100.00", "payment"),
      directionalRow("turnover-receipt", "bank", "2100.00", "receipt"),
    ];
    const formalGroup: WorkbenchRelationGroup = {
      id: "case:turnover:turnover-rel-2100",
      groupType: "unpaired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "active_formal_relation",
      formalMemberIdentities: formalBankRows.map((record) => ({
        id: record.id,
        recordType: record.recordType,
      })),
      rows: { oa: [], bank: formalBankRows, invoice: [] },
      amountCheck: {
        status: "matched",
        direction: "unknown",
        bankAmount: "4200.00",
        oaAmount: "--",
        bankTotal: "4200.00",
        amountDelta: "--",
        requiresNote: false,
      },
    };
    const oaPayment = directionalRow("oa-payment-2100", "oa", "2100.00", "payment");
    const independentBankPayment = directionalRow(
      "bank-payment-2100",
      "bank",
      "2100.00",
      "payment",
    );

    const context = buildWorkbenchSelectionContext({
      explicitRows: [formalBankRows[0], oaPayment, independentBankPayment],
      sourceGroups: [formalGroup],
      zoneId: "unpaired",
    });

    expect(context.summary).toMatchObject({
      explicitTotal: 3,
      total: 4,
      oa: 1,
      bank: 3,
      invoice: 0,
      amounts: { oa: "2100.00", bank: "2100.00", invoice: "0.00" },
    });
  });

  test("does not use an absolute formal bank total when its principal direction is unknown", () => {
    const formalBankRows = [
      directionalRow("unknown-payment", "bank", "2100.00", "payment"),
      directionalRow("unknown-receipt", "bank", "2100.00", "receipt"),
    ];
    const formalGroup: WorkbenchRelationGroup = {
      id: "case:turnover:unknown-direction",
      groupType: "unpaired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "active_formal_relation",
      formalMemberIdentities: formalBankRows.map((record) => ({
        id: record.id,
        recordType: record.recordType,
      })),
      rows: { oa: [], bank: formalBankRows, invoice: [] },
      amountCheck: {
        status: "matched",
        direction: "unknown",
        bankAmount: "4200.00",
        oaAmount: "--",
        bankTotal: "4200.00",
        amountDelta: "--",
        requiresNote: false,
      },
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [formalBankRows[0]],
      sourceGroups: [formalGroup],
      zoneId: "unpaired",
    });

    expect(context.summary).toMatchObject({
      total: 2,
      bank: 2,
      amounts: { bank: "--" },
    });
  });

  test("uses the authoritative amount check for a fully hydrated formal relation", () => {
    const formalOa = directionalRow("formal-net-oa", "oa", "2100.00", "payment");
    const formalBankRows = [
      directionalRow("formal-net-payment-1", "bank", "2100.00", "payment"),
      directionalRow("formal-net-refund", "bank", "2100.00", "receipt"),
      directionalRow("formal-net-payment-2", "bank", "2100.00", "payment"),
    ];
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:formal-authoritative-net",
      groupType: "paired",
      rawGroupType: "relation",
      relationMode: "manual_confirmed",
      matchConfidence: "high",
      reason: "active_formal_relation",
      formalMemberIdentities: [formalOa, ...formalBankRows].map((record) => ({
        id: record.id,
        recordType: record.recordType,
      })),
      rows: { oa: [formalOa], bank: formalBankRows, invoice: [] },
      amountCheck: {
        status: "matched",
        direction: "payment",
        bankAmount: "2100.00",
        oaAmount: "2100.00",
        oaTotal: "2100.00",
        bankTotal: "2100.00",
        invoiceTotal: "0.00",
        amountDelta: "0.00",
        requiresNote: false,
      },
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [formalBankRows[0]],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.summary).toMatchObject({
      total: 4,
      oa: 1,
      bank: 3,
      amounts: { oa: "2100.00", bank: "2100.00", invoice: "0.00" },
    });
  });

  test("keeps a fully hydrated formal relation selectable without inferring a missing amount check", () => {
    const formalOa = directionalRow("formal-missing-amount-oa", "oa", "2100.00", "payment");
    const formalBank = directionalRow(
      "formal-missing-amount-bank",
      "bank",
      "2100.00",
      "payment",
    );
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:formal-missing-amount-check",
      groupType: "paired",
      rawGroupType: "relation",
      relationMode: "manual_confirmed",
      matchConfidence: "high",
      reason: "active_formal_relation",
      formalMemberIdentities: [formalOa, formalBank].map((record) => ({
        id: record.id,
        recordType: record.recordType,
      })),
      rows: { oa: [formalOa], bank: [formalBank], invoice: [] },
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [formalBank],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.includedRows).toEqual([formalOa, formalBank]);
    expect(context.summary).toMatchObject({
      total: 2,
      oa: 1,
      bank: 1,
      amounts: { oa: "--", bank: "--", invoice: "0.00" },
    });
  });

  test("preserves the authoritative principal-side amount for a turnover closure", () => {
    const formalOa = directionalRow("closure-oa", "oa", "240000.00", "payment");
    const formalBankRows = [
      directionalRow("closure-payment", "bank", "240000.00", "payment"),
      directionalRow("closure-receipt", "bank", "240000.00", "receipt"),
    ];
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:turnover-closure-authoritative",
      groupType: "paired",
      rawGroupType: "relation",
      relationMode: "turnover_manual_closure",
      matchConfidence: "high",
      reason: "active_formal_relation",
      formalMemberIdentities: [formalOa, ...formalBankRows].map((record) => ({
        id: record.id,
        recordType: record.recordType,
      })),
      rows: { oa: [formalOa], bank: formalBankRows, invoice: [] },
      amountCheck: {
        status: "matched",
        direction: "payment",
        bankAmount: "240000.00",
        oaAmount: "240000.00",
        oaTotal: "240000.00",
        bankTotal: "240000.00",
        invoiceTotal: "0.00",
        amountDelta: "0.00",
        requiresNote: false,
      },
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [formalBankRows[0]],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.summary.amounts.bank).toBe("240000.00");
  });

  test("paired zone selection keeps a formal two-pane relation as one selectable group", () => {
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:CASE-PARTIAL",
      groupType: "paired",
      rawGroupType: "relation",
      relationMode: "manual_confirmed",
      matchConfidence: "medium",
      reason: "active_formal_relation",
      formalMemberIdentities: [
        { id: "oa-partial", recordType: "oa" },
        { id: "bank-partial", recordType: "bank" },
      ],
      rows: {
        oa: [row("oa-partial", "oa")],
        bank: [row("bank-partial", "bank")],
        invoice: [],
      },
      amountCheck: authoritativeAmountCheck("100.00", "100.00", "0.00"),
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [sourceGroup.rows.bank[0]],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.explicitRows.map((record) => record.id)).toEqual(["bank-partial"]);
    expect(context.includedRowIdentityKeys).toEqual([
      "oa\u001foa-partial",
      "bank\u001fbank-partial",
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
      formalMemberIdentities: [
        { id: "shared-source-id", recordType: "oa" },
        { id: "shared-source-id", recordType: "bank" },
      ],
      rows: {
        oa: [sharedOaRow],
        bank: [sharedBankRow],
        invoice: [],
      },
      amountCheck: authoritativeAmountCheck("100.00", "100.00", "0.00"),
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [sharedBankRow],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.explicitRows).toEqual([sharedBankRow]);
    expect(context.includedRows).toEqual([sharedOaRow, sharedBankRow]);
    expect(context.includedRowIdentityKeys).toEqual([
      "oa\u001fshared-source-id",
      "bank\u001fshared-source-id",
    ]);
    expect([...context.relatedRowIdentityKeySet]).toEqual(["oa\u001fshared-source-id"]);
    expect(context.summary).toMatchObject({ explicitTotal: 1, total: 2, oa: 1, bank: 1 });
  });

  test("expands a large formal relation without truncating its members", () => {
    const bankRows = Array.from({ length: 500 }, (_, index) => row(`bank-${index}`, "bank"));
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:large-relation",
      groupType: "paired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "active_formal_relation",
      formalMemberIdentities: bankRows.map((bankRow) => ({
        id: bankRow.id,
        recordType: bankRow.recordType,
      })),
      rows: {
        oa: [],
        bank: bankRows,
        invoice: [],
      },
      amountCheck: authoritativeAmountCheck("0.00", "50000.00", "0.00"),
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [bankRows[0]],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.includedRows).toHaveLength(500);
    expect(context.includedRowIdentityKeys).toHaveLength(500);
    expect(context.summary).toMatchObject({ explicitTotal: 1, total: 500, bank: 500 });
  });

  test("resolves a relation display row to only the formal relation rows", () => {
    const summaryRow = row("relation-summary", "bank", "999999.00");
    summaryRow.actionVariant = "detail-only";
    const formalOa = row("formal-oa", "oa", "125.00");
    const formalBank = row("formal-bank", "bank", "125.00");
    const formalInvoice = row("formal-invoice", "invoice", "125.00");
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:display-alias",
      groupType: "paired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "active_formal_relation",
      summaryRow,
      formalMemberIdentities: [
        { id: "formal-oa", recordType: "oa" },
        { id: "formal-bank", recordType: "bank" },
        { id: "formal-invoice", recordType: "invoice" },
      ],
      rows: {
        oa: [formalOa],
        bank: [formalBank],
        invoice: [formalInvoice],
      },
      amountCheck: authoritativeAmountCheck("125.00", "125.00", "125.00"),
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [summaryRow],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.explicitRows).toEqual([summaryRow]);
    expect(context.includedRows).toEqual([formalOa, formalBank, formalInvoice]);
    expect(context.includedRowIdentityKeys).toEqual([
      "oa\u001fformal-oa",
      "bank\u001fformal-bank",
      "invoice\u001fformal-invoice",
    ]);
    expect(context.summary).toMatchObject({
      explicitTotal: 1,
      total: 3,
      oa: 1,
      bank: 1,
      invoice: 1,
      amounts: { oa: "125.00", bank: "125.00", invoice: "125.00" },
    });
  });

  test("resolves a detail-only collapsed row to its parent formal relation", () => {
    const collapsedDetail = row("collapsed-bank-detail", "bank", "25.00");
    collapsedDetail.actionVariant = "detail-only";
    const formalOa = row("collapsed-formal-oa", "oa", "200.00");
    const formalBank = row("collapsed-formal-bank", "bank", "200.00");
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:collapsed-detail-alias",
      groupType: "paired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "active_formal_relation",
      formalMemberIdentities: [
        { id: "collapsed-formal-oa", recordType: "oa" },
        { id: "collapsed-formal-bank", recordType: "bank" },
      ],
      rows: {
        oa: [formalOa],
        bank: [formalBank],
        invoice: [],
      },
      collapsedRows: {
        oa: [],
        bank: [collapsedDetail],
        invoice: [],
      },
      amountCheck: authoritativeAmountCheck("200.00", "200.00", "0.00"),
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [collapsedDetail],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.explicitRows).toEqual([collapsedDetail]);
    expect(context.includedRows).toEqual([formalOa, formalBank]);
    expect(context.summary).toMatchObject({
      explicitTotal: 1,
      total: 2,
      amounts: { oa: "200.00", bank: "200.00", invoice: "0.00" },
    });
    expect([...context.relatedRowIdentityKeySet]).toEqual([
      "oa\u001fcollapsed-formal-oa",
      "bank\u001fcollapsed-formal-bank",
    ]);
  });

  test("keeps one ETC relation amount when summary and detail aliases are selected together", () => {
    const summaryRow = row("etc-summary", "invoice", "2411.25");
    summaryRow.sourceKind = "etc_invoice_summary";
    const detailOne = row("etc-detail-1", "invoice", "58.64");
    detailOne.sourceKind = "etc_invoice";
    const detailTwo = row("etc-detail-2", "invoice", "88.86");
    detailTwo.sourceKind = "etc_invoice";
    const formalOa = row("etc-oa", "oa", "2411.25");
    const formalBank = row("etc-bank", "bank", "2411.25");
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:etc-batch",
      groupType: "paired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "active_formal_relation",
      summaryRow,
      formalMemberIdentities: [
        { id: "etc-oa", recordType: "oa" },
        { id: "etc-bank", recordType: "bank" },
        { id: "etc-summary", recordType: "invoice" },
      ],
      rows: {
        oa: [formalOa],
        bank: [formalBank],
        invoice: [summaryRow],
      },
      collapsedRows: {
        oa: [],
        bank: [],
        invoice: [detailOne, detailTwo],
      },
      amountCheck: authoritativeAmountCheck("2411.25", "2411.25", "2411.25"),
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [summaryRow, detailOne, detailTwo],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.explicitRows).toEqual([summaryRow, detailOne, detailTwo]);
    expect(context.includedRows).toEqual([formalOa, formalBank, summaryRow]);
    expect(context.includedRowIdentityKeys).toEqual([
      "oa\u001fetc-oa",
      "bank\u001fetc-bank",
      "invoice\u001fetc-summary",
    ]);
    expect(context.summary).toMatchObject({
      explicitTotal: 3,
      total: 3,
      oa: 1,
      bank: 1,
      invoice: 1,
      amounts: { oa: "2411.25", bank: "2411.25", invoice: "2411.25" },
    });
  });

  test("keeps a selected row independent inside a non-relation context group", () => {
    const selectedOa = row("context-oa", "oa", "90.00");
    const contextInvoice = row("context-invoice", "invoice", "90.00");
    const sourceGroup: WorkbenchRelationGroup = {
      id: "context:oa-attachment",
      groupType: "unpaired",
      rawGroupType: "oa_attachment_context",
      matchConfidence: "low",
      reason: "source_context_only",
      rows: {
        oa: [selectedOa],
        bank: [],
        invoice: [contextInvoice],
      },
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [selectedOa],
      sourceGroups: [sourceGroup],
      zoneId: "unpaired",
    });

    expect(context.includedRows).toEqual([selectedOa]);
    expect(context.summary).toMatchObject({ explicitTotal: 1, total: 1, oa: 1, invoice: 0 });
    expect([...context.relatedRowIdentityKeySet]).toEqual([]);
  });

  test("excludes source-owned display invoices from formal relation amounts and payload rows", () => {
    const formalOa = row("formal-only-oa", "oa", "137.95");
    const formalBank = row("formal-only-bank", "bank", "137.95");
    const displayInvoice = row("display-only-invoice", "invoice", "77.00");
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:formal-with-display",
      groupType: "paired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "active_formal_relation",
      formalMemberIdentities: [
        { id: formalOa.id, recordType: formalOa.recordType },
        { id: formalBank.id, recordType: formalBank.recordType },
      ],
      rows: {
        oa: [formalOa],
        bank: [formalBank],
        invoice: [displayInvoice],
      },
      amountCheck: authoritativeAmountCheck("137.95", "137.95", "0.00"),
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [displayInvoice],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.explicitRows).toEqual([displayInvoice]);
    expect(context.includedRows).toEqual([formalOa, formalBank]);
    expect(context.includedRowIdentityKeys).toEqual([
      "oa\u001fformal-only-oa",
      "bank\u001fformal-only-bank",
    ]);
    expect(context.summary).toMatchObject({
      explicitTotal: 1,
      total: 2,
      oa: 1,
      bank: 1,
      invoice: 0,
      amounts: { oa: "137.95", bank: "137.95", invoice: "0.00" },
    });
  });

  test("keeps compact bank-flow formal identities without inventing unhydrated records", () => {
    const summaryRow = row("bank-flow-summary", "bank", "124.50");
    summaryRow.sourceKind = "bank_flow_rule_batch_summary";
    const sourceGroup: WorkbenchRelationGroup = {
      id: "bank-flow-rule-batch:compact",
      groupType: "paired",
      rawGroupType: "relation",
      relationMode: "bank_flow_rule_batch",
      matchConfidence: "high",
      reason: "active_formal_relation",
      summaryRow,
      formalMemberIdentities: [
        { id: "bank-detail-1", recordType: "bank" },
        { id: "bank-detail-2", recordType: "bank" },
      ],
      rows: { oa: [], bank: [summaryRow], invoice: [] },
      amountCheck: authoritativeAmountCheck("0.00", "124.50", "0.00"),
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [summaryRow],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.explicitRows).toEqual([summaryRow]);
    expect(context.includedRows).toEqual([]);
    expect(context.includedRowIdentities).toEqual([
      { id: "bank-detail-1", recordType: "bank" },
      { id: "bank-detail-2", recordType: "bank" },
    ]);
    expect(context.selectedRelationGroupIds).toEqual(["bank-flow-rule-batch:compact"]);
    expect(context.summary).toMatchObject({
      explicitTotal: 1,
      total: 2,
      bank: 2,
      amounts: { oa: "0.00", bank: "124.50", invoice: "0.00" },
    });
  });

  test("keeps valid formal identities selectable when hydration and amount display are incomplete", () => {
    const formalOa = row("fail-closed-oa", "oa", "100.00");
    const displayInvoice = row("fail-closed-display", "invoice", "100.00");
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:invalid-formal-contract",
      groupType: "paired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "active_formal_relation",
      formalMemberIdentities: [
        { id: formalOa.id, recordType: formalOa.recordType },
        { id: "missing-bank", recordType: "bank" },
      ],
      rows: { oa: [formalOa], bank: [], invoice: [displayInvoice] },
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [displayInvoice],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.explicitRows).toEqual([displayInvoice]);
    expect(context.includedRows).toEqual([formalOa]);
    expect(context.includedRowIdentityKeys).toEqual([
      "oa\u001ffail-closed-oa",
      "bank\u001fmissing-bank",
    ]);
    expect(context.summary).toMatchObject({
      total: 2,
      oa: 1,
      bank: 1,
      invoice: 0,
      amounts: { oa: "--", bank: "--", invoice: "0.00" },
    });
  });

  test("deduplicates repeated explicit and formal rows by typed identity", () => {
    const formalOa = row("dedup-oa", "oa", "88.00");
    const formalBank = row("dedup-bank", "bank", "88.00");
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:typed-dedup",
      groupType: "paired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "active_formal_relation",
      formalMemberIdentities: [
        { id: "dedup-oa", recordType: "oa" },
        { id: "dedup-bank", recordType: "bank" },
      ],
      rows: {
        oa: [formalOa, { ...formalOa }],
        bank: [formalBank],
        invoice: [],
      },
      amountCheck: authoritativeAmountCheck("88.00", "88.00", "0.00"),
    };

    const context = buildWorkbenchSelectionContext({
      explicitRows: [formalBank, { ...formalBank }],
      sourceGroups: [sourceGroup],
      zoneId: "paired",
    });

    expect(context.explicitRows).toEqual([formalBank]);
    expect(context.includedRowIdentityKeys).toEqual([
      "oa\u001fdedup-oa",
      "bank\u001fdedup-bank",
    ]);
    expect(context.summary).toMatchObject({ explicitTotal: 1, total: 2, oa: 1, bank: 1 });
  });
});
