import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

function startStrictBrowserErrorCapture(page: Page, options: { allowedConsoleErrors?: RegExp[] } = {}) {
  const errors: string[] = [];
  page.on("pageerror", (error) => {
    errors.push(`pageerror: ${error.stack || error.message}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
      const text = message.text();
      if (options.allowedConsoleErrors?.some((pattern) => pattern.test(text))) {
        return;
      }
      errors.push(`console.error: ${text}`);
    }
  });
  page.on("requestfailed", (request) => {
    const failure = request.failure()?.errorText ?? "";
    if (failure === "net::ERR_ABORTED") {
      return;
    }
    errors.push(`requestfailed: ${request.method()} ${request.url()} ${failure}`.trim());
  });
  page.on("dialog", async (dialog) => {
    errors.push(`dialog: ${dialog.type()} ${dialog.message()}`);
    await dialog.dismiss().catch(() => undefined);
  });
  return errors;
}

function waitForEtcBusinessBatches(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET"
      && url.pathname === "/api/etc/business-batches";
  });
}

function waitForEtcBusinessBatchDelete(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "DELETE"
      && url.pathname === "/api/etc/business-batches/etc-business-e2e-001";
  });
}

function waitForEtcSourceFileDelete(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "DELETE"
      && url.pathname === "/api/etc/reconciliation-tasks/etc-recon-e2e-001/source-files/etc-source-e2e-001";
  });
}

function waitForEtcTicketRootUpload(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST"
      && url.pathname === "/api/etc/reconciliation-tasks/etc-recon-e2e-001/ticket-root-files";
  });
}

function createEtcLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/etc-tickets",
    pageKey: "etc-tickets",
    module: "etc-tickets",
  });
}

async function openEtcDisclosure(page: Page, name: RegExp | string) {
  const trigger = page.getByRole("button", { name });
  await expect(trigger).toBeVisible();
  if ((await trigger.getAttribute("aria-expanded")) !== "true") {
    await trigger.click();
  }
  return trigger;
}

test.describe("ETC ticket management browser flow", () => {
  test("downloads the merged invoice PDF after the OA draft exists", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    await installDeterministicApiMocks(page, {
      etcTicketInitialBusinessBatchStatus: "oa_confirmation_pending",
      sessionMode: "read_export_only",
    });
    await page.route("**/api/etc/business-batches/etc-business-e2e-001/invoice-pdf", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/pdf",
        headers: {
          "Content-Disposition": "attachment; filename*=UTF-8''ETC%E5%8F%91%E7%A5%A8_3%E6%9C%88%E6%89%B9%E6%AC%A1_2%E5%BC%A0.pdf",
        },
        body: "%PDF-1.4\n%%EOF\n",
      });
    });
    const recordLatency = createEtcLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "etc-tickets.download-merged-invoice-pdf",
      visibleLabel: "下载发票PDF",
      actionType: "click",
    }, async (mark) => {
      await page.goto("/etc-tickets");
      await page.getByRole("radio", { name: "暂存 1" }).click();
      const downloadButton = page.getByRole("button", { name: "下载发票PDF" });
      await mark("firstVisibleResponseLatencyMs", expect(downloadButton).toBeVisible());
      const downloadPromise = page.waitForEvent("download");
      await downloadButton.click();
      const download = await mark("finalSettledLatencyMs", downloadPromise);
      expect(download.suggestedFilename()).toBe("ETC发票_3月批次_2张.pdf");
    });

    await expect(page.getByText("当前账号仅支持查看和导出")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("recovers business batches after a transient load failure when refreshed", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketBusinessBatchesFailuresBeforeSuccess: 2,
      etcTicketWorkflowTaskMatchesBusinessBatch: true,
      sessionMode: "full_access",
    });
    const recordLatency = createEtcLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "etc-tickets.open-page-load-failure",
      visibleLabel: "ETC票据",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/etc-tickets");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("etc-ticket-management-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByText("ETC业务批次加载暂时失败，请刷新后重试。")).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "ETC票据" })).toBeVisible();
    await expect(page.getByText("ETC业务批次加载暂时失败，请刷新后重试。")).toBeVisible();
    await expect(page.getByText("无匹配批次。")).toHaveCount(0);

    let recovered = false;
    for (let attempt = 0; attempt < 4 && !recovered; attempt += 1) {
      await recordLatency({
        operationId: `etc-tickets.refresh-after-load-failure.${attempt + 1}`,
        visibleLabel: "刷新",
        actionType: "click",
      }, async (mark) => {
        const responsePromise = waitForEtcBusinessBatches(page);
        await page.getByRole("button", { name: /^刷新$/ }).click();
        const response = await mark("apiLatencyMs", responsePromise);
        recovered = response.status() === 200;
        if (recovered) {
          await mark("finalSettledLatencyMs", expect(page.getByTestId("etc-batch-row-etc-business-e2e-001")).toBeVisible());
        } else {
          await mark("firstVisibleResponseLatencyMs", expect(page.getByText("ETC业务批次加载暂时失败，请刷新后重试。")).toBeVisible());
        }
      });
    }
    expect(recovered).toBe(true);

    await expect(page.getByText("ETC业务批次加载暂时失败，请刷新后重试。")).toHaveCount(0);
    await expect(page.getByRole("radio", { name: "未提交 1" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "暂存 0" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "已提交 0" })).toBeVisible();
    const row = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(row).toBeVisible();
    await expect(row).toContainText("3月批次");
    await expect(page.getByLabel("车牌", { exact: true })).toHaveCount(0);
    await expect(page.getByLabel("关键词", { exact: true })).toHaveCount(0);
    const lifecycle = page.getByRole("list", { name: "批次生命周期" });
    await expect(lifecycle).toBeVisible();
    await expect(lifecycle.getByRole("listitem")).toHaveCount(4);
    await expect(lifecycle.getByText("准备核对资料", { exact: true })).toBeVisible();
    await expect(lifecycle.getByText("确认核对结果", { exact: true })).toBeVisible();
    await expect(lifecycle.getByText("导入 ETC 发票", { exact: true })).toBeVisible();
    await expect(lifecycle.getByText("提交 OA 审批", { exact: true })).toBeVisible();
    await expect(page.getByRole("table", { name: "ETC发票明细" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "ETC-E2E-001" })).toBeVisible();
    await expect(page.getByRole("button", { name: "提交审批" })).toBeEnabled();
    expect(api.count("GET /api/etc/business-batches")).toBeGreaterThanOrEqual(3);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps a business batch deletion recoverable after a transient failure", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketBusinessBatchDeleteFailuresBeforeSuccess: 1,
      sessionMode: "full_access",
    });
    const recordLatency = createEtcLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "etc-tickets.open-page-delete-unsubmitted",
      visibleLabel: "ETC票据",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/etc-tickets");
      await mark("finalSettledLatencyMs", expect(page.getByTestId("etc-ticket-management-page")).toBeVisible());
    });
    await expect(page.getByRole("radio", { name: "未提交 1" })).toHaveAttribute("aria-checked", "true");
    const row = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(row).toBeVisible();
    await expect(row).toContainText("3月批次");

    const deleteDialog = page.getByRole("dialog", { name: "删除批次" });
    await recordLatency({
      operationId: "etc-tickets.open-delete-unsubmitted-dialog",
      visibleLabel: "删除批次 3月批次",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "删除批次 3月批次" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(deleteDialog).toBeVisible());
      await mark("finalSettledLatencyMs", expect(deleteDialog).toContainText("3月批次"));
    });
    await expect(deleteDialog).toContainText("3月批次");

    await recordLatency({
      operationId: "etc-tickets.confirm-delete-unsubmitted-failed",
      visibleLabel: "确认删除",
      actionType: "click",
    }, async (mark) => {
      const failedDeleteResponse = waitForEtcBusinessBatchDelete(page);
      await deleteDialog.getByRole("button", { name: "确认删除" }).click();
      expect((await mark("apiLatencyMs", failedDeleteResponse)).status()).toBe(503);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("ETC业务批次删除暂时失败，请重试。")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "删除批次" })).toBeVisible());
    });
    expect(api.count("DELETE /api/etc/business-batches/etc-business-e2e-001")).toBe(1);
    await expect(page.getByText("ETC业务批次删除暂时失败，请重试。")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "删除批次" })).toBeVisible();
    await expect(row).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 1" })).toHaveAttribute("aria-checked", "true");

    await recordLatency({
      operationId: "etc-tickets.confirm-delete-unsubmitted-retry",
      visibleLabel: "确认删除",
      actionType: "click",
    }, async (mark) => {
      const recoveredDeleteResponse = waitForEtcBusinessBatchDelete(page);
      await deleteDialog.getByRole("button", { name: "确认删除" }).click();
      expect((await mark("apiLatencyMs", recoveredDeleteResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("etc-batch-row-etc-business-e2e-001")).toHaveCount(0));
    });
    expect(api.count("DELETE /api/etc/business-batches/etc-business-e2e-001")).toBe(2);

    await expect(page.getByText("ETC业务批次删除暂时失败，请重试。")).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "删除批次" })).toHaveCount(0);
    await expect(page.getByTestId("etc-batch-row-etc-business-e2e-001")).toHaveCount(0);
    await expect(page.getByRole("radio", { name: "未提交 0" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "暂存 0" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "已提交 0" })).toBeVisible();
    await expect(page.getByText("无匹配批次。")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps submitted batch reset deletion recoverable after a relation command failure", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketBusinessBatchDeleteFailuresBeforeSuccess: 1,
      etcTicketInitialBusinessBatchStatus: "manually_marked_submitted",
      sessionMode: "full_access",
    });
    const recordLatency = createEtcLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "etc-tickets.open-page-delete-submitted",
      visibleLabel: "ETC票据",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/etc-tickets");
      await mark("finalSettledLatencyMs", expect(page.getByTestId("etc-ticket-management-page")).toBeVisible());
    });
    await expect(page.getByRole("radio", { name: "未提交 0" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "暂存 0" })).toBeVisible();
    await recordLatency({
      operationId: "etc-tickets.open-submitted-bucket",
      visibleLabel: "已提交 1",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("radio", { name: "已提交 1" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true"));
    });
    await expect(page.getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true");

    const row = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(row).toBeVisible();
    await expect(row).toContainText("3月批次");
    await expect(row).toContainText("人工确认已提交");

    const deleteDialog = page.getByRole("dialog", { name: "删除批次" });
    await recordLatency({
      operationId: "etc-tickets.open-delete-submitted-dialog",
      visibleLabel: "删除批次 3月批次",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "删除批次 3月批次" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(deleteDialog).toBeVisible());
      await mark("finalSettledLatencyMs", expect(deleteDialog).toContainText("取消发票合并"));
    });
    await expect(deleteDialog).toContainText("取消发票合并");
    await expect(deleteDialog).toContainText("审批系统中的草稿和已提交记录不会删除");

    await recordLatency({
      operationId: "etc-tickets.confirm-delete-submitted-failed",
      visibleLabel: "确认删除",
      actionType: "click",
    }, async (mark) => {
      const failedDeleteResponse = waitForEtcBusinessBatchDelete(page);
      await deleteDialog.getByRole("button", { name: "确认删除" }).click();
      expect((await mark("apiLatencyMs", failedDeleteResponse)).status()).toBe(503);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("ETC业务批次删除暂时失败，请重试。")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "删除批次" })).toBeVisible());
    });
    expect(api.count("DELETE /api/etc/business-batches/etc-business-e2e-001")).toBe(1);
    expect(api.lastBody("DELETE /api/etc/business-batches/etc-business-e2e-001")).toMatchObject({
      expectedVersion: 9,
      reason: "用户在 ETC 页面删除已提交业务批次并释放发票。",
    });
    await expect(page.getByText("ETC业务批次删除暂时失败，请重试。")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "删除批次" })).toBeVisible();
    await expect(row).toBeVisible();
    await expect(page.getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "暂存 0" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 0" })).toBeVisible();

    await expect(deleteDialog.getByRole("button", { name: "确认删除" })).toBeEnabled();
    await recordLatency({
      operationId: "etc-tickets.confirm-delete-submitted-retry",
      visibleLabel: "确认删除",
      actionType: "click",
    }, async (mark) => {
      const recoveredDeleteResponse = waitForEtcBusinessBatchDelete(page);
      await deleteDialog.getByRole("button", { name: "确认删除" }).click();
      expect((await mark("apiLatencyMs", recoveredDeleteResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("etc-batch-row-etc-business-e2e-001")).toHaveCount(0));
    });
    expect(api.count("DELETE /api/etc/business-batches/etc-business-e2e-001")).toBe(2);

    await expect(page.getByText("ETC业务批次删除暂时失败，请重试。")).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "删除批次" })).toHaveCount(0);
    await expect(page.getByTestId("etc-batch-row-etc-business-e2e-001")).toHaveCount(0);
    await expect(page.getByRole("radio", { name: "已提交 0" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "暂存 0" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 0" })).toBeVisible();
    await expect(page.getByText("无匹配批次。")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps source file deletion recoverable after a transient failure", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketReconciliationWorkflow: true,
      etcTicketSourceFileDeleteFailuresBeforeSuccess: 1,
      etcTicketWorkflowTaskMatchesBusinessBatch: true,
      sessionMode: "full_access",
    });
    const recordLatency = createEtcLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "etc-tickets.open-page-source-file-delete",
      visibleLabel: "ETC票据",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/etc-tickets");
      await mark("finalSettledLatencyMs", expect(page.getByTestId("etc-ticket-management-page")).toBeVisible());
    });
    await expect(page.getByTestId("etc-batch-row-etc-business-e2e-001")).toBeVisible();
    await recordLatency({
      operationId: "etc-tickets.expand-source-files",
      visibleLabel: "已上传文件",
      actionType: "click",
    }, async (mark) => {
      await openEtcDisclosure(page, /已上传文件/);
      await mark("finalSettledLatencyMs", expect(page.getByRole("list", { name: "已上传文件列表" })).toBeVisible());
    });
    const sourceFileList = page.getByRole("list", { name: "已上传文件列表" });
    await expect(sourceFileList).toBeVisible();
    await expect(sourceFileList.getByText("ccb-statement.pdf")).toBeVisible();

    const deleteDialog = page.getByRole("dialog", { name: "删除源文件" });
    await recordLatency({
      operationId: "etc-tickets.open-source-file-delete-dialog",
      visibleLabel: "删除源文件 ccb-statement.pdf",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "删除源文件 ccb-statement.pdf" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(deleteDialog).toBeVisible());
      await mark("finalSettledLatencyMs", expect(deleteDialog).toContainText("ccb-statement.pdf"));
    });
    await expect(deleteDialog).toContainText("ccb-statement.pdf");

    await recordLatency({
      operationId: "etc-tickets.confirm-source-file-delete-failed",
      visibleLabel: "确认删除",
      actionType: "click",
    }, async (mark) => {
      const failedDeleteResponse = waitForEtcSourceFileDelete(page);
      await deleteDialog.getByRole("button", { name: "确认删除" }).click();
      expect((await mark("apiLatencyMs", failedDeleteResponse)).status()).toBe(503);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("ETC源文件删除暂时失败，请重试。")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "删除源文件" })).toBeVisible());
    });
    expect(api.count("DELETE /api/etc/reconciliation-tasks/etc-recon-e2e-001/source-files/etc-source-e2e-001")).toBe(1);
    await expect(page.getByText("ETC源文件删除暂时失败，请重试。")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "删除源文件" })).toBeVisible();
    await expect(sourceFileList.getByText("ccb-statement.pdf")).toBeVisible();

    await recordLatency({
      operationId: "etc-tickets.confirm-source-file-delete-retry",
      visibleLabel: "确认删除",
      actionType: "click",
    }, async (mark) => {
      const recoveredDeleteResponse = waitForEtcSourceFileDelete(page);
      await deleteDialog.getByRole("button", { name: "确认删除" }).click();
      expect((await mark("apiLatencyMs", recoveredDeleteResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(sourceFileList.getByText("ccb-statement.pdf")).toHaveCount(0));
    });
    expect(api.count("DELETE /api/etc/reconciliation-tasks/etc-recon-e2e-001/source-files/etc-source-e2e-001")).toBe(2);

    await expect(page.getByText("ETC源文件删除暂时失败，请重试。")).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "删除源文件" })).toHaveCount(0);
    await expect(sourceFileList.getByText("ccb-statement.pdf")).toHaveCount(0);
    await expect(page.getByText("暂无文件。")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps ticket-root source upload recoverable after a transient failure", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketReconciliationWorkflow: true,
      etcTicketSourceFileUploadFailuresBeforeSuccess: 1,
      etcTicketWorkflowTaskMatchesBusinessBatch: true,
      sessionMode: "full_access",
    });
    const recordLatency = createEtcLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "etc-tickets.open-page-ticket-root-upload",
      visibleLabel: "ETC票据",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/etc-tickets");
      await mark("finalSettledLatencyMs", expect(page.getByTestId("etc-ticket-management-page")).toBeVisible());
    });
    await expect(page.getByTestId("etc-batch-row-etc-business-e2e-001")).toBeVisible();
    await recordLatency({
      operationId: "etc-tickets.expand-upload-files",
      visibleLabel: "上传文件",
      actionType: "click",
    }, async (mark) => {
      await openEtcDisclosure(page, /^上传文件\s/);
      await mark("finalSettledLatencyMs", expect(page.getByLabel("上传票根网")).toBeVisible());
    });
    await recordLatency({
      operationId: "etc-tickets.expand-uploaded-files",
      visibleLabel: "已上传文件",
      actionType: "click",
    }, async (mark) => {
      await openEtcDisclosure(page, /已上传文件/);
      await mark("finalSettledLatencyMs", expect(page.getByRole("list", { name: "已上传文件列表" })).toBeVisible());
    });
    const sourceFileList = page.getByRole("list", { name: "已上传文件列表" });
    await expect(sourceFileList.getByText("ccb-statement.pdf")).toBeVisible();
    await expect(sourceFileList.getByText("ticket-root-upload.txt")).toHaveCount(0);

    const ticketRootInput = page.locator('label[aria-label="上传票根网"] input[type="file"]');
    await expect(page.getByLabel("上传票根网")).toBeVisible();

    await recordLatency({
      operationId: "etc-tickets.upload-ticket-root-failed",
      visibleLabel: "上传票根网",
      actionType: "upload",
    }, async (mark) => {
      const failedUploadResponse = waitForEtcTicketRootUpload(page);
      await ticketRootInput.setInputFiles({
        name: "ticket-root-upload.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("车牌号：云ADA0381\n交易时间：2026-03-27 10:20:00\n交易金额：95.00"),
      });
      expect((await mark("apiLatencyMs", failedUploadResponse)).status()).toBe(503);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("ETC票根网文件上传暂时失败，请重试。")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(sourceFileList.getByText("ticket-root-upload.txt")).toHaveCount(0));
    });
    expect(api.count("POST /api/etc/reconciliation-tasks/etc-recon-e2e-001/ticket-root-files")).toBe(1);
    await expect(page.getByText("ETC票根网文件上传暂时失败，请重试。")).toBeVisible();
    await expect(sourceFileList.getByText("ccb-statement.pdf")).toBeVisible();
    await expect(sourceFileList.getByText("ticket-root-upload.txt")).toHaveCount(0);
    await expect(page.getByLabel("上传票根网")).not.toHaveAttribute("aria-disabled", "true");

    await recordLatency({
      operationId: "etc-tickets.upload-ticket-root-retry",
      visibleLabel: "上传票根网",
      actionType: "upload",
    }, async (mark) => {
      const recoveredUploadResponse = waitForEtcTicketRootUpload(page);
      await ticketRootInput.setInputFiles({
        name: "ticket-root-upload.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("车牌号：云ADA0381\n交易时间：2026-03-27 10:20:00\n交易金额：95.00"),
      });
      expect((await mark("apiLatencyMs", recoveredUploadResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(sourceFileList.getByText("ticket-root-upload.txt")).toBeVisible());
    });
    expect(api.count("POST /api/etc/reconciliation-tasks/etc-recon-e2e-001/ticket-root-files")).toBe(2);

    await expect(page.getByText("ETC票根网文件上传暂时失败，请重试。")).toHaveCount(0);
    await expect(sourceFileList.getByText("ccb-statement.pdf")).toBeVisible();
    await expect(sourceFileList.getByText("ticket-root-upload.txt")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps the OA draft dialog recoverable after a transient draft creation failure", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketOaDraftFailuresBeforeSuccess: 1,
      etcTicketWorkflowTaskMatchesBusinessBatch: true,
      sessionMode: "full_access",
    });
    const recordLatency = createEtcLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "etc-tickets.open-page-oa-draft-failure",
      visibleLabel: "ETC票据",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/etc-tickets");
      await mark("finalSettledLatencyMs", expect(page.getByTestId("etc-ticket-management-page")).toBeVisible());
    });
    const row = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(row).toBeVisible();
    await expect(page.getByRole("button", { name: "提交审批" })).toBeEnabled();

    const createDialog = page.getByRole("dialog", { name: "创建审批草稿" });
    await recordLatency({
      operationId: "etc-tickets.open-oa-draft-dialog",
      visibleLabel: "提交审批",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "提交审批" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(createDialog).toBeVisible());
      await mark("finalSettledLatencyMs", expect(createDialog.getByText(/OA 草稿金额：120\.00 元/)).toBeVisible());
    });
    await expect(createDialog.getByText(/OA 草稿金额：120\.00 元/)).toBeVisible();

    await recordLatency({
      operationId: "etc-tickets.create-oa-draft-failed",
      visibleLabel: "创建草稿",
      actionType: "click",
    }, async (mark) => {
      const failedDraftResponse = page.waitForResponse((response) =>
        response.url().includes("/api/etc/business-batches/etc-business-e2e-001/oa-draft")
          && response.request().method() === "POST",
      );
      await createDialog.getByRole("button", { name: "创建草稿" }).click();
      expect((await mark("apiLatencyMs", failedDraftResponse)).status()).toBe(503);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("审批草稿创建暂时失败，请重试。")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "创建审批草稿" })).toBeVisible());
    });
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/oa-draft")).toBe(1);
    await expect(page.getByText("审批草稿创建暂时失败，请重试。")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "创建审批草稿" })).toBeVisible();
    await expect(page.getByRole("dialog", { name: "确认 OA 草稿处理结果" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "提交审批" })).toBeEnabled();

    await recordLatency({
      operationId: "etc-tickets.create-oa-draft-retry",
      visibleLabel: "创建草稿",
      actionType: "click",
    }, async (mark) => {
      const recoveredDraftResponse = page.waitForResponse((response) =>
        response.url().includes("/api/etc/business-batches/etc-business-e2e-001/oa-draft")
          && response.request().method() === "POST",
      );
      await createDialog.getByRole("button", { name: "创建草稿" }).click();
      expect((await mark("apiLatencyMs", recoveredDraftResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "确认 OA 草稿处理结果" })).toBeVisible());
    });
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/oa-draft")).toBe(2);

    const resultDialog = page.getByRole("dialog", { name: "确认 OA 草稿处理结果" });
    await expect(resultDialog).toBeVisible();
    await expect(resultDialog.getByText("OA 草稿已创建。请根据你在 OA 系统中的实际操作选择结果。")).toBeVisible();
    await expect(page.getByText("审批草稿创建暂时失败，请重试。")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps the manual OA status confirmation recoverable after a transient failure", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketManualStatusFailuresBeforeSuccess: 1,
      etcTicketWorkflowTaskMatchesBusinessBatch: true,
      sessionMode: "full_access",
    });
    const recordLatency = createEtcLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "etc-tickets.open-page-manual-status-failure",
      visibleLabel: "ETC票据",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/etc-tickets");
      await mark("finalSettledLatencyMs", expect(page.getByTestId("etc-ticket-management-page")).toBeVisible());
    });
    await expect(page.getByRole("button", { name: "提交审批" })).toBeEnabled();

    const createDialog = page.getByRole("dialog", { name: "创建审批草稿" });
    await recordLatency({
      operationId: "etc-tickets.open-oa-draft-dialog-before-manual-status",
      visibleLabel: "提交审批",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "提交审批" }).click();
      await mark("finalSettledLatencyMs", expect(createDialog).toBeVisible());
    });
    const draftResponse = page.waitForResponse((response) =>
      response.url().includes("/api/etc/business-batches/etc-business-e2e-001/oa-draft")
        && response.request().method() === "POST",
    );
    await recordLatency({
      operationId: "etc-tickets.create-oa-draft-before-manual-status",
      visibleLabel: "创建草稿",
      actionType: "click",
    }, async (mark) => {
      await createDialog.getByRole("button", { name: "创建草稿" }).click();
      expect((await mark("apiLatencyMs", draftResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "确认 OA 草稿处理结果" })).toBeVisible());
    });

    const resultDialog = page.getByRole("dialog", { name: "确认 OA 草稿处理结果" });
    await expect(resultDialog).toBeVisible();
    await expect(resultDialog.getByText("OA 草稿已创建。请根据你在 OA 系统中的实际操作选择结果。")).toBeVisible();

    await recordLatency({
      operationId: "etc-tickets.manual-status-submitted-failed",
      visibleLabel: "我已在 OA 系统上完成 OA 草稿的提交",
      actionType: "click",
    }, async (mark) => {
      const failedManualStatusResponse = page.waitForResponse((response) =>
        response.url().includes("/api/etc/business-batches/etc-business-e2e-001/manual-oa-status")
          && response.request().method() === "POST",
      );
      await resultDialog.getByRole("button", { name: "我已在 OA 系统上完成 OA 草稿的提交" }).click();
      expect((await mark("apiLatencyMs", failedManualStatusResponse)).status()).toBe(503);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("人工确认暂时失败，请重试。")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "确认 OA 草稿处理结果" })).toBeVisible());
    });
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/manual-oa-status")).toBe(1);
    await expect(page.getByText("人工确认暂时失败，请重试。")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "确认 OA 草稿处理结果" })).toBeVisible();
    await expect(resultDialog.getByRole("button", { name: "我已在 OA 系统上完成 OA 草稿的提交" })).toBeEnabled();
    await expect(resultDialog.getByRole("button", { name: "我已在 OA 系统上删除该 OA 草稿" })).toBeEnabled();
    await expect(page.getByRole("radio", { name: "未提交 0" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "暂存 1" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "已提交 0" })).toBeVisible();

    await recordLatency({
      operationId: "etc-tickets.manual-status-submitted-retry",
      visibleLabel: "我已在 OA 系统上完成 OA 草稿的提交",
      actionType: "click",
    }, async (mark) => {
      const recoveredManualStatusResponse = page.waitForResponse((response) =>
        response.url().includes("/api/etc/business-batches/etc-business-e2e-001/manual-oa-status")
          && response.request().method() === "POST",
      );
      await resultDialog.getByRole("button", { name: "我已在 OA 系统上完成 OA 草稿的提交" }).click();
      expect((await mark("apiLatencyMs", recoveredManualStatusResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true"));
    });
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/manual-oa-status")).toBe(2);

    await expect(page.getByText("人工确认暂时失败，请重试。")).toHaveCount(0);
    await expect(page.getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true");
    const submittedRow = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(submittedRow).toBeVisible();
    await expect(submittedRow).toContainText("人工确认已提交");
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("creates an OA draft for an imported ETC batch and moves it to submitted history", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      etcTicketWorkflowTaskMatchesBusinessBatch: true,
      sessionMode: "full_access",
    });
    const recordLatency = createEtcLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "etc-tickets.open-page-oa-happy-path",
      visibleLabel: "ETC票据",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/etc-tickets");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("etc-ticket-management-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "ETC票据" })).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "ETC票据" })).toBeVisible();
    await expect(page.getByRole("radiogroup", { name: "ETC批次状态" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 1" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "暂存 0" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "已提交 0" })).toBeVisible();

    const row = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(row).toBeVisible();
    await expect(row).toContainText("3月批次");
    await expect(row).toContainText("发票 2");
    await expect(page.getByRole("table", { name: "ETC发票明细" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "ETC-E2E-001" })).toBeVisible();

    const submitButton = page.getByRole("button", { name: "提交审批" });
    await expect(submitButton).toBeEnabled();

    const createDialog = page.getByRole("dialog", { name: "创建审批草稿" });
    await recordLatency({
      operationId: "etc-tickets.open-oa-draft-dialog-happy-path",
      visibleLabel: "提交审批",
      actionType: "click",
    }, async (mark) => {
      await submitButton.click();
      await mark("firstVisibleResponseLatencyMs", expect(createDialog).toBeVisible());
      await mark("finalSettledLatencyMs", expect(createDialog.getByText(/OA 草稿金额：120\.00 元/)).toBeVisible());
    });
    await expect(createDialog.getByText(/OA 草稿金额：120\.00 元/)).toBeVisible();
    await expect(createDialog.getByText("已导入 ETC 发票：2 张 / 32.26 元")).toBeVisible();
    await expect(createDialog.getByText("两者相差 87.74 元；OA 草稿仍按对账任务金额创建。")).toBeVisible();
    await expect(createDialog.getByText("批次：3月批次")).toBeVisible();

    const draftResponse = page.waitForResponse((response) =>
      response.url().includes("/api/etc/business-batches/etc-business-e2e-001/oa-draft")
        && response.request().method() === "POST",
    );
    await recordLatency({
      operationId: "etc-tickets.create-oa-draft-happy-path",
      visibleLabel: "创建草稿",
      actionType: "click",
    }, async (mark) => {
      await createDialog.getByRole("button", { name: "创建草稿" }).click();
      expect((await mark("apiLatencyMs", draftResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "确认 OA 草稿处理结果" })).toBeVisible());
    });
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/oa-draft")).toBe(1);

    const resultDialog = page.getByRole("dialog", { name: "确认 OA 草稿处理结果" });
    await expect(resultDialog).toBeVisible();
    await expect(resultDialog.getByText("OA 草稿已创建。请根据你在 OA 系统中的实际操作选择结果。")).toBeVisible();
    await expect(resultDialog.getByRole("button", { name: "打开草稿" })).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    const manualStatusResponse = page.waitForResponse((response) =>
      response.url().includes("/api/etc/business-batches/etc-business-e2e-001/manual-oa-status")
        && response.request().method() === "POST",
    );
    await recordLatency({
      operationId: "etc-tickets.manual-status-submitted-happy-path",
      visibleLabel: "我已在 OA 系统上完成 OA 草稿的提交",
      actionType: "click",
    }, async (mark) => {
      await resultDialog.getByRole("button", { name: "我已在 OA 系统上完成 OA 草稿的提交" }).click();
      expect((await mark("apiLatencyMs", manualStatusResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true"));
    });
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/manual-oa-status")).toBe(1);

    await expect(page.getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("button", { name: "提交审批" })).toHaveCount(0);
    const submittedRow = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(submittedRow).toBeVisible();
    await expect(submittedRow).toContainText("人工确认已提交");
    await expect(submittedRow).toContainText("3月批次");
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });
});
