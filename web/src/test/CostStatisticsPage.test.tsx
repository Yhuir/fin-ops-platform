import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import CostStatisticsTable from "../components/cost-statistics/CostStatisticsTable";
import { AppChromeProvider } from "../contexts/AppChromeContext";
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
  canAccessApp: true,
  canAdminAccess: false,
  allowedPageKeys: ["cost-statistics"],
};

const staticSession: SessionContextValue = {
  status: "authenticated",
  session: defaultSession,
  refresh: () => undefined,
};

function renderPage(session: SessionContextValue = staticSession) {
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

async function waitUntilReady() {
  expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.queryByTestId("cost-statistics-interaction-overlay")).not.toBeInTheDocument();
  });
}

describe("Cost statistics page", () => {
  test("scope lost response is verified by GET without a repeated PUT", async () => {
    installMockApiFetch();
    const otherFetch = globalThis.fetch;
    let codes = ["material"], version = 1, writes = 0;
    globalThis.fetch = vi.fn(async (input, init) => {
      if (!String(input).includes("cost-statistics/project-cost-scope")) return otherFetch(input, init);
      if (init?.method === "PUT") {
        codes = JSON.parse(String(init.body)).selected_tag_codes; version++; writes++;
        throw new TypeError("connection lost after commit");
      }
      return new Response(JSON.stringify({ version, selected_tag_codes: codes, can_save: true,
        available_tags: [{ code: "material", label: "材料款", path: ["材料款"], status: "active", direction: "expense", can_select: true }] }),
        { status: 200, headers: { "Content-Type": "application/json" } });
    });
    renderPage(); await waitUntilReady();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "项目成本范围", exact: true }));
    await user.click(await screen.findByRole("checkbox", { name: "材料款" }));
    await user.click(screen.getByRole("button", { name: "保存范围" }));
    expect(await screen.findByText("保存结果待核实，修改已保留")).toBeVisible();
    expect(screen.getByRole("button", { name: "保存范围" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "核实保存结果" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "项目成本范围" })).not.toBeInTheDocument());
    expect(writes).toBe(1); expect(codes).toEqual([]);
  });

  test("keeps pagination explicit and does not load on scroll", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();
    const rendered = render(
      <CostStatisticsTable
        ariaLabel="分页测试表"
        columns={[{ key: "label", header: "内容", render: (row: { id: string }) => row.id }]}
        getRowKey={(row) => row.id}
        onPageChange={onPageChange}
        onRetryPage={vi.fn()}
        page={1}
        pageSize={1}
        rows={[{ id: "row-1" }]}
        total={3}
      />,
    );
    const scrollSurface = screen.getByRole("grid", { name: "分页测试表" }).closest(".finance-table__scroll");
    fireEvent.scroll(scrollSurface as HTMLElement);
    expect(onPageChange).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /下一页/ }));
    expect(onPageChange).toHaveBeenCalledWith(2);
    rendered.unmount();
  });

  test("keeps project-cost views and restores the two bank-flow views", async () => {
    installMockApiFetch();
    renderPage();
    await waitUntilReady();

    const switcher = screen.getByRole("group", { name: "成本统计视图切换" });
    expect(within(switcher).getByText("项目成本")).toBeInTheDocument();
    const views = within(switcher).getByRole("radiogroup", { name: "项目成本统计视图" });
    expect(within(views).getAllByRole("radio").map((item) => item.textContent)).toEqual([
      "按项目",
      "按流水标签",
      "按银行账户",
    ]);
    expect(within(switcher).getByText("银行流水")).toBeInTheDocument();
    const bankFlowViews = within(switcher).getByRole("radiogroup", { name: "银行流水统计视图" });
    expect(within(bankFlowViews).getAllByRole("radio").map((item) => item.textContent)).toEqual([
      "按标签",
      "按时间",
    ]);
    const statistics = screen.getByLabelText("成本统计数据统计");
    expect(within(statistics).getByText("银行流水")).toBeInTheDocument();
    expect(within(statistics).getByText("支出流水")).toBeInTheDocument();
    expect(within(statistics).getByText("收入流水")).toBeInTheDocument();
    expect(within(statistics).queryByText("成本明细")).not.toBeInTheDocument();
    expect(screen.queryByText("成本归因")).not.toBeInTheDocument();
    expect(screen.queryByText(/条归集/)).not.toBeInTheDocument();
    expect(screen.queryByText("展开")).not.toBeInTheDocument();
  });

  test("keeps bank labels and original OA expense types distinct in manual allocation", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderPage();
    await waitUntilReady();

    await user.click(screen.getByRole("button", { name: "打开成本人工分配" }));
    const drawer = await screen.findByRole("dialog", { name: "成本人工分配" });
    expect(await within(drawer).findByRole("heading", { name: /银行流水/ })).toBeInTheDocument();
    expect(within(drawer).queryByText(/bank-manual-00/)).not.toBeInTheDocument();
    expect(within(drawer).getAllByText("项目开销", { exact: true }).length).toBeGreaterThan(0);
    expect(within(drawer).getByText("材料费")).toBeInTheDocument();
    expect(within(drawer).getByText("交通费")).toBeInTheDocument();
    expect(within(drawer).queryByRole("combobox")).not.toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "保存分配" }));
    expect(screen.getByRole("dialog", { name: "分配校验" })).toHaveTextContent("请分配来源，或明确设为零成本");
    await user.keyboard("{Escape}");
    expect(within(drawer).queryByLabelText("项目 A本项成本")).not.toBeInTheDocument();
    const firstUnit = drawer.querySelector(".cost-source-table tbody")! as HTMLElement;
    await user.click(within(firstUnit).getByRole("button", { name: "新增来源" }));
    const source = within(firstUnit).getByRole("combobox", { name: "来源流水 1" });
    expect(source).toHaveFocus();
    await user.click(source);
    await user.click(screen.getAllByRole("option")[0]);
    await user.type(within(firstUnit).getByLabelText("分配金额 1"), "600");
    expect(within(firstUnit).queryByLabelText("银行账户")).not.toBeInTheDocument();
  });

  test("shows signed bank flows by time and drills from tag to raw rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderPage();
    await waitUntilReady();

    await user.click(screen.getByRole("radio", { name: "按时间" }));
    expect(await screen.findByRole("heading", { name: "按时间统计" })).toBeInTheDocument();
    const timeGrid = await screen.findByRole("grid", { name: "按时间银行流水表" });
    expect(timeGrid.closest(".cost-explorer-grid.time")).not.toBeNull();
    expect(timeGrid.closest(".cost-table-shell")?.querySelector(".cost-table-pagination-footer")).not.toBeNull();
    expect(screen.getAllByText("收", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.queryByText("净支出", { exact: true })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("view=time"),
      expect.any(Object),
    );

    await user.click(screen.getByRole("radio", { name: "按标签" }));
    await user.click(await screen.findByRole("option", { name: "选择主标签 项目开销" }));
    await user.click(await screen.findByRole("option", { name: "选择子标签 设备材料" }));
    expect(await screen.findByRole("grid", { name: "按标签银行流水表" })).toBeInTheDocument();
    expect(screen.queryByText("净额", { exact: true })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/view=bank_tag.*bank_tag_primary_label=.*bank_tag_sub_label=/),
      expect.any(Object),
    );
  });

  test("refreshes the basic header statistics when the active time scope changes", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderPage();
    await waitUntilReady();

    await user.click(screen.getByRole("radio", { name: "按时间" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringMatching(/scope=2026-03&view=time&page_size=1(?:&|$)/),
        expect.any(Object),
      );
    });

    await user.click(screen.getByRole("button", { name: "全部" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringMatching(/scope=all&view=time&page_size=1(?:&|$)/),
        expect.any(Object),
      );
    });
  });

  test("drills from project to bank tags to cost detail", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderPage();
    await waitUntilReady();

    await user.click(screen.getByRole("option", { name: "选择项目名 云南溯源科技" }));
    await user.click(await screen.findByRole("option", { name: "选择银行主标签 项目开销" }));
    await user.click(await screen.findByRole("option", { name: "选择银行子标签 设备材料" }));
    expect(await screen.findByRole("grid", { name: "成本明细表" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("view=project&project_name="),
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("bank_tag_primary_key="),
      expect.any(Object),
    );
  });

  test("drills from bank account to project to the same cost rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderPage();
    await waitUntilReady();

    await user.click(screen.getByRole("radio", { name: "按银行账户" }));
    const account = await screen.findByRole("option", { name: "选择银行账户 工商银行 账户 0001" });
    await user.click(account);
    await user.click(await screen.findByRole("option", { name: /选择项目名 云南溯源科技/ }));
    await user.click(await screen.findByRole("option", { name: "选择银行主标签 项目开销" }));
    await user.click(await screen.findByRole("option", { name: "选择银行子标签 设备材料" }));

    expect(await screen.findByRole("grid", { name: "成本明细表" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/view=bank_account.*project_name=.*bank_account_label=/),
      expect.any(Object),
    );
  });

  test("keeps bank-tag drill-down independent", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderPage();
    await waitUntilReady();

    await user.click(screen.getByRole("radio", { name: "按流水标签" }));
    await user.click(await screen.findByRole("option", { name: "选择银行主标签 项目开销" }));
    await user.click(await screen.findByRole("option", { name: "选择银行子标签 设备材料" }));
    expect(await screen.findByRole("grid", { name: "成本明细表" })).toBeInTheDocument();
  });

  test("shows a scoped error and recovers through refresh", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ costExplorerFailuresBeforeSuccess: 1 });
    renderPage();
    expect(await screen.findByText("成本统计数据加载暂时失败，请刷新后重试。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "刷新成本统计" }));
    await waitUntilReady();
    expect(screen.getByRole("heading", { name: "按项目统计" })).toBeInTheDocument();
  });

  test("export center offers cost and bank-flow views and supports both previews", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderPage();
    await waitUntilReady();

    await user.click(screen.getByRole("button", { name: "导出中心" }));
    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
    const tabs = within(dialog).getByRole("tablist", { name: "导出视图切换" });
    expect(within(tabs).getAllByRole("button").map((item) => item.textContent)).toEqual([
      "按时间",
      "按标签",
      "按银行账户",
      "按项目",
      "按银行主标签",
    ]);
    await user.click(within(tabs).getByRole("button", { name: "按时间" }));
    await user.click(within(dialog).getByRole("button", { name: "仅预览" }));
    expect(await within(dialog).findByText(/预计导出 \d+ 条银行流水/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/export-preview\?month=2026-03&view=time/),
      expect.any(Object),
    );
    await user.click(within(tabs).getByRole("button", { name: "按银行账户" }));
    await user.click(within(dialog).getByRole("button", { name: "仅预览" }));
    expect(await within(dialog).findByText(/预计导出 \d+ 条成本明细/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/export-preview\?month=2026-03&view=bank_account.*bank_account_label=/),
      expect.any(Object),
    );
  });

  test("a user assigned to the page can read, export, and use its normal actions", async () => {
    installMockApiFetch({ sessionRole: "user" });
    renderPage();
    await waitUntilReady();
    expect(screen.getByRole("button", { name: "导出中心" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "无 OA 成本范围" })).toBeInTheDocument();
  });
});
