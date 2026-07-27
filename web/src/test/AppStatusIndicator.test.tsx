import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";

const globalAppStatus = {
  version: 1,
  generated_at: "2026-06-04T10:00:00+08:00",
  overall: {
    level: "busy",
    color: "yellow",
    reason: "后台任务处理中",
    blocks_mutations: false,
  },
  domains: [
    {
      key: "bank_details",
      label: "银行明细",
      route: "/bank-details",
      level: "ok",
      status: "ready",
      reason: "银行明细已同步",
      details: [],
      read_models: [],
      workers: [],
      job_ids: [],
      updated_at: "2026-06-04T10:00:00+08:00",
    },
    {
      key: "imports_etc_invoices",
      label: "ETC发票导入",
      route: "/imports/etc-invoices",
      level: "busy",
      status: "refreshing",
      reason: "ETC发票导入正在同步",
      details: [],
      read_models: [],
      workers: ["import"],
      job_ids: ["job_etc_001"],
      updated_at: "2026-06-04T10:00:00+08:00",
    },
    {
      key: "tax_offset",
      label: "税金抵扣",
      route: "/tax-offset",
      level: "busy",
      status: "missing",
      reason: "税金抵扣正在同步",
      details: [],
      read_models: [],
      workers: [],
      job_ids: [],
      updated_at: "2026-06-04T10:00:00+08:00",
    },
    {
      key: "workbench",
      label: "关联台",
      route: "/",
      level: "busy",
      status: "failed",
      reason: "关联关系局部分片需要重试",
      details: ["2026-05: projection failed"],
      read_models: ["workbench_relation"],
      read_model_scopes: [
        {
          read_model_key: "workbench_relation",
          scope_type: "workbench_relation",
          scope_key: "all",
          status: "fresh",
          updated_at: "2026-06-04T10:03:00+08:00",
        },
        {
          read_model_key: "workbench_relation",
          scope_type: "workbench_relation",
          scope_key: "2026-05",
          status: "failed",
          last_error: "projection failed",
          updated_at: "2026-06-04T10:05:00+08:00",
        },
      ],
      workers: ["workbench-relation"],
      job_ids: [],
      updated_at: "2026-06-04T10:05:00+08:00",
    },
  ],
  runtime_summary: {
    read_models: {
      total: 4,
      fresh: 1,
      refreshing: 1,
      stale: 0,
      missing: 1,
      failed: 1,
      unavailable: 0,
      issue_count: 3,
      scope_issue_count: 1,
    },
    workers: {
      total: 4,
      required: 3,
      ready: 1,
      idle: 1,
      working: 1,
      stale: 1,
      missing: 1,
      mismatched: 0,
      unavailable: 0,
      issue_count: 2,
    },
    queue: {
      event_type_count: 3,
      pending: 2,
      processing: 1,
      failed: 3,
      backlog: 6,
    },
  },
  background_tasks: [
    {
      job_id: "job_etc_001",
      type: "etc_invoice_import",
      status: "running",
      label: "导入 ETC发票",
      short_label: "正在导入 ETC发票 3/31",
      message: "正在导入 ETC发票。",
      phase: "persist_items",
      current: 3,
      total: 31,
      percent: 10,
      affected_domains: ["imports_etc_invoices"],
      affected_scopes: ["2026-05"],
      route: "/imports/etc-invoices",
      attention: false,
      updated_at: "2026-06-04T10:00:00+08:00",
    },
    {
      job_id: "job_invoice_001",
      type: "file_import",
      status: "running",
      label: "导入发票",
      short_label: "导入发票",
      message: "正在导入发票。",
      phase: "persist_items",
      current: 210,
      total: 500,
      percent: 42,
      affected_domains: ["imports_invoices"],
      affected_scopes: ["2026-06"],
      route: "/imports/invoices",
      attention: false,
      updated_at: "2026-06-04T10:00:00+08:00",
    },
  ],
  alerts: [],
};

