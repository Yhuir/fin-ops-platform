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

describe("AppHealthOperationsPage", () => {
  test("renders the read-only operations dashboard", async () => {
    const fetchMock = renderOperationsPage();

    expect(await screen.findByRole("heading", { name: "AppHealth 运维状态" }, { timeout: PAGE_TIMEOUT })).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/operations/app-health-dashboard"))).toBe(true);
    });

    const data = await screen.findByTestId("app-health-data", {}, { timeout: PAGE_TIMEOUT });
    expect(data).toHaveTextContent("数据");
    expect(data).toHaveTextContent("流水");
    expect(data).toHaveTextContent("128");
    expect(data).toHaveTextContent("发票");
    expect(data).toHaveTextContent("256");
    expect(data).toHaveTextContent("OA 解析");
    expect(data).toHaveTextContent("ETC");

    const requests = screen.getByTestId("app-health-requests");
    expect(requests).toHaveTextContent("请求");
    expect(requests).toHaveTextContent("GET /api/workbench/summary");
    expect(requests).toHaveTextContent("640 ms");
    expect(requests).toHaveTextContent("260 ms");
    expect(within(requests).getByText("640 ms").closest("td")).toHaveAttribute("data-tone", "yellow");
    expect(within(requests).getByText("260 ms").closest("td")).toHaveAttribute("data-tone", "green");

    const runtime = screen.getByTestId("app-health-runtime");
    expect(runtime).toHaveTextContent("后台");
    expect(runtime).toHaveTextContent("pending");
    expect(runtime).toHaveTextContent("finops.workbench.read_model.refresh");
    expect(runtime).toHaveTextContent("workbench");
    expect(runtime).toHaveTextContent("runtime-worker");

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

    expect(await screen.findByText("当前账号没有管理员权限，不能查看 AppHealth 运维状态。", {}, { timeout: PAGE_TIMEOUT })).toBeInTheDocument();
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
    expect(screen.getByTestId("app-health-data")).toHaveTextContent("128");
  });
});
