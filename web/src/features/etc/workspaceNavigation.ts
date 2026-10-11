import type { EtcBusinessBatchBucket } from "./types";

// Route context is navigation only; APIs still validate the selected task and version.
export function etcImportPath(taskId: string, batchId: string, bucket: EtcBusinessBatchBucket, page: number) {
  const params = new URLSearchParams({ from: "etc-tickets", etc_task: taskId, batch: batchId, bucket, page: String(page) });
  return `/imports/etc-invoices?${params}`;
}

export function etcReturnContext(params: URLSearchParams) {
  if (!params.has("batch")) return null;
  const batchId = params.get("batch")!;
  const bucket = params.get("bucket");
  const rawPage = params.get("page") ?? "";
  if (!batchId || !["unsubmitted", "staged", "submitted"].includes(bucket ?? "") || !/^[1-9]\d*$/.test(rawPage) || !Number.isSafeInteger(Number(rawPage))) {
    throw new Error("ETC 批次导航参数无效。");
  }
  return { batchId, bucket: bucket as EtcBusinessBatchBucket, page: Number(rawPage) };
}

export function etcReturnPath(params: URLSearchParams) {
  const context = etcReturnContext(params);
  if (!context) return "/etc-tickets";
  return `/etc-tickets?${new URLSearchParams({ batch: context.batchId, bucket: context.bucket, page: String(context.page) })}`;
}
