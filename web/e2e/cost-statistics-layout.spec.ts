import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test("project-cost layouts stay contained, compact and readable across views and widths", async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    const now = Date.now();
    sessionStorage.setItem("finops:pageSession:v1:e2e-user:cost-statistics:explorerState", JSON.stringify({
      version: 6,
      updatedAt: now,
      expiresAt: now + 60 * 60 * 1000,
      value: {
        viewMode: "project",
        projectScopeMode: "all",
        projectScopeYear: "2026",
        projectScopeMonth: "2026-03",
        bankAccountScopeMode: "all",
        bankAccountScopeYear: "2026",
        bankAccountScopeMonth: "2026-03",
        costTagScopeMode: "all",
        costTagScopeYear: "2026",
        costTagScopeMonth: "2026-03",
        bankFlowScopeMode: "month",
        bankFlowScopeYear: "2026",
        bankFlowScopeMonth: "2026-03",
      },
    }));
  });
  await installDeterministicApiMocks(page, { sessionMode: "user", costStatisticsLargeDataset: true });
  await page.setViewportSize({ width: 1920, height: 900 });
  await page.goto("/cost-statistics");
  const reads: string[] = [];
  page.on("request", request => { if (request.url().includes("/cost-statistics/explorer")) reads.push(request.url()); });
  for (const view of ["按项目", "按流水标签", "按银行账户"]) {
    await page.getByRole("radio", { name: view, exact: true }).click();
    if (view === "按银行账户") await page.getByRole("option", { name: "选择银行账户 工商银行 账户 0001", exact: true }).click();
    if (view !== "按流水标签") await page.getByRole("option", { name: "选择项目名 云南溯源科技", exact: true }).click();
    await page.getByRole("option", { name: "选择银行主标签 项目开销", exact: true }).click();
    await page.getByRole("option", { name: "选择银行子标签 设备材料", exact: true }).click();
    await expect(page.getByRole("grid", { name: "成本明细表" })).toContainText(view === "按流水标签" ? "大型成本流水费用内容" : "PLC 模块采购");
    await expect(page.locator(".cost-hierarchy .cost-explorer-item-main > span")).toHaveCount(0);
    for (const size of [{ width: 1920, height: 900 }, { width: 1440, height: 720 }, { width: 1024, height: 600 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(size);
      const detail = page.locator(".cost-hierarchy-detail");
      await expect(detail).toBeVisible();
      await expect.poll(async () => page.evaluate(() => ({
        vertical: document.documentElement.scrollHeight <= innerHeight + 1,
        horizontal: document.documentElement.scrollWidth <= innerWidth + 1,
      }))).toEqual({ vertical: true, horizontal: true });
      const times = await page.locator(".cost-entry-time").evaluateAll(nodes => nodes.map(node => ({ height: node.getBoundingClientRect().height, width: node.getBoundingClientRect().width, scrollWidth: node.scrollWidth })));
      expect(times.length).toBeGreaterThan(0);
      for (const time of times) { expect(time.height).toBeLessThanOrEqual(19); expect(time.scrollWidth).toBeLessThanOrEqual(time.width + 1); }
      const scroll = page.locator(".cost-hierarchy .finance-table__scroll");

      if (size.width === 1920) {
        await page.screenshot({ path: testInfo.outputPath(`${view}-before-wheel.png`) });

      }
      const readCount = reads.length;
      await scroll.evaluate(node => { node.scrollTop = node.scrollHeight; });
      await scroll.hover();
      await page.mouse.wheel(0, 800);
      expect(await page.evaluate(() => scrollY)).toBe(0);
      const header = await scroll.locator("thead").boundingBox();
      const bounds = await scroll.boundingBox();
      expect(header!.y).toBeGreaterThanOrEqual(bounds!.y - 1);
      expect(header!.y + header!.height).toBeLessThanOrEqual(bounds!.y + bounds!.height + 1);
      expect(bounds!.height).toBeGreaterThan(100);
      expect(reads.length).toBe(readCount);
      await scroll.evaluate(node => { node.scrollTop = 0; });
      await expect.poll(() => scroll.evaluate(node => node.scrollTop)).toBe(0);
      await page.screenshot({ path: testInfo.outputPath(`${view}-${size.width}.png`), fullPage: true });
    }
    await page.setViewportSize({ width: 1920, height: 900 });
    if (view === "按银行账户") {
      const accountList = page.locator(".cost-hierarchy-column").first().locator(".cost-explorer-list");
      expect(await accountList.evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true);
      await accountList.hover();
      await page.mouse.wheel(0, 500);
      await expect.poll(() => accountList.evaluate(node => node.scrollTop)).toBeGreaterThan(0);
      expect(await page.locator(".cost-hierarchy .finance-table__scroll").evaluate(node => node.scrollTop)).toBe(0);
      expect(await page.evaluate(() => scrollY)).toBe(0);
    }
  }
  await page.getByRole("radio", { name: "按时间", exact: true }).click();
  await expect(page.locator(".cost-page--project")).toHaveCount(0);
  await expect(page.locator(".cost-transaction-time-chip").first()).toBeVisible();
});
