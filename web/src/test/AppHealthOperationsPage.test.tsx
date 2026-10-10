import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../app/App";
import { installMockApiFetch } from "./apiMock";

function renderPage(options: Parameters<typeof installMockApiFetch>[0] = {}) {
  window.history.pushState({}, "", "/operations/app-health");
  const fetch = installMockApiFetch({ sessionRole: "admin", sessionUsername: "admin.ops", ...options });
  render(<App />);
  return fetch;
}
async function openHistory() {
  await userEvent.click(await screen.findByRole("button", { name: "导入历史", exact: true }));
  const drawer = await screen.findByRole("dialog", { name: "导入历史" });
  await within(drawer).findByRole("button", { name: "查看 bank-6.xlsx" });
  return drawer;
}
describe("AppHealth data and imports", () => {
  test("shows two blocks, reconciled invoice dimensions and no technical panels or requests", async () => {
    const fetch = renderPage();
    const data = await screen.findByTestId("app-health-data");
    expect(screen.getByRole("heading", { name: "数据与导入" })).toBeInTheDocument();
    const invoice = within(data).getByLabelText("发票统计");
    expect(invoice).toHaveTextContent("256");
    expect(within(invoice).getAllByText("合计 256 张")).toHaveLength(2);
    expect(invoice).toHaveTextContent("手工导入");
    expect(invoice).toHaveTextContent("251");
    expect(invoice).toHaveTextContent("OA 解析新增");
    expect(invoice).not.toHaveTextContent("40");
    const oa = within(data).getByLabelText("OA 状态");
    expect(oa).toHaveTextContent("61");
    expect(oa).toHaveTextContent("11");
    expect(oa).not.toHaveTextContent("72");
    expect(screen.getByTestId("app-health-recent-imports")).toHaveTextContent("bank-5.xlsx");
    for (const id of ["app-health-requests", "app-health-runtime", "app-health-system-audit"]) expect(screen.queryByTestId(id)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "导入任务诊断" })).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/page-audit"))).toBe(false);
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/api/imports/jobs?page=1&page_size=20"))).toBe(false);
  });
  test("history supports filtering, page size, details and return without losing filters", async () => {
    const fetch = renderPage();
    const drawer = await openHistory();
    await userEvent.selectOptions(within(drawer).getByLabelText("类型"), "bank_transaction");
    await userEvent.type(within(drawer).getByLabelText("文件名"), "bank-6");
    await userEvent.click(within(drawer).getByRole("button", { name: "查询" }));
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes("search=bank-6"))).toBe(true));
    await userEvent.selectOptions(within(drawer).getByLabelText("每页"), "100");
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes("page_size=100"))).toBe(true));
    await userEvent.click(await within(drawer).findByRole("button", { name: "查看 bank-6.xlsx" }));
    await within(drawer).findByText("建设银行 · 8106");
    expect(drawer).toHaveTextContent("未关联导入任务");
    await userEvent.click(within(drawer).getByRole("button", { name: "返回列表" }));
    expect(within(drawer).getByLabelText("文件名")).toHaveValue("bank-6");
    expect(within(drawer).getByLabelText("每页")).toHaveValue("100");
    await userEvent.type(within(drawer).getByLabelText("文件名"), "missing");
    await userEvent.click(within(drawer).getByRole("button", { name: "查询" }));
    expect(await within(drawer).findByText("暂无导入记录")).toBeInTheDocument();
    await userEvent.click(within(drawer).getByRole("button", { name: "关闭导入历史" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "导入历史" })).not.toBeInTheDocument());
  });
  test("withdrawal confirms once then reads history, detail and dashboard again", async () => {
    const fetch = renderPage();
    const drawer = await openHistory();
    await userEvent.click(within(drawer).getByRole("button", { name: "查看 bank-6.xlsx" }));
    await userEvent.click(await within(drawer).findByRole("button", { name: "撤回本次流水导入" }));
    const confirm = await screen.findByRole("dialog", { name: "撤回流水导入" });
    expect(confirm).toHaveTextContent("OA、发票及导入/操作审计记录不会删除");
    await userEvent.click(within(confirm).getByRole("button", { name: "确认撤回" }));
    expect(await within(drawer).findByText("已撤回 8 笔银行流水。")).toBeInTheDocument();
    await waitFor(() => expect(within(drawer).queryByRole("button", { name: "撤回本次流水导入" })).not.toBeInTheDocument());
    expect(fetch.mock.calls.filter(([url, init]) => String(url).includes("/bank-6/withdraw") && init?.method === "POST")).toHaveLength(1);
    expect(fetch.mock.calls.filter(([url]) => String(url).includes("/app-health-dashboard")).length).toBeGreaterThan(1);
    expect(fetch.mock.calls.filter(([url]) => String(url).includes("/import-history/bank-6")).length).toBeGreaterThan(1);
  });
  test("withdrawal conflict retains details and displays the actual error", async () => {
    renderPage({ appHealthWithdrawalError: true });
    const drawer = await openHistory();
    await userEvent.click(within(drawer).getByRole("button", { name: "查看 bank-6.xlsx" }));
    await userEvent.click(await within(drawer).findByRole("button", { name: "撤回本次流水导入" }));
    const dialog = await screen.findByRole("dialog", { name: "撤回流水导入" });
    await userEvent.click(within(dialog).getByRole("button", { name: "确认撤回" }));
    await waitFor(() => expect(within(dialog).getByRole("alert")).toHaveTextContent("该批次包含更新记录，不能撤回。"));
    expect(within(drawer).queryByText("已撤回 8 笔银行流水。")).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "取消" }));
  });
  test("shows explicit initial read failures and denies non administrators", async () => {
    renderPage({ appHealthDashboardErrorStatus: 503, appHealthDashboardErrorBody: { message: "统计读取失败" } });
    expect(await screen.findByRole("alert")).toHaveTextContent("统计读取失败");
    expect(screen.queryByTestId("app-health-data")).not.toBeInTheDocument();
  });
  test("denies non administrators without requesting the dashboard", async () => {
    const fetch = renderPage({ sessionRole: "user", sessionUsername: "ordinary" });
    await screen.findByText("当前账号没有管理员权限，不能查看 AppHealth 运维状态。");
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/app-health-dashboard"))).toBe(false);
    expect(screen.queryByTestId("app-health-data")).not.toBeInTheDocument();
  });
  test("recent detail failures stay visible and support retry", async () => {
    const fetch = renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "查看 bank-5.xlsx" }));
    const drawer = await screen.findByRole("dialog", { name: "导入历史" });
    expect(await within(drawer).findByRole("alert")).toHaveTextContent("导入记录不存在。");
    await userEvent.click(within(drawer).getByRole("button", { name: "重试" }));
    await waitFor(() => expect(fetch.mock.calls.filter(([url]) => String(url).includes("/import-history/bank-5"))).toHaveLength(2));
  });
  test("unknown counts stay unknown and mismatched partitions are not forced to close", async () => {
    renderPage({ appHealthDashboard: {
      generated_at: "2026-10-10T10:00:00+08:00", data_inventory: {
        bank: { total_count: null, latest_synced_at: null, sources: [] },
        invoice: { total_count: 10, latest_synced_at: null, sources: [
          { key: "input_invoice", count: 8 }, { key: "output_invoice", count: 2 },
          { key: "manual", count: 6 }, { key: "oa_attachment", count: 5, supplementary_count: 2 },
        ] },
        oa: { total_count: 999, latest_synced_at: null, sources: [] }, import_events: [],
      },
    } });
    const data = await screen.findByTestId("app-health-data");
    expect(within(data).getByRole("alert")).toHaveTextContent("统计未闭合 · 差异 2 张");
    expect(within(data).getAllByText("合计 10 张")).toHaveLength(1);
    expect(within(data).getByLabelText("OA 状态")).not.toHaveTextContent("999");
    expect(within(data).getAllByText("—").length).toBeGreaterThan(2);
  });
  test("history paginates without mixing rows from the previous page", async () => {
    renderPage({ appHealthImportHistoryRows: Array.from({ length: 51 }, (_, index) => ({
      key: `row-${index}`, batch_id: `row-${index}`, batch_type: "input_invoice", label: "手工导入",
      source_name: `invoice-${index}.xlsx`, imported_by: "admin.ops", count: 1, status: "partial_success",
    })) });
    await userEvent.click(await screen.findByRole("button", { name: "导入历史", exact: true }));
    const drawer = await screen.findByRole("dialog", { name: "导入历史" });
    await within(drawer).findByRole("button", { name: "查看 invoice-0.xlsx" });
    await userEvent.click(within(drawer).getByRole("button", { name: "下一页" }));
    await within(drawer).findByRole("button", { name: "查看 invoice-50.xlsx" });
    expect(within(drawer).queryByRole("button", { name: "查看 invoice-0.xlsx" })).not.toBeInTheDocument();
    expect(drawer).toHaveTextContent("部分完成");
  });
  test("the pending entry reuses the shared task drawer and closes back to the page", async () => {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "导入任务", exact: true }));
    const drawer = await screen.findByRole("dialog", { name: "共享导入任务" });
    expect(await within(drawer).findByText("无待处理导入任务")).toBeInTheDocument();
    await userEvent.click(within(drawer).getByRole("button", { name: "关闭抽屉" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "共享导入任务" })).not.toBeInTheDocument());
    expect(screen.getByTestId("app-health-data")).toBeInTheDocument();
  });
});
