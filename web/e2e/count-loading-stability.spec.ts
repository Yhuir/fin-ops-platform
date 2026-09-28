import { expect, test, type Locator } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

async function boxes(controls: Locator) {
  return controls.evaluateAll(elements => elements.map(element => {
    const { x, y, width, height } = element.getBoundingClientRect();
    return { x, y, width, height };
  }));
}

for (const width of [1440, 960]) {
  for (const config of [
    { path: "oa-pending-payments", endpoint: "/api/oa-pending-payments/rows", selector: ".app-segments", role: "radio" as const },
    { path: "output-invoice-collections", endpoint: "/api/output-invoice-collections/rows", selector: ".invoice-count-segments", role: "tab" as const },
    { path: "input-invoice-usage", endpoint: "/api/input-invoice-usage/rows", selector: ".invoice-count-segments", role: "tab" as const },
    { path: "etc-tickets", endpoint: "/api/etc/business-batches", selector: ".etc-status-segmented", role: "radio" as const },
    { path: "batch-accounting", endpoint: "/api/batch-accounting", selector: ".app-segments", role: "radio" as const },
    { path: "bank-flow-rule-batches", endpoint: "/api/bank-flow-rule-batches", selector: ".app-segments", role: "radio" as const },
    { path: "pending-invoices", endpoint: "/api/pending-invoices/rows", selector: ".invoice-count-segments", role: "tab" as const },
  ]) {
    test(`${config.path} retains counts and geometry throughout a delayed switch at ${width}`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await installDeterministicApiMocks(page, { sessionMode: "user", outputInvoiceCollectionListInteractions: true });
      await page.goto(`/${config.path}`);
      const allGroups = page.locator(config.selector);
      const groups = config.path === "input-invoice-usage" ? allGroups.nth(1) : allGroups;
      const controls = (config.path === "pending-invoices" ? groups.first() : groups).getByRole(config.role);
      await expect(controls.first()).toContainText(/\d/);
      await expect(groups.locator('.stable-count__number').first()).not.toHaveText("—");
      // Bring the target into view before taking geometry, so click auto-scroll is not mistaken for reflow.
      await controls.nth(1).scrollIntoViewIfNeeded();
      await controls.nth(1).focus();
      const beforeText = await controls.allTextContents();
      const before = await boxes(controls);
      let release!: () => void;
      const held = new Promise<void>(resolve => { release = resolve; });
      let requests = 0;
      await page.route(`**${config.endpoint}?**`, async route => {
        if (new URL(route.request().url()).searchParams.get("include_statistics") === "true") return route.fallback();
        requests++;
        await held;
        await route.fallback();
      });
      const response = page.waitForResponse(r => new URL(r.url()).pathname === config.endpoint && !r.url().includes("include_statistics=true"));
      await controls.nth(1).click();
      await expect.poll(() => requests).toBe(1);
      expect(await controls.allTextContents()).toEqual(beforeText);
      expect(await boxes(controls)).toEqual(before);
      await page.screenshot({ path: info.outputPath("loading.png") });
      release();
      expect((await response).status()).toBe(200);
      await expect(groups.first()).toHaveAttribute("data-count-pending", "false");
      // Pending direction changes intentionally select a different set of status options.
      const firstGroup = groups.first().getByRole(config.role);
      expect(await boxes(firstGroup)).toEqual(before.slice(0, await firstGroup.count()));
      expect(requests).toBe(1);
    });
  }
}
