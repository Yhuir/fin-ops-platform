import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ClipboardCheck,
  FileInput,
  FileOutput,
  FileQuestion,
  FileText,
  Inbox,
  ListChecks,
  Ticket,
  WalletCards,
} from "lucide-react";
import { vi } from "vitest";

import App from "../app/App";
import { isSidebarDisclosureItem, sidebarGroups } from "../components/shell/sidebarItems";
import { currentBusinessMonth } from "../features/dateTime";
import { installMockApiFetch } from "./apiMock";

const WORKBENCH_RENDER_TIMEOUT = 3000;

function stubShellCompactMode(matches: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === "(max-width: 899.95px)" ? matches : false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

describe("Finance operations shell", () => {
  test.each([
    ["admin", true, true],
    ["full_access", true, false],
    ["read_export_only", false, false],
    ["denied", false, false],
  ] as const)(
    "keeps Settings ACL controls on the canonical %s tier",
    async (accessTier, canSaveSettings, canAdminAccess) => {
      window.history.pushState({}, "", "/settings");
      installMockApiFetch({
        sessionMode: accessTier === "denied" ? "forbidden" : "authorized",
        sessionAccessTier: accessTier,
        sessionUsername: accessTier === "admin" ? "YNSYLP005" : accessTier === "denied" ? "YNSYLP006" : "E2EUSER001",
      });

      render(<App />);

      if (accessTier === "denied") {
        expect(await screen.findByRole("heading", { name: "无权访问财务运营平台" })).toBeInTheDocument();
        expect(screen.queryByTestId("settings-page")).not.toBeInTheDocument();
        return;
      }

      expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
      const settingsTree = await screen.findByRole("tree", { name: "设置分类" });
      expect(within(settingsTree).getAllByRole("treeitem").filter((item) => item.textContent?.includes("访问账户"))).toHaveLength(
        canAdminAccess ? 1 : 0,
      );
      expect(screen.getByRole("button", { name: "保存设置" })).toHaveProperty("disabled", !canSaveSettings);
    },
  );

  test("stops a denied direct /fin-ops/ visit before the business tree mounts", async () => {
    window.history.pushState({}, "", "/fin-ops/");
    const fetchMock = installMockApiFetch({
      sessionMode: "forbidden",
      sessionUsername: "YNSYLP006",
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "无权访问财务运营平台" })).toBeInTheDocument();
    expect(screen.queryByTestId("settings-page")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /未配对.*布局与栏显示/ })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).startsWith("/api/workbench?"))).toBe(false);
  });

  test("orders finance business above system operations in the sidebar", () => {
    expect(sidebarGroups.map((group) => group.title)).toEqual(["财务业务", "系统操作"]);
  });

  test("places selected invoice pages at the bottom of finance before system operations", () => {
    const financeLabels = sidebarGroups.find((group) => group.title === "财务业务")?.items.map((item) => item.label);
    const systemLabels = sidebarGroups.find((group) => group.title === "系统操作")?.items.map((item) => item.label);
    expect(financeLabels).toBeDefined();
    expect(systemLabels).toBeDefined();
    expect(financeLabels?.slice(-4)).toEqual(["税金抵扣", "待找发票", "进项发票使用情况", "销项发票收款情况"]);
    expect(systemLabels?.[0]).toBe("设置");
  });

  test("assigns sidebar icons from each page's business facts", () => {
    const sidebarItems = sidebarGroups.flatMap((group) => group.items.flatMap((item) => (
      isSidebarDisclosureItem(item) ? [item, ...item.children] : [item]
    )));
    const iconByLabel = new Map(sidebarItems.map((item) => [item.label, item.icon]));

    expect(iconByLabel.get("待找发票")).toBe(FileQuestion);
    expect(iconByLabel.get("进项发票使用情况")).toBe(FileInput);
    expect(iconByLabel.get("OA待付款核对")).toBe(ClipboardCheck);
    expect(iconByLabel.get("销项发票收款情况")).toBe(FileOutput);
    expect(iconByLabel.get("流水规则批量处理")).toBe(ListChecks);
    expect(iconByLabel.get("批量账务")).toBe(WalletCards);
    expect(iconByLabel.get("ETC票据管理")).toBe(Ticket);
    expect(iconByLabel.get("银行流水导入")).toBe(Inbox);
    expect(iconByLabel.get("发票导入")).toBe(FileText);

    expect(new Set([
      iconByLabel.get("待找发票"),
      iconByLabel.get("进项发票使用情况"),
      iconByLabel.get("OA待付款核对"),
      iconByLabel.get("销项发票收款情况"),
    ])).toHaveLength(4);
    expect(new Set([
      iconByLabel.get("银行明细"),
      iconByLabel.get("流水规则批量处理"),
      iconByLabel.get("批量账务"),
      iconByLabel.get("银行流水导入"),
    ])).toHaveLength(4);
  });

  test("loads the workbench as an all-time view and keeps the month picker scoped to tax offset", async () => {
    const defaultMonth = currentBusinessMonth();
    const [defaultYear, defaultMonthNumber] = defaultMonth.split("-");
    window.history.pushState({}, "", "/");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();
    expect(screen.getByText("财务运营平台")).toBeInTheDocument();
    expect(screen.getByText("溯源办公系统")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        name: "OA & 银行流水 & 进销项发票关联台",
      }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "年月选择" })).not.toBeInTheDocument();
    expect(document.querySelector(".global-header")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "搜索" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "设置" })).toHaveAttribute("href", "/settings");
    await user.click(screen.getByRole("button", { name: "导入" }));
    expect(screen.getByRole("link", { name: "银行流水导入" })).toHaveAttribute("href", "/imports/bank-transactions");
    expect(screen.getByRole("link", { name: "发票导入" })).toHaveAttribute("href", "/imports/invoices");
    expect(screen.getByRole("link", { name: "ETC发票导入" })).toHaveAttribute("href", "/imports/etc-invoices");
    expect(await screen.findByText("王青", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "税金抵扣" }));

    expect(
      await screen.findByRole("heading", { name: "税金抵扣计划与试算" }, { timeout: WORKBENCH_RENDER_TIMEOUT }),
    ).toBeInTheDocument();
    expect(document.querySelector(".global-header")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "搜索" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "设置" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: `税金抵扣月份：${defaultYear}年${Number(defaultMonthNumber)}月` })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/workbench?month=all", expect.any(Object));
    expect(fetchMock.mock.calls.filter(([input]) => String(input).startsWith("/api/workbench?"))).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith(`/api/tax-offset?month=${defaultMonth}`, expect.any(Object));
  });

  test("keeps the shell sidebar controls stable on cost statistics", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();
    expect(document.querySelector(".global-header")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "搜索" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "设置" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "成本统计" })).toHaveAttribute("aria-current", "page");
  });

  test("opens the compact sidebar from the top bar and preserves navigation entries", async () => {
    stubShellCompactMode(true);
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();
    expect(document.querySelector(".global-header")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开菜单" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "打开菜单" }));
    const settingsLink = await screen.findByRole("link", { name: "设置" });
    expect(settingsLink).toHaveAttribute("href", "/settings");
    await user.click(settingsLink);

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/settings");
  });

  test("renders the turnover ledger route from the shell sidebar", async () => {
    window.history.pushState({}, "", "/turnover-ledger");
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "外部往来款管理" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "外部往来款管理" })).toHaveAttribute("aria-current", "page");
  });

  test("does not refresh the workbench from cross-page relation events", async () => {
    window.history.pushState({}, "", "/");
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();
    const before = fetchMock.mock.calls.filter(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/workbench";
    }).length;

    window.dispatchEvent(new CustomEvent("turnoverRelationUpdated", { detail: { relationId: "rel-company-001" } }));

    const after = fetchMock.mock.calls.filter(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/workbench";
    }).length;
    expect(after).toBe(before);
  });

  test("hides the global workbench title block while a zone is expanded", async () => {
    window.history.pushState({}, "", "/");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();
    expect(screen.getByText("财务运营平台")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /未配对.*布局与栏显示/ }));
    await user.click(screen.getByRole("menuitem", { name: /^放大 未配对/ }));

    expect(document.body.classList.contains("workbench-focus-mode")).toBe(true);

    await user.click(screen.getByRole("button", { name: /未配对.*布局与栏显示/ }));
    await user.click(screen.getByRole("menuitem", { name: /^恢复 未配对/ }));

    expect(document.body.classList.contains("workbench-focus-mode")).toBe(false);
    expect(screen.getByText("财务运营平台")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "年月选择" })).not.toBeInTheDocument();
  });

  test("hides the sidebar brand in the collapsed OA iframe until the menu expands", async () => {
    window.history.pushState({}, "", "/?embedded=oa");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "系统状态正常" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "关联台" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "展开菜单" }));
    expect(screen.getByRole("button", { name: "系统状态正常" })).toBeInTheDocument();
    expect(await screen.findByText("财务运营平台")).toBeInTheDocument();
    expect(screen.getByText("溯源办公系统")).toBeInTheDocument();
    expect(document.querySelector(".app-shell.embedded-shell")).not.toBeNull();
    expect(document.querySelector(".page-body.embedded")).not.toBeNull();
  });

  test("keeps global status independent while warning when OA data is incomplete", async () => {
    window.history.pushState({}, "", "/");
    installMockApiFetch({
      workbenchOaStatus: {
        code: "error",
        message: "OA 连接失败",
      },
    });

    render(<App />);

    const statusIndicator = await screen.findByRole("button", { name: "系统状态正常" }, { timeout: WORKBENCH_RENDER_TIMEOUT });
    expect(statusIndicator).toHaveClass("ok");
    expect(statusIndicator.textContent).toBe("");
    expect(await screen.findByText("OA 连接失败，本次结果未包含完整 OA 数据。")).toBeInTheDocument();
  });

  test("navigates to the standalone settings page from the shell sidebar", async () => {
    window.history.pushState({}, "", "/");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "设置" }));

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "关联台设置" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "设置" })).toHaveAttribute("aria-current", "page");
  });

  test("renders the standalone settings route directly", async () => {
    window.history.pushState({}, "", "/settings");
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "关联台设置" })).not.toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "设置" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("button", { name: "搜索" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入" })).toBeInTheDocument();
  });

  test("navigates to the standalone bank transaction import page from the shell sidebar", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "导入" }));
    await user.click(screen.getByRole("link", { name: "银行流水导入" }));

    expect(await screen.findByRole("heading", { name: "银行流水导入" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/imports/bank-transactions");
    expect(window.location.search).toBe("");
  });

  test("redirects the retired import summary route without mounting a second import page", async () => {
    window.history.pushState({}, "", "/imports");
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "银行流水导入" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/imports/bank-transactions");
    expect(screen.queryByRole("heading", { name: "导入中心" })).not.toBeInTheDocument();
  });
});
