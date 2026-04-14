import {
  buildWorkbenchDisplayGroups,
  createEmptyWorkbenchZoneDisplayState,
} from "../features/workbench/groupDisplayModel";
import type { WorkbenchCandidateGroup, WorkbenchRecord } from "../features/workbench/types";

function buildBankRow(id: string, transactionTime: string): WorkbenchRecord {
  return {
    id,
    caseId: `case-${id}`,
    recordType: "bank",
    label: `bank-${id}`,
    status: "待处理",
    statusCode: "open",
    statusTone: "warn",
    exceptionHandled: false,
    amount: "100.00",
    counterparty: `counterparty-${id}`,
    tableValues: {
      transactionTime,
    },
    detailFields: [],
    actionVariant: "detail-only",
    availableActions: ["detail"],
  };
}

function buildGroup(id: string, transactionTime: string): WorkbenchCandidateGroup {
  return {
    id,
    groupType: "candidate",
    matchConfidence: "medium",
    reason: "test",
    rows: {
      oa: [],
      bank: [buildBankRow(id, transactionTime)],
      invoice: [],
    },
  };
}

describe("groupDisplayModel time filter", () => {
  test("filters bank groups by year and month when bank pane is active", () => {
    const groups = [
      buildGroup("group-2025-12", "2025-12-18 10:00"),
      buildGroup("group-2026-03", "2026-03-28 10:18"),
      buildGroup("group-2026-04", "2026-04-20 09:15"),
    ];

    const yearState = {
      ...createEmptyWorkbenchZoneDisplayState(),
      activePaneId: "bank",
      timeFilterByPane: {
        oa: { mode: "none" },
        bank: { mode: "year", year: "2026" },
        invoice: { mode: "none" },
      },
    } as ReturnType<typeof createEmptyWorkbenchZoneDisplayState> & {
      timeFilterByPane: {
        oa: { mode: "none" };
        bank: { mode: "year"; year: string };
        invoice: { mode: "none" };
      };
    };

    expect(buildWorkbenchDisplayGroups(groups, yearState).map((group) => group.id)).toEqual([
      "group-2026-03",
      "group-2026-04",
    ]);

    const monthState = {
      ...yearState,
      timeFilterByPane: {
        oa: { mode: "none" },
        bank: { mode: "month", month: "2026-04" },
        invoice: { mode: "none" },
      },
    } as ReturnType<typeof createEmptyWorkbenchZoneDisplayState> & {
      timeFilterByPane: {
        oa: { mode: "none" };
        bank: { mode: "month"; month: string };
        invoice: { mode: "none" };
      };
    };

    expect(buildWorkbenchDisplayGroups(groups, monthState).map((group) => group.id)).toEqual(["group-2026-04"]);
  });
});
