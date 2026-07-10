import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import PageAuditIcon from "../components/common/PageAuditIcon";


describe("PageAuditIcon", () => {
  test("does not treat an unknown page read-model status as fresh", async () => {
    const user = userEvent.setup();
    render(
      <PageAuditIcon
        ariaLabel="Audit 测试页面"
        label="测试页面"
        runAudit={vi.fn().mockResolvedValue({
          overall_status: "pass",
          audit_status: { integrity: "pass", freshness: "fresh", queue: "drained" },
          audit_contract: { database_snapshot: true, snapshot_consistency: "repeatable_read_read_only" },
          summary: { blocking_issue_sample_count: 0, issue_sample_count: 0 },
          issues: [],
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Audit 测试页面" }));

    expect(await screen.findByText(/Not fresh/)).toHaveTextContent("freshness not_fresh");
    expect(screen.queryByText(/已登记 App 内部数据完整正确/)).not.toBeInTheDocument();
  });

  test("requires a drained queue and a repeatable-read database snapshot before success", async () => {
    const user = userEvent.setup();
    const runAudit = vi
      .fn()
      .mockResolvedValueOnce({
        overall_status: "pass",
        audit_status: { integrity: "pass", freshness: "fresh", queue: "drained" },
        audit_contract: { database_snapshot: false, snapshot_consistency: "caller_managed" },
        summary: { blocking_issue_sample_count: 0, issue_sample_count: 0 },
        issues: [],
      })
      .mockResolvedValueOnce({
        overall_status: "pass",
        audit_status: { integrity: "pass", freshness: "fresh", queue: "backlog" },
        audit_contract: { database_snapshot: true, snapshot_consistency: "repeatable_read_read_only" },
        summary: { blocking_issue_sample_count: 0, issue_sample_count: 0 },
        issues: [],
      });
    render(
      <PageAuditIcon
        ariaLabel="Audit 测试页面"
        label="测试页面"
        readModelStatus="fresh"
        runAudit={runAudit}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Audit 测试页面" }));
    expect(await screen.findByText(/consistency snapshot unavailable/)).toHaveAttribute("data-tone", "danger");

    await user.click(screen.getByRole("button", { name: "Audit 测试页面" }));
    expect(await screen.findByText(/queue backlog/)).toHaveAttribute("data-tone", "warning");
    expect(screen.queryByText(/已登记 App 内部数据完整正确/)).not.toBeInTheDocument();
  });

  test("shows the bounded App-internal guarantee only when every proof gate passes", async () => {
    const user = userEvent.setup();
    render(
      <PageAuditIcon
        ariaLabel="Audit 测试页面"
        label="测试页面"
        readModelStatus="fresh"
        runAudit={vi.fn().mockResolvedValue({
          overall_status: "pass",
          audit_status: { integrity: "pass", freshness: "fresh", queue: "drained" },
          audit_contract: { database_snapshot: true, snapshot_consistency: "repeatable_read_read_only" },
          summary: { blocking_issue_sample_count: 0, issue_sample_count: 0 },
          issues: [],
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Audit 测试页面" }));

    expect(await screen.findByText(/已登记 App 内部数据完整正确/)).toHaveTextContent("配对关系完整正确");
  });

  test("labels capped issue results as samples and exposes truncation", async () => {
    const user = userEvent.setup();
    render(
      <PageAuditIcon
        ariaLabel="Audit 测试页面"
        label="测试页面"
        readModelStatus="fresh"
        runAudit={vi.fn().mockResolvedValue({
          overall_status: "issues_found",
          audit_status: { integrity: "issues_found", freshness: "fresh", queue: "drained" },
          summary: {
            blocking_issue_sample_count: 50,
            issue_sample_count: 50,
            issue_samples_truncated: true,
          },
          issues: [],
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Audit 测试页面" }));

    const status = await screen.findByText(/integrity issues_found/);
    expect(status).toHaveTextContent("blocking samples 50+");
    expect(status).toHaveTextContent("issue samples 50+");
  });
});
