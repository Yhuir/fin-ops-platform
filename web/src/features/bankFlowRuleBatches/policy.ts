import type { BankFlowRuleBatch, BankFlowRuleBatchStatusBucket } from "./types";

export function statusBucketFor(batch: BankFlowRuleBatch): BankFlowRuleBatchStatusBucket {
  if (batch.statusBucket === "submitted" || batch.status === "submitted") {
    return "submitted";
  }
  if (batch.statusBucket === "withdrawn" || batch.status === "withdrawn") {
    return "withdrawn";
  }
  return "unsubmitted";
}

export function canWithdrawBatch(batch: BankFlowRuleBatch) {
  return batch.canWithdraw || batch.status === "submitted";
}

export function isUnsubmittedDraftBatch(batch: BankFlowRuleBatch) {
  return statusBucketFor(batch) === "unsubmitted"
    && (batch.status === "draft" || batch.status === "unsubmitted");
}

export function canSelectBatchRows(batch: BankFlowRuleBatch, bucket: BankFlowRuleBatchStatusBucket) {
  return bucket === "unsubmitted"
    && isUnsubmittedDraftBatch(batch)
    && batch.batchType !== "internal_transfer";
}

export function canSubmitInternalTransferBatch(batch: BankFlowRuleBatch, bucket: BankFlowRuleBatchStatusBucket) {
  return bucket === "unsubmitted"
    && isUnsubmittedDraftBatch(batch)
    && batch.canSubmit
    && batch.batchType === "internal_transfer";
}
