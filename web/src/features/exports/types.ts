export type ExportSummary = { rowCount: number };
export type ExportDownload = { blob: Blob; fileName: string; count: number };

export function validateExportCount(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new Error("导出数量不完整或无效，请重试。");
  }
  return value;
}

export function readExportCount(headers: Headers): number {
  const value = headers.get("X-Export-Count");
  if (value === null || !/^\d+$/.test(value)) {
    throw new Error("下载响应缺少有效的导出数量，请重试。");
  }
  return validateExportCount(Number(value));
}
