import type { WorkbenchEntityCounts } from "./types";

export function formatWorkbenchEntityCounts(counts: WorkbenchEntityCounts | null | undefined): string {
  if (!counts) return "—";
  return `OA ${counts.oa}条 · 流水 ${counts.bank}笔 · 发票 ${counts.invoice}张`;
}
