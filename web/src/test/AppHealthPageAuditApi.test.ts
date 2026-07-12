import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchPageAudit } from "../features/appHealth/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("app health page business audit API", () => {
  test("requests the dedicated page audit endpoint with the page key", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      expect(url).toContain("/api/operations/app-health/page-audit?page=bank-details");
      return new Response(JSON.stringify({
        mode: "page-business-read-model-audit",
        page_key: "bank-details",
        domain_key: "bank_details",
        overall_status: "pass",
        audit_status: { integrity: "pass", freshness: "fresh", queue: "drained" },
        summary: {
          blocking_issue_sample_count: 0,
          issue_sample_count: 0,
        },
        issues: [],
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const payload = await fetchPageAudit("bank-details");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(payload).toMatchObject({
      mode: "page-business-read-model-audit",
      page_key: "bank-details",
      domain_key: "bank_details",
      overall_status: "pass",
    });
  });
});
