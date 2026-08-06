import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

type DrawerMotionSample = {
  elapsed: number;
  left: number;
  right: number;
  width: number;
  viewportWidth: number;
};

async function armDrawerSampler(page: Page) {
  await page.evaluate(() => {
    const state = window as typeof window & {
      __drawerMotionDone?: boolean;
      __drawerMotionSamples?: DrawerMotionSample[];
    };
    state.__drawerMotionDone = false;
    state.__drawerMotionSamples = [];
    const startedAt = performance.now();
    let observedContent: HTMLElement | null = null;
    let observer: MutationObserver;
    const finish = () => {
      observer.disconnect();
      state.__drawerMotionDone = true;
    };
    const sampleDrawer = (timestamp: number) => {
      const content = document.querySelector<HTMLElement>(
        ".finance-drawer__content[data-placement='right']",
      );
      const drawer = content?.querySelector<HTMLElement>(".finance-drawer") ?? null;
      if (drawer) {
        const rect = drawer.getBoundingClientRect();
        state.__drawerMotionSamples?.push({
          elapsed: timestamp - startedAt,
          left: rect.left,
          right: rect.right,
          width: rect.width,
          viewportWidth: window.innerWidth,
        });
      }
      if (content && drawer && content !== observedContent) {
        observedContent = content;
        content.addEventListener("transitionend", (event) => {
          if (event.propertyName !== "translate" || (event.target !== content && event.target !== drawer)) {
            return;
          }
          sampleDrawer(performance.now());
          finish();
        });
      }
      if (!content && observedContent && !observedContent.isConnected) {
        finish();
      }
    };
    observer = new MutationObserver(() => sampleDrawer(performance.now()));
    observer.observe(document.body, { childList: true, subtree: true });
    const sampleFrame = (timestamp: number) => {
      sampleDrawer(timestamp);
      if (!state.__drawerMotionDone) {
        requestAnimationFrame(sampleFrame);
      }
    };
    requestAnimationFrame(sampleFrame);
  });
}

async function drawerSamples(page: Page) {
  await expect.poll(() => page.evaluate(() => (
    window as typeof window & { __drawerMotionDone?: boolean }
  ).__drawerMotionDone)).toBe(true);
  return page.evaluate(() => {
    const samples = (
      window as typeof window & { __drawerMotionSamples?: DrawerMotionSample[] }
    ).__drawerMotionSamples ?? [];
    const drawer = document.querySelector<HTMLElement>(
      ".finance-drawer__content[data-placement='right'] .finance-drawer",
    );
    if (drawer) {
      const rect = drawer.getBoundingClientRect();
      samples.push({
        elapsed: (samples.at(-1)?.elapsed ?? 0) + 1,
        left: rect.left,
        right: rect.right,
        width: rect.width,
        viewportWidth: window.innerWidth,
      });
    }
    return samples;
  });
}

function expectFullWidthTravel(samples: DrawerMotionSample[], direction: "enter" | "exit") {
  const frames = samples.filter((sample) => sample.width > 0);
  expect(frames.length).toBeGreaterThan(3);
  const lefts = frames.map((sample) => sample.left);
  const minLeft = Math.min(...lefts);
  const maxLeft = Math.max(...lefts);
  const width = frames[0]?.width ?? 0;
  const openFrame = direction === "enter" ? frames.at(-1) : frames[0];
  const closedFrame = direction === "enter" ? frames[0] : frames.at(-1);
  const intermediateIndex = frames.findIndex((sample) => (
    sample.left > (openFrame?.left ?? 0) + 8
    && sample.left < (closedFrame?.left ?? 0) - 8
  ));
  expect(width).toBeGreaterThan(0);
  expect(maxLeft - minLeft).toBeGreaterThan(width * 0.75);
  expect(Math.abs((openFrame?.right ?? 0) - (openFrame?.viewportWidth ?? 0))).toBeLessThanOrEqual(2);
  // HeroUI removes the modal at transition end, so the last paint sampled before
  // removal can trail the computed 100% endpoint by a few pixels under load.
  const exitEndpointTolerance = Math.max(2, width * 0.01);
  expect(closedFrame?.left).toBeGreaterThanOrEqual(
    (closedFrame?.viewportWidth ?? 0) - exitEndpointTolerance,
  );
  expect(intermediateIndex).toBeGreaterThan(0);
  expect(frames[intermediateIndex]?.left).toBeGreaterThan(openFrame?.left ?? 0);
  expect(frames[intermediateIndex]?.left).toBeLessThan(closedFrame?.left ?? 0);
  if (direction === "enter") {
    expect(intermediateIndex).toBeLessThan(frames.length - 1);
    expect(openFrame?.left).toBeCloseTo(minLeft, 0);
  } else {
    expect(closedFrame?.left).toBeCloseTo(maxLeft, 0);
  }
}

