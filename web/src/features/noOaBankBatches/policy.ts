import type { NoOaBankBatch, NoOaBankBatchStatusBucket } from "./types";

export function statusBucketFor(batch: NoOaBankBatch): NoOaBankBatchStatusBucket {
  if (batch.statusBucket === "submitted" || batch.status === "submitted") {
    return "submitted";
  }
  if (batch.statusBucket === "withdrawn" || batch.status === "withdrawn") {
    return "withdrawn";
  }
  return "unsubmitted";
}

export function canWithdrawBatch(batch: NoOaBankBatch) {
  return batch.canWithdraw || batch.status === "submitted";
}

export function isUnsubmittedDraftBatch(batch: NoOaBankBatch) {
  return statusBucketFor(batch) === "unsubmitted"
    && (batch.status === "draft" || batch.status === "unsubmitted");
}

export function canSelectBatchRows(batch: NoOaBankBatch, bucket: NoOaBankBatchStatusBucket) {
  return bucket === "unsubmitted"
    && isUnsubmittedDraftBatch(batch)
    && batch.batchType !== "internal_transfer";
}

export function canSubmitInternalTransferBatch(batch: NoOaBankBatch, bucket: NoOaBankBatchStatusBucket) {
  return bucket === "unsubmitted"
    && isUnsubmittedDraftBatch(batch)
    && batch.canSubmit
    && batch.batchType === "internal_transfer";
}
