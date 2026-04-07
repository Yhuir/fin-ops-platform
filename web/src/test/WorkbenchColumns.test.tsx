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
    expect(within(oaPane).queryByRole("columnheader", { name: "申请类型" })).not.toBeInTheDocument();
    expect(within(oaPane).queryByRole("columnheader", { name: "OA和流水关联情况" })).not.toBeInTheDocument();
    expect(within(oaPane).queryByRole("columnheader", { name: "操作" })).not.toBeInTheDocument();

    expect(within(bankPane).getByRole("columnheader", { name: "金额" })).toBeInTheDocument();
    expect(within(bankPane).getByRole("columnheader", { name: "还借款日期" })).toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "借方发生额" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "贷方发生额" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "资金方向" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "支付账户" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "交易时间" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "支付/收款时间" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "和发票OA关联情况" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "操作" })).not.toBeInTheDocument();
    expect(within(bankPane).getAllByRole("columnheader")[0]).toHaveTextContent("对方户名");

    expect(within(invoicePane).getByRole("columnheader", { name: "销方名称/识别号" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "购买方名称/识别号" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "金额/税率/税额" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "价税合计" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "操作" })).toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "发票类型" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "销方识别号" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "购方识别号" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "金额" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "税率" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "税额" })).not.toBeInTheDocument();
  });

  test("renders OA applicant column with compact width styling", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const oaPane = screen.getAllByTestId("pane-oa")[0];
    const applicantHeader = within(oaPane).getByRole("columnheader", { name: "申请人" });

    expect(applicantHeader).toHaveClass("column-applicant-compact");
    expect(applicantHeader).toHaveClass("column-content-centered");
  });

  test("renders OA project metadata row with both application type and OA-bank relation status", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const oaRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-oa"));

    expect(oaRow).toBeDefined();

    const projectName = within(oaRow as HTMLElement).getByText("华东改造项目");
    const applicant = within(oaRow as HTMLElement).getByText("赵华");
    const applicationType = within(oaRow as HTMLElement).getByText("供应商付款申请");
    const relationStatus = within(oaRow as HTMLElement).getByText("完全关联");
    const metadataRow = applicationType.closest(".compound-cell-secondary");

    expect(projectName).toHaveClass("cell-text-value-full");
    expect(applicant).toHaveClass("cell-text-value-full");
    expect(projectName).not.toHaveClass("cell-text-value-project");
    expect(applicationType).toHaveClass("inline-meta-tag");
    expect(relationStatus.closest(".compound-cell-secondary")).not.toBeNull();
    expect(metadataRow).toBe(relationStatus.closest(".compound-cell-secondary"));
  });

  test("renders inline detail actions for OA and bank rows while keeping invoice actions in the action column", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const openGroup = screen.getByTestId("candidate-group-open-case:CASE-202603-101");
    const oaRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-oa"));
    const bankRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-bank"));
    const pairedInvoiceRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-invoice"));
    const openInvoiceRow = within(openGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-invoice"));

    expect(oaRow).toBeDefined();
    expect(bankRow).toBeDefined();
    expect(pairedInvoiceRow).toBeDefined();
    expect(openInvoiceRow).toBeDefined();
    expect(within(oaRow as HTMLElement).getByRole("button", { name: "详情" })).toBeInTheDocument();
    expect(within(bankRow as HTMLElement).getByRole("button", { name: "详情" })).toBeInTheDocument();
    expect(within(bankRow as HTMLElement).queryByRole("button", { name: "更多" })).not.toBeInTheDocument();
    expect(within(pairedInvoiceRow as HTMLElement).getByRole("button", { name: "详情" })).toBeInTheDocument();
    expect(within(openInvoiceRow as HTMLElement).getByRole("button", { name: "详情" })).toBeInTheDocument();
    expect(within(openInvoiceRow as HTMLElement).getByRole("button", { name: "忽略" })).toBeInTheDocument();
  });

  test("renders compact two-line datetime tags in bank rows", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const bankRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-bank"));

    expect(bankRow).toBeDefined();
    expect(within(bankRow as HTMLElement).getByText("2026-03-25")).toBeInTheDocument();
    expect(within(bankRow as HTMLElement).getByText("14:22")).toBeInTheDocument();
  });

  test("renders bank invoice relation status on the same metadata row as the two-line datetime tag", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const bankRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-bank"));

    expect(bankRow).toBeDefined();

    const counterpartyCell = within(bankRow as HTMLElement)
      .getByText("华东设备供应商")
      .closest(".compound-cell-value");
    const relationStatus = within(bankRow as HTMLElement).getByText("完全关联");
    const timeDate = within(bankRow as HTMLElement).getByText("2026-03-25");
    const timeTag = timeDate.closest(".inline-meta-tag-datetime");

    expect(counterpartyCell).not.toBeNull();
    expect(timeTag).not.toBeNull();
    expect(relationStatus.closest(".compound-cell-secondary")).not.toBeNull();
    expect(timeTag?.closest(".compound-cell-secondary")).toBe(relationStatus.closest(".compound-cell-secondary"));
  });

  test("renders a bank direction tag on the second line under the amount instead of a dedicated direction column", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const oaPane = screen.getAllByTestId("pane-oa")[0];
    const bankPane = screen.getAllByTestId("pane-bank")[0];
    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const oaRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-oa"));
    const bankRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-bank"));
    const directionTag = within(pairedGroup).getAllByText("支出")[0];
    const moneyValueRow = directionTag.closest(".money-cell-value");
    const moneyMetaRow = directionTag.closest(".money-cell-meta-row");
    const oaAmountHeader = within(oaPane).getByRole("columnheader", { name: "金额" });
    const bankAmountHeader = within(bankPane).getByRole("columnheader", { name: "金额" });
    const oaAmountCell = within(oaRow as HTMLElement).getByText("128,000.00").closest(".record-card-cell");
    const bankAmountCell = within(bankRow as HTMLElement).getByText("128,000.00").closest(".record-card-cell");

    expect(directionTag).toHaveClass("direction-tag");
    expect(directionTag).toHaveClass("direction-tag-outflow");
    expect(within(pairedGroup).queryByText("资金方向")).not.toBeInTheDocument();
    expect(moneyValueRow).toBeNull();
    expect(moneyMetaRow).not.toBeNull();
    expect(within(bankAmountCell as HTMLElement).getByText("128,000.00")).toBeInTheDocument();
    expect(oaAmountHeader).toHaveClass("column-money-centered");
    expect(bankAmountHeader).toHaveClass("column-money-centered");
    expect(oaAmountCell).toHaveClass("column-money-centered");
    expect(bankAmountCell).toHaveClass("column-money-centered");
  });

  test("renders bank direction and payment account on the same second line under the amount", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");

    const bankName = within(pairedGroup).getByText("招商银行");
    expect(bankName).toBeInTheDocument();
    expect(bankName.closest(".bank-account-tag")).not.toBeNull();
    expect(within(pairedGroup).getByText("9123")).toBeInTheDocument();
    const directionTag = within(pairedGroup).getAllByText("支出")[0];
    const moneyMetaRow = bankName.closest(".money-cell-meta-row");
    expect(moneyMetaRow).not.toBeNull();
    expect(directionTag.closest(".money-cell-meta-row")).toBe(moneyMetaRow);
    expect(within(moneyMetaRow as HTMLElement).getByText("招商银行")).toBeInTheDocument();
  });

  test("renders invoice input or output label before seller tax id instead of a dedicated invoice type column", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const inputLabel = within(pairedGroup).getByText("进");

    expect(inputLabel).toHaveClass("invoice-flow-tag");
    expect(inputLabel).toHaveClass("invoice-flow-tag-input");
    expect(within(pairedGroup).queryByText("发票类型")).not.toBeInTheDocument();
  });

  test("renders invoice amount with tax rate and tax amount on the second line in the same column", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const invoicePane = screen.getAllByTestId("pane-invoice")[0];
    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const amount = within(pairedGroup).getAllByText("128,000.00").find((element) =>
      element.closest(".record-card-invoice"),
    );
    const taxMeta = within(pairedGroup).getByText("13% (16,640.00)");
    const amountHeader = within(invoicePane).getByRole("columnheader", { name: "金额/税率/税额" });
    const grossHeader = within(invoicePane).getByRole("columnheader", { name: "价税合计" });
    const amountCell = amount?.closest(".record-card-cell");
    const grossCell = within(pairedGroup)
      .getByText("144,640.00")
      .closest(".record-card-cell");

    expect(amount).toBeDefined();
    expect(amount?.closest(".compound-cell-value")).not.toBeNull();
    expect(taxMeta.closest(".compound-cell-secondary")).not.toBeNull();
    expect(amountHeader).toHaveClass("column-invoice-amount-compact", "column-money-centered");
    expect(grossHeader).toHaveClass("column-invoice-gross-compact", "column-money-centered");
    expect(amountCell).toHaveClass("column-invoice-amount-compact", "column-money-centered");
    expect(grossCell).toHaveClass("column-invoice-gross-compact", "column-money-centered");
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
