import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";
import * as etcApi from "../features/etc/api";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ETC ticket management page", () => {
  test("refreshes batch list when ETC import background job completes", async () => {
    const fetchMock = installMockApiFetch({
      backgroundJobs: [
        {
          job_id: "job_etc_import_0001",
          type: "etc_invoice_import",
          label: "导入 ETC发票",
          short_label: "导入 ETC发票完成 4/4",
          status: "succeeded",
          phase: "complete",
          current: 4,
          total: 4,
          percent: 100,
          message: "ETC发票导入完成。",
          result_summary: { created: 1, imported: 1, updated: 1, attachments_completed: 1, duplicates: 1, failed: 1, total: 4 },
          error: null,
          created_at: "2026-05-03T10:00:00+00:00",
          updated_at: "2026-05-03T10:00:04+00:00",
          finished_at: "2026-05-03T10:00:04+00:00",
        },
      ],
    });
    renderAppAt("/etc-tickets");

    await screen.findByTestId("etc-ticket-management-page");

    await waitFor(() => {
      const batchListCalls = fetchMock.mock.calls.filter(([url]) => String(url).startsWith("/api/etc/batches?"));
      expect(batchListCalls.length).toBeGreaterThanOrEqual(2);
    });
  });

  test("unsubmitted mode shows batch list and whole-batch OA submit action", async () => {
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(within(page).getByRole("heading", { name: "ETC票据管理" })).toBeInTheDocument();
    expect(await within(page).findByRole("button", { name: "未提交 2" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "已提交 1" })).toBeInTheDocument();
    expect(within(page).getByRole("list", { name: "ETC批次列表" })).toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toHaveTextContent("ETC-2026-03-A");
    expect(within(page).getByRole("button", { name: "提交OA支付申请" })).toBeEnabled();
    expect(within(page).getAllByText("ETC-2026-03-A").length).toBeGreaterThanOrEqual(1);
    expect(await within(page).findByText("ETC-2026-001")).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/batches?status=unsubmitted&page=1&page_size=100",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith("/api/etc/invoices?"))).toBe(false);
  });

  test("deletes an unsubmitted ETC batch through confirmation and refreshes the list", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const row = await within(page).findByTestId("etc-batch-row-etc-batch-unsubmitted-01");
    await user.click(within(row).getByRole("button", { name: "删除ETC批次 ETC-2026-03-A" }));

    const dialog = await screen.findByRole("dialog", { name: "删除ETC批次" });
    expect(dialog).toHaveTextContent("ETC-2026-03-A");
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/batches/etc-batch-unsubmitted-01",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
    expect(await within(page).findByRole("button", { name: "未提交 1" })).toBeInTheDocument();
    expect(within(page).queryByTestId("etc-batch-row-etc-batch-unsubmitted-01")).not.toBeInTheDocument();
  });

  test("deletes a mutable reconciliation task with expected version without selecting the row", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const row = await within(page).findByTestId("etc-reconciliation-task-row-etc-recon-task-001");
    await user.click(within(row).getByRole("button", { name: "删除对账任务 2026-02 ETC 对账" }));

    const dialog = await screen.findByRole("dialog", { name: "删除对账任务" });
    expect(dialog).toHaveTextContent("2026-02 ETC 对账");
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/reconciliation-tasks/etc-recon-task-001",
        expect.objectContaining({
          method: "DELETE",
          body: JSON.stringify({ expectedVersion: 3 }),
        }),
      );
    });
    expect(within(page).queryByTestId("etc-reconciliation-task-row-etc-recon-task-001")).not.toBeInTheDocument();
  });

  test("shows the reconciliation workspace with upload blocks, statuses, supplements, and parse issues", async () => {
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("button", { name: "新建批次" })).toBeInTheDocument();
    expect(within(page).getByTestId("etc-reconciliation-task-row-etc-recon-task-001")).toHaveTextContent("2.27-2.28");
    expect(within(page).getByTestId("etc-reconciliation-task-row-etc-recon-task-001")).toHaveTextContent("ETC票 2 + 补充凭证 1");

    expect(within(page).getByRole("button", { name: "票根网 PDF/JPG" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "信用卡账单 PDF" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "补充凭证" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "补ETC发票" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "确认对账" })).toBeDisabled();

    expect(within(page).getByText("信用卡侧")).toBeInTheDocument();
    expect(within(page).getByText("票根/补充凭证侧")).toBeInTheDocument();
    expect(within(page).getByRole("region", { name: "人工核对处理" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "接受推荐票根" })).toBeDisabled();
    expect(within(page).getByRole("button", { name: "关联所选记录" })).toBeDisabled();
    expect(within(page).getByText("ETC补充凭证")).toBeInTheDocument();
    expect(within(page).getByText(/票根网缺少车牌号/)).toBeInTheDocument();

    expect(within(page).getByRole("region", { name: "ETC批次详情" })).toBeInTheDocument();
  });

  test("shows source file context, deletes a mutable source file, and fresh tasks do not inherit old issues", async () => {
    const user = userEvent.setup();
    installMockApiFetch();

    const taskWithSourceFiles = {
      taskId: "etc-recon-task-source-001",
      status: "reviewing",
      version: 3,
      title: "2026-04 ETC 对账",
      periodStart: "2026-04-01",
      periodEnd: "2026-04-30",
      statementPeriodStart: "2026-04-01",
      statementPeriodEnd: "2026-04-30",
      oaTotalAmount: "80.00",
      etcInvoiceAmount: "50.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [
        {
          fileId: "file-ticket-ok",
          sourceKind: "ticket_root",
          originalName: "票根网-成功.pdf",
          hasBlockingIssue: false,
        },
        {
          fileId: "file-ticket-bad",
          sourceKind: "ticket_root",
          originalName: "票根网-失败.pdf",
          hasBlockingIssue: true,
        },
      ],
      parseIssues: [
        {
          issueId: "parse-issue-ticket-bad",
          fileId: "file-ticket-bad",
          sourceKind: "ticket_root",
          originalName: "票根网-失败.pdf",
          severity: "blocking",
          message: "票根网通行项缺少车牌号，不能进入核对。",
          sourcePage: 2,
          sourceLine: null,
          extractionMethod: "ocr",
          fieldName: "vehicle_plate",
        },
      ],
    };
    const taskAfterFileDelete = {
      ...taskWithSourceFiles,
      version: 4,
      sourceFiles: [taskWithSourceFiles.sourceFiles[0]],
      parseIssues: [],
    };
    const freshTask = {
      ...taskWithSourceFiles,
      taskId: "etc-recon-task-fresh-001",
      status: "draft",
      version: 1,
      title: "新建ETC对账批次",
      sourceFiles: [],
      parseIssues: [],
      vehiclePlates: [],
      etcInvoiceCount: 0,
      supplementCount: 0,
    };

    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [taskWithSourceFiles] } as never);
    vi.spyOn(etcApi as Record<string, unknown>, "deleteEtcReconciliationSourceFile").mockResolvedValue(taskAfterFileDelete as never);
    vi.spyOn(etcApi, "createEtcReconciliationTask").mockResolvedValue(freshTask as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByText("已上传文件")).toBeInTheDocument();
    expect(within(page).getByText("票根网-成功.pdf")).toBeInTheDocument();
    expect(within(page).getAllByText("票根网-失败.pdf").length).toBeGreaterThanOrEqual(1);
    expect(within(page).getAllByText("票根网").length).toBeGreaterThanOrEqual(2);
    expect(within(page).getByText("blocking")).toBeInTheDocument();
    expect(within(page).getAllByText(/票根网-失败\.pdf/).length).toBeGreaterThanOrEqual(1);
    expect(within(page).getByText(/第 2 页/)).toBeInTheDocument();
    expect(within(page).getByText(/ocr/)).toBeInTheDocument();
    expect(within(page).getByText(/票根网通行项缺少车牌号/)).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "新建批次" }));
    await waitFor(() => expect(within(page).getByText("新建ETC对账批次 / v1")).toBeInTheDocument());
    expect(within(page).queryByText("票根网-成功.pdf")).not.toBeInTheDocument();
    expect(within(page).queryByText(/票根网通行项缺少车牌号/)).not.toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "查看对账任务 2026-04 ETC 对账" }));
    await waitFor(() => expect(within(page).getAllByText("票根网-失败.pdf").length).toBeGreaterThanOrEqual(1));
    await user.click(within(page).getByRole("button", { name: "删除源文件 票根网-失败.pdf" }));
    const dialog = await screen.findByRole("dialog", { name: "删除源文件" });
    expect(dialog).toHaveTextContent("票根网-失败.pdf");
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect((etcApi as Record<string, unknown>).deleteEtcReconciliationSourceFile).toHaveBeenCalledWith(
        "etc-recon-task-source-001",
        "file-ticket-bad",
        3,
      );
    });
    await waitFor(() => expect(within(page).queryByText("票根网-失败.pdf")).not.toBeInTheDocument());
    expect(within(page).queryByText(/票根网通行项缺少车牌号/)).not.toBeInTheDocument();
  });

  test("switches to manual ticket-root text mode, opens paste dialog, and submits text", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const task = {
      taskId: "etc-recon-task-manual-001",
      status: "draft",
      version: 2,
      title: "2026-04 ETC 对账",
      periodStart: null,
      periodEnd: null,
      statementPeriodStart: null,
      statementPeriodEnd: null,
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "",
      oaTotalAmount: "0.00",
      etcInvoiceAmount: "0.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 0,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: [],
      confirmedItemSetHash: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    const updatedTask = {
      ...task,
      version: 3,
      ticketRootItems: [
        {
          itemId: "ticket-paste-1",
          sourceFileId: "paste-source-1",
          vehiclePlate: "云ADA0381",
          transactionAt: "2026-04-08 18:57:17",
          amount: "71.25",
          entryStation: "云南弥勒南站",
          exitStation: "云南小喜村站",
          invoiceCount: 2,
          recommendationStatus: "unmatched",
          linkedCreditCardItemIds: [],
        },
      ],
      sourceFiles: [
        {
          fileId: "paste-source-1",
          sourceKind: "ticket_root",
          originalName: "票根网手工粘贴-云ADA0381-202604-1.txt",
          contentType: "text/plain; charset=utf-8",
          hasBlockingIssue: false,
        },
      ],
      vehiclePlates: ["云ADA0381"],
      etcInvoiceCount: 2,
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [task] } as never);
    vi.spyOn(etcApi, "uploadEtcTicketRootTexts").mockResolvedValue(updatedTask as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("group", { name: "票根网导入方式" })).toBeInTheDocument();
    await user.click(within(page).getByRole("button", { name: "手工输入" }));
    expect(within(page).getByRole("button", { name: "点击粘贴票根网文本" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "增加粘贴框" })).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "点击粘贴票根网文本" }));
    const dialog = await screen.findByRole("dialog", { name: "粘贴票根网文本" });
    await user.type(within(dialog).getByLabelText("票根网文本"), "车牌号：云ADA0381\n交易时间：2026-04-08 18:57:17交易金额：￥71.25");
    await user.click(within(dialog).getByRole("button", { name: "确定" }));

    await waitFor(() => {
      expect(etcApi.uploadEtcTicketRootTexts).toHaveBeenCalledWith(
        "etc-recon-task-manual-001",
        [{ clientId: "paste-1", text: "车牌号：云ADA0381\n交易时间：2026-04-08 18:57:17交易金额：￥71.25" }],
        2,
      );
    });
    await waitFor(() => expect(within(page).getAllByText(/已解析 1 条/).length).toBeGreaterThanOrEqual(1));
  });

  test("disables PDF/JPG upload when manual ticket-root text source exists", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-task-manual-existing",
          status: "reviewing",
          version: 3,
          title: "已有手工粘贴",
          periodStart: null,
          periodEnd: null,
          statementPeriodStart: null,
          statementPeriodEnd: null,
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "",
          oaTotalAmount: "0.00",
          etcInvoiceAmount: "0.00",
          supplementAmount: "0.00",
          etcInvoiceCount: 1,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云ADA0381"],
          confirmedItemSetHash: "",
          creditCardItems: [],
          ticketRootItems: [],
          supplementEvidences: [],
          sourceFiles: [
            {
              fileId: "paste-source-1",
              sourceKind: "ticket_root",
              originalName: "票根网手工粘贴-云ADA0381-202604-1.txt",
              contentType: "text/plain; charset=utf-8",
              hasBlockingIssue: false,
            },
          ],
          parseIssues: [],
        },
      ],
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("button", { name: "PDF/JPG" })).toBeDisabled();
    expect(within(page).getByRole("button", { name: "票根网 PDF/JPG" })).toHaveAttribute("aria-disabled", "true");
    expect(within(page).getByText("已有手工粘贴源，删除后可切换。")).toBeInTheDocument();
  });

  test("shows per manual ticket-root paste source counts and plates", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-task-manual-existing",
          status: "reviewing",
          version: 3,
          title: "已有手工粘贴",
          periodStart: "2026-04-01",
          periodEnd: "2026-04-30",
          statementPeriodStart: "2026-04-01",
          statementPeriodEnd: "2026-04-30",
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "",
          oaTotalAmount: "0.00",
          etcInvoiceAmount: "0.00",
          supplementAmount: "0.00",
          etcInvoiceCount: 4,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云A516HJ", "云ADA0381"],
          confirmedItemSetHash: "",
          creditCardItems: [],
          ticketRootItems: [
            {
              itemId: "ticket-paste-1",
              sourceFileId: "paste-source-1",
              vehiclePlate: "云A516HJ",
              transactionAt: "2026-04-15 12:24:08",
              amount: "146.98",
              entryStation: "云南昆明西站",
              exitStation: "云南下关站",
              invoiceCount: 2,
              recommendationStatus: "unmatched",
              linkedCreditCardItemIds: [],
            },
            {
              itemId: "ticket-paste-2",
              sourceFileId: "paste-source-1",
              vehiclePlate: "云A516HJ",
              transactionAt: "2026-04-02 13:30:29",
              amount: "57.95",
              entryStation: "云南沙桥站",
              exitStation: "云南下关站",
              invoiceCount: 2,
              recommendationStatus: "unmatched",
              linkedCreditCardItemIds: [],
            },
            {
              itemId: "ticket-paste-3",
              sourceFileId: "paste-source-2",
              vehiclePlate: "云ADA0381",
              transactionAt: "2026-04-08 18:57:17",
              amount: "71.25",
              entryStation: "云南弥勒南站",
              exitStation: "云南小喜村站",
              invoiceCount: 2,
              recommendationStatus: "unmatched",
              linkedCreditCardItemIds: [],
            },
          ],
          supplementEvidences: [],
          sourceFiles: [
            {
              fileId: "paste-source-1",
              sourceKind: "ticket_root",
              originalName: "票根网手工粘贴-云A516HJ-202604-1.txt",
              contentType: "text/plain; charset=utf-8",
              hasBlockingIssue: false,
            },
            {
              fileId: "paste-source-2",
              sourceKind: "ticket_root",
              originalName: "票根网手工粘贴-云ADA0381-202604-1.txt",
              contentType: "text/plain; charset=utf-8",
              hasBlockingIssue: false,
            },
          ],
          parseIssues: [],
        },
      ],
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByText("云A516HJ / 已解析 2 条")).toBeInTheDocument();
    expect(within(page).getByText("云ADA0381 / 已解析 1 条")).toBeInTheDocument();
    expect(within(page).queryByText("已解析 3 条")).not.toBeInTheDocument();
  });

  test("disables manual ticket-root text mode when PDF/JPG ticket-root source exists", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-task-pdf-existing",
          status: "reviewing",
          version: 3,
          title: "已有PDF",
          periodStart: null,
          periodEnd: null,
          statementPeriodStart: null,
          statementPeriodEnd: null,
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "",
          oaTotalAmount: "0.00",
          etcInvoiceAmount: "0.00",
          supplementAmount: "0.00",
          etcInvoiceCount: 1,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云ADA0381"],
          confirmedItemSetHash: "",
          creditCardItems: [],
          ticketRootItems: [],
          supplementEvidences: [],
          sourceFiles: [
            {
              fileId: "ticket-pdf-1",
              sourceKind: "ticket_root",
              originalName: "票根网.pdf",
              contentType: "application/pdf",
              hasBlockingIssue: false,
            },
          ],
          parseIssues: [],
        },
      ],
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("button", { name: "手工输入" })).toBeDisabled();
    expect(within(page).getByText("已有 PDF/JPG 源文件，删除后可切换。")).toBeInTheDocument();
  });

  test("renders paired reconciliation table without row status chips or station wording", async () => {
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const table = await within(page).findByRole("table", { name: "ETC双侧核对明细" });

    expect(within(table).getByRole("columnheader", { name: "交易日/银行记账日" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "交易描述" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "金额" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "交易时间" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "金额 / 车牌" })).toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "站点/类型" })).not.toBeInTheDocument();

    const suggestedPairRow = within(table).getByTestId("etc-reconciliation-row-card-item-suggested");
    expect(suggestedPairRow).toHaveAttribute("data-highlight", "matched");
    expect(suggestedPairRow).toHaveTextContent("财付通-微信支付-贵州黔通智联");
    expect(suggestedPairRow).toHaveTextContent("2026-02-27");
    expect(suggestedPairRow).toHaveTextContent("10:00:00");
    expect(suggestedPairRow).toHaveTextContent("云ADA0381");
    expect(suggestedPairRow).toHaveTextContent("30.00");

    const missingRow = within(table).getByTestId("etc-reconciliation-row-card-item-missing");
    expect(missingRow).toHaveAttribute("data-highlight", "missing");
    expect(within(missingRow).getByTestId("etc-reconciliation-card-cell-card-item-missing")).toHaveAttribute("data-highlight", "missing");

    const extraRow = within(table).getByTestId("etc-reconciliation-row-right-ticket-item-extra");
    expect(extraRow).toHaveAttribute("data-highlight", "extra");
    expect(within(extraRow).getByTestId("etc-reconciliation-evidence-cell-ticket-item-extra")).toHaveAttribute("data-highlight", "extra");

    expect(within(table).getAllByText("2026").length).toBeGreaterThanOrEqual(1);
    expect(within(table).getAllByText("02-27").length).toBeGreaterThanOrEqual(1);
    expect(within(table).getAllByText("02-28").length).toBeGreaterThanOrEqual(1);
    expect(within(table).getByText("ETC补充凭证")).toBeInTheDocument();
    expect(within(table).queryByText("suggested")).not.toBeInTheDocument();
    expect(within(table).queryByText("系统建议")).not.toBeInTheDocument();
    expect(within(table).queryByText("manual")).not.toBeInTheDocument();
    expect(within(table).queryByText("covered")).not.toBeInTheDocument();
    expect(within(table).queryByText("人工已处理")).not.toBeInTheDocument();
    expect(within(table).queryByText(/昆明东/)).not.toBeInTheDocument();
    expect(within(table).queryByText(/玉溪北/)).not.toBeInTheDocument();
  });

  test("does not pair same-amount suggested rows without an explicit ticket link", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-unlinked-suggested",
          status: "reviewing",
          version: 1,
          title: "未明确 link 的同金额 suggested",
          periodStart: "2026-04-08",
          periodEnd: "2026-04-10",
          statementPeriodStart: "2026-04-01",
          statementPeriodEnd: "2026-04-30",
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "8514",
          oaTotalAmount: "71.25",
          etcInvoiceAmount: "0.00",
          supplementAmount: "0.00",
          etcInvoiceCount: 1,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云ADA0381"],
          confirmedItemSetHash: "",
          sourceFiles: [],
          parseIssues: [],
          supplementEvidences: [],
          creditCardItems: [
            {
              itemId: "card-unlinked-suggested",
              transactionDate: "2026-04-08",
              postingDate: "2026-04-09",
              cardLast4: "8514",
              description: "高速通行费-同金额未link",
              amount: "71.25",
              settlementAmount: "71.25",
              isEtcCandidate: true,
              candidateReason: "ETC关键词",
              recommendationStatus: "suggested_match",
              manualResolution: "unresolved",
              manualResolutionReason: "",
              reviewNote: "",
            },
          ],
          ticketRootItems: [
            {
              itemId: "ticket-unlinked-suggested",
              vehiclePlate: "云ADA0381",
              transactionAt: "2026-04-08T18:57:17",
              amount: "71.25",
              entryStation: "昆明南",
              exitStation: "九龙池",
              invoiceCount: 1,
              recommendationStatus: "suggested_match",
              linkedCreditCardItemIds: [],
            },
          ],
        },
      ],
    } as never);
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const table = await within(page).findByRole("table", { name: "ETC双侧核对明细" });

    const cardOnlyRow = within(table).getByTestId("etc-reconciliation-row-card-unlinked-suggested");
    expect(cardOnlyRow).toHaveAttribute("data-highlight", "missing");
    expect(cardOnlyRow).toHaveTextContent("高速通行费-同金额未link");
    expect(cardOnlyRow).not.toHaveTextContent("云ADA0381");

    const ticketOnlyRow = within(table).getByTestId("etc-reconciliation-row-right-ticket-unlinked-suggested");
    expect(ticketOnlyRow).toHaveAttribute("data-highlight", "extra");
    expect(ticketOnlyRow).toHaveTextContent("云ADA0381");
    expect(ticketOnlyRow).not.toHaveTextContent("高速通行费-同金额未link");
  });

  test("manual reconciliation accepts a suggested ticket instead of directly marking an item included", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByText("财付通-微信支付-贵州黔通智联"));
    const acceptButton = within(page).getByRole("button", { name: "接受推荐票根" });
    await waitFor(() => expect(acceptButton).toBeEnabled());
    await user.click(acceptButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/reconciliation-tasks/etc-recon-task-001/items/card-item-suggested",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            expectedVersion: 3,
            action: "link_ticket",
            ticketItemId: "ticket-item-001",
          }),
        }),
      );
    });
  });

  test("submitted mode hides submit action and shows OA information", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByRole("button", { name: "已提交 1" }));

    await waitFor(() => expect(within(page).getAllByText("ETC-HIST-2026-01").length).toBeGreaterThanOrEqual(1));
    expect(within(page).queryByRole("button", { name: "提交OA支付申请" })).not.toBeInTheDocument();
    expect(within(page).getAllByText(/刘树刚 \/ 2026-02-02 \/ OA 31.80/).length).toBeGreaterThanOrEqual(1);
    expect(within(page).getByRole("button", { name: "撤销提交状态" })).toBeEnabled();
    expect(within(page).getByRole("button", { name: "已提交批次不能删除" })).toBeDisabled();
  });

  test("clicking a batch updates the detail grid", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByText("ETC-2026-001")).toBeInTheDocument();
    expect(within(page).queryByText("ETC-2026-003")).not.toBeInTheDocument();

    await user.click(within(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-02")).getByRole("button", { name: "查看ETC批次 ETC-2026-03-B" }));

    await waitFor(() => expect(within(page).getAllByText("ETC-2026-03-B").length).toBeGreaterThanOrEqual(1));
    await waitFor(() => {
      expect(within(page).getByText("ETC-2026-003")).toBeInTheDocument();
      expect(within(page).queryByText("ETC-2026-001")).not.toBeInTheDocument();
    });
  });

  test("removes basket wording and old partial-selection actions", async () => {
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await within(page).findByRole("list", { name: "ETC批次列表" });

    expect(within(page).queryByText("提交篮子")).not.toBeInTheDocument();
    expect(within(page).queryByText("加入提交篮子")).not.toBeInTheDocument();
    expect(within(page).queryByText("移回未提交")).not.toBeInTheDocument();
    expect(within(page).queryByRole("checkbox")).not.toBeInTheDocument();
  });

  test("creates OA draft through the selected batch endpoint and refreshes after confirmation", async () => {
    const user = userEvent.setup();
    const openedWindow = {
      closed: false,
      close: vi.fn(),
      location: { href: "about:blank" },
      opener: {},
    };
    const openMock = vi.fn(() => openedWindow);
    vi.stubGlobal("open", openMock);
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await waitFor(() => expect(within(page).getAllByText("ETC-2026-03-A").length).toBeGreaterThanOrEqual(1));
    await user.click(within(page).getByRole("button", { name: "提交OA支付申请" }));

    const dialog = await screen.findByRole("dialog", { name: "创建OA支付申请草稿" });
    expect(dialog).toHaveTextContent("将为当前 ETC 批次创建 OA 支付申请草稿");
    expect(dialog).toHaveTextContent("当前批次：ETC-2026-03-A");
    await user.click(within(dialog).getByRole("button", { name: "确认创建草稿" }));

    expect(openMock).toHaveBeenCalledWith("about:blank", "_blank");
    await waitFor(() => expect(openedWindow.location.href).toContain("https://oa.example.test/oa/#/normal/forms/form/2"));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/batches/etc-batch-unsubmitted-01/draft",
      expect.objectContaining({ method: "POST" }),
    );

    const resultDialog = await screen.findByRole("dialog", { name: "OA提交结果确认" });
    expect(resultDialog).toHaveTextContent("批次号：ETC-2026-03-A");
    await user.click(within(resultDialog).getByRole("button", { name: "确认已提交OA" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/batches/etc-batch-unsubmitted-01/confirm-submitted",
      expect.objectContaining({ method: "POST" }),
    );
    expect(await within(page).findByRole("button", { name: "未提交 1" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "已提交 2" })).toBeInTheDocument();
  });
});
