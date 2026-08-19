import { readFileSync } from "node:fs";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../app/App";
import { installMockApiFetch } from "./apiMock";

const PAGE_TIMEOUT = 3000;

function renderOperationsPage(options: Parameters<typeof installMockApiFetch>[0] = {}) {
  window.history.pushState({}, "", "/operations/app-health");
  const fetchMock = installMockApiFetch({
    sessionAccessTier: "admin",
    sessionUsername: "admin.ops",
    sessionDisplayName: "运维管理员",
    ...options,
  });
  render(<App />);
  return fetchMock;
}

function expectProjectNotice(message: HTMLElement) {
  const notice = message.closest('[role="alert"], [role="status"]');
  expect(notice).not.toBeNull();
  const noticeRoot = notice as HTMLElement;
  expect(noticeRoot).toHaveClass("app-health-notice");
  expect(noticeRoot).not.toHaveClass("MuiAlert-root");
  return noticeRoot;
}

function expectProjectSection(section: HTMLElement) {
  expect(section).toHaveClass("app-health-section");
  expect(section).not.toHaveClass("MuiBox-root");
}

describe("AppHealthOperationsPage", () => {
  test("keeps AppHealth premium visual treatment compact and scoped", () => {
    const styles = readFileSync("src/app/styles.css", "utf8");

    expect(styles).toMatch(/\.app-health-page\s*\{[^}]*gap:\s*var\(--fp-space-3\)[^}]*padding:\s*var\(--fp-space-4\)/s);
    expect(styles).toMatch(/\.app-health-title\s*\{[\s\S]*font-size:\s*var\(--fp-text-display\)/);
    expect(styles).toMatch(/\.app-health-section__header\s*\{[\s\S]*background:\s*var\(--fp-surface-muted\)/);
    expect(styles).toMatch(/\.app-health-inventory-table__number,[\s\S]*font-family:\s*var\(--fp-font-data\)/);
    expect(styles).toMatch(/\.app-health-audit-grid\s*\{[\s\S]*grid-template-columns:\s*repeat\(6,\s*minmax\(0,\s*1fr\)\)/);
    expect(styles).toMatch(/\.app-health-refresh-button\s*\{[\s\S]*transition:[\s\S]*border-color var\(--motion-fast\) var\(--ease-standard\)/);
  });

  test("renders the read-only operations dashboard", async () => {
    const fetchMock = renderOperationsPage();

    expect(await screen.findByRole("heading", { name: "AppHealth 运维状态" }, { timeout: PAGE_TIMEOUT })).toBeInTheDocument();
    const page = screen.getByTestId("app-health-page");
    expect(page).toHaveClass("app-health-page");
    expect(page).not.toHaveClass("MuiStack-root");
    const header = screen.getByTestId("app-health-header");
    expect(header).toHaveClass("app-health-header");
    expect(header).not.toHaveClass("MuiStack-root");
    const refreshButton = screen.getByRole("button", { name: "刷新" });
    expect(refreshButton).toHaveClass("app-health-refresh-button");
    expect(refreshButton).not.toHaveClass("MuiIconButton-root");
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/operations/app-health-dashboard"))).toBe(true);
    });

    const data = await screen.findByTestId("app-health-data", {}, { timeout: PAGE_TIMEOUT });
    expectProjectSection(data);
    expect(data).toHaveTextContent("数据");
    expect(data).toHaveTextContent("流水");
    expect(data).toHaveTextContent("128");
    const invoiceStats = within(data).getByRole("grid", { name: "发票统计" });
    expect(invoiceStats).toHaveTextContent("按类型分");
    expect(invoiceStats).toHaveTextContent("进项发票236");
    expect(invoiceStats).toHaveTextContent("销项发票20");
    expect(invoiceStats).toHaveTextContent("按导入方式分");
    expect(invoiceStats).toHaveTextContent("手工导入251");
    expect(invoiceStats).toHaveTextContent("OA 解析仅新增入池5");
    expect(within(invoiceStats).getAllByText("256")).toHaveLength(4);
    expect(invoiceStats).not.toHaveTextContent("40");
    expect(invoiceStats).not.toHaveTextContent("口径未闭合");
    expect(data).not.toHaveTextContent("普通导入");
    expect(data).not.toHaveTextContent("ETC");
    const oaStats = within(data).getByRole("grid", { name: "OA 状态" });
    expect(oaStats).toHaveTextContent("已完成 OA61");
    expect(oaStats).toHaveTextContent("进行中 OA11");
    expect(oaStats).not.toHaveTextContent("单据");
    expect(oaStats).not.toHaveTextContent("明细");
    const recentImportEvents = within(data).getByRole("grid", { name: "最近导入记录" });
    expect(recentImportEvents).toBeInTheDocument();
    expect(data).toHaveTextContent("bank-5.xlsx");
    expect(data).toHaveTextContent("invoice-4.xlsx");
    expect(recentImportEvents).toHaveTextContent("已完成");
    expect(recentImportEvents).not.toHaveTextContent("OA 同步");
    expect(recentImportEvents).not.toHaveTextContent("OA 附件解析");
    expect(data).not.toHaveTextContent("bank-6.xlsx");
    expect(within(data).getByRole("grid", { name: "银行流水来源" })).toBeInTheDocument();

    const audit = screen.getByTestId("app-health-system-audit");
    expectProjectSection(audit);
    expect(audit).toHaveTextContent("System Audit");
    expect(audit).toHaveTextContent("App 内部合同");
    expect(audit).not.toHaveTextContent("0 页 App 内部合同");
    expect(audit).toHaveTextContent("未验证");
    const auditButton = within(audit).getByRole("button", { name: "Audit 全系统 App 内部合同" });
    expect(auditButton).toHaveClass("app-health-audit-button");
    await userEvent.click(auditButton);
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/operations/app-health/page-audit?page=app-health-operations"))).toBe(true);
    });
    expect(audit).toHaveTextContent("pass");
    expect(audit).toHaveTextContent("18 页 App 内部合同");
    expect(audit).toHaveTextContent("业务页面通过");
    expect(audit).toHaveTextContent("App 内部 pass");
    expect(audit).toHaveTextContent("外部域 unknown");
    expect(audit).toHaveTextContent("bank unknown");
    expect(audit).toHaveTextContent("oa unknown");
    expect(audit).toHaveTextContent("仅证明该只读数据库快照内的已登记 App 内部合同");
    expect(audit).toHaveTextContent("Blocking samples");
    expect(within(audit).getAllByText("16").length).toBeGreaterThanOrEqual(1);

    await userEvent.click(refreshButton);
    await waitFor(() => {
      expect(audit).toHaveTextContent("未验证");
    });
    expect(within(audit).queryByText("App 内部 pass")).not.toBeInTheDocument();

    const requests = screen.getByTestId("app-health-requests");
    expectProjectSection(requests);
    expect(requests).toHaveTextContent("请求");
    expect(within(requests).getByRole("grid", { name: "请求性能" })).toBeInTheDocument();
    expect(requests).toHaveTextContent("GET /api/workbench");
    expect(requests).toHaveTextContent("640 ms");
    expect(requests).toHaveTextContent("260 ms");
    expect(within(requests).getByText("640 ms").closest("td")).toHaveAttribute("data-tone", "yellow");
    expect(within(requests).getByText("260 ms").closest("td")).toHaveAttribute("data-tone", "green");

    const runtime = screen.getByTestId("app-health-runtime");
    expectProjectSection(runtime);
    expect(runtime).toHaveTextContent("后台");
    const runtimeOverview = within(runtime).getByTestId("app-health-runtime-overview");
    expect(runtimeOverview).toHaveTextContent("Worker");
    expect(runtimeOverview).toHaveTextContent("active 1");
    expect(runtimeOverview).toHaveTextContent("Queue");
    expect(runtimeOverview).toHaveTextContent("4 backlog");
    expect(within(runtime).getByRole("grid", { name: "Outbox 状态" })).toBeInTheDocument();
    expect(within(runtime).getByRole("grid", { name: "RabbitMQ 队列" })).toBeInTheDocument();
    expect(within(runtime).getByRole("grid", { name: "Worker 状态" })).toBeInTheDocument();
    expect(runtime).toHaveTextContent("pending");
    expect(runtime).toHaveTextContent("runtime-worker");
    expect(runtime).toHaveTextContent("active");
    expect(runtime).toHaveTextContent("required");

    await userEvent.click(within(data).getByRole("button", { name: "查看全部导入历史" }));
    const drawer = await screen.findByRole("dialog", { name: "导入历史" }, { timeout: PAGE_TIMEOUT });
    expect(within(drawer).getByRole("grid", { name: "全部导入历史" })).toBeInTheDocument();
    expect(drawer).toHaveTextContent("bank-6.xlsx");
    expect(drawer).not.toHaveTextContent("OA 同步");
    expect(drawer).not.toHaveTextContent("OA 附件解析");
    const withdrawButton = within(drawer).getByRole("button", { name: "撤回 bank-6.xlsx" });
    await userEvent.click(withdrawButton);
    const confirmDialog = await screen.findByRole("dialog", { name: "撤回流水导入" });
    expect(confirmDialog).toHaveTextContent("OA、发票及导入/操作审计记录不会删除");
    await userEvent.click(within(confirmDialog).getByRole("button", { name: "确认撤回" }));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url, init]) => (
        String(url).includes("/api/imports/bank-transaction-batches/bank-6/withdraw")
        && String(init?.method).toUpperCase() === "POST"
      ))).toBe(true);
    });
    expect(await within(drawer).findByText("已撤回 8 条银行流水；OA、发票和导入审计记录已保留。")).toBeInTheDocument();

    expect(screen.queryByTestId("app-health-summary")).not.toBeInTheDocument();
    expect(screen.queryByTestId("app-health-background-jobs")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Retry/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Acknowledge/i })).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url, init]) => String(url).includes("/api/background-jobs") && String(init?.method ?? "GET").toUpperCase() === "POST"),
    ).toBe(false);
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url).includes("/api/operations/app-health/page-audit?page=app-health-operations")
          && String(init?.method ?? "GET").toUpperCase() !== "GET",
      ),
    ).toBe(false);
  });

  test("does not label an unversioned or non-snapshot audit as pass", async () => {
    renderOperationsPage({
      appHealthSystemAudit: {
        overall_status: "pass",
        audit_status: { integrity: "pass", freshness: "fresh", queue: "drained" },
        audit_contract: { database_snapshot: false, snapshot_consistency: "caller_managed" },
        summary: { blocking_issue_sample_count: 0, error_sample_count: 0 },
        issues: [],
      },
    });

    const audit = await screen.findByTestId("app-health-system-audit", {}, { timeout: PAGE_TIMEOUT });
    await userEvent.click(within(audit).getByRole("button", { name: "Audit 全系统 App 内部合同" }));

    expect((await within(audit).findByText("proof_unavailable")).closest(".finance-status-tag")).toHaveAttribute(
      "data-tone",
      "danger",
    );
    expect(within(audit).queryByText("pass")).not.toBeInTheDocument();
  });

  test("shows versioned external domain pass as an as-of claim instead of extending it to live truth", async () => {
    renderOperationsPage({
      appHealthSystemAudit: {
        overall_status: "pass",
        audit_status: { integrity: "pass", freshness: "fresh", queue: "drained", external: "pass" },
        audit_contract: {
          database_snapshot: true,
          snapshot_consistency: "repeatable_read_read_only",
          proof_availability: "ready",
          contract_revision: "page-audit-contract.v22",
        },
        summary: {
          registered_page_count: 18,
          audited_business_page_count: 16,
          passed_business_page_count: 16,
          database_internal_contracts: "pass",
          end_to_end_source_truth: "proven_as_of_external_evidence",
          blocking_issue_sample_count: 0,
          issue_sample_count: 0,
        },
        issues: [],
        database_system_snapshot: {
          system_audit_id: "system-audit:external-pass",
          snapshot_identity: "100:100:",
          snapshot_generated_at: "2026-07-11T12:00:00Z",
          database_snapshot: true,
        },
        external_evidence: {
          status: "pass",
          end_to_end_source_truth: "proven_as_of_external_evidence",
          claim_boundary: "仅证明外部 evidence observed_at 与当前不可变 App 快照之间的精确相等；不证明后续变化。",
          summary: { required_domain_count: 4, passed_domain_count: 4, failed_domain_count: 0, unknown_domain_count: 0 },
          domains: ["bank", "oa", "invoice", "etc"].map((domain) => ({
            domain,
            status: "pass",
            observed_at: "2026-07-11T11:59:00Z",
          })),
        },
      },
    });

    const audit = await screen.findByTestId("app-health-system-audit", {}, { timeout: PAGE_TIMEOUT });
    await userEvent.click(within(audit).getByRole("button", { name: "Audit 全系统 App 内部合同" }));

    expect((await within(audit).findByText("外部证据 pass")).closest(".finance-status-tag")).toHaveAttribute("data-tone", "success");
    expect(audit).toHaveTextContent("bank pass");
    expect(audit).toHaveTextContent("不证明后续变化");
    expect(audit).not.toHaveTextContent("外部域 unknown4");
  });

  test("blocks non admin users without fetching dashboard data", async () => {
    const fetchMock = renderOperationsPage({
      sessionAccessTier: "full_access",
      sessionUsername: "finance.user",
      sessionDisplayName: "财务用户",
    });

    const permissionMessage = await screen.findByText("当前账号没有管理员权限，不能查看 AppHealth 运维状态。", {}, { timeout: PAGE_TIMEOUT });
    expectProjectNotice(permissionMessage);
    expect(screen.queryByTestId("app-health-data")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/operations/app-health-dashboard"))).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/operations/app-health/page-audit?page=app-health-operations"))).toBe(false);
  });

  test("renders unknown metrics as dashes instead of zero", async () => {
    renderOperationsPage({
      appHealthDashboard: {
        generated_at: "2026-05-23T10:00:00+08:00",
        data_inventory: {
          bank: {
            total_count: null,
            latest_synced_at: null,
            status: "unknown",
            sources: [{ key: "bank_transactions", label: "银行流水", count: null, latest_synced_at: null, status: "unknown" }],
          },
          invoice: {
            total_count: null,
            latest_synced_at: null,
            status: "unknown",
            sources: [
              { key: "manual", label: "手工导入", count: null, latest_synced_at: null, status: "unknown" },
              { key: "input_invoice", label: "进项发票", count: null, latest_synced_at: null, status: "unknown" },
              { key: "output_invoice", label: "销项发票", count: null, latest_synced_at: null, status: "unknown" },
              { key: "oa_attachment", label: "OA 解析", count: null, supplementary_count: null, latest_synced_at: null, status: "unknown" },
            ],
          },
          oa: {
            total_count: null,
            latest_synced_at: null,
            status: "unknown",
            sources: [
              { key: "oa_records", label: "单据", count: null, latest_synced_at: null, status: "unknown" },
              { key: "oa_records_completed", label: "已完成 OA", count: null, latest_synced_at: null, status: "unknown" },
              { key: "oa_records_in_progress", label: "进行中 OA", count: null, latest_synced_at: null, status: "unknown" },
              { key: "oa_items", label: "明细", count: null, latest_synced_at: null, status: "unknown" },
            ],
          },
          import_events: [],
        },
        request_performance: {
          window: { type: "process_rolling_window", sample_limit_per_endpoint: 512, reset_on_restart: true },
          endpoints: [
            {
              endpoint: "GET /api/workbench",
              sample_count: 0,
              last_status_code: null,
              duration_ms: { p50: null, p95: null, p99: null },
              database_duration_ms: { p50: null, p95: null, p99: null },
              connection_acquire_ms: { p50: null, p95: null, p99: null },
              sql_execute_fetch_ms: { p50: null, p95: null, p99: null },
              database_query_count: { p50: null, p95: null, p99: null },
            },
          ],
        },
        runtime_performance: {
          outbox: {
            pending_count: null,
            publishing_count: null,
            failed_count: null,
            publish_failed_count: null,
            oldest_pending_age_seconds: null,
            status: "unknown",
            warning_code: "outbox_metrics_unavailable",
          },
          queues: [
            {
              event_type: "oa.sync",
              queue: "finops.oa.sync",
              messages: null,
              unacked: null,
              consumers: null,
              dlq_messages: null,
              status: "unknown",
              warning_code: "rabbitmq_metrics_unavailable",
            },
          ],
          workers: [{ worker_kind: "runtime-worker", heartbeat_lag_seconds: null, status: "unknown" }],
        },
        freshness: { warnings: ["rabbitmq_metrics_unavailable"] },
      },
    });

    const data = await screen.findByTestId("app-health-data", {}, { timeout: PAGE_TIMEOUT });
    expect(within(data).getAllByText("--").length).toBeGreaterThan(2);
    expect(within(data).getByRole("grid", { name: "发票统计" })).not.toHaveTextContent("口径未闭合");
    expect(screen.getByTestId("app-health-requests")).toHaveTextContent("--");
    expect(within(screen.getByTestId("app-health-requests")).getAllByText("--")[0].closest("td")).toHaveAttribute("data-tone", "unknown");
    expect(screen.getByTestId("app-health-runtime")).toHaveTextContent("--");
  });

  test("keeps the current dashboard visible when refresh fails", async () => {
    const user = userEvent.setup();
    renderOperationsPage({
      appHealthDashboardSequence: [
        {
          body: {
            generated_at: "2026-05-23T10:00:00+08:00",
            data_inventory: {
              bank: {
                total_count: 128,
                latest_synced_at: "2026-05-23T09:50:00+08:00",
                status: "available",
                sources: [{ key: "bank_transactions", label: "银行流水", count: 128, latest_synced_at: "2026-05-23T09:50:00+08:00", status: "available" }],
              },
              invoice: {
                total_count: 256,
                latest_synced_at: "2026-05-23T09:48:00+08:00",
                status: "available",
                sources: [
                  { key: "manual", label: "手工导入", count: 6, latest_synced_at: "2026-05-23T09:20:00+08:00", status: "available" },
                  { key: "input_invoice", label: "进项发票", count: 236, latest_synced_at: "2026-05-23T09:46:00+08:00", status: "available" },
                  { key: "output_invoice", label: "销项发票", count: 20, latest_synced_at: "2026-05-23T09:42:00+08:00", status: "available" },
                  { key: "oa_attachment", label: "OA 解析", count: 40, supplementary_count: 5, latest_synced_at: "2026-05-23T09:48:00+08:00", status: "available" },
                ],
              },
              oa: {
                total_count: 72,
                latest_synced_at: "2026-05-23T09:45:00+08:00",
                status: "available",
                sources: [
                  { key: "oa_records", label: "单据", count: 72, latest_synced_at: "2026-05-23T09:45:00+08:00", status: "available" },
                  { key: "oa_records_completed", label: "已完成 OA", count: 61, latest_synced_at: "2026-05-23T09:45:00+08:00", status: "available" },
                  { key: "oa_records_in_progress", label: "进行中 OA", count: 11, latest_synced_at: "2026-05-23T09:45:00+08:00", status: "available" },
                  { key: "oa_items", label: "明细", count: 316, latest_synced_at: "2026-05-23T09:45:00+08:00", status: "available" },
                ],
              },
              import_events: [],
            },
            request_performance: {
              window: { type: "process_rolling_window", sample_limit_per_endpoint: 512, reset_on_restart: true },
              endpoints: [],
            },
            runtime_performance: {
              outbox: { pending_count: 3, publishing_count: 0, failed_count: 0, publish_failed_count: 0, oldest_pending_age_seconds: 42, status: "available" },
              queues: [],
              workers: [],
            },
            freshness: { warnings: [] },
          },
        },
        { status: 500, body: { message: "dashboard failed" } },
      ],
    });

    const data = await screen.findByTestId("app-health-data", {}, { timeout: PAGE_TIMEOUT });
    expect(data).toHaveTextContent("128");
    expect(within(data).getByRole("grid", { name: "发票统计" })).toHaveTextContent("口径未闭合 · 差异 245");

    await user.click(screen.getByRole("button", { name: "刷新" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("dashboard failed"));
    expect(screen.getByRole("alert")).toHaveClass("app-health-notice");
    expect(screen.getByRole("alert")).not.toHaveClass("MuiAlert-root");
    expect(screen.getByTestId("app-health-data")).toHaveTextContent("128");
  });
});
