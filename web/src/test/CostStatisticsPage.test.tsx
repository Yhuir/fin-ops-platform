import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import App from "../app/App";
import { installMockApiFetch } from "./apiMock";

const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;
const PAGE_RENDER_TIMEOUT = 3000;

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

function getStatCard(label: string) {
  const card = screen
    .getAllByText(label)
    .map((element) => element.closest(".stat-card"))
    .find((element): element is HTMLElement => Boolean(element));
  if (!card) {
    throw new Error(`Stat card not found for ${label}`);
  }
  return card;
}

function findCostStatisticsHeading() {
  return screen.findByRole("heading", { name: "成本统计" }, { timeout: PAGE_RENDER_TIMEOUT });
}

describe("Cost statistics page", () => {
  test("defaults to time view and loads month-aware transaction rows", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "按时间" })).toHaveClass("active");
    const timeTable = await screen.findByRole("table", { name: "按时间统计表" });
    expect(within(timeTable).getByRole("button", { name: "查看流水 cost-txn-003" })).toBeInTheDocument();
    expect(within(timeTable).queryByRole("button", { name: "查看流水 cost-txn-004" })).not.toBeInTheDocument();
    expect(within(timeTable).queryByRole("columnheader", { name: "资金方向" })).not.toBeInTheDocument();
    expect(within(timeTable).getAllByText("支出")[0]).toHaveClass("direction-tag");
    expect(within(getStatCard("时间流水")).getByText("3")).toBeInTheDocument();
    expect(within(getStatCard("支出流水")).getByText("3")).toBeInTheDocument();
    expect(within(getStatCard("支出总额")).getByText("13,360.00")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?month=2026-03&project_scope=active",
      expect.any(Object),
    );

    await user.click(screen.getByRole("button", { name: "4月" }));

    const nextTimeTable = await screen.findByRole("table", { name: "按时间统计表" });
    expect(within(nextTimeTable).getByRole("button", { name: "查看流水 cost-txn-102" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/cost-statistics/explorer?month=2026-04&project_scope=active", expect.any(Object));
  });

  test("project view drills down from project to expense type to transaction from left to right", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按项目" }));
    expect(await screen.findAllByText("全部时间")).not.toHaveLength(0);
    expect(fetchMock).toHaveBeenCalledWith("/api/cost-statistics/explorer?month=all&project_scope=active", expect.any(Object));
    expect(screen.getByText("昆明卷烟厂动力设备控制系统升级改造项目")).toBeInTheDocument();
    expect(screen.queryByText("昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "项目范围：进行中" }));
    expect(await screen.findByRole("button", { name: "项目范围：所有项目" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/cost-statistics/explorer?month=all&project_scope=all", expect.any(Object));
    expect(await screen.findByText("昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目")).toBeInTheDocument();

    const projectLane = screen.getByRole("heading", { name: "项目名" }).closest(".cost-explorer-lane");
    expect(projectLane).not.toBeNull();
    expect(within(projectLane as HTMLElement).getByText("47.4%")).toBeInTheDocument();
    await user.click(within(projectLane as HTMLElement).getByRole("button", { name: /云南溯源科技/ }));

    const expenseLane = screen.getByRole("heading", { name: "费用类型" }).closest(".cost-explorer-lane");
    expect(expenseLane).not.toBeNull();
    expect(within(expenseLane as HTMLElement).getByText("设备货款及材料费")).toBeInTheDocument();
    expect(within(expenseLane as HTMLElement).getByText("交通费")).toBeInTheDocument();
    expect(within(expenseLane as HTMLElement).getByText("93.6%")).toBeInTheDocument();
    expect(within(expenseLane as HTMLElement).getByText("6.4%")).toBeInTheDocument();

    await user.click(within(expenseLane as HTMLElement).getByRole("button", { name: /设备货款及材料费/ }));

    const transactionTable = screen.getByRole("table", { name: "项目对应流水表" });
    expect(within(transactionTable).getByRole("button", { name: "查看流水 cost-txn-001" })).toBeInTheDocument();
    expect(within(transactionTable).getByRole("button", { name: "查看流水 cost-txn-002" })).toBeInTheDocument();
    expect(within(transactionTable).queryByRole("columnheader", { name: "资金方向" })).not.toBeInTheDocument();

    await user.click(within(transactionTable).getByRole("button", { name: "查看流水 cost-txn-001" }));

    const dialog = await screen.findByRole("dialog", { name: "流水详情" });
    expect(dialog).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/transactions/cost-txn-001?project_scope=all",
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
    await user.click(within(dialog).getByRole("button", { name: "关闭" }));
    expect(screen.queryByRole("dialog", { name: "流水详情" })).not.toBeInTheDocument();
  });

  test("project view supports all time, year, month, and custom date range scopes", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按项目" }));

    expect(await screen.findAllByText("全部时间")).not.toHaveLength(0);
    const projectLane = screen.getByRole("heading", { name: "项目名" }).closest(".cost-explorer-lane");
    expect(projectLane).not.toBeNull();
    expect(within(projectLane as HTMLElement).getByText("云南溯源科技")).toBeInTheDocument();
    expect(within(projectLane as HTMLElement).getByText("昆明卷烟厂动力设备控制系统升级改造项目")).toBeInTheDocument();
    expect(within(projectLane as HTMLElement).queryByText("昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "按年统计" }));
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "2026年" })).toBeInTheDocument();
    expect(within(projectLane as HTMLElement).getByText("云南溯源科技")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "按年统计 2026年" })).toHaveClass("active");

    await user.click(screen.getByRole("button", { name: "按月统计" }));
    await user.click(screen.getByRole("button", { name: "4月" }));
    expect(screen.getByRole("button", { name: "按月统计 2026年4月" })).toHaveClass("active");

    expect(await within(projectLane as HTMLElement).findByText("昆明卷烟厂动力设备控制系统升级改造项目")).toBeInTheDocument();
    expect(within(projectLane as HTMLElement).queryByText("云南溯源科技")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "自定义时间段" }));
    fireEvent.change(screen.getByLabelText("项目统计开始日期"), { target: { value: "2026-03-18" } });
    fireEvent.change(screen.getByLabelText("项目统计结束日期"), { target: { value: "2026-03-20" } });
    expect(screen.getByRole("button", { name: "自定义时间段 2026-03-18至2026-03-20" })).toHaveClass("active");

    expect(await within(projectLane as HTMLElement).findByText("云南溯源科技")).toBeInTheDocument();
    expect(within(projectLane as HTMLElement).queryByText("昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目")).not.toBeInTheDocument();
    expect(within(projectLane as HTMLElement).queryByText("昆明卷烟厂动力设备控制系统升级改造项目")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "全部时间" }));
    expect(await within(projectLane as HTMLElement).findByText("昆明卷烟厂动力设备控制系统升级改造项目")).toBeInTheDocument();
  });

  test("expense type view shows time, project name, amount and expense content in a modal drilldown", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按费用类型" }));

    const expenseLane = screen.getByRole("heading", { name: "费用类型" }).closest(".cost-explorer-lane");
    expect(expenseLane).not.toBeNull();
    await user.click(within(expenseLane as HTMLElement).getByRole("button", { name: /交通费/ }));

    const transactionTable = screen.getByRole("table", { name: "按费用类型流水表" });
    expect(within(transactionTable).getByText("2026-03-18 17:02:09")).toBeInTheDocument();
    expect(within(transactionTable).getByText("云南溯源科技")).toBeInTheDocument();
    expect(within(transactionTable).getByText("860.00")).toBeInTheDocument();
    expect(within(transactionTable).getByText("项目现场往返交通")).toBeInTheDocument();
    expect(within(transactionTable).queryByRole("columnheader", { name: "资金方向" })).not.toBeInTheDocument();
    await user.click(within(transactionTable).getByRole("button", { name: "查看流水 cost-txn-003" }));
    const dialog = await screen.findByRole("dialog", { name: "流水详情" });
    expect(dialog).toBeInTheDocument();
    const expenseDetailBankName = within(dialog).getByText("招商银行");
    expect(expenseDetailBankName).toBeInTheDocument();
    expect(expenseDetailBankName.closest(".bank-account-tag")).not.toBeNull();
    expect(within(dialog).getByText("2201")).toBeInTheDocument();
    expect(within(dialog).queryByText("招商银行 账户 2201")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("支付账户")).not.toBeInTheDocument();
  });

  test("shows empty state when the selected month has no cost statistics", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("table", { name: "按时间统计表" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "5月" }));

    expect(await screen.findAllByText("当前时间范围没有可用于成本统计的支出流水。")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "按月统计 2026年5月" })).toHaveClass("active");
    await user.click(screen.getByRole("button", { name: "3月" }));
    expect(await screen.findByRole("table", { name: "按时间统计表" })).toBeInTheDocument();
  });

  test("bank view supports all-time, year, and month drilldown from bank to project to transaction", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按银行" }));

    expect(await screen.findAllByText("全部时间")).not.toHaveLength(0);
    const bankLane = screen.getByRole("heading", { name: "银行账户" }).closest(".cost-explorer-lane");
    expect(bankLane).not.toBeNull();
    expect(within(bankLane as HTMLElement).getByText("工商银行 账户 0001")).toBeInTheDocument();
    expect(within(bankLane as HTMLElement).getByText("平安银行 账户 8821")).toBeInTheDocument();
    expect(within(bankLane as HTMLElement).getByText("54.4%")).toBeInTheDocument();

    await user.click(within(bankLane as HTMLElement).getByRole("button", { name: /工商银行 账户 0001/ }));

    const projectLane = screen.getByRole("heading", { name: "项目名" }).closest(".cost-explorer-lane");
    expect(projectLane).not.toBeNull();
    expect(within(projectLane as HTMLElement).getByText("云南溯源科技")).toBeInTheDocument();
    expect(within(projectLane as HTMLElement).getByText("100.0%")).toBeInTheDocument();

    await user.click(within(projectLane as HTMLElement).getByRole("button", { name: /云南溯源科技/ }));
    const transactionTable = screen.getByRole("table", { name: "银行对应流水表" });
    expect(within(transactionTable).getByRole("button", { name: "查看流水 cost-txn-001" })).toBeInTheDocument();
    expect(within(transactionTable).getByRole("button", { name: "查看流水 cost-txn-002" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "按年统计" }));
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "2026年" })).toBeInTheDocument();
    expect(within(bankLane as HTMLElement).getByText("平安银行 账户 8821")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "按年统计 2026年" })).toHaveClass("active");

    await user.click(screen.getByRole("button", { name: "按月统计" }));
    await user.click(screen.getByRole("button", { name: "4月" }));
    expect(screen.getByRole("button", { name: "按月统计 2026年4月" })).toHaveClass("active");

    expect(await within(bankLane as HTMLElement).findByText("平安银行 账户 8821")).toBeInTheDocument();
    expect(within(bankLane as HTMLElement).queryByText("工商银行 账户 0001")).not.toBeInTheDocument();
  });

  test("time and expense type scopes stay independent and both support inline range controls", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按时间" }));
    await user.click(screen.getByRole("button", { name: "按月统计 2026年3月" }));
    await user.click(screen.getByRole("button", { name: "4月" }));
    expect(await screen.findByRole("button", { name: "按月统计 2026年4月" })).toHaveClass("active");
    expect(screen.getByRole("table", { name: "按时间统计表" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看流水 cost-txn-102" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "按费用类型" }));
    await user.click(screen.getByRole("button", { name: "自定义时间段" }));
    fireEvent.change(screen.getByLabelText("费用类型统计开始日期"), {
      target: { value: "2026-03-18" },
    });
    fireEvent.change(screen.getByLabelText("费用类型统计结束日期"), {
      target: { value: "2026-04-16" },
    });
    expect(screen.getByRole("button", { name: "自定义时间段 2026-03-18至2026-04-16" })).toHaveClass("active");
    expect(await screen.findByText("交通费")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "按时间" }));
    expect(screen.getByRole("button", { name: "按月统计 2026年4月" })).toHaveClass("active");
    expect(screen.getByRole("button", { name: "查看流水 cost-txn-102" })).toBeInTheDocument();
  });

  test("scope pickers float under the toggle row instead of taking layout height", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按时间" }));
    await user.click(screen.getByRole("button", { name: "按月统计 2026年3月" }));
    const scopeControls = screen.getByRole("tablist", { name: "时间统计时间范围" }).closest(".cost-scope-controls");
    expect(scopeControls).not.toBeNull();
    const floatingPanel = scopeControls?.querySelector(".cost-scope-floating-panel");
    expect(floatingPanel).not.toBeNull();
  });

  test("scope picker closes when clicking the active button again or clicking outside", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    const monthScopeButton = screen.getByRole("button", { name: "按月统计 2026年3月" });
    expect(screen.getByLabelText("时间统计月份")).toBeInTheDocument();

    await user.click(monthScopeButton);
    expect(screen.queryByLabelText("时间统计月份")).not.toBeInTheDocument();

    await user.click(monthScopeButton);
    expect(screen.getByLabelText("时间统计月份")).toBeInTheDocument();
    await user.click(document.body);
    expect(screen.queryByLabelText("时间统计月份")).not.toBeInTheDocument();
  });

  test("keeps current content visible while switching views or ranges that trigger background refresh", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "按时间统计表" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "按银行" }));

    expect(screen.queryByText("正在加载成本统计数据...")).not.toBeInTheDocument();
    expect(screen.getByText("从左到右依次展开：银行账户 / 项目名 / 流水，支持按范围重新统计")).toBeInTheDocument();
  });

  test("shows error state when explorer loading fails", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costErrorMonths: ["2026-04"] });

    render(<App />);

    expect(await screen.findByRole("table", { name: "按时间统计表" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "4月" }));

    expect(await screen.findByText("成本统计数据加载失败，请稍后重试。")).toBeInTheDocument();
  });

  test("opens export center in time view with exact date range and shows export feedback inside the modal", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导出中心" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "最近导出" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "高级导出" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "导出项目明细" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "导出中心" }));
    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
    expect(within(dialog).getByRole("button", { name: "按时间" })).toHaveClass("active");
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
    expect(within(dialog).getByText("预计导出 5 条流水")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "导出" }));
    expect(await within(dialog).findByText("已导出 成本统计_2026-03-10至2026-04-16_按时间统计.xlsx")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/export?month=all&view=time&project_scope=active&start_date=2026-03-10&end_date=2026-04-16",
      expect.any(Object),
    );
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  });

  test("uses export center in project mode with project and expense type filters", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按项目" }));
    await user.click(screen.getByRole("button", { name: "项目范围：进行中" }));
    expect(await screen.findByRole("button", { name: "项目范围：所有项目" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "导出中心" }));
    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
    expect(within(dialog).getByRole("button", { name: "按项目" })).toHaveClass("active");
    expect(within(dialog).getByLabelText("云南溯源科技")).toBeChecked();
    await user.click(within(dialog).getByLabelText("交通费"));
    await user.click(within(dialog).getByRole("button", { name: "仅预览" }));

    expect(await within(dialog).findByText("预览结果")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/cost-statistics/export-preview?month=all&view=project&project_scope=all&project_name=${encodeURIComponent("云南溯源科技")}&aggregate_by=month&expense_type=${encodeURIComponent("设备货款及材料费")}`,
      expect.any(Object),
    );
    expect(within(dialog).getByText("预计导出 2 条流水")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "导出" }));
    expect(await within(dialog).findByText("已导出 成本统计_全部期间_按项目统计_按月_云南溯源科技.xlsx")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/cost-statistics/export?month=all&view=project&project_scope=all&project_name=${encodeURIComponent("云南溯源科技")}&aggregate_by=month&expense_type=${encodeURIComponent("设备货款及材料费")}&include_oa_details=true&include_invoice_details=true&include_exception_rows=true&include_ignored_rows=true&include_expense_content_summary=true&sort_by=time`,
      expect.any(Object),
    );
  });

  test("supports expense type export center filters with range and multi-select", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await findCostStatisticsHeading()).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按费用类型" }));
    await user.click(screen.getByRole("button", { name: "导出中心" }));

    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
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
