import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { renderAuthenticatedAppAt } from "./renderHelpers";

const rowsPayload = {
  rows: [
    {
      id: "output-blue",
      invoice_id: "invoice-blue",
      invoice_identity_key: "id:invoice-blue",
      invoice: {
        id: "invoice-blue",
        display_no: "XSFP-BLUE-001",
        invoice_no: "BLUE-001",
        issue_date: "2026-07-08",
        buyer_name: "云南客户有限公司",
        buyer_tax_no: "91530100BUYER01",
        seller_name: "云南溯源科技有限公司",
        seller_tax_no: "91530000SELLER01",
        total_with_tax: "182400.00",
        amount_without_tax: "161415.93",
        tax_rate: "13%",
        tax_amount: "20984.07",
        specific_business_type: "技术服务",
        taxable_item_name: "系统建设服务",
      },
      collection_status: {
        code: "reversed_by_red",
        label: "已被红冲",
        reason: "已由红字发票冲销。",
        collected_amount: "0.00",
        pending_amount: "0.00",
      },
      bank: {
        primary: {
          id: "bank-001",
          counterparty_name: "云南客户有限公司",
          trade_time: "2026-07-09 10:30:00",
          amount: "182400.00",
          direction: "inflow",
          direction_label: "收入",
          bank_name: "建设银行",
          account_last4: "8106",
          summary: "客户回款",
          relation_status: "linked",
        },
        relation_count: 1,
        has_multiple: false,
        received_total: "182400.00",
        detail_mode: "single",
        summaries: [],
      },
      invoice_relations: {
        primary: {
          id: "invoice-red",
          display_no: "XSFP-RED-001",
          invoice_no: "RED-001",
          invoice_date: "2026-07-10",
          buyer_name: "云南客户有限公司",
          total_with_tax: "-182400.00",
          relation_mode: "output_invoice_reversal",
          relation_status: "linked",
          relation_source: "auto",
        },
        relation_count: 2,
        has_multiple: true,
        total_with_tax: "0.00",
        detail_mode: "list",
        summaries: [
          {
            id: "invoice-red",
            display_no: "XSFP-RED-001",
            invoice_no: "RED-001",
            invoice_date: "2026-07-10",
            buyer_name: "云南客户有限公司",
            total_with_tax: "-182400.00",
            relation_mode: "output_invoice_reversal",
            relation_status: "linked",
            relation_source: "auto",
          },
          {
            id: "invoice-blue",
            display_no: "XSFP-BLUE-001",
            invoice_no: "BLUE-001",
            invoice_date: "2026-07-08",
            buyer_name: "云南客户有限公司",
            total_with_tax: "182400.00",
            relation_mode: "output_invoice_reversal",
            relation_status: "linked",
            relation_source: "auto",
          },
        ],
      },
    },
    {
      id: "output-red",
      invoice_id: "invoice-red",
      invoice: {
        id: "invoice-red",
        display_no: "XSFP-RED-001",
        invoice_no: "RED-001",
        issue_date: "2026-07-10",
        buyer_name: "云南客户有限公司",
        buyer_tax_no: "91530100BUYER01",
        seller_name: "云南溯源科技有限公司",
        seller_tax_no: "91530000SELLER01",
        total_with_tax: "-182400.00",
        amount_without_tax: "-161415.93",
        tax_rate: "13%",
        tax_amount: "-20984.07",
        specific_business_type: "技术服务",
        taxable_item_name: "系统建设服务",
      },
      collection_status: {
        code: "reverses_blue",
        label: "已冲销蓝票",
        reason: "已冲销对应蓝字发票。",
        collected_amount: "0.00",
        pending_amount: "0.00",
      },
      bank: {
        primary: null,
        relation_count: 0,
        has_multiple: false,
        detail_mode: "none",
        summaries: [],
      },
      invoice_relations: {
        primary: {
          id: "invoice-blue",
          display_no: "XSFP-BLUE-001",
          invoice_no: "BLUE-001",
          invoice_date: "2026-07-08",
          buyer_name: "云南客户有限公司",
          total_with_tax: "182400.00",
          relation_mode: "output_invoice_reversal",
          relation_status: "linked",
          relation_source: "auto",
        },
        relation_count: 1,
        has_multiple: false,
        detail_mode: "single",
        summaries: [],
      },
    },
  ],
  statistics: {
    invoice_count: 2,
    linked_income_bank_invoice_count: 1,
    collected_invoice_count: 0,
    unlinked_bank_invoice_count: 1,
    uncollected_invoice_count: 0,
    red_invoice_count: 1,
  },
  pagination: { page: 1, page_size: 20, total: 2 },
  filter_config: [],
  filter_options: [],
};

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installFetchMock() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/api/output-invoice-collections/rows") {
      return jsonResponse(rowsPayload);
    }
    if (url.pathname === "/api/output-invoice-collections/invoices/invoice-blue/detail") {
      return jsonResponse({
        invoice_no: "BLUE-001",
        digital_invoice_no: "XSFP-BLUE-001",
        invoice_date: "2026-07-08",
        seller_name: "云南溯源科技有限公司",
        buyer_name: "云南客户有限公司",
        total_with_tax: "182400.00",
      });
    }
    if (url.pathname === "/api/output-invoice-collections/rows/output-blue/relation-details") {
      return jsonResponse({
        kind: "invoice",
        relation_count: 2,
        has_multiple: true,
        summaries: rowsPayload.rows[0].invoice_relations.summaries,
      });
    }
    throw new Error(`unexpected request: ${url.pathname}`);
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});

