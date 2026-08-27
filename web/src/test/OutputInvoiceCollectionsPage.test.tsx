import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { renderAuthenticatedAppAt } from "./renderHelpers";

function collectionStatusRow({
  id,
  displayNo,
  totalWithTax,
  statusCode,
  statusLabel,
  statusReason,
  collectedAmount,
  pendingAmount,
  bankRelationCount = 0,
  isPositiveInvoice = "是",
}: {
  id: string;
  displayNo: string;
  totalWithTax: string;
  statusCode: string;
  statusLabel: string;
  statusReason: string;
  collectedAmount: string;
  pendingAmount: string;
  bankRelationCount?: number;
  isPositiveInvoice?: "是" | "否";
}) {
  const hasBank = bankRelationCount > 0;
  const invoiceId = `invoice-${id}`;
  return {
    id,
    invoice_id: invoiceId,
    invoice_identity_key: `id:${invoiceId}`,
    invoice: {
      id: invoiceId,
      display_no: displayNo,
      invoice_no: displayNo,
      issue_date: "2026-06-05",
      buyer_name: "云南驰林科技有限公司",
      buyer_tax_no: "91530103MA6K63DE44",
      seller_name: "云南溯源科技有限公司",
      seller_tax_no: "915300007194052520",
      total_with_tax: totalWithTax,
      amount_without_tax: totalWithTax,
      tax_rate: "0%",
      tax_amount: "0.00",
      specific_business_type: "技术服务",
      taxable_item_name: "生产生活服务",
      is_positive_invoice: isPositiveInvoice,
    },
    collection_status: {
      code: statusCode,
      label: statusLabel,
      reason: statusReason,
      collected_amount: collectedAmount,
      pending_amount: pendingAmount,
    },
    bank: {
      primary: hasBank ? {
        id: `bank-${id}`,
        counterparty_name: "云南驰林科技有限公司",
        trade_time: "2026-06-06 10:30:00",
        amount: collectedAmount,
        direction: "inflow",
        direction_label: "收入",
        bank_name: "建设银行",
        account_last4: "8106",
        summary: "客户回款",
        remark: "销项收款",
        relation_status: "linked",
      } : null,
      relation_count: bankRelationCount,
      has_multiple: bankRelationCount > 1,
      received_total: collectedAmount,
      detail_mode: bankRelationCount > 1 ? "list" : hasBank ? "single" : "none",
      summaries: [],
    },
    invoice_relations: {
      primary: null,
      relation_count: 0,
      has_multiple: false,
      total_with_tax: "0.00",
      detail_mode: "none",
      summaries: [],
    },
  };
}

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
        is_positive_invoice: "是",
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
        reversal_target_invoice_nos: ["26532000000395506981"],
        is_positive_invoice: "否",
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
    collectionStatusRow({
      id: "output-pending",
      displayNo: "XSFP-PENDING-001",
      totalWithTax: "62160.00",
      statusCode: "pending_collection",
      statusLabel: "待收款",
      statusReason: "尚无 canonical 配对的收入流水。",
      collectedAmount: "0.00",
      pendingAmount: "62160.00",
    }),
    collectionStatusRow({
      id: "output-partial",
      displayNo: "XSFP-PARTIAL-001",
      totalWithTax: "50000.00",
      statusCode: "partial_collected",
      statusLabel: "部分收款",
      statusReason: "canonical 配对的收入流水尚未覆盖发票金额。",
      collectedAmount: "30000.00",
      pendingAmount: "20000.00",
      bankRelationCount: 1,
    }),
    collectionStatusRow({
      id: "output-collected-multiple",
      displayNo: "XSFP-COLLECTED-001",
      totalWithTax: "1020032.00",
      statusCode: "collected",
      statusLabel: "已收款",
      statusReason: "canonical 配对的收入流水已覆盖发票金额。",
      collectedAmount: "1020032.00",
      pendingAmount: "0.00",
      bankRelationCount: 2,
    }),
    collectionStatusRow({
      id: "output-unmatched-red",
      displayNo: "XSFP-UNMATCHED-RED-001",
      totalWithTax: "-10000.00",
      statusCode: "unmatched_red",
      statusLabel: "红票待核对",
      statusReason: "红字发票尚未形成唯一、确定的蓝字发票配对关系。",
      collectedAmount: "0.00",
      pendingAmount: "0.00",
      isPositiveInvoice: "否",
    }),
  ],
  statistics: {
    invoice_count: 6,
    income_bank_transaction_count: 3,
    blue_invoice_count: 4,
    red_invoice_count: 2,
  },
  pagination: { page: 1, page_size: 20, total: 6 },
  filter_config: [
    {
      field: "collection_status",
      label: "收款状态",
      mode: "enum_multi",
      sortable: true,
      operators: ["in"],
    },
  ],
  filter_options: [
    {
      field: "collection_status",
      label: "收款状态",
      mode: "enum_multi",
      sortable: true,
      operators: ["in"],
      options: [
        { value: "reversed_by_red", label: "已被红冲", count: 1 },
        { value: "reverses_blue", label: "已冲销蓝票", count: 1 },
        { value: "unmatched_red", label: "红票待核对", count: 1 },
        { value: "collected", label: "已收款", count: 1 },
        { value: "partial_collected", label: "部分收款", count: 1 },
        { value: "pending_collection", label: "待收款", count: 1 },
      ],
    },
  ],
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
    if (url.pathname === "/api/output-invoice-collections/invoices/invoice-red/detail") {
      return jsonResponse({
        invoice_no: "RED-001",
        digital_invoice_no: "XSFP-RED-001",
        invoice_date: "2026-07-10",
        seller_name: "云南溯源科技有限公司",
        buyer_name: "云南客户有限公司",
        total_with_tax: "-182400.00",
        reversal_target_invoice_nos: ["26532000000395506981"],
        remark: "被红冲蓝字数电发票号码：26532000000395506981",
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

    const blueRow = within(table).getByRole("row", { name: /XSFP-BLUE-001/ });
    const redRow = within(table).getByRole("row", { name: /XSFP-RED-001/ });
    expect(within(blueRow).getByText("蓝字")).toHaveClass("output-invoice-collections-table-tag--info");
    expect(within(redRow).getByText("红字")).toHaveClass("output-invoice-collections-table-tag--danger");
    expect(within(redRow).getByText("冲红蓝票：26532000000395506981")).toBeVisible();
    const blueInvoiceTags = within(blueRow).getByText("2026-07-08").closest(".output-invoice-collections-tag-row");
    expect(Array.from(blueInvoiceTags?.children ?? []).map((child) => child.textContent)).toEqual([
      "2026-07-08",
      "蓝字",
      "红蓝票 · 2",
    ]);

    expect(screen.queryByText("OA", { selector: "th" })).not.toBeInTheDocument();
    expect(screen.queryByText("收据", { selector: "th" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "收款状态规则" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "收据编号设置" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "状态/提醒" })).not.toBeInTheDocument();
  });

  test("收款状态只显示状态与必要金额并保留多流水行的原生表格单元格", async () => {
    installFetchMock();

    renderAuthenticatedAppAt("/output-invoice-collections");

    const table = await screen.findByRole("grid", { name: "销项发票收款情况表" });
    const pendingRow = within(table).getByRole("row", { name: /XSFP-PENDING-001/ });
    const partialRow = within(table).getByRole("row", { name: /XSFP-PARTIAL-001/ });
    const collectedRow = within(table).getByRole("row", { name: /XSFP-COLLECTED-001/ });
    const unmatchedRedRow = within(table).getByRole("row", { name: /XSFP-UNMATCHED-RED-001/ });
    const reversedBlueRow = within(table).getByRole("row", { name: /XSFP-BLUE-001/ });
    const reversesBlueRow = within(table).getByRole("row", { name: /XSFP-RED-001/ });

    expect(within(pendingRow).getByText("待收款")).toBeVisible();
    expect(within(pendingRow).getByText("已收 0.00")).toHaveClass("output-invoice-collection-amount--collected");
    expect(within(pendingRow).getByText("待收 62160.00")).toHaveClass("output-invoice-collection-amount--pending");

    expect(within(partialRow).getByText("部分收款")).toBeVisible();
    expect(within(partialRow).getByText("已收 30000.00")).toHaveClass("output-invoice-collection-amount--collected");
    expect(within(partialRow).getByText("待收 20000.00")).toHaveClass("output-invoice-collection-amount--pending");

    expect(within(collectedRow).getByText("已收款")).toBeVisible();
    expect(within(collectedRow).getByText("已收 1020032.00")).toHaveClass("output-invoice-collection-amount--collected");
    expect(within(collectedRow).getByText("待收 0.00")).toHaveClass("output-invoice-collection-amount--pending");
    expect(within(collectedRow).getByRole("button", { name: "收入流水 · 2" })).toBeVisible();
    expect(collectedRow.querySelector(".output-invoice-collections-table-cell--status")).not.toHaveClass("output-invoice-collection-status-cell");

    expect(within(unmatchedRedRow).getByText("红票待核对")).toBeVisible();
    expect(within(reversedBlueRow).getByText("已被红冲")).toBeVisible();
    expect(within(reversesBlueRow).getByText("已冲销蓝票")).toBeVisible();
    for (const redStatusRow of [unmatchedRedRow, reversedBlueRow, reversesBlueRow]) {
      expect(within(redStatusRow).queryByText(/^已收 /)).not.toBeInTheDocument();
      expect(within(redStatusRow).queryByText(/^待收 /)).not.toBeInTheDocument();
    }

    expect(within(table).queryByText(/canonical/)).not.toBeInTheDocument();
    expect(within(table).queryByText("已由红字发票冲销。")).not.toBeInTheDocument();
    expect(within(table).queryByText("已冲销对应蓝字发票。")).not.toBeInTheDocument();
    expect(within(table).queryByText("红字发票尚未形成唯一、确定的蓝字发票配对关系。")).not.toBeInTheDocument();
  });

  test("筛选收款状态时保留完整候选并只在原表格内刷新", async () => {
    const fetchMock = installFetchMock();
    const user = userEvent.setup();

    renderAuthenticatedAppAt("/output-invoice-collections");

    const tableBefore = await screen.findByRole("grid", { name: "销项发票收款情况表" });
    await user.click(within(tableBefore).getByRole("button", { name: "筛选 状态" }));
    const menu = await screen.findByRole("menu", { name: "状态筛选与排序" });
    const allStatusLabels = ["已被红冲 1", "已冲销蓝票 1", "红票待核对 1", "已收款 1", "部分收款 1", "待收款 1"];
    allStatusLabels.forEach((label) => {
      expect(within(menu).getByRole("checkbox", { name: label })).toBeInTheDocument();
    });

    await user.click(within(menu).getByRole("checkbox", { name: "已收款 1" }));

    await waitFor(() => {
      const rowRequests = fetchMock.mock.calls
        .map(([input]) => new URL(String(input), "http://localhost"))
        .filter((url) => url.pathname === "/api/output-invoice-collections/rows");
      expect(rowRequests.length).toBeGreaterThanOrEqual(2);
      expect(rowRequests.at(-1)?.searchParams.get("filters")).toContain("collection_status");
    });

    expect(document.querySelector('[aria-label="销项发票收款情况表"]')).toBe(tableBefore);
    allStatusLabels.forEach((label) => {
      expect(within(menu).getByRole("checkbox", { name: label })).toBeInTheDocument();
    });
  });

  test("详情只读取统一事实源与正式关联关系", async () => {
    const fetchMock = installFetchMock();
    const user = userEvent.setup();

    renderAuthenticatedAppAt("/output-invoice-collections");

    await user.click(await screen.findByRole("button", { name: "查看发票 XSFP-BLUE-001 详情" }));
    const invoiceDrawer = await screen.findByRole("dialog", { name: "销项发票详情" });
    expect(within(invoiceDrawer).getByText("云南客户有限公司")).toBeVisible();
    await user.click(within(invoiceDrawer).getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(screen.getByRole("button", { name: "查看发票 XSFP-RED-001 详情" }));
    const redInvoiceDrawer = await screen.findByRole("dialog", { name: "销项发票详情" });
    expect(within(redInvoiceDrawer).getByText("被冲红蓝字发票号码")).toBeVisible();
    expect(within(redInvoiceDrawer).getByText("26532000000395506981")).toBeVisible();
    expect(within(redInvoiceDrawer).getByText("被红冲蓝字数电发票号码：26532000000395506981")).toBeVisible();
    await user.click(within(redInvoiceDrawer).getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(screen.getByRole("button", { name: "红蓝票 · 2" }));
    const relationDrawer = await screen.findByRole("dialog", { name: "销项发票详情" });
    expect(within(relationDrawer).getByRole("heading", { name: "发票 1" })).toBeVisible();
    expect(within(relationDrawer).getByRole("heading", { name: "发票 2" })).toBeVisible();
    expect(within(relationDrawer).getByText("XSFP-RED-001")).toBeVisible();
    expect(within(relationDrawer).getByText("XSFP-BLUE-001")).toBeVisible();
    expect(within(relationDrawer).queryByText("关系数量")).not.toBeInTheDocument();
    expect(within(relationDrawer).queryByText("关系模式")).not.toBeInTheDocument();
    expect(within(relationDrawer).queryByText("关系来源")).not.toBeInTheDocument();
    expect(within(relationDrawer).queryByText("output_invoice_reversal")).not.toBeInTheDocument();

    await waitFor(() => {
      const requestedPaths = fetchMock.mock.calls.map(([input]) => new URL(String(input), "http://localhost").pathname);
      expect(requestedPaths).toContain("/api/output-invoice-collections/invoices/invoice-blue/detail");
      expect(requestedPaths).toContain("/api/output-invoice-collections/invoices/invoice-red/detail");
      expect(requestedPaths).toContain("/api/output-invoice-collections/rows/output-blue/relation-details");
      expect(requestedPaths.some((path) => path.includes("/status") || path.includes("/receipts") || path.includes("/red-invoice"))).toBe(false);
    });
  });
});
