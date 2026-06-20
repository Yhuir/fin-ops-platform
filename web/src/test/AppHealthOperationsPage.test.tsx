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

    expect(styles).toMatch(/\.app-health-page\s*\{[\s\S]*gap:\s*var\(--fp-space-3\)/);
    expect(styles).toMatch(/\.app-health-title\s*\{[\s\S]*font-size:\s*var\(--fp-text-display\)/);
    expect(styles).toMatch(/\.app-health-section__header\s*\{[\s\S]*background:\s*var\(--fp-surface-muted\)/);
    expect(styles).toMatch(/\.app-health-inventory-card__value\s*\{[\s\S]*font-family:\s*var\(--fp-font-data\)/);
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
    expect(data).toHaveTextContent("发票");
    expect(data).toHaveTextContent("256");
    expect(data).toHaveTextContent("OA 解析");
    expect(data).toHaveTextContent("ETC");
    expect(within(data).getByRole("grid", { name: "银行流水来源" })).toBeInTheDocument();
    expect(within(data).getByRole("grid", { name: "发票来源" })).toBeInTheDocument();
    expect(within(data).getByRole("grid", { name: "OA来源" })).toBeInTheDocument();

    const requests = screen.getByTestId("app-health-requests");
    expectProjectSection(requests);
    expect(requests).toHaveTextContent("请求");
    expect(within(requests).getByRole("grid", { name: "请求性能" })).toBeInTheDocument();
    expect(requests).toHaveTextContent("GET /api/workbench/summary");
    expect(requests).toHaveTextContent("640 ms");
    expect(requests).toHaveTextContent("260 ms");
    expect(within(requests).getByText("640 ms").closest("td")).toHaveAttribute("data-tone", "yellow");
    expect(within(requests).getByText("260 ms").closest("td")).toHaveAttribute("data-tone", "green");

    const runtime = screen.getByTestId("app-health-runtime");
    expectProjectSection(runtime);
    expect(runtime).toHaveTextContent("后台");
    const runtimeOverview = within(runtime).getByTestId("app-health-runtime-overview");
    expect(runtimeOverview).toHaveTextContent("Read model");
    expect(runtimeOverview).toHaveTextContent("1 refreshing");
    expect(runtimeOverview).toHaveTextContent("Worker");
    expect(runtimeOverview).toHaveTextContent("active 1");
    expect(runtimeOverview).toHaveTextContent("Queue");
    expect(runtimeOverview).toHaveTextContent("4 backlog");
    expect(within(runtime).getByRole("grid", { name: "Outbox 状态" })).toBeInTheDocument();
    expect(within(runtime).getByRole("grid", { name: "RabbitMQ 队列" })).toBeInTheDocument();
    expect(within(runtime).getByRole("grid", { name: "Read Model 状态" })).toBeInTheDocument();
    expect(within(runtime).getByRole("grid", { name: "Worker 状态" })).toBeInTheDocument();
    expect(runtime).toHaveTextContent("pending");
    expect(runtime).toHaveTextContent("finops.workbench.read_model.refresh");
    expect(runtime).toHaveTextContent("workbench");
    expect(runtime).toHaveTextContent("refreshing");
    expect(runtime).toHaveTextContent("runtime-worker");
    expect(runtime).toHaveTextContent("active");
    expect(runtime).toHaveTextContent("required");

    expect(screen.queryByTestId("app-health-summary")).not.toBeInTheDocument();
    expect(screen.queryByTestId("app-health-background-jobs")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Retry/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Acknowledge/i })).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url, init]) => String(url).includes("/api/background-jobs") && String(init?.method ?? "GET").toUpperCase() === "POST"),
    ).toBe(false);
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
              { key: "standard_import", label: "普通导入", count: null, latest_synced_at: null, status: "unknown" },
              { key: "oa_attachment", label: "OA 解析", count: null, latest_synced_at: null, status: "unknown" },
              { key: "etc", label: "ETC", count: null, latest_synced_at: null, status: "unknown" },
              { key: "manual", label: "手工导入", count: null, latest_synced_at: null, status: "unknown" },
            ],
          },
          oa: {
            total_count: null,
            latest_synced_at: null,
            status: "unknown",
            sources: [
              { key: "oa_records", label: "单据", count: null, latest_synced_at: null, status: "unknown" },
              { key: "oa_items", label: "明细", count: null, latest_synced_at: null, status: "unknown" },
            ],
          },
        },
        request_performance: {
          window: { type: "process_rolling_window", sample_limit_per_endpoint: 512, reset_on_restart: true },
          endpoints: [
            {
              endpoint: "GET /api/search",
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
              event_type: "workbench.read_model.refresh",
              queue: "finops.workbench.read_model.refresh",
              messages: null,
              unacked: null,
              consumers: null,
              dlq_messages: null,
              status: "unknown",
              warning_code: "rabbitmq_metrics_unavailable",
            },
          ],
          read_models: [
            {
              key: "workbench",
              refresh_duration_ms: { p50: null, p95: null, p99: null },
              stale_count: null,
              unavailable_count: null,
              status: "unknown",
            },
          ],
          workers: [{ worker_kind: "runtime-worker", heartbeat_lag_seconds: null, status: "unknown" }],
        },
        freshness: { warnings: ["rabbitmq_metrics_unavailable"] },
      },
    });

    const data = await screen.findByTestId("app-health-data", {}, { timeout: PAGE_TIMEOUT });
    expect(within(data).getAllByText("--").length).toBeGreaterThan(2);
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
                  { key: "standard_import", label: "普通导入", count: 180, latest_synced_at: "2026-05-23T09:44:00+08:00", status: "available" },
                  { key: "oa_attachment", label: "OA 解析", count: 40, latest_synced_at: "2026-05-23T09:48:00+08:00", status: "available" },
                  { key: "etc", label: "ETC", count: 30, latest_synced_at: "2026-05-23T09:30:00+08:00", status: "available" },
                  { key: "manual", label: "手工导入", count: 6, latest_synced_at: "2026-05-23T09:20:00+08:00", status: "available" },
                ],
              },
              oa: {
                total_count: 72,
                latest_synced_at: "2026-05-23T09:45:00+08:00",
                status: "available",
                sources: [
                  { key: "oa_records", label: "单据", count: 72, latest_synced_at: "2026-05-23T09:45:00+08:00", status: "available" },
                  { key: "oa_items", label: "明细", count: 316, latest_synced_at: "2026-05-23T09:45:00+08:00", status: "available" },
                ],
              },
            },
            request_performance: {
              window: { type: "process_rolling_window", sample_limit_per_endpoint: 512, reset_on_restart: true },
              endpoints: [],
            },
            runtime_performance: {
              outbox: { pending_count: 3, publishing_count: 0, failed_count: 0, publish_failed_count: 0, oldest_pending_age_seconds: 42, status: "available" },
              queues: [],
              read_models: [],
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

    await user.click(screen.getByRole("button", { name: "刷新" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("dashboard failed"));
    expect(screen.getByRole("alert")).toHaveClass("app-health-notice");
    expect(screen.getByRole("alert")).not.toHaveClass("MuiAlert-root");
    expect(screen.getByTestId("app-health-data")).toHaveTextContent("128");
  });
});
