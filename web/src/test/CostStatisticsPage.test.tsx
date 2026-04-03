import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import App from "../app/App";
import { installMockApiFetch } from "./apiMock";

const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;

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

describe("Cost statistics page", () => {
  test("defaults to time view and loads month-aware transaction rows", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "按时间" })).toHaveClass("active");
    const timeTable = screen.getByRole("table", { name: "按时间统计表" });
    expect(within(timeTable).getByRole("button", { name: "查看流水 cost-txn-004" })).toBeInTheDocument();
    expect(within(timeTable).queryByRole("columnheader", { name: "资金方向" })).not.toBeInTheDocument();
    expect(within(timeTable).getAllByText("支出")[0]).toHaveClass("direction-tag");
    expect(within(getStatCard("时间流水")).getByText("4")).toBeInTheDocument();
    expect(within(getStatCard("支出流水")).getByText("4")).toBeInTheDocument();
    expect(within(getStatCard("支出总额")).getByText("18,560.00")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "年月选择" }));
    await user.click(screen.getByRole("button", { name: "2026年" }));
    await user.click(screen.getByRole("button", { name: "4月" }));

    const nextTimeTable = await screen.findByRole("table", { name: "按时间统计表" });
    expect(within(nextTimeTable).getByRole("button", { name: "查看流水 cost-txn-102" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/cost-statistics/explorer?month=2026-04", expect.any(Object));
  });

  test("project view drills down from project to expense type to transaction from left to right", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按项目" }));
    expect(await screen.findByText("全部期间")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/cost-statistics/explorer?month=all", expect.any(Object));
    expect(screen.getByText("昆明卷烟厂动力设备控制系统升级改造项目")).toBeInTheDocument();
    expect(screen.getByText("昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目")).toBeInTheDocument();

    const projectLane = screen.getByRole("heading", { name: "项目名" }).closest(".cost-explorer-lane");
    expect(projectLane).not.toBeNull();
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
    expect(screen.getAllByText("PLC 模块采购").length).toBeGreaterThan(0);
    expect(within(dialog).getByText("工商银行")).toBeInTheDocument();
    expect(within(dialog).getByText("0001")).toBeInTheDocument();
    expect(within(dialog).queryByText("工商银行 账户 0001")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("资金方向")).not.toBeInTheDocument();
    expect(within(dialog).getByText("支出")).toHaveClass("direction-tag");
    await user.click(within(dialog).getByRole("button", { name: "关闭" }));
    expect(screen.queryByRole("dialog", { name: "流水详情" })).not.toBeInTheDocument();
  });

  test("expense type view shows time, project name, amount and expense content in a modal drilldown", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();
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
    expect(within(dialog).getByText("招商银行")).toBeInTheDocument();
    expect(within(dialog).getByText("2201")).toBeInTheDocument();
    expect(within(dialog).queryByText("招商银行 账户 2201")).not.toBeInTheDocument();
  });

  test("shows empty state when the selected month has no cost statistics", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("table", { name: "按时间统计表" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "年月选择" }));
    await user.click(screen.getByRole("button", { name: "2026年" }));
    await user.click(screen.getByRole("button", { name: "5月" }));

    expect(await screen.findByText("当前月份没有可用于成本统计的支出流水。")).toBeInTheDocument();
  });

  test("shows error state when explorer loading fails", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch({ costErrorMonths: ["2026-04"] });

    render(<App />);

    expect(await screen.findByRole("table", { name: "按时间统计表" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "年月选择" }));
    await user.click(screen.getByRole("button", { name: "2026年" }));
    await user.click(screen.getByRole("button", { name: "4月" }));

    expect(await screen.findByText("成本统计数据加载失败，请稍后重试。")).toBeInTheDocument();
  });

  test("opens export center in time view with exact date range and shows export feedback inside the modal", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();
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
      "/api/cost-statistics/export-preview?month=all&view=time&start_date=2026-03-10&end_date=2026-04-16",
      expect.any(Object),
    );
    expect(within(dialog).getByText("预计导出 6 条流水")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "导出" }));
    expect(await within(dialog).findByText("已导出 成本统计_2026-03-10至2026-04-16_按时间统计.xlsx")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cost-statistics/export?month=all&view=time&start_date=2026-03-10&end_date=2026-04-16",
      expect.any(Object),
    );
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  });

  test("uses export center in project mode with project and expense type filters", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "按项目" }));

    await user.click(screen.getByRole("button", { name: "导出中心" }));
    const dialog = await screen.findByRole("dialog", { name: "导出中心" });
    expect(within(dialog).getByRole("button", { name: "按项目" })).toHaveClass("active");
    expect(within(dialog).getByLabelText("云南溯源科技")).toBeChecked();
    await user.click(within(dialog).getByLabelText("交通费"));
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

    render(<App />);

    expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();
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
