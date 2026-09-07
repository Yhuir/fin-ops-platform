import { expect, test, type Page, type Locator } from "./fixtures/strictTest";

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === "1";
const token = process.env.FIN_OPS_E2E_OA_TOKEN ?? "";
test.use({ screenshot: "off", trace: "off", video: "off" });

// Opt-in verification only. Never create accounts, roles, flows or OA records here.
test.describe("production cash read-only verification", () => {
  test.skip(!enabled || !token, "Requires explicit production smoke mode and the local token wrapper.");

  test("opens every cash view, checks isolation, and measures real response-to-paint latency", async ({ page, baseURL }) => {
    test.setTimeout(300_000);
    const origin = new URL(baseURL!).origin;
    const writes: string[] = [], failed: string[] = [], cashCalls: string[] = [];
    const ordinaryDuringCash: string[] = [];
    let cashActive = true;
    await page.context().addCookies([{ name: "Admin-Token", value: token, domain: new URL(origin).hostname, path: "/", secure: true, sameSite: "Lax" }]);
    await page.route("**/*", async route => {
      const request = route.request(), url = new URL(request.url());
      if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) {
        writes.push(`${request.method()} ${url.pathname}`); await route.abort("blockedbyclient"); return;
      }
      if (url.pathname.includes("/api/cash/")) cashCalls.push(url.pathname);
      if (cashActive && /\/api\/(bank-details|workbench|turnover-ledger|operation-history|invoices)\b/.test(url.pathname)) ordinaryDuringCash.push(url.pathname);
      await route.continue();
    });
    page.on("response", response => {
      const path = new URL(response.url()).pathname;
      if (path.includes("/api/cash/") && response.status() !== 200) failed.push(`${response.status()} ${path}`);
    });
    const samples: Record<string, { clickToPaint: number; responseToPaint: number }[]> = {};
    const menuPaint: number[] = [];
    const menuPointerPaint: number[] = [];
    async function checkMenu(label: string) {
      const trigger = page.getByRole("button", { name: label, exact: true });
      await trigger.scrollIntoViewIfNeeded();
      await trigger.focus(); await twoFrames(page);
      const geometry = () => page.evaluate(() => Array.from(document.querySelectorAll(
        ".cash-page .page-header, .cash-page .cash-toolbar, .cash-page .finance-table, .cash-page .finance-table__footer",
      )).map(element => {
        const rect = element.getBoundingClientRect();
        return [rect.x, rect.y, rect.width, rect.height];
      }));
      const before = await geometry();
      await trigger.evaluate(button => button.addEventListener("pointerdown", () => {
        (window as Window & { cashOpenStarted?: number }).cashOpenStarted = performance.now();
      }, { once: true }));
      const started = performance.now();
      await trigger.click();
      const dialog = page.getByRole("dialog", { name: label, exact: true });
      await expect(dialog).toBeVisible(); await twoFrames(page);
      menuPaint.push(performance.now() - started);
      menuPointerPaint.push(await dialog.evaluate(() => performance.now() - (window as Window & { cashOpenStarted?: number }).cashOpenStarted!));
      const after = await geometry();
      expect(after.length).toBe(before.length);
      after.forEach((rect, index) => rect.forEach((value, axis) => expect(Math.abs(value - before[index][axis])).toBeLessThanOrEqual(1)));
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0); await expect(trigger).toBeFocused();
      const closed = await geometry();
      expect(closed.length).toBe(before.length);
      closed.forEach((rect, index) => rect.forEach((value, axis) => expect(Math.abs(value - before[index][axis])).toBeLessThanOrEqual(1)));
    }
    async function show(name: string, path: string, action: () => Promise<unknown>, grid?: Locator) {
      const start = performance.now();
      const incoming = page.waitForResponse(response => new URL(response.url()).pathname === `/fin-ops-api/api/cash/${path}` && response.request().method() === "GET");
      await action(); const response = await incoming; await response.finished(); const received = performance.now();
      expect(response.status(), path).toBe(200); expect(response.headers()["cache-control"]).toContain("no-store");
      if (grid) await expect(grid).toBeVisible();
      await expect(page.locator(".cash-page").getByText(/^正在读取/)).toHaveCount(0);
      await expect(page.locator(".cash-page [role=alert]")).toHaveCount(0);
      await twoFrames(page);
      const painted = performance.now();
      (samples[name] ??= []).push({ clickToPaint: painted - start, responseToPaint: painted - received });
    }
    const nav = () => page.getByRole("navigation", { name: "主导航" });
    const flowsGrid = page.getByRole("grid", { name: "现金流水明细" });
    await show("cold_flows", "flows", () => page.goto("/fin-ops/cash?section=flows", { waitUntil: "domcontentloaded" }), flowsGrid);
    for (const name of ["现金流水", "现金账目", "每月任务", "基础设置"]) await expect(nav().getByRole("link", { name, exact: true })).toBeVisible();
    await expect(page.getByRole("tab")).toHaveCount(0);
    await checkMenu("筛选账户"); await checkMenu("筛选来源");
    await show("turnover", "reports/turnover", () => nav().getByRole("link", { name: "现金账目", exact: true }).click(), page.getByRole("grid", { name: "往来账总表" }));
    await expect(page.getByRole("tab")).toHaveCount(3);
    await checkMenu("筛选项目");
    await show("tickets", "reports/ticket-payments", () => page.getByRole("tab", { name: "有票支付", exact: true }).click(), page.getByRole("grid", { name: "有票支付", exact: true }));
    await checkMenu("筛选使用状态");
    await show("personal_matrix", "reports/personal", () => page.getByRole("tab", { name: "个人专账", exact: true }).click(), page.getByRole("grid", { name: "个人年度还款矩阵" }));
    await checkMenu("筛选银行 / 账单");
    for (const [label, grid] of [["现金归还", "个人现金归还"], ["有票直接冲", "有票直接冲"], ["无票报销冲抵", "无票报销冲抵"]]) {
      await page.getByRole("button", { name: /个人专账视图$/ }).click();
      await show(grid, "reports/personal", () => page.getByRole("option", { name: label, exact: true }).click(), page.getByRole("grid", { name: grid, exact: true }));
    }
    await show("task_month", "task-occurrences", () => nav().getByRole("link", { name: "每月任务", exact: true }).click());
    await checkMenu("筛选任务状态");
    await show("task_templates", "tasks", () => page.getByRole("tab", { name: "任务配置", exact: true }).click(), page.getByRole("grid", { name: "任务模板" }));
    await checkMenu("筛选模板类别");
    await show("accounts", "settings/accounts", () => nav().getByRole("link", { name: "基础设置", exact: true }).click(), page.getByRole("grid", { name: "现金账户", exact: true }));
    await checkMenu("筛选账户状态");
    await show("categories", "settings/categories", () => page.getByRole("tab", { name: "费用类型", exact: true }).click());
    await checkMenu("筛选适用范围");
    await show("projects", "projects", () => page.getByRole("tab", { name: "OA 项目与可选阶段", exact: true }).click(), page.getByRole("grid", { name: "OA 项目列表" }));
    expect(await page.locator(".cash-checkbox-grid").getByRole("checkbox").count()).toBeGreaterThan(0);
    await checkMenu("筛选项目阶段");
    const guideCalls = cashCalls.length;
    await page.getByRole("tab", { name: "支付办理说明", exact: true }).click();
    await expect(page.getByRole("grid", { name: "支付办理参考" })).toBeVisible(); await twoFrames(page);
    expect(cashCalls).toHaveLength(guideCalls);

    // Return to the total before sampling repeated section switches. No mutation or mock response.
    await show("personal_return", "reports/personal", () => nav().getByRole("link", { name: "现金账目", exact: true }).click());
    await show("turnover_return", "reports/turnover", () => page.getByRole("tab", { name: "往来账总表", exact: true }).click());
    for (let index = 0; index < 100; index += 1) {
      await show("warm_flows", "flows", () => nav().getByRole("link", { name: "现金流水", exact: true }).click(), flowsGrid);
      await show("warm_turnover", "reports/turnover", () => nav().getByRole("link", { name: "现金账目", exact: true }).click());
    }
    cashActive = false;
    await nav().getByRole("link", { name: "银行明细", exact: true }).click();
    await expect(page.getByRole("grid", { name: "交易流水" })).toBeVisible();
    const cashCount = cashCalls.length;
    await page.getByRole("grid", { name: "交易流水" }).getByRole("columnheader").first().focus(); await twoFrames(page);
    expect(cashCalls).toHaveLength(cashCount); await expect(page.locator(".cash-workspace")).toHaveCount(0);
    expect(writes).toEqual([]); expect(failed).toEqual([]); expect(ordinaryDuringCash).toEqual([]);
    const metrics = Object.fromEntries(Object.entries(samples).map(([name, rows]) => [name, {
      count: rows.length, clickToPaintMs: percentiles(rows.map(row => row.clickToPaint)), responseToPaintMs: percentiles(rows.map(row => row.responseToPaint)),
    }]));
    console.log("CASH_READONLY_METRICS", JSON.stringify({ metrics, menuSamples: menuPaint.length, menuClickToVisibleMs: percentiles(menuPaint), menuPointerToVisibleMs: percentiles(menuPointerPaint), cashGetCount: cashCalls.length, blockedWrites: writes.length, failures: failed.length }));
  });
});

async function twoFrames(page: Page) {
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
}
function percentiles(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b);
  const at = (p: number) => Math.round(sorted[Math.ceil(sorted.length * p) - 1] * 100) / 100;
  return { p50: at(.5), p95: at(.95), p99: at(.99) };
}
