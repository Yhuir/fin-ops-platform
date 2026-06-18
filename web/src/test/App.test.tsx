import { act, render, screen, waitFor } from "@testing-library/react";
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
import { sidebarGroups } from "../components/shell/sidebarItems";
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
    const sidebarItems = sidebarGroups.flatMap((group) => group.items);
    const iconByLabel = new Map(sidebarItems.map((item) => [item.label, item.icon]));

    expect(iconByLabel.get("待找发票")).toBe(FileQuestion);
    expect(iconByLabel.get("进项发票使用情况")).toBe(FileInput);
    expect(iconByLabel.get("OA待付款核对")).toBe(ClipboardCheck);
    expect(iconByLabel.get("销项发票收款情况")).toBe(FileOutput);
    expect(iconByLabel.get("免OA流水批量处理")).toBe(ListChecks);
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
      iconByLabel.get("免OA流水批量处理"),
      iconByLabel.get("批量账务"),
      iconByLabel.get("银行流水导入"),
    ])).toHaveLength(4);
  });

  test("loads the workbench as an all-time view and keeps the month picker scoped to tax offset", async () => {
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
    expect(screen.queryByRole("button", { name: "导入中心" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "设置" })).toHaveAttribute("href", "/settings");
    expect(screen.queryByRole("link", { name: "导入中心" })).not.toBeInTheDocument();
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
    expect(screen.queryByRole("button", { name: "导入中心" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "设置" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "导入中心" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "年月选择" })).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "年份" })).toHaveAttribute("aria-valuenow", "2026");
    expect(screen.getByRole("spinbutton", { name: "月份" })).toHaveAttribute("aria-valuenow", "3");
    expect(fetchMock).toHaveBeenCalledWith("/api/workbench/summary?month=all", expect.any(Object));
    expect(fetchMock.mock.calls.some(([input]) => String(input).startsWith("/api/workbench/groups?month=all&zone=paired"))).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => String(input).startsWith("/api/workbench/groups?month=all&zone=open"))).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => String(input).startsWith("/api/workbench?"))).toBe(false);
    expect(fetchMock).toHaveBeenCalledWith("/api/tax-offset?month=2026-03", expect.any(Object));
  });

  test("keeps the shell sidebar controls stable on cost statistics", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();
    expect(document.querySelector(".global-header")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "搜索" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "设置" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "导入中心" })).not.toBeInTheDocument();
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

  test("refreshes the workbench when turnover relations change", async () => {
    window.history.pushState({}, "", "/");
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();
    const before = fetchMock.mock.calls.filter(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/workbench/summary";
    }).length;

    act(() => {
      window.dispatchEvent(new CustomEvent("turnoverRelationUpdated", { detail: { relationId: "rel-company-001" } }));
    });

    await waitFor(() => {
      const after = fetchMock.mock.calls.filter(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/workbench/summary";
      }).length;
      expect(after).toBeGreaterThan(before);
    });
  });

  test("hides the global workbench title block while a zone is expanded", async () => {
    window.history.pushState({}, "", "/");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();
    expect(screen.getByText("财务运营平台")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /放大 未配对/ }));

    expect(document.body.classList.contains("workbench-focus-mode")).toBe(true);

    await user.click(screen.getByRole("button", { name: /恢复 未配对/ }));

    expect(document.body.classList.contains("workbench-focus-mode")).toBe(false);
    expect(screen.getByText("财务运营平台")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "年月选择" })).not.toBeInTheDocument();
  });

  test("keeps the sidebar brand available inside the OA iframe", async () => {
    window.history.pushState({}, "", "/?embedded=oa");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "关联台" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "展开菜单" }));
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

    const statusIndicator = await screen.findByRole("status", { name: "系统状态正常" }, { timeout: WORKBENCH_RENDER_TIMEOUT });
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
    expect(screen.queryByRole("link", { name: "导入中心" })).not.toBeInTheDocument();
  });

  test("navigates to the standalone bank transaction import page from the shell sidebar", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "银行流水导入" }));

    expect(await screen.findByRole("heading", { name: "银行流水导入" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/imports/bank-transactions");
    expect(window.location.search).toBe("");
  });
});
