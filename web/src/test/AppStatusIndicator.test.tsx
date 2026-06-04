import { screen, waitFor } from "@testing-library/react";
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
      details: ["bank_detail readiness fresh, schema v1"],
      read_models: ["bank_detail"],
      workers: ["bank-detail"],
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
  ],
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
        workbench_read_model: { status: "ready", dirty_scopes: [], stale_scopes: [], rebuilding_scopes: [] },
        background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
        dependencies: {},
        app_status: globalAppStatus,
      },
    });
    renderAppAt("/");

    const indicator = await screen.findByRole("status", { name: "后台任务处理中" });
    expect(indicator).toHaveClass("pending");

    await user.hover(indicator);

    expect(await screen.findByText("全局运行状态")).toBeInTheDocument();
    expect(screen.getByText("正在导入 ETC发票 3/31")).toBeInTheDocument();
    expect(screen.getByText("银行明细已同步")).toBeInTheDocument();
    expect(screen.getByText("bank_detail readiness fresh, schema v1")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "查看 App Health" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: /银行明细/ }));

    await waitFor(() => {
      expect(screen.getByText("全局运行状态")).toBeInTheDocument();
      expect(screen.getByText("正在导入 ETC发票 3/31")).toBeInTheDocument();
      expect(screen.getByText("银行明细已同步")).toBeInTheDocument();
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
        workbench_read_model: { status: "ready", dirty_scopes: [], stale_scopes: [], rebuilding_scopes: [] },
        background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
        dependencies: {},
        app_status: globalAppStatus,
      },
    });
    renderAppAt("/");

    const indicator = await screen.findByRole("status", { name: "后台任务处理中" });

    await user.hover(indicator);

    expect(await screen.findByRole("link", { name: "查看 App Health" })).toBeInTheDocument();

    await user.unhover(indicator);

    await waitFor(() => {
      expect(screen.queryByText("全局运行状态")).not.toBeInTheDocument();
    });
  });
});
