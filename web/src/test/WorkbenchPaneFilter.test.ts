import {
  buildWorkbenchDisplayGroups,
  buildWorkbenchPaneRows,
  collectWorkbenchFilterOptions,
  createEmptyWorkbenchZoneDisplayState,
} from "../features/workbench/groupDisplayModel";
import type { WorkbenchCandidateGroup, WorkbenchRecord, WorkbenchRecordType } from "../features/workbench/types";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { installMockApiFetch } from "./apiMock";
import { renderWorkbenchPage } from "./workbenchRenderHelpers";

function buildRow(id: string, recordType: WorkbenchRecordType, tableValues: Record<string, string>): WorkbenchRecord {
  return {
    id,
    caseId: `case:${id}`,
    recordType,
    label: recordType.toUpperCase(),
    status: "待处理",
    statusCode: "pending",
    statusTone: "warning",
    exceptionHandled: false,
    amount: tableValues.amount ?? "--",
    counterparty: tableValues.counterparty ?? tableValues.projectName ?? tableValues.sellerName ?? "--",
    tableValues,
    detailFields: [],
    actionVariant: "detail-only",
    availableActions: ["detail"],
  };
}

describe("Workbench pane display model", () => {
  test("keeps original groups when no pane search or filter is active", () => {
    const groups: WorkbenchCandidateGroup[] = [
      {
        id: "group-1",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [buildRow("oa-1", "oa", { applicant: "赵华", projectName: "华东改造项目", counterparty: "中科视拓" })],
          bank: [buildRow("bank-1", "bank", { counterparty: "中科视拓", amount: "500.00", loanRepaymentDate: "--" })],
          invoice: [buildRow("invoice-1", "invoice", { sellerName: "中科视拓", buyerName: "云南溯源", issueDate: "2026-03-01" })],
        },
      },
    ];

    expect(buildWorkbenchDisplayGroups(groups, createEmptyWorkbenchZoneDisplayState())).toEqual(groups);
  });

  test("keeps the matched candidate group visible across panes while searching by one pane", () => {
    const groups: WorkbenchCandidateGroup[] = [
      {
        id: "group-1",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [
            buildRow("oa-1", "oa", { applicant: "赵华", projectName: "华东改造项目", counterparty: "中科视拓" }),
            buildRow("oa-2", "oa", { applicant: "陈涛", projectName: "智能工厂设备商", counterparty: "智能工厂设备商" }),
          ],
          bank: [buildRow("bank-1", "bank", { counterparty: "中科视拓", amount: "500.00", loanRepaymentDate: "--" })],
          invoice: [buildRow("invoice-1", "invoice", { sellerName: "中科视拓", buyerName: "云南溯源", issueDate: "2026-03-01" })],
        },
      },
    ];
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "oa";
    state.openSearchPaneId = "oa";
    state.searchQueryByPane.oa = "赵华";

    const displayGroups = buildWorkbenchDisplayGroups(groups, state);
    const paneRows = buildWorkbenchPaneRows(displayGroups);

    expect(displayGroups).toHaveLength(1);
    expect(displayGroups[0].rows.oa).toHaveLength(2);
    expect(displayGroups[0].rows.oa[0]?.id).toBe("oa-1");
    expect(displayGroups[0].rows.bank).toHaveLength(1);
    expect(displayGroups[0].rows.invoice).toHaveLength(1);
    expect(paneRows.oa.map((row) => row.id)).toEqual(["oa-1", "oa-2"]);
    expect(paneRows.bank.map((row) => row.id)).toEqual(["bank-1"]);
    expect(paneRows.invoice.map((row) => row.id)).toEqual(["invoice-1"]);
  });

  test("sorts groups by bank transaction time for the active pane and keeps groups without bank rows last", () => {
    const groups: WorkbenchCandidateGroup[] = [
      {
        id: "group-late",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [buildRow("oa-late", "oa", { applicant: "赵华", projectName: "华东改造项目", counterparty: "中科视拓" })],
          bank: [buildRow("bank-late", "bank", { counterparty: "中科视拓", transactionTime: "2026-03-28 10:18" })],
          invoice: [],
        },
      },
      {
        id: "group-empty",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [buildRow("oa-empty", "oa", { applicant: "陈涛", projectName: "智能工厂设备商", counterparty: "智能工厂设备商" })],
          bank: [],
          invoice: [],
        },
      },
      {
        id: "group-early",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [buildRow("oa-early", "oa", { applicant: "孙悦", projectName: "维保补录项目", counterparty: "独立服务商" })],
          bank: [buildRow("bank-early", "bank", { counterparty: "独立服务商", transactionTime: "2026-03-27 09:40" })],
          invoice: [],
        },
      },
    ];
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "bank";
    state.sortByPane.bank = "asc";

    expect(buildWorkbenchDisplayGroups(groups, state).map((group) => group.id)).toEqual([
      "group-early",
      "group-late",
      "group-empty",
    ]);
  });

  test("sorts groups by invoice issue date descending for the active pane", () => {
    const groups: WorkbenchCandidateGroup[] = [
      {
        id: "group-march",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [],
          bank: [],
          invoice: [buildRow("invoice-march", "invoice", { sellerName: "A", buyerName: "B", issueDate: "2026-03-25" })],
        },
      },
      {
        id: "group-april",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [],
          bank: [],
          invoice: [buildRow("invoice-april", "invoice", { sellerName: "C", buyerName: "D", issueDate: "2026-04-05" })],
        },
      },
    ];
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "invoice";
    state.sortByPane.invoice = "desc";

    expect(buildWorkbenchDisplayGroups(groups, state).map((group) => group.id)).toEqual([
      "group-april",
      "group-march",
    ]);
  });

  test("sorts groups by OA approval time for the active pane", () => {
    const groups: WorkbenchCandidateGroup[] = [
      {
        id: "group-late",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [buildRow("oa-late", "oa", { applicant: "赵华", applicationTime: "2026-03-28 18:10" })],
          bank: [],
          invoice: [],
        },
      },
      {
        id: "group-empty",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [buildRow("oa-empty", "oa", { applicant: "陈涛" })],
          bank: [],
          invoice: [],
        },
      },
      {
        id: "group-early",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [buildRow("oa-early", "oa", { applicant: "孙悦", applicationTime: "2026-03-26 09:20" })],
          bank: [],
          invoice: [],
        },
      },
    ];
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "oa";
    state.sortByPane.oa = "asc";

    expect(buildWorkbenchDisplayGroups(groups, state).map((group) => group.id)).toEqual([
      "group-early",
      "group-late",
      "group-empty",
    ]);
  });

  test("searches while typing and only clears pane-local search from the inner clear action", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("陈涛");

    const openZone = screen.getByTestId("zone-open");
    const openOaPane = within(openZone).getByTestId("pane-oa");
    const openBankPane = within(openZone).getByTestId("pane-bank");
    const openInvoicePane = within(openZone).getByTestId("pane-invoice");

    fireEvent.click(within(openOaPane).getByRole("button", { name: "搜索 OA" }));

    const oaSearchInput = within(openOaPane).getByRole("searchbox", { name: "搜索 OA" });
    expect(oaSearchInput.closest(".pane-search-popover")).not.toBeNull();
    expect(within(openOaPane).getByRole("button", { name: "收起搜索 OA" })).toHaveClass("pane-search-toggle-btn", "fixed");
    fireEvent.change(oaSearchInput, { target: { value: "陈涛" } });

    await waitFor(() => {
      expect(within(openZone).queryByTestId("candidate-group-open-row:oa-o-202603-002")).not.toBeInTheDocument();
    });
    expect(within(openZone).getAllByText((content) => content.includes("智能工厂设备商")).length).toBeGreaterThan(1);
    expect(oaSearchInput.closest(".pane-search-field")).not.toBeNull();
    expect(within(openOaPane).getByRole("button", { name: "收起搜索 OA" })).toHaveClass("pane-search-toggle-btn", "fixed");
    expect(within(openOaPane).getByRole("button", { name: "清空搜索 OA" })).toBeInTheDocument();

    fireEvent.click(within(openOaPane).getByRole("button", { name: "收起搜索 OA" }));
    expect(within(openOaPane).queryByRole("searchbox", { name: "搜索 OA" })).not.toBeInTheDocument();
    expect(within(openOaPane).getByRole("button", { name: "搜索 OA，当前关键词 陈涛" })).toHaveTextContent("陈涛");

    fireEvent.click(within(openOaPane).getByRole("button", { name: "搜索 OA，当前关键词 陈涛" }));
    const reopenedOaSearchInput = within(openOaPane).getByRole("searchbox", { name: "搜索 OA" });
    expect(reopenedOaSearchInput).toBeInTheDocument();
    expect(within(openOaPane).getByRole("button", { name: "收起搜索 OA" })).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(within(openOaPane).queryByRole("searchbox", { name: "搜索 OA" })).not.toBeInTheDocument();
    expect(within(openOaPane).getByRole("button", { name: "搜索 OA，当前关键词 陈涛" })).toHaveTextContent("陈涛");

    fireEvent.click(within(openBankPane).getByRole("button", { name: "搜索 银行流水" }));
    expect(within(openBankPane).getByRole("searchbox", { name: "搜索 银行流水" })).toBeInTheDocument();
    expect(within(openOaPane).getByRole("button", { name: "搜索 OA，当前关键词 陈涛" })).toHaveTextContent("陈涛");

    fireEvent.click(within(openOaPane).getByRole("button", { name: "搜索 OA，当前关键词 陈涛" }));
    expect(within(openOaPane).getByRole("searchbox", { name: "搜索 OA" })).toBeInTheDocument();
    fireEvent.click(within(openOaPane).getByRole("button", { name: "清空搜索 OA" }));
    await waitFor(() => {
      expect(within(openZone).getByTestId("candidate-group-open-row:oa-o-202603-002")).toBeInTheDocument();
    });
    expect(within(openOaPane).getByRole("searchbox", { name: "搜索 OA" })).toHaveValue("");
    expect(within(openOaPane).getByRole("button", { name: "收起搜索 OA" })).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(within(openOaPane).getByRole("button", { name: "搜索 OA" })).toBeInTheDocument();
  });

  test("supports multi-select column filtering with select-all and clear actions", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("陈涛");

    const openZone = screen.getByTestId("zone-open");
    const openOaPane = within(openZone).getByTestId("pane-oa");

    fireEvent.click(within(openOaPane).getByRole("button", { name: "筛选 申请人" }));

    const menu = screen.getByRole("dialog", { name: "筛选 申请人" });
    fireEvent.click(within(menu).getByLabelText("陈涛"));

    await waitFor(() => {
      expect(within(openZone).getAllByText("陈涛").length).toBeGreaterThan(0);
      expect(within(openZone).queryByTestId("candidate-group-open-row:oa-o-202603-002")).not.toBeInTheDocument();
    });

    fireEvent.click(within(menu).getByRole("button", { name: "全选" }));
    await waitFor(() => {
      expect(within(openZone).getAllByText("陈涛").length).toBeGreaterThan(0);
      expect(within(openZone).queryByTestId("candidate-group-open-row:oa-o-202603-002")).not.toBeInTheDocument();
    });

    fireEvent.click(within(menu).getByRole("button", { name: "清空" }));
    await waitFor(() => {
      expect(within(openZone).getAllByText("陈涛").length).toBeGreaterThan(0);
      expect(within(openZone).getByTestId("candidate-group-open-row:oa-o-202603-002")).toBeInTheDocument();
    });
  });

  test("applies pane search and column filters locally while the server page refresh is pending", async () => {
    const fetchMock = installMockApiFetch({ workbenchLoadDelayMs: 1000 });
    renderWorkbenchPage();
    await screen.findByTestId("zone-open", {}, { timeout: 3000 });

    const openZone = screen.getByTestId("zone-open");
    const openBankPane = within(openZone).getByTestId("pane-bank");
    await waitFor(() => {
      expect(within(openZone).getByRole("row", { name: /智能工厂设备商.*建设银行 1138/ })).toBeInTheDocument();
      expect(within(openZone).getByRole("row", { name: /尾差设备商.*建设银行 1138/ })).toBeInTheDocument();
    }, { timeout: 3000 });

    fireEvent.click(within(openBankPane).getByRole("button", { name: "搜索 银行流水" }));
    fireEvent.change(within(openBankPane).getByRole("searchbox", { name: "搜索 银行流水" }), {
      target: { value: "智能工厂" },
    });
    fireEvent.click(within(openBankPane).getByRole("button", { name: "筛选 金额" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "筛选 金额" })).getByLabelText("建设银行 1138"));

    await waitFor(() => {
      expect(within(openZone).getByRole("row", { name: /智能工厂设备商.*建设银行 1138/ })).toBeInTheDocument();
      expect(within(openZone).queryByRole("row", { name: /尾差设备商.*建设银行 1138/ })).not.toBeInTheDocument();
    }, { timeout: 400 });
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => {
        const url = new URL(String(input), "http://localhost");
        return (
          url.pathname === "/api/workbench/groups"
          && url.searchParams.get("search") === "智能工厂"
          && url.searchParams.get("search_mode") === "linked_context"
          && !url.searchParams.has("search_by_pane")
        );
      })).toBe(true);
    }, { timeout: 3000 });
  });

  test("uses direction and payment account options for the bank amount filter instead of raw amounts", () => {
    const groups: WorkbenchCandidateGroup[] = [
      {
        id: "group-1",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [],
          bank: [
            buildRow("bank-1", "bank", {
              counterparty: "中科视拓",
              amount: "500.00",
              direction: "支出",
              paymentAccount: "建行 8106",
            }),
            buildRow("bank-2", "bank", {
              counterparty: "云南溯源",
              amount: "800.00",
              direction: "收入",
              paymentAccount: "民生 9486",
            }),
          ],
          invoice: [],
        },
      },
    ];

    expect(collectWorkbenchFilterOptions(groups, "bank", "amount")).toEqual([
      "支出",
      "收入",
      "建行 8106",
      "民生 9486",
    ]);
  });

  test("combines linked search with bank dropdown filters without forcing the same row", () => {
    const groups: WorkbenchCandidateGroup[] = [
      {
        id: "split-bank-criteria",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [],
          bank: [
            buildRow("bank-income-ccb", "bank", {
              counterparty: "建行客户",
              amount: "800.00",
              direction: "收入",
              paymentAccount: "建行 8106",
            }),
            buildRow("bank-expense-ms", "bank", {
              counterparty: "民生供应商",
              amount: "500.00",
              direction: "支出",
              paymentAccount: "民生 9486",
            }),
          ],
          invoice: [],
        },
      },
      {
        id: "same-bank-row-criteria",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [],
          bank: [
            buildRow("bank-expense-ccb", "bank", {
              counterparty: "建行供应商",
              amount: "300.00",
              direction: "支出",
              paymentAccount: "建行 8106",
            }),
          ],
          invoice: [],
        },
      },
    ];
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "bank";
    state.searchQueryByPane.bank = "建行";
    state.filtersByPaneAndColumn.bank = {
      amount: ["支出"],
    };

    const displayGroups = buildWorkbenchDisplayGroups(groups, state);

    expect(displayGroups.map((group) => group.id)).toEqual(["split-bank-criteria", "same-bank-row-criteria"]);
    expect(displayGroups[0].rows.bank.map((row) => row.id)).toEqual(["bank-expense-ms"]);
    expect(displayGroups[1].rows.bank.map((row) => row.id)).toEqual(["bank-expense-ccb"]);
  });

  test("requires all selected bank amount filter values on the same row", () => {
    const groups: WorkbenchCandidateGroup[] = [
      {
        id: "split-bank-filter-values",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [],
          bank: [
            buildRow("bank-income-ccb", "bank", {
              counterparty: "建行客户",
              amount: "800.00",
              direction: "收入",
              paymentAccount: "建行 8106",
            }),
            buildRow("bank-expense-ms", "bank", {
              counterparty: "民生供应商",
              amount: "500.00",
              direction: "支出",
              paymentAccount: "民生 9486",
            }),
          ],
          invoice: [],
        },
      },
      {
        id: "same-bank-filter-values",
        groupType: "candidate",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [],
          bank: [
            buildRow("bank-expense-ccb", "bank", {
              counterparty: "建行供应商",
              amount: "300.00",
              direction: "支出",
              paymentAccount: "建行 8106",
            }),
          ],
          invoice: [],
        },
      },
    ];
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "bank";
    state.filtersByPaneAndColumn.bank = {
      amount: ["支出", "建行 8106"],
    };

    const displayGroups = buildWorkbenchDisplayGroups(groups, state);

    expect(displayGroups.map((group) => group.id)).toEqual(["same-bank-filter-values"]);
    expect(displayGroups[0].rows.bank.map((row) => row.id)).toEqual(["bank-expense-ccb"]);
  });
});
