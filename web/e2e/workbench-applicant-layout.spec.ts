import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

for (const width of [1685, 1280, 900]) {
  test(`OA applicant stays readable with an anomaly at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await installDeterministicApiMocks(page, { sessionMode: "user", workbenchApplicantLayoutScenario: true });
    await page.goto("/");
    const zone = page.getByTestId("zone-unpaired");
    const cell = zone.locator(".record-card-oa .column-applicant-compact").first();
    await expect(cell).toBeVisible();
    const check = async () => {
      const result = await cell.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const content = element.querySelector(".compound-cell-value")!.getBoundingClientRect();
        const actions = element.querySelector(".workbench-oa-applicant-actions")!.getBoundingClientRect();
        const nodes = element.querySelectorAll(".cell-text-value, .chip, .inline-meta-tag, .workbench-detail-trigger, .workbench-anomaly-indicator__trigger");
        return {
          width: rect.width,
          clipped: [...nodes].filter(node => {
            const r = node.getBoundingClientRect();
            return r.left < rect.left - 1 || r.right > rect.right + 1;
          }).map(node => node.textContent),
          separateActions: actions.top >= content.bottom,
        };
      });
      expect(result.width).toBeGreaterThanOrEqual(111);
      expect(result.clipped).toEqual([]);
      expect(result.separateActions).toBe(true);
    };
    await check();
    const sidebar = page.getByRole("button", { name: /展开菜单|折叠菜单/ });
    await sidebar.click();
    await check();
    const row = zone.locator(".record-card-oa").first();
    await cell.getByRole("button", { name: /该OA有.*异常/ }).hover();
    await expect(page.getByRole("dialog", { name: "该OA异常详情" })).toBeVisible();
    await expect(row).toHaveAttribute("data-row-state", "idle");
    await cell.getByRole("button", { name: /该OA有.*异常/ }).click();
    await cell.getByRole("button", { name: /查看OA.*详情/ }).click();
    await expect(page.getByRole("dialog").last()).toBeVisible();
    await expect(row).toHaveAttribute("data-row-state", "idle");
    await page.getByRole("dialog").last().getByRole("button", { name: "关闭详情抽屉", exact: true }).click();
    const scrollbar = page.getByTestId("pane-scrollbar-unpaired-oa");
    await scrollbar.evaluate(el => { el.scrollLeft = el.scrollWidth; el.dispatchEvent(new Event("scroll", { bubbles: true })); });
    const header = page.getByTestId("pane-scroll-head-unpaired-oa");
    await expect.poll(async () => Math.abs(await header.locator(".column-applicant-compact").evaluate(el => el.getBoundingClientRect().right) - await cell.evaluate(el => el.getBoundingClientRect().right))).toBeLessThanOrEqual(1);
    await scrollbar.evaluate(el => { el.scrollLeft = 0; el.dispatchEvent(new Event("scroll", { bubbles: true })); });
    await page.screenshot({ path: `test-results/applicant-${width}.png`, fullPage: true });
  });
}
