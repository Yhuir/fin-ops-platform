import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

type DrawerMotionSample = {
  elapsed: number;
  left: number;
  right: number;
  width: number;
};

async function armDrawerSampler(page: Page, durationMs = 360) {
  await page.evaluate((duration) => {
    const state = window as typeof window & {
      __drawerMotionDone?: boolean;
      __drawerMotionSamples?: DrawerMotionSample[];
    };
    state.__drawerMotionDone = false;
    state.__drawerMotionSamples = [];
    const startedAt = performance.now();
    const sample = (timestamp: number) => {
      const drawer = document.querySelector<HTMLElement>(".finance-drawer__content[data-placement='right']");
      if (drawer) {
        const rect = drawer.getBoundingClientRect();
        state.__drawerMotionSamples?.push({
          elapsed: timestamp - startedAt,
          left: rect.left,
          right: rect.right,
          width: rect.width,
        });
      }
      if (timestamp - startedAt < duration) {
        requestAnimationFrame(sample);
      } else {
        state.__drawerMotionDone = true;
      }
    };
    requestAnimationFrame(sample);
  }, durationMs);
}

async function drawerSamples(page: Page) {
  await expect.poll(() => page.evaluate(() => (
    window as typeof window & { __drawerMotionDone?: boolean }
  ).__drawerMotionDone)).toBe(true);
  return page.evaluate(() => (
    window as typeof window & { __drawerMotionSamples?: DrawerMotionSample[] }
  ).__drawerMotionSamples ?? []);
}

function expectFullWidthTravel(samples: DrawerMotionSample[], direction: "enter" | "exit") {
  expect(samples.length).toBeGreaterThan(3);
  const lefts = samples.map((sample) => sample.left);
  const minLeft = Math.min(...lefts);
  const maxLeft = Math.max(...lefts);
  const width = samples.find((sample) => sample.width > 0)?.width ?? 0;
  expect(width).toBeGreaterThan(0);
  expect(maxLeft - minLeft).toBeGreaterThan(width * 0.75);
  expect(lefts.some((left) => left > minLeft + 8 && left < maxLeft - 8)).toBe(true);
  if (direction === "enter") {
    expect(samples.at(-1)?.left).toBeCloseTo(minLeft, 0);
  } else {
    expect(samples.at(-1)?.left).toBeGreaterThan(minLeft + width * 0.5);
  }
}

async function openWorkbenchDetail(page: Page) {
  const row = page.getByTestId("candidate-group-unpaired-row:oa-large-202603-001");
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: /查看OA.*详情/ }).click();
  const drawer = page.getByRole("dialog", { name: "OA详情" });
  await expect(drawer).toBeVisible();
  return drawer;
}

test.describe("right drawer motion", () => {
  test("travels from and to the right edge without layout shift or close-time I/O", async ({ page }) => {
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

    const requestsBeforeOpen = api.calls.length;
    await armDrawerSampler(page);
    const drawer = await openWorkbenchDetail(page);
    const entering = await drawerSamples(page);
    expectFullWidthTravel(entering, "enter");
    const requestsAfterOpen = api.calls.length;
    expect(requestsAfterOpen - requestsBeforeOpen).toBeLessThanOrEqual(1);

    await armDrawerSampler(page, 300);
    await drawer.getByRole("button", { name: "关闭详情抽屉" }).click();
    const exiting = await drawerSamples(page);
    expectFullWidthTravel(exiting, "exit");
    await expect(drawer).toHaveCount(0);
    expect(api.calls.length).toBe(requestsAfterOpen);
    expect(await page.evaluate(() => (
      window as typeof window & { __drawerCls?: number }
    ).__drawerCls ?? 0)).toBe(0);
  });

  test("disables spatial transitions for reduced motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchLargeDataset: true,
    });
    await page.goto("/");

    const drawer = await openWorkbenchDetail(page);
    const motion = await drawer.locator("xpath=ancestor::*[contains(@class, 'finance-drawer__content')]").evaluate((element) => {
      const style = getComputedStyle(element);
      return { duration: style.transitionDuration, property: style.transitionProperty };
    });
    expect(motion.duration).toBe("0s");
    expect(motion.property).toBe("none");
  });
});