describe("销项发票收款情况", () => {
  test("只显示销项发票、收款状态和收入流水三个事实源分组", async () => {
    installFetchMock();

    renderAuthenticatedAppAt("/output-invoice-collections");

    const table = await screen.findByRole("grid", { name: "销项发票收款情况表" });
    expect(table.closest(".finance-table")).toHaveClass("finance-table--contained");
    expect(within(table).getByText("销项发票")).toBeVisible();
    expect(within(table).getByText("收款状态")).toBeVisible();
    expect(within(table).getByText("收入流水")).toBeVisible();
    expect(within(table).getByText("已被红冲")).toBeVisible();
    expect(within(table).getByText("已冲销蓝票")).toBeVisible();
    expect(within(table).getByRole("button", { name: "红蓝票 · 2" })).toBeVisible();

    expect(screen.queryByText("OA", { selector: "th" })).not.toBeInTheDocument();
    expect(screen.queryByText("收据", { selector: "th" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "收款状态规则" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "收据编号设置" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "状态/提醒" })).not.toBeInTheDocument();
  });

  test("详情只读取统一事实源与正式关联关系", async () => {
    const fetchMock = installFetchMock();
    const user = userEvent.setup();

    renderAuthenticatedAppAt("/output-invoice-collections");

    await user.click(await screen.findByRole("button", { name: "查看发票 XSFP-BLUE-001 详情" }));
    const invoiceDrawer = await screen.findByRole("dialog", { name: "销项发票详情" });
    expect(within(invoiceDrawer).getByText("云南客户有限公司")).toBeVisible();
    await user.click(within(invoiceDrawer).getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(screen.getByRole("button", { name: "红蓝票 · 2" }));
    const relationDrawer = await screen.findByRole("dialog", { name: "销项发票详情" });
    expect(within(relationDrawer).getByText("关系数量")).toBeVisible();
    expect(within(relationDrawer).getByText("2")).toBeVisible();

    await waitFor(() => {
      const requestedPaths = fetchMock.mock.calls.map(([input]) => new URL(String(input), "http://localhost").pathname);
      expect(requestedPaths).toContain("/api/output-invoice-collections/invoices/invoice-blue/detail");
      expect(requestedPaths).toContain("/api/output-invoice-collections/rows/output-blue/relation-details");
      expect(requestedPaths.some((path) => path.includes("/status") || path.includes("/receipts") || path.includes("/red-invoice"))).toBe(false);
    });
  });
});
