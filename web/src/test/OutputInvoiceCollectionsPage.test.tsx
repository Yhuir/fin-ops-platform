import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import { buildPageSessionStorageKey, createStoredPayload } from "../contexts/pageSessionStorage";

import { renderAuthenticatedAppAt } from "./renderHelpers";

// JSDOM has no Web Animations API; real indicator rendering is covered in Playwright.
const originalGetAnimations = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "getAnimations");
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "getAnimations", { configurable: true, value: () => [] });
});
afterAll(() => {
  if (originalGetAnimations) Object.defineProperty(HTMLElement.prototype, "getAnimations", originalGetAnimations);
  else Reflect.deleteProperty(HTMLElement.prototype, "getAnimations");
});

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
      original_amount: collectedAmount,
      original_transaction_count: bankRelationCount,
      primary: hasBank ? {
        id: `bank-${id}`,
        counterparty_name: "云南驰林科技有限公司",
        trade_time: "2026-06-06 10:30:00",
        amount: collectedAmount,
        original_amount: collectedAmount,
        direction: "inflow",
        direction_label: "收入",
        bank_name: "建设银行",
        bank_short_name: "建行",
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
        sections: [{title: "购销双方", fields: [{label: "购买方名称", value: "云南客户有限公司"}]}],
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
        label: "蓝票已被红冲",
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
          original_amount: "182400.00",
          original_transaction_count: 1,
        },
        relation_count: 1,
        has_multiple: false,
        received_total: "182400.00",
        detail_mode: "single",
        summaries: [],
        original_amount: "182400.00",
        original_transaction_count: 1,
      },
      invoice_relations: {
        primary: {
          id: "invoice-red",
          display_no: "XSFP-RED-001",
          sections: [{title: "业务信息", fields: [{label: "备注", value: "被红冲蓝字数电发票号码：26532000000395506981"}]}],
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
            sections: [{title: "业务信息", fields: [{label: "备注", value: "被红冲蓝字数电发票号码：26532000000395506981"}]}],
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
            sections: [{title: "购销双方", fields: [{label: "购买方名称", value: "云南客户有限公司"}]}],
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
        sections: [{title: "业务信息", fields: [{label: "备注", value: "被红冲蓝字数电发票号码：26532000000395506981"}]}],
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
        label: "红票已关联蓝票",
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
          sections: [{title: "购销双方", fields: [{label: "购买方名称", value: "云南客户有限公司"}]}],
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
      statusLabel: "红票未关联蓝票",
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
        { value: "reversed_by_red", label: "蓝票已被红冲", count: 1 },
        { value: "reverses_blue", label: "红票已关联蓝票", count: 1 },
        { value: "unmatched_red", label: "红票未关联蓝票", count: 1 },
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

function installFetchMock(rowPayloadFor: (url: URL) => unknown = () => rowsPayload) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/api/output-invoice-collections/rows") {
      return jsonResponse(await rowPayloadFor(url));
    }
    if (url.pathname === "/api/output-invoice-collections/invoices/invoice-blue/detail") {
      return jsonResponse({
        sections: [{title: "购销双方", fields: [{label: "购买方名称", value: "云南客户有限公司"}]}],
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
        sections: [{title: "业务信息", fields: [{label: "备注", value: "被红冲蓝字数电发票号码：26532000000395506981"}]}],
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
        sections: [
          { title: "发票 1", fields: [{ label: "发票号码", value: "XSFP-RED-001" }] },
          { title: "发票 2", fields: [{ label: "发票号码", value: "XSFP-BLUE-001" }] },
        ],
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
  test("原件缺少价税合计时待收显示未知并保留已收金额", async () => {
    const row = collectionStatusRow({ id: "missing-gross", displayNo: "MISSING-GROSS", totalWithTax: "",
      statusCode: "pending_collection", statusLabel: "待收款", statusReason: "原件未提供价税合计",
      collectedAmount: "40.00", pendingAmount: "", bankRelationCount: 1 });
    installFetchMock(() => ({ ...rowsPayload, rows: [row] }));
    renderAuthenticatedAppAt("/output-invoice-collections");
    const invoice = await screen.findByRole("button", { name: "查看发票 MISSING-GROSS 详情" });
    const invoiceRow = invoice.closest("tr")!;
    expect(within(invoiceRow).getByText("待收 —")).toBeVisible();
    expect(within(invoiceRow).getByText("已收 40.00")).toBeVisible();
    expect(within(invoiceRow).queryByText("待收 0.00")).not.toBeInTheDocument();
  });

  test.each(["已移除的选项", "17%"])("恢复当前不可选税率条件 %s 时不自动扩大查询，并提供明确清除入口", async (retiredRate) => {
    const user = userEvent.setup();
    const requests: URL[] = [];
    installFetchMock((url) => {
      requests.push(url);
      return { ...rowsPayload, rows: [], pagination: { page: 1, page_size: 20, total: 0 },
        filter_options: [...rowsPayload.filter_options, { field: "tax_rate", label: "税率", mode: "enum_multi", sortable: true, operators: ["in"], options: [{ value: "13%", label: "13%", count: 2 }] }],
      };
    });
    window.sessionStorage.setItem(buildPageSessionStorageKey({ userScope: "101", pageKey: "output-invoice-collections", stateKey: "query" }),
      JSON.stringify(createStoredPayload({ version: 2, ttlMs: 60_000, value: {
        page: 1, pageSize: 20, keyword: "", month: "", invoiceDateFrom: "", invoiceDateTo: "",
        filters: [{ field: "tax_rate", operator: "in", values: [retiredRate] }],
        sortField: "", sortDirection: "", activeWorkflow: null, detailTarget: null,
      } })));
    renderAuthenticatedAppAt("/output-invoice-collections");
    await screen.findByRole("grid", { name: "销项发票收款情况表" });
    const currentFilters = () => JSON.parse(decodeURIComponent(requests.at(-1)?.searchParams.get("filters") ?? "[]"));
    expect(currentFilters()).toEqual([{ field: "tax_rate", operator: "in", values: [retiredRate] }]);
    await user.click(screen.getByRole("button", { name: "筛选 税率" }));
    expect(await screen.findByText("部分已选条件不在当前可选项中，可取消勾选。")).toBeVisible();
    const oldRate = screen.getByRole("checkbox", { name: `${retiredRate} 当前无选项` });
    expect(oldRate).toBeChecked();
    await user.click(oldRate);
    await waitFor(() => expect(currentFilters()).toEqual([]));
    expect(screen.queryByText("部分已选条件不在当前可选项中，可取消勾选。")).not.toBeInTheDocument();
  });

  test("重进先清旧日期及范围关联详情，保留非日期条件，本次刷新不清月份", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    window.sessionStorage.setItem(buildPageSessionStorageKey({ userScope: "101", pageKey: "output-invoice-collections", stateKey: "query" }),
      JSON.stringify(createStoredPayload({ version: 2, ttlMs: 60_000, value: {
        page: 4, pageSize: 50, keyword: "客户", month: "2025-12", invoiceDateFrom: "2025-12-01", invoiceDateTo: "2025-12-31",
        filters: [{ field: "collection_status", operator: "in", values: ["pending_collection"] },
          { field: "invoice_date", operator: "equals", value: "2025-12-01" },
          { field: "bank_trade_time", operator: "equals", value: "2025-12-02" }],
        sortField: "invoice_no", sortDirection: "asc", activeWorkflow: { kind: "export" },
        detailTarget: { kind: "invoice", id: "old-invoice" },
      } })));
    const requests = () => fetchMock.mock.calls.map(([input]) => new URL(String(input), "http://localhost"))
      .filter((url) => url.pathname === "/api/output-invoice-collections/rows");
    const mounted = renderAuthenticatedAppAt("/output-invoice-collections");
    await screen.findByRole("grid", { name: "销项发票收款情况表" });
    expect(requests().length).toBeGreaterThan(0);
    for (const request of requests()) {
      for (const field of ["month", "invoice_date_from", "invoice_date_to"]) expect(request.searchParams.has(field)).toBe(false);
      expect(request.searchParams.get("page")).toBe("1");
      expect(request.searchParams.get("page_size")).toBe("50");
      expect(request.searchParams.get("keyword")).toBe("客户");
      expect(JSON.parse(decodeURIComponent(request.searchParams.get("filters") ?? "[]"))).toEqual([{ field: "collection_status", operator: "in", values: ["pending_collection"] }]);
      expect(request.searchParams.get("sort_direction")).toBe("asc");
    }
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "销项发票月份：年月" }));
    await user.click(within(await screen.findByRole("dialog", { name: "销项发票月份选择器" })).getByRole("button", { name: "四月" }));
    await waitFor(() => expect(requests().at(-1)?.searchParams.get("month")).toBe("2026-04"));
    await user.click(screen.getByRole("button", { name: "刷新", exact: true }));
    await waitFor(() => expect(screen.getByRole("button", { name: "刷新", exact: true })).toBeEnabled());
    expect(requests().at(-1)?.searchParams.get("month")).toBe("2026-04");
    await waitFor(() => expect(window.sessionStorage.getItem(buildPageSessionStorageKey({ userScope: "101", pageKey: "output-invoice-collections", stateKey: "query" }))).toContain('"month":"2026-04"'));
    const count = requests().length;
    mounted.unmount();
    renderAuthenticatedAppAt("/output-invoice-collections");
    await waitFor(() => expect(requests().length).toBeGreaterThan(count));
    expect(requests().slice(count).every((url) => !url.searchParams.has("month"))).toBe(true);
  });

  test("切回全部后旧月份的迟到响应不能覆盖当前结果", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    const originalFetch = fetchMock.getMockImplementation()!;
    let resolveMonth!: (response: Response) => void;
    const monthResponse = new Promise<Response>((resolve) => { resolveMonth = resolve; });
    fetchMock.mockImplementation((input, init) => {
      const url = new URL(String(input), "http://localhost");
      return url.pathname === "/api/output-invoice-collections/rows" && url.searchParams.get("month") === "2026-04"
        ? monthResponse : originalFetch(input, init);
    });
    renderAuthenticatedAppAt("/output-invoice-collections");
    await screen.findByRole("grid", { name: "销项发票收款情况表" });
    await user.click(screen.getByRole("button", { name: "销项发票月份：年月" }));
    await user.click(within(await screen.findByRole("dialog", { name: "销项发票月份选择器" })).getByRole("button", { name: "四月" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => new URL(String(input), "http://localhost").searchParams.get("month") === "2026-04")).toBe(true));
    await user.click(screen.getByRole("button", { name: "全部", exact: true }));
    await waitFor(() => expect(screen.getByRole("button", { name: "刷新", exact: true })).toBeEnabled());
    await act(async () => {
      resolveMonth(jsonResponse({ ...rowsPayload, rows: [], pagination: { ...rowsPayload.pagination, total: 0 } }));
      await monthResponse;
    });
    expect(screen.getByRole("grid", { name: "销项发票收款情况表" })).toHaveTextContent("XSFP-BLUE-001");
    expect(screen.getByRole("button", { name: "全部", exact: true })).toHaveAttribute("aria-pressed", "true");
  });

  test("只显示销项发票、收款状态和收入流水三个事实源分组", async () => {
    installFetchMock();

    renderAuthenticatedAppAt("/output-invoice-collections");

    const table = await screen.findByRole("grid", { name: "销项发票收款情况表" });
    expect(table.closest(".finance-table")).toHaveClass("finance-table--contained");
    const groups = screen.getByLabelText("当前筛选合计");
    expect(within(groups).getByText("销项发票")).toBeVisible();
    expect(within(groups).getByText("收款状态")).toBeVisible();
    expect(within(groups).getByText("收入流水")).toBeVisible();
    expect(within(table).getByText("蓝票已被红冲")).toBeVisible();
    expect(within(table).getByText("红票已关联蓝票")).toBeVisible();
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

  test("税率勾选保留其它选项、全范围合计，刷新失败不显示旧金额", async () => {
    const user = userEvent.setup();
    let fail = false;
    const requests: URL[] = [];
    installFetchMock(url => {
      requests.push(url);
      if (fail) throw new Error('统计读取失败');
      return {...rowsPayload,
        rows: rowsPayload.rows.map(row => ({...row,invoice:{...row.invoice,tax_rate:'13%'}})),
        summary: {invoiceCount:36,totalWithTax:'5680807.61',amountWithoutTax:'5030000.00',collectedAmount:'1991700.08'},
        filter_options:[...rowsPayload.filter_options,{field:'tax_rate',label:'税率',mode:'enum_multi',sortable:true,operators:['in'],options:[{value:'13%',label:'13%',count:19},{value:'6%',label:'6%',count:9},{value:'—',label:'—',count:6}]}],
      };
    });
    renderAuthenticatedAppAt('/output-invoice-collections');
    const totals = await screen.findByLabelText('当前筛选合计');
    expect(totals).toHaveTextContent('5680807.61');
    expect(totals).toHaveTextContent('5030000.00');
    expect(totals).toHaveTextContent('1991700.08');
    expect(screen.queryByText('税额/税率')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button',{name:'筛选 税率'}));
    await user.click(await screen.findByRole('checkbox',{name:/13%/}));
    await waitFor(() => expect(requests.at(-1)?.searchParams.get('filters')).toContain('13'));
    expect(screen.getByRole('checkbox',{name:/—/})).toBeVisible();
    await user.click(screen.getByRole('checkbox',{name:/6%/}));
    await waitFor(() => expect(JSON.parse(decodeURIComponent(requests.at(-1)!.searchParams.get('filters')!))[0].values).toEqual(['13%','6%']));
    expect(totals).toHaveTextContent('5680807.61');
    await user.keyboard('{Escape}');
    fail = true;
    await user.click(screen.getByRole('button',{name:'刷新',exact:true}));
    await screen.findByText('统计读取失败');
    expect(totals).not.toHaveTextContent('5680807.61');
    expect(totals).toHaveTextContent('含税金额合计 —');
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
    const bankAmountCell = collectedRow.querySelectorAll("td")[6] as HTMLElement;
    const bankMetadata = bankAmountCell.querySelector(".output-invoice-collections-tag-row--right") as HTMLElement;
    expect(bankAmountCell.querySelector(".output-invoice-collections-table-text--numeric")).toHaveTextContent("1020032.00");
    expect(within(bankMetadata).getByText("收入")).toBeVisible();
    expect(bankMetadata.querySelector(".bank-account-value")).toHaveTextContent("建行");
    expect(bankMetadata.querySelector(".bank-account-value")).not.toHaveTextContent("建设银行");
    expect(bankMetadata.querySelector(".bank-account-value")).not.toHaveClass("output-invoice-collections-table-tag");
    expect(collectedRow.querySelector(".output-invoice-collections-table-cell--status")).not.toHaveClass("output-invoice-collection-status-cell");

    expect(within(unmatchedRedRow).getByText("红票未关联蓝票")).toBeVisible();
    expect(within(reversedBlueRow).getByText("蓝票已被红冲")).toBeVisible();
    expect(within(reversesBlueRow).getByText("红票已关联蓝票")).toBeVisible();
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
    expect(screen.queryByText("当前筛选范围 · 按发票张数")).not.toBeInTheDocument();
    expect(within(tableBefore).queryByRole('button', { name: '筛选 状态' })).not.toBeInTheDocument();
    const tabs = screen.getByRole('tablist', { name: '销项发票状态分类' });
    await user.click(within(tabs).getByRole('tab', { name: '已收款 1 张' }));
    await waitFor(() => {
      const rowRequests = fetchMock.mock.calls
        .map(([input]) => new URL(String(input), "http://localhost"))
        .filter((url) => url.pathname === "/api/output-invoice-collections/rows");
      expect(rowRequests.length).toBeGreaterThanOrEqual(2);
      expect(rowRequests.at(-1)?.searchParams.get("filters")).toContain("collection_status");
    });

    expect(document.querySelector('[aria-label="销项发票收款情况表"]')).toBe(tableBefore);
    expect(within(tabs).getAllByRole('tab')).toHaveLength(7);
    expect(screen.queryByText('更新中…')).not.toBeInTheDocument();
  });

  test("统计使用完整范围张数，切换复用单一筛选且保留搜索", async () => {
    const fetchMock = installFetchMock(() => ({ ...rowsPayload, rows: rowsPayload.rows.slice(0, 1) }));
    const user = userEvent.setup();
    renderAuthenticatedAppAt("/output-invoice-collections");
    const tabs = await screen.findByRole("tablist", { name: "销项发票状态分类" });
    await within(tabs).findByRole("tab", { name: "全部 6 张" });
    expect(within(tabs).getAllByRole("tab")).toHaveLength(7);
    await user.type(screen.getByRole("searchbox", { name: "搜索销项发票收款情况" }), "客户");
    await user.click(screen.getByRole("button", { name: "查询", exact: true }));
    await user.click(await within(tabs).findByRole("tab", { name: "已收款 1 张" }));
    await waitFor(() => {
      const url = new URL(String(fetchMock.mock.calls.at(-1)?.[0]), "http://localhost");
      expect(url.searchParams.get("keyword")).toBe("客户");
      expect(url.searchParams.get("page")).toBe("1");
      expect(JSON.parse(decodeURIComponent(url.searchParams.get("filters")!))).toEqual([{ field: "collection_status", operator: "in", values: ["collected"] }]);
    });
    await user.click(await within(tabs).findByRole("tab", { name: "全部 6 张" }));
    await waitFor(() => {
      const url = new URL(String(fetchMock.mock.calls.at(-1)?.[0]), "http://localhost");
      expect(url.searchParams.get("keyword")).toBe("客户");
      expect(url.searchParams.has("filters")).toBe(false);
    });
  });

  test("顶部单选替换状态且表头不再提供重复筛选", async () => {
    const fetchMock = installFetchMock(); const user = userEvent.setup();
    renderAuthenticatedAppAt('/output-invoice-collections');
    await screen.findByRole('grid', { name: '销项发票收款情况表' });
    expect(screen.queryByRole('button', { name: '筛选 状态' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: '已收款 1 张' }));
    await user.click(screen.getByRole('tab', { name: '待收款 1 张' }));
    await waitFor(() => {
      const url = new URL(String(fetchMock.mock.calls.at(-1)?.[0]), 'http://localhost');
      expect(JSON.parse(decodeURIComponent(url.searchParams.get('filters')!))).toEqual([{field:'collection_status',operator:'in',values:['pending_collection']}]);
    });
  });

  test("无效统计明确报错，保留表格但不显示假零或允许旧结果导出", async () => {
    let invalid = false;
    installFetchMock(() => invalid ? { ...rowsPayload, filter_options: [] } : rowsPayload);
    const user = userEvent.setup();
    renderAuthenticatedAppAt("/output-invoice-collections");
    await screen.findByRole("tab", { name: "全部 6 张" });
    const table = screen.getByRole("grid", { name: "销项发票收款情况表" });
    invalid = true;
    await user.click(screen.getByRole("button", { name: "刷新", exact: true }));
    expect(await screen.findByRole("alert")).toHaveTextContent("分类统计不完整或无效");
    expect(screen.getByRole("tab", { name: "全部 — 张" })).toBeInTheDocument();
    expect(screen.getByRole("grid", { name: "销项发票收款情况表" })).toBe(table);
    expect(screen.getByRole("button", { name: "筛选内容导出" })).toBeDisabled();
  });

  test("详情只读取统一事实源与正式关联关系", async () => {
    const fetchMock = installFetchMock();
    const user = userEvent.setup();

    renderAuthenticatedAppAt("/output-invoice-collections");

    await user.click(await screen.findByRole("button", { name: "查看发票 XSFP-BLUE-001 详情" }));
    const invoiceDrawer = await screen.findByRole("dialog", { name: "发票详情" });
    expect(await within(invoiceDrawer).findByText("云南客户有限公司")).toBeVisible();
    await user.click(within(invoiceDrawer).getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(screen.getByRole("button", { name: "查看发票 XSFP-RED-001 详情" }));
    const redInvoiceDrawer = await screen.findByRole("dialog", { name: "发票详情" });
    expect(within(redInvoiceDrawer).queryByText("被冲红蓝字发票号码")).not.toBeInTheDocument();
    expect(await within(redInvoiceDrawer).findByText("被红冲蓝字数电发票号码：26532000000395506981")).toBeVisible();
    await user.click(within(redInvoiceDrawer).getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(screen.getByRole("button", { name: "红蓝票 · 2" }));
    const relationDrawer = await screen.findByRole("dialog", { name: "发票详情" });
    expect(await within(relationDrawer).findByRole("heading", { name: "发票 1" })).toBeVisible();
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
