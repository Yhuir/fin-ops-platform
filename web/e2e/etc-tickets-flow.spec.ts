import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
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

async function openEtcDisclosure(page: Page, name: RegExp | string) {
  const trigger = page.getByRole("button", { name });
  await expect(trigger).toBeVisible();
  if ((await trigger.getAttribute("aria-expanded")) !== "true") {
    await trigger.click();
  }
  return trigger;
}

test.describe("ETC ticket management browser flow", () => {
  test("recovers business batches after a transient load failure when refreshed", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketBusinessBatchesFailuresBeforeSuccess: 2,
      sessionMode: "full_access",
    });

    await page.goto("/etc-tickets");
    await expect(page.getByTestId("etc-ticket-management-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "ETC票据" })).toBeVisible();
    await expect(page.getByText("ETC业务批次加载暂时失败，请刷新后重试。")).toBeVisible();
    await expect(page.getByText("无匹配批次。")).toHaveCount(0);

    let recovered = false;
    for (let attempt = 0; attempt < 4 && !recovered; attempt += 1) {
      const responsePromise = waitForEtcBusinessBatches(page);
      await page.getByRole("button", { name: /^刷新$/ }).click();
      const response = await responsePromise;
      recovered = response.status() === 200;
    }
    expect(recovered).toBe(true);

    await expect(page.getByText("ETC业务批次加载暂时失败，请刷新后重试。")).toHaveCount(0);
    await expect(page.getByRole("radio", { name: "未提交 1" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "已提交 0" })).toBeVisible();
    const row = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(row).toBeVisible();
    await expect(row).toContainText("ETC-E2E-2026-03");
    await expect(page.getByRole("table", { name: "ETC发票明细" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "ETC-E2E-001" })).toBeVisible();
    await expect(page.getByRole("button", { name: "提交OA" })).toBeEnabled();
    expect(api.count("GET /api/etc/business-batches")).toBeGreaterThanOrEqual(3);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps a business batch deletion recoverable after a transient failure", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketBusinessBatchDeleteFailuresBeforeSuccess: 1,
      sessionMode: "full_access",
    });

    await page.goto("/etc-tickets");
    await expect(page.getByTestId("etc-ticket-management-page")).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 1" })).toHaveAttribute("aria-checked", "true");
    const row = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(row).toBeVisible();
    await expect(row).toContainText("ETC-E2E-2026-03");

    await row.getByRole("button", { name: "删除批次 ETC-E2E-2026-03" }).click();
    const deleteDialog = page.getByRole("dialog", { name: "删除批次" });
    await expect(deleteDialog).toBeVisible();
    await expect(deleteDialog).toContainText("ETC-E2E-2026-03");

    const failedDeleteResponse = waitForEtcBusinessBatchDelete(page);
    await deleteDialog.getByRole("button", { name: "确认删除" }).click();
    expect((await failedDeleteResponse).status()).toBe(503);
    expect(api.count("DELETE /api/etc/business-batches/etc-business-e2e-001")).toBe(1);
    await expect(page.getByText("ETC业务批次删除暂时失败，请重试。")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "删除批次" })).toBeVisible();
    await expect(row).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 1" })).toHaveAttribute("aria-checked", "true");

    const recoveredDeleteResponse = waitForEtcBusinessBatchDelete(page);
    await deleteDialog.getByRole("button", { name: "确认删除" }).click();
    expect((await recoveredDeleteResponse).status()).toBe(200);
    expect(api.count("DELETE /api/etc/business-batches/etc-business-e2e-001")).toBe(2);

    await expect(page.getByText("ETC业务批次删除暂时失败，请重试。")).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "删除批次" })).toHaveCount(0);
    await expect(page.getByTestId("etc-batch-row-etc-business-e2e-001")).toHaveCount(0);
    await expect(page.getByRole("radio", { name: "未提交 0" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "已提交 0" })).toBeVisible();
    await expect(page.getByText("无匹配批次。")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps submitted batch reset deletion recoverable after a relation command failure", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketBusinessBatchDeleteFailuresBeforeSuccess: 1,
      etcTicketInitialBusinessBatchStatus: "manually_marked_submitted",
      sessionMode: "full_access",
    });

    await page.goto("/etc-tickets");
    await expect(page.getByTestId("etc-ticket-management-page")).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 0" })).toHaveAttribute("aria-checked", "true");
    await page.getByRole("radio", { name: "已提交 1" }).click();
    await expect(page.getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true");

    const row = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(row).toBeVisible();
    await expect(row).toContainText("ETC-E2E-2026-03");
    await expect(row).toContainText("人工确认已提交");

    await row.getByRole("button", { name: "删除批次 ETC-E2E-2026-03" }).click();
    const deleteDialog = page.getByRole("dialog", { name: "删除批次" });
    await expect(deleteDialog).toBeVisible();
    await expect(deleteDialog).toContainText("取消发票合并");
    await expect(deleteDialog).toContainText("OA 系统中的草稿和已提交记录不会删除");

    const failedDeleteResponse = waitForEtcBusinessBatchDelete(page);
    await deleteDialog.getByRole("button", { name: "确认删除" }).click();
    expect((await failedDeleteResponse).status()).toBe(503);
    expect(api.count("DELETE /api/etc/business-batches/etc-business-e2e-001")).toBe(1);
    expect(api.lastBody("DELETE /api/etc/business-batches/etc-business-e2e-001")).toMatchObject({
      expectedVersion: 9,
      reason: "用户在 ETC 页面删除已提交业务批次并释放发票。",
    });
    await expect(page.getByText("ETC业务批次删除暂时失败，请重试。")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "删除批次" })).toBeVisible();
    await expect(row).toBeVisible();
    await expect(page.getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "未提交 0" })).toBeVisible();

    const recoveredDeleteResponse = waitForEtcBusinessBatchDelete(page);
    await expect(deleteDialog.getByRole("button", { name: "确认删除" })).toBeEnabled();
    await deleteDialog.getByRole("button", { name: "确认删除" }).click();
    expect((await recoveredDeleteResponse).status()).toBe(200);
    expect(api.count("DELETE /api/etc/business-batches/etc-business-e2e-001")).toBe(2);

    await expect(page.getByText("ETC业务批次删除暂时失败，请重试。")).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "删除批次" })).toHaveCount(0);
    await expect(page.getByTestId("etc-batch-row-etc-business-e2e-001")).toHaveCount(0);
    await expect(page.getByRole("radio", { name: "已提交 0" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "未提交 0" })).toBeVisible();
    await expect(page.getByText("无匹配批次。")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps source file deletion recoverable after a transient failure", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketReconciliationWorkflow: true,
      etcTicketSourceFileDeleteFailuresBeforeSuccess: 1,
      etcTicketWorkflowTaskMatchesBusinessBatch: true,
      sessionMode: "full_access",
    });

    await page.goto("/etc-tickets");
    await expect(page.getByTestId("etc-ticket-management-page")).toBeVisible();
    await expect(page.getByTestId("etc-batch-row-etc-business-e2e-001")).toBeVisible();
    await openEtcDisclosure(page, /已上传文件/);
    const sourceFileList = page.getByRole("list", { name: "已上传文件列表" });
    await expect(sourceFileList).toBeVisible();
    await expect(sourceFileList.getByText("ccb-statement.pdf")).toBeVisible();

    await page.getByRole("button", { name: "删除源文件 ccb-statement.pdf" }).click();
    const deleteDialog = page.getByRole("dialog", { name: "删除源文件" });
    await expect(deleteDialog).toBeVisible();
    await expect(deleteDialog).toContainText("ccb-statement.pdf");

    const failedDeleteResponse = waitForEtcSourceFileDelete(page);
    await deleteDialog.getByRole("button", { name: "确认删除" }).click();
    expect((await failedDeleteResponse).status()).toBe(503);
    expect(api.count("DELETE /api/etc/reconciliation-tasks/etc-recon-e2e-001/source-files/etc-source-e2e-001")).toBe(1);
    await expect(page.getByText("ETC源文件删除暂时失败，请重试。")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "删除源文件" })).toBeVisible();
    await expect(sourceFileList.getByText("ccb-statement.pdf")).toBeVisible();

    const recoveredDeleteResponse = waitForEtcSourceFileDelete(page);
    await deleteDialog.getByRole("button", { name: "确认删除" }).click();
    expect((await recoveredDeleteResponse).status()).toBe(200);
    expect(api.count("DELETE /api/etc/reconciliation-tasks/etc-recon-e2e-001/source-files/etc-source-e2e-001")).toBe(2);

    await expect(page.getByText("ETC源文件删除暂时失败，请重试。")).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "删除源文件" })).toHaveCount(0);
    await expect(sourceFileList.getByText("ccb-statement.pdf")).toHaveCount(0);
    await expect(page.getByText("暂无文件。")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps ticket-root source upload recoverable after a transient failure", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketReconciliationWorkflow: true,
      etcTicketSourceFileUploadFailuresBeforeSuccess: 1,
      etcTicketWorkflowTaskMatchesBusinessBatch: true,
      sessionMode: "full_access",
    });

    await page.goto("/etc-tickets");
    await expect(page.getByTestId("etc-ticket-management-page")).toBeVisible();
    await expect(page.getByTestId("etc-batch-row-etc-business-e2e-001")).toBeVisible();
    await openEtcDisclosure(page, /^上传文件\s/);
    await openEtcDisclosure(page, /已上传文件/);
    const sourceFileList = page.getByRole("list", { name: "已上传文件列表" });
    await expect(sourceFileList.getByText("ccb-statement.pdf")).toBeVisible();
    await expect(sourceFileList.getByText("ticket-root-upload.txt")).toHaveCount(0);

    const ticketRootInput = page.locator('label[aria-label="上传票根网"] input[type="file"]');
    await expect(page.getByLabel("上传票根网")).toBeVisible();

    const failedUploadResponse = waitForEtcTicketRootUpload(page);
    await ticketRootInput.setInputFiles({
      name: "ticket-root-upload.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("车牌号：云ADA0381\n交易时间：2026-03-27 10:20:00\n交易金额：95.00"),
    });
    expect((await failedUploadResponse).status()).toBe(503);
    expect(api.count("POST /api/etc/reconciliation-tasks/etc-recon-e2e-001/ticket-root-files")).toBe(1);
    await expect(page.getByText("ETC票根网文件上传暂时失败，请重试。")).toBeVisible();
    await expect(sourceFileList.getByText("ccb-statement.pdf")).toBeVisible();
    await expect(sourceFileList.getByText("ticket-root-upload.txt")).toHaveCount(0);
    await expect(page.getByLabel("上传票根网")).not.toHaveAttribute("aria-disabled", "true");

    const recoveredUploadResponse = waitForEtcTicketRootUpload(page);
    await ticketRootInput.setInputFiles({
      name: "ticket-root-upload.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("车牌号：云ADA0381\n交易时间：2026-03-27 10:20:00\n交易金额：95.00"),
    });
    expect((await recoveredUploadResponse).status()).toBe(200);
    expect(api.count("POST /api/etc/reconciliation-tasks/etc-recon-e2e-001/ticket-root-files")).toBe(2);

    await expect(page.getByText("ETC票根网文件上传暂时失败，请重试。")).toHaveCount(0);
    await expect(sourceFileList.getByText("ccb-statement.pdf")).toBeVisible();
    await expect(sourceFileList.getByText("ticket-root-upload.txt")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps the OA draft dialog recoverable after a transient draft creation failure", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketOaDraftFailuresBeforeSuccess: 1,
      sessionMode: "full_access",
    });

    await page.goto("/etc-tickets");
    await expect(page.getByTestId("etc-ticket-management-page")).toBeVisible();
    const row = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(row).toBeVisible();
    await expect(page.getByRole("button", { name: "提交OA" })).toBeEnabled();

    await page.getByRole("button", { name: "提交OA" }).click();
    const createDialog = page.getByRole("dialog", { name: "创建OA草稿" });
    await expect(createDialog).toBeVisible();
    await expect(createDialog.getByText("为当前批次创建 OA 草稿。")).toBeVisible();

    const failedDraftResponse = page.waitForResponse((response) =>
      response.url().includes("/api/etc/business-batches/etc-business-e2e-001/oa-draft")
        && response.request().method() === "POST",
    );
    await createDialog.getByRole("button", { name: "创建草稿" }).click();
    expect((await failedDraftResponse).status()).toBe(503);
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/oa-draft")).toBe(1);
    await expect(page.getByText("OA 草稿创建暂时失败，请重试。")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "创建OA草稿" })).toBeVisible();
    await expect(page.getByRole("dialog", { name: "OA提交确认" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "提交OA" })).toBeEnabled();

    const recoveredDraftResponse = page.waitForResponse((response) =>
      response.url().includes("/api/etc/business-batches/etc-business-e2e-001/oa-draft")
        && response.request().method() === "POST",
    );
    await createDialog.getByRole("button", { name: "创建草稿" }).click();
    expect((await recoveredDraftResponse).status()).toBe(200);
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/oa-draft")).toBe(2);

    const resultDialog = page.getByRole("dialog", { name: "OA提交确认" });
    await expect(resultDialog).toBeVisible();
    await expect(resultDialog.getByText("OA草稿已创建，等待提交确认。")).toBeVisible();
    await expect(page.getByText("OA 草稿创建暂时失败，请重试。")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps the manual OA status confirmation recoverable after a transient failure", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketManualStatusFailuresBeforeSuccess: 1,
      sessionMode: "full_access",
    });

    await page.goto("/etc-tickets");
    await expect(page.getByTestId("etc-ticket-management-page")).toBeVisible();
    await expect(page.getByRole("button", { name: "提交OA" })).toBeEnabled();
    await page.getByRole("button", { name: "提交OA" }).click();

    const createDialog = page.getByRole("dialog", { name: "创建OA草稿" });
    await expect(createDialog).toBeVisible();
    const draftResponse = page.waitForResponse((response) =>
      response.url().includes("/api/etc/business-batches/etc-business-e2e-001/oa-draft")
        && response.request().method() === "POST",
    );
    await createDialog.getByRole("button", { name: "创建草稿" }).click();
    expect((await draftResponse).status()).toBe(200);

    const resultDialog = page.getByRole("dialog", { name: "OA提交确认" });
    await expect(resultDialog).toBeVisible();
    await expect(resultDialog.getByText("OA草稿已创建，等待提交确认。")).toBeVisible();

    const failedManualStatusResponse = page.waitForResponse((response) =>
      response.url().includes("/api/etc/business-batches/etc-business-e2e-001/manual-oa-status")
        && response.request().method() === "POST",
    );
    await resultDialog.getByRole("button", { name: "已提交" }).click();
    expect((await failedManualStatusResponse).status()).toBe(503);
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/manual-oa-status")).toBe(1);
    await expect(page.getByText("人工确认暂时失败，请重试。")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "OA提交确认" })).toBeVisible();
    await expect(resultDialog.getByRole("button", { name: "已提交" })).toBeEnabled();
    await expect(resultDialog.getByRole("button", { name: "未提交" })).toBeEnabled();
    await expect(page.getByRole("radio", { name: "未提交 1" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "已提交 0" })).toBeVisible();

    const recoveredManualStatusResponse = page.waitForResponse((response) =>
      response.url().includes("/api/etc/business-batches/etc-business-e2e-001/manual-oa-status")
        && response.request().method() === "POST",
    );
    await resultDialog.getByRole("button", { name: "已提交" }).click();
    expect((await recoveredManualStatusResponse).status()).toBe(200);
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/manual-oa-status")).toBe(2);

    await expect(page.getByText("人工确认暂时失败，请重试。")).toHaveCount(0);
    await expect(page.getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true");
    const submittedRow = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(submittedRow).toBeVisible();
    await expect(submittedRow).toContainText("人工确认已提交");
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("creates an OA draft for an imported ETC batch and moves it to submitted history", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/etc-tickets");
    await expect(page.getByTestId("etc-ticket-management-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "ETC票据" })).toBeVisible();
    await expect(page.getByRole("radiogroup", { name: "ETC批次状态" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 1" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "已提交 0" })).toBeVisible();

    const row = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(row).toBeVisible();
    await expect(row).toContainText("ETC-E2E-2026-03");
    await expect(row).toContainText("ETC票 2 + 补充凭证 0");
    await expect(page.getByRole("table", { name: "ETC发票明细" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "ETC-E2E-001" })).toBeVisible();

    const submitButton = page.getByRole("button", { name: "提交OA" });
    await expect(submitButton).toBeEnabled();
    await submitButton.click();

    const createDialog = page.getByRole("dialog", { name: "创建OA草稿" });
    await expect(createDialog).toBeVisible();
    await expect(createDialog.getByText("为当前批次创建 OA 草稿。")).toBeVisible();
    await expect(createDialog.getByText("批次：ETC-E2E-2026-03")).toBeVisible();

    const draftResponse = page.waitForResponse((response) =>
      response.url().includes("/api/etc/business-batches/etc-business-e2e-001/oa-draft")
        && response.request().method() === "POST",
    );
    await createDialog.getByRole("button", { name: "创建草稿" }).click();
    expect((await draftResponse).status()).toBe(200);
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/oa-draft")).toBe(1);

    const resultDialog = page.getByRole("dialog", { name: "OA提交确认" });
    await expect(resultDialog).toBeVisible();
    await expect(resultDialog.getByText("OA草稿已创建，等待提交确认。")).toBeVisible();
    await expect(resultDialog.getByRole("button", { name: "打开草稿" })).toBeEnabled();
    await expectNoUnexpectedSuccessUiErrors(page);

    const manualStatusResponse = page.waitForResponse((response) =>
      response.url().includes("/api/etc/business-batches/etc-business-e2e-001/manual-oa-status")
        && response.request().method() === "POST",
    );
    await resultDialog.getByRole("button", { name: "已提交" }).click();
    expect((await manualStatusResponse).status()).toBe(200);
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/manual-oa-status")).toBe(1);

    await expect(page.getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("button", { name: "提交OA" })).toHaveCount(0);
    const submittedRow = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(submittedRow).toBeVisible();
    await expect(submittedRow).toContainText("人工确认已提交");
    await expect(submittedRow).toContainText("ETC-E2E-2026-03");
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });
});
