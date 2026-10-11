import { mkdir } from "node:fs/promises";
import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

const visualDir = process.env.FIN_OPS_ETC_VISUAL_DIR;

test("stage views preserve manual input and selection without API I/O", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await installDeterministicApiMocks(page, { sessionMode: "admin", etcTicketInitialBusinessBatchStatus: "reviewing", etcTicketReconciliationWorkflow: true, etcTicketWorkflowTaskMatchesBusinessBatch: true });
  const calls: string[] = [];
  page.on("request", req => { if (new URL(req.url()).pathname.startsWith("/api/etc/")) calls.push(`${req.method()} ${new URL(req.url()).pathname}`); });
  await page.goto("/etc-tickets");
  const stages = page.getByRole("list", { name: "批次生命周期" });
  await expect(stages.getByRole("button")).toHaveCount(4);
  await stages.getByRole("button", { name: /准备核对资料/ }).click();
  await expect(stages.getByRole("button", { name: /准备核对资料/ })).toContainText("正在查看");
  await expect(stages.locator('[aria-current="step"]')).toContainText("确认核对结果");
  await expect(page.getByLabel("上传信用卡账单")).toBeVisible();
  await expect(page.getByRole("list", { name: "已上传文件列表" })).toBeVisible();
  await expect(page.getByRole("grid", { name: "ETC双侧核对明细" })).toBeHidden();
  if (visualDir) { await mkdir(visualDir, { recursive: true }); await page.screenshot({ path: `${visualDir}/sources.png`, animations: "disabled" }); }
  await stages.getByRole("button", { name: /确认核对结果/ }).click();
  const table = page.getByRole("grid", { name: "ETC双侧核对明细" });
  await expect(table).toBeVisible();
  await table.locator('[data-testid^="etc-reconciliation-card-cell-"]').first().click();
  const note = page.getByLabel("处理说明", { exact: true });
  await note.fill("核对备注应保留");
  const checks = table.getByRole("checkbox");
  await table.locator(".checkbox").first().click();
  if (visualDir) {
    await page.locator(".etc-batch-context").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${visualDir}/reconciliation.png`, fullPage: true, animations: "disabled" });
  }
  const before = calls.length;
  await stages.getByRole("button", { name: /准备核对资料/ }).click();
  await stages.getByRole("button", { name: /确认核对结果/ }).click();
  await expect(note).toHaveValue("核对备注应保留");
  await expect(checks.first()).toBeChecked();
  expect(calls.slice(before)).toEqual([]);
  await testInfo.attach("stage-view-requests", { body: JSON.stringify({ extraRequests: calls.slice(before) }), contentType: "application/json" });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator('.etc-workflow-surface')).toHaveCSS('animation-name', 'none');
});

test("returning to a removed batch does not select a different batch", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  await page.goto("/etc-tickets?batch=removed&bucket=unsubmitted&page=1");
  await expect(page.getByText("原批次已不在当前分组或页码，请重新选择批次。")).toBeVisible();
  await expect(page.locator('.etc-list-row-button[aria-current="true"]')).toHaveCount(0);
  await expect(page.getByRole("list", { name: "批次生命周期" })).toHaveCount(0);
});

test("workspace motion and zoom preserve the four stage controls", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await installDeterministicApiMocks(page, { sessionMode: "admin", etcTicketInitialBusinessBatchStatus: "reviewing", etcTicketReconciliationWorkflow: true, etcTicketWorkflowTaskMatchesBusinessBatch: true });
  await page.goto("/etc-tickets");
  const stages = page.getByRole("list", { name: "批次生命周期" });
  await expect(stages.getByRole("button")).toHaveCount(4);
  const sample = async (selector: string, prefix: string) => {
    const element = page.locator(selector);
    const duration = await element.evaluate(el => {
      const target = el as HTMLElement;
      target.style.animation = "none";
      target.getBoundingClientRect();
      target.style.removeProperty("animation");
      const animation = el.getAnimations()[0];
      if (!animation) throw new Error("Missing workspace transition");
      animation.pause(); animation.currentTime = 0;
      return Number(animation.effect!.getComputedTiming().duration);
    });
    expect(duration).toBeGreaterThan(0);
    for (const [label, fraction] of [["start", 0], ["mid", .5], ["end", 1]] as const) {
      await element.evaluate((el, time) => { el.getAnimations()[0].currentTime = time; }, duration * fraction);
      if (visualDir) await page.screenshot({ path: `${visualDir}/${prefix}-${label}.png`, animations: "allow" });
    }
    return duration;
  };
  const entryMs = await sample(".etc-right-column", "entry");
  await stages.getByRole("button", { name: /准备核对资料/ }).click();
  const stageMs = await sample(".etc-workflow-surface", "stage");
  const button = stages.getByRole("button", { name: /确认核对结果/ });
  await button.hover();
  if (visualDir) await page.screenshot({ path: `${visualDir}/press-start.png` });
  await page.mouse.down();
  await expect(button).toHaveCSS("transform", "matrix(1, 0, 0, 1, 0, 1)");
  if (visualDir) await page.screenshot({ path: `${visualDir}/press-mid.png` });
  await page.mouse.up();
  await expect(button).toHaveAttribute("aria-pressed", "true");
  if (visualDir) await page.screenshot({ path: `${visualDir}/press-end.png` });
  await page.setViewportSize({ width: 720, height: 500 });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: 720, height: 500, deviceScaleFactor: 2, mobile: false });
  await expect(stages.getByRole("button")).toHaveCount(4);
  for (const stage of await stages.getByRole("button").all()) {
    await expect(stage).toBeVisible();
    expect((await stage.boundingBox())!.width).toBeGreaterThan(100);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const cardFits = await page.locator(".etc-batch-scroll").evaluate(el => el.clientHeight >= (el.querySelector(".etc-batch-row") as HTMLElement).offsetHeight);
  expect(cardFits, "At 200% the list must show at least one complete batch card").toBe(true);
  if (visualDir) await page.screenshot({ path: `${visualDir}/zoom-200.png`, fullPage: true, animations: "disabled" });
  await testInfo.attach("workspace-motion", { body: JSON.stringify({ entryMs, stageMs, pressFeedback: "translateY(1px)", zoom: 2 }), contentType: "application/json" });
});

test("current batch import selects the exact task and returns to the same batch and page", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await installDeterministicApiMocks(page, { sessionMode: "admin", etcTicketInitialBusinessBatchStatus: "ready_for_import" });
  await page.route("**/api/etc/reconciliation-tasks/etc-recon-e2e-001", async route => {
    await route.fulfill({ json: { task_id: "etc-recon-e2e-001", status: "ready_for_import", version: 7, title: "当前批次", oa_total_amount: "188.00", etc_invoice_count: 3, supplement_count: 1, imported_invoice_count: 0, imported_invoice_amount: "0.00", vehicle_plates: [], credit_card_items: [], ticket_root_items: [], supplement_evidences: [], reconciled_items: [], source_files: [], parse_issues: [] } });
  });
  await page.route("**/api/etc/reconciliation-tasks/ready-for-import", async route => {
    await route.fulfill({ json: { tasks: [{ task_id: "other", status: "ready_for_import", version: 1, title: "其他任务", oa_total_amount: "1.00", etc_invoice_count: 1, supplement_count: 0, vehicle_plates: [] }, { task_id: "etc-recon-e2e-001", status: "ready_for_import", version: 7, title: "当前批次", oa_total_amount: "188.00", etc_invoice_count: 3, supplement_count: 1, vehicle_plates: [] }], unavailable_tasks: [] } });
  });
  await page.goto("/etc-tickets");
  await page.getByRole("button", { name: /导入 ETC 发票/ }).click();
  if (visualDir) {
    await page.screenshot({ path: `${visualDir}/import-stage.png`, fullPage: true, animations: "disabled" });
    await page.getByRole("button", { name: /提交 OA 审批/ }).click();
    await expect(page.getByRole("button", { name: "提交审批", exact: true })).toBeDisabled();
    await expect(page.locator(".etc-submit-action")).toContainText("当前批次状态不能创建审批草稿。");
    await page.screenshot({ path: `${visualDir}/oa-stage.png`, fullPage: true, animations: "disabled" });
    await page.getByRole("button", { name: /导入 ETC 发票/ }).click();
  }
  const importButton = page.getByRole("link", { name: "导入当前批次" });
  if (visualDir) {
    await importButton.hover();
    await page.screenshot({ path: `${visualDir}/primary-press-start.png`, animations: "disabled" });
    await page.mouse.down();
    await expect(importButton).toHaveCSS("transform", "matrix(1, 0, 0, 1, 0, 1)");
    await page.screenshot({ path: `${visualDir}/primary-press-mid.png`, animations: "disabled" });
    await page.mouse.up();
    await page.screenshot({ path: `${visualDir}/primary-press-end.png`, animations: "disabled" });
  } else await importButton.click();
  await expect(page).toHaveURL(/etc_task=etc-recon-e2e-001/);
  await expect(page.getByLabel("ETC对账任务", { exact: true })).toHaveValue("etc-recon-e2e-001");
  await page.getByRole("button", { name: "返回 ETC 批次" }).click();
  await expect(page).toHaveURL(/etc-tickets\?batch=etc-business-e2e-001&bucket=unsubmitted&page=1/);
  await expect(page.getByTestId("etc-batch-row-etc-business-e2e-001").getByRole("button").first()).toHaveAttribute("aria-current", "true");
});

test("missing requested import task cannot silently use another task", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  await page.goto("/imports/etc-invoices?from=etc-tickets&etc_task=missing&batch=batch-missing&bucket=unsubmitted&page=2");
  await expect(page.getByText("当前批次的核对任务不可导入，请返回 ETC 批次核对状态。")).toBeVisible();
  await expect(page.getByLabel("ETC对账任务", { exact: true })).toHaveValue("");
  await expect(page.getByRole("button", { name: "开始预览" })).toBeDisabled();
});
