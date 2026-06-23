import { describe, expect, test } from "vitest";

import {
  canSelectBatchRows,
  canSubmitInternalTransferBatch,
  canWithdrawBatch,
  statusBucketFor,
} from "../features/noOaBankBatches/policy";
import type { NoOaBankBatch } from "../features/noOaBankBatches/types";

function batch(overrides: Partial<NoOaBankBatch> = {}): NoOaBankBatch {
  return {
    batchId: "batch-001",
    batchType: "fee",
    batchLabel: "手续费",
    scopeMonth: "2026-01",
    accountKey: "ccb:8106",
    bankName: "建设银行",
    accountLast4: "8106",
    status: "draft",
    statusBucket: "unsubmitted",
    rowCount: 1,
    totalAmount: "1.00",
    submittedBy: "",
    submittedAt: null,
    withdrawnBy: "",
    withdrawnAt: null,
    conflictReason: "",
    blockedReason: "",
    tagCounts: {},
    directionCounts: {},
    canSubmit: false,
    canWithdraw: false,
    version: 1,
    ...overrides,
  };
}

describe("no OA bank batch policy", () => {
  test.each([
    "fee",
    "salary",
    "holiday_bonus",
    "bonus",
    "tax_payment",
    "treasury_tax_collection",
    "social_security",
  ])("keeps ordinary %s batches row-selectable for legacy unsubmitted status", (batchType) => {
    const subject = batch({
      batchType,
      status: "unsubmitted",
      statusBucket: "unsubmitted",
      canSubmit: false,
    });

    expect(statusBucketFor(subject)).toBe("unsubmitted");
    expect(canSelectBatchRows(subject, "unsubmitted")).toBe(true);
    expect(canSubmitInternalTransferBatch(subject, "unsubmitted")).toBe(false);
  });

  test("routes internal transfer drafts to whole-batch submit instead of row selection", () => {
    const subject = batch({
      batchType: "internal_transfer",
      status: "unsubmitted",
      statusBucket: "unsubmitted",
      canSubmit: true,
    });

    expect(canSelectBatchRows(subject, "unsubmitted")).toBe(false);
    expect(canSubmitInternalTransferBatch(subject, "unsubmitted")).toBe(true);
  });

  test("does not expose submit controls for non-draft or non-unsubmitted lifecycle states", () => {
    expect(canSelectBatchRows(batch({ status: "conflict", statusBucket: "unsubmitted" }), "unsubmitted")).toBe(false);
    expect(canSelectBatchRows(batch({ status: "stale", statusBucket: "unsubmitted" }), "unsubmitted")).toBe(false);
    expect(canSelectBatchRows(batch({ status: "submitted", statusBucket: "submitted" }), "submitted")).toBe(false);
    expect(canSubmitInternalTransferBatch(
      batch({ batchType: "internal_transfer", status: "submitted", statusBucket: "submitted", canSubmit: true }),
      "submitted",
    )).toBe(false);
  });

  test("keeps withdraw availability tied to submitted lifecycle or backend capability", () => {
    expect(canWithdrawBatch(batch({ status: "submitted", canWithdraw: false }))).toBe(true);
    expect(canWithdrawBatch(batch({ status: "draft", canWithdraw: true }))).toBe(true);
    expect(canWithdrawBatch(batch({ status: "draft", canWithdraw: false }))).toBe(false);
  });
});
