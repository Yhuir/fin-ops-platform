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
      "按费用类型",
      "按银行账户",
    ]);
    expect(within(switcher).getByText("银行流水")).toBeInTheDocument();
    const bankFlowViews = within(switcher).getByRole("radiogroup", { name: "银行流水统计视图" });
    expect(within(bankFlowViews).getAllByRole("radio").map((item) => item.textContent)).toEqual([
      "按标签",
      "按时间",
    ]);
    expect(screen.queryByText("成本归因")).not.toBeInTheDocument();
  });

  test("keeps bank labels and OA expense types distinct in manual allocation", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderPage();
    await waitUntilReady();

    await user.click(screen.getByRole("button", { name: "打开成本人工分配" }));
    const drawer = await screen.findByRole("dialog", { name: "成本人工分配" });
    await user.click(within(drawer).getByRole("button", { name: "展开项目 A 等 2 个项目人工分配" }));

    expect(within(drawer).getByText("流水1", { exact: true })).toBeInTheDocument();
    expect(within(drawer).getByText("流水2", { exact: true })).toBeInTheDocument();
    expect(within(drawer).getByText("2026-08-27 09:30:00", { exact: true }).closest(".cost-manual-allocation-meta-chip")).not.toBeNull();
    expect(within(drawer).getAllByText("项目开销 / 设备材料 / 设备采购", { exact: true })).toHaveLength(2);
    expect(within(drawer).getByText("支付申请", { exact: true })).toBeInTheDocument();
    expect(within(drawer).getByText("日常报销", { exact: true })).toBeInTheDocument();
    expect(within(drawer).getByText("材料费", { exact: true })).toBeInTheDocument();
    expect(within(drawer).getByText("交通费", { exact: true })).toBeInTheDocument();
    expect(within(drawer).queryByText("设备采购", { exact: true })).not.toBeInTheDocument();
    expect(within(drawer).queryByText("每项分配金额均需填写为非负数，并保留两位小数。")).not.toBeInTheDocument();
    expect(within(drawer).getByRole("checkbox", { name: "不计入成本" })).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "保存分配" })).toBeDisabled();

    await user.type(within(drawer).getByLabelText("项目 A分配金额"), "600.00");
    expect(await within(drawer).findByText("待分配 400.00")).toBeInTheDocument();
    await user.type(within(drawer).getByLabelText("项目 B分配金额"), "400.00");
    expect(within(drawer).queryByText("待分配 400.00", { exact: true })).not.toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "保存分配" })).toBeEnabled();
  });

  test("shows signed bank flows by time and drills from tag to raw rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderPage();
    await waitUntilReady();

    await user.click(screen.getByRole("radio", { name: "按时间" }));
    expect(await screen.findByRole("heading", { name: "按时间统计" })).toBeInTheDocument();
    expect(await screen.findByRole("grid", { name: "按时间银行流水表" })).toBeInTheDocument();
    expect(screen.getAllByText("收入").length).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("view=time"),
      expect.any(Object),
    );

    await user.click(screen.getByRole("radio", { name: "按标签" }));
    await user.click(await screen.findByRole("button", { name: "选择主标签 项目开销" }));
    await user.click(await screen.findByRole("button", { name: "选择子标签 设备材料" }));
    expect(await screen.findByRole("grid", { name: "按标签银行流水表" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/view=bank_tag.*bank_tag_primary_label=.*bank_tag_sub_label=/),
      expect.any(Object),
    );
  });

  test("drills from project to expense type to cost detail", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderPage();
    await waitUntilReady();

    await user.click(screen.getByRole("button", { name: "选择项目名 云南溯源科技" }));
    await user.click(await screen.findByRole("button", { name: "选择费用类型 设备货款及材料费" }));
    expect(await screen.findByRole("grid", { name: "项目成本明细表" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("view=project&project_name="),
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("expense_type="),
      expect.any(Object),
    );
  });

  test("drills from bank account to project to the same cost rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderPage();
    await waitUntilReady();

    await user.click(screen.getByRole("radio", { name: "按银行账户" }));
    const account = await screen.findByRole("button", { name: "选择银行账户 工商银行 账户 0001" });
    await user.click(account);
    await user.click(await screen.findByRole("button", { name: /选择项目 云南溯源科技/ }));

    expect(await screen.findByRole("grid", { name: "银行账户项目成本明细表" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/view=bank_account.*project_name=.*bank_account_label=/),
      expect.any(Object),
    );
  });

  test("keeps expense-type drill-down independent", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderPage();
    await waitUntilReady();

    await user.click(screen.getByRole("radio", { name: "按费用类型" }));
    await user.click(await screen.findByRole("button", { name: "选择费用类型 设备货款及材料费" }));
    expect(await screen.findByRole("grid", { name: "按费用类型成本明细表" })).toBeInTheDocument();
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
      "按费用类型",
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

  test("read-export users can read and export but do not see the no-OA write entry", async () => {
    installMockApiFetch({ sessionAccessTier: "read_export_only" });
    renderPage({
      ...staticSession,
      session: {
        ...defaultSession,
        accessTier: "read_export_only",
        canMutateData: false,
      },
    });
    await waitUntilReady();
    expect(screen.getByRole("button", { name: "导出中心" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "无 OA 归集设置" })).not.toBeInTheDocument();
  });
});
