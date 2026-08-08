import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import OaPendingPaymentAuditIcon from "../components/oaPendingPayments/OaPendingPaymentAuditIcon";


function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function auditPayload(overrides: Record<string, unknown> = {}) {
  return {
    overall_status: "pass",
    audit_status: { integrity: "pass", freshness: "fresh", queue: "drained" },
    audit_contract: {
      database_snapshot: true,
      snapshot_consistency: "repeatable_read_read_only",
      proof_availability: "ready",
      contract_revision: "page-audit-contract.v13",
    },
    summary: { blocking_issue_sample_count: 0, issue_sample_count: 0 },
    issues: [],
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("OA pending payment Audit", () => {
  test("shows the bounded Chinese success copy", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(auditPayload())));
    const user = userEvent.setup();
    render(<OaPendingPaymentAuditIcon />);

    await user.click(screen.getByRole("button", { name: "Audit OA 待付款核对" }));

    expect(await screen.findByText("Audit 通过 · App 内部数据一致")).toHaveAttribute("data-tone", "success");
  });

  test("shows issue count and at most three deduplicated Chinese samples", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(auditPayload({
      overall_status: "issues_found",
      audit_status: { integrity: "issues_found", freshness: "fresh", queue: "drained" },
      summary: { blocking_issue_sample_count: 3, issue_sample_count: 3 },
      issues: [
        { code: "oa_pending_payments_canonical_source_version_mismatch", scope_key: "2026-06", subject_id: "oa-1" },
        { code: "oa_pending_payments_canonical_source_version_mismatch", scope_key: "2026-06", subject_id: "oa-1" },
        { code: "oa_pending_payments_relation_edge_mismatch", scope_key: "2026-06", subject_id: "case-1" },
        { code: "oa_pending_payments_missing_canonical_fact", scope_key: "2026-07" },
        { code: "oa_pending_payments_duplicate_canonical_identity", scope_key: "2026-07", subject_id: "oa-2" },
      ],
    }))));
    const user = userEvent.setup();
    render(<OaPendingPaymentAuditIcon />);

    await user.click(screen.getByRole("button", { name: "Audit OA 待付款核对" }));

    const status = await screen.findByText(/Audit 未通过 · 发现 3 个一致性问题/);
    expect(status).toHaveTextContent("来源数据不一致");
    expect(status).toHaveTextContent("关联关系不一致");
    expect(status).toHaveTextContent("数据缺失");
    expect(status).not.toHaveTextContent("存在重复数据");
    expect(status).not.toHaveTextContent("integrity issues_found");
    expect(status).not.toHaveTextContent("blocking samples");
    expect(status).not.toHaveTextContent("oa-1");
    expect(status).not.toHaveTextContent("case-1");
    expect(status).not.toHaveTextContent("source_version_mismatch");
  });

  test("reports the audit state once without page read-model barrier retries", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      expect(url.pathname).toBe("/api/operations/app-health/page-audit");
      expect(url.searchParams.get("page")).toBe("oa-pending-payments");
      return jsonResponse(
        auditPayload({ audit_status: { integrity: "pass", freshness: "not_fresh", queue: "backlog" } }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<OaPendingPaymentAuditIcon />);

    await user.click(screen.getByRole("button", { name: "Audit OA 待付款核对" }));

    expect(await screen.findByText("Audit 校验中 · 新数据正在生成")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
