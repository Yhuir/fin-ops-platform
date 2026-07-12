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
          audit_contract: {
            database_snapshot: true,
            snapshot_consistency: "repeatable_read_read_only",
            proof_availability: "ready",
            contract_revision: "page-audit-contract.v9",
          },
          summary: { blocking_issue_sample_count: 0, issue_sample_count: 0 },
          issues: [],
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Audit 测试页面" }));

    expect(await screen.findByText(/Not fresh/)).toHaveTextContent("freshness not_fresh");
    expect(screen.queryByText(/已登记 App 内部合同一致/)).not.toBeInTheDocument();
  });

  test("uses the Audit snapshot freshness gate for a registered direct-canonical page", async () => {
    const user = userEvent.setup();
    render(
      <PageAuditIcon
        ariaLabel="Audit ETC票据管理"
        label="ETC票据管理"
        runAudit={vi.fn().mockResolvedValue({
          overall_status: "pass",
          audit_status: { integrity: "pass", freshness: "fresh", queue: "drained" },
          audit_contract: {
            database_snapshot: true,
            snapshot_consistency: "repeatable_read_read_only",
            proof_availability: "ready",
            contract_revision: "page-audit-contract.v12",
            registered_read_model_keys: [],
            relation_proof_required: true,
            relation_edge_equality: "bidirectional equality for ETC internal typed edges",
          },
          summary: { blocking_issue_sample_count: 0, issue_sample_count: 0 },
          issues: [],
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Audit ETC票据管理" }));

    expect(await screen.findByText(/已登记 App 内部合同一致/)).toHaveTextContent("已登记配对证明一致");
  });

  test("requires a drained queue and a repeatable-read database snapshot before success", async () => {
    const user = userEvent.setup();
    const runAudit = vi
      .fn()
      .mockResolvedValueOnce({
        overall_status: "pass",
        audit_status: { integrity: "pass", freshness: "fresh", queue: "drained" },
        audit_contract: {
          database_snapshot: false,
          snapshot_consistency: "caller_managed",
          proof_availability: "ready",
          contract_revision: "page-audit-contract.v9",
        },
        summary: { blocking_issue_sample_count: 0, issue_sample_count: 0 },
        issues: [],
      })
      .mockResolvedValueOnce({
        overall_status: "pass",
        audit_status: { integrity: "pass", freshness: "fresh", queue: "backlog" },
        audit_contract: {
          database_snapshot: true,
          snapshot_consistency: "repeatable_read_read_only",
          proof_availability: "ready",
          contract_revision: "page-audit-contract.v9",
        },
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
    expect(screen.queryByText(/已登记 App 内部合同一致/)).not.toBeInTheDocument();
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
          audit_contract: {
            database_snapshot: true,
            snapshot_consistency: "repeatable_read_read_only",
            proof_availability: "ready",
            contract_revision: "page-audit-contract.v9",
          },
          summary: { blocking_issue_sample_count: 0, issue_sample_count: 0 },
          issues: [],
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Audit 测试页面" }));

    expect(await screen.findByText(/已登记 App 内部合同一致/)).toHaveTextContent("已登记配对证明一致");
  });

  test("does not claim relation proof for a page that does not consume relations", async () => {
    const user = userEvent.setup();
    render(
      <PageAuditIcon
        ariaLabel="Audit 税金抵扣"
        label="税金抵扣"
        readModelStatus="fresh"
        runAudit={vi.fn().mockResolvedValue({
          overall_status: "pass",
          audit_status: { integrity: "pass", freshness: "fresh", queue: "drained" },
          audit_contract: {
            database_snapshot: true,
            snapshot_consistency: "repeatable_read_read_only",
            proof_availability: "ready",
            contract_revision: "page-audit-contract.v11",
            relation_proof_required: false,
            relation_edge_equality: "not_applicable: tax-offset does not consume or display Workbench relations",
          },
          summary: { blocking_issue_sample_count: 0, issue_sample_count: 0 },
          issues: [],
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Audit 税金抵扣" }));

    const status = await screen.findByText(/本页面不消费配对关系/);
    expect(status).not.toHaveTextContent("已登记配对证明一致");
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

  test("fails closed when the proof contract is unavailable or unversioned", async () => {
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

    expect(await screen.findByText(/proof contract unavailable or unversioned/)).toHaveAttribute("data-tone", "danger");
    expect(screen.queryByText(/已登记 App 内部合同一致/)).not.toBeInTheDocument();
  });
});
