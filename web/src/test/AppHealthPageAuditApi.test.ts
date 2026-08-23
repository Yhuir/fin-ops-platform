import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchAppHealthSystemAudit } from "../features/appHealth/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("app health System Audit API", () => {
  test("requests only the centralized System Audit endpoint", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      expect(url).toContain("/api/operations/app-health/page-audit?page=app-health-operations");
      return new Response(JSON.stringify({
        mode: "app-health-system-audit",
        page_key: "app-health-operations",
        domain_key: "app_health_operations",
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

    const payload = await fetchAppHealthSystemAudit();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(payload).toMatchObject({
      mode: "app-health-system-audit",
      page_key: "app-health-operations",
      domain_key: "app_health_operations",
      overall_status: "pass",
    });
  });
});
