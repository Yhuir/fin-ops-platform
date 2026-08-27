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

vi.mock("../features/dateTime", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../features/dateTime")>()),
  currentBusinessMonth: () => "2026-03",
  currentBusinessYear: () => "2026",
}));

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
  const viewSwitcher = screen.getByRole("group", { name: "成本统计视图切换" });
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
  expect(dialog).toHaveClass(name === "导出中心" ? "export-center-modal" : "cost-transaction-detail-drawer");
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
  const groupName = triggerName.split("：")[0];
  if (optionName === "全部") {
    await user.click(within(screen.getByRole("group", { name: groupName })).getByRole("button", { name: "全部" }));
    return;
  }
  const trigger = screen.queryByRole("button", { name: triggerName });
  if (trigger) {
    await user.click(trigger);
    const picker = await screen.findByRole("dialog", { name: /时间范围选择器/ });
    const modeName = /^\d{4}年$/.test(optionName) ? "按年" : "按月";
    const modeButton = within(picker).queryByRole("button", { name: modeName });
    if (modeButton && modeButton.getAttribute("aria-pressed") !== "true") await user.click(modeButton);
    await user.click(within(picker).getByRole("button", { name: optionName }));
    return;
  }
  const picker = screen.getByRole("group", { name: groupName });
  await user.click(within(picker).getByRole("button", { name: optionName }));
}

function expectInlineTimeSelection(optionName: string) {
  const picker = screen.getByRole("group", { name: "时间统计时间范围" });
  expect(within(picker).getByRole("button", { name: optionName })).toHaveAttribute("aria-pressed", "true");
}

