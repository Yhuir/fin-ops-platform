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
    {
      key: "tax_offset",
      label: "税金抵扣",
      route: "/tax-offset",
      level: "busy",
      status: "missing",
      reason: "税金抵扣正在同步",
      details: ["readiness record missing"],
      read_models: ["tax_offset"],
      workers: ["cost-tax"],
      job_ids: [],
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

    const indicator = await screen.findByRole("status", { name: "后台任务处理中" }, { timeout: 10_000 });
    expect(indicator).toHaveClass("pending");

    await user.hover(indicator);

    expect(await screen.findByText("运行状态")).toBeInTheDocument();
    expect(document.querySelector(".MuiPopover-root")).not.toBeInTheDocument();
    const statusDialog = screen.getByRole("dialog", { name: "全局运行状态" });
    expect(within(statusDialog).getByText("正在导入 ETC发票 3/31")).toBeInTheDocument();
    expect(within(statusDialog).getByText("银行明细")).toBeInTheDocument();
    expect(within(statusDialog).getByRole("link", { name: "银行明细 已同步" })).toBeInTheDocument();
    expect(within(statusDialog).getByText("税金抵扣")).toBeInTheDocument();
    expect(within(statusDialog).queryByText("就绪")).not.toBeInTheDocument();
    expect(screen.queryByText("银行明细已同步")).not.toBeInTheDocument();
    expect(screen.queryByText("bank_detail readiness fresh, schema v1")).not.toBeInTheDocument();
    expect(screen.queryByText("readiness record missing")).not.toBeInTheDocument();
    expect(screen.queryByText(/更新于/)).not.toBeInTheDocument();
    expect(screen.queryByText("当前没有后台任务。")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "App Health" })).not.toBeInTheDocument();

    await user.click(within(statusDialog).getByRole("link", { name: /银行明细/ }));

    await waitFor(() => {
      const stableDialog = screen.getByRole("dialog", { name: "全局运行状态" });
      expect(within(stableDialog).getByText("运行状态")).toBeInTheDocument();
      expect(within(stableDialog).getByText("正在导入 ETC发票 3/31")).toBeInTheDocument();
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
        workbench_read_model: { status: "ready", dirty_scopes: [], stale_scopes: [], rebuilding_scopes: [] },
        background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
        dependencies: {},
        app_status: globalAppStatus,
      },
    });
    renderAppAt("/");

    const indicator = await screen.findByRole("status", { name: "后台任务处理中" });

    await user.hover(indicator);

    expect(await screen.findByRole("link", { name: "App Health" })).toBeInTheDocument();

    await user.unhover(indicator);

    await waitFor(() => {
      expect(screen.queryByText("全局运行状态")).not.toBeInTheDocument();
    });
  });
});
