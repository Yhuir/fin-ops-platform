import { afterEach, expect, test, vi } from "vitest";
import { fetchImportHistory, fetchImportHistoryDetail } from "../features/appHealth/api";
afterEach(() => vi.unstubAllGlobals());
test("encodes history filters and reads exact batch detail", async () => {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ rows: [], row: { batch_id: "batch/1" }, pagination: { total: 0 } }), { status: 200, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
  const signal = new AbortController().signal;
  await fetchImportHistory({ page: 2, page_size: 100, batch_type: "input_invoice", status: "partial_success", search: "文件%_.xlsx", start_date: "2026-10-10", end_date: "2026-10-10" }, signal);
  const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
  expect(url.searchParams.get("search")).toBe("文件%_.xlsx");
  expect(url.searchParams.get("status")).toBe("partial_success");
  expect(url.searchParams.get("page_size")).toBe("100");
  await fetchImportHistoryDetail("batch/1");
  expect(String(fetchMock.mock.calls[1][0])).toContain("/import-history/batch%2F1");
});