describe("Cost statistics page", () => {
  test("loads only from an overflowing table near its bottom and keeps retry local", async () => {
    const user = userEvent.setup();
    const onRequestNextPage = vi.fn();
    const requestAnimationFrame = vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 1);
    const props = {
      ariaLabel: "自动加载测试表",
      columns: [{ key: "label", header: "内容", render: (row: { id: string }) => row.id }],
      rows: [{ id: "row-1" }],
      getRowKey: (row: { id: string }) => row.id,
      hasNextPage: true,
      onRequestNextPage,
    };
    const rendered = render(<CostStatisticsTable {...props} />);
    const scrollSurface = screen.getByRole("grid", { name: "自动加载测试表" }).closest(".finance-table__scroll");
    expect(scrollSurface).not.toBeNull();
    const scrollElement = scrollSurface as HTMLElement;
    expect(onRequestNextPage).not.toHaveBeenCalled();

    Object.defineProperties(scrollElement, {
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 1000 },
      scrollTop: { configurable: true, value: 500 },
    });
    fireEvent.scroll(scrollElement);

    await waitFor(() => expect(onRequestNextPage).toHaveBeenCalledTimes(1));

    rendered.rerender(<CostStatisticsTable {...props} loadMoreError="下一页加载失败" />);
    await user.click(screen.getByRole("button", { name: "重试" }));
    expect(onRequestNextPage).toHaveBeenCalledTimes(2);
    requestAnimationFrame.mockRestore();
  });

  test("locks compact premium surface and motion styling contracts", () => {
    const css = readFileSync("src/app/styles.css", "utf8");
    const pageSource = readFileSync("src/pages/CostStatisticsPage.tsx", "utf8");
    const listSource = readFileSync("src/components/cost-statistics/CostExplorerList.tsx", "utf8");

    expect(css).not.toContain(".cost-page .stat-card");
    expect(css).toMatch(/\.cost-analysis-toolbar\s*{[^}]*border:\s*0/s);
    expect(css).toMatch(/\.cost-finance-table \.finance-table__row\s*{[^}]*min-height:\s*52px/s);
    expect(css).toMatch(/\.cost-view-tabs\s*{[^}]*border:\s*1px solid var\(--fp-border-subtle\)[^}]*background:\s*var\(--fp-surface\)/s);
    expect(css).toMatch(/\.cost-view-switcher-divider\s*{[^}]*width:\s*1px[^}]*background:\s*var\(--fp-border\)/s);
    expect(css).toMatch(/\.cost-view-tab\s*{[^}]*transition:[^}]*var\(--motion-fast\)/s);
    expect(css).toMatch(/\.business-period-picker\s*{[^}]*--business-period-control-height:\s*40px/s);
    expect(css).toMatch(/\.business-period-popover\s*{[^}]*width:\s*min\(340px,\s*calc\(100vw - 24px\)\)/s);
    expect(css).toMatch(/\.cost-time-workspace,\s*\.cost-explorer-grid\s*{[^}]*height:\s*var\(--cost-workspace-height\)/s);
    expect(css).toMatch(/\.cost-analysis-layout\.time-layout\s*{[^}]*grid-template-columns:\s*minmax\(190px, 15%\) minmax\(0, 1fr\)/s);
    expect(css).not.toMatch(/\.cost-explorer-list\s*{[^}]*(?:display:\s*grid|grid-template-columns:)/s);
    expect(css).toMatch(/\.cost-explorer-item\s*{[^}]*min-height:\s*66px[^}]*transition:[^}]*var\(--motion-fast\)/s);
    expect(css).not.toMatch(/\.cost-explorer-item\s*{[^}]*overflow:\s*hidden/s);
    expect(css).toMatch(/\.cost-explorer-item-content\s*{[^}]*min-height:\s*66px[^}]*padding:\s*11px var\(--fp-space-3\)[^}]*user-select:\s*text[^}]*transition:[^}]*var\(--motion-fast\)/s);
    expect(css).not.toContain(".cost-explorer-item-select");
    expect(css).toMatch(/\.cost-explorer-item-main strong\s*{[^}]*overflow:\s*hidden[^}]*text-overflow:\s*ellipsis[^}]*white-space:\s*nowrap/s);
    expect(css).toMatch(/\.cost-explorer-item\.is-expanded \.cost-explorer-item-main strong\s*{[^}]*overflow:\s*visible[^}]*overflow-wrap:\s*anywhere[^}]*text-overflow:\s*clip[^}]*white-space:\s*normal/s);
    expect(css).toMatch(/\.cost-explorer-item\.active\s*{[^}]*box-shadow:\s*inset 0 0 0 1px/s);
    expect(css).toMatch(/\.cost-explorer-item-disclosure\s*{[^}]*position:\s*absolute[^}]*top:\s*19px[^}]*min-height:\s*28px/s);
    expect(css).not.toContain(".cost-explorer-text-popover");
    expect(css).not.toContain(".cost-explorer-text-dialog");
    expect(css).not.toContain("height: max(560px, calc(100dvh - 240px))");
    expect(css).toMatch(/\.cost-view-scope-heading \.cost-section-heading-actions\s*{[^}]*justify-content:\s*flex-end/s);
    expect(css).toMatch(/\.cost-view-scope-heading\s*{[^}]*min-height:\s*44px/s);
    expect(css).toMatch(/\.cost-view-scope-heading \.business-period-picker--segmented\s*{[^}]*flex:\s*0 0 auto/s);
    expect(css).toMatch(/\.cost-view-scope-heading \.business-period-picker--segmented \.business-period-trigger\s*{[^}]*min-width:\s*154px/s);
    expect(css).toMatch(/@media \(max-width:\s*1024px\)\s*{[\s\S]*?\.cost-view-scope-heading\s*{[^}]*flex-wrap:\s*wrap/s);
    expect(css).toMatch(/@media \(max-width:\s*1024px\)\s*{[\s\S]*?\.cost-view-scope-heading \.cost-section-heading-actions\s*{[^}]*width:\s*100%[^}]*flex-wrap:\s*wrap/s);
    expect(css).toMatch(/\.cost-table-section > \.cost-table-shell\s*{[^}]*border:\s*0[^}]*border-radius:\s*0/s);
    expect(css).not.toMatch(/\.cost-view-scope-heading \.cost-section-heading-actions\s*{[^}]*order:\s*-1/s);
    expect(pageSource).toContain("lg:grid-cols-[minmax(220px,0.92fr)_minmax(220px,0.92fr)_minmax(0,2.16fr)]");
    expect(pageSource).toContain("lg:grid-cols-[minmax(210px,0.82fr)_minmax(210px,0.82fr)_minmax(0,2.36fr)]");
    expect(pageSource).toContain("bg-[var(--fp-page)]");
    ["Button", "Chip"].forEach((symbol) => {
      expect(listSource).toContain(symbol);
    });
    ["PopoverRoot", "PopoverTrigger", "PopoverContent", "PopoverDialog"].forEach((symbol) => {
      expect(listSource).not.toContain(symbol);
    });
    expect(listSource).toContain("getPrimaryText");
    expect(listSource).not.toContain("renderPrimary");
    expect(css).toMatch(/\.cost-lock-target\.is-locked\s*{[^}]*opacity:\s*0\.62/s);
    expect(css).toMatch(/\.cost-lock-overlay\s*{[^}]*background:\s*color-mix\(in srgb, var\(--fp-page\) 20%, transparent\)[^}]*pointer-events:\s*auto/s);
    expect(css).not.toMatch(/\.cost-lock-overlay\s*{[^}]*backdrop-filter/s);
    expect(css).not.toMatch(/\.cost-lock-overlay\s*{[^}]*animation:/s);
    expect(css).not.toContain("cost-lock-breathe");
    expect(css).toMatch(/\.cost-direction-summary\s*{[^}]*grid-template-columns:\s*minmax\(0,\s*max-content\)[^}]*gap:\s*var\(--fp-space-1\)/s);
    expect(css).not.toMatch(/\.cost-direction-summary\s*{[^}]*repeat\(2,/s);
    expect(css).toMatch(/\.cost-section-heading > span,[\s\S]*\.cost-section-heading-copy > span:not\(\.cost-direction-amount\)\s*{[^}]*color:\s*var\(--fp-text-muted\)/s);
    expect(css).not.toMatch(/\.cost-section-heading span,/);
    expect(css).toMatch(/\.cost-direction-amount--aligned\s*{[^}]*grid-template-columns:\s*auto minmax\(82px,\s*max-content\)/s);
    expect(css).toMatch(/\.export-center-modal\s*{[^}]*border-radius:\s*var\(--fp-radius-lg\)/s);
    expect(css).toMatch(/\.cost-transaction-detail-drawer \.finance-drawer__body\s*{[^}]*padding:\s*0/s);
    expect(css).toMatch(/\.entity-detail-table \.finance-table__content\s*{[^}]*table-layout:\s*fixed/s);
    expect(css).not.toContain(".cost-detail-modal");
  });

  test("uses a lightweight inline interaction lock instead of a dialog while initial data is unverified", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    installMockApiFetch({ costExplorerDelayMs: 50 });

    renderCostStatisticsPage();

    const heading = await screen.findByRole("heading", { name: "成本统计" }, { timeout: PAGE_RENDER_TIMEOUT });
    const statusCopy = screen.getByText("正在加载成本统计");
    const status = statusCopy.closest('[role="status"]');
    const tablist = screen.getByRole("group", { name: "成本统计视图切换" });
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
    const bankViewButton = screen.getByRole("radio", { name: "按银行" });
    await user.click(bankViewButton);

    expect(screen.queryByText("正在加载成本统计")).not.toBeInTheDocument();
    expect(screen.queryByTestId("cost-statistics-interaction-overlay")).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "成本统计视图切换" }).closest("[inert]")).toBeNull();
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
    expect(screen.getByText("配对归集")).toBeInTheDocument();
    expect(screen.getByText("流水分析")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "按时间" })).toHaveAttribute("aria-checked", "true");
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
    expect(await within(timeGrid).findByRole("button", { name: "查看银行流水 云南航空 2026-03-18 17:02:09 860.00" })).toBeInTheDocument();
    expect(within(timeGrid).getByRole("button", { name: "查看银行流水 昆明运维服务商 2026-03-20 15:11:02 5200.00" })).toBeInTheDocument();
    expect(within(timeGrid).getByText("2026-03-10 21:27:55")).toBeInTheDocument();
    expect(within(timeGrid).queryByText("2026-03-10T21:27:55+08:00")).not.toBeInTheDocument();
    expect(within(timeGrid).queryByRole("columnheader", { name: "资金方向" })).not.toBeInTheDocument();
    expect(within(timeGrid).getAllByText("支出")[0]).toHaveClass("direction-tag");
    expect(screen.getByLabelText("支出金额 18560.00")).toHaveClass("cost-direction-amount--expense");
    expect(screen.getByLabelText("收入金额 2000.00")).toHaveClass("cost-direction-amount--income");
    expect(
      Array.from(screen.getByLabelText("时间统计方向金额").children).map((node) => node.getAttribute("aria-label")),
    ).toEqual(["支出金额 18560.00", "收入金额 2000.00"]);
    expect(screen.queryByText("总金额 20560.00")).not.toBeInTheDocument();
    expect(await within(timeGrid).findByRole("button", { name: "查看银行流水 项目客户 2026-03-22 10:30:00 2000.00" })).toBeInTheDocument();
    expect(within(timeGrid).getByText("2000.00").closest(".money-cell-value")).toHaveClass("cost-flow-amount--income");
    expectInlineTimeSelection("三月");
    expect(screen.queryByRole("button", { name: /加载更多/ })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=2026-03&view=time&page_size=50&include_statistics=false",
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=2026-03&view=time&page_size=1",
      expect.any(Object),
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=project&page_size=1",
      expect.any(Object),
    );

    await chooseScopeOption(user, "时间统计时间范围：2026年3月", "四月");

    const nextTimeGrid = await screen.findByRole("grid", { name: "按时间统计表" });
    expectProjectCostTable("按时间统计表");
    expect(await within(nextTimeGrid).findByRole("button", { name: "查看银行流水 云南冶金集团股份有限公司 2026-04-16 09:15:08 4800.00" })).toBeInTheDocument();
    expectInlineTimeSelection("四月");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=2026-04&view=time&page_size=50&include_statistics=false",
      expect.any(Object),
    );
  });

  test("loads the global manual-allocation queue lazily, validates the source matrix, and moves saved work to allocated", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();
    await findCostStatisticsHeading();

    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/cost-statistics/manual-allocations?page_size=50&status=pending",
      expect.any(Object),
    );
    await user.click(screen.getByRole("button", { name: "打开成本人工分配" }));
    const dialog = await screen.findByRole("dialog", { name: "成本人工分配" });
    const projectA = within(dialog).getByRole("textbox", { name: "项目 A分配至昆明设备供应商的金额" });
    const projectB = within(dialog).getByRole("textbox", { name: "项目 B分配至昆明设备供应商的金额" });

    expect(projectA).toHaveValue("");
    expect(projectB).toHaveValue("");
    expect(within(dialog).getByRole("button", { name: "保存分配" })).toBeDisabled();

    await user.type(projectA, "900.00");
    await user.type(projectB, "100.00");
    expect(within(dialog).getByText("流水已填 1000.00 / 1000.00")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "保存分配" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/manual-allocations/relation-manual-001",
      expect.objectContaining({ method: "PUT" }),
    ));
    expect(await within(dialog).findByText("当前没有待人工分配的关系。")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("radio", { name: "人工已分配 1" }));
    expect(await within(dialog).findByText("人工已分配")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "保存修改" })).toBeEnabled();
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
        `/api/cost-statistics/explorer?scope=2026-03&view=time&query=${encodeURIComponent("昆明设备")}&page_size=50&include_statistics=false`,
        expect.any(Object),
      );
    });
    expect(heading).toBeInTheDocument();
    expect(screen.queryByTestId("cost-statistics-interaction-overlay")).not.toBeInTheDocument();
    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
  });

  test("closes tag rules drawer after canonical save without waiting for a read model barrier", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "无 OA 成本范围" }));
    const drawer = await screen.findByRole("dialog", { name: "无 OA 成本范围" });
    await user.click(within(drawer).getByRole("button", { name: "新增虚拟项目" }));
    await user.type(within(drawer).getByLabelText("虚拟项目名称"), "云南溯源无 OA 分类");
    await user.click(within(drawer).getByText("材料费"));

    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "无 OA 成本范围" })).not.toBeInTheDocument();
    });
    const saveCall = fetchMock.mock.calls.find(([request, init]) =>
      request === "/api/cost-statistics/no-oa-rules" && init?.method === "PUT",
    );
    const saveBody = JSON.parse(String(saveCall?.[1]?.body));
    expect(saveBody.projects[0]).toMatchObject({
      display_name: "云南溯源无 OA 分类",
      tag_codes: ["fee"],
    });
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/operation-barrier/status",
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=2026-03&view=time&page_size=50&include_statistics=false",
      expect.any(Object),
    );
  });

  test("keeps time/tag rules independent and refreshes only the visible raw-bank view", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    const initialExplorerCallCount = fetchMock.mock.calls.filter(([request]) =>
      String(request).startsWith("/api/cost-statistics/explorer?scope=2026-03&view=time"),
    ).length;
    await user.click(screen.getByRole("button", { name: "按标签/按时间标签规则" }));
    const drawer = await screen.findByRole("dialog", { name: "按标签/按时间标签规则" });
    expect(within(drawer).getByText("当前：全部标签（自动包含新标签）")).toBeInTheDocument();
    expect(within(drawer).getByText("未标记流水")).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "清空" }));
    expect(within(drawer).getByText("当前：自定义范围")).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => expect(screen.queryByRole("dialog", { name: "按标签/按时间标签规则" })).not.toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/time-tag-rules",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ expected_version: 1, mode: "custom", selected_tag_codes: [] }),
      }),
    );
    await waitFor(() => {
      expect(fetchMock.mock.calls.filter(([request]) =>
        String(request).startsWith("/api/cost-statistics/explorer?scope=2026-03&view=time"),
      ).length).toBeGreaterThan(initialExplorerCallCount);
    });
    expect(fetchMock).not.toHaveBeenCalledWith("/api/cost-statistics/no-oa-rules", expect.any(Object));
  });

  test("disables tag rules save when API marks the rule set read-only", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costTagRulesCanSave: false });

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "无 OA 成本范围" }));
    const drawer = await screen.findByRole("dialog", { name: "无 OA 成本范围" });

    expect(within(drawer).getByRole("button", { name: "保存" })).toBeDisabled();
  });

  test("groups no-OA child tags under one parent and keeps singleton leaves selectable", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "无 OA 成本范围" }));
    const drawer = await screen.findByRole("dialog", { name: "无 OA 成本范围" });
    await user.click(within(drawer).getByRole("button", { name: "新增虚拟项目" }));
    await user.type(within(drawer).getByLabelText("虚拟项目名称"), "项目 A");

    const feeGroup = within(drawer).getByRole("group", { name: "费用" });
    expect(within(drawer).getAllByText("费用")).toHaveLength(1);
    expect(within(drawer).queryByRole("checkbox", { name: "费用" })).not.toBeInTheDocument();
    expect(within(feeGroup).getByRole("checkbox", { name: "材料费" })).toBeInTheDocument();
    expect(within(feeGroup).getByRole("checkbox", { name: "过路费（ETC）" })).toBeInTheDocument();
    expect(within(drawer).getByRole("checkbox", { name: "内部往来款" })).toBeInTheDocument();
    expect(within(drawer).getByText("请至少选择一个标签。")).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "保存" })).toBeDisabled();

    await user.click(within(drawer).getByRole("checkbox", { name: "内部往来款" }));

    expect(within(drawer).queryByText("请至少选择一个标签。")).not.toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "保存" })).toBeEnabled();
  });

  test("shows no-OA tags as mutually exclusive across virtual projects", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "无 OA 成本范围" }));
    const drawer = await screen.findByRole("dialog", { name: "无 OA 成本范围" });
    await user.click(within(drawer).getByRole("button", { name: "新增虚拟项目" }));
    const firstName = within(drawer).getByLabelText("虚拟项目名称");
    await user.type(firstName, "项目 A{Enter}");
    await user.click(within(drawer).getByText("材料费"));
    await user.click(within(drawer).getByRole("button", { name: "新增虚拟项目" }));
    await user.type(within(drawer).getByLabelText("虚拟项目名称"), "项目 B{Enter}");

    expect(within(drawer).getByText("已归属：项目 A")).toBeInTheDocument();
    expect(within(drawer).getByRole("checkbox", { name: /材料费/ })).toBeDisabled();
  });

  test("project view drills down from project to expense type to transaction from left to right", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "按项目" }));
    expect(await screen.findByRole("button", { name: "项目统计时间范围：年月" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=project&page_size=50&include_statistics=false",
      expect.any(Object),
    );
    expect(screen.getByText("昆明卷烟厂动力设备控制系统升级改造项目")).toBeInTheDocument();
    expect(screen.getByText("昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /项目范围：/ })).not.toBeInTheDocument();

    const projectLane = screen.getByRole("heading", { name: "项目名" }).closest(".cost-explorer-lane");
    expect(projectLane).not.toBeNull();
    expect(within(projectLane as HTMLElement).getByText("47.4%")).toBeInTheDocument();
    expect(within(projectLane as HTMLElement).getByLabelText("支出 13360.00")).toHaveClass("cost-direction-amount--aligned");
    await user.click(within(projectLane as HTMLElement).getByRole("button", { name: /云南溯源科技/ }));

    const expenseLane = screen.getByRole("heading", { name: "费用类型" }).closest(".cost-explorer-lane");
    expect(expenseLane).not.toBeNull();
    expect(within(expenseLane as HTMLElement).getByText("设备货款及材料费")).toBeInTheDocument();
    expect(within(expenseLane as HTMLElement).getByText("交通费")).toBeInTheDocument();
    expect(within(expenseLane as HTMLElement).getByText("93.6%")).toBeInTheDocument();
    expect(within(expenseLane as HTMLElement).getByText("6.4%")).toBeInTheDocument();

    await user.click(within(expenseLane as HTMLElement).getByRole("button", { name: /设备货款及材料费/ }));

    const transactionTable = screen.getByRole("grid", { name: "项目成本明细表" });
    expectProjectCostTable("项目成本明细表");
    expect(within(transactionTable).getByRole("columnheader", { name: "申请/报销人" })).toBeInTheDocument();
    expect(within(transactionTable).getByText("张三、李四")).toBeInTheDocument();
    const projectTransactionTrigger = await within(transactionTable).findByRole("button", {
      name: "查看OA 成本归集 云南溯源科技 2026-03-10 21:27:55 10000.00",
    });
    expect(projectTransactionTrigger).toBeInTheDocument();
    expect(within(projectTransactionTrigger).getByText("2026-03-10 21:27:55")).toHaveClass("cost-transaction-time-chip");
    expect(await within(transactionTable).findByRole("button", { name: "查看OA 成本归集 云南溯源科技 2026-03-12 08:40:12 2500.00" })).toBeInTheDocument();
    expect(within(transactionTable).queryByRole("columnheader", { name: "时间" })).not.toBeInTheDocument();
    expect(within(transactionTable).queryByRole("columnheader", { name: "资金方向" })).not.toBeInTheDocument();

    await user.click(within(transactionTable).getByRole("button", { name: "查看OA 成本归集 云南溯源科技 2026-03-10 21:27:55 10000.00" }));

    const dialog = await screen.findByRole("dialog", { name: "OA 成本归集明细" });
    expectProjectCostDialog("OA 成本归集明细");
    expect(dialog).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/cost-statistics/allocations/${encodeURIComponent("cost-txn-001:allocation:PLC 模块采购")}?view=project&scope=all`,
      expect.any(Object),
    );
    expect(screen.getAllByText("PLC 模块采购").length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText("工商银行 账户 0001").length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText("银行账户").length).toBeGreaterThan(0);
    expect(within(dialog).queryByText("资金方向")).not.toBeInTheDocument();
    expect(within(dialog).getByRole("heading", { name: "基本信息" })).toBeInTheDocument();
    expect(within(dialog).queryByText("OA 单号")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("子付款项 ID")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("关系组")).not.toBeInTheDocument();
    expect(within(dialog).getByRole("heading", { name: "关系内银行流水" })).toBeInTheDocument();
    expect(within(dialog).getAllByText("云南溯源科技").length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText("设备货款及材料费").length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText(/10000\.00/).length).toBeGreaterThan(0);
    expect(within(dialog).queryByText(/查看当前成本流水|展示这条支出流水|用于快速核对|保留原始银行流水/)).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "关闭OA 成本归集明细" }));
    expect(screen.queryByRole("dialog", { name: "OA 成本归集明细" })).not.toBeInTheDocument();
  });

  test("opens the transaction drawer immediately without page-level loading copy", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costDetailDelayMs: 500 });

    renderCostStatisticsPage();
    const transactionTable = await screen.findByRole("grid", { name: "按时间统计表" });
    await user.click(within(transactionTable).getByRole("button", { name: "查看银行流水 昆明设备供应商 2026-03-10 21:27:55 10000.00" }));

    const drawer = screen.getByRole("dialog", { name: "银行流水详情" });
    expect(drawer).toHaveClass("cost-transaction-detail-drawer");
    expect(within(drawer).getByRole("status", { name: "银行流水详情加载中" })).toBeInTheDocument();
    expect(screen.queryByText(/正在加载流水/)).not.toBeInTheDocument();
    expect(document.querySelector('button[aria-label="刷新成本统计"]')).not.toBeDisabled();
    const exportButton = Array.from(document.querySelectorAll("button"))
      .find((button) => button.textContent?.trim() === "导出中心");
    expect(exportButton).toBeInstanceOf(HTMLButtonElement);
    expect(exportButton).not.toBeDisabled();
    expect((await within(drawer).findAllByText("设备采购款")).length).toBeGreaterThan(0);
    expect(within(drawer).queryByRole("status", { name: "银行流水详情加载中" })).not.toBeInTheDocument();
  });

  test("keeps transaction detail failures inside the drawer and retries locally", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costDetailFailuresBeforeSuccess: 1 });

    renderCostStatisticsPage();
    const transactionTable = await screen.findByRole("grid", { name: "按时间统计表" });
    await user.click(within(transactionTable).getByRole("button", { name: "查看银行流水 昆明设备供应商 2026-03-10 21:27:55 10000.00" }));

    const drawer = screen.getByRole("dialog", { name: "银行流水详情" });
    expect(await within(drawer).findByRole("alert")).toHaveTextContent("银行流水详情加载失败，请稍后重试。");
    expect(screen.queryByText("无法确认成本数据状态")).not.toBeInTheDocument();
    expect(document.querySelector('[role="grid"][aria-label="按时间统计表"]')).not.toBeNull();

    await user.click(within(drawer).getByRole("button", { name: "重试" }));
    expect((await within(drawer).findAllByText("设备采购款")).length).toBeGreaterThan(0);
    expect(within(drawer).queryByRole("alert")).not.toBeInTheDocument();
  });

  test("keeps upstream lanes and clears only dependent lanes during project drilldown", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costExplorerDelayMs: 50 });

    renderCostStatisticsPage();
    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "按项目" }));

    const projectLane = (await screen.findByRole("heading", { name: "项目名" })).closest(".cost-explorer-lane");
    expect(projectLane).not.toBeNull();
    await user.click(within(projectLane as HTMLElement).getByRole("button", { name: /云南溯源科技/ }));

    const expenseLane = screen.getByRole("heading", { name: "费用类型" }).closest(".cost-explorer-lane");
    const transactionLane = screen.getByRole("heading", { name: "成本明细" }).closest(".cost-explorer-lane");
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

    expect(await screen.findByRole("grid", { name: "项目成本明细表" })).toBeInTheDocument();
  });

  test("sends one canonical request per project or scope selection", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ costExplorerDelayMs: 50 });

    renderCostStatisticsPage();
    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "按项目" }));

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
    await chooseScopeOption(user, "项目统计时间范围：年月", "四月");
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
      await user.click(screen.getByRole("radio", { name: "按项目" }));

      const projectLane = screen.getByRole("heading", { name: "项目名" }).closest(".cost-explorer-lane");
      expect(projectLane).not.toBeNull();
      await user.click(within(projectLane as HTMLElement).getByRole("button", { name: /云南溯源科技/ }));

      const expenseLane = screen.getByRole("heading", { name: "费用类型" }).closest(".cost-explorer-lane");
      expect(expenseLane).not.toBeNull();
      await user.click(within(expenseLane as HTMLElement).getByRole("button", { name: /设备货款及材料费/ }));

      const transactionTable = screen.getByRole("grid", { name: "项目成本明细表" });
      expect(await within(transactionTable).findAllByRole("button", { name: /^查看OA 成本归集 云南溯源科技 2026-03-10 21:27:55/ })).toHaveLength(2);
      expect(within(transactionTable).getByRole("button", { name: "查看OA 成本归集 云南溯源科技 2026-03-10 21:27:55 10000.00" })).toBeInTheDocument();
      expect(within(transactionTable).getByRole("button", { name: "查看OA 成本归集 云南溯源科技 2026-03-10 21:27:55 1250.00" })).toBeInTheDocument();
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
    await user.click(screen.getByRole("radio", { name: "按项目" }));

    expect(await screen.findByRole("button", { name: "项目统计时间范围：年月" })).toBeInTheDocument();
    const projectLane = () => screen.getByRole("heading", { name: "项目名" }).closest(".cost-explorer-lane") as HTMLElement;
    expect(within(projectLane()).getByText("云南溯源科技")).toBeInTheDocument();
    expect(within(projectLane()).getByText("昆明卷烟厂动力设备控制系统升级改造项目")).toBeInTheDocument();
    expect(within(projectLane()).getByText("昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目")).toBeInTheDocument();

    await chooseScopeOption(user, "项目统计时间范围：年月", "2026年");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(await within(projectLane()).findByText("云南溯源科技")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "项目统计时间范围：2026年" })).toBeInTheDocument();

    await chooseScopeOption(user, "项目统计时间范围：2026年", "四月");
    expect(screen.getByRole("button", { name: "项目统计时间范围：2026年4月" })).toBeInTheDocument();

    expect(await within(projectLane()).findByText("昆明卷烟厂动力设备控制系统升级改造项目")).toBeInTheDocument();
    expect(within(projectLane()).queryByText("云南溯源科技")).not.toBeInTheDocument();

    await chooseScopeOption(user, "项目统计时间范围：2026年4月", "全部");
    expect(await within(projectLane()).findByText("云南溯源科技")).toBeInTheDocument();
    expect(await within(projectLane()).findByText("昆明卷烟厂动力设备控制系统升级改造项目")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "项目统计时间范围：年月" })).toBeInTheDocument();
  });

  test("expense type view shows time, project name, amount and expense content in a drawer drilldown", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "按费用类型" }));
    await waitForCostStatisticsReady();

    const expenseLane = screen.getByRole("heading", { name: "费用类型" }).closest(".cost-explorer-lane");
    expect(expenseLane).not.toBeNull();
    expect(within(expenseLane as HTMLElement).getByLabelText("支出 860.00")).toHaveClass("cost-direction-amount--aligned");
    await user.click(within(expenseLane as HTMLElement).getByRole("button", { name: /交通费/ }));

    const transactionTable = screen.getByRole("grid", { name: "按费用类型成本明细表" });
    expectProjectCostTable("按费用类型成本明细表");
    expect(within(transactionTable).getByRole("columnheader", { name: "项目名 / 申请/报销人" })).toBeInTheDocument();
    expect(within(transactionTable).getByText("赵六")).toBeInTheDocument();
    const transactionTime = await within(transactionTable).findByText("2026-03-18 17:02:09");
    expect(transactionTime).toHaveClass("cost-transaction-time-chip");
    expect(within(transactionTable).getByText("云南溯源科技")).toBeInTheDocument();
    expect(within(transactionTable).getByText("860.00")).toBeInTheDocument();
    expect(within(transactionTable).getByText("项目现场往返交通")).toBeInTheDocument();
    expect(within(transactionTable).queryByRole("columnheader", { name: "资金方向" })).not.toBeInTheDocument();
    expect(within(transactionTable).queryByRole("columnheader", { name: "时间" })).not.toBeInTheDocument();
    await user.click(await within(transactionTable).findByRole("button", { name: "查看OA 成本归集 云南溯源科技 2026-03-18 17:02:09 860.00" }));
    const dialog = await screen.findByRole("dialog", { name: "OA 成本归集明细" });
    expectProjectCostDialog("OA 成本归集明细");
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getAllByText("招商银行 账户 2201").length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText("银行账户").length).toBeGreaterThan(0);
  });

  test("bank tag view drills down from primary tag to sub tag to transaction", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "按标签" }));

    expect(screen.getByRole("heading", { name: "按标签统计" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "流水标签统计时间范围：2026年3月" })).toBeInTheDocument();
    const primaryLane = screen.getByRole("heading", { name: "主标签" }).closest(".cost-explorer-lane");
    expect(primaryLane).not.toBeNull();
    expect(within(primaryLane as HTMLElement).getByText("项目开销")).toBeInTheDocument();
    expect(within(primaryLane as HTMLElement).getByText("差旅交通")).toBeInTheDocument();
    expect(within(primaryLane as HTMLElement).getByText("经营收入")).toBeInTheDocument();
    expect(screen.getByLabelText("支出金额 18560.00")).toHaveClass("cost-direction-amount--expense");
    expect(screen.getByLabelText("收入金额 2000.00")).toHaveClass("cost-direction-amount--income");
    expect(
      Array.from(screen.getByLabelText("标签统计方向金额").children).map((node) => node.getAttribute("aria-label")),
    ).toEqual(["支出金额 18560.00", "收入金额 2000.00"]);
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
    ).toEqual(["收入"]);
    expect(within(incomeOnlyRow).queryByLabelText("支出")).not.toBeInTheDocument();
    expect(within(incomeOnlyRow).queryByText("0.00")).not.toBeInTheDocument();
    const expenseOnlyRow = within(primaryLane as HTMLElement).getByRole("button", { name: /项目开销/ });
    expect(expenseOnlyRow).toHaveTextContent("收入 0 笔");
    expect(
      Array.from(expenseOnlyRow.querySelectorAll(".cost-direction-amount-label")).map((node) => node.textContent),
    ).toEqual(["支出"]);
    expect(within(expenseOnlyRow).queryByLabelText("收入")).not.toBeInTheDocument();

    await user.click(expenseOnlyRow);

    const subLane = screen.getByRole("heading", { name: "子标签" }).closest(".cost-explorer-lane");
    expect(subLane).not.toBeNull();
    expect(within(subLane as HTMLElement).getByText("设备材料")).toBeInTheDocument();
    const expenseOnlySubRow = within(subLane as HTMLElement).getByRole("button", { name: /设备材料/ });
    expect(expenseOnlySubRow).toHaveTextContent("收入 0 笔");
    expect(
      Array.from(expenseOnlySubRow.querySelectorAll(".cost-direction-amount-label")).map((node) => node.textContent),
    ).toEqual(["支出"]);
    expect(within(expenseOnlySubRow).queryByLabelText("收入")).not.toBeInTheDocument();
    await user.click(expenseOnlySubRow);

    const transactionTable = screen.getByRole("grid", { name: "流水标签对应流水表" });
    expectProjectCostTable("流水标签对应流水表");
    expect(
      await within(transactionTable).findByRole("button", { name: "查看银行流水 昆明设备供应商 2026-03-10 21:27:55 10000.00" }),
    ).toBeInTheDocument();
    expect(
      await within(transactionTable).findByRole("button", { name: "查看银行流水 昆明设备供应商 2026-03-12 08:40:12 2500.00" }),
    ).toBeInTheDocument();
    expect(within(transactionTable).getByText("2026-03-10 21:27:55")).toHaveClass("cost-transaction-time-chip");
    expect(within(transactionTable).queryByRole("columnheader", { name: "时间" })).not.toBeInTheDocument();

    await user.click(within(transactionTable).getByRole("button", { name: "查看银行流水 昆明设备供应商 2026-03-10 21:27:55 10000.00" }));

    expect(await screen.findByRole("dialog", { name: "银行流水详情" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/bank-transactions/cost-txn-001?view=bank_tag&scope=2026-03",
      expect.any(Object),
    );
  });

  test("exports bank tag income and expense rows with directional summaries", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "按标签" }));
    await user.click(screen.getByRole("button", { name: "导出中心" }));
    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
    expect(within(dialog).getByRole("button", { name: "按标签" })).toHaveAttribute("aria-pressed", "true");

    await user.click(within(dialog).getByRole("button", { name: "仅预览" }));

    expect(await within(dialog).findByText("支出金额 18560.00")).toHaveClass("cost-direction-amount--expense");
    expect(within(dialog).getByText("收入金额 2000.00")).toHaveClass("cost-direction-amount--income");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/export-preview?month=2026-03&view=bank_tag",
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
    expect(screen.queryByText("当前时间范围没有可用于流水统计的收入或支出流水。")).not.toBeInTheDocument();
    expectInlineTimeSelection("五月");
    await chooseScopeOption(user, "时间统计时间范围：2026年5月", "三月");
    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
  });

  test("bank view supports all-time, year, and month drilldown from bank to project to transaction", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "按银行" }));
    await waitForCostStatisticsReady();

    expect(await screen.findByRole("button", { name: "银行统计时间范围：年月" })).toBeInTheDocument();
    const bankLane = screen.getByRole("heading", { name: "银行账户" }).closest(".cost-explorer-lane");
    expect(bankLane).not.toBeNull();
    expect(within(bankLane as HTMLElement).getByText("工商银行 账户 0001")).toBeInTheDocument();
    expect(within(bankLane as HTMLElement).getByText("平安银行 账户 8821")).toBeInTheDocument();
    expect(within(bankLane as HTMLElement).getByText("民生银行 账户 9486")).toBeInTheDocument();
    expect(within(bankLane as HTMLElement).getByText("44.4%")).toBeInTheDocument();
    expect(screen.getByLabelText("支出金额 28160.00")).toBeInTheDocument();
    expect(within(bankLane as HTMLElement).getByLabelText("支出 12500.00")).toHaveClass("cost-direction-amount--aligned");

    await user.click(within(bankLane as HTMLElement).getByRole("button", { name: /工商银行 账户 0001/ }));

    const projectLane = screen.getByRole("heading", { name: "项目名" }).closest(".cost-explorer-lane");
    expect(projectLane).not.toBeNull();
    expect(within(projectLane as HTMLElement).getByText("云南溯源科技")).toBeInTheDocument();
    expect(within(projectLane as HTMLElement).getByText("100.0%")).toBeInTheDocument();

    await user.click(within(projectLane as HTMLElement).getByRole("button", { name: /云南溯源科技/ }));
    const transactionTable = screen.getByRole("grid", { name: "银行成本明细表" });
    expectProjectCostTable("银行成本明细表");
    expect(within(transactionTable).getByRole("columnheader", { name: "申请/报销人" })).toBeInTheDocument();
    expect(within(transactionTable).getByText("张三、李四")).toBeInTheDocument();
    expect(
      await within(transactionTable).findByRole("button", { name: "查看OA 成本归集 云南溯源科技 2026-03-10 21:27:55 10000.00" }),
    ).toBeInTheDocument();
    expect(
      await within(transactionTable).findByRole("button", { name: "查看OA 成本归集 云南溯源科技 2026-03-12 08:40:12 2500.00" }),
    ).toBeInTheDocument();
    expect(within(transactionTable).getByText("2026-03-10 21:27:55")).toHaveClass("cost-transaction-time-chip");
    expect(within(transactionTable).queryByRole("columnheader", { name: "时间" })).not.toBeInTheDocument();

    await chooseScopeOption(user, "银行统计时间范围：年月", "2026年");
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
    expect(screen.getByLabelText("支出金额 9600.00")).toBeInTheDocument();
  });

  test("time and expense type scopes stay independent with one range control per view", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "按时间" }));
    await chooseScopeOption(user, "时间统计时间范围：2026年3月", "四月");
    await screen.findByRole("grid", { name: "按时间统计表" });
    expectInlineTimeSelection("四月");
    expect(screen.getByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "查看银行流水 云南冶金集团股份有限公司 2026-04-16 09:15:08 4800.00" })).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "按费用类型" }));
    await chooseScopeOption(user, "费用类型统计时间范围：2026年3月", "2026年");
    expect(screen.getByRole("button", { name: "费用类型统计时间范围：2026年" })).toBeInTheDocument();
    expect(await screen.findByText("交通费")).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "按时间" }));
    expectInlineTimeSelection("四月");
    expect(await screen.findByRole("button", { name: "查看银行流水 云南冶金集团股份有限公司 2026-04-16 09:15:08 4800.00" })).toBeInTheDocument();
  });

  test("time view keeps its period picker permanently visible in the fixed left rail", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    const timeTab = screen.getByRole("radio", { name: "按时间" });
    await user.click(timeTab);
    const rail = document.querySelector(".cost-time-filter-rail");
    expect(rail).not.toBeNull();
    expect(within(rail as HTMLElement).getByRole("button", { name: "全部" })).toBeInTheDocument();
    expect(within(rail as HTMLElement).getByRole("button", { name: "三月" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("dialog", { name: "时间统计时间范围选择器" })).not.toBeInTheDocument();
  });

  test("popover period picker closes when clicking the trigger again or clicking outside", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "按项目" }));
    const monthScopeButton = await screen.findByRole("button", { name: "项目统计时间范围：年月" });
    expect(screen.queryByRole("button", { name: "按年" })).not.toBeInTheDocument();

    await user.click(monthScopeButton);
    expect(screen.getByRole("button", { name: "按年" })).toBeInTheDocument();

    await user.click(monthScopeButton);
    expect(screen.queryByRole("button", { name: "按年" })).not.toBeInTheDocument();
    await user.click(monthScopeButton);
    expect(screen.getByRole("button", { name: "按年" })).toBeInTheDocument();
    await user.click(document.body);
    expect(screen.queryByRole("button", { name: "按年" })).not.toBeInTheDocument();
  });

  test("only replaces the content surface while a new view is loading", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costExplorerDelayMs: 50 });

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "按银行" }));

    expect(screen.queryByText("正在加载成本统计")).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "成本统计视图切换" }).closest("[inert]")).toBeNull();
    expect(screen.queryByRole("grid", { name: "按时间统计表" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("正在加载成本统计内容")).toHaveAttribute("aria-busy", "true");
    expect(await screen.findByRole("heading", { name: "按银行统计" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "成本统计视图切换" }).closest("[inert]")).toBeNull();
    expect(screen.getByRole("button", { name: "银行统计时间范围：年月" })).toBeInTheDocument();
  });

  test("only replaces the content surface while the time range is loading", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costExplorerDelayMs: 50 });

    renderCostStatisticsPage();
    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    await chooseScopeOption(user, "时间统计时间范围：2026年3月", "四月");

    expectInlineTimeSelection("四月");
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
      "/api/cost-statistics/explorer?scope=2026-03&view=time&page_size=50&include_statistics=false",
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
            === "/api/cost-statistics/explorer?scope=2026-03&view=time&page_size=50&include_statistics=false"
        ));
        expect(explorerCalls).toHaveLength(1);
      },
      { timeout: PAGE_RENDER_TIMEOUT },
    );
  });

  test("manual refresh reloads scoped content and global statistics", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const initialUrl = "/api/cost-statistics/explorer?scope=2026-03&view=time&page_size=50&include_statistics=false";

    renderCostStatisticsPage();

    expect(await screen.findByRole("grid", { name: "按时间统计表" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "刷新成本统计" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.filter(([request]) => String(request) === initialUrl)).toHaveLength(2);
      expect(fetchMock.mock.calls.filter(([request]) => String(request) === "/api/cost-statistics/explorer?scope=2026-03&view=time&page_size=1")).toHaveLength(2);
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
    expect(within(dialog).getByRole("button", { name: "按时间" })).toHaveAttribute("aria-pressed", "true");
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=project&page_size=1",
      expect.any(Object),
    );
    expect(within(dialog).getByLabelText("自定义月份")).toBeChecked();
    expect(within(dialog).getByRole("button", { name: /^统计月份：/ })).toBeInTheDocument();
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
      "/api/cost-statistics/export-preview?month=all&view=time&start_date=2026-03-10&end_date=2026-04-16",
      expect.any(Object),
    );
    expect(within(dialog).getByText("预计导出 7 条流水")).toBeInTheDocument();
    expect(within(dialog).getByText("支出金额 28160.00")).toHaveClass("cost-direction-amount--expense");
    expect(within(dialog).getByText("收入金额 2000.00")).toHaveClass("cost-direction-amount--income");

    await user.click(within(dialog).getByRole("button", { name: "导出" }));
    expect(await within(dialog).findByText("已导出 成本统计_2026-03-10至2026-04-16_按时间统计.xlsx")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/export?month=all&view=time&start_date=2026-03-10&end_date=2026-04-16",
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
      "/api/cost-statistics/explorer?scope=all&view=project&page_size=1",
      expect.any(Object),
    );

    await user.click(within(dialog).getByRole("button", { name: "按项目" }));

    await waitFor(() => expect(within(dialog).getByLabelText("云南溯源科技")).toBeChecked());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=project&page_size=1&include_statistics=false",
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
    await user.click(screen.getByRole("radio", { name: "按项目" }));
    expect(await screen.findByRole("button", { name: "项目统计时间范围：年月" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "导出中心" }));
    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
    expectProjectCostDialog("导出中心");
    expect(within(dialog).getByRole("button", { name: "按项目" })).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(within(dialog).getByLabelText("云南溯源科技")).toBeChecked());
    await user.click(within(dialog).getByLabelText("交通费"));
    await user.click(within(dialog).getByLabelText("经营/办公费用"));
    await user.click(within(dialog).getByLabelText("人工费/劳务费/服务费"));
    await user.click(within(dialog).getByRole("button", { name: "仅预览" }));

    expect(await within(dialog).findByText("预览结果")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/cost-statistics/export-preview?month=all&view=project&project_name=${encodeURIComponent("云南溯源科技")}&aggregate_by=month&expense_type=${encodeURIComponent("设备货款及材料费")}`,
      expect.any(Object),
    );
    expect(within(dialog).getByText("预计导出 2 条流水")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "导出" }));
    expect(await within(dialog).findByText("已导出 成本统计_全部期间_按项目统计_按月_云南溯源科技.xlsx")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/cost-statistics/export?month=all&view=project&project_name=${encodeURIComponent("云南溯源科技")}&aggregate_by=month&expense_type=${encodeURIComponent("设备货款及材料费")}&include_oa_details=true&include_invoice_details=true&include_exception_rows=true&include_ignored_rows=true&include_expense_content_summary=true&sort_by=time`,
      expect.any(Object),
    );
  });

  test("supports expense type export center filters with range and multi-select", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderCostStatisticsPage();

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "按费用类型" }));
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=project&page_size=1",
      expect.any(Object),
    );
    await user.click(screen.getByRole("button", { name: "导出中心" }));

    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=expense_type&page_size=1&include_statistics=false",
      expect.any(Object),
    );
    expectProjectCostDialog("导出中心");
    expect(within(dialog).getByRole("button", { name: "按费用类型" })).toHaveAttribute("aria-pressed", "true");
    expect(within(dialog).getByLabelText("自定义月份")).toBeChecked();
    expect(within(dialog).getByRole("button", { name: /^统计月份：/ })).toBeInTheDocument();
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
      `/api/cost-statistics/export-preview?month=all&view=expense_type&start_date=2026-03-18&end_date=2026-04-16&expense_type=${encodeURIComponent("交通费")}`,
      expect.any(Object),
    );

    await user.click(within(dialog).getByRole("button", { name: "导出" }));
    expect(await within(dialog).findByText("已导出 成本统计_2026-03-18至2026-04-16_按费用类型统计_交通费.xlsx")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/cost-statistics/export?month=all&view=expense_type&start_date=2026-03-18&end_date=2026-04-16&expense_type=${encodeURIComponent("交通费")}`,
      expect.any(Object),
    );
  });
});
