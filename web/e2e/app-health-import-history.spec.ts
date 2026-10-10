import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

test.use({ video: "on" });

test("data partitions, history filters, pagination and withdrawal form one complete flow", async ({ page }, testInfo) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });
  const visualDirectory = process.env.FIN_OPS_VISUAL_OUTPUT_DIR;
  const screenshot = async (name: string) => {
    if (!visualDirectory) return;
    await mkdir(visualDirectory, { recursive: true });
    const dialogs = page.getByRole("dialog");
    const hasDialog = await dialogs.count() > 0;
    if (hasDialog) await expect.poll(async () => {
      const box = await dialogs.last().boundingBox();
      const viewport = page.viewportSize()!;
      return box !== null && box.x >= 0 && Math.abs(box.x + box.width - viewport.width) < 1;
    }).toBe(true);
    await page.screenshot({ path: join(visualDirectory, `${name}.png`), fullPage: !hasDialog });
  };
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/operations/app-health");
  await expect(page.getByLabel("按类型")).toContainText("合计 1 张");
  await expect(page.getByLabel("按导入方式")).toContainText("合计 1 张");
  await expect(page.getByTestId("app-health-page").locator("section")).toHaveCount(2);
  await screenshot("desktop");
  // Replay the production CSS entrance animation and pause it for three-frame evidence.
  for (const [name, time] of [["entry-start", 0], ["entry-mid", 90], ["entry-end", 200]] as const) {
    await page.locator(".app-health-content").evaluate((element, position) => {
      const container = element as HTMLElement;
      container.style.animation = "none";
      void container.offsetHeight;
      container.style.animation = "";
      const animation = container.getAnimations()[0];
      if (!animation) throw new Error("Production entrance animation is missing");
      animation.pause(); animation.currentTime = position;
    }, time);
    await screenshot(name);
  }
  await page.locator(".app-health-content").evaluate(element => element.getAnimations().forEach(animation => animation.finish()));

  await screenshot("refresh-start");
  let finishRefresh!: () => void;
  const hold = new Promise<void>(resolve => { finishRefresh = resolve; });
  await page.route("**/api/operations/app-health-dashboard", async route => { await hold; await route.fallback(); }, { times: 1 });
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(page.getByRole("button", { name: "刷新", exact: true })).toBeDisabled();
  await screenshot("refresh-mid");
  finishRefresh();
  await expect(page.getByRole("button", { name: "刷新", exact: true })).toBeEnabled();
  await screenshot("refresh-end");
  await screenshot("drawer-start");
  await page.getByRole("button", { name: "导入历史", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "导入历史", exact: true });
  await expect(drawer).toBeVisible();
  await expect(drawer).toContainText("共 51 条");
  await screenshot("drawer-end");
  await drawer.getByRole("button", { name: "下一页", exact: true }).click();
  await expect(drawer.getByRole("button", { name: "查看 交易明细-50.xlsx" })).toBeVisible();
  await expect(drawer.getByRole("button", { name: "查看 交易明细-2.xlsx" })).toHaveCount(0);
  await drawer.getByLabel("每页").selectOption("100");
  await drawer.getByRole("combobox", { name: "状态", exact: true }).selectOption("partial_success");
  await drawer.getByLabel("开始日期").fill("2026-10-10");
  await drawer.getByLabel("结束日期").fill("2026-10-10");
  await drawer.getByRole("button", { name: "查询", exact: true }).click();
  await expect(drawer).toContainText("共 1 条");
  await expect(drawer).toContainText("部分完成");
  await drawer.getByRole("button", { name: "查看 交易明细-1.xlsx" }).click();
  await expect(drawer).toContainText("建设银行 · 8106");
  await expect(drawer.getByRole("button", { name: "撤回本次流水导入" })).toHaveCount(0);
  await drawer.getByRole("button", { name: "返回列表", exact: true }).click();
  await expect(drawer.getByRole("combobox", { name: "状态", exact: true })).toHaveValue("partial_success");
  await expect(drawer.getByLabel("开始日期")).toHaveValue("2026-10-10");
  await drawer.getByLabel("文件名").fill("不存在.xlsx");
  await drawer.getByRole("button", { name: "查询", exact: true }).click();
  await expect(drawer).toContainText("暂无导入记录");
  await drawer.getByRole("button", { name: "关闭导入历史", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);

  const sourceName = "A058171TB_ND9438900000501277800011_CN000_20261010163813_20466424_resp.xls";
  await page.getByRole("button", { name: `查看 ${sourceName}` }).click();
  await expect(drawer.getByRole("heading", { name: sourceName })).toBeVisible();
  await screenshot("detail");
  await drawer.getByRole("button", { name: "撤回本次流水导入" }).click();
  const confirmation = page.getByRole("dialog", { name: "撤回流水导入", exact: true });
  await expect(confirmation).toContainText("OA、发票及导入/操作审计记录不会删除");
  let withdrawals = 0;
  await page.route("**/api/imports/bank-transaction-batches/bank-0/withdraw", route => {
    withdrawals++;
    return route.fulfill({ json: { batch_id: "bank-0", withdrawn_count: 18 } });
  });
  await page.route("**/api/operations/import-history/bank-0", route => {
    return route.fulfill({ json: { row: { key: "bank-0", batch_id: "bank-0", batch_type: "bank_transaction", label: "流水导入",
      source_name: sourceName, imported_by: "YNSYLP007", imported_at: "2026-10-10T08:38:00Z", count: 18,
      selected_bank_name: "建设银行", selected_bank_last4: "8106", status: "withdrawn", withdrawal_allowed: false,
      withdrawal: { withdrawn_count: 18, withdrawn_by: "YNSYLP005", withdrawn_at: "2026-10-11T00:00:00Z" } } } });
  });
  await confirmation.getByRole("button", { name: "确认撤回", exact: true }).click();
  await expect(drawer).toContainText("已撤回 18 笔银行流水。");
  await expect(drawer.getByRole("button", { name: "撤回本次流水导入" })).toHaveCount(0);
  expect(withdrawals).toBe(1);
  await expectNoUnexpectedSuccessUiErrors(page);
  expect(api.count("GET /api/operations/app-health-dashboard")).toBeGreaterThan(1);
  await drawer.getByRole("button", { name: "关闭导入历史", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "导入历史", exact: true })).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await screenshot("mobile");
  const recent = page.getByRole("grid", { name: "最近导入记录" });
  await expect(recent.getByRole("columnheader", { name: "状态", exact: true })).toBeVisible();
  await expect(recent.getByRole("button", { name: `查看 ${sourceName}` })).toBeInViewport();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.getByRole("button", { name: "导入历史", exact: true }).click();
  await expect(drawer).toBeVisible();
  expect((await drawer.getByLabel("开始日期").boundingBox())!.width).toBeGreaterThan(240);
  await expect(drawer.getByText("暂无导入记录", { exact: true })).toBeVisible();
  await screenshot("mobile-history");
  await drawer.getByRole("button", { name: "关闭导入历史", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await testInfo.attach("app-health-flow", { body: JSON.stringify({ withdrawalRequests: withdrawals, dashboardReads: api.count("GET /api/operations/app-health-dashboard") }), contentType: "application/json" });
});
