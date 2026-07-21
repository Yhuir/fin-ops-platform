import {
  buildWorkbenchDisplayGroups,
  buildWorkbenchPaneRows,
  collectWorkbenchFilterOptions,
  createEmptyWorkbenchZoneDisplayState,
} from "../features/workbench/groupDisplayModel";
import type { WorkbenchRelationGroup, WorkbenchRecord, WorkbenchRecordType } from "../features/workbench/types";
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
    const groups: WorkbenchRelationGroup[] = [
      {
        id: "group-1",
        groupType: "unpaired",
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
    const groups: WorkbenchRelationGroup[] = [
      {
        id: "group-1",
        groupType: "unpaired",
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
    state.searchQuery = "赵华";

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
    const groups: WorkbenchRelationGroup[] = [
      {
        id: "group-late",
        groupType: "unpaired",
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
        groupType: "unpaired",
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
        groupType: "unpaired",
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
    const groups: WorkbenchRelationGroup[] = [
      {
        id: "group-march",
        groupType: "unpaired",
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
        groupType: "unpaired",
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
    const groups: WorkbenchRelationGroup[] = [
      {
        id: "group-late",
        groupType: "unpaired",
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
        groupType: "unpaired",
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
        groupType: "unpaired",
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

  test("searches a whole zone while typing and keeps the paired zone query independent", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("陈涛", {}, { timeout: 3_000 });

    const unpairedZone = screen.getByTestId("zone-unpaired");
    const pairedZone = screen.getByTestId("zone-paired");
    const unpairedSearch = within(unpairedZone).getByRole("searchbox", { name: "搜索未配对区域" });
    const pairedSearch = within(pairedZone).getByRole("searchbox", { name: "搜索已配对区域" });

    expect(within(unpairedZone).queryByRole("searchbox", { name: "搜索 OA" })).not.toBeInTheDocument();
    fireEvent.change(unpairedSearch, { target: { value: "陈涛" } });

    await waitFor(() => {
      expect(within(unpairedZone).queryByTestId("candidate-group-unpaired-row:oa-o-202603-002")).not.toBeInTheDocument();
    });
    expect(within(unpairedZone).getAllByText((content) => content.includes("智能工厂设备商"))).toHaveLength(1);
    expect(within(unpairedZone).queryByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).not.toBeInTheDocument();
    expect(pairedSearch).toHaveValue("");
    expect(within(unpairedZone).getAllByText("陈涛").some((node) => node.classList.contains("search-hit"))).toBe(true);

    fireEvent.click(within(unpairedZone).getByRole("button", { name: "清空搜索" }));
    await waitFor(() => {
      expect(within(unpairedZone).getByTestId("candidate-group-unpaired-row:oa-o-202603-002")).toBeInTheDocument();
    });
    expect(unpairedSearch).toHaveValue("");
  });

  test("runs a zone search entered before the initial page load finishes", async () => {
    const fetchMock = installMockApiFetch({ workbenchLoadDelayMs: 600 });
    renderWorkbenchPage();

    const unpairedZone = await screen.findByTestId("zone-unpaired");
    const unpairedSearch = within(unpairedZone).getByRole("searchbox", { name: "搜索未配对区域" });
    fireEvent.change(unpairedSearch, { target: { value: "智能工厂" } });

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => {
        const url = new URL(String(input), "http://localhost");
        const unpairedQuery = JSON.parse(url.searchParams.get("unpaired_query") ?? "{}") as Record<string, unknown>;
        return url.pathname === "/api/workbench" && unpairedQuery.search === "智能工厂";
      })).toBe(true);
    }, { timeout: 3_000 });
  });

  test("supports multi-select column filtering with select-all and clear actions", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("陈涛");

    const unpairedZone = screen.getByTestId("zone-unpaired");
    const openOaPane = within(unpairedZone).getByTestId("pane-oa");

    fireEvent.click(within(openOaPane).getByRole("button", { name: "筛选 申请人" }));

    const menu = screen.getByRole("dialog", { name: "筛选 申请人" });
    fireEvent.click(within(menu).getByLabelText("陈涛"));

    await waitFor(() => {
      expect(within(unpairedZone).getAllByText("陈涛").length).toBeGreaterThan(0);
      expect(within(unpairedZone).queryByTestId("candidate-group-unpaired-row:oa-o-202603-002")).not.toBeInTheDocument();
    });

    fireEvent.click(within(menu).getByRole("button", { name: "全选" }));
    await waitFor(() => {
      expect(within(unpairedZone).getAllByText("陈涛").length).toBeGreaterThan(0);
      within(menu).getAllByRole("checkbox").forEach((checkbox) => {
        expect(checkbox).toBeChecked();
      });
    });

    fireEvent.click(within(menu).getByRole("button", { name: "清空" }));
    await waitFor(() => {
      expect(within(unpairedZone).getAllByText("陈涛").length).toBeGreaterThan(0);
      expect(within(unpairedZone).getByTestId("candidate-group-unpaired-row:oa-o-202603-002")).toBeInTheDocument();
    });
  });

  test("applies pane search and column filters locally while the server page refresh is pending", async () => {
    const fetchMock = installMockApiFetch({ workbenchLoadDelayMs: 1000 });
    renderWorkbenchPage();
    await screen.findByTestId("zone-unpaired", {}, { timeout: 3000 });

    const unpairedZone = screen.getByTestId("zone-unpaired");
    const openBankPane = within(unpairedZone).getByTestId("pane-bank");
    await waitFor(() => {
      expect(within(unpairedZone).getByRole("row", { name: /智能工厂设备商.*建设银行 1138/ })).toBeInTheDocument();
      expect(within(unpairedZone).getByRole("row", { name: /尾差设备商.*建设银行 1138/ })).toBeInTheDocument();
    }, { timeout: 3000 });

    fireEvent.change(within(unpairedZone).getByRole("searchbox", { name: "搜索未配对区域" }), {
      target: { value: "智能工厂" },
    });
    fireEvent.click(within(openBankPane).getByRole("button", { name: "筛选 金额" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "筛选 金额" })).getByLabelText("建设银行 1138"));

    await waitFor(() => {
      expect(within(unpairedZone).getByRole("row", { name: /智能工厂设备商.*建设银行 1138/ })).toBeInTheDocument();
      expect(within(unpairedZone).queryByRole("row", { name: /尾差设备商.*建设银行 1138/ })).not.toBeInTheDocument();
    }, { timeout: 400 });
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => {
        const url = new URL(String(input), "http://localhost");
        const unpairedQuery = JSON.parse(url.searchParams.get("unpaired_query") ?? "{}") as Record<string, unknown>;
        return url.pathname === "/api/workbench"
          && unpairedQuery.search === "智能工厂"
          && !("search_by_pane" in unpairedQuery)
          && !("search_mode" in unpairedQuery);
      })).toBe(true);
    }, { timeout: 3000 });
  });

  test("uses direction and payment account options for the bank amount filter instead of raw amounts", () => {
    const groups: WorkbenchRelationGroup[] = [
      {
        id: "group-1",
        groupType: "unpaired",
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
    const groups: WorkbenchRelationGroup[] = [
      {
        id: "split-bank-criteria",
        groupType: "unpaired",
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
        groupType: "unpaired",
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
    state.searchQuery = "建行";
    state.filtersByPaneAndColumn.bank = {
      amount: ["支出"],
    };

    const displayGroups = buildWorkbenchDisplayGroups(groups, state);

    expect(displayGroups.map((group) => group.id)).toEqual(["split-bank-criteria", "same-bank-row-criteria"]);
    expect(displayGroups[0].rows.bank.map((row) => row.id)).toEqual(["bank-expense-ms"]);
    expect(displayGroups[1].rows.bank.map((row) => row.id)).toEqual(["bank-expense-ccb"]);
  });

  test("requires all selected bank amount filter values on the same row", () => {
    const groups: WorkbenchRelationGroup[] = [
      {
        id: "split-bank-filter-values",
        groupType: "unpaired",
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
        groupType: "unpaired",
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

  test("matches any selected value within an ordinary scalar column", () => {
    const groups: WorkbenchRelationGroup[] = [
      {
        id: "oa-chen",
        groupType: "unpaired",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [buildRow("oa-chen-row", "oa", { applicant: "陈涛" })],
          bank: [],
          invoice: [],
        },
      },
      {
        id: "oa-sun",
        groupType: "unpaired",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [buildRow("oa-sun-row", "oa", { applicant: "孙敏" })],
          bank: [],
          invoice: [],
        },
      },
      {
        id: "oa-lin",
        groupType: "unpaired",
        matchConfidence: "medium",
        reason: "test",
        rows: {
          oa: [buildRow("oa-lin-row", "oa", { applicant: "林晨" })],
          bank: [],
          invoice: [],
        },
      },
    ];
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "oa";
    state.filtersByPaneAndColumn.oa = {
      applicant: ["陈涛", "孙敏"],
    };

    expect(buildWorkbenchDisplayGroups(groups, state).map((group) => group.id)).toEqual(["oa-chen", "oa-sun"]);
  });
});
