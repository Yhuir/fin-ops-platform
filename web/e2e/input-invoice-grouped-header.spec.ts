import { expect, test, type Locator, type Page } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

const tableName = "进项发票使用情况表";
const rowsPath = "/api/input-invoice-usage/rows";

function waitForRows(page: Page) {
  return page.waitForResponse(response => new URL(response.url()).pathname === rowsPath);
}

async function expectGroupedHeader(table: Locator) {
  const groups = table.locator("thead > tr").first().locator("th");
  await expect(groups).toHaveText([/^进项发票.*张价税合计.*税额合计/, "支付状态", "OA", "流水"]);
  expect(await groups.evaluateAll(headers => headers.map(header => (header as HTMLTableCellElement).colSpan))).toEqual([4, 1, 2, 3]);
  await expect(groups.nth(1)).toHaveAttribute("rowspan", "2");
  await expect(groups.nth(1)).toHaveAttribute("scope", "col");
  for (const index of [0, 2, 3]) await expect(groups.nth(index)).toHaveAttribute("scope", "colgroup");
  await expect(table.locator("thead > tr")).toHaveCount(2);
  await expect(table.locator("thead > tr").last().locator("th")).toHaveCount(9);
  await expect(table.locator("colgroup > col")).toHaveCount(10);
  expect(await table.locator("colgroup").evaluateAll(groups => groups.map(group => group.children.length))).toEqual([4, 1, 2, 3]);
}

async function expectGroupGeometry(table: Locator) {
  const geometry = await table.evaluate(element => {
    const headers = [...element.querySelectorAll<HTMLTableCellElement>("thead > tr:first-child > th")];
    const cells = [...element.querySelectorAll<HTMLTableCellElement>("tbody > tr:first-child > :is(th, td)")];
    const leafHeaders = [...element.querySelectorAll<HTMLTableCellElement>("thead > tr:last-child > th")];
    const bounds = (node: Element) => {
      const { left, right, top, bottom, width, height } = node.getBoundingClientRect();
      return { left, right, top, bottom, width, height };
    };
    return { groups: headers.map(bounds), cells: cells.map(bounds),
      leaves: [...leafHeaders.slice(0, 4), headers[1], ...leafHeaders.slice(4)].map(bounds),
      head: bounds(element.querySelector("thead")!),
      backgrounds: cells.map(cell => getComputedStyle(cell).backgroundColor) };
  });
  expect(geometry.cells).toHaveLength(10);
  expect(geometry.head.height).toBeGreaterThanOrEqual(70);
  expect(geometry.head.height).toBeLessThanOrEqual(78);
  for (const [groupIndex, [first, last]] of [[0, 3], [4, 4], [5, 6], [7, 9]].entries()) {
    expect(Math.abs(geometry.groups[groupIndex].left - geometry.cells[first].left)).toBeLessThan(1);
    expect(Math.abs(geometry.groups[groupIndex].right - geometry.cells[last].right)).toBeLessThan(1);
  }
  for (const [index, leaf] of geometry.leaves.entries()) {
    expect(Math.abs(leaf.left - geometry.cells[index].left)).toBeLessThan(1);
    expect(Math.abs(leaf.right - geometry.cells[index].right)).toBeLessThan(1);
  }
  expect(geometry.cells[4].width).toBeGreaterThanOrEqual(146);
  expect(geometry.cells[4].width).toBeLessThanOrEqual(150);
  expect(geometry.cells[1].width).toBeGreaterThan(geometry.cells[5].width);
  expect(geometry.backgrounds[4]).toBe(geometry.backgrounds[0]);
  return geometry;
}

