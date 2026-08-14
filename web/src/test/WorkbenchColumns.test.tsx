import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import WorkbenchRecordCard from "../components/workbench/WorkbenchRecordCard";
import { installMockApiFetch } from "./apiMock";
import { renderWorkbenchPage } from "./workbenchRenderHelpers";

describe("Workbench columns and inline actions", () => {
  test("keeps bank amount warning icon interactions from selecting the row", async () => {
    const user = userEvent.setup();
    const onSelectRow = vi.fn();
    const onOpenDetail = vi.fn();

    render(
      <WorkbenchRecordCard
        canMutateData
        columns={[
          { key: "amount", label: "金额", kind: "money", track: "minmax(144px, 144fr)", minWidth: 144 },
        ]}
        onOpenDetail={onOpenDetail}
        onRowAction={() => {}}
        onSelectRow={onSelectRow}
        paneId="bank"
        row={{
          id: "bank-warning-1",
          caseId: "case:bank-warning-1",
          recordType: "bank",
          label: "银行流水",
          status: "已配对",
          statusCode: "paired",
          statusTone: "warning",
          exceptionHandled: false,
          amount: "3,617.41",
          counterparty: "华东设备供应商",
          actionVariant: "detail-only",
          availableActions: ["detail"],
          detailFields: [],
          relationNote: "财务确认差额闭环",
          relationAmountCheck: {
            status: "mismatch",
            direction: "expense",
            bankAmount: "3,617.41",
            oaAmount: "3,425.41",
            amountDelta: "192.00",
            requiresNote: true,
          },
          tableValues: {
            amount: "3,617.41",
            direction: "支出",
            paymentAccount: "招商银行 9123",
            counterparty: "华东设备供应商",
          },
        }}
        rowState="idle"
        showWorkflowActions
        zoneId="paired"
      />,
    );

    const warningButton = screen.getByRole("button", { name: "查看金额不一致差额说明" });
    await user.click(warningButton);

    expect(await screen.findByText("金额不一致")).toBeInTheDocument();
    expect(onSelectRow).not.toHaveBeenCalled();
    expect(onOpenDetail).not.toHaveBeenCalled();
  });

  test("keeps invoice inline detail icon clicks from bubbling into row selection", async () => {
    const user = userEvent.setup();
    const onSelectRow = vi.fn();
    const onOpenDetail = vi.fn();

    render(
      <WorkbenchRecordCard
        canMutateData
        columns={[{ key: "issueDate", label: "发票号码" }]}
        onOpenDetail={onOpenDetail}
        onRowAction={() => {}}
        onSelectRow={onSelectRow}
        paneId="invoice"
        row={{
          id: "invoice-action-1",
          caseId: "case:invoice-action-1",
          recordType: "invoice",
          label: "进项发票",
          status: "待人工核查",
          statusCode: "manual_review",
          statusTone: "danger",
          exceptionHandled: false,
          amount: "49.50",
          counterparty: "弥勒市豪荟酒店",
          actionVariant: "detail-only",
          availableActions: ["detail", "ignore"],
          detailFields: [],
          tableValues: {
            sellerName: "弥勒市豪荟酒店",
            sellerTaxId: "92532526MA6NTMA00H",
            invoiceNo: "26532000000065242711",
            issueDate: "2026-01-14",
            invoiceType: "进项专票",
          },
        }}
        rowState="idle"
        showWorkflowActions
        zoneId="unpaired"
      />,
    );

    await user.click(screen.getByRole("button", { name: "查看发票 26532000000065242711 详情" }));

    expect(onOpenDetail).toHaveBeenCalledTimes(1);
    expect(onSelectRow).not.toHaveBeenCalled();
  });

  test("renders requirement-aligned column headers for OA, bank, and invoice panes", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const oaPanes = screen.getAllByTestId("pane-oa");
    const oaPane = oaPanes[0];
    const bankPane = screen.getAllByTestId("pane-bank")[0];
    const invoicePane = screen.getAllByTestId("pane-invoice")[0];

    expect(within(oaPane).getByRole("columnheader", { name: "申请人" })).toBeInTheDocument();
    expect(within(oaPane).getByRole("columnheader", { name: "项目名称" })).toBeInTheDocument();
    expect(within(oaPane).getByRole("columnheader", { name: "金额" })).toBeInTheDocument();
    expect(within(oaPane).getByRole("columnheader", { name: "对方户名" })).toBeInTheDocument();
    expect(within(oaPane).getByRole("columnheader", { name: "申请事由" })).toBeInTheDocument();
    expect(within(oaPane).queryByRole("columnheader", { name: "申请类型" })).not.toBeInTheDocument();
    expect(within(oaPane).queryByRole("columnheader", { name: "OA和流水关联情况" })).not.toBeInTheDocument();
    oaPanes.forEach((pane) => {
      expect(within(pane).queryByRole("columnheader", { name: "操作" })).not.toBeInTheDocument();
      expect(within(pane).queryByRole("button", { name: "确认关联" })).not.toBeInTheDocument();
      expect(within(pane).queryByRole("button", { name: "异常处理" })).not.toBeInTheDocument();
    });
    expect(within(oaPane).queryByRole("button", { name: "筛选 金额" })).not.toBeInTheDocument();
    expect(within(oaPane).queryByRole("button", { name: "筛选 申请事由" })).not.toBeInTheDocument();

    expect(within(bankPane).getByRole("columnheader", { name: "对方户名" })).toBeInTheDocument();
    expect(within(bankPane).getByRole("columnheader", { name: "金额" })).toBeInTheDocument();
    expect(within(bankPane).queryByRole("columnheader", { name: "还借款日期" })).not.toBeInTheDocument();
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
    expect(within(invoicePane).getByRole("columnheader", { name: "发票号码" })).toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "发票代码/发票号码" })).not.toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "价税合计" })).toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "不含税价格/税率（税额）" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "操作" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "发票类型" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "销方识别号" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "购方识别号" })).not.toBeInTheDocument();
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

  test("renders OA applicant column with an application time tag on the second line", async () => {
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

  test("keeps OA applicant name on the first line and renders only a date chip on the second line", () => {
    render(
      <WorkbenchRecordCard
        canMutateData
        columns={[{ key: "applicant", label: "申请人", track: "minmax(112px, 112fr)", minWidth: 112 }]}
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        paneId="oa"
        row={{
          id: "oa-applicant-date-chip-1",
          recordType: "oa",
          label: "日常报销",
          status: "待处理",
          statusCode: "pending",
          statusTone: "warn",
          exceptionHandled: false,
          amount: "1872.93",
          counterparty: "批量账务集中处理",
          actionVariant: "detail-only",
          availableActions: ["detail"],
          detailFields: [],
          tableValues: {
            applicant: "刘树刚",
            applicationTime: "2026-01-14 14:04:00",
            workflowStatus: "in_progress",
          },
        }}
        rowState="idle"
        showWorkflowActions
        zoneId="unpaired"
      />,
    );

    const applicantLine = screen.getByText("刘树刚").closest(".workbench-oa-applicant-line");
    const dateChip = screen.getByText("2026-01-14").closest(".inline-meta-tag");

    expect(applicantLine).not.toBeNull();
    expect(dateChip).not.toBeNull();
    expect(within(applicantLine as HTMLElement).queryByText("2026-01-14")).not.toBeInTheDocument();
    expect(dateChip).toHaveClass("inline-meta-tag-muted");
    expect(dateChip?.closest(".compound-cell-secondary")).not.toBeNull();
    expect(screen.getByText("14:04:00").closest(".inline-meta-tag")).toBe(dateChip);
    expect(screen.getByLabelText("OA流程状态：进行中")).toBeInTheDocument();
  });

  test("shows an explicit missing-time chip when an OA has no authoritative application time", () => {
    render(
      <WorkbenchRecordCard
        canMutateData
        columns={[{ key: "applicant", label: "申请人", track: "minmax(112px, 112fr)", minWidth: 112 }]}
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        paneId="oa"
        row={{
          id: "oa-applicant-missing-time-1",
          recordType: "oa",
          label: "支付申请",
          status: "待处理",
          statusCode: "pending",
          statusTone: "warn",
          exceptionHandled: false,
          amount: "900.00",
          counterparty: "云南省建筑技工学校",
          actionVariant: "detail-only",
          availableActions: ["detail"],
          detailFields: [],
          tableValues: {
            applicant: "樊祖芳",
            applicationTime: "--",
            workflowStatus: "in_progress",
          },
        }}
        rowState="idle"
        showWorkflowActions
        zoneId="unpaired"
      />,
    );

    expect(screen.getByText("时间缺失").closest(".inline-meta-tag")).toHaveClass("inline-meta-tag-muted");
  });

  test("moves the OA type to the applicant cell and keeps the project cell free of workflow chips", async () => {
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
    const metadataRow = applicationType.closest(".compound-cell-secondary");

    expect(projectName).toHaveClass("cell-text-value-full");
    expect(applicant).toHaveClass("cell-text-value-full");
    expect(projectName).not.toHaveClass("cell-text-value-project");
    expect(applicationType.closest(".finance-status-tag")).not.toBeNull();
    expect(metadataRow?.closest(".record-card-cell")).toContainElement(applicant);
    expect(within(oaRow as HTMLElement).queryByText("完全关联")).not.toBeInTheDocument();
  });

  test("does not render process or evidence tags in the OA project cell", () => {
    render(
      <WorkbenchRecordCard
        canMutateData
        columns={[{ key: "projectName", label: "项目名称", track: "minmax(192px, 192fr)", minWidth: 192 }]}
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        paneId="oa"
        row={{
          id: "oa-etc-tags-1",
          recordType: "oa",
          label: "日常报销",
          status: "完全关联",
          statusCode: "linked",
          statusTone: "success",
          exceptionHandled: false,
          amount: "1872.93",
          counterparty: "批量账务集中处理",
          actionVariant: "detail-only",
          availableActions: ["detail"],
          detailFields: [],
          tags: ["ETC 发票已关联", "ETC 批次", "ETC 批次批量提交", "多明细"],
          tableValues: {
            projectName: "云南溯源科技",
            applicationType: "日常报销",
            reconciliationStatus: "完全关联",
          },
        }}
        rowState="idle"
        showWorkflowActions
        zoneId="paired"
      />,
    );

    expect(screen.getByText("云南溯源科技")).toHaveClass("cell-text-value-full");
    expect(screen.queryByText("ETC")).not.toBeInTheDocument();
    expect(screen.queryByText("ETC 发票已关联")).not.toBeInTheDocument();
    expect(screen.queryByText("ETC 批次")).not.toBeInTheDocument();
    expect(screen.queryByText("ETC 批次批量提交")).not.toBeInTheDocument();
    expect(screen.queryByText("多明细")).not.toBeInTheDocument();
  });

  test("keeps OA evidence and relation tags out of the project cell", () => {
    render(
      <WorkbenchRecordCard
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

    const applicationType = screen.getByText("日常报销");

    expect(applicationType.closest(".finance-status-tag")).not.toBeNull();
    expect(screen.queryByText("冲")).not.toBeInTheDocument();
    expect(screen.queryByText("待找流水与发票")).not.toBeInTheDocument();
  });

  test("renders inline detail actions while keeping other row actions in the compact menu", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const unpairedInvoiceGroup = screen.getByTestId("candidate-group-unpaired-row:iv-o-202603-001");
    const oaRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-oa"));
    const bankRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-bank"));
    const pairedInvoiceRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-invoice"));
    const openInvoiceRow = within(unpairedInvoiceGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-invoice"));

    expect(oaRow).toBeDefined();
    expect(bankRow).toBeDefined();
    expect(pairedInvoiceRow).toBeDefined();
    expect(openInvoiceRow).toBeDefined();
    expect(within(oaRow as HTMLElement).getByRole("button", { name: "查看OA 赵华 详情" })).toHaveClass("row-action-btn-icon");
    expect(within(bankRow as HTMLElement).getByRole("button", { name: /查看银行流水 .* 详情/ })).toBeInTheDocument();
    expect(within(bankRow as HTMLElement).getByRole("button", { name: "更多操作" })).toBeInTheDocument();
    expect(within(bankRow as HTMLElement).queryByRole("button", { name: "详情" })).not.toBeInTheDocument();
    expect(within(pairedInvoiceRow as HTMLElement).getByRole("button", { name: /查看发票 .* 详情/ })).toBeInTheDocument();
    expect(within(openInvoiceRow as HTMLElement).getByRole("button", { name: /查看发票 .* 详情/ })).toBeInTheDocument();
    const openInvoiceActions = within(openInvoiceRow as HTMLElement).getByRole("button", { name: "更多操作" });
    await user.click(openInvoiceActions);
    expect(screen.getByRole("menuitem", { name: "忽略" })).toBeInTheDocument();
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

  test("removes internal transfer relation status from bank counterparty metadata while keeping inline detail available", () => {
    render(
      <WorkbenchRecordCard
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

    expect(screen.getByRole("button", { name: /查看银行流水 .* 详情/ })).toBeInTheDocument();
    expect(screen.queryByText("已匹配：")).not.toBeInTheDocument();
    expect(screen.queryByText("内部往来款")).not.toBeInTheDocument();
    expect(screen.getByText("2026-03-20")).toBeInTheDocument();
  });

  test("removes salary relation status while retaining bank transaction time", () => {
    render(
      <WorkbenchRecordCard
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

    expect(screen.queryByText("已匹配：")).not.toBeInTheDocument();
    expect(screen.getByText("2026-03-20").closest(".compound-cell-secondary")).not.toBeNull();
  });

  test("removes bank invoice relation status from counterparty metadata", async () => {
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
    const timeDate = within(bankRow as HTMLElement).getByText("2026-03-25");
    const timeTag = timeDate.closest(".inline-meta-tag-datetime");

    expect(counterpartyCell).not.toBeNull();
    expect(timeTag).not.toBeNull();
    expect(within(bankRow as HTMLElement).queryByText("完全关联")).not.toBeInTheDocument();
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
    const bankAmountCell = within(bankRow as HTMLElement).getByText("128000.00").closest(".record-card-cell");

    expect(directionTag).toHaveClass("direction-tag");
    expect(directionTag).toHaveClass("direction-tag-outflow");
    expect(within(pairedGroup).queryByText("资金方向")).not.toBeInTheDocument();
    expect(moneyValueRow).toBeNull();
    expect(moneyMetaRow).not.toBeNull();
    expect(within(bankAmountCell as HTMLElement).getByText("128000.00")).toBeInTheDocument();
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

  test("renders the bank detail category tag on a dedicated third line under the amount", () => {
    render(
      <WorkbenchRecordCard
        canMutateData
        columns={[
          { key: "amount", label: "金额", kind: "money", track: "minmax(144px, 144fr)", minWidth: 144 },
        ]}
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        paneId="bank"
        row={{
          id: "bank-category-amount-1",
          caseId: "case:bank-category-amount-1",
          recordType: "bank",
          label: "银行流水",
          status: "待人工核查",
          statusCode: "manual_review",
          statusTone: "danger",
          exceptionHandled: false,
          amount: "200,000.00",
          counterparty: "梁希涛",
          actionVariant: "detail-only",
          availableActions: ["detail"],
          detailFields: [],
          categoryLabel: "待还款",
          categoryLabelPath: ["借入", "公司往来款", "待还款"],
          categoryResolutionStatus: "manual_confirmed",
          categoryPath: ["借入", "公司往来款", "待还款"],
          tableValues: {
            counterparty: "梁希涛",
            transactionTime: "2026-03-05 09:34:42",
            invoiceRelationStatus: "候选未闭环",
            amount: "200,000.00",
            direction: "支出",
            paymentAccount: "建设银行 8106",
            note: "还暂借款",
            repaymentDate: "--",
          },
        }}
        rowState="idle"
        showWorkflowActions
        zoneId="unpaired"
      />,
    );

    const categoryTag = screen.getByText("借入 / 公司往来款 / 待还款");
    const accountTag = screen.getByText("8106").closest(".bank-account-tag");
    const categoryRow = categoryTag.closest(".money-cell-category-row");
    const metadataRow = accountTag?.closest(".money-cell-meta-row");

    expect(categoryTag.closest('[data-slot="chip"]')).toHaveClass("workbench-bank-category-chip");
    expect(categoryTag.closest('[data-slot="chip"]')).toHaveAttribute(
      "aria-label",
      "流水分类：借入 / 公司往来款 / 待还款",
    );
    expect(categoryRow).not.toBeNull();
    expect(metadataRow).not.toBeNull();
    expect(categoryTag.closest(".money-cell-meta-row")).toBeNull();
    expect(within(metadataRow as HTMLElement).getByText("建行")).toBeInTheDocument();
    expect(within(metadataRow as HTMLElement).getByText("支出")).toHaveClass("direction-tag");
  });

  test.each([
    ["unmatched", "待分类"],
    ["needs_confirmation", "待确认"],
  ] as const)("renders %s bank category resolution as %s", (categoryResolutionStatus, label) => {
    render(
      <WorkbenchRecordCard
        canMutateData
        columns={[{ key: "amount", label: "金额", kind: "money", track: "minmax(144px, 144fr)", minWidth: 144 }]}
        onOpenDetail={() => {}}
        onRowAction={() => {}}
        onSelectRow={() => {}}
        paneId="bank"
        row={{
          id: `bank-${categoryResolutionStatus}`,
          recordType: "bank",
          label: "银行流水",
          status: "完全关联",
          statusCode: "fully_linked",
          statusTone: "success",
          exceptionHandled: false,
          amount: "100.00",
          counterparty: "测试公司",
          actionVariant: "detail-only",
          availableActions: ["detail"],
          detailFields: [],
          categoryResolutionStatus,
          tableValues: {
            amount: "100.00",
            direction: "支出",
            paymentAccount: "建设银行 8106",
            counterparty: "测试公司",
            transactionTime: "2026-08-03 10:00:00",
            invoiceRelationStatus: "完全关联",
          },
        }}
        rowState="idle"
        showWorkflowActions
        zoneId="paired"
      />,
    );

    expect(screen.getByText(label).closest('[data-slot="chip"]')).toHaveClass("workbench-bank-category-chip");
    expect(screen.queryByText("完全关联")).not.toBeInTheDocument();
  });

  test("renders short bank names in bank row amount account tags", () => {
    render(
      <WorkbenchRecordCard
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
        zoneId="unpaired"
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

  test("renders invoice source tags under the direction tag line", () => {
    const createInvoiceRow = (id: string, sourceKind?: string) => ({
      id,
      caseId: `case:${id}`,
      recordType: "invoice" as const,
      sourceKind,
      label: "进项发票",
      status: "待人工核查",
      statusCode: "manual_review",
      statusTone: "danger",
      exceptionHandled: false,
      amount: "49.50",
      counterparty: "弥勒市豪荟酒店",
      actionVariant: "detail-only" as const,
      availableActions: ["detail"],
      detailFields: [],
      tableValues: {
        sellerName: id === "inv-oa-source" ? "OA附件销方" : "人工导入销方",
        sellerTaxId: "92532526MA6NTMA00H",
        invoiceType: "进项专票",
      },
    });

    render(
      <div>
        <WorkbenchRecordCard
          canMutateData
          columns={[{ key: "sellerName", label: "销方名称/识别号" }]}
          onOpenDetail={() => {}}
          onRowAction={() => {}}
          onSelectRow={() => {}}
          paneId="invoice"
          row={createInvoiceRow("inv-oa-source", "oa_attachment_invoice")}
          rowState="idle"
          showWorkflowActions
          zoneId="unpaired"
        />
        <WorkbenchRecordCard
          canMutateData
          columns={[{ key: "sellerName", label: "销方名称/识别号" }]}
          onOpenDetail={() => {}}
          onRowAction={() => {}}
          onSelectRow={() => {}}
          paneId="invoice"
          row={createInvoiceRow("inv-manual-source")}
          rowState="idle"
          showWorkflowActions
          zoneId="unpaired"
        />
      </div>,
    );

    const oaRow = screen.getByRole("row", { name: /OA附件销方/ });
    const manualRow = screen.getByRole("row", { name: /人工导入销方/ });
    const oaSourceTag = within(oaRow).getByText("OA附件");
    const manualSourceTag = within(manualRow).getByText("人工导入");

    expect(oaSourceTag).toHaveClass("inline-meta-tag");
    expect(manualSourceTag).toHaveClass("inline-meta-tag");
    const oaChipRow = within(oaRow).getByText("进").closest(".invoice-chip-row");
    const manualChipRow = within(manualRow).getByText("进").closest(".invoice-chip-row");

    expect(oaChipRow).not.toBeNull();
    expect(manualChipRow).not.toBeNull();
    expect(oaSourceTag.closest(".invoice-chip-row")).toBe(oaChipRow);
    expect(manualSourceTag.closest(".invoice-chip-row")).toBe(manualChipRow);
  });

  test("renders invoice number and issue date tag without the issue date filter menu", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const invoicePane = screen.getAllByTestId("pane-invoice")[0];
    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const invoiceRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-invoice"));

    expect(invoiceRow).toBeDefined();
    expect(within(invoicePane).getByRole("columnheader", { name: "发票号码" })).toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "发票代码/发票号码" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("button", { name: "筛选 发票号码" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("button", { name: "筛选 开票日期" })).not.toBeInTheDocument();

    const identityCell = within(invoiceRow as HTMLElement).getByText("00061345").closest(".invoice-identity-value");
    expect(identityCell).not.toBeNull();
    expect(within(identityCell as HTMLElement).queryByText("032002600111 /")).not.toBeInTheDocument();
    const issueDateTag = within(identityCell as HTMLElement).getByText("2026-03-25").closest(".inline-meta-tag");
    expect(issueDateTag).toHaveClass("invoice-issue-date-tag");
  });

  test("renders invoice merged amount summary without adding filter menus to it", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("赵华");

    const invoicePane = screen.getAllByTestId("pane-invoice")[0];
    const pairedGroup = screen.getByTestId("candidate-group-paired-case:CASE-202603-001");
    const invoiceRow = within(pairedGroup)
      .getAllByRole("row")
      .find((row) => row.classList.contains("record-card-invoice"));

    expect(invoiceRow).toBeDefined();
    expect(within(invoicePane).getByRole("columnheader", { name: "价税合计" })).toBeInTheDocument();
    expect(within(invoicePane).getByRole("columnheader", { name: "发票号码" })).toBeInTheDocument();
    expect(within(invoicePane).queryByRole("columnheader", { name: "不含税价格/税率（税额）" })).not.toBeInTheDocument();
    expect(within(invoicePane).queryByRole("button", { name: "筛选 价税合计" })).not.toBeInTheDocument();
    expect(within(invoiceRow as HTMLElement).getByText("2026-03-25")).toBeInTheDocument();
    expect(within(invoiceRow as HTMLElement).getByText("144640.00")).toBeInTheDocument();
    expect(within(invoiceRow as HTMLElement).getByText("128000.00 13% (16640.00)")).toBeInTheDocument();
  });

  test("renders invoice gross amount column with net amount and tax meta on the second line", () => {
    render(
      <WorkbenchRecordCard
        canMutateData
        columns={[{ key: "grossAmount", label: "价税合计" }]}
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
        zoneId="unpaired"
      />,
    );

    expect(screen.getByText("49.50 1% (0.50)")).toBeInTheDocument();
    expect(screen.getByText("50.00")).toBeInTheDocument();
  });

  test("renders unpaired zone batch action buttons in the zone header instead of row inline workflow buttons", async () => {
    installMockApiFetch();
    renderWorkbenchPage();
    await screen.findByText("陈涛");

    const unpairedGroup = screen.getByTestId("candidate-group-unpaired-row:oa-o-202603-001");
    const unpairedZone = screen.getByTestId("zone-unpaired");

    expect(within(unpairedZone).getByRole("button", { name: "确认关联" })).toBeInTheDocument();
    expect(within(unpairedZone).getByRole("button", { name: "撤回关联" })).toBeInTheDocument();
    expect(within(unpairedZone).getByRole("button", { name: "清空选择" })).toBeInTheDocument();
    expect(within(unpairedGroup).queryByRole("button", { name: "确认关联" })).not.toBeInTheDocument();
    expect(within(unpairedGroup).queryByRole("button", { name: "标记异常" })).not.toBeInTheDocument();
  });
});
