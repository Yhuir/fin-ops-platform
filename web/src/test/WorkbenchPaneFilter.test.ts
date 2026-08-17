import {
  buildWorkbenchDisplayGroups,
  buildWorkbenchPaneRows,
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
        return url.pathname === "/api/workbench/groups"
          && url.searchParams.get("zone") === "unpaired"
          && url.searchParams.get("search") === "智能工厂";
      })).toBe(true);
    }, { timeout: 3_000 });
    expect(fetchMock.mock.calls.filter(([input]) => {
      const url = new URL(String(input), "http://localhost");
      return url.pathname === "/api/workbench";
    })).toHaveLength(1);
  });

  test("loads complete column options from the workbench facet API and clears the active filter", async () => {
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("陈涛");

    const unpairedZone = screen.getByTestId("zone-unpaired");
    const openOaPane = within(unpairedZone).getByTestId("pane-oa");

    fireEvent.click(within(openOaPane).getByRole("button", { name: "筛选 申请人" }));

    const menu = await screen.findByRole("dialog", { name: "筛选 申请人" });
    const chenOption = await within(menu).findByRole("checkbox", { name: "陈涛" });
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(String(input), "http://localhost");
      return url.pathname === "/api/workbench/filter-options"
        && url.searchParams.get("zone") === "unpaired"
        && url.searchParams.get("pane") === "oa"
        && url.searchParams.get("column") === "applicant";
    })).toBe(true);
    fireEvent.click(chenOption);

    await waitFor(() => {
      expect(within(unpairedZone).getAllByText("陈涛").length).toBeGreaterThan(0);
      expect(within(unpairedZone).queryByTestId("candidate-group-unpaired-row:oa-o-202603-002")).not.toBeInTheDocument();
    });

    expect(within(menu).queryByRole("button", { name: "全选" })).not.toBeInTheDocument();
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
    fireEvent.click(
      await within(screen.getByRole("dialog", { name: "筛选 金额" })).findByLabelText(
        "建设银行 1138",
        {},
        { timeout: 3_000 },
      ),
    );
    fireEvent.keyDown(screen.getByRole("dialog", { name: "筛选 金额" }), { key: "Escape" });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "筛选 金额" })).not.toBeInTheDocument();
    });

    await waitFor(() => {
      expect(within(unpairedZone).getByRole("row", { name: /智能工厂设备商.*建设银行 1138/ })).toBeInTheDocument();
      expect(within(unpairedZone).queryByRole("row", { name: /尾差设备商.*建设银行 1138/ })).not.toBeInTheDocument();
    }, { timeout: 400 });
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => {
        const url = new URL(String(input), "http://localhost");
        const columnFilters = JSON.parse(url.searchParams.get("column_filters") ?? "{}") as Record<string, unknown>;
        return url.pathname === "/api/workbench/groups"
          && url.searchParams.get("zone") === "unpaired"
          && url.searchParams.get("search") === "智能工厂"
          && Object.keys(columnFilters).length > 0
          && !url.searchParams.has("cursor");
      })).toBe(true);
    }, { timeout: 3000 });
    expect(fetchMock.mock.calls.filter(([input]) => {
      const url = new URL(String(input), "http://localhost");
      return url.pathname === "/api/workbench/groups" && url.searchParams.get("zone") === "paired";
    })).toHaveLength(0);
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
      amount: ["direction:expense"],
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
      amount: ["direction:expense", "account:8106"],
    };

    const displayGroups = buildWorkbenchDisplayGroups(groups, state);

    expect(displayGroups.map((group) => group.id)).toEqual(["same-bank-filter-values"]);
    expect(displayGroups[0].rows.bank.map((row) => row.id)).toEqual(["bank-expense-ccb"]);
  });

  test("matches bank direction, account, and canonical tag on the same row", () => {
    const taggedRow = {
      ...buildRow("bank-tagged", "bank", {
        direction: "支出",
        paymentAccount: "建设银行 基本户 8106",
      }),
      categoryCode: "expense-project",
    };
    const state = createEmptyWorkbenchZoneDisplayState();
    state.filtersByPaneAndColumn.bank = {
      amount: ["direction:expense", "account:8106", "bankTag:expense-project"],
    };

    expect(buildWorkbenchDisplayGroups([{
      id: "bank-tagged-group",
      groupType: "unpaired",
      matchConfidence: "medium",
      reason: "test",
      rows: { oa: [], bank: [taggedRow], invoice: [] },
    }], state)).toHaveLength(1);
  });

  test("matches OA type, workflow status, and applicant on the same row", () => {
    const state = createEmptyWorkbenchZoneDisplayState();
    state.filtersByPaneAndColumn.oa = {
      applicant: ["oaType:支付申请", "workflow:completed", "applicant:杨丽萍"],
    };
    const row = buildRow("oa-payment", "oa", {
      applicationType: "供应商付款申请",
      workflowStatus: "completed",
      applicant: "杨丽萍",
    });

    expect(buildWorkbenchDisplayGroups([{
      id: "oa-payment-group",
      groupType: "unpaired",
      matchConfidence: "medium",
      reason: "test",
      rows: { oa: [row], bank: [], invoice: [] },
    }], state)).toHaveLength(1);
  });

  test("requires project and expense type on the same OA expense item", () => {
    const crossItemRow = {
      ...buildRow("oa-cross-items", "oa", { projectName: "多个项目" }),
      expenseItems: [
        { id: "item-1", rowIndex: "1", projectName: "大理项目", expenseType: "材料费", amount: "10.00" },
        { id: "item-2", rowIndex: "2", projectName: "曲靖项目", expenseType: "交通费", amount: "20.00" },
      ],
    };
    const matchingRow = {
      ...buildRow("oa-same-item", "oa", { projectName: "多个项目" }),
      expenseItems: [
        { id: "item-1", rowIndex: "1", projectName: "大理项目", expenseType: "交通费", amount: "30.00" },
      ],
    };
    const state = createEmptyWorkbenchZoneDisplayState();
    state.filtersByPaneAndColumn.oa = {
      projectName: ["project:大理项目", "expenseType:交通费"],
    };
    const groups: WorkbenchRelationGroup[] = [crossItemRow, matchingRow].map((row) => ({
      id: `group:${row.id}`,
      groupType: "unpaired",
      matchConfidence: "medium",
      reason: "test",
      rows: { oa: [row], bank: [], invoice: [] },
    }));

    expect(buildWorkbenchDisplayGroups(groups, state).map((group) => group.id)).toEqual([
      "group:oa-same-item",
    ]);
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
      applicant: ["applicant:陈涛", "applicant:孙敏"],
    };

    expect(buildWorkbenchDisplayGroups(groups, state).map((group) => group.id)).toEqual(["oa-chen", "oa-sun"]);
  });
});
