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
  test("aligns standard page headers to the input invoice usage baseline", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await installDeterministicApiMocks(page, { sessionMode: "admin" });

    const routes = [
      { path: "/input-invoice-usage", title: "进项发票使用情况" },
      { path: "/pending-invoices", title: "待找发票" },
      { path: "/bank-details", title: "银行明细" },
    ] as const;

    let baseline: { top: number; left: number } | null = null;
    for (const route of routes) {
      await page.goto(route.path);
      const title = page.getByRole("heading", { name: route.title, exact: true });
      await expect(title).toBeVisible();
      const inset = await title.evaluate((heading) => {
        const pageBody = heading.closest(".page-body");
        if (!(pageBody instanceof HTMLElement)) throw new Error("page body missing");
        const headingRect = heading.getBoundingClientRect();
        const pageBodyRect = pageBody.getBoundingClientRect();
        return {
          top: headingRect.top - pageBodyRect.top,
          left: headingRect.left - pageBodyRect.left,
        };
      });
      if (baseline === null) {
        baseline = inset;
        continue;
      }
      expect(inset.top, route.path).toBeCloseTo(baseline.top, 1);
      expect(inset.left, route.path).toBeCloseTo(baseline.left, 1);
    }

    await page.goto("/operations/app-health");
    await expect(page.getByRole("heading", { name: "AppHealth 运维状态", exact: true })).toBeVisible();
    const operationsInset = await page.locator(".app-health-header").evaluate((header) => {
      const pageBody = header.closest(".page-body");
      if (!(pageBody instanceof HTMLElement)) throw new Error("page body missing");
      const headerRect = header.getBoundingClientRect();
      const pageBodyRect = pageBody.getBoundingClientRect();
      return {
        top: headerRect.top - pageBodyRect.top,
        left: headerRect.left - pageBodyRect.left,
      };
    });
    expect(operationsInset.top).toBeCloseTo(16, 1);
    expect(operationsInset.left).toBeCloseTo(16, 1);
  });

  test("opens the compact navigation drawer and closes it after route navigation", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const api = await installDeterministicApiMocks(page, { sessionMode: "user" });
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
    await drawer.getByRole("button", { name: "导入" }).click();
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
    await installDeterministicApiMocks(page, { sessionMode: "user" });
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

    const collapsedGeometry = await page.locator(".app-sidebar-link").evaluateAll((links) => links.map((link) => {
      const icon = link.querySelector<HTMLElement>(".app-sidebar-link-icon");
      const svg = icon?.querySelector<SVGElement>("svg");
      if (!icon || !svg) throw new Error("sidebar icon geometry missing");
      const linkRect = link.getBoundingClientRect();
      const iconRect = icon.getBoundingClientRect();
      const svgRect = svg.getBoundingClientRect();
      return {
        label: link.getAttribute("aria-label"),
        centerDeltaPx: Math.abs((linkRect.left + linkRect.width / 2) - (iconRect.left + iconRect.width / 2)),
        iconWidth: iconRect.width,
        svgWidth: svgRect.width,
        svgHeight: svgRect.height,
      };
    }));
    expect(collapsedGeometry.length).toBeGreaterThan(10);
    for (const item of collapsedGeometry) {
      expect(item.centerDeltaPx, JSON.stringify(item)).toBeLessThanOrEqual(0.5);
      expect(item.iconWidth, JSON.stringify(item)).toBeCloseTo(34, 1);
      expect(item.svgWidth, JSON.stringify(item)).toBeCloseTo(16, 1);
      expect(item.svgHeight, JSON.stringify(item)).toBeCloseTo(16, 1);
    }

    await expect(page.locator(".app-sidebar-brand-lockup")).toBeHidden();
    await expect(page.locator(".app-sidebar-brand-mark")).toBeHidden();
    const collapsedHeaderGeometry = await page.locator(".app-sidebar-brand").evaluate((brand) => {
      const sidebar = brand.closest<HTMLElement>(".app-sidebar");
      const toggle = brand.querySelector<HTMLElement>(".app-sidebar-toggle");
      if (!sidebar || !toggle) throw new Error("collapsed sidebar header geometry missing");
      const sidebarRect = sidebar.getBoundingClientRect();
      const toggleRect = toggle.getBoundingClientRect();
      return {
        centerDeltaPx: Math.abs(
          (sidebarRect.left + sidebarRect.width / 2)
          - (toggleRect.left + toggleRect.width / 2),
        ),
        toggleWidth: toggleRect.width,
        toggleHeight: toggleRect.height,
      };
    });
    expect(collapsedHeaderGeometry.centerDeltaPx).toBeLessThanOrEqual(0.5);
    expect(collapsedHeaderGeometry.toggleWidth).toBeCloseTo(32, 1);
    expect(collapsedHeaderGeometry.toggleHeight).toBeCloseTo(32, 1);
    const collapsedScreenshotPath = testInfo.outputPath("sidebar-collapsed.png");
    await page.locator(".app-sidebar").screenshot({ path: collapsedScreenshotPath });
    await testInfo.attach("sidebar-collapsed.png", { path: collapsedScreenshotPath, contentType: "image/png" });

    const measureSidebarMotion = (targetWidth: number) => page.evaluate(async (expectedWidth) => {
      const sidebarPaper = document.querySelector<HTMLElement>(".app-sidebar-paper");
      if (!sidebarPaper) throw new Error("sidebar paper missing");
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
        frames.push({ at: performance.now(), width: sidebarPaper.getBoundingClientRect().width });
      }
      observer.disconnect();
      const firstWidth = frames[0]?.width ?? 72;
      const motionStartIndex = frames.findIndex((frame) => Math.abs(frame.width - firstWidth) > 0.5);
      const targetIndex = frames.findIndex((frame, index) => (
        index >= motionStartIndex && Math.abs(frame.width - expectedWidth) <= 0.5
      ));
      const motionFrames = motionStartIndex >= 0 && targetIndex >= motionStartIndex
        ? frames.slice(motionStartIndex, targetIndex + 1)
        : [];
      const intervals = motionFrames.slice(1)
        .map((frame, index) => frame.at - motionFrames[index]!.at)
        .sort((a, b) => a - b);
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
        elapsedMs: motionFrames.length >= 2
          ? motionFrames.at(-1)!.at - motionFrames[0]!.at
          : Number.POSITIVE_INFINITY,
        firstWidth,
        lastWidth: frames.at(-1)?.width ?? 0,
        frameCount: intervals.length,
        frameMaxMs: intervals.at(-1) ?? 0,
        frameP50Ms: percentile(0.5),
        frameP95Ms: percentile(0.95),
      };
    }, targetWidth);
    const sidebarMotion = measureSidebarMotion(232);
    await page.getByRole("button", { name: "展开菜单" }).click();
    const motion = await sidebarMotion;
    await testInfo.attach("sidebar-expand-performance.json", {
      body: Buffer.from(JSON.stringify(motion, null, 2)),
      contentType: "application/json",
    });

    expect(motion.firstWidth).toBeCloseTo(72, 0);
    expect(motion.lastWidth).toBeCloseTo(232, 0);
    expect(motion.elapsedMs).toBeGreaterThanOrEqual(100);
    expect(motion.elapsedMs).toBeLessThanOrEqual(300);
    expect(motion.frameP95Ms, JSON.stringify(motion)).toBeLessThanOrEqual(25);
    expect(motion.cls).toBe(0);
    await expect(page.getByRole("button", { name: "折叠菜单" })).toBeVisible();

    await expect(page.getByText("财务运营平台").first()).toBeVisible();
    await expect(page.getByText("溯源办公系统").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "折叠菜单" })).toBeVisible();
    const expandedScreenshotPath = testInfo.outputPath("sidebar-expanded.png");
    await page.locator(".app-sidebar").screenshot({ path: expandedScreenshotPath });
    await testInfo.attach("sidebar-expanded.png", { path: expandedScreenshotPath, contentType: "image/png" });

    const toggle = page.locator(".app-sidebar-toggle");
    await toggle.focus();
    const sidebarCollapseMotion = measureSidebarMotion(72);
    await toggle.click();
    const collapseMotion = await sidebarCollapseMotion;
    await testInfo.attach("sidebar-collapse-performance.json", {
      body: Buffer.from(JSON.stringify(collapseMotion, null, 2)),
      contentType: "application/json",
    });

    expect(collapseMotion.firstWidth).toBeCloseTo(232, 0);
    expect(collapseMotion.lastWidth).toBeCloseTo(72, 0);
    expect(collapseMotion.elapsedMs).toBeGreaterThanOrEqual(100);
    expect(collapseMotion.elapsedMs).toBeLessThanOrEqual(300);
    expect(collapseMotion.frameP95Ms, JSON.stringify(collapseMotion)).toBeLessThanOrEqual(25);
    expect(collapseMotion.cls).toBe(0);
    await expect(page.getByRole("button", { name: "展开菜单" })).toBeVisible();
    await expect(page.locator(".app-sidebar-brand-mark")).toBeHidden();
    await expect(toggle).toBeFocused();

    await toggle.click();
    await expect(page.getByRole("button", { name: "折叠菜单" })).toBeVisible();
    await expect(page.locator(".app-sidebar-paper")).toHaveCSS("width", "232px");
    await toggle.click();
    await toggle.click();
    await expect(page.getByRole("button", { name: "折叠菜单" })).toBeVisible();
    await expect(toggle).toBeFocused();
  });
});