test("two-level invoice headers remain aligned and sticky while scrolling both axes", async ({ page }, testInfo) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "admin", inputInvoiceUsageFilterSortRows: true });
  await page.goto("/input-invoice-usage");
  const table = page.getByRole("table", { name: tableName });
  await expect(table.locator("tbody > tr")).toHaveCount(20);
  await expect(table.getByRole("rowheader")).toHaveCount(20);
  await expectGroupedHeader(table);
  const initialReads = api.count(`GET ${rowsPath}`);
  const scroller = page.locator(".input-invoice-usage-table-shell .finance-table__scroll");
  await expect(scroller).toHaveCount(1);

  for (const width of [1920, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await scroller.evaluate(node => { node.scrollTop = 0; node.scrollLeft = 0; });
    const before = await expectGroupGeometry(table);
    await scroller.evaluate(node => { node.scrollTop = 300; });
    await expect.poll(() => scroller.evaluate(node => node.scrollTop)).toBeGreaterThan(0);
    const vertical = await expectGroupGeometry(table);
    expect(Math.abs(vertical.head.top - before.head.top)).toBeLessThan(1);
    expect(vertical.cells[0].top).toBeLessThan(before.cells[0].top - 100);
    const horizontalRange = await scroller.evaluate(node => node.scrollWidth - node.clientWidth);
    const horizontalDistance = Math.min(240, Math.floor(horizontalRange / 2));
    await scroller.evaluate((node, distance) => { node.scrollLeft = distance; }, horizontalDistance);
    await expect.poll(() => scroller.evaluate(node => node.scrollLeft)).toBeCloseTo(horizontalDistance, 0);
    const horizontal = await expectGroupGeometry(table);
    expect(Math.abs(horizontal.head.top - before.head.top)).toBeLessThan(1);
    expect(Math.abs(horizontal.cells[0].left - vertical.cells[0].left + horizontalDistance)).toBeLessThan(1);
    if (width === 1440) expect(horizontalRange).toBeGreaterThan(0);
    await page.screenshot({ path: testInfo.outputPath(`input-grouped-header-${width}.png`), animations: "disabled" });
  }
  expect(api.count(`GET ${rowsPath}`)).toBe(initialReads);
  expect(api.count("GET /api/input-invoice-usage/filter-options")).toBe(0);
});

test("grouped headers retain keyboard sorting, filters, source detail and a ten-column empty state", async ({ page }) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "admin", inputInvoiceUsageFilterSortRows: true });
  await page.setViewportSize({ width: 1920, height: 1000 });
  await page.goto("/input-invoice-usage");
  const table = page.getByRole("table", { name: tableName });
  await expectGroupedHeader(table);
  const dateSort = table.getByRole("button", { name: "按开票日期排序", exact: true });
  await dateSort.focus();
  await expect(dateSort).toBeFocused();
  const sorted = waitForRows(page);
  await dateSort.press("Enter");
  const sortedUrl = new URL((await sorted).url());
  expect(sortedUrl.searchParams.get("sort_field")).toBe("invoice_date");
  expect(sortedUrl.searchParams.get("sort_direction")).toBe("asc");
  await expect(table.locator("tbody > tr").first()).toContainText("SD-INV-E2E-0099");

  const readsBeforeMenu = api.count(`GET ${rowsPath}`);
  const sellerFilter = table.getByRole("button", { name: "筛选 销方名称", exact: true });
  await sellerFilter.focus();
  await sellerFilter.press("Enter");
  const sellerMenu = page.getByRole("menu", { name: "销方名称筛选与排序" });
  await expect(sellerMenu).toBeVisible();
  const filtered = waitForRows(page);
  await sellerMenu.locator("label.input-invoice-usage-filter-menu__item").filter({ hasText: /页外供应商 1/ }).click();
  const filterUrl = new URL((await filtered).url());
  expect(JSON.parse(decodeURIComponent(filterUrl.searchParams.get("filters")!))).toEqual([{ field: "seller_name", operator: "in", values: ["页外供应商"] }]);
  await expect(table.locator("tbody > tr")).toHaveCount(1);
  expect(api.count(`GET ${rowsPath}`)).toBe(readsBeforeMenu + 1);
  await page.keyboard.press("Escape");
  await expect(sellerMenu).toHaveCount(0);

  const detail = table.getByRole("button", { name: /^查看发票 .* 详情$/ }).first();
  await detail.focus();
  await detail.press("Enter");
  const drawer = page.getByRole("dialog", { name: "发票详情", exact: true });
  await expect(drawer).toBeVisible();
  await drawer.getByRole("button", { name: "关闭详情抽屉", exact: true }).click();
  await expect(drawer).toHaveCount(0);
  expect(api.count(`GET ${rowsPath}`)).toBe(readsBeforeMenu + 1);

  const search = page.getByRole("searchbox", { name: "进项发票使用情况搜索" });
  await search.fill("没有对应记录的筛选条件");
  const empty = waitForRows(page);
  await search.press("Enter");
  await empty;
  await expect(table.locator("tbody > tr")).toHaveCount(1);
  await expect(table.locator("tbody td")).toHaveCount(1);
  await expect(table.locator("tbody td")).toHaveAttribute("colspan", "10");
  await expect(table.locator("tbody td")).toContainText("当前条件下没有进项发票使用记录");
  await expectGroupedHeader(table);
  expect(api.count("GET /api/input-invoice-usage/filter-options")).toBe(0);
  expect(api.calls.filter(call => /^(POST|PUT|PATCH|DELETE) /.test(call))).toEqual([]);
});
