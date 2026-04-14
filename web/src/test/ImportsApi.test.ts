import { afterEach, describe, expect, test, vi } from "vitest";

import {
  confirmImportFiles,
  fetchImportSession,
  previewImportFiles,
  retryImportFiles,
} from "../features/imports/api";

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
  document.cookie = "Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

describe("imports api", () => {
  test("sends Authorization header and credentials for preview uploads", async () => {
    document.cookie = "Admin-Token=mock-cookie-token";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          session: {
            id: "import_session_0001",
            imported_by: "web_finance_user",
            file_count: 1,
            status: "preview_ready",
            created_at: "2026-04-14T10:00:00Z",
          },
          files: [
            {
              id: "import_file_0001",
              file_name: "销项发票.xlsx",
              template_code: "invoice_export",
              batch_type: "output_invoice",
              status: "preview_ready",
              message: "预览成功",
              row_count: 1,
              success_count: 1,
              error_count: 0,
              duplicate_count: 0,
              suspected_duplicate_count: 0,
              updated_count: 0,
              row_results: [],
            },
          ],
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );
    global.fetch = fetchMock as typeof fetch;

    await previewImportFiles([
      new File(["demo"], "销项发票.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
    ]);

    expect(fetchMock).toHaveBeenCalledWith(
      "/imports/files/preview",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.any(Headers),
      }),
    );
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer mock-cookie-token");
    expect(init.body).toBeInstanceOf(FormData);
  });

  test("sends Authorization header and credentials for json import actions", async () => {
    document.cookie = "Admin-Token=mock-cookie-token";
    const fetchMock = vi.fn().mockImplementation(async () =>
      new Response(
        JSON.stringify({
          session: {
            id: "import_session_0001",
            imported_by: "web_finance_user",
            file_count: 1,
            status: "preview_ready",
            created_at: "2026-04-14T10:00:00Z",
          },
          files: [],
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      )
    );
    global.fetch = fetchMock as typeof fetch;

    await retryImportFiles("import_session_0001", ["import_file_0001"], {
      import_file_0001: { templateCode: "invoice_export", batchType: "output_invoice" },
    });
    await confirmImportFiles("import_session_0001", ["import_file_0001"]);
    await fetchImportSession("import_session_0001");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/imports/files/retry",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.any(Headers),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/imports/files/confirm",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.any(Headers),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/imports/files/sessions/import_session_0001",
      expect.objectContaining({
        method: "GET",
        credentials: "include",
        headers: expect.any(Headers),
      }),
    );

    fetchMock.mock.calls.forEach(([, init]) => {
      const headers = init?.headers as Headers;
      expect(headers.get("Authorization")).toBe("Bearer mock-cookie-token");
    });
  });
});
