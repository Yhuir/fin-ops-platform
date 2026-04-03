import { screen, within } from "@testing-library/react";

import { installMockApiFetch } from "./apiMock";
import { renderWorkbenchPage } from "./renderHelpers";

describe("Workbench columns and inline actions", () => {
  test("renders requirement-aligned column headers for OA, bank, and invoice panes", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const oaPane = screen.getAllByTestId("pane-oa")[0];
    const bankPane = screen.getAllByTestId("pane-bank")[0];
    const invoicePane = screen.getAllByTestId("pane-invoice")[0];

    expect(within(oaPane).getByRole("columnheader", { name: "申请人" })).toBeInTheDocument();
    expect(within(oaPane).getByRole("columnheader", { name: "项目名称" })).toBeInTheDocument();
    expect(within(oaPane).getByRole("columnheader", { name: "申请事由" })).toBeInTheDocument();

    expect(within(bankPane).getByRole("columnheader", { name: "交易时间" })).toBeInTheDocument();
    expect(within(bankPane).getByRole("columnheader", { name: "借方发生额" })).toBeInTheDocument();
    expect(within(bankPane).getByRole("columnheader", { name: "还借款日期" })).toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "资金方向" })).not.toBeInTheDocument();

    expect(within(invoicePane).getByRole("columnheader", { name: "销方识别号" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "购买方名称" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "价税合计" })).toBeInTheDocument();
  });

  test("renders OA applicant column with compact width styling", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const oaPane = screen.getAllByTestId("pane-oa")[0];
    const applicantHeader = within(oaPane).getByRole("columnheader", { name: "申请人" });

    expect(applicantHeader).toHaveClass("column-applicant-compact");
  });

  test("renders OA text values in a full multiline wrapper without truncation classes", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const projectName = within(pairedGroup).getByText("华东改造项目");
    const applicant = within(pairedGroup).getByText("赵华");

    expect(projectName).toHaveClass("cell-text-value-full");
    expect(applicant).toHaveClass("cell-text-value-full");
    expect(projectName).not.toHaveClass("cell-text-value-project");
  });

  test("renders bank detail and more actions in paired bank rows", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");

    expect(within(pairedGroup).getAllByRole("button", { name: "详情" }).length).toBeGreaterThan(0);
    expect(within(pairedGroup).getAllByRole("button", { name: "更多" }).length).toBeGreaterThan(0);
  });

  test("renders compact two-line datetime values in bank rows", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");

    expect(within(pairedGroup).getAllByText("2026-03-25").length).toBeGreaterThan(0);
    expect(within(pairedGroup).getAllByText("14:22").length).toBeGreaterThan(0);
  });

  test("renders a bank direction tag beside the amount instead of a dedicated direction column", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const directionTag = within(pairedGroup).getAllByText("支出")[0];

    expect(directionTag).toHaveClass("direction-tag");
    expect(directionTag).toHaveClass("direction-tag-outflow");
    expect(within(pairedGroup).queryByText("资金方向")).not.toBeInTheDocument();
  });

  test("renders bank payment account labels across two lines with bank name and tail number", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");

    expect(within(pairedGroup).getByText("招商银行")).toBeInTheDocument();
    expect(within(pairedGroup).getByText("9123")).toBeInTheDocument();
    expect(within(pairedGroup).queryByText("招商银行 9123")).not.toBeInTheDocument();
  });

  test("renders open zone batch action buttons in the zone header instead of row inline workflow buttons", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("陈涛");

    const openGroup = screen.getByTestId("candidate-group-open-case:CASE-202603-101");
    const openZone = screen.getByTestId("zone-open");

    expect(within(openZone).getByRole("button", { name: "确认关联" })).toBeInTheDocument();
    expect(within(openZone).getByRole("button", { name: "异常处理" })).toBeInTheDocument();
    expect(within(openZone).getByRole("button", { name: "清空选择" })).toBeInTheDocument();
    expect(within(openGroup).queryByRole("button", { name: "确认关联" })).not.toBeInTheDocument();
    expect(within(openGroup).queryByRole("button", { name: "标记异常" })).not.toBeInTheDocument();
  });
});
