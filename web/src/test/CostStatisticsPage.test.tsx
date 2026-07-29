import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { AppChromeProvider } from "../contexts/AppChromeContext";
import CostStatisticsTable from "../components/cost-statistics/CostStatisticsTable";
import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { SessionPayload } from "../features/session/api";
import CostStatisticsPage from "../pages/CostStatisticsPage";
import { installMockApiFetch } from "./apiMock";

const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;
const PAGE_RENDER_TIMEOUT = 3000;
const defaultSession: SessionPayload = {
  allowed: true,
  user: {
    userId: "1",
    username: "TESTFULL001",
    nickname: "测试全权限",
    displayName: "测试全权限",
    deptId: null,
    deptName: null,
    avatar: null,
  },
  roles: ["fin_ops_user"],
  permissions: ["finops:app:view"],
  accessTier: "full_access",
  canAccessApp: true,
  canMutateData: true,
  canAdminAccess: false,
};

const staticSession: SessionContextValue = {
  status: "authenticated",
  session: defaultSession,
  refresh: () => undefined,
};

beforeAll(() => {
  Object.defineProperty(URL, "createObjectURL", {
    writable: true,
    value: vi.fn(() => "blob:cost-statistics-export"),
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    writable: true,
    value: vi.fn(),
  });
});

afterEach(() => {
  vi.mocked(URL.createObjectURL).mockClear();
  vi.mocked(URL.revokeObjectURL).mockClear();
});

afterAll(() => {
  Object.defineProperty(URL, "createObjectURL", {
    writable: true,
    value: originalCreateObjectURL,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    writable: true,
    value: originalRevokeObjectURL,
  });
});

function expectProjectCostShell() {
  const heading = screen.getByRole("heading", { name: "成本统计" });
  const page = heading.closest(".cost-page");
  expect(page).not.toBeNull();
  expect(page).not.toHaveClass("MuiBox-root");
  const viewSwitcher = screen.getByRole("tablist", { name: "成本统计视图切换" });
  expect(viewSwitcher).toHaveClass("cost-view-switcher");
  expect(viewSwitcher).not.toHaveClass("MuiTabs-root");
  expect(heading.closest(".page-header")).toContainElement(viewSwitcher);
}

function expectProjectCostTable(name: string) {
  const grid = screen.getByRole("grid", { name });
  const tableRoot = grid.closest(".finance-table");
  expect(tableRoot).not.toBeNull();
  expect(grid).not.toHaveClass("MuiDataGrid-root");
}

function expectProjectCostDialog(name: string) {
  const dialog = screen.getByRole("dialog", { name });
  expect(dialog.closest(".MuiDialog-root")).toBeNull();
  expect(dialog).toHaveClass(name === "导出中心" ? "export-center-modal" : "cost-detail-modal");
}

async function waitForCostStatisticsReady() {
  await waitFor(
    () => expect(screen.queryByTestId("cost-statistics-interaction-overlay")).not.toBeInTheDocument(),
    { timeout: PAGE_RENDER_TIMEOUT },
  );
}

async function findCostStatisticsHeading() {
  const heading = await screen.findByRole("heading", { name: "成本统计" }, { timeout: PAGE_RENDER_TIMEOUT });
  await waitForCostStatisticsReady();
  return heading;
}

function renderCostStatisticsPage(session: SessionContextValue = staticSession) {
  return render(
    <MemoryRouter initialEntries={["/cost-statistics"]}>
      <AppChromeProvider>
        <SessionContext.Provider value={session}>
          <PageSessionStateProvider>
            <CostStatisticsPage />
          </PageSessionStateProvider>
        </SessionContext.Provider>
      </AppChromeProvider>
    </MemoryRouter>,
  );
}

async function chooseScopeOption(user: ReturnType<typeof userEvent.setup>, triggerName: string, optionName: string) {
  await user.click(screen.getByRole("button", { name: triggerName }));
  const picker = await screen.findByRole("dialog", { name: /时间范围选择器/ });
  await user.click(within(picker).getByRole("button", { name: optionName }));
}

