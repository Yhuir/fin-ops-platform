import { screen, within } from "@testing-library/react";

import { reorderWorkbenchColumnLayout } from "../features/workbench/columnLayout";
import { getWorkbenchPaneGridStyle } from "../features/workbench/tableConfig";
import { fetchWorkbenchSettings, saveWorkbenchSettings } from "../features/workbench/api";
import { installMockApiFetch } from "./apiMock";
import { renderWorkbenchPage } from "./renderHelpers";

describe("Workbench column layout", () => {
  test("reorders a pane layout before the target column", () => {
    const nextLayouts = reorderWorkbenchColumnLayout(
      {
        oa: ["applicant", "projectName", "amount", "counterparty", "reason"],
        bank: ["counterparty", "amount", "loanRepaymentDate", "note"],
        invoice: ["sellerName", "buyerName", "issueDate", "amount", "grossAmount"],
      },
      "oa",
      "reason",
      "projectName",
      "before",
    );

    expect(nextLayouts.oa).toEqual(["applicant", "reason", "projectName", "amount", "counterparty"]);
  });

  test("keeps bank column widths bound to the column after reorder", () => {
    const gridStyle = getWorkbenchPaneGridStyle(
      "bank",
      {
        oa: ["applicant", "projectName", "amount", "counterparty", "reason"],
        bank: ["amount", "counterparty", "loanRepaymentDate", "note"],
        invoice: ["sellerName", "buyerName", "issueDate", "amount", "grossAmount"],
      },
      false,
    );

    expect(gridStyle.gridTemplateColumns).toBe(
      "minmax(144px, 144fr) minmax(176px, 176fr) minmax(108px, 108fr) minmax(168px, 168fr)",
    );
    expect(gridStyle.minWidth).toBe("596px");
  });

  test("renders drag handles for pane column headers", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const bankPane = screen.getAllByTestId("pane-bank")[0];
    expect(within(bankPane).getByRole("button", { name: "拖动 对方户名 列" })).toBeInTheDocument();
    expect(within(bankPane).getByRole("button", { name: "拖动 金额 列" })).toBeInTheDocument();
  });

  test("restores a saved pane layout on the next render", async () => {
    installMockApiFetch();
    const settings = await fetchWorkbenchSettings();
    await saveWorkbenchSettings({
      completedProjectIds: settings.projects.completedProjectIds,
      bankAccountMappings: settings.bankAccountMappings,
      allowedUsernames: settings.accessControl.allowedUsernames,
      readonlyExportUsernames: settings.accessControl.readonlyExportUsernames,
      adminUsernames: settings.accessControl.adminUsernames,
      oaRetention: settings.oaRetention,
      workbenchColumnLayouts: {
        ...settings.workbenchColumnLayouts,
        bank: ["amount", "counterparty", "loanRepaymentDate", "note"],
      },
    });

    const rendered = renderWorkbenchPage();
    await screen.findByText("赵华");

    rendered.unmount();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const rerenderedBankPane = screen.getAllByTestId("pane-bank")[0];
    const headerNames = within(rerenderedBankPane)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.replace(/\s+/g, "") ?? "");

    expect(headerNames.slice(0, 4)).toEqual(["金额", "对方户名", "还借款日期", "备注"]);
  });

  test("saveWorkbenchSettings keeps column layouts across a fresh settings fetch", async () => {
    installMockApiFetch();
    const settings = await fetchWorkbenchSettings();

    await saveWorkbenchSettings({
      completedProjectIds: settings.projects.completedProjectIds,
      bankAccountMappings: settings.bankAccountMappings,
      allowedUsernames: settings.accessControl.allowedUsernames,
      readonlyExportUsernames: settings.accessControl.readonlyExportUsernames,
      adminUsernames: settings.accessControl.adminUsernames,
      oaRetention: settings.oaRetention,
      workbenchColumnLayouts: {
        ...settings.workbenchColumnLayouts,
        invoice: ["issueDate", "sellerName", "buyerName", "amount", "grossAmount"],
      },
    });

    const refreshed = await fetchWorkbenchSettings();
    expect(refreshed.workbenchColumnLayouts.invoice).toEqual([
      "issueDate",
      "sellerName",
      "buyerName",
      "amount",
      "grossAmount",
    ]);
  });
});
