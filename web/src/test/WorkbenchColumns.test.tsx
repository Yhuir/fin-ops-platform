import { render, screen, within } from "@testing-library/react";

import WorkbenchRecordCard from "../components/workbench/WorkbenchRecordCard";
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
    expect(within(oaPane).getByRole("columnheader", { name: "金额" })).toBeInTheDocument();
    expect(within(oaPane).getByRole("columnheader", { name: "对方户名" })).toBeInTheDocument();
    expect(within(oaPane).getByRole("columnheader", { name: "申请事由" })).toBeInTheDocument();
    expect(within(oaPane).queryByRole("columnheader", { name: "申请类型" })).not.toBeInTheDocument();
    expect(within(oaPane).queryByRole("columnheader", { name: "OA和流水关联情况" })).not.toBeInTheDocument();
    expect(within(oaPane).queryByRole("columnheader", { name: "操作" })).not.toBeInTheDocument();
    expect(within(oaPane).queryByRole("button", { name: "筛选 金额" })).not.toBeInTheDocument();
    expect(within(oaPane).queryByRole("button", { name: "筛选 申请事由" })).not.toBeInTheDocument();

    expect(within(bankPane).getByRole("columnheader", { name: "对方户名" })).toBeInTheDocument();
    expect(within(bankPane).getByRole("columnheader", { name: "金额" })).toBeInTheDocument();
    expect(within(bankPane).getByRole("columnheader", { name: "还借款日期" })).toBeInTheDocument();
    expect(within(bankPane).getByRole("columnheader", { name: "备注" })).toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "借方发生额" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "贷方发生额" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "资金方向" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "支付账户" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "交易时间" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "支付/收款时间" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "和发票OA关联情况" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "操作" })).not.toBeInTheDocument();
    expect(within(bankPane).queryByRole("button", { name: "筛选 备注" })).not.toBeInTheDocument();
    expect(within(bankPane).getAllByRole("columnheader")[0]).toHaveTextContent("对方户名");

    expect(within(invoicePane).getByRole("columnheader", { name: "销方名称/识别号" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "购方名称/识别号" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "发票代码/发票号码" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "不含税价格/税率（税额）" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "价税合计" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "操作" })).toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "发票类型" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "销方识别号" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "购方识别号" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("button", { name: "筛选 不含税价格/税率（税额）" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("button", { name: "筛选 价税合计" })).not.toBeInTheDocument();
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

  test("renders pane column headers in saved layout order from settings", async () => {
    installMockApiFetch({
      workbenchColumnLayouts: {
        oa: ["projectName", "applicant", "counterparty", "amount", "reason"],
      },
    });
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const oaPane = screen.getAllByTestId("pane-oa")[0];
    const headerNames = within(oaPane)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.replace(/\s+/g, "") ?? "");

    expect(headerNames.slice(0, 5)).toEqual(["项目名称", "申请人", "对方户名", "金额", "申请事由"]);
  });

  test("renders OA applicant column with an approval time tag on the second line", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const oaRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-oa"));

    expect(oaRow).toBeDefined();
    expect(within(oaRow as HTMLElement).getByText("2026-03-25")).toBeInTheDocument();
    expect(within(oaRow as HTMLElement).getByText("11:05")).toBeInTheDocument();
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

  test("renders OA invoice offset tag next to application type and pending status", () => {
    render(
      <WorkbenchRecordCard
        actionMode="default"
        canMutateData
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        paneId="oa"
        row={{
          id: "oa-offset-1",
          caseId: "case:offset-1",
          recordType: "oa",
          label: "日常报销",
          status: "待找流水与发票",
          statusCode: "oa_invoice_offset_auto_match",
          statusTone: "warn",
          exceptionHandled: false,
          amount: "200.00",
          counterparty: "云南中油严家山交通服务有限公司",
          actionVariant: "detail-only",
          availableActions: ["detail"],
          detailFields: [],
          tags: ["冲"],
          tableValues: {
            applicant: "周洁莹",
            applicationTime: "2026-02-09",
            projectName: "云南溯源科技",
            applicationType: "日常报销",
            reconciliationStatus: "待找流水与发票",
            amount: "200.00",
            counterparty: "云南中油严家山交通服务有限公司",
            reason: "汽油费",
          },
        }}
        rowState="idle"
        showWorkflowActions
        zoneId="paired"
      />,
    );

    const offsetTag = screen.getByText("冲");
    const applicationType = screen.getByText("日常报销");
    const pendingStatus = screen.getByText("待找流水与发票");

    expect(offsetTag).toHaveClass("inline-meta-tag");
    expect(offsetTag.closest(".compound-cell-secondary")).toBe(applicationType.closest(".compound-cell-secondary"));
    expect(offsetTag.closest(".compound-cell-secondary")).toBe(pendingStatus.closest(".compound-cell-secondary"));
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

  test("renders internal transfer matched status in bank counterparty metadata while keeping inline detail available", () => {
    render(
      <WorkbenchRecordCard
        actionMode="default"
        canMutateData
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        paneId="bank"
        row={{
          id: "bank-internal-transfer-1",
          caseId: "case:internal-transfer-1",
          recordType: "bank",
          label: "银行流水",
          status: "已配对",
          statusCode: "paired",
          statusTone: "success",
          exceptionHandled: false,
          amount: "9.00",
          counterparty: "云南溯源科技有限公司",
          actionVariant: "detail-only",
          availableActions: ["detail"],
          detailFields: [],
          tableValues: {
            counterparty: "云南溯源科技有限公司",
            transactionTime: "2026-03-20 16:05:40",
            invoiceRelationStatus: "已匹配：内部往来款",
            amount: "9.00",
            direction: "支出",
            paymentAccount: "民生 9486",
            repaymentDate: "--",
          },
        }}
        rowState="idle"
        showWorkflowActions
        zoneId="paired"
      />,
    );

    expect(screen.getByRole("button", { name: "详情" })).toBeInTheDocument();
    expect(screen.getByText("已匹配：")).toBeInTheDocument();
    expect(screen.getByText("内部往来款")).toBeInTheDocument();
  });

  test("renders salary auto-match status as a two-line matched tag on the same metadata row as time", () => {
    render(
      <WorkbenchRecordCard
        actionMode="default"
        canMutateData
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        paneId="bank"
        row={{
          id: "bank-salary-1",
          caseId: "case:salary-1",
          recordType: "bank",
          label: "银行流水",
          status: "已配对",
          statusCode: "paired",
          statusTone: "success",
          exceptionHandled: false,
          amount: "6,000.00",
          counterparty: "张三",
          actionVariant: "detail-only",
          availableActions: ["detail"],
          detailFields: [],
          tableValues: {
            counterparty: "张三",
            transactionTime: "2026-03-20 16:05:40",
            invoiceRelationStatus: "已匹配：工资",
            amount: "6,000.00",
            direction: "支出",
            paymentAccount: "建行 8106",
            note: "工资",
            repaymentDate: "--",
          },
        }}
        rowState="idle"
        showWorkflowActions
        zoneId="paired"
      />,
    );

    const statusTag = screen.getByText("已匹配：").closest(".status-tag");
    expect(statusTag).not.toBeNull();
    expect(within(statusTag as HTMLElement).getByText("工资")).toBeInTheDocument();
    const metadataRow = statusTag?.closest(".compound-cell-secondary");
    expect(metadataRow).not.toBeNull();
    expect(screen.getByText("2026-03-20").closest(".compound-cell-secondary")).toBe(metadataRow);
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

    const bankPane = screen.getAllByTestId("pane-bank")[0];
    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const bankRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-bank"));
    const directionTag = within(pairedGroup).getAllByText("支出")[0];
    const moneyValueRow = directionTag.closest(".money-cell-value");
    const moneyMetaRow = directionTag.closest(".money-cell-meta-row");
    const bankAmountHeader = within(bankPane).getByRole("columnheader", { name: "金额" });
    const bankAmountCell = within(bankRow as HTMLElement).getByText("128,000.00").closest(".record-card-cell");

    expect(directionTag).toHaveClass("direction-tag");
    expect(directionTag).toHaveClass("direction-tag-outflow");
    expect(within(pairedGroup).queryByText("资金方向")).not.toBeInTheDocument();
    expect(moneyValueRow).toBeNull();
    expect(moneyMetaRow).not.toBeNull();
    expect(within(bankAmountCell as HTMLElement).getByText("128,000.00")).toBeInTheDocument();
    expect(bankAmountHeader).toHaveClass("column-money-centered");
    expect(bankAmountCell).toHaveClass("column-money-centered");
  });

  test("renders bank direction and payment account on the same second line under the amount", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");

    const bankName = within(pairedGroup).getByText("招行");
    expect(bankName).toBeInTheDocument();
    expect(bankName.closest(".bank-account-tag")).not.toBeNull();
    expect(within(pairedGroup).getByText("9123")).toBeInTheDocument();
    const directionTag = within(pairedGroup).getAllByText("支出")[0];
    const moneyMetaRow = bankName.closest(".money-cell-meta-row");
    expect(moneyMetaRow).not.toBeNull();
    expect(directionTag.closest(".money-cell-meta-row")).toBe(moneyMetaRow);
    expect(within(moneyMetaRow as HTMLElement).getByText("招行")).toBeInTheDocument();
  });

  test("renders short bank names in bank row amount account tags", () => {
    render(
      <WorkbenchRecordCard
        actionMode="default"
        canMutateData
        columns={[
          { key: "amount", label: "金额", kind: "money", track: "minmax(144px, 144fr)", minWidth: 144 },
        ]}
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        paneId="bank"
        row={{
          id: "bank-short-account-1",
          caseId: "case:bank-short-account-1",
          recordType: "bank",
          label: "银行流水",
          status: "待人工核查",
          statusCode: "manual_review",
          statusTone: "danger",
          exceptionHandled: false,
          amount: "9,370.53",
          counterparty: "待报解预算收入",
          actionVariant: "detail-only",
          availableActions: ["detail"],
          detailFields: [],
          tableValues: {
            counterparty: "待报解预算收入",
            transactionTime: "2026-04-16 11:27:30",
            invoiceRelationStatus: "待人工核查",
            amount: "9,370.53",
            direction: "支出",
            paymentAccount: "工商银行 6386",
            note: "18985283",
            repaymentDate: "--",
          },
        }}
        rowState="idle"
        showWorkflowActions
        zoneId="open"
      />,
    );

    const accountTag = screen.getByText("6386").closest(".bank-account-tag");
    expect(accountTag).not.toBeNull();
    expect(within(accountTag as HTMLElement).getByText("工行")).toBeInTheDocument();
    expect(within(accountTag as HTMLElement).queryByText("工商银行")).not.toBeInTheDocument();
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

  test("renders invoice code number and issue date tag without the issue date filter menu", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const invoicePane = screen.getAllByTestId("pane-invoice")[0];
    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const invoiceRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-invoice"));

    expect(invoiceRow).toBeDefined();
    expect(within(invoicePane).getByRole("columnheader", { name: "发票代码/发票号码" })).toBeInTheDocument();
    expect(within(invoicePane).queryByRole("button", { name: "筛选 发票代码/发票号码" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("button", { name: "筛选 开票日期" })).not.toBeInTheDocument();

    const identityCell = within(invoiceRow as HTMLElement).getByText("032002600111 /").closest(".invoice-identity-value");
    expect(identityCell).not.toBeNull();
    expect(within(identityCell as HTMLElement).getByText("00061345")).toBeInTheDocument();
    const issueDateTag = within(identityCell as HTMLElement).getByText("2026-03-25").closest(".inline-meta-tag");
    expect(issueDateTag).toHaveClass("invoice-issue-date-tag");
  });

  test("restores invoice amount summary columns without adding filter menus to them", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const invoicePane = screen.getAllByTestId("pane-invoice")[0];
    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const invoiceRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-invoice"));

    expect(invoiceRow).toBeDefined();
    expect(within(invoicePane).getByRole("columnheader", { name: "不含税价格/税率（税额）" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "价税合计" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "发票代码/发票号码" })).toBeInTheDocument();
    expect(within(invoicePane).queryByRole("button", { name: "筛选 不含税价格/税率（税额）" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("button", { name: "筛选 价税合计" })).not.toBeInTheDocument();
    expect(within(invoiceRow as HTMLElement).getByText("2026-03-25")).toBeInTheDocument();
    expect(within(invoiceRow as HTMLElement).getByText("128,000.00")).toBeInTheDocument();
    expect(within(invoiceRow as HTMLElement).getByText("144,640.00")).toBeInTheDocument();
  });

  test("renders invoice amount column as net amount with tax meta on the second line", () => {
    render(
      <WorkbenchRecordCard
        actionMode="default"
        canMutateData
        columns={[
          { key: "amount", label: "不含税价格/税率（税额）" },
          { key: "grossAmount", label: "价税合计" },
        ]}
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        paneId="invoice"
        row={{
          id: "inv-net-amount-001",
          caseId: "case:inv-net-amount-001",
          recordType: "invoice",
          label: "进项发票",
          status: "待人工核查",
          statusCode: "manual_review",
          statusTone: "danger",
          exceptionHandled: false,
          amount: "49.50",
          counterparty: "弥勒市豪荟酒店",
          actionVariant: "detail-only",
          availableActions: ["detail"],
          detailFields: [],
          tableValues: {
            sellerName: "弥勒市豪荟酒店",
            sellerTaxId: "92532526MA6NTMA00H",
            buyerName: "云南溯源科技有限公司",
            buyerTaxId: "915300007194052520",
            invoiceCode: "—",
            invoiceNo: "26532000000065242711",
            issueDate: "2026-01-14",
            amount: "49.50",
            taxRate: "1%",
            taxAmount: "0.50",
            grossAmount: "50.00",
          },
        }}
        rowState="idle"
        showWorkflowActions
        zoneId="open"
      />,
    );

    expect(screen.getByText("49.50")).toBeInTheDocument();
    expect(screen.getByText("1% (0.50)")).toBeInTheDocument();
    expect(screen.getByText("50.00")).toBeInTheDocument();
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
