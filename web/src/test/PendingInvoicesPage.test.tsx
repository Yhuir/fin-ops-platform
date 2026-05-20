import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";

function installPendingInvoiceFetch() {
  const baseFetch = installMockApiFetch();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/pending-invoices/rows") {
      const direction = url.searchParams.get("direction") ?? "expense";
      const filter = url.searchParams.get("filter") ?? "all";
      const expenseRows = [
        {
          id: "txn-requires-missing",
          bank_transaction: {
            id: "txn-requires-missing",
            counterparty_name: "云南开票供应商",
            trade_time: "2026-05-02 10:00:00",
            amount: "1200.00",
            bank_name: "工商银行",
            account_last4: "6386",
            effective_tag_code: "fee",
            effective_tag_label: "手续费",
          },
          invoices: [],
          oa_applicant: "张三",
          can_create_invoice: true,
          relation_case_ids: ["case-001"],
        },
        {
          id: "txn-no-required-missing",
          bank_transaction: {
            id: "txn-no-required-missing",
            counterparty_name: "无需发票供应商",
            trade_time: "2026-05-03 09:00:00",
            amount: "300.00",
            bank_name: "工商银行",
            account_last4: "6386",
            effective_tag_code: "salary",
            effective_tag_label: "工资",
          },
          invoices: [],
          oa_applicant: null,
          can_create_invoice: false,
          relation_case_ids: [],
        },
        {
          id: "txn-multi-invoices",
          bank_transaction: {
            id: "txn-multi-invoices",
            counterparty_name: "多票供应商",
            trade_time: "2026-05-04 11:00:00",
            amount: "2000.00",
            bank_name: "建设银行",
            account_last4: "8826",
            effective_tag_code: "fee",
            effective_tag_label: "手续费",
          },
          invoices: [
            { id: "inv-001", invoice_no: "INV-001", digital_invoice_no: "", issue_date: "2026-05-04", total_with_tax: "1000.00", seller_name: "多票供应商A", buyer_name: "云南溯源科技", invoice_type: "input" },
            { id: "inv-002", invoice_no: "INV-002", digital_invoice_no: "", issue_date: "2026-05-05", total_with_tax: "1000.00", seller_name: "多票供应商B", buyer_name: "云南溯源科技", invoice_type: "input" },
          ],
          oa_applicant: "李四",
          can_create_invoice: false,
          relation_case_ids: ["case-002"],
        },
      ];
      const incomeRows = [
        {
          id: "txn-income-missing",
          bank_transaction: {
            id: "txn-income-missing",
            counterparty_name: "客户有限公司",
            trade_time: "2026-05-05 15:00:00",
            amount: "5000.00",
            bank_name: "工商银行",
            account_last4: "6386",
            effective_tag_code: "business_invoiced_pending_collection",
            effective_tag_label: "已开票待收款",
          },
          invoices: [],
          oa_applicant: "王五",
          can_create_invoice: true,
          relation_case_ids: [],
        },
      ];
      const rows = direction === "income"
        ? incomeRows
        : filter === "no_invoice_required"
          ? [expenseRows[1]]
          : filter === "bank_statement_as_invoice"
            ? [{ ...expenseRows[0], id: "txn-bank-statement", bank_transaction: { ...expenseRows[0].bank_transaction, id: "txn-bank-statement", counterparty_name: "流水替票供应商" } }]
            : expenseRows;
      return new Response(JSON.stringify({
        direction,
        filter: direction === "income" ? "all" : filter,
        rows,
        pagination: { page: 1, page_size: 50, total: rows.length },
        summary: { total_rows: rows.length, missing_invoice_rows: rows.filter((row) => row.invoices.length === 0).length, create_invoice_available_rows: rows.filter((row) => row.can_create_invoice).length },
        tag_dictionary: { version: 1, tags: [] },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/manual-invoices/preview") {
      return new Response(JSON.stringify({
        preview_id: "preview-001",
        request_key: "manual-key",
        can_confirm: true,
        target_invoice_type: "input",
        bank_transaction_summary: { id: "txn-requires-missing", direction: "expense", counterparty_name: "云南开票供应商", trade_time: "2026-05-02", amount: "1200.00" },
        invoice_identity: { source_unique_key: "source-key", data_fingerprint: "fingerprint" },
        duplicate_check: { status: "clear", matched_invoice_id: null, message: "未发现重复发票" },
        relation_impact: { relation_mode: "pending_invoice_manual_invoice", affected_months: ["2026-05"] },
        warnings: [],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/manual-invoices") {
      return new Response(JSON.stringify({
        invoice_id: "inv-created",
        relation_case_id: "case-created",
        affected_transaction_ids: ["txn-requires-missing"],
        affected_invoice_ids: ["inv-created"],
        affected_months: ["2026-05"],
        row: {
          id: "txn-requires-missing",
          bank_transaction: { id: "txn-requires-missing", counterparty_name: "云南开票供应商", trade_time: "2026-05-02 10:00:00", amount: "1200.00", bank_name: "工商银行", account_last4: "6386" },
          invoices: [{ id: "inv-created", invoice_no: "INV-MANUAL", issue_date: "2026-05-06", total_with_tax: "1200.00", seller_name: "手工销方", buyer_name: "云南溯源科技", invoice_type: "input" }],
          oa_applicant: "张三",
          can_create_invoice: false,
          relation_case_ids: ["case-created"],
        },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return baseFetch(input, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Pending invoices page", () => {
  test("adds sidebar entry and renders route with expense table columns", async () => {
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    expect(await screen.findByRole("link", { name: "待找发票" })).toHaveAttribute("href", "/pending-invoices");
    const page = await screen.findByTestId("pending-invoices-page");
    expect(within(page).getByRole("button", { name: "支出流水" })).toHaveAttribute("aria-pressed", "true");
    expect(within(page).getByRole("button", { name: "收入流水" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "全部" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "支出流水" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "进项发票" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "OA申请人" })).toBeInTheDocument();
    expect(await within(page).findByText("云南开票供应商")).toBeInTheDocument();
    expect(within(page).getByText("2026-05-02 10:00:00").closest(".MuiChip-root")).toBeInTheDocument();
    expect(within(page).getAllByText("工商银行 6386")[0].closest(".MuiChip-root")).toBeInTheDocument();
    expect(within(page).getByText("INV-001")).toBeInTheDocument();
    expect(within(page).getByText("INV-002")).toBeInTheDocument();
    expect(within(page).getByText("多票供应商A")).toBeInTheDocument();
    expect(within(page).getByRole("row", { name: /无需发票供应商/ })).not.toHaveTextContent("新增发票");

    const request = fetchMock.mock.calls
      .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
      .find((url) => url.pathname === "/api/pending-invoices/rows");
    expect(request?.searchParams.get("direction")).toBe("expense");
  });

  test("hides expense filter in income mode and keeps plus available for missing output invoice", async () => {
    const user = userEvent.setup();
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await screen.findByTestId("pending-invoices-page");
    await user.click(within(page).getByRole("button", { name: "收入流水" }));

    expect(await within(page).findByText("客户有限公司")).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "全部" })).not.toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "收入流水" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "销项发票" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /客户有限公司 新增发票/ })).toBeInTheDocument();
    await waitFor(() => {
      const request = fetchMock.mock.calls
        .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
        .filter((url) => url.pathname === "/api/pending-invoices/rows")
        .at(-1);
      expect(request?.searchParams.get("direction")).toBe("income");
      expect(request?.searchParams.get("filter")).toBeNull();
    });
  });

  test("expense filters drive plus rules and dialog previews before confirm", async () => {
    const user = userEvent.setup();
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await screen.findByTestId("pending-invoices-page");
    await user.click(await within(page).findByRole("button", { name: "全部" }));
    await user.click(await screen.findByRole("menuitem", { name: "流水代替发票" }));
    expect(await within(page).findByText("流水替票供应商")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /流水替票供应商 新增发票/ })).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: /流水替票供应商 新增发票/ }));
    const dialog = await screen.findByRole("dialog", { name: "手工补录发票" });
    await user.type(within(dialog).getByLabelText("发票号码"), "INV-MANUAL");
    await user.type(within(dialog).getByLabelText("开票日期"), "2026-05-06");
    await user.type(within(dialog).getByLabelText("价税合计"), "1200.00");
    await user.type(within(dialog).getByLabelText("销方名称"), "手工销方");
    await user.type(within(dialog).getByLabelText("购方名称"), "云南溯源科技");
    await user.click(within(dialog).getByRole("button", { name: "预览" }));

    expect(await within(dialog).findByText(/manual-key/)).toBeInTheDocument();
    expect(within(dialog).getByText(/未发现重复发票/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "确认写入" }));

    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname);
      expect(paths).toContain("/api/pending-invoices/manual-invoices/preview");
      expect(paths).toContain("/api/pending-invoices/manual-invoices");
    });
  });
});
