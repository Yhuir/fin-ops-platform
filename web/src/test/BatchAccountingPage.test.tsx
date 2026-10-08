import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import BatchAccountingHistory from "../components/batchAccounting/BatchAccountingHistory";
import { fetchBatchAccountingHistory, fetchBatchAccountingHistoryDetail } from "../features/batchAccounting/api";

vi.mock("../features/batchAccounting/api", () => ({ fetchBatchAccountingHistory: vi.fn(), fetchBatchAccountingHistoryDetail: vi.fn() }));
const history = { summary: { bank_year: null, relation_count: 51, transaction_count: 52 }, available_years: ["2026"], pagination: { page: 1, page_size: 50, total: 51 }, rows: [{ relation_id: "r1", trade_time: "2026-01-01", bank_accounts: [{ bank_name: "建行", account_last4: "8106" }], counterparty_names: ["历史商户"], bank_amount: "1200.00", bank_count: 2, oa_count: 1 }] };
afterEach(() => vi.resetAllMocks());

describe("batch accounting readonly history", () => {
  test("loads all years, paginates on server and opens complete readonly detail", async () => {
    vi.mocked(fetchBatchAccountingHistory).mockResolvedValue(history);
    const invoice = { id: "i1", invoice_no: "INV-ETC-001", invoice_code: "", digital_invoice_no: "", issue_date: "2026-01-01", seller_name: "高速公路", buyer_name: "测试公司", amount: "100", total_with_tax: "103" };
    vi.mocked(fetchBatchAccountingHistoryDetail).mockResolvedValue({ relation_id: "r1", note: "提交备注", bank_amount: "1200.00", oa_amount: "1200.00", amount_delta: "0.00", missing_member_ids: [], bank_rows: [
      { id: "b1", trade_time: "2026-01-01", bank_name: "建行", account_last4: "8106", counterparty_name: "成员一", amount: "1000", signed_amount: "-1000", direction: "outflow" },
      { id: "b2", trade_time: "2026-01-02", bank_name: "建行", account_last4: "8106", counterparty_name: "成员二", amount: "200", signed_amount: "-200", direction: "outflow" },
    ], oa_rows: [{ id: "o1", applicant: "张三", apply_time: "2026-01-01", project_name: "项目", amount: "1200", reason: "差旅", apply_type: "报销", expense_type: "差旅" }], invoice_rows: [{ ...invoice, id: "etc-group", etc_invoice_detail_rows: [invoice] }, invoice] });
    render(<BatchAccountingHistory />);
    expect(await screen.findByText("历史商户")).toBeInTheDocument();
    expect(fetchBatchAccountingHistory).toHaveBeenCalledWith(expect.objectContaining({ bankYear: "all", page: 1, pageSize: 50 }));
    expect(fetchBatchAccountingHistoryDetail).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "查看 历史商户 详情" }));
    const dialog = await screen.findByRole("dialog", { name: "批量账务详情" });
    expect(await within(dialog).findByText("成员二")).toBeInTheDocument();
    expect(within(dialog).getByText(/张三/)).toBeInTheDocument();
    expect(within(dialog).getByText("提交备注")).toBeInTheDocument();
    expect(within(dialog).getAllByText("INV-ETC-001")).toHaveLength(1);
    expect(within(dialog).getByText("发票 · 1 张")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /提交|撤回|保存|关联/ })).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "关闭抽屉" }));
    await userEvent.click(screen.getByText("下一页"));
    await waitFor(() => expect(fetchBatchAccountingHistory).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
  });
  test("shows load failure rather than empty and retries explicitly", async () => {
    vi.mocked(fetchBatchAccountingHistory).mockRejectedValueOnce(new Error("查询失败")).mockResolvedValueOnce({ ...history, rows: [], summary: { bank_year: null, relation_count: 0, transaction_count: 0 }, pagination: { page: 1, page_size: 50, total: 0 } });
    render(<BatchAccountingHistory />);
    expect(await screen.findByText("查询失败")).toBeInTheDocument();
    expect(screen.queryByText("暂无已提交记录")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("暂无已提交记录")).toBeInTheDocument();
  });
  test("surfaces unavailable detail and preserves null money", async () => {
    vi.mocked(fetchBatchAccountingHistory).mockResolvedValue({ ...history, rows: [{ ...history.rows[0], bank_amount: null }] });
    vi.mocked(fetchBatchAccountingHistoryDetail).mockRejectedValue(new Error("关联记录不存在"));
    render(<BatchAccountingHistory />);
    expect(await screen.findByText("—")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "查看 历史商户 详情" }));
    expect(await screen.findByText("关联记录不存在")).toBeInTheDocument();
  });
  test("year filtering resets pagination and ignores aborted response", async () => {
    vi.mocked(fetchBatchAccountingHistory).mockResolvedValue(history);
    render(<BatchAccountingHistory />);
    await screen.findByText("历史商户");
    await userEvent.click(screen.getByRole("button", { name: /流水年份/ }));
    await userEvent.click(screen.getByRole("option", { name: "2026" }));
    await waitFor(() => expect(fetchBatchAccountingHistory).toHaveBeenLastCalledWith(expect.objectContaining({ bankYear: "2026", page: 1 })));
    const firstSignal = vi.mocked(fetchBatchAccountingHistory).mock.calls[0][0].signal;
    expect(firstSignal?.aborted).toBe(true);
  });
});
