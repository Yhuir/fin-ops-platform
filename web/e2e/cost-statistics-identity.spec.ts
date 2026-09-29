import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test("all five views filter the full scope, sort, paginate, and clear independently", async ({ page }, info) => {
  test.setTimeout(120_000);
  let paginatedViews = 0;
  await installDeterministicApiMocks(page, { sessionMode: "user", costStatisticsLargeDataset: true });
  await page.setViewportSize({ width: 1920, height: 900 });
  await page.goto("/cost-statistics");
  const reads: URL[] = [];
  page.on("request", request => { const url = new URL(request.url()); if (url.pathname.endsWith("/cost-statistics/explorer") && url.searchParams.get("include_statistics") === "false") reads.push(url); });
  for (const view of ["按项目", "按成本标签", "按银行账户", "按标签", "按时间"]) {
    await page.getByRole("radio", { name: view, exact: true }).click();
    const bank = view === "按标签" || view === "按时间";
    if (view === "按银行账户") {
      const account = page.getByRole("option", { name: "选择银行账户 工商银行 账户 0001", exact: true });
      await expect(account.locator(".bank-account-primary")).toHaveText("工商银行");
      await expect(account.locator(".bank-account-secondary")).toHaveText("0001");
      const primary = await account.locator(".bank-account-primary").boundingBox();
      const secondary = await account.locator(".bank-account-secondary").boundingBox();
      expect(secondary!.y).toBeGreaterThanOrEqual(primary!.y + primary!.height);
      await account.click();
    }
    if (view === "按项目" || view === "按银行账户") await page.getByRole("option", { name: "选择项目名 云南溯源科技", exact: true }).click();
    if (!bank) {
      await page.getByRole("option", { name: "选择成本主标签 项目开销", exact: true }).click();
      await page.getByRole("option", { name: "选择成本子标签 设备材料", exact: true }).click();
    } else if (view === "按标签") {
      await page.getByRole("option", { name: "选择主标签 项目开销", exact: true }).click();
      await page.getByRole("option", { name: "选择子标签 设备材料", exact: true }).click();
    }
    const label = bank ? "对方户名" : "申请人";
    const grid = page.getByRole("grid", { name: bank ? `${view}银行流水表` : "成本明细表" });
    await expect(grid).toBeVisible();
    await expect(grid.getByRole("button", { name: "时间倒序，点击切换正序" })).toBeVisible();
    await expect(grid.locator(".cost-entry-time").first()).toBeVisible();
    if (await page.getByRole("button", { name: "下一页", exact: true }).isEnabled()) {
      await page.getByRole("button", { name: "下一页", exact: true }).click();
      await expect(page.locator(".cost-table-pagination-footer")).toContainText("第 2");
      paginatedViews += 1;
    }
    await grid.getByRole("button", { name: `筛选${label}`, exact: true }).click();
    const menu = page.getByRole("dialog", { name: `筛选${label}` });
    const choices = menu.getByRole("checkbox");
    const before = reads.length;
    await menu.locator(".column-filter-option").first().click();
    await expect(choices.first()).toBeChecked();
    expect(reads.length).toBe(before);
    await menu.getByRole("button", { name: "应用", exact: true }).click();
    await expect(grid.getByRole("button", { name: `筛选${label}，已选1项`, exact: true })).toBeVisible();
    await expect(page.locator(".cost-table-pagination-footer")).toContainText("第 1");
    await expect.poll(() => reads.length).toBe(before + 1);
    expect(reads.at(-1)!.searchParams.has("cursor")).toBe(false);
    expect(JSON.parse(reads.at(-1)!.searchParams.get("identity_names")!)).toHaveLength(1);
    await grid.getByRole("button", { name: "时间倒序，点击切换正序" }).click();
    await expect(grid.getByRole("button", { name: "时间正序，点击切换倒序" })).toBeVisible();
    expect(reads.at(-1)!.searchParams.get("sort_order")).toBe("asc");
    await expect(grid.locator(".cost-entry-time").first()).toBeVisible();
    const times = await grid.locator(".cost-entry-time").allTextContents();
    expect(times).toEqual([...times].sort());
    await grid.getByRole("button", { name: `筛选${label}，已选1项`, exact: true }).click();
    await menu.getByRole("button", { name: "清空", exact: true }).click();
    await menu.getByRole("button", { name: "应用", exact: true }).click();
    await expect(grid.getByRole("button", { name: `筛选${label}`, exact: true })).toBeVisible();
    expect(reads.at(-1)!.searchParams.has("identity_names")).toBe(false);
    await expect(grid.locator(".cost-entry-time").first()).toBeVisible();
    await page.screenshot({ path: info.outputPath(`${view}-identity.png`) });
    // A narrow viewport must keep the popup inside the visible viewport.
    await page.setViewportSize({ width: 1024, height: 600 });
    await grid.getByRole("button", { name: `筛选${label}`, exact: true }).click();
    const box = await menu.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0); expect(box!.x + box!.width).toBeLessThanOrEqual(1024);
    expect(box!.y + box!.height).toBeLessThanOrEqual(600);
    await page.keyboard.press("Escape");
    await page.setViewportSize({ width: 1920, height: 900 });
  }
  expect(paginatedViews).toBeGreaterThanOrEqual(3);
  // 1920×900 at 125% browser zoom has a 1536×720 CSS layout viewport.
  await page.setViewportSize({ width: 1536, height: 720 });
  await expect(page.getByRole("grid", { name: "按时间银行流水表" })).toBeVisible();
  await page.getByRole("button", { name: "筛选对方户名", exact: true }).click();
  const zoomMenu = page.getByRole("dialog", { name: "筛选对方户名" });
  await expect.poll(async () => { const box = (await zoomMenu.boundingBox())!; return box.x + box.width; }).toBeLessThanOrEqual(1536);
  await expect.poll(async () => { const box = (await zoomMenu.boundingBox())!; return box.y + box.height; }).toBeLessThanOrEqual(720);
  await page.screenshot({ path: info.outputPath("zoom-125-menu.png") });
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 1920, height: 900 });
});
