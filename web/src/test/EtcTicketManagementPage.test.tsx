import { fireEvent, screen, waitFor, within } from "@testing-library/react";
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
      const batchListCalls = fetchMock.mock.calls.filter(([url]) => String(url).startsWith("/api/etc/business-batches?"));
      expect(batchListCalls.length).toBeGreaterThanOrEqual(2);
    });
    await waitFor(() => {
      const taskCalls = fetchMock.mock.calls.filter(([url]) => String(url) === "/api/etc/reconciliation-tasks");
      expect(taskCalls.length).toBeGreaterThanOrEqual(2);
    });
  });

  test("unsubmitted mode shows batch list and whole-batch OA submit action", async () => {
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(within(page).getByRole("heading", { name: "ETC票据" })).toBeInTheDocument();
    expect(await within(page).findByRole("button", { name: "未提交 2" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "已提交 1" })).toBeInTheDocument();
    expect(within(page).getByRole("list", { name: "ETC批次列表" })).toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toHaveTextContent("ETC-2026-03-A");
    await waitFor(() => expect(within(page).getByRole("button", { name: "提交OA" })).toBeEnabled());
    expect(within(page).getAllByText("ETC-2026-03-A").length).toBeGreaterThanOrEqual(1);
    expect(await within(page).findByText("ETC-2026-001")).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/business-batches?status=active&page=1&page_size=100",
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
    await user.click(within(row).getByRole("button", { name: "删除批次 ETC-2026-03-A" }));

    const dialog = await screen.findByRole("dialog", { name: "删除批次" });
    expect(dialog).toHaveTextContent("ETC-2026-03-A");
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/business-batches/etc-batch-unsubmitted-01",
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
    await user.click(within(row).getByRole("button", { name: "删除任务 2026-02 ETC 对账" }));

    const dialog = await screen.findByRole("dialog", { name: "删除任务" });
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

  test("closes the task delete dialog after delete succeeds even when the follow-up task refresh hangs", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const task = {
      taskId: "etc-recon-delete-refresh-hangs-001",
      status: "reviewing",
      version: 3,
      title: "2026-02 ETC 对账",
      periodStart: "2026-02-27",
      periodEnd: "2026-02-28",
      statementPeriodStart: "2026-02-01",
      statementPeriodEnd: "2026-02-29",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "7788",
      oaTotalAmount: "120.00",
      etcInvoiceAmount: "90.00",
      supplementAmount: "30.00",
      etcInvoiceCount: 2,
      supplementCount: 1,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "",
      importBatchId: "",
      etcBatchId: "",
      hasImportedInvoices: false,
      importedInvoiceCount: 0,
      importedInvoiceAmount: "0.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    } as never;
    let taskLoadCount = 0;
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockImplementation(() => {
      taskLoadCount += 1;
      if (taskLoadCount === 1) {
        return Promise.resolve({ items: [task] });
      }
      return new Promise(() => undefined);
    });
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue(task);
    const deleteTask = vi.spyOn(etcApi, "deleteEtcReconciliationTask").mockResolvedValue(undefined);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const row = await within(page).findByTestId("etc-reconciliation-task-row-etc-recon-delete-refresh-hangs-001");
    await user.click(within(row).getByRole("button", { name: "删除任务 2026-02 ETC 对账" }));
    const dialog = await screen.findByRole("dialog", { name: "删除任务" });
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(deleteTask).toHaveBeenCalledWith("etc-recon-delete-refresh-hangs-001", 3);
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "删除任务" })).not.toBeInTheDocument();
    });
    expect(within(page).queryByTestId("etc-reconciliation-task-row-etc-recon-delete-refresh-hangs-001")).not.toBeInTheDocument();
    expect(screen.queryByText("正在删除...")).not.toBeInTheDocument();
  });

  test("deletes an imported reconciliation task with the latest task version and removes it from the list", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const importedTask = {
      taskId: "etc-recon-imported-delete-001",
      status: "imported",
      version: 8,
      title: "2026-03 ETC 已导入",
      periodStart: "2026-03-01",
      periodEnd: "2026-03-31",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "7788",
      oaTotalAmount: "30.00",
      etcInvoiceAmount: "30.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "import-session-delete-001",
      etcBatchId: "",
      hasImportedInvoices: true,
      importedInvoiceCount: 1,
      importedInvoiceAmount: "30.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks")
      .mockResolvedValueOnce({ items: [importedTask] } as never)
      .mockResolvedValueOnce({ items: [] } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue({
      ...importedTask,
      version: 9,
    } as never);
    vi.spyOn(etcApi, "fetchEtcBatchDetail").mockResolvedValue({
      id: "import-session-delete-001",
      etcBatchId: "ETC-2026-IMPORTED-DELETE",
      externalBatchId: "ETC-2026-IMPORTED-DELETE",
      status: "unsubmitted",
      sourceType: "etc_zip",
      invoiceCount: 1,
      totalAmount: "30.00",
      taxAmount: "1.80",
      issueStartDate: "2026-03-03",
      issueEndDate: "2026-03-03",
      passageStartDate: "2026-03-03",
      passageEndDate: "2026-03-03",
      plateCount: 1,
      plateSummary: [{ plateNumber: "云ADA0381", invoiceCount: 1, totalAmount: "30.00" }],
      linkedOaRowId: "",
      linkedOaCaseId: "",
      linkedOaApplicant: "",
      linkedOaApplyDate: "",
      linkedOaAmount: "0.00",
      amountDelta: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      supplementAmount: "0.00",
      displayCountText: "ETC票 1 + 补充凭证 0",
      note: "",
      invoiceItems: [
        {
          id: "etc-inv-imported-delete-001",
          invoiceNumber: "ETC-IMPORTED-DELETE-001",
          issueDate: "2026-03-03",
          passageStartDate: "2026-03-03",
          passageEndDate: "2026-03-03",
          plateNumber: "云ADA0381",
          sellerName: "云南高速通行费",
          buyerName: "云南溯源科技",
          amountWithoutTax: "28.20",
          taxAmount: "1.80",
          totalAmount: "30.00",
          status: "unsubmitted",
          hasPdf: true,
          hasXml: true,
        },
      ],
    } as never);
    const deleteTask = vi.spyOn(etcApi, "deleteEtcReconciliationTask").mockResolvedValue(undefined as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const row = await within(page).findByTestId("etc-reconciliation-task-row-etc-recon-imported-delete-001");
    await user.click(within(row).getByRole("button", { name: "删除任务 2026-03 ETC 已导入" }));

    const dialog = await screen.findByRole("dialog", { name: "删除任务" });
    expect(dialog).toHaveTextContent("将删除该任务及未进入 OA 的数据");
    expect(dialog).toHaveTextContent("一并删除已导入发票");
    expect(dialog.textContent).toContain("重新确认并导入 ZIP");
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(deleteTask).toHaveBeenCalledWith("etc-recon-imported-delete-001", 9);
    });
    await waitFor(() => {
      expect(within(page).queryByTestId("etc-reconciliation-task-row-etc-recon-imported-delete-001")).not.toBeInTheDocument();
    });
    expect(within(page).getByText("选择左侧任务，或新建批次。")).toBeInTheDocument();
    expect(within(page).queryByRole("region", { name: "已导入ETC发票" })).not.toBeInTheDocument();
  });

  test("shows the reconciliation workspace with upload blocks, statuses, supplements, and parse issues", async () => {
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("button", { name: "新建批次" })).toBeInTheDocument();
    expect(within(page).getByTestId("etc-reconciliation-task-row-etc-recon-task-001")).toHaveTextContent("2.27-2.28");
    expect(within(page).getByTestId("etc-reconciliation-task-row-etc-recon-task-001")).toHaveTextContent("ETC票 2 + 补充凭证 1");

    expect(within(page).queryByRole("group", { name: "票根网导入方式" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "票根网 PDF/JPG" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "手工输入" })).not.toBeInTheDocument();
    expect(within(page).getByLabelText("上传信用卡账单")).toBeInTheDocument();
    expect(within(page).queryByLabelText("上传补充凭证")).not.toBeInTheDocument();
    expect(within(page).getByLabelText("上传票根网")).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "补ETC发票" })).not.toBeInTheDocument();
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

  test("renders the batch-level file drop upload boxes in the ticket-root import area", async () => {
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await within(page).findByLabelText("上传信用卡账单");
    const uploadRegion = page.querySelector('[aria-label="ETC对账文件上传"]');
    if (!(uploadRegion instanceof HTMLElement)) {
      throw new Error("Expected upload region to render.");
    }
    const dropGrid = uploadRegion.querySelector(".etc-upload-drop-grid");

    expect(dropGrid).toBeInstanceOf(HTMLElement);
    expect(within(dropGrid as HTMLElement).getByLabelText("上传信用卡账单")).toBeInTheDocument();
    expect(within(dropGrid as HTMLElement).queryByLabelText("上传补充凭证")).not.toBeInTheDocument();
    expect(within(dropGrid as HTMLElement).getByLabelText("上传票根网")).toBeInTheDocument();
    expect(within(dropGrid as HTMLElement).queryByRole("button", { name: "票根网 PDF/JPG" })).not.toBeInTheDocument();
    expect(within(dropGrid as HTMLElement).queryByRole("button", { name: "补ETC发票" })).not.toBeInTheDocument();
  });

  test("uploads a supplement from an unmatched card row with a delta note", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const initialTask = {
      taskId: "etc-recon-row-supplement-001",
      status: "reviewing",
      version: 5,
      title: "2026-03 ETC 对账",
      periodStart: "2026-03-03",
      periodEnd: "2026-03-03",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      oaTotalAmount: "0.00",
      etcInvoiceAmount: "0.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 0,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: [],
      confirmedItemSetHash: "",
      importBatchId: "",
      etcBatchId: "",
      hasImportedInvoices: false,
      importedInvoiceCount: 0,
      importedInvoiceAmount: "0.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      sourceFiles: [],
      parseIssues: [],
      creditCardItems: [
        {
          itemId: "card-unmatched-001",
          transactionDate: "2026-03-03",
          postingDate: "2026-03-04",
          cardLast4: "3632",
          description: "高速停车费",
          amount: "25.00",
          settlementAmount: "25.00",
          isEtcCandidate: true,
          candidateReason: "ETC关键词",
          recommendationStatus: "missing_ticket",
          manualResolution: "unresolved",
          manualResolutionReason: "",
          reviewNote: "",
        },
      ],
      ticketRootItems: [],
      supplementEvidences: [],
      reconciledItems: [],
    };
    const updatedTask = {
      ...initialTask,
      version: 6,
      supplementAmount: "25.00",
      supplementCount: 1,
      canConfirm: true,
      creditCardItems: [
        {
          ...initialTask.creditCardItems[0],
          manualResolution: "covered_by_supplement",
          reviewNote: "凭证少开 2 元，按信用卡实际支出提交。",
        },
      ],
      supplementEvidences: [
        {
          evidenceId: "supplement-row-001",
          sourceName: "parking.pdf",
          evidenceKind: "non_etc_invoice",
          amount: "23.00",
          paidAt: "2026-03-03",
          merchantName: "停车场",
          tags: ["ETC补充凭证"],
          includeInEtcZipCheck: false,
          includeInOaSubmission: true,
          includeInWorkbench: true,
        },
      ],
      reconciledItems: [
        {
          itemId: "RECONCILED-card-unmatched-001",
          creditCardItemId: "card-unmatched-001",
          ticketRootItemIds: [],
          supplementEvidenceIds: ["supplement-row-001"],
          resolution: "covered_by_supplement",
          note: "凭证少开 2 元，按信用卡实际支出提交。",
          claimAmount: "25.00",
          evidenceAmount: "23.00",
          amountDelta: "2.00",
          amountDeltaNote: "凭证少开 2 元，按信用卡实际支出提交。",
        },
      ],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [initialTask] } as never);
    const uploadSupplement = vi.spyOn(etcApi, "uploadEtcSupplementEvidenceForCard").mockResolvedValue(updatedTask as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByRole("button", { name: "上传补充凭证覆盖 高速停车费" }));
    const dialog = await screen.findByRole("dialog", { name: "上传补充凭证" });
    await user.upload(within(dialog).getByLabelText("选择补充凭证文件"), new File(["金额 23.00"], "parking.pdf", { type: "application/pdf" }));
    await user.type(within(dialog).getByLabelText("差异说明"), "凭证少开 2 元，按信用卡实际支出提交。");
    await user.click(within(dialog).getByRole("button", { name: "上传并覆盖" }));

    await waitFor(() => {
      expect(uploadSupplement).toHaveBeenCalledWith(
        "etc-recon-row-supplement-001",
        "card-unmatched-001",
        [expect.objectContaining({ name: "parking.pdf" })],
        5,
        {
          evidenceKind: "non_etc_invoice",
          note: "凭证少开 2 元，按信用卡实际支出提交。",
        },
      );
    });
    expect(await within(page).findByText("ETC补充凭证")).toBeInTheDocument();
    expect(within(page).getByTestId("etc-reconciliation-row-card-unmatched-001")).toHaveTextContent("23.00");
  });

  test("uploads ticket-root TXT files through the ticket-root files endpoint", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const txtUploadBox = await within(page).findByLabelText("上传票根网");
    expect(txtUploadBox).toBeEnabled();
    expect(within(page).queryByRole("button", { name: "票根网 PDF/JPG" })).not.toBeInTheDocument();

    const txtInput = txtUploadBox.querySelector('input[type="file"]');
    if (!(txtInput instanceof HTMLInputElement)) {
      throw new Error("Expected ticket-root TXT upload input to render.");
    }
    expect(txtInput).toHaveAttribute("accept", ".txt,text/plain");

    const txtFile = new File(["车牌号：云A516HJ\n交易时间：2026-04-02 13:30:29交易金额：￥57.95"], "云A516HJ", { type: "text/plain" });
    await user.upload(txtInput, txtFile);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-files",
        expect.objectContaining({ method: "POST" }),
      );
    });
    const request = fetchMock.mock.calls.find(([url]) => url === "/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-files")?.[1] as RequestInit;
    const formData = request.body as FormData;
    expect(formData.get("expectedVersion")).toBe("3");
    expect((formData.getAll("files") as File[])[0]).toMatchObject({ name: "云A516HJ", type: "text/plain" });
  });

  test("uploads ticket-root TXT files by dropping them on the upload box", async () => {
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const txtUploadBox = await within(page).findByLabelText("上传票根网");
    const txtFile = new File(["车牌号：云A516HJ\n交易时间：2026-04-02 13:30:29交易金额：￥57.95"], "云A516HJ.txt", { type: "text/plain" });

    fireEvent.dragEnter(txtUploadBox, { dataTransfer: { files: [txtFile] } });
    fireEvent.dragOver(txtUploadBox, { dataTransfer: { files: [txtFile] } });
    fireEvent.drop(txtUploadBox, { dataTransfer: { files: [txtFile] } });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-files",
        expect.objectContaining({ method: "POST" }),
      );
    });
    const request = fetchMock.mock.calls.find(([url]) => url === "/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-files")?.[1] as RequestInit;
    const formData = request.body as FormData;
    expect((formData.getAll("files") as File[])[0]).toMatchObject({ name: "云A516HJ.txt", type: "text/plain" });
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
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue(taskWithSourceFiles as never);
    vi.spyOn(etcApi as Record<string, unknown>, "deleteEtcReconciliationSourceFile").mockResolvedValue(taskAfterFileDelete as never);
    vi.spyOn(etcApi, "createEtcReconciliationTask").mockResolvedValue(freshTask as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByText("上传文件")).toBeInTheDocument();
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

  test("removes legacy ticket-root mode controls and keeps only TXT ticket-root upload", async () => {
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByLabelText("上传票根网")).toBeInTheDocument();
    expect(within(page).queryByRole("group", { name: "票根网导入方式" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "手工输入" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "TXT文件" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "PDF/JPG" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "点击粘贴票根网文本" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "票根网 PDF/JPG" })).not.toBeInTheDocument();
  });

  test("disables ticket-root TXT upload when a legacy non-TXT ticket-root source exists", async () => {
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
    expect(await within(page).findByLabelText("上传票根网")).toHaveAttribute("aria-disabled", "true");
    expect(within(page).getByText("已有非 TXT 来源，删除后可导入。")).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "票根网 PDF/JPG" })).not.toBeInTheDocument();
  });

  test("auto-selects TXT mode for text ticket-root files and shows each source summary", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-task-txt-existing",
          status: "reviewing",
          version: 3,
          title: "已有TXT",
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
          etcInvoiceCount: 3,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云A516HJ", "云ADA0381"],
          confirmedItemSetHash: "",
          creditCardItems: [],
          ticketRootItems: [
            {
              itemId: "ticket-txt-1",
              sourceFileId: "ticket-txt-source-1",
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
              itemId: "ticket-txt-2",
              sourceFileId: "ticket-txt-source-1",
              vehiclePlate: "云A516HJ",
              transactionAt: "2026-04-02 11:25:48",
              amount: "88.86",
              entryStation: "云南昆明西站",
              exitStation: "云南下关站",
              invoiceCount: 2,
              recommendationStatus: "unmatched",
              linkedCreditCardItemIds: [],
            },
            {
              itemId: "ticket-txt-3",
              sourceFileId: "ticket-txt-source-2",
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
              fileId: "ticket-txt-source-1",
              sourceKind: "ticket_root",
              originalName: "云A516HJ",
              contentType: "text/plain; charset=utf-8",
              hasBlockingIssue: false,
            },
            {
              fileId: "ticket-txt-source-2",
              sourceKind: "ticket_root",
              originalName: "云ADA0381.txt",
              contentType: "text/plain",
              hasBlockingIssue: false,
            },
          ],
          parseIssues: [],
        },
      ],
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByLabelText("上传票根网")).toBeEnabled();
    expect(within(page).queryByRole("button", { name: "手工输入" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "PDF/JPG" })).not.toBeInTheDocument();
    expect(within(page).queryByText("已有 TXT 源文件，删除后可切换。")).not.toBeInTheDocument();

    const sourceList = within(page).getByRole("list", { name: "已上传文件列表" });
    const firstSource = within(sourceList).getByText("云A516HJ").closest("li");
    const secondSource = within(sourceList).getByText("云ADA0381.txt").closest("li");
    if (!firstSource || !secondSource) {
      throw new Error("Expected both ticket-root TXT source rows to render.");
    }
    expect(firstSource).toHaveTextContent("票根网");
    expect(firstSource).toHaveTextContent("云A516HJ / 已解析 2 条");
    expect(firstSource).toHaveTextContent("金额合计 146.81");
    expect(firstSource).toHaveTextContent("日期 2026-04-02");

    expect(secondSource).toHaveTextContent("票根网");
    expect(secondSource).toHaveTextContent("云ADA0381 / 已解析 1 条");
    expect(secondSource).toHaveTextContent("金额合计 71.25");
    expect(secondSource).toHaveTextContent("日期 2026-04-08");
    expect(within(page).queryByRole("button", { name: /编辑票根网文本/ })).not.toBeInTheDocument();
  });

  test("shows legacy manual ticket-root source summaries only in the uploaded source list", async () => {
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
    const sourceList = await within(page).findByRole("list", { name: "已上传文件列表" });
    const firstSource = within(sourceList).getByText("票根网手工粘贴-云A516HJ-202604-1.txt").closest("li");
    const secondSource = within(sourceList).getByText("票根网手工粘贴-云ADA0381-202604-1.txt").closest("li");
    if (!firstSource || !secondSource) {
      throw new Error("Expected both legacy ticket-root source rows to be rendered.");
    }
    expect(firstSource).toHaveTextContent("云A516HJ");
    expect(firstSource).toHaveTextContent("已解析 2 条");
    expect(firstSource).toHaveTextContent("金额合计 204.93");
    expect(firstSource).toHaveTextContent("日期 2026-04-02 至 2026-04-15");

    expect(secondSource).toHaveTextContent("云ADA0381");
    expect(secondSource).toHaveTextContent("已解析 1 条");
    expect(secondSource).toHaveTextContent("金额合计 71.25");
    expect(secondSource).toHaveTextContent("日期 2026-04-08");
    expect(within(page).queryByRole("button", { name: /编辑票根网文本/ })).not.toBeInTheDocument();
    expect(within(page).queryByText("已解析 3 条")).not.toBeInTheDocument();
  });

  test("disables ticket-root TXT upload when a legacy PDF ticket-root source exists", async () => {
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
    expect(await within(page).findByLabelText("上传票根网")).toHaveAttribute("aria-disabled", "true");
    expect(within(page).getByText("已有非 TXT 来源，删除后可导入。")).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "手工输入" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "票根网 PDF/JPG" })).not.toBeInTheDocument();
  });

  test("renders paired reconciliation table without row status chips or station wording", async () => {
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const table = await within(page).findByRole("table", { name: "ETC双侧核对明细" });
    expect(within(page).getByRole("button", { name: "全选" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "全选配对项" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "清空" })).toBeInTheDocument();

    expect(within(table).getByRole("columnheader", { name: "交易日" })).toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "交易日/银行记账日" })).not.toBeInTheDocument();
    expect(within(table).queryByText("银行记账日")).not.toBeInTheDocument();
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

    expect(within(suggestedPairRow).getByTestId("etc-card-date-transaction-card-item-suggested")).toHaveTextContent("2026-02-27");
    expect(within(suggestedPairRow).queryByTestId("etc-card-date-posting-card-item-suggested")).not.toBeInTheDocument();
    expect(within(suggestedPairRow).queryByText("2026-02-28")).not.toBeInTheDocument();
    expect(within(suggestedPairRow).queryByText("2026-02")).not.toBeInTheDocument();
    expect(within(suggestedPairRow).queryByText("交易")).not.toBeInTheDocument();
    expect(within(suggestedPairRow).queryByText("记账")).not.toBeInTheDocument();
    expect(within(table).queryByText("02-27")).not.toBeInTheDocument();
    expect(within(table).queryByText("02-28")).not.toBeInTheDocument();
    expect(within(table).getByText("ETC补充凭证")).toBeInTheDocument();
    expect(within(table).queryByText("suggested")).not.toBeInTheDocument();
    expect(within(table).queryByText("系统建议")).not.toBeInTheDocument();
    expect(within(table).queryByText("manual")).not.toBeInTheDocument();
    expect(within(table).queryByText("covered")).not.toBeInTheDocument();
    expect(within(table).queryByText("人工已处理")).not.toBeInTheDocument();
    expect(within(table).queryByText(/昆明东/)).not.toBeInTheDocument();
    expect(within(table).queryByText(/玉溪北/)).not.toBeInTheDocument();

    const compactBlock = page.querySelector(".etc-reconciliation-table-block");
    if (!(compactBlock instanceof HTMLElement)) {
      throw new Error("Expected reconciliation table block to render.");
    }
    expect(getComputedStyle(compactBlock).getPropertyValue("--etc-reconciliation-row-height").trim()).toBe("32px");
    const bodyRowCount = table.querySelectorAll("tbody .etc-reconciliation-table-row").length;
    expect(table.querySelectorAll(".etc-reconciliation-divider")).toHaveLength(2 + bodyRowCount);
    expect(getComputedStyle(within(missingRow).getByTestId("etc-reconciliation-card-cell-card-item-missing")).boxShadow).not.toContain("inset");
    expect(getComputedStyle(within(extraRow).getByTestId("etc-reconciliation-evidence-cell-ticket-item-extra")).boxShadow).not.toContain("inset");
  });

  test("keeps long reconciliation descriptions to one line until expanded", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const table = await within(page).findByRole("table", { name: "ETC双侧核对明细" });
    const row = within(table).getByTestId("etc-reconciliation-row-card-item-suggested");
    const description = within(row).getByTestId("etc-reconciliation-description-card-item-suggested");

    expect(description).toHaveClass("etc-reconciliation-description--collapsed");
    expect(within(row).getByRole("button", { name: "展开交易描述 card-item-suggested" })).toBeInTheDocument();

    await user.click(within(row).getByRole("button", { name: "展开交易描述 card-item-suggested" }));

    expect(description).toHaveClass("etc-reconciliation-description--expanded");
    expect(within(row).getByRole("button", { name: "收起交易描述 card-item-suggested" })).toBeInTheDocument();
  });

  test("selects reconciliation rows locally with all, paired-only, and clear actions", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const table = await within(page).findByRole("table", { name: "ETC双侧核对明细" });
    const rowCheckboxes = [
      within(table).getByRole("checkbox", { name: "选择核对行 card-item-suggested" }),
      within(table).getByRole("checkbox", { name: "选择核对行 card-item-missing" }),
      within(table).getByRole("checkbox", { name: "选择核对行 card-item-covered" }),
      within(table).getByRole("checkbox", { name: "选择核对行 right-ticket-item-extra" }),
    ];

    rowCheckboxes.forEach((checkbox) => expect(checkbox).not.toBeChecked());

    await user.click(rowCheckboxes[1]);
    expect(rowCheckboxes[1]).toBeChecked();
    expect(rowCheckboxes[0]).not.toBeChecked();

    await user.click(within(page).getByRole("button", { name: "全选" }));
    rowCheckboxes.forEach((checkbox) => expect(checkbox).toBeChecked());

    await user.click(within(page).getByRole("button", { name: "清空" }));
    rowCheckboxes.forEach((checkbox) => expect(checkbox).not.toBeChecked());

    await user.click(within(page).getByRole("button", { name: "全选配对项" }));
    expect(rowCheckboxes[0]).toBeChecked();
    expect(rowCheckboxes[2]).toBeChecked();
    expect(rowCheckboxes[1]).not.toBeChecked();
    expect(rowCheckboxes[3]).not.toBeChecked();
  });

  test("updates confirmation metrics from the checked paired rows", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const metrics = await within(page).findByLabelText("本次确认预览");

    expect(metrics).toHaveTextContent("金额");
    expect(metrics).toHaveTextContent("0.00");
    expect(metrics).toHaveTextContent("范围");
    expect(metrics).toHaveTextContent("-");
    expect(metrics).toHaveTextContent("数量");
    expect(metrics).toHaveTextContent("ETC票 0 + 补充凭证 0");

    await user.click(within(page).getByRole("button", { name: "全选配对项" }));

    expect(metrics).toHaveTextContent("60.00");
    expect(metrics).toHaveTextContent("2026-02-27");
    expect(metrics).toHaveTextContent("2026-02-28");
    expect(metrics).toHaveTextContent("ETC票 1 + 补充凭证 1");

    await user.click(within(page).getByRole("button", { name: "清空" }));

    expect(metrics).toHaveTextContent("0.00");
    expect(metrics).toHaveTextContent("-");
    expect(metrics).toHaveTextContent("ETC票 0 + 补充凭证 0");
  });

  test("submits the checked card item ids when confirming reconciliation and blocks empty selection", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-task-001",
          status: "reviewing",
          version: 3,
          title: "2026-02 ETC 对账",
          periodStart: "2026-02-27",
          periodEnd: "2026-02-28",
          statementPeriodStart: "2026-02-01",
          statementPeriodEnd: "2026-02-29",
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "7788",
          oaTotalAmount: "120.00",
          etcInvoiceAmount: "90.00",
          supplementAmount: "30.00",
          etcInvoiceCount: 2,
          supplementCount: 1,
          canConfirm: false,
          vehiclePlates: ["云ADA0381"],
          confirmedItemSetHash: "",
          sourceFiles: [],
          parseIssues: [],
          creditCardItems: [
            {
              itemId: "card-item-suggested",
              transactionDate: "2026-02-27",
              postingDate: "2026-02-28",
              cardLast4: "7788",
              description: "财付通-微信支付-贵州黔通智联",
              amount: "30.00",
              settlementAmount: "30.00",
              isEtcCandidate: true,
              candidateReason: "ETC关键词",
              recommendationStatus: "suggested_match",
              manualResolution: "unresolved",
              manualResolutionReason: "",
              reviewNote: "",
            },
            {
              itemId: "card-item-covered",
              transactionDate: "2026-02-28",
              postingDate: "2026-02-29",
              cardLast4: "7788",
              description: "停车费补充凭证",
              amount: "30.00",
              settlementAmount: "30.00",
              isEtcCandidate: false,
              candidateReason: "",
              recommendationStatus: "not_candidate",
              manualResolution: "covered_by_supplement",
              manualResolutionReason: "",
              reviewNote: "",
            },
          ],
          ticketRootItems: [
            {
              itemId: "ticket-item-001",
              sourceFileId: "ticket-file-001",
              vehiclePlate: "云ADA0381",
              transactionAt: "2026-02-27T10:00:00",
              amount: "30.00",
              entryStation: "昆明东",
              exitStation: "玉溪北",
              invoiceCount: 1,
              recommendationStatus: "suggested_match",
              linkedCreditCardItemIds: ["card-item-suggested"],
            },
          ],
          supplementEvidences: [
            {
              evidenceId: "supplement-001",
              sourceName: "parking.pdf",
              evidenceKind: "non_etc_invoice",
              amount: "30.00",
              paidAt: "2026-02-28",
              merchantName: "停车场",
              tags: ["ETC补充凭证"],
              includeInEtcZipCheck: false,
              includeInOaSubmission: true,
              includeInWorkbench: true,
            },
          ],
        },
      ],
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await within(page).findByRole("table", { name: "ETC双侧核对明细" });
    expect(within(page).getByRole("button", { name: "确认对账" })).toBeDisabled();

    await user.click(within(page).getByRole("button", { name: "全选配对项" }));
    expect(within(page).getByRole("button", { name: "确认对账" })).toBeEnabled();
    await user.click(within(page).getByRole("button", { name: "确认对账" }));

    await waitFor(() => {
      const confirmRequest = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/api/etc/reconciliation-tasks/etc-recon-task-001/confirm"))?.[1] as RequestInit | undefined;
      expect(confirmRequest).toBeDefined();
      expect(JSON.parse(String(confirmRequest?.body))).toMatchObject({
        expectedVersion: 3,
        confirmedCreditCardItemIds: ["card-item-suggested"],
      });
    });
  });

  test("shows imported task invoices under the reconciliation task and collapses both task blocks", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const importedTask = {
      taskId: "etc-recon-imported-001",
      status: "imported",
      version: 8,
      title: "2026-03 ETC 已导入",
      periodStart: "2026-03-01",
      periodEnd: "2026-03-31",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "7788",
      oaTotalAmount: "30.00",
      etcInvoiceAmount: "30.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "import-session-001",
      etcBatchId: "etc-batch-imported-001",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [importedTask],
    } as never);
    vi.spyOn(etcApi, "fetchEtcBatchDetail").mockResolvedValue({
      id: "etc-batch-imported-001",
      etcBatchId: "ETC-2026-IMPORTED",
      externalBatchId: "ETC-2026-IMPORTED",
      status: "unsubmitted",
      sourceType: "etc_zip",
      invoiceCount: 1,
      totalAmount: "30.00",
      taxAmount: "1.80",
      issueStartDate: "2026-03-03",
      issueEndDate: "2026-03-03",
      passageStartDate: "2026-03-03",
      passageEndDate: "2026-03-03",
      plateCount: 1,
      plateSummary: [{ plateNumber: "云ADA0381", invoiceCount: 1, totalAmount: "30.00" }],
      linkedOaRowId: "",
      linkedOaCaseId: "",
      linkedOaApplicant: "",
      linkedOaApplyDate: "",
      linkedOaAmount: "0.00",
      amountDelta: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      supplementAmount: "0.00",
      displayCountText: "ETC票 1 + 补充凭证 0",
      note: "",
      invoiceItems: [
        {
          id: "etc-inv-imported-001",
          invoiceNumber: "ETC-IMPORTED-001",
          issueDate: "2026-03-03",
          passageStartDate: "2026-03-03",
          passageEndDate: "2026-03-03",
          plateNumber: "云ADA0381",
          sellerName: "云南高速通行费",
          buyerName: "云南溯源科技",
          amountWithoutTax: "28.20",
          taxAmount: "1.80",
          totalAmount: "30.00",
          status: "unsubmitted",
          hasPdf: true,
          hasXml: true,
        },
      ],
    } as never);
    vi.spyOn(etcApi, "deleteEtcReconciliationTaskImportedInvoices").mockResolvedValue({
      ...importedTask,
      status: "ready_for_import",
      version: 9,
      importBatchId: "",
      etcBatchId: "",
    } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue({
      ...importedTask,
      version: 9,
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("heading", { name: "已导入发票" })).toBeInTheDocument();
    const importedInvoiceSection = within(page).getByRole("region", { name: "已导入ETC发票" });
    expect(within(importedInvoiceSection).getByText("1 张")).toBeInTheDocument();
    const removeButton = within(importedInvoiceSection).getByRole("button", { name: "移除发票" });
    expect(removeButton).toBeEnabled();
    expect(within(importedInvoiceSection).getByRole("table", { name: "已导入ETC发票明细" })).toBeInTheDocument();
    expect(within(importedInvoiceSection).getByText("ETC-IMPORTED-001")).toBeInTheDocument();
    expect(etcApi.fetchEtcBatchDetail).toHaveBeenCalledWith("import-session-001", expect.any(AbortSignal));

    await user.click(removeButton);
    const dialog = await screen.findByRole("dialog", { name: "移除发票" });
    expect(dialog).toHaveTextContent("2026-03 ETC 已导入");
    expect(dialog).toHaveTextContent("1 张");
    await user.click(within(dialog).getByRole("button", { name: "确认移除" }));

    await waitFor(() => {
      expect(etcApi.deleteEtcReconciliationTaskImportedInvoices).toHaveBeenCalledWith("etc-recon-imported-001", 9);
    });
    await waitFor(() => {
      expect(within(page).queryByRole("region", { name: "已导入ETC发票" })).not.toBeInTheDocument();
    });
    expect(within(page).getByText("2026-03 ETC 已导入 / v9")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "移除发票" })).not.toBeInTheDocument());

    await user.click(within(page).getByRole("button", { name: "折叠任务" }));
    expect(within(page).queryByText("已导入发票")).not.toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "展开任务" })).toHaveAttribute("aria-expanded", "false");

    expect(within(page).getByRole("region", { name: "ETC批次详情" })).toBeInTheDocument();
    await user.click(within(page).getByRole("button", { name: "折叠详情" }));
    expect(within(page).queryByRole("table", { name: "ETC发票明细" })).not.toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "展开详情" })).toHaveAttribute("aria-expanded", "false");
  });

  test("creates OA draft from the selected imported reconciliation task batch", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const openedWindow = {
      closed: false,
      close: vi.fn(),
      location: { href: "about:blank" },
      opener: {},
    };
    const openMock = vi.fn(() => openedWindow);
    vi.stubGlobal("open", openMock);
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-imported-submit-001",
          status: "imported",
          version: 11,
          title: "2026-04 ETC 已导入",
          periodStart: "2026-03-28",
          periodEnd: "2026-04-27",
          statementPeriodStart: "2026-03-28",
          statementPeriodEnd: "2026-04-27",
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "8514",
          oaTotalAmount: "1673.30",
          etcInvoiceAmount: "1673.30",
          supplementAmount: "0.00",
          etcInvoiceCount: 37,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云ADA0381"],
          confirmedItemSetHash: "sha256:selected",
          importBatchId: "etc_import_batch_0004",
          etcBatchId: "",
          hasImportedInvoices: true,
          importedInvoiceCount: 36,
          importedInvoiceAmount: "1673.30",
          oaDraftBatchId: "",
          oaDraftStatus: "",
          submittedConfirmedAt: "",
          creditCardItems: [],
          ticketRootItems: [],
          supplementEvidences: [],
          sourceFiles: [],
          parseIssues: [],
        },
      ],
    } as never);
    vi.spyOn(etcApi, "fetchEtcBatchDetail").mockResolvedValue({
      id: "etc_import_batch_0004",
      etcBatchId: "etc_import_batch_0004",
      externalBatchId: "etc_import_batch_0004",
      status: "unsubmitted",
      sourceType: "etc_import",
      invoiceCount: 36,
      totalAmount: "1673.30",
      taxAmount: "48.74",
      issueStartDate: "2026-03-28",
      issueEndDate: "2026-04-27",
      passageStartDate: "2026-03-28",
      passageEndDate: "2026-04-27",
      plateCount: 1,
      plateSummary: [{ plateNumber: "云ADA0381", invoiceCount: 36, totalAmount: "1673.30" }],
      linkedOaRowId: "",
      linkedOaCaseId: "",
      linkedOaApplicant: "",
      linkedOaApplyDate: "",
      linkedOaAmount: "0.00",
      amountDelta: "0.00",
      etcInvoiceCount: 37,
      supplementCount: 0,
      supplementAmount: "0.00",
      displayCountText: "ETC票 37 + 补充凭证 0",
      note: "",
      invoiceItems: [
        {
          id: "etc-inv-imported-submit-001",
          invoiceNumber: "ETC-IMPORTED-SUBMIT-001",
          issueDate: "2026-04-27",
          passageStartDate: "2026-04-27",
          passageEndDate: "2026-04-27",
          plateNumber: "云ADA0381",
          sellerName: "云南高速通行费",
          buyerName: "云南溯源科技",
          amountWithoutTax: "1624.56",
          taxAmount: "48.74",
          totalAmount: "1673.30",
          status: "unsubmitted",
          hasPdf: true,
          hasXml: true,
        },
      ],
    } as never);
    const businessBatch = {
      businessBatchId: "etc_business_batch_imported_submit_001",
      taskId: "etc-recon-imported-submit-001",
      status: "imported",
      version: 11,
      ownerUserId: "web_finance_user",
      ownerOrgId: "finance",
      importBatchIds: ["etc_import_batch_0004"],
      submissionBatchId: "",
      externalEtcBatchId: "ETC-2026-OA-001",
      oaDraftId: "",
      oaDraftUrl: "",
      oaRowId: "",
      oaProcessStatus: "",
      oaDetectionStatus: "",
      oaDetectionReason: "",
      oaDetectionError: "",
      oaDetectionStartedAt: "",
      oaDetectionNextRunAt: "",
      oaDetectionDeadlineAt: "",
      oaDetectionFinalRetryUntil: "",
      oaDetectionAttempts: 0,
      invoiceSummary: { count: 36, amount: "1673.30" },
      invoiceIds: ["etc-inv-imported-submit-001"],
      importAttempts: [
        {
          attemptId: "attempt-imported-submit-001",
          importBatchId: "etc_import_batch_0004",
          status: "imported",
          imported: 36,
          duplicatesSkipped: 0,
          attachmentsCompleted: 0,
          failed: 0,
          createdAt: "2026-05-19T09:00:00+08:00",
        },
      ],
      auditEvents: [],
      createdAt: "2026-05-19T09:00:00+08:00",
      updatedAt: "2026-05-19T09:00:00+08:00",
      invoiceItems: [
        {
          id: "etc-inv-imported-submit-001",
          invoiceNumber: "ETC-IMPORTED-SUBMIT-001",
          issueDate: "2026-04-27",
          passageStartDate: "2026-04-27",
          passageEndDate: "2026-04-27",
          plateNumber: "云ADA0381",
          sellerName: "云南高速通行费",
          buyerName: "云南溯源科技",
          amountWithoutTax: "1624.56",
          taxAmount: "48.74",
          totalAmount: "1673.30",
          status: "unsubmitted",
          hasPdf: true,
          hasXml: true,
        },
      ],
    } as const;
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 1, submitted: 0 },
      items: [businessBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockResolvedValue(businessBatch as never);
    const createDraft = vi.spyOn(etcApi, "createEtcBusinessBatchOaDraft").mockResolvedValue({
      ...businessBatch,
      status: "oa_submission_detecting",
      version: 12,
      submissionBatchId: "etc_batch_submission_001",
      oaDraftId: "oa-draft-001",
      oaDraftUrl: "https://oa.example.test/oa/#/normal/forms/form/2?formId=2&id=oa-draft-001",
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("region", { name: "导入记录" })).toBeInTheDocument();
    expect(within(page).getByText(/导入 36，重复 0，补齐 0，失败 0/)).toBeInTheDocument();

    const submitButton = within(page).getByRole("button", { name: "提交OA" });
    await waitFor(() => expect(submitButton).toBeEnabled());
    await user.click(submitButton);

    const dialog = await screen.findByRole("dialog", { name: "创建OA草稿" });
    expect(dialog).toHaveTextContent("为当前任务的 36 张发票创建 OA 草稿，合计 1673.30。");
    expect(dialog).toHaveTextContent("批次：ETC-2026-OA-001");
    await user.click(within(dialog).getByRole("button", { name: "创建草稿" }));

    expect(openMock).toHaveBeenCalledWith("about:blank", "_blank");
    await waitFor(() => expect(createDraft).toHaveBeenCalledWith("etc_business_batch_imported_submit_001", { expectedVersion: 11 }));
    await waitFor(() => expect(openedWindow.location.href).toContain("https://oa.example.test/oa/#/normal/forms/form/2"));
  });

  test("deletes an imported reconciliation task through confirmation", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    const importedTask = {
      taskId: "etc-recon-imported-delete-001",
      status: "imported",
      version: 8,
      title: "2026-03 ETC 已导入",
      periodStart: "2026-03-01",
      periodEnd: "2026-03-31",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      approvedDelta: "0.00",
      approvedDeltaNote: "",
      cardLast4: "7788",
      oaTotalAmount: "30.00",
      etcInvoiceAmount: "30.00",
      supplementAmount: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      confirmedItemSetHash: "sha256:selected",
      importBatchId: "import-session-delete-001",
      etcBatchId: "",
      hasImportedInvoices: true,
      importedInvoiceCount: 1,
      importedInvoiceAmount: "30.00",
      oaDraftBatchId: "",
      oaDraftStatus: "",
      submittedConfirmedAt: "",
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      sourceFiles: [],
      parseIssues: [],
    };
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks")
      .mockResolvedValueOnce({ items: [importedTask] } as never)
      .mockResolvedValue({ items: [] } as never);
    vi.spyOn(etcApi, "fetchEtcReconciliationTask").mockResolvedValue(importedTask as never);
    vi.spyOn(etcApi, "fetchEtcBatchDetail").mockResolvedValue({
      id: "import-session-delete-001",
      etcBatchId: "import-session-delete-001",
      externalBatchId: "import-session-delete-001",
      status: "unsubmitted",
      sourceType: "etc_zip",
      invoiceCount: 1,
      totalAmount: "30.00",
      taxAmount: "1.80",
      issueStartDate: "2026-03-03",
      issueEndDate: "2026-03-03",
      passageStartDate: "2026-03-03",
      passageEndDate: "2026-03-03",
      plateCount: 1,
      plateSummary: [],
      linkedOaRowId: "",
      linkedOaCaseId: "",
      linkedOaApplicant: "",
      linkedOaApplyDate: "",
      linkedOaAmount: "0.00",
      amountDelta: "0.00",
      etcInvoiceCount: 1,
      supplementCount: 0,
      supplementAmount: "0.00",
      displayCountText: "ETC票 1 + 补充凭证 0",
      note: "",
      invoiceItems: [],
    } as never);
    vi.spyOn(etcApi, "deleteEtcReconciliationTask").mockResolvedValue(undefined);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const deleteButton = await within(page).findByRole("button", { name: /删除任务 2026-03 ETC 已导入/ });
    expect(deleteButton).toBeEnabled();
    await user.click(deleteButton);
    const dialog = await screen.findByRole("dialog", { name: "删除任务" });
    expect(dialog).toHaveTextContent("将一并删除已导入发票");
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(etcApi.deleteEtcReconciliationTask).toHaveBeenCalledWith("etc-recon-imported-delete-001", 8);
    });
    await waitFor(() => {
      expect(within(page).queryByTestId("etc-reconciliation-task-row-etc-recon-imported-delete-001")).not.toBeInTheDocument();
    });
  });

  test("does not render a task imported invoice batch as a separate left-side batch", async () => {
    installMockApiFetch();
    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({
      items: [
        {
          taskId: "etc-recon-task-imported-batch",
          status: "imported",
          version: 5,
          title: "2026-03 ETC 对账",
          periodStart: "2026-03-01",
          periodEnd: "2026-03-31",
          statementPeriodStart: "2026-03-01",
          statementPeriodEnd: "2026-03-31",
          approvedDelta: "0.00",
          approvedDeltaNote: "",
          cardLast4: "",
          oaTotalAmount: "21.35",
          etcInvoiceAmount: "21.35",
          supplementAmount: "0.00",
          etcInvoiceCount: 1,
          supplementCount: 0,
          canConfirm: false,
          vehiclePlates: ["云A8H66Q"],
          confirmedItemSetHash: "sha256:selected",
          importBatchId: "",
          etcBatchId: "etc-batch-unsubmitted-02",
          oaDraftBatchId: "",
          oaDraftStatus: "",
          submittedConfirmedAt: "",
          creditCardItems: [],
          ticketRootItems: [],
          supplementEvidences: [],
          sourceFiles: [],
          parseIssues: [],
        },
      ],
    } as never);

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByTestId("etc-reconciliation-task-row-etc-recon-task-imported-batch")).toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toBeInTheDocument();
    expect(within(page).queryByTestId("etc-batch-row-etc-batch-unsubmitted-02")).not.toBeInTheDocument();
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

  test("refreshes reconciliation matches from the task API and rerenders explicit links", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const baseFetch = fetchMock.getMockImplementation();
    const initialTask = {
      taskId: "etc-recon-refresh-001",
      status: "reviewing",
      version: 4,
      title: "刷新匹配",
      periodStart: "2026-04-08",
      periodEnd: "2026-04-08",
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
          itemId: "card-refresh-001",
          transactionDate: "2026-04-08",
          postingDate: "2026-04-09",
          cardLast4: "8514",
          description: "高速通行费-刷新后配对",
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
          itemId: "ticket-refresh-001",
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
    };
    const refreshedTask = {
      ...initialTask,
      version: 5,
      ticketRootItems: [
        {
          ...initialTask.ticketRootItems[0],
          linkedCreditCardItemIds: ["card-refresh-001"],
        },
      ],
    };

    vi.spyOn(etcApi, "fetchEtcReconciliationTasks").mockResolvedValue({ items: [initialTask] } as never);
    fetchMock.mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (String(url).endsWith("/api/etc/reconciliation-tasks/etc-recon-refresh-001/refresh-matches")) {
        return new Response(JSON.stringify(refreshedTask), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (!baseFetch) {
        throw new Error(`Unhandled fetch ${String(url)}`);
      }
      return baseFetch(input, init);
    });

    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    const table = await within(page).findByRole("table", { name: "ETC双侧核对明细" });
    expect(within(table).getByTestId("etc-reconciliation-row-card-refresh-001")).toHaveAttribute("data-highlight", "missing");
    expect(within(table).getByTestId("etc-reconciliation-row-right-ticket-refresh-001")).toHaveAttribute("data-highlight", "extra");

    await user.click(within(page).getByRole("button", { name: "刷新匹配" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/etc/reconciliation-tasks/etc-recon-refresh-001/refresh-matches",
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => {
      expect(within(table).getByTestId("etc-reconciliation-row-card-refresh-001")).toHaveAttribute("data-highlight", "matched");
    });
    expect(within(table).queryByTestId("etc-reconciliation-row-right-ticket-refresh-001")).not.toBeInTheDocument();
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
    expect(within(page).queryByRole("button", { name: "提交OA" })).not.toBeInTheDocument();
    expect(within(page).getAllByText("OA已提交").length).toBeGreaterThanOrEqual(1);
    expect(within(page).getByRole("button", { name: "撤销提交状态" })).toBeEnabled();
    expect(within(page).getByRole("button", { name: "已提交批次不能删除" })).toBeDisabled();
  });

  test("renders batch invoice details with a native table instead of DataGrid", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByRole("table", { name: "ETC发票明细" })).toBeInTheDocument();
    expect(within(page).queryByRole("grid", { name: "ETC发票明细" })).not.toBeInTheDocument();
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
    await within(page).findByRole("table", { name: "ETC双侧核对明细" });

    expect(within(page).queryByText("提交篮子")).not.toBeInTheDocument();
    expect(within(page).queryByText("加入提交篮子")).not.toBeInTheDocument();
    expect(within(page).queryByText("移回未提交")).not.toBeInTheDocument();
    expect(within(page).getAllByRole("checkbox", { name: /选择核对行/ })).toHaveLength(4);
  });

  test("creates OA draft through the selected business batch and waits for OA detection", async () => {
    const user = userEvent.setup();
    const openedWindow = {
      closed: false,
      close: vi.fn(),
      location: { href: "about:blank" },
      opener: {},
    };
    const openMock = vi.fn(() => openedWindow);
    vi.stubGlobal("open", openMock);
    installMockApiFetch();
    const businessBatch = {
      businessBatchId: "etc_business_batch_0001",
      taskId: "etc-recon-task-001",
      status: "imported",
      version: 7,
      ownerUserId: "web_finance_user",
      ownerOrgId: "finance",
      importBatchIds: ["etc_import_batch_0004"],
      submissionBatchId: "",
      externalEtcBatchId: "ETC-2026-03-A",
      oaDraftId: "",
      oaDraftUrl: "",
      oaRowId: "",
      oaProcessStatus: "",
      oaDetectionStatus: "",
      oaDetectionReason: "",
      oaDetectionError: "",
      oaDetectionStartedAt: "",
      oaDetectionNextRunAt: "",
      oaDetectionDeadlineAt: "",
      oaDetectionFinalRetryUntil: "",
      oaDetectionAttempts: 0,
      invoiceSummary: { count: 2, amount: "32.26" },
      invoiceIds: ["etc-inv-001", "etc-inv-002"],
      importAttempts: [
        {
          attemptId: "attempt-001",
          importBatchId: "etc_import_batch_0004",
          status: "imported",
          imported: 2,
          duplicatesSkipped: 0,
          attachmentsCompleted: 0,
          failed: 0,
          createdAt: "2026-05-19T09:00:00+08:00",
        },
      ],
      auditEvents: [],
      createdAt: "2026-05-19T09:00:00+08:00",
      updatedAt: "2026-05-19T09:00:00+08:00",
      invoiceItems: [
        {
          id: "etc-inv-001",
          invoiceNumber: "ETC-2026-001",
          issueDate: "2026-02-27",
          passageStartDate: "2026-02-27",
          passageEndDate: "2026-02-27",
          plateNumber: "云ADA0381",
          sellerName: "云南高速通行费",
          buyerName: "云南溯源科技",
          amountWithoutTax: "12.34",
          taxAmount: "0.73",
          totalAmount: "13.07",
          status: "unsubmitted",
          hasPdf: true,
          hasXml: true,
        },
      ],
    } as const;
    vi.spyOn(etcApi, "fetchEtcBusinessBatches").mockResolvedValue({
      counts: { active: 1, submitted: 0 },
      items: [businessBatch],
      pagination: { page: 1, pageSize: 100, total: 1 },
    } as never);
    vi.spyOn(etcApi, "fetchEtcBusinessBatchDetail").mockResolvedValue(businessBatch as never);
    const createDraft = vi.spyOn(etcApi, "createEtcBusinessBatchOaDraft").mockResolvedValue({
      ...businessBatch,
      status: "oa_submission_detecting",
      version: 8,
      submissionBatchId: "etc_batch_0027",
      oaDraftId: "oa_draft_001",
      oaDraftUrl: "https://oa.example.test/oa/#/normal/forms/form/2?formId=2&id=oa_draft_001",
    } as never);
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await waitFor(() => expect(within(page).getAllByText("ETC-2026-03-A").length).toBeGreaterThanOrEqual(1));
    const submitButton = within(page).getByRole("button", { name: "提交OA" });
    await waitFor(() => expect(submitButton).toBeEnabled());
    await user.click(submitButton);

    const dialog = await screen.findByRole("dialog", { name: "创建OA草稿" });
    expect(dialog).toHaveTextContent("为当前任务的 2 张发票创建 OA 草稿");
    expect(dialog).toHaveTextContent("批次：ETC-2026-03-A");
    await user.click(within(dialog).getByRole("button", { name: "创建草稿" }));

    expect(openMock).toHaveBeenCalledWith("about:blank", "_blank");
    await waitFor(() => expect(openedWindow.location.href).toContain("https://oa.example.test/oa/#/normal/forms/form/2"));
    await waitFor(() => expect(createDraft).toHaveBeenCalledWith("etc_business_batch_0001", { expectedVersion: 7 }));

    const resultDialog = await screen.findByRole("dialog", { name: "OA自动检测" });
    expect(resultDialog).toHaveTextContent("OA草稿已创建，等待提交确认。");
    expect(within(resultDialog).getByRole("button", { name: "打开草稿" })).toBeEnabled();
    expect(within(resultDialog).getByRole("button", { name: "刷新检测" })).toBeEnabled();
    expect(within(resultDialog).getByRole("button", { name: "撤销草稿" })).toBeEnabled();
    expect(within(resultDialog).queryByRole("button", { name: "确认已提交OA" })).not.toBeInTheDocument();
    expect(within(resultDialog).queryByRole("button", { name: "未提交OA" })).not.toBeInTheDocument();
  });
});