describe("Cost statistics page", () => {
  test("loads the next page near the table bottom and keeps retry local", async () => {
    const user = userEvent.setup();
    const onRequestNextPage = vi.fn();
    const props = {
      ariaLabel: "自动加载测试表",
      columns: [{ key: "label", header: "内容", render: (row: { id: string }) => row.id }],
      rows: [{ id: "row-1" }],
      getRowKey: (row: { id: string }) => row.id,
      hasNextPage: true,
      onRequestNextPage,
    };
    const rendered = render(<CostStatisticsTable {...props} />);

    await waitFor(() => expect(onRequestNextPage).toHaveBeenCalledTimes(1));

    rendered.rerender(<CostStatisticsTable {...props} loadMoreError="下一页加载失败" />);
    await user.click(screen.getByRole("button", { name: "重试" }));
    expect(onRequestNextPage).toHaveBeenCalledTimes(2);
  });

  test("locks compact premium surface and motion styling contracts", () => {
    const css = readFileSync("src/app/styles.css", "utf8");

    expect(css).not.toContain(".cost-page .stat-card");
    expect(css).toMatch(/\.cost-analysis-toolbar\s*{[^}]*border:\s*0/s);
    expect(css).toMatch(/\.cost-finance-table \.finance-table__row\s*{[^}]*min-height:\s*52px/s);
    expect(css).toMatch(/\.cost-view-tab\s*{[^}]*transition:[^}]*var\(--motion-fast\)/s);
    expect(css).toMatch(/\.cost-scope-trigger\s*{[^}]*min-height:\s*42px[^}]*transition:[^}]*var\(--motion-fast\)/s);
    expect(css).toMatch(/\.cost-scope-popover\s*{[^}]*width:\s*min\(360px,\s*calc\(100vw - 32px\)\)/s);
    expect(css).toMatch(/\.cost-explorer-item\s*{[^}]*padding:\s*10px var\(--fp-space-3\)[^}]*transition:[^}]*var\(--motion-fast\)/s);
    expect(css).toMatch(/\.cost-explorer-grid\.bank-tag\s*{[^}]*grid-template-columns:\s*minmax\(144px,\s*0\.8fr\) minmax\(144px,\s*0\.8fr\) minmax\(420px,\s*2\.4fr\)/s);
    expect(css).toMatch(/\.cost-explorer-grid\.project,[\s\S]*height:\s*max\(560px,\s*calc\(100dvh - 240px\)\)/s);
    expect(css).toMatch(/\.cost-view-scope-heading \.cost-section-heading-actions\s*{[^}]*order:\s*-1/s);
    expect(css).toMatch(/\.cost-lock-target\.is-locked\s*{[^}]*opacity:\s*0\.62/s);
    expect(css).toMatch(/\.cost-lock-overlay\s*{[^}]*background:\s*color-mix\(in srgb, var\(--fp-page\) 20%, transparent\)[^}]*pointer-events:\s*auto/s);
    expect(css).not.toMatch(/\.cost-lock-overlay\s*{[^}]*backdrop-filter/s);
    expect(css).not.toMatch(/\.cost-lock-overlay\s*{[^}]*animation:/s);
    expect(css).not.toContain("cost-lock-breathe");
    expect(css).toMatch(/\.cost-direction-amount--aligned\s*{[^}]*grid-template-columns:\s*auto minmax\(82px,\s*max-content\)/s);
    expect(css).toMatch(/\.export-center-modal\s*{[^}]*border-radius:\s*var\(--fp-radius-lg\)/s);
    expect(css).toMatch(/\.cost-detail-modal\s*{[^}]*border-radius:\s*var\(--fp-radius-lg\)/s);
  });

  test("uses a lightweight inline interaction lock instead of a dialog while initial data is unverified", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    installMockApiFetch({ costExplorerDelayMs: 50 });

    renderCostStatisticsPage();

    const heading = await screen.findByRole("heading", { name: "成本统计" }, { timeout: PAGE_RENDER_TIMEOUT });
    const statusCopy = screen.getByText("正在加载成本统计");
    const status = statusCopy.closest('[role="status"]');
    const tablist = screen.getByRole("tablist", { name: "成本统计视图切换" });
    const overlay = screen.getByTestId("cost-statistics-interaction-overlay");

    expect(status).toHaveClass("cost-lock-status--loading");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(overlay).toHaveClass("cost-lock-overlay");
    expect(tablist.closest("[inert]")).not.toBeNull();
    expect(heading.closest("[inert]")).toBeNull();

    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    expect(screen.queryByTestId("cost-statistics-interaction-overlay")).not.toBeInTheDocument();
    expect(tablist.closest("[inert]")).toBeNull();
  });

  test("keeps page controls interactive while switching an already loaded view", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costExplorerDelayMs: 50 });

    renderCostStatisticsPage();

    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    const bankViewButton = screen.getByRole("button", { name: "按银行" });
    await user.click(bankViewButton);

    expect(screen.queryByText("正在加载成本统计")).not.toBeInTheDocument();
    expect(screen.queryByTestId("cost-statistics-interaction-overlay")).not.toBeInTheDocument();
    expect(screen.getByRole("tablist", { name: "成本统计视图切换" }).closest("[inert]")).toBeNull();
    expect(screen.getByLabelText("正在加载成本统计内容")).toHaveAttribute("aria-busy", "true");
    expect(await screen.findByRole("heading", { name: "按银行统计" })).toBeInTheDocument();
  });

  test("defaults to time view and loads month-aware transaction rows", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    expectProjectCostShell();
    expect(screen.getByRole("button", { name: "按时间" })).toHaveClass("active");
    expect(screen.queryByText(/以已配对的支出流水为基准/)).not.toBeInTheDocument();
    expect(screen.queryByText("费用类型数")).not.toBeInTheDocument();
    expect(screen.queryByText("支出流水")).not.toBeInTheDocument();
    expect(screen.queryByText("支出总额")).not.toBeInTheDocument();
    expect(document.querySelector(".cost-page .stat-card")).toBeNull();
    const timeGrid = await screen.findByRole("grid", { name: "按时间统计表" });
    expectProjectCostTable("按时间统计表");
    expect(within(timeGrid).getByRole("columnheader", { name: "时间" })).toBeInTheDocument();
    expect(within(timeGrid).getByRole("columnheader", { name: "对方户名" })).toBeInTheDocument();
    expect(within(timeGrid).getByRole("columnheader", { name: "流水标签" })).toBeInTheDocument();
    expect(within(timeGrid).getByRole("columnheader", { name: "流水摘要" })).toBeInTheDocument();
    expect(within(timeGrid).queryByRole("columnheader", { name: "项目名" })).not.toBeInTheDocument();
    expect(within(timeGrid).queryByRole("columnheader", { name: "费用类型" })).not.toBeInTheDocument();
    expect(await within(timeGrid).findByRole("button", { name: "查看流水 cost-txn-003" })).toBeInTheDocument();
    expect(within(timeGrid).queryByRole("button", { name: "查看流水 cost-txn-004" })).not.toBeInTheDocument();
    expect(within(timeGrid).getByText("2026-03-10 21:27:55")).toBeInTheDocument();
    expect(within(timeGrid).queryByText("2026-03-10T21:27:55+08:00")).not.toBeInTheDocument();
    expect(within(timeGrid).queryByRole("columnheader", { name: "资金方向" })).not.toBeInTheDocument();
    expect(within(timeGrid).getAllByText("支出")[0]).toHaveClass("direction-tag");
    expect(screen.getByLabelText("支出金额 13,360.00")).toHaveClass("cost-direction-amount--expense");
    expect(screen.getByLabelText("收入金额 2,000.00")).toHaveClass("cost-direction-amount--income");
    expect(screen.queryByText("总金额 15,360.00")).not.toBeInTheDocument();
    expect(await within(timeGrid).findByRole("button", { name: "查看流水 cost-income-001" })).toBeInTheDocument();
    expect(within(timeGrid).getByText("2,000.00").closest(".money-cell-value")).toHaveClass("cost-flow-amount--income");
    expect(screen.getByRole("button", { name: "时间统计时间范围：2026年3月" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /加载更多/ })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=2026-03&view=time&project_scope=active&page_size=50",
      expect.any(Object),
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=project&project_scope=active&page_size=1",
      expect.any(Object),
    );

    await chooseScopeOption(user, "时间统计时间范围：2026年3月", "四月");

    const nextTimeGrid = await screen.findByRole("grid", { name: "按时间统计表" });
    expectProjectCostTable("按时间统计表");
    expect(await within(nextTimeGrid).findByRole("button", { name: "查看流水 cost-txn-102" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "时间统计时间范围：2026年4月" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=2026-04&view=time&project_scope=active&page_size=50",
      expect.any(Object),
    );
  });

  test("searches only the active view without refreshing the page chrome", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    const heading = screen.getByRole("heading", { name: "成本统计" });
    await user.type(screen.getByRole("searchbox", { name: "搜索当前成本统计表格" }), "昆明设备");

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/cost-statistics/explorer?scope=2026-03&view=time&project_scope=active&query=${encodeURIComponent("昆明设备")}&page_size=50`,
        expect.any(Object),
      );
    });
    expect(heading).toBeInTheDocument();
    expect(screen.queryByTestId("cost-statistics-interaction-overlay")).not.toBeInTheDocument();
    expect(screen.getByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
  });

  test("closes tag rules drawer after canonical save without waiting for a read model barrier", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "成本统计标签规则" }));
    const drawer = await screen.findByRole("dialog", { name: "成本统计标签规则" });
    expect(within(drawer).getAllByText("未分类").length).toBeGreaterThan(0);
    expect(within(drawer).getByText("收入 · 经营收入")).toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "成本统计标签规则" })).not.toBeInTheDocument();
    });
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/operation-barrier/status",
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=2026-03&view=time&project_scope=active&page_size=50",
      expect.any(Object),
    );
  });

  test("disables tag rules save when API marks the rule set read-only", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costTagRulesCanSave: false });

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "成本统计标签规则" }));
    const drawer = await screen.findByRole("dialog", { name: "成本统计标签规则" });

    expect(within(drawer).getByRole("button", { name: "保存" })).toBeDisabled();
  });

  test("admin can run the cost statistics title audit icon", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderCostStatisticsPage({
      ...staticSession,
      session: {
        ...defaultSession,
        canAdminAccess: true,
      },
    });

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Audit 成本统计" }));

    expect(
      await screen.findByText("Audit 通过 · 此数据库快照内已登记 App 内部合同一致 · 已登记配对证明一致 · 外部来源未证明 · Fresh"),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/operations/app-health/page-audit?page=cost-statistics",
      expect.any(Object),
    );
  });

  test("project view drills down from project to expense type to transaction from left to right", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按项目" }));
    expect(await screen.findByRole("button", { name: "项目统计时间范围：全部时间" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=project&project_scope=active&page_size=50",
      expect.any(Object),
    );
    expect(screen.getByText("昆明卷烟厂动力设备控制系统升级改造项目")).toBeInTheDocument();
    expect(screen.queryByText("昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /项目范围：/ })).not.toBeInTheDocument();

    const projectLane = screen.getByRole("heading", { name: "项目名" }).closest(".cost-explorer-lane");
    expect(projectLane).not.toBeNull();
    expect(within(projectLane as HTMLElement).getByText("58.2%")).toBeInTheDocument();
    expect(within(projectLane as HTMLElement).getByLabelText("支出 13,360.00")).toHaveClass("cost-direction-amount--aligned");
    await user.click(within(projectLane as HTMLElement).getByRole("button", { name: /云南溯源科技/ }));

    const expenseLane = screen.getByRole("heading", { name: "费用类型" }).closest(".cost-explorer-lane");
    expect(expenseLane).not.toBeNull();
    expect(within(expenseLane as HTMLElement).getByText("设备货款及材料费")).toBeInTheDocument();
    expect(within(expenseLane as HTMLElement).getByText("交通费")).toBeInTheDocument();
    expect(within(expenseLane as HTMLElement).getByText("93.6%")).toBeInTheDocument();
    expect(within(expenseLane as HTMLElement).getByText("6.4%")).toBeInTheDocument();

    await user.click(within(expenseLane as HTMLElement).getByRole("button", { name: /设备货款及材料费/ }));

    const transactionTable = screen.getByRole("grid", { name: "项目对应流水表" });
    expectProjectCostTable("项目对应流水表");
    const projectTransactionTrigger = await within(transactionTable).findByRole("button", {
      name: "查看流水 cost-txn-001",
    });
    expect(projectTransactionTrigger).toBeInTheDocument();
    expect(within(projectTransactionTrigger).getByText("2026-03-10 21:27:55")).toHaveClass("cost-transaction-time-chip");
    expect(await within(transactionTable).findByRole("button", { name: "查看流水 cost-txn-002" })).toBeInTheDocument();
    expect(within(transactionTable).queryByRole("columnheader", { name: "时间" })).not.toBeInTheDocument();
    expect(within(transactionTable).queryByRole("columnheader", { name: "资金方向" })).not.toBeInTheDocument();

    await user.click(within(transactionTable).getByRole("button", { name: "查看流水 cost-txn-001" }));

    const dialog = await screen.findByRole("dialog", { name: "流水详情" });
    expectProjectCostDialog("流水详情");
    expect(dialog).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/transactions/cost-txn-001?project_scope=active&view=project&scope=all",
      expect.any(Object),
    );
    expect(screen.getAllByText("PLC 模块采购").length).toBeGreaterThan(0);
    const detailBankName = within(dialog).getByText("工商银行");
    expect(detailBankName).toBeInTheDocument();
    expect(detailBankName.closest(".bank-account-tag")).not.toBeNull();
    expect(within(dialog).getByText("0001")).toBeInTheDocument();
    expect(within(dialog).queryByText("工商银行 账户 0001")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("支付账户")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("资金方向")).not.toBeInTheDocument();
    expect(within(dialog).getByText("支出")).toHaveClass("direction-tag");
    expect(within(dialog).getByRole("heading", { name: "OA 成本拆分" })).toBeInTheDocument();
    expect(within(dialog).getByText("云南溯源科技 · 设备货款及材料费")).toBeInTheDocument();
    expect(within(dialog).getByText("昆明升级项目 · 安装服务费")).toBeInTheDocument();
    expect(within(dialog).getByText(/6,000\.00/)).toBeInTheDocument();
    expect(within(dialog).getByText(/4,000\.00/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "关闭" }));
    expect(screen.queryByRole("dialog", { name: "流水详情" })).not.toBeInTheDocument();
  });

  test("keeps upstream lanes and clears only dependent lanes during project drilldown", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costExplorerDelayMs: 50 });

    renderCostStatisticsPage();
    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按项目" }));

    const projectLane = (await screen.findByRole("heading", { name: "项目名" })).closest(".cost-explorer-lane");
    expect(projectLane).not.toBeNull();
    await user.click(within(projectLane as HTMLElement).getByRole("button", { name: /云南溯源科技/ }));

    const expenseLane = screen.getByRole("heading", { name: "费用类型" }).closest(".cost-explorer-lane");
    const transactionLane = screen.getByRole("heading", { name: "对应流水" }).closest(".cost-explorer-lane");
    expect(within(projectLane as HTMLElement).getByText("云南溯源科技")).toBeInTheDocument();
    expect(expenseLane).toHaveAttribute("aria-busy", "true");
    expect(transactionLane).toHaveAttribute("aria-busy", "true");
    expect(within(transactionLane as HTMLElement).queryByText(/请先/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("cost-statistics-interaction-overlay")).not.toBeInTheDocument();

    await waitFor(() => expect(expenseLane).toHaveAttribute("aria-busy", "false"));
    await user.click(within(expenseLane as HTMLElement).getByRole("button", { name: /设备货款及材料费/ }));

    expect(within(projectLane as HTMLElement).getByText("云南溯源科技")).toBeInTheDocument();
    expect(within(expenseLane as HTMLElement).getByText("设备货款及材料费")).toBeInTheDocument();
    expect(transactionLane).toHaveAttribute("aria-busy", "true");
    expect(within(transactionLane as HTMLElement).queryByText(/请先/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("cost-statistics-interaction-overlay")).not.toBeInTheDocument();

    expect(await screen.findByRole("grid", { name: "项目对应流水表" })).toBeInTheDocument();
  });

  test("sends one canonical request per project or scope selection", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ costExplorerDelayMs: 50 });

    renderCostStatisticsPage();
    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按项目" }));

    const projectLane = (await screen.findByRole("heading", { name: "项目名" })).closest(".cost-explorer-lane");
    expect(projectLane).not.toBeNull();
    const projectCallStart = fetchMock.mock.calls.length;
    await user.click(within(projectLane as HTMLElement).getByRole("button", { name: /云南溯源科技/ }));

    const expenseLane = screen.getByRole("heading", { name: "费用类型" }).closest(".cost-explorer-lane");
    await waitFor(() => expect(expenseLane).toHaveAttribute("aria-busy", "false"));
    const projectCalls = fetchMock.mock.calls
      .slice(projectCallStart)
      .map(([url]) => String(url))
      .filter((url) => url.includes("/api/cost-statistics/explorer"));
    expect(projectCalls).toHaveLength(1);
    expect(projectCalls[0]).toContain("scope=all&view=project");
    expect(projectCalls[0]).toContain("project_name=%E4%BA%91%E5%8D%97%E6%BA%AF%E6%BA%90%E7%A7%91%E6%8A%80");

    const scopeCallStart = fetchMock.mock.calls.length;
    await chooseScopeOption(user, "项目统计时间范围：全部时间", "四月");
    expect(await screen.findByRole("button", { name: "项目统计时间范围：2026年4月" })).toBeInTheDocument();
    await waitFor(() => expect(projectLane).toHaveAttribute("aria-busy", "false"));

    const scopeCalls = fetchMock.mock.calls
      .slice(scopeCallStart)
      .map(([url]) => String(url))
      .filter((url) => url.includes("/api/cost-statistics/explorer"));
    expect(scopeCalls).toHaveLength(1);
    expect(scopeCalls[0]).toContain("scope=2026-04&view=project");
    expect(scopeCalls[0]).not.toContain("project_name=");
    expect(scopeCalls[0]).not.toContain("expense_type=");
  });

  test("project view keeps split cost rows with the same transaction id renderable", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    installMockApiFetch({ costDuplicateTransactionRows: true });

    try {
      renderCostStatisticsPage();

      expect(await findCostStatisticsHeading()).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "按项目" }));

      const projectLane = screen.getByRole("heading", { name: "项目名" }).closest(".cost-explorer-lane");
      expect(projectLane).not.toBeNull();
      await user.click(within(projectLane as HTMLElement).getByRole("button", { name: /云南溯源科技/ }));

      const expenseLane = screen.getByRole("heading", { name: "费用类型" }).closest(".cost-explorer-lane");
      expect(expenseLane).not.toBeNull();
      await user.click(within(expenseLane as HTMLElement).getByRole("button", { name: /设备货款及材料费/ }));

      const transactionTable = screen.getByRole("grid", { name: "项目对应流水表" });
      expect(await within(transactionTable).findAllByRole("button", { name: "查看流水 cost-txn-001" })).toHaveLength(2);
      expect(within(transactionTable).getByText("PLC 模块采购追加成本")).toBeInTheDocument();
      expect(
        consoleError.mock.calls.some((call) => call.join(" ").includes("Encountered two children with the same key")),
      ).toBe(false);
    } finally {
      consoleError.mockRestore();
    }
  });

  test("project view supports all time, year, and month scopes from one range button", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按项目" }));

    expect(await screen.findByRole("button", { name: "项目统计时间范围：全部时间" })).toBeInTheDocument();
    const projectLane = () => screen.getByRole("heading", { name: "项目名" }).closest(".cost-explorer-lane") as HTMLElement;
    expect(within(projectLane()).getByText("云南溯源科技")).toBeInTheDocument();
    expect(within(projectLane()).getByText("昆明卷烟厂动力设备控制系统升级改造项目")).toBeInTheDocument();
    expect(within(projectLane()).queryByText("昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目")).not.toBeInTheDocument();

    await chooseScopeOption(user, "项目统计时间范围：全部时间", "2026年");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(await within(projectLane()).findByText("云南溯源科技")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "项目统计时间范围：2026年" })).toBeInTheDocument();

    await chooseScopeOption(user, "项目统计时间范围：2026年", "四月");
    expect(screen.getByRole("button", { name: "项目统计时间范围：2026年4月" })).toBeInTheDocument();

    expect(await within(projectLane()).findByText("昆明卷烟厂动力设备控制系统升级改造项目")).toBeInTheDocument();
    expect(within(projectLane()).queryByText("云南溯源科技")).not.toBeInTheDocument();

    await chooseScopeOption(user, "项目统计时间范围：2026年4月", "全部时间");
    expect(await within(projectLane()).findByText("云南溯源科技")).toBeInTheDocument();
    expect(await within(projectLane()).findByText("昆明卷烟厂动力设备控制系统升级改造项目")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "项目统计时间范围：全部时间" })).toBeInTheDocument();
  });

  test("expense type view shows time, project name, amount and expense content in a modal drilldown", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按OA费用类型" }));
    await waitForCostStatisticsReady();

    const expenseLane = screen.getByRole("heading", { name: "费用类型" }).closest(".cost-explorer-lane");
    expect(expenseLane).not.toBeNull();
    expect(within(expenseLane as HTMLElement).getByLabelText("支出 860.00")).toHaveClass("cost-direction-amount--aligned");
    await user.click(within(expenseLane as HTMLElement).getByRole("button", { name: /交通费/ }));

    const transactionTable = screen.getByRole("grid", { name: "按费用类型流水表" });
    expectProjectCostTable("按费用类型流水表");
    const transactionTime = await within(transactionTable).findByText("2026-03-18 17:02:09");
    expect(transactionTime).toHaveClass("cost-transaction-time-chip");
    expect(within(transactionTable).getByText("云南溯源科技")).toBeInTheDocument();
    expect(within(transactionTable).getByText("860.00")).toBeInTheDocument();
    expect(within(transactionTable).getByText("项目现场往返交通")).toBeInTheDocument();
    expect(within(transactionTable).queryByRole("columnheader", { name: "资金方向" })).not.toBeInTheDocument();
    expect(within(transactionTable).queryByRole("columnheader", { name: "时间" })).not.toBeInTheDocument();
    await user.click(await within(transactionTable).findByRole("button", { name: "查看流水 cost-txn-003" }));
    const dialog = await screen.findByRole("dialog", { name: "流水详情" });
    expectProjectCostDialog("流水详情");
    expect(dialog).toBeInTheDocument();
    const expenseDetailBankName = within(dialog).getByText("招商银行");
    expect(expenseDetailBankName).toBeInTheDocument();
    expect(expenseDetailBankName.closest(".bank-account-tag")).not.toBeNull();
    expect(within(dialog).getByText("2201")).toBeInTheDocument();
    expect(within(dialog).queryByText("招商银行 账户 2201")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("支付账户")).not.toBeInTheDocument();
  });

  test("bank tag view drills down from primary tag to sub tag to transaction", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按标签" }));

    expect(screen.getByRole("heading", { name: "按标签统计" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "流水标签统计时间范围：2026年3月" })).toBeInTheDocument();
    const primaryLane = screen.getByRole("heading", { name: "主标签" }).closest(".cost-explorer-lane");
    expect(primaryLane).not.toBeNull();
    expect(within(primaryLane as HTMLElement).getByText("项目开销")).toBeInTheDocument();
    expect(within(primaryLane as HTMLElement).getByText("差旅交通")).toBeInTheDocument();
    expect(within(primaryLane as HTMLElement).getByText("经营收入")).toBeInTheDocument();
    expect(screen.getByLabelText("支出金额 13,360.00")).toHaveClass("cost-direction-amount--expense");
    expect(screen.getByLabelText("收入金额 2,000.00")).toHaveClass("cost-direction-amount--income");
    expect(within(primaryLane as HTMLElement).queryByText(/%$/)).not.toBeInTheDocument();
    const incomeCountRow = within(primaryLane as HTMLElement).getByRole("button", { name: /经营收入/ });
    expect(incomeCountRow).toHaveTextContent("支出 0 笔");
    expect(incomeCountRow).toHaveTextContent("收入 1 笔");
    expect(incomeCountRow).toHaveTextContent("1 个子标签");
    expect(incomeCountRow.querySelector(".cost-tag-count--expense")).toHaveTextContent("0");
    expect(incomeCountRow.querySelector(".cost-tag-count--income")).toHaveTextContent("1");
    const incomeOnlyRow = within(primaryLane as HTMLElement).getByRole("button", { name: /经营收入/ });
    expect(
      Array.from(incomeOnlyRow.querySelectorAll(".cost-direction-amount-label")).map((node) => node.textContent),
    ).toEqual(["支出", "收入"]);
    expect(within(incomeOnlyRow).getByLabelText("支出")).toBeInTheDocument();
    expect(within(incomeOnlyRow).queryByText("0.00")).not.toBeInTheDocument();

    await user.click(within(primaryLane as HTMLElement).getByRole("button", { name: /项目开销/ }));

    const subLane = screen.getByRole("heading", { name: "子标签" }).closest(".cost-explorer-lane");
    expect(subLane).not.toBeNull();
    expect(within(subLane as HTMLElement).getByText("设备材料")).toBeInTheDocument();
    await user.click(within(subLane as HTMLElement).getByRole("button", { name: /设备材料/ }));

    const transactionTable = screen.getByRole("grid", { name: "流水标签对应流水表" });
    expectProjectCostTable("流水标签对应流水表");
    expect(
      await within(transactionTable).findByRole("button", { name: "查看流水 cost-txn-001" }),
    ).toBeInTheDocument();
    expect(
      await within(transactionTable).findByRole("button", { name: "查看流水 cost-txn-002" }),
    ).toBeInTheDocument();
    expect(within(transactionTable).getByText("2026-03-10 21:27:55")).toHaveClass("cost-transaction-time-chip");
    expect(within(transactionTable).queryByRole("columnheader", { name: "时间" })).not.toBeInTheDocument();

    await user.click(within(transactionTable).getByRole("button", { name: "查看流水 cost-txn-001" }));

    expect(await screen.findByRole("dialog", { name: "流水详情" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/transactions/cost-txn-001?project_scope=active&view=bank_tag&scope=2026-03",
      expect.any(Object),
    );
  });

  test("exports bank tag income and expense rows with directional summaries", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按标签" }));
    await user.click(screen.getByRole("button", { name: "导出中心" }));
    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
    expect(within(dialog).getByRole("button", { name: "按标签" })).toHaveClass("active");

    await user.click(within(dialog).getByRole("button", { name: "仅预览" }));

    expect(await within(dialog).findByText("支出金额 13,360.00")).toHaveClass("cost-direction-amount--expense");
    expect(within(dialog).getByText("收入金额 2,000.00")).toHaveClass("cost-direction-amount--income");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/export-preview?month=2026-03&view=bank_tag&project_scope=active",
      expect.any(Object),
    );

    await user.click(within(dialog).getByRole("button", { name: "导出" }));
    expect(await within(dialog).findByText("已导出 成本统计_2026-03_按标签统计.xlsx")).toBeInTheDocument();
  });

  test("shows empty state when the selected month has no cost statistics", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    await chooseScopeOption(user, "时间统计时间范围：2026年3月", "五月");

    expect(await screen.findAllByText("当前时间范围没有收入或支出流水。")).toHaveLength(1);
    expect(screen.getByText("当前时间范围没有可用于流水统计的收入或支出流水。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "时间统计时间范围：2026年5月" })).toBeInTheDocument();
    await chooseScopeOption(user, "时间统计时间范围：2026年5月", "三月");
    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
  });

  test("bank view supports all-time, year, and month drilldown from bank to project to transaction", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按银行" }));
    await waitForCostStatisticsReady();

    expect(await screen.findByRole("button", { name: "银行统计时间范围：全部时间" })).toBeInTheDocument();
    const bankLane = screen.getByRole("heading", { name: "银行账户" }).closest(".cost-explorer-lane");
    expect(bankLane).not.toBeNull();
    expect(within(bankLane as HTMLElement).getByText("工商银行 账户 0001")).toBeInTheDocument();
    expect(within(bankLane as HTMLElement).getByText("平安银行 账户 8821")).toBeInTheDocument();
    expect(within(bankLane as HTMLElement).getByText("民生银行 账户 9486")).toBeInTheDocument();
    expect(within(bankLane as HTMLElement).getByText("54.4%")).toBeInTheDocument();
    expect(screen.getByLabelText("支出金额 22,960.00")).toBeInTheDocument();
    expect(within(bankLane as HTMLElement).getByLabelText("支出 12,500.00")).toHaveClass("cost-direction-amount--aligned");

    await user.click(within(bankLane as HTMLElement).getByRole("button", { name: /工商银行 账户 0001/ }));

    const projectLane = screen.getByRole("heading", { name: "项目名" }).closest(".cost-explorer-lane");
    expect(projectLane).not.toBeNull();
    expect(within(projectLane as HTMLElement).getByText("云南溯源科技")).toBeInTheDocument();
    expect(within(projectLane as HTMLElement).getByText("100.0%")).toBeInTheDocument();

    await user.click(within(projectLane as HTMLElement).getByRole("button", { name: /云南溯源科技/ }));
    const transactionTable = screen.getByRole("grid", { name: "银行对应流水表" });
    expectProjectCostTable("银行对应流水表");
    expect(
      await within(transactionTable).findByRole("button", { name: "查看流水 cost-txn-001" }),
    ).toBeInTheDocument();
    expect(
      await within(transactionTable).findByRole("button", { name: "查看流水 cost-txn-002" }),
    ).toBeInTheDocument();
    expect(within(transactionTable).getByText("2026-03-10 21:27:55")).toHaveClass("cost-transaction-time-chip");
    expect(within(transactionTable).queryByRole("columnheader", { name: "时间" })).not.toBeInTheDocument();

    await chooseScopeOption(user, "银行统计时间范围：全部时间", "2026年");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    const yearBankLane = screen.getByRole("heading", { name: "银行账户" }).closest(".cost-explorer-lane");
    expect(yearBankLane).not.toBeNull();
    expect(within(yearBankLane as HTMLElement).getByText("平安银行 账户 8821")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "银行统计时间范围：2026年" })).toBeInTheDocument();

    await chooseScopeOption(user, "银行统计时间范围：2026年", "四月");
    expect(screen.getByRole("button", { name: "银行统计时间范围：2026年4月" })).toBeInTheDocument();

    const monthBankLane = screen.getByRole("heading", { name: "银行账户" }).closest(".cost-explorer-lane");
    expect(monthBankLane).not.toBeNull();
    expect(await within(monthBankLane as HTMLElement).findByText("平安银行 账户 8821")).toBeInTheDocument();
    expect(within(monthBankLane as HTMLElement).getByText("工商银行 账户 0001")).toBeInTheDocument();
    expect(within(monthBankLane as HTMLElement).getByText("民生银行 账户 9486")).toBeInTheDocument();
    expect(screen.getByLabelText("支出金额 9,600.00")).toBeInTheDocument();
  });

  test("time and expense type scopes stay independent with one range control per view", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按时间" }));
    await chooseScopeOption(user, "时间统计时间范围：2026年3月", "四月");
    expect(await screen.findByRole("button", { name: "时间统计时间范围：2026年4月" })).toBeInTheDocument();
    expect(screen.getByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "查看流水 cost-txn-102" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "按OA费用类型" }));
    await chooseScopeOption(user, "OA费用类型统计时间范围：2026年3月", "2026年");
    expect(screen.getByRole("button", { name: "OA费用类型统计时间范围：2026年" })).toBeInTheDocument();
    expect(await screen.findByText("交通费")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "按时间" }));
    expect(screen.getByRole("button", { name: "时间统计时间范围：2026年4月" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "查看流水 cost-txn-102" })).toBeInTheDocument();
  });

  test("scope picker floats under the range button instead of taking layout height", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按时间" }));
    await user.click(screen.getByRole("button", { name: "时间统计时间范围：2026年3月" }));
    const scopeControls = screen.getByRole("button", { name: "时间统计时间范围：2026年3月" }).closest(".cost-scope-controls");
    expect(scopeControls).not.toBeNull();
    expect(scopeControls).not.toHaveClass("MuiTabs-root");
    const floatingPanel = scopeControls?.querySelector(".cost-scope-popover");
    expect(floatingPanel).not.toBeNull();
    expect(floatingPanel).toHaveAttribute("role", "dialog");
  });

  test("scope picker closes when clicking the active button again or clicking outside", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    const monthScopeButton = await screen.findByRole("button", { name: "时间统计时间范围：2026年3月" });
    expect(screen.queryByRole("button", { name: "三月" })).not.toBeInTheDocument();

    await user.click(monthScopeButton);
    expect(screen.getByRole("button", { name: "三月" })).toBeInTheDocument();

    await user.click(monthScopeButton);
    expect(screen.queryByRole("button", { name: "三月" })).not.toBeInTheDocument();
    await user.click(monthScopeButton);
    expect(screen.getByRole("button", { name: "三月" })).toBeInTheDocument();
    await user.click(document.body);
    expect(screen.queryByRole("button", { name: "三月" })).not.toBeInTheDocument();
  });

  test("only replaces the content surface while a new view is loading", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costExplorerDelayMs: 50 });

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "按银行" }));

    expect(screen.queryByText("正在加载成本统计")).not.toBeInTheDocument();
    expect(screen.getByRole("tablist", { name: "成本统计视图切换" }).closest("[inert]")).toBeNull();
    expect(screen.queryByRole("grid", { name: "按时间统计表" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("正在加载成本统计内容")).toHaveAttribute("aria-busy", "true");
    expect(await screen.findByRole("heading", { name: "按银行统计" })).toBeInTheDocument();
    expect(screen.getByRole("tablist", { name: "成本统计视图切换" }).closest("[inert]")).toBeNull();
    expect(screen.getByRole("button", { name: "银行统计时间范围：全部时间" })).toBeInTheDocument();
  });

  test("only replaces the content surface while the time range is loading", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costExplorerDelayMs: 50 });

    renderCostStatisticsPage();
    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    await chooseScopeOption(user, "时间统计时间范围：2026年3月", "四月");

    expect(screen.getByRole("button", { name: "时间统计时间范围：2026年4月" })).toBeEnabled();
    expect(screen.queryByTestId("cost-statistics-interaction-overlay")).not.toBeInTheDocument();
    expect(screen.getByLabelText("正在加载成本统计内容")).toHaveAttribute("aria-busy", "true");
    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
  });

  test("shows error state when explorer loading fails", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costErrorMonths: ["2026-04"] });

    renderCostStatisticsPage();

    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    await chooseScopeOption(user, "时间统计时间范围：2026年3月", "四月");

    expect(await screen.findByText("成本统计数据加载失败，请点击刷新重试。")).toBeInTheDocument();
  });

  test("refreshes explorer data after a transient loading failure", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ costExplorerFailuresBeforeSuccess: 1 });

    renderCostStatisticsPage();

    expect(await screen.findByText("成本统计数据加载暂时失败，请刷新后重试。")).toBeInTheDocument();
    expect(screen.queryByText("当前时间范围没有可用于成本统计的支出流水。")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导出中心" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "刷新成本统计" }).closest("[inert]")).not.toBeNull();

    await user.click(screen.getByRole("button", { name: "重新检查" }));

    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    expect(screen.queryByText("成本统计数据加载暂时失败，请刷新后重试。")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导出中心" })).toBeEnabled();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=2026-03&view=time&project_scope=active&page_size=50",
      expect.any(Object),
    );
  });

  test("loads the canonical page once without background polling", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(
      await screen.findByRole("grid", { name: "按时间统计表" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("cost-statistics-interaction-overlay"),
    ).not.toBeInTheDocument();
    await waitFor(
      () => {
        const explorerCalls = fetchMock.mock.calls.filter(([request]) => (
          String(request)
            === "/api/cost-statistics/explorer?scope=2026-03&view=time&project_scope=active&page_size=50"
        ));
        expect(explorerCalls).toHaveLength(1);
      },
      { timeout: PAGE_RENDER_TIMEOUT },
    );
  });

  test("manual refresh reloads global statistics instead of using the drilldown-only contract", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const initialUrl = "/api/cost-statistics/explorer?scope=2026-03&view=time&project_scope=active&page_size=50";

    renderCostStatisticsPage();

    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "刷新成本统计" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.filter(([request]) => String(request) === initialUrl)).toHaveLength(2);
    });
  });

  test("surfaces OA session errors from explorer loading", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        error: "invalid_oa_session",
        message: "缺少 OA 登录态，请从 OA 系统进入。",
      }), {
        status: 401,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      }),
    ) as typeof fetch;

    renderCostStatisticsPage();

    expect(await screen.findByText("缺少 OA 登录态，请从 OA 系统进入。")).toBeInTheDocument();
    expect(screen.queryByText("成本统计数据加载失败，请稍后重试。")).not.toBeInTheDocument();
  });

  test("opens export center in time view with exact date range and shows export feedback inside the modal", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导出中心" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "最近导出" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "高级导出" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "导出项目明细" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "导出中心" }));
    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
    expectProjectCostDialog("导出中心");
    expect(within(dialog).getByRole("button", { name: "按时间" })).toHaveClass("active");
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=project&project_scope=active&page_size=1",
      expect.any(Object),
    );
    expect(within(dialog).getByLabelText("自定义月份")).toBeChecked();
    expect(within(dialog).getByRole("button", { name: "统计月份" })).toBeInTheDocument();
    await user.click(within(dialog).getByLabelText("自定义时间区间（精确到日）"));
    fireEvent.change(within(dialog).getByLabelText("开始日期"), {
      target: { value: "2026-03-10" },
    });
    fireEvent.change(within(dialog).getByLabelText("结束日期"), {
      target: { value: "2026-04-16" },
    });
    await user.click(within(dialog).getByRole("button", { name: "仅预览" }));

    expect(await within(dialog).findByText("预览结果")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/export-preview?month=all&view=time&project_scope=active&start_date=2026-03-10&end_date=2026-04-16",
      expect.any(Object),
    );
    expect(within(dialog).getByText("预计导出 6 条流水")).toBeInTheDocument();
    expect(within(dialog).getByText("支出金额 22,960.00")).toHaveClass("cost-direction-amount--expense");
    expect(within(dialog).getByText("收入金额 2,000.00")).toHaveClass("cost-direction-amount--income");

    await user.click(within(dialog).getByRole("button", { name: "导出" }));
    expect(await within(dialog).findByText("已导出 成本统计_2026-03-10至2026-04-16_按时间统计.xlsx")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/export?month=all&view=time&project_scope=active&start_date=2026-03-10&end_date=2026-04-16",
      expect.any(Object),
    );
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  });

  test("loads all-scope export options only when an open export center switches to project mode", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "导出中心" }));
    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=project&project_scope=active&page_size=1",
      expect.any(Object),
    );

    await user.click(within(dialog).getByRole("button", { name: "按项目" }));

    await waitFor(() => expect(within(dialog).getByLabelText("云南溯源科技")).toBeChecked());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=project&project_scope=active&page_size=1&include_statistics=false",
      expect.any(Object),
    );
  });

  test("shows backend export failure messages inside the export center", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costExportErrorViews: ["time"] });

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "导出中心" }));
    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
    await user.click(within(dialog).getByRole("button", { name: "导出" }));

    expect(await within(dialog).findByText("cost statistics export failed")).toBeInTheDocument();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  test("uses export center in project mode with project and expense type filters", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按项目" }));
    expect(await screen.findByRole("button", { name: "项目统计时间范围：全部时间" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "导出中心" }));
    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
    expectProjectCostDialog("导出中心");
    expect(within(dialog).getByRole("button", { name: "按项目" })).toHaveClass("active");
    await waitFor(() => expect(within(dialog).getByLabelText("云南溯源科技")).toBeChecked());
    await user.click(within(dialog).getByLabelText("交通费"));
    await user.click(within(dialog).getByLabelText("经营/办公费用"));
    await user.click(within(dialog).getByRole("button", { name: "仅预览" }));

    expect(await within(dialog).findByText("预览结果")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/cost-statistics/export-preview?month=all&view=project&project_scope=active&project_name=${encodeURIComponent("云南溯源科技")}&aggregate_by=month&expense_type=${encodeURIComponent("设备货款及材料费")}`,
      expect.any(Object),
    );
    expect(within(dialog).getByText("预计导出 2 条流水")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "导出" }));
    expect(await within(dialog).findByText("已导出 成本统计_全部期间_按项目统计_按月_云南溯源科技.xlsx")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/cost-statistics/export?month=all&view=project&project_scope=active&project_name=${encodeURIComponent("云南溯源科技")}&aggregate_by=month&expense_type=${encodeURIComponent("设备货款及材料费")}&include_oa_details=true&include_invoice_details=true&include_exception_rows=true&include_ignored_rows=true&include_expense_content_summary=true&sort_by=time`,
      expect.any(Object),
    );
  });

  test("supports expense type export center filters with range and multi-select", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按OA费用类型" }));
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=project&project_scope=active&page_size=1",
      expect.any(Object),
    );
    await user.click(screen.getByRole("button", { name: "导出中心" }));

    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=expense_type&project_scope=active&page_size=1&include_statistics=false",
      expect.any(Object),
    );
    expectProjectCostDialog("导出中心");
    expect(within(dialog).getByRole("button", { name: "按费用类型" })).toHaveClass("active");
    expect(within(dialog).getByLabelText("自定义月份")).toBeChecked();
    expect(within(dialog).getByRole("button", { name: "统计月份" })).toBeInTheDocument();
    await user.click(within(dialog).getByLabelText("自定义时间区间（精确到日）"));
    fireEvent.change(within(dialog).getByLabelText("开始日期"), {
      target: { value: "2026-03-18" },
    });
    fireEvent.change(within(dialog).getByLabelText("结束日期"), {
      target: { value: "2026-04-16" },
    });
    await user.click(within(dialog).getByLabelText("交通费"));
    await user.click(within(dialog).getByRole("button", { name: "仅预览" }));

    expect(await within(dialog).findByText("预览结果")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/cost-statistics/export-preview?month=all&view=expense_type&project_scope=active&start_date=2026-03-18&end_date=2026-04-16&expense_type=${encodeURIComponent("交通费")}`,
      expect.any(Object),
    );

    await user.click(within(dialog).getByRole("button", { name: "导出" }));
    expect(await within(dialog).findByText("已导出 成本统计_2026-03-18至2026-04-16_按费用类型统计_交通费.xlsx")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/cost-statistics/export?month=all&view=expense_type&project_scope=active&start_date=2026-03-18&end_date=2026-04-16&expense_type=${encodeURIComponent("交通费")}`,
      expect.any(Object),
    );
  });
});
