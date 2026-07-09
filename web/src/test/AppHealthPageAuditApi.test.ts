import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchPageBusinessAudit } from "../features/appHealth/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("app health page business audit API", () => {
  test("requests the dedicated page audit endpoint with the domain key", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      expect(url).toContain("/api/operations/app-health/page-audit?domain=bank_details");
      return new Response(JSON.stringify({
        mode: "page-business-read-model-audit",
        domain_key: "bank_details",
        overall_status: "pass",
        summary: {
          blocking_issue_count: 0,
          issue_count: 0,
        },
        issues: [],
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const payload = await fetchPageBusinessAudit("bank_details");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(payload).toMatchObject({
      mode: "page-business-read-model-audit",
      domain_key: "bank_details",
      overall_status: "pass",
    });
  });
});
