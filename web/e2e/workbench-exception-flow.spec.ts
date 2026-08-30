import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

const AMOUNT_RULE_FAMILY_TITLES = [
  "OA = 流水",
  "OA = 发票",
  "流水 = 发票",
  "三项互异",
] as const;

test.describe("workbench exception browser flow", () => {
  test("loads bounded anomaly summaries and fetches detail only after expansion", async ({ page }) => {
    const groupRequestUrls: URL[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (request.method() === "GET" && url.pathname === "/api/workbench/groups") {
        groupRequestUrls.push(url);
      }
    });
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchAmountMismatchScenario: true,
      workbenchExceptionDatasetSize: 51,
      workbenchInitialRelationConfirmed: true,
    });

    await page.goto("/");
    await page
      .getByTestId("zone-unpaired")
      .getByRole("button", { name: /未配对异常 \d+ \| 已配对异常 \d+/ })
      .click();

    const drawer = page.getByRole("dialog", { name: "异常处理" });
    await expect(drawer.getByText("显示 10 / 51")).toBeVisible();
    expect(api.count("GET /api/workbench/groups")).toBe(1);
    expect(api.count("GET /api/workbench/groups/detail")).toBe(0);
    expect(groupRequestUrls[0]?.searchParams.get("exception_view")).toBe("amount");
    expect(groupRequestUrls[0]?.searchParams.has("exception_code")).toBe(false);

    await drawer.getByRole("button", { name: "展开异常明细" }).first().click();
    await expect(drawer.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeVisible();
    expect(api.count("GET /api/workbench/groups/detail")).toBe(1);

    await drawer.getByRole("button", { name: "加载更多异常" }).click();
    await expect(drawer.getByText("显示 20 / 51")).toBeVisible();
    expect(api.count("GET /api/workbench/groups")).toBe(2);
    const loadMoreUrl = groupRequestUrls.find((url) => url.searchParams.has("cursor"));
    expect(loadMoreUrl?.searchParams.get("cursor")).toBeTruthy();
    expect(loadMoreUrl?.searchParams.has("page")).toBe(false);
    expect(loadMoreUrl?.searchParams.get("exception_view")).toBe("amount");
    expect(loadMoreUrl?.searchParams.has("exception_code")).toBe(false);

    await drawer.getByRole("radio", { name: "三项不一致 0" }).click();
    await expect(drawer.getByText("当前分类没有金额异常。")).toBeVisible();
    const categoryUrl = [...groupRequestUrls].reverse().find((url) => (
      url.searchParams.get("exception_code") === "all_amounts_different"
    ));
    expect(categoryUrl?.searchParams.get("exception_view")).toBe("amount");
  });

  test("keeps the existing invoice-entry action available in the document-only drawer", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchOaInvoiceUnparsedScenario: true,
    });

    await page.goto("/");
    await page
      .getByTestId("zone-unpaired")
      .getByRole("button", { name: "未配对异常 1 | 已配对异常 0" })
      .click();

    const exceptionDrawer = page.getByRole("dialog", { name: "异常处理" });
    await expect(
      exceptionDrawer.locator(".workbench-anomaly-drawer__amount-filters"),
    ).toBeVisible();
    await exceptionDrawer.getByRole("radio", { name: "仅资料异常 1" }).click();
    await expect(
      exceptionDrawer.locator(".workbench-anomaly-drawer__amount-filters"),
    ).toHaveCount(0);
    await exceptionDrawer.getByRole("button", { name: "展开异常明细" }).click();
    const invoiceEntry = exceptionDrawer.getByRole("button", { name: "录入发票" });
    await expect(invoiceEntry).toBeEnabled();
    await expect(exceptionDrawer.getByRole("button", { name: "撤回关联" })).toHaveCount(0);
    await expect(exceptionDrawer.getByRole("checkbox")).toHaveCount(0);
    await invoiceEntry.click();

    await expect(exceptionDrawer).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "录入发票" })).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(1);
  });

  test("hands an unassigned invoice from the exception drawer to one OA-item drawer", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchInvoiceAssignmentScenario: true,
    });

    await page.goto("/");
    await page
      .getByTestId("zone-unpaired")
      .getByRole("button", { name: "未配对异常 1 | 已配对异常 0" })
      .click();

    const exceptionDrawer = page.getByRole("dialog", { name: "异常处理" });
    await exceptionDrawer.getByRole("radio", { name: "仅资料异常 1" }).click();
    await exceptionDrawer.getByRole("button", { name: "展开异常明细" }).click();
    const indicator = exceptionDrawer.getByRole("button", {
      name: "该发票有 1 项异常，查看详情",
    });
    await indicator.hover();
    await page.getByRole("button", { name: "选择 OA 明细" }).click();

    await expect(exceptionDrawer).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "选择 OA 明细" })).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(1);
  });

  test("reviews, accepts, and withdraws an automatically classified exact-cent mismatch", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchAmountMismatchScenario: true,
      workbenchMultiSourceScenario: true,
      workbenchInitialRelationConfirmed: true,
    });

    await page.goto("/");

    const pairedZone = page.getByTestId("zone-paired");
    const unpairedZone = page.getByTestId("zone-unpaired");
    const unpairedIndicator = unpairedZone.getByRole("button", {
      name: "该发票有 1 项异常，查看详情",
    });
    await expect(unpairedIndicator).toBeVisible();
    await expect(unpairedZone.getByText("OA附件", { exact: true })).toHaveCount(1);
    await expect(unpairedZone.getByText("明细归属", { exact: true })).toHaveCount(1);
    await expect(unpairedZone.getByText("人工导入", { exact: true })).toHaveCount(1);
    await expect(unpairedZone.getByText("导入记录", { exact: true })).toHaveCount(0);
    await expect(unpairedZone.getByText("OA 流水一致，票少")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "查看金额不一致差额说明" })).toHaveCount(0);
    await unpairedIndicator.hover();
    await expect(page.getByText("OA 流水一致，票少")).toBeVisible();
    const indicatorStyle = await unpairedIndicator.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        backgroundColor: style.backgroundColor,
        boxShadow: style.boxShadow,
        color: style.color,
        height: element.getBoundingClientRect().height,
        width: element.getBoundingClientRect().width,
      };
    });
    expect(indicatorStyle).toEqual({
      backgroundColor: "rgb(111, 61, 0)",
      boxShadow: "none",
      color: "rgb(255, 255, 255)",
      height: 28,
      width: 28,
    });
    await unpairedIndicator.click();
    await expect(page.getByText("OA 流水一致，票少")).toHaveCount(0);
    await page.waitForTimeout(180);
    await expect(page.getByText("OA 流水一致，票少")).toHaveCount(0);
    await unpairedIndicator.click();
    await expect(page.getByText("OA 流水一致，票少")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(pairedZone.getByRole("button", {
      name: "该发票有 1 项异常，查看详情",
    })).toHaveCount(0);
    await page
      .getByTestId("zone-unpaired")
      .getByRole("button", { name: "未配对异常 1 | 已配对异常 0" })
      .click();

    const drawer = page.getByRole("dialog", { name: "异常处理" });
    const collapsedIndicator = drawer.getByRole("button", {
      name: "该关联组有 1 项异常，查看详情",
    });
    await expect(collapsedIndicator).toBeVisible();
    const collapsedHeading = drawer.locator(".workbench-anomaly-drawer__heading").first();
    await expect(collapsedHeading.getByText("OA 流水一致，票少")).toHaveCount(0);
    await collapsedIndicator.hover();
    const collapsedPopover = page.getByRole("dialog", { name: "该关联组异常详情" });
    await expect(collapsedPopover.getByText("OA 流水一致，票少")).toBeVisible();
    await expect(collapsedPopover.getByText("确认关联备注")).toBeVisible();
    await expect(collapsedPopover.getByText("票面金额少 0.01 元，经确认保留关联")).toBeVisible();
    await collapsedIndicator.click();
    await expect(collapsedPopover).toHaveCount(0);
    await collapsedIndicator.click();
    await expect(page.getByRole("dialog", { name: "该关联组异常详情" })).toBeVisible();
    await page.keyboard.press("Escape");
    await drawer.getByRole("button", { name: "展开异常明细" }).first().click();
    await expect(drawer.getByRole("button", {
      name: "该发票有 1 项异常，查看详情",
    })).toBeVisible();
    await expect(drawer.getByText("OA附件", { exact: true })).toHaveCount(1);
    await expect(drawer.getByText("明细归属", { exact: true })).toHaveCount(1);
    await expect(drawer.getByText("人工导入", { exact: true })).toHaveCount(0);
    await expect(drawer.getByText("导入记录", { exact: true })).toHaveCount(0);
    await expect(drawer.getByRole("button", { name: /人工金额判断/ })).toHaveCount(0);
    await expect(drawer.getByRole("checkbox")).toHaveCount(0);
    const workbenchLoadsBeforeAccept = api.count("GET /api/workbench");
    const bucketLoadsBeforeAccept = api.count("GET /api/workbench/groups");
    await drawer.getByRole("button", { name: "接受异常并进入已配对" }).click();

    await expect(drawer.getByRole("radio", { name: "未配对异常 0" })).toHaveAttribute("aria-checked", "true");
    await expect(drawer.getByText("当前分类没有金额异常。")).toBeVisible();
    await expect(pairedZone.getByRole("button", {
      name: "该发票有 1 项异常，查看详情",
    })).toBeVisible();
    expect(api.count("POST /api/workbench/exceptions/review")).toBe(1);
    expect(api.lastBody("POST /api/workbench/exceptions/review")).toMatchObject({
      month: "all",
      zone: "unpaired",
      group_id: "case:CASE-202603-101",
      fingerprint: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      decision: "accept_paired",
    });
    expect(api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeAccept + 1);
    expect(api.count("GET /api/workbench/groups")).toBe(bucketLoadsBeforeAccept + 1);
    await expect(unpairedZone.getByRole("button", {
      name: "未配对异常 0 | 已配对异常 1",
    })).toBeVisible();

    await drawer.getByRole("radio", { name: "已配对异常 1" }).click();
    await collapsedIndicator.hover();
    const reviewedPopover = page.getByRole("dialog", { name: "该关联组异常详情" });
    await expect(reviewedPopover.getByText("已接受该异常风险")).toBeVisible();
    await expect(reviewedPopover.getByText("操作账户")).toBeVisible();
    await expect(reviewedPopover.getByText("E2E-REVIEWER（浏览器测试员）")).toBeVisible();
    await expect(reviewedPopover.getByText("操作时间")).toBeVisible();
    await expect(reviewedPopover.getByText("2026-08-25 17:03:47")).toBeVisible();
    await expect(reviewedPopover).not.toContainText("+08:00");
    await page.keyboard.press("Escape");
    await expect(unpairedZone.getByRole("button", {
      name: "该发票有 1 项异常，查看详情",
    })).toHaveCount(0);

    const workbenchLoadsBeforeWithdraw = api.count("GET /api/workbench");
    const bucketLoadsBeforeWithdraw = api.count("GET /api/workbench/groups");
    await drawer.getByRole("button", { name: "展开异常明细" }).first().click();
    await drawer.getByRole("button", { name: "撤回到未配对" }).click();

    await expect(drawer.getByRole("radio", { name: "已配对异常 0" })).toHaveAttribute("aria-checked", "true");
    await expect(drawer.getByText("当前分类没有金额异常。")).toBeVisible();
    await expect(unpairedZone.getByRole("button", {
      name: "该发票有 1 项异常，查看详情",
    })).toBeVisible();
    await expect(pairedZone.getByRole("button", {
      name: "该发票有 1 项异常，查看详情",
    })).toHaveCount(0);
    expect(api.count("POST /api/workbench/exceptions/review")).toBe(2);
    expect(api.lastBody("POST /api/workbench/exceptions/review")).toMatchObject({
      month: "all",
      zone: "paired",
      group_id: "case:CASE-202603-101",
      fingerprint: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      decision: "keep_unpaired",
    });
    expect(api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeWithdraw + 1);
    expect(api.count("GET /api/workbench/groups")).toBe(bucketLoadsBeforeWithdraw + 1);
    await expect(unpairedZone.getByRole("button", {
      name: "未配对异常 1 | 已配对异常 0",
    })).toBeVisible();
    await drawer.getByRole("button", { name: "关闭抽屉" }).click();
    await expect(drawer).toHaveCount(0);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("keeps the wider compact drawer inside the viewport without clipping review controls", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchAmountMismatchScenario: true,
      workbenchInitialRelationConfirmed: true,
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await page
      .getByTestId("zone-unpaired")
      .getByRole("button", { name: "未配对异常 1 | 已配对异常 0" })
      .click();

    const drawer = page.getByRole("dialog", { name: "异常处理" });
    await expect(drawer).toBeVisible();
    const expectExceptionFilterLayout = async () => {
      const header = drawer.locator(".finance-drawer__header");
      const bucketControls = drawer.getByRole("radiogroup", { name: "异常状态" });
      const exceptionType = drawer.getByRole("radiogroup", { name: "异常类型" });
      const amountFilters = drawer.locator(".workbench-anomaly-drawer__amount-filters");

      await expect(header.getByRole("heading", { name: "异常处理" })).toBeVisible();
      await expect(bucketControls).toBeVisible();
      await expect(exceptionType).toBeVisible();
      await expect(amountFilters).toBeVisible();
      for (const title of AMOUNT_RULE_FAMILY_TITLES) {
        await expect(amountFilters.getByText(title, { exact: true })).toBeVisible();
      }
      await expect(amountFilters.getByRole("radio")).toHaveCount(7);
      await expect.poll(async () => amountFilters.evaluate(
        (element) => getComputedStyle(element).gridTemplateColumns.split(" ").length,
      )).toBe(4);

      await expect.poll(async () => {
        const [exceptionTypeBox, amountFiltersBox] = await Promise.all([
          exceptionType.boundingBox(),
          amountFilters.boundingBox(),
        ]);
        if (!exceptionTypeBox || !amountFiltersBox) {
          return Number.NEGATIVE_INFINITY;
        }
        return amountFiltersBox.y - (exceptionTypeBox.y + exceptionTypeBox.height);
      }).toBeGreaterThanOrEqual(-1);

      await expect.poll(async () => amountFilters.evaluate(
        (element) => element.scrollWidth - element.clientWidth,
      )).toBeLessThanOrEqual(1);
      await expect.poll(async () => {
        const [headerBox, bucketBox] = await Promise.all([
          header.boundingBox(),
          bucketControls.boundingBox(),
        ]);
        if (!headerBox || !bucketBox) {
          return Number.POSITIVE_INFINITY;
        }
        return Math.abs(
          (bucketBox.y + bucketBox.height / 2) - (headerBox.y + headerBox.height / 2),
        );
      }).toBeLessThanOrEqual(2);
      await expect.poll(async () => drawer.evaluate(
        (element) => element.scrollWidth - element.clientWidth,
      )).toBeLessThanOrEqual(1);
      await expect.poll(async () => page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )).toBeLessThanOrEqual(1);
    };

    await expectExceptionFilterLayout();
    await expect.poll(async () => {
      const box = await drawer.boundingBox();
      return box ? box.x + box.width : Number.POSITIVE_INFINITY;
    }).toBeLessThanOrEqual(1440);
    const collapsedBox = await drawer.boundingBox();
    expect(collapsedBox).not.toBeNull();
    expect(collapsedBox!.x).toBeGreaterThanOrEqual(0);
    expect(collapsedBox!.x + collapsedBox!.width).toBeLessThanOrEqual(1440);
    await expect(drawer.locator(".workbench-anomaly-drawer__heading").getByText("OA 流水一致，票少")).toHaveCount(0);

    await drawer.getByRole("button", { name: "展开异常明细" }).first().click();
    const review = drawer.getByRole("region", { name: "异常审阅" });
    await review.scrollIntoViewIfNeeded();
    await expect(drawer.getByRole("button", {
      name: "该发票有 1 项异常，查看详情",
    })).toBeVisible();
    await expect(review.getByRole("button", { name: /人工金额判断/ })).toHaveCount(0);
    await expect(review.getByRole("checkbox")).toHaveCount(0);
    await expect(review.getByRole("button", { name: "留在未配对" })).toBeVisible();
    await expect(review.getByRole("button", { name: "接受异常并进入已配对" })).toBeVisible();
    const reviewBox = await review.boundingBox();
    expect(reviewBox).not.toBeNull();
    expect(reviewBox!.x).toBeGreaterThanOrEqual(collapsedBox!.x);
    expect(reviewBox!.x + reviewBox!.width).toBeLessThanOrEqual(collapsedBox!.x + collapsedBox!.width);

    await page.setViewportSize({ width: 1024, height: 768 });
    await expectExceptionFilterLayout();
    await expect.poll(async () => {
      const box = await drawer.boundingBox();
      return box ? box.x + box.width : Number.POSITIVE_INFINITY;
    }).toBeLessThanOrEqual(1024);
    const compactDrawerBox = await drawer.boundingBox();
    const compactReviewBox = await review.boundingBox();
    expect(compactDrawerBox).not.toBeNull();
    expect(compactReviewBox).not.toBeNull();
    expect(compactDrawerBox!.x + compactDrawerBox!.width).toBeLessThanOrEqual(1024);
    expect(compactReviewBox!.x + compactReviewBox!.width)
      .toBeLessThanOrEqual(compactDrawerBox!.x + compactDrawerBox!.width);
  });
});
