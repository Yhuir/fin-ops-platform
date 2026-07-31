import { expect, test, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";

function createAppShellLatencyRecorder(page: Parameters<typeof createOperationLatencyRecorder>[0], testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/",
    pageKey: "app-shell-navigation",
    module: "app-shell-navigation",
  });
}

test.describe("app shell responsive browser smoke", () => {
  test("opens the compact navigation drawer and closes it after route navigation", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createAppShellLatencyRecorder(page, testInfo);

    await recordLatency({
      route: "/cost-statistics",
      operationId: "app-shell.open-cost-statistics-mobile",
      visibleLabel: "成本统计",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/cost-statistics");
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible());
    });

    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    const openMenuButton = page.locator("button[aria-label='打开菜单']");
    await expect(openMenuButton).toBeVisible();

    const drawer = page.getByRole("dialog", { name: "主导航菜单" });
    await recordLatency({
      route: "/cost-statistics",
      operationId: "app-shell.open-compact-navigation-drawer",
      visibleLabel: "打开菜单",
      actionType: "click",
    }, async (mark) => {
      await openMenuButton.click();
      await mark("finalSettledLatencyMs", expect(drawer).toBeVisible());
    });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("link", { name: "设置" })).toBeVisible();
    await expect(drawer.getByRole("link", { name: "银行流水导入" })).toBeVisible();

    const sessionRequestsBeforeAccount = api.count("GET /api/session/me");
    const accountDialog = page.getByRole("dialog", { name: "当前 OA 账号详情" });
    await page.evaluate(() => {
      const trigger = document.querySelector<HTMLElement>(".app-sidebar-account-trigger");
      if (!trigger) throw new Error("account trigger missing");
      trigger.addEventListener("click", () => {
        const state = window as typeof window & {
          __accountFirstVisibleMs?: number;
          __accountSettledMs?: number;
        };
        const startedAt = performance.now();
        const sample = () => {
          const popover = document.querySelector<HTMLElement>(".app-sidebar-account-popover");
          if (popover && state.__accountFirstVisibleMs === undefined && Number.parseFloat(getComputedStyle(popover).opacity) > 0) {
            state.__accountFirstVisibleMs = performance.now() - startedAt;
          }
          if (popover && !popover.hasAttribute("data-entering")) {
            state.__accountSettledMs = performance.now() - startedAt;
            return;
          }
          requestAnimationFrame(sample);
        };
        requestAnimationFrame(sample);
      }, { once: true });
    });
    await recordLatency({
      route: "/cost-statistics",
      operationId: "app-shell.open-current-oa-account",
      visibleLabel: "当前 OA 账号详情",
      actionType: "click",
    }, async (mark) => {
      await drawer.getByRole("button", { name: "当前账号：浏览器测试用户" }).click();
      await mark("finalSettledLatencyMs", expect(accountDialog).toBeVisible());
    });
    await page.waitForFunction(() => (
      window as typeof window & { __accountSettledMs?: number }
    ).__accountSettledMs !== undefined);
    const accountPerformance = await page.evaluate(() => {
      const state = window as typeof window & {
        __accountFirstVisibleMs?: number;
        __accountSettledMs?: number;
      };
      return {
        firstVisibleMs: state.__accountFirstVisibleMs ?? Number.POSITIVE_INFINITY,
        settledMs: state.__accountSettledMs ?? Number.POSITIVE_INFINITY,
      };
    });
    await testInfo.attach("account-popover-performance.json", {
      body: Buffer.from(JSON.stringify(accountPerformance, null, 2)),
      contentType: "application/json",
    });
    expect(accountPerformance.firstVisibleMs).toBeLessThanOrEqual(100);
    expect(accountPerformance.settledMs).toBeLessThanOrEqual(250);
    await expect(accountDialog).toContainText("E2EUSER001");
    await expect(accountDialog).toContainText("财务部");
    await page.keyboard.press("Escape");
    await expect(accountDialog).toBeHidden();
    expect(api.count("GET /api/session/me")).toBe(sessionRequestsBeforeAccount);

    await recordLatency({
      route: "/settings",
      operationId: "app-shell.navigate-drawer-to-settings",
      visibleLabel: "设置",
      actionType: "click",
    }, async (mark) => {
      await drawer.getByRole("link", { name: "设置" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(drawer).toBeHidden());
    });

    await expect(page).toHaveURL(/\/settings$/);
    await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
    await expect(drawer).toBeHidden();
  });

  test("keeps embedded OA shell collapsed but expandable on desktop", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createAppShellLatencyRecorder(page, testInfo);

    await recordLatency({
      route: "/",
      operationId: "app-shell.open-embedded-oa-shell",
      visibleLabel: "embedded OA shell",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/?embedded=oa");
      await mark("finalSettledLatencyMs", expect(page.locator(".app-shell.embedded-shell")).toBeVisible());
    });

    await expect(page.locator(".app-shell.embedded-shell")).toBeVisible();
    await expect(page.locator(".page-body.embedded")).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-o-202603-001")).toBeVisible();
    await expect(page.getByRole("link", { name: "关联台" })).toBeVisible();
    await expect(page.getByRole("button", { name: "展开菜单" })).toBeVisible();
    await expect(page.getByRole("button", { name: "打开菜单" })).toHaveCount(0);

    const sidebarMotion = page.evaluate(async () => {
      const sidebar = document.querySelector<HTMLElement>(".app-sidebar");
      if (!sidebar) throw new Error("sidebar missing");
      let cls = 0;
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          const shift = entry as PerformanceEntry & { hadRecentInput?: boolean; value?: number };
          if (!shift.hadRecentInput) cls += shift.value ?? 0;
        }
      });
      observer.observe({ type: "layout-shift" });

      const frames: Array<{ at: number; width: number }> = [];
      const startedAt = performance.now();
      while (performance.now() - startedAt < 420) {
        await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
        frames.push({ at: performance.now(), width: sidebar.getBoundingClientRect().width });
      }
      observer.disconnect();
      const firstWidth = frames[0]?.width ?? 72;
      const motionStart = frames.find((frame) => Math.abs(frame.width - firstWidth) > 0.5)?.at ?? startedAt;
      const target = frames.find((frame) => frame.width >= 231.5)?.at ?? Number.POSITIVE_INFINITY;
      const intervals = frames.slice(1).map((frame, index) => frame.at - frames[index]!.at).sort((a, b) => a - b);
      const percentile = (ratio: number) => {
        if (intervals.length === 0) return 0;
        const rank = (intervals.length - 1) * ratio;
        const lower = Math.floor(rank);
        const upper = Math.ceil(rank);
        const weight = rank - lower;
        return intervals[lower]! * (1 - weight) + intervals[upper]! * weight;
      };
      return {
        cls,
        elapsedMs: target - motionStart,
        firstWidth,
        lastWidth: frames.at(-1)?.width ?? 0,
        frameCount: intervals.length,
        frameMaxMs: intervals.at(-1) ?? 0,
        frameP50Ms: percentile(0.5),
        frameP95Ms: percentile(0.95),
      };
    });
    await page.getByRole("button", { name: "展开菜单" }).click();
    const motion = await sidebarMotion;
    await testInfo.attach("sidebar-expand-performance.json", {
      body: Buffer.from(JSON.stringify(motion, null, 2)),
      contentType: "application/json",
    });

    expect(motion.firstWidth).toBeCloseTo(72, 0);
    expect(motion.lastWidth).toBeCloseTo(232, 0);
    expect(motion.elapsedMs).toBeLessThanOrEqual(300);
    expect(motion.frameP95Ms, JSON.stringify(motion)).toBeLessThanOrEqual(25);
    expect(motion.cls).toBe(0);
    await expect(page.getByRole("button", { name: "折叠菜单" })).toBeVisible();

    await expect(page.getByText("财务运营平台").first()).toBeVisible();
    await expect(page.getByText("溯源办公系统").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "折叠菜单" })).toBeVisible();
  });
});