async function openWorkbenchDetail(page: Page) {
  const row = page.getByTestId("candidate-group-unpaired-row:oa-large-202603-001");
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: /查看OA.*详情/ }).evaluate((button: HTMLElement) => button.click());
  const drawer = page.getByRole("dialog", { name: "OA详情" });
  await expect(drawer).toBeVisible();
  return drawer;
}

test.describe("right drawer motion", () => {
  test("travels without layout shift or close-triggered non-periodic business I/O", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchLargeDataset: true,
    });
    await page.goto("/");
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-large-202603-001")).toBeVisible();

    await page.evaluate(() => {
      const state = window as typeof window & { __drawerCls?: number };
      state.__drawerCls = 0;
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          const shift = entry as PerformanceEntry & { hadRecentInput?: boolean; value?: number };
          if (!shift.hadRecentInput) state.__drawerCls = (state.__drawerCls ?? 0) + (shift.value ?? 0);
        }
      }).observe({ type: "layout-shift", buffered: true });
    });

    const workbenchSelfConvergenceCalls = new Set([
      "GET /api/oa-sync/status",
      "GET /api/workbench",
      "GET /api/workbench/refresh-status",
    ]);
    const businessCallCount = () => api.calls.filter(
      (call) => !workbenchSelfConvergenceCalls.has(call),
    ).length;
    const detailRequest = "GET /api/workbench/rows/oa-large-202603-001";
    const detailRequestsBeforeOpen = api.count(detailRequest);
    const requestsBeforeOpen = businessCallCount();
    await armDrawerSampler(page);
    const drawer = await openWorkbenchDetail(page);
    const entering = await drawerSamples(page);
    expectFullWidthTravel(entering, "enter");
    const requestsAfterOpen = businessCallCount();
    expect(requestsAfterOpen - requestsBeforeOpen).toBeLessThanOrEqual(1);
    expect(api.count(detailRequest)).toBe(detailRequestsBeforeOpen + 1);

    await armDrawerSampler(page);
    await drawer.getByRole("button", { name: "关闭详情抽屉" }).click();
    const exiting = await drawerSamples(page);
    expectFullWidthTravel(exiting, "exit");
    await expect(drawer).toHaveCount(0);
    expect(businessCallCount()).toBe(requestsAfterOpen);
    expect(await page.evaluate(() => (
      window as typeof window & { __drawerCls?: number }
    ).__drawerCls ?? 0)).toBeLessThan(0.01);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("applies the same viewport motion to the migrated bank-flow modal", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    await page.goto("/bank-flow-rule-batches");
    const opener = page.getByRole("button", { name: "流水规则标签管理" });
    await expect(opener).toBeEnabled();

    await armDrawerSampler(page);
    await opener.click();
    const drawer = page.getByRole("dialog", { name: "流水规则标签管理" });
    await expect(drawer).toBeVisible();
    expectFullWidthTravel(await drawerSamples(page), "enter");
    const requestsBeforeClose = api.calls.length;

    await armDrawerSampler(page);
    await drawer.getByRole("button", { name: "关闭流水规则标签管理" }).click();
    expectFullWidthTravel(await drawerSamples(page), "exit");
    await expect(drawer).toHaveCount(0);
    expect(api.calls.length).toBe(requestsBeforeClose);
    expect(api.count("PUT /api/bank-flow-rule-batches/tag-rules")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("covers the OA bank-link modal lifecycle and blocks dismissal while candidates load", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentBankLinkFlow: true,
      sessionMode: "full_access",
    });
    let releaseCandidates!: () => void;
    const candidatesGate = new Promise<void>((resolve) => {
      releaseCandidates = resolve;
    });
    await page.route("**/api/oa-pending-payments/bank-transaction-candidates*", async (route) => {
      await candidatesGate;
      await route.fallback();
    });
    await page.goto("/oa-pending-payments");
    await page.getByRole("button", { name: /进行中 OA/ }).click();
    const row = page.getByRole("row", { name: /进行中关联申请人/ });
    await expect(row).toBeVisible();
    await row.getByRole("checkbox", { name: /选择 OA 进行中关联申请人/ }).check();
    const opener = page.getByRole("button", { name: "关联支出流水" });
    await expect(opener).toBeEnabled();

    await armDrawerSampler(page);
    await opener.click();
    const drawer = page.getByRole("dialog", { name: "关联支出流水抽屉" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText("加载中")).toBeVisible();
    await expect(drawer.getByRole("button", { name: "取消" })).toBeDisabled();
    await expect(drawer.getByRole("button", { name: "关闭关联支出流水抽屉" })).toBeDisabled();
    await page.keyboard.press("Escape");
    await page.locator(".finance-drawer__backdrop").evaluate((backdrop: HTMLElement) => backdrop.click());
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText("加载中")).toBeVisible();
    releaseCandidates();
    await expect(drawer.getByText("显示 3 / 3 条")).toBeVisible();
    expectFullWidthTravel(await drawerSamples(page), "enter");
    const requestsBeforeClose = api.calls.length;

    await armDrawerSampler(page);
    await drawer.getByRole("button", { name: "关闭关联支出流水抽屉" }).click();
    expectFullWidthTravel(await drawerSamples(page), "exit");
    await expect(drawer).toHaveCount(0);
    expect(api.calls.length).toBe(requestsBeforeClose);
    expect(api.count("POST /api/oa-pending-payments/link-bank-transactions")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("applies viewport motion and safe exit state to the production persistent drawer", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    await page.goto("/input-invoice-usage");
    const opener = page.getByRole("button", { name: "以发票反提 OA" });
    await expect(opener).toBeEnabled();

    await armDrawerSampler(page);
    await opener.click();
    const workflow = page.getByLabel("以发票反提 OA 工作流", { exact: true });
    await expect(workflow).toBeVisible();
    expectFullWidthTravel(await drawerSamples(page), "enter");
    const requestsBeforeClose = api.calls.length;

    await armDrawerSampler(page);
    await page.getByRole("button", { name: "关闭以发票反提 OA 工作流" }).click();
    const persistentDrawer = page.locator(".finance-drawer__content--persistent");
    await expect(persistentDrawer).toHaveAttribute("data-exiting", "true");
    await expect(persistentDrawer).toHaveAttribute("inert", "");
    await expect(opener).toBeFocused();
    expectFullWidthTravel(await drawerSamples(page), "exit");
    await expect(persistentDrawer).toHaveCount(0);
    expect(api.calls.length).toBe(requestsBeforeClose);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/oa-draft")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("keeps the tax results rail mounted and inert while collapsed", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    await page.goto("/tax-offset");
    const rail = page.getByRole("complementary", { name: "已认证结果" });
    const body = rail.locator("#tax-certified-results-body");
    await expect(body).toBeVisible();

    const requestsBeforeCollapse = api.calls.length;
    await rail.getByRole("button", { name: /收起已认证结果/ }).click();
    await expect(body).toBeAttached();
    await expect(body).toHaveAttribute("aria-hidden", "true");
    await expect(body).toHaveAttribute("inert", "");
    await expect(rail.getByRole("button", { name: /展开已认证结果/ })).toHaveAttribute("aria-expanded", "false");
    expect(api.calls.length).toBe(requestsBeforeCollapse);

    const requestsBeforeExpand = api.calls.length;
    await rail.getByRole("button", { name: /展开已认证结果/ }).click();
    await expect(body).toHaveAttribute("aria-hidden", "false");
    await expect(rail.getByRole("button", { name: /收起已认证结果/ })).toHaveAttribute("aria-expanded", "true");
    expect(api.calls.length).toBe(requestsBeforeExpand);
    expect(api.count("POST /api/tax-offset/plans")).toBe(0);
    expect(api.count("POST /api/tax-offset/certified-import/confirm")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("disables spatial transitions for reduced motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchLargeDataset: true,
    });
    await page.goto("/");

    const drawer = await openWorkbenchDetail(page);
    const motion = await drawer.evaluate((element) => {
      const style = getComputedStyle(element);
      const durationMs = style.transitionDuration.split(",").reduce((maximum, duration) => {
        const value = Number.parseFloat(duration);
        const milliseconds = duration.trim().endsWith("ms") ? value : value * 1_000;
        return Math.max(maximum, milliseconds);
      }, 0);
      return { durationMs, property: style.transitionProperty };
    });
    expect(motion.durationMs).toBeLessThanOrEqual(1);
    expect(["none", "translate"]).toContain(motion.property);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
