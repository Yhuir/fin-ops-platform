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
  test("selects and drops extensionless ticket text without hiding files or silently filtering mixed selections", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    await installDeterministicApiMocks(page, {
      etcTicketReconciliationWorkflow: true, etcTicketWorkflowTaskMatchesBusinessBatch: true, sessionMode: "user",
    });
    const initialResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/etc/reconciliation-tasks/etc-recon-e2e-001");
    await page.goto("/etc-tickets");
    const task = await (await initialResponse).json();
    task.parse_issues = [];
    const posts: string[] = [];
    await page.route("**/api/etc/reconciliation-tasks/etc-recon-e2e-001/ticket-root-files", async (route) => {
      posts.push(route.request().postDataBuffer()!.toString("utf8"));
      const name = posts.length === 1 ? "云A516HJ" : "行程二";
      task.version += 1;
      task.source_files.push({ file_id: `uploaded-${posts.length}`, source_kind: "ticket_root", original_name: name, content_type: "text/plain", has_blocking_issue: false });
      await route.fulfill({ json: task });
    });
    const box = page.getByLabel("上传票根网");
    const input = box.locator('input[type="file"]');
    await expect(box).toBeVisible();
    expect(await input.getAttribute("accept")).toBeNull();
    await expect(page.getByLabel("上传信用卡账单").locator('input[type="file"]')).toHaveAttribute("accept", ".pdf,application/pdf");
    const payload = "车牌号：云A516HJ\r\n交易时间：2026-03-27 10:20:00\r\n交易金额：95.00";
    const chooser = page.waitForEvent("filechooser");
    await box.click();
    await (await chooser).setFiles({ name: "云A516HJ", mimeType: "", buffer: Buffer.from(payload) });
    await expect(page.getByRole("list", { name: "已上传文件列表" }).getByText("云A516HJ", { exact: true })).toBeVisible();
    expect(posts).toHaveLength(1);
    expect(posts[0]).toContain('filename="云A516HJ"');
    expect(posts[0]).toContain(payload);

    await input.setInputFiles([
      { name: "合法.txt", mimeType: "text/plain", buffer: Buffer.from(payload) },
      { name: "错误.pdf", mimeType: "application/pdf", buffer: Buffer.from("pdf") },
      { name: "错误.zip", mimeType: "application/zip", buffer: Buffer.from("zip") },
    ]);
    await expect(page.getByText(/本次未上传任何文件。不支持：错误.pdf、错误.zip/)).toBeVisible();
    expect(posts).toHaveLength(1);
    const dropData = await page.evaluateHandle((text) => {
      const data = new DataTransfer();
      data.items.add(new File([text], "行程二"));
      return data;
    }, payload);
    await box.dispatchEvent("drop", { dataTransfer: dropData });
    await dropData.dispose();
    await expect(page.getByRole("list", { name: "已上传文件列表" }).getByText("行程二", { exact: true })).toBeVisible();
    expect(posts).toHaveLength(2);
    expect(posts[1]).toContain('filename="行程二"');
    expect(posts[1]).toContain(payload);
    await expect(page.getByText(/本次未上传任何文件/)).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath("extensionless-upload.png"), fullPage: true });
    expect(browserErrors).toEqual([]);
  });

  test("shows partial saved files after one outcome read and never reposts an uncertain upload", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, { allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/] });
    await installDeterministicApiMocks(page, {
      etcTicketReconciliationWorkflow: true, etcTicketWorkflowTaskMatchesBusinessBatch: true, sessionMode: "user",
    });
    const initialResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/etc/reconciliation-tasks/etc-recon-e2e-001");
    await page.goto("/etc-tickets");
    const task = await (await initialResponse).json();
    task.parse_issues = [];
    let posts = 0;
    let reads = 0;
    await page.route("**/api/etc/reconciliation-tasks/etc-recon-e2e-001", async (route) => {
      reads += 1;
      await route.fulfill({ json: task });
    });
    await page.route("**/api/etc/reconciliation-tasks/etc-recon-e2e-001/ticket-root-files", async (route) => {
      posts += 1;
      task.version += 1;
      task.source_files.push({ file_id: "first-saved", source_kind: "ticket_root", original_name: "已保存行程", content_type: "text/plain", has_blocking_issue: false });
      await route.fulfill({ status: 503, json: { error: "file_storage_unavailable", message: "第二个文件存储失败，部分文件可能已保存。" } });
    });
    const input = page.getByLabel("上传票根网").locator('input[type="file"]');
    await input.setInputFiles([
      { name: "已保存行程", mimeType: "", buffer: Buffer.from("first") },
      { name: "未保存行程", mimeType: "", buffer: Buffer.from("second") },
    ]);
    await expect(page.getByText("第二个文件存储失败，部分文件可能已保存。")).toBeVisible();
    const list = page.getByRole("list", { name: "已上传文件列表" });
    await expect(list.getByText("已保存行程", { exact: true })).toBeVisible();
    await expect(list.getByText("未保存行程", { exact: true })).toHaveCount(0);
    expect(posts).toBe(1);
    expect(reads).toBe(1);
    await page.screenshot({ path: testInfo.outputPath("partial-upload.png"), fullPage: true });
    expect(browserErrors).toEqual([]);
  });

  test("keeps accepted damaged ticket text visible as a parsing issue rather than successful records", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    await installDeterministicApiMocks(page, {
      etcTicketReconciliationWorkflow: true, etcTicketWorkflowTaskMatchesBusinessBatch: true, sessionMode: "user",
    });
    const initialResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/etc/reconciliation-tasks/etc-recon-e2e-001");
    await page.goto("/etc-tickets");
    const task = await (await initialResponse).json();
    await page.route("**/api/etc/reconciliation-tasks/etc-recon-e2e-001/ticket-root-files", async (route) => {
      await route.fulfill({ json: {
        ...task, version: task.version + 1, ticket_root_items: [],
        source_files: [...task.source_files, { file_id: "bad-text", source_kind: "ticket_root", original_name: "损坏行程", content_type: "text/plain", has_blocking_issue: true }],
        parse_issues: [{ issue_id: "bad-amount", file_id: "bad-text", source_kind: "ticket_root", original_name: "损坏行程", severity: "blocking", message: "第 2 条记录金额不合法", source_line: 5, extraction_method: "text", field_name: "amount" }],
      } });
    });
    await page.getByLabel("上传票根网").locator('input[type="file"]').setInputFiles({ name: "损坏行程", mimeType: "", buffer: Buffer.from("bad record") });
    await expect(page.getByText(/文件已上传，但有内容需要处理/)).toBeVisible();
    await expect(page.getByText("第 2 条记录金额不合法")).toBeVisible();
    await expect(page.getByRole("button", { name: /^解析异常/ })).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("button", { name: /^已上传文件/ })).toHaveAttribute("aria-expanded", "true");
    await page.screenshot({ path: testInfo.outputPath("damaged-text-feedback.png"), fullPage: true });
    expect(browserErrors).toEqual([]);
  });

  test("administrator saves ETC OA draft prefill without exposing internal ids", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });

    await page.goto("/etc-tickets");
    await expect(page.getByTestId("etc-ticket-management-page")).toBeVisible();
    const loadResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && new URL(response.url()).pathname === "/api/workbench/settings/oa-draft-prefill/etc",
    );
    await page.getByRole("button", { name: "OA 草稿预填管理" }).click();
    await loadResponse;

    const drawer = page.getByRole("dialog", { name: "OA 草稿预填管理" });
    await expect(drawer.getByLabel("申请人")).toHaveValue("杨丽萍");
    await expect(drawer.getByLabel("申请人")).toBeDisabled();
    await drawer.getByLabel("开户行").fill("中国建设银行");
    const saveResponse = page.waitForResponse((response) =>
      response.request().method() === "PUT"
      && new URL(response.url()).pathname === "/api/workbench/settings/oa-draft-prefill/etc",
    );
    await drawer.getByRole("button", { name: "保存" }).click();
    await saveResponse;

    const body = api.lastBody("PUT /api/workbench/settings/oa-draft-prefill/etc") as {
      configuration?: { bank?: string; reason_template?: string };
    };
    expect(body.configuration?.bank).toBe("中国建设银行");
    expect(body.configuration?.reason_template).not.toContain("batch_id");
    await expect(drawer.getByText("已保存。")).toBeVisible();
    expect(browserErrors).toEqual([]);
  });

  test("reaches all ETC business batches after the first 100", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    await installDeterministicApiMocks(page, {
      etcTicketBusinessBatchTotal: 121,
      sessionMode: "user",
    });

    await page.goto("/etc-tickets");
    await expect(page.getByText("121 批")).toBeVisible();
    await expect(page.getByText("显示 1-50 / 121")).toBeVisible();

    const secondPageResponse = waitForEtcBusinessBatches(page);
    await page.getByRole("button", { name: "下一页" }).click();
    const secondPageUrl = new URL((await secondPageResponse).url());
    expect(secondPageUrl.searchParams.get("page")).toBe("2");
    expect(secondPageUrl.searchParams.get("page_size")).toBe("50");
    await expect(page.getByTestId("etc-batch-row-etc-business-page-051")).toBeVisible();
    await expect(page.getByText("显示 51-100 / 121")).toBeVisible();

    const thirdPageResponse = waitForEtcBusinessBatches(page);
    await page.getByRole("button", { name: "下一页" }).click();
    const thirdPageUrl = new URL((await thirdPageResponse).url());
    expect(thirdPageUrl.searchParams.get("page")).toBe("3");
    await expect(page.getByTestId("etc-batch-row-etc-business-page-121")).toBeVisible();
    await expect(page.getByText("显示 101-121 / 121")).toBeVisible();
    expect(browserErrors).toEqual([]);
  });

  test("downloads the merged invoice PDF after the OA draft exists", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    await installDeterministicApiMocks(page, {
      etcTicketInitialBusinessBatchStatus: "oa_confirmation_pending",
      sessionMode: "user",
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

    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps an in-progress OA draft in staged with both manual decisions", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    await installDeterministicApiMocks(page, {
      etcTicketInitialBusinessBatchStatus: "oa_draft_creating",
      sessionMode: "user",
    });

    await page.goto("/etc-tickets");
    await expect(page.getByTestId("etc-ticket-management-page")).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 0" })).toBeVisible();
    await page.getByRole("radio", { name: "暂存 1" }).click();
    await expect(page.getByRole("region", { name: "审批提交确认" })).toContainText("已发起审批草稿创建，等待确认。");
    await expect(page.getByRole("button", { name: "我已在 OA 系统上完成 OA 草稿的提交" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "我已在 OA 系统上删除该 OA 草稿" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "核实草稿状态" })).toHaveCount(0);
    expect(browserErrors).toEqual([]);
  });

  test("recovers business batches after a transient load failure when refreshed", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      etcTicketBusinessBatchesFailuresBeforeSuccess: 2,
      etcTicketWorkflowTaskMatchesBusinessBatch: true,
      sessionMode: "user",
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
    await expect(row).toContainText("2026年3月 ETC发票");
    await expect(page.getByLabel("车牌", { exact: true })).toHaveCount(0);
    await expect(page.getByLabel("关键词", { exact: true })).toHaveCount(0);
    const lifecycle = page.getByRole("list", { name: "批次生命周期" });
    await expect(lifecycle).toBeVisible();
    await expect(lifecycle.getByRole("listitem")).toHaveCount(4);
    await expect(lifecycle.getByText("准备核对资料", { exact: true })).toBeVisible();
    await expect(lifecycle.getByText("确认核对结果", { exact: true })).toBeVisible();
    await expect(lifecycle.getByText("导入 ETC 发票", { exact: true })).toBeVisible();
    await expect(lifecycle.getByText("提交 OA 审批", { exact: true })).toBeVisible();
    await expect(page.getByRole("grid", { name: "ETC发票明细" })).toBeVisible();
    await expect(page.getByRole("rowheader", { name: "ETC-E2E-001" })).toBeVisible();
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
      sessionMode: "user",
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
    await expect(row).toContainText("2026年3月 ETC发票");

    const deleteDialog = page.getByRole("dialog", { name: "删除批次" });
    await recordLatency({
      operationId: "etc-tickets.open-delete-unsubmitted-dialog",
      visibleLabel: "删除批次 2026年3月 ETC发票",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "删除批次 2026年3月 ETC发票" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(deleteDialog).toBeVisible());
      await mark("finalSettledLatencyMs", expect(deleteDialog).toContainText("2026年3月 ETC发票"));
    });
    await expect(deleteDialog).toContainText("2026年3月 ETC发票");

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
      sessionMode: "user",
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
    await expect(row).toContainText("2026年3月 ETC发票");
    await expect(row).toContainText("人工确认已提交");

    const deleteDialog = page.getByRole("dialog", { name: "删除批次" });
    await recordLatency({
      operationId: "etc-tickets.open-delete-submitted-dialog",
      visibleLabel: "删除批次 2026年3月 ETC发票",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "删除批次 2026年3月 ETC发票" }).click();
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
      expectedVersion: 10,
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
      sessionMode: "user",
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
      sessionMode: "user",
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
      sessionMode: "user",
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
      sessionMode: "user",
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
    await expect(page.getByRole("radio", { name: "未提交 0" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "暂存 1" })).toHaveAttribute("aria-checked", "true");
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
      sessionMode: "user",
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
    const statusWidths = await page.getByRole("radio", { name: /未提交|暂存|已提交/ }).evaluateAll((buttons) =>
      buttons.map((button) => Math.round(button.getBoundingClientRect().width)),
    );
    expect(Math.max(...statusWidths) - Math.min(...statusWidths)).toBeLessThanOrEqual(1);

    const row = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(row).toBeVisible();
    await expect(row).toContainText("2026年3月 ETC发票");
    await expect(row).toContainText("2 张 · 32.26 元");
    await expect(page.getByRole("grid", { name: "ETC发票明细" })).toBeVisible();
    await expect(page.getByRole("rowheader", { name: "ETC-E2E-001" })).toBeVisible();

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
    await expect(createDialog.getByText("差额 87.74 元")).toBeVisible();
    await expect(createDialog.getByText("批次：2026年3月 ETC发票")).toBeVisible();

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
    await expect(submittedRow).toContainText("2026年3月 ETC发票");
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });
});