describe("global app status indicator", () => {
  test("renders app_status from the global runtime plane and keeps popover stable across route changes", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      appHealth: {
        status: "ok",
        generated_at: "2026-06-04T10:00:00+08:00",
        session: { status: "authenticated" },
        oa_sync: { status: "synced", message: "OA 已同步", dirty_scopes: [] },
        workbench_matching: { status: "ready", dirty_scopes: [], stale_scopes: [], rebuilding_scopes: [] },
        background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
        dependencies: {},
        app_status: globalAppStatus,
      },
    });
    renderAppAt("/");

    const indicator = await screen.findByRole("status", { name: "后台任务处理中" }, { timeout: 10_000 });
    expect(indicator).toHaveClass("pending");

    await user.hover(indicator);

    expect(screen.queryByText("运行状态")).not.toBeInTheDocument();

    await user.click(indicator);

    expect(await screen.findByText("运行状态")).toBeInTheDocument();
    expect(document.querySelector(".MuiPopover-root")).not.toBeInTheDocument();
    const statusDialog = screen.getByRole("dialog", { name: "全局运行状态" });
    expect(within(statusDialog).getByText("正在导入ETC发票 3/31")).toBeInTheDocument();
    expect(within(statusDialog).getByText("正在导入发票 210/500")).toBeInTheDocument();
    const runtimeSummary = within(statusDialog).getByTestId("app-status-runtime-summary");
    expect(runtimeSummary).toHaveTextContent("Read model");
    expect(runtimeSummary).toHaveTextContent("1 失败 / 0 不可用");
    expect(runtimeSummary).toHaveTextContent("Worker");
    expect(runtimeSummary).toHaveTextContent("1 stale / 1 missing / 0 mismatch");
    expect(runtimeSummary).toHaveTextContent("Queue");
    expect(runtimeSummary).toHaveTextContent("3 failed / 6 backlog");
    expect(within(statusDialog).getByText("银行明细")).toBeInTheDocument();
    expect(within(statusDialog).getByRole("link", { name: "银行明细 已同步" })).toBeInTheDocument();
    expect(within(statusDialog).getByText("税金抵扣")).toBeInTheDocument();
    expect(within(statusDialog).getByText("关联台")).toBeInTheDocument();
    expect(within(statusDialog).getByText("2026-05")).toBeInTheDocument();
    expect(within(statusDialog).getByText("projection failed")).toBeInTheDocument();
    expect(within(statusDialog).queryByText("就绪")).not.toBeInTheDocument();
    expect(screen.queryByText("银行明细已同步")).not.toBeInTheDocument();
    expect(screen.queryByText(/更新于/)).not.toBeInTheDocument();
    expect(screen.queryByText("当前没有后台任务。")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "App Health" })).not.toBeInTheDocument();

    await user.click(within(statusDialog).getByRole("link", { name: /银行明细/ }));

    await waitFor(() => {
      const stableDialog = screen.getByRole("dialog", { name: "全局运行状态" });
      expect(within(stableDialog).getByText("运行状态")).toBeInTheDocument();
      expect(within(stableDialog).getByText("正在导入ETC发票 3/31")).toBeInTheDocument();
      expect(within(stableDialog).getByText("正在导入发票 210/500")).toBeInTheDocument();
      expect(within(stableDialog).getByText("银行明细")).toBeInTheDocument();
    });

    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(screen.queryByText("全局运行状态")).not.toBeInTheDocument();
    });
  });

  test("shows operations link only for admin sessions and closes after pointer leave", async () => {
    const user = userEvent.setup();
    installMockApiFetch({
      sessionAccessTier: "admin",
      appHealth: {
        status: "ok",
        generated_at: "2026-06-04T10:00:00+08:00",
        session: { status: "authenticated" },
        oa_sync: { status: "synced", message: "OA 已同步", dirty_scopes: [] },
        workbench_matching: { status: "ready", dirty_scopes: [], stale_scopes: [], rebuilding_scopes: [] },
        background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
        dependencies: {},
        app_status: globalAppStatus,
      },
    });
    renderAppAt("/");

    const indicator = await screen.findByRole("status", { name: "后台任务处理中" });

    await user.click(indicator);

    expect(await screen.findByRole("link", { name: "App Health" })).toBeInTheDocument();

    await user.unhover(screen.getByRole("dialog", { name: "全局运行状态" }));

    await waitFor(() => {
      expect(screen.queryByText("全局运行状态")).not.toBeInTheDocument();
    });
  });
});
