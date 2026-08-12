import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

test.describe("workbench exception browser flow", () => {
  test("applies a unified exception with exactly one direct combined reread", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchInitialRelationConfirmed: true,
    });

    await page.goto("/");
    const pairedGroup = page.getByTestId("candidate-group-paired-case:CASE-202603-101");
    const bankRow = pairedGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ });
    await bankRow.getByRole("button", { name: "更多操作" }).click();
    await page.getByRole("menuitem", { name: "异常处理" }).click();

    const modal = page.getByRole("dialog", { name: "统一异常处理" });
    await expect(modal).toBeVisible();
    await modal
      .getByText("追进项发票", { exact: true })
      .locator("xpath=ancestor::label[1]")
      .click();
    await modal.getByLabel("备注").fill("direct exception e2e");
    const workbenchLoadsBeforeApply = api.count("GET /api/workbench");
    await modal.getByRole("button", { name: "提交处理" }).click();

    await expect(modal).toHaveCount(0);
    expect(api.count("POST /api/workbench/exception/apply")).toBe(1);
    await expect.poll(() => api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeApply + 1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
  });

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
      .getByRole("button", { name: /异常 \d+ \| 已忽略 \d+/ })
      .click();

    const drawer = page.getByRole("dialog", { name: "异常处理" });
    await expect(drawer.getByText("50 / 51 项")).toBeVisible();
    expect(api.count("GET /api/workbench/groups")).toBe(2);
    expect(api.count("GET /api/workbench/groups/detail")).toBe(0);

    await drawer.getByRole("button", { name: "展开异常明细" }).first().click();
    await expect(drawer.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeVisible();
    expect(api.count("GET /api/workbench/groups/detail")).toBe(1);

    await drawer.getByRole("button", { name: "加载更多异常" }).click();
    await expect(drawer.getByText("51 项")).toBeVisible();
    expect(api.count("GET /api/workbench/groups")).toBe(3);
    const loadMoreUrl = groupRequestUrls.find((url) => url.searchParams.has("cursor"));
    expect(loadMoreUrl?.searchParams.get("cursor")).toBeTruthy();
    expect(loadMoreUrl?.searchParams.has("page")).toBe(false);
  });

  test("keeps row-ignore state out of the OA invoice anomaly drawer", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/");

    const openZone = page.getByTestId("zone-unpaired");
    const openGroup = page.getByTestId("candidate-group-unpaired-row:iv-o-202603-001");
    await expect(openGroup).toBeVisible();
    const invoiceRow = openGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ });
    await expect(invoiceRow).toBeVisible();

    const workbenchLoadsBeforeIgnore = api.count("GET /api/workbench");
    await invoiceRow.getByRole("button", { name: "更多操作" }).click();
    await page.getByRole("menuitem", { name: "忽略" }).click();

    await expect(openGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })).toHaveCount(0);
    await expect(openZone.getByRole("button", { name: /异常 \d+ \| 已忽略 \d+/ })).toBeVisible();
    expect(api.count("POST /api/workbench/actions/ignore-row")).toBe(1);
    expect(api.lastBody("POST /api/workbench/actions/ignore-row")).toMatchObject({
      month: "all",
      row_id: "iv-o-202603-001",
      row_type: "invoice",
      comment: "由关联台忽略发票：iv-o-202603-001",
    });
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    await expect.poll(() => api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeIgnore + 1);
    await expectNoUnexpectedSuccessUiErrors(page);

    await openZone.getByRole("button", { name: /异常 \d+ \| 已忽略 \d+/ }).click();
    const exceptionDrawer = page.getByRole("dialog", { name: "异常处理" });
    await expect(exceptionDrawer).toBeVisible();
    await exceptionDrawer.getByRole("radio", { name: "已忽略的异常" }).click();
    await expect(exceptionDrawer.getByText("当前没有已忽略的异常。")).toBeVisible();
    await expect(exceptionDrawer.getByText("智能工厂设备商")).toHaveCount(0);
    expect(api.count("POST /api/workbench/actions/unignore-row")).toBe(0);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("ignores and restores an exact-cent OA invoice amount mismatch", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchAmountMismatchScenario: true,
      workbenchInitialRelationConfirmed: true,
    });

    await page.goto("/");

    const pairedZone = page.getByTestId("zone-paired");
    await expect(pairedZone.getByText("金额不一致")).toBeVisible();
    await page
      .getByTestId("zone-unpaired")
      .getByRole("button", { name: /异常 \d+ \| 已忽略 \d+/ })
      .click();

    const drawer = page.getByRole("dialog", { name: "异常处理" });
    await expect(drawer.getByText("金额不一致").first()).toBeVisible();
    const workbenchLoadsBeforeIgnore = api.count("GET /api/workbench");
    const bucketLoadsBeforeIgnore = api.count("GET /api/workbench/groups");
    await drawer.getByRole("button", { name: "忽略" }).click();

    await expect(drawer.getByText("当前没有进行中的异常。")).toBeVisible();
    await expect(pairedZone.getByText("金额不一致")).toBeVisible();
    await expect(pairedZone.getByText("已忽略：金额不一致")).toHaveCount(0);
    expect(api.count("POST /api/workbench/exceptions/amount-mismatch/ignore")).toBe(1);
    expect(api.lastBody("POST /api/workbench/exceptions/amount-mismatch/ignore")).toMatchObject({
      month: "all",
      zone: "paired",
      group_id: "case:CASE-202603-101",
      fingerprint: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    });
    expect(api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeIgnore);
    expect(api.count("GET /api/workbench/groups")).toBe(bucketLoadsBeforeIgnore + 2);

    await drawer.getByRole("radio", { name: "已忽略的异常" }).click();
    await expect(drawer.getByText("已忽略：金额不一致").first()).toBeVisible();
    await expect(page.getByTestId("zone-unpaired").getByRole("button", {
      name: "异常 0 | 已忽略 1",
    })).toBeVisible();
    const workbenchLoadsBeforeRestore = api.count("GET /api/workbench");
    const bucketLoadsBeforeRestore = api.count("GET /api/workbench/groups");
    await drawer.getByRole("button", { name: "撤回忽略" }).click();

    await expect(drawer.getByText("当前没有已忽略的异常。")).toBeVisible();
    await expect(pairedZone.getByText("金额不一致")).toBeVisible();
    await expect(pairedZone.getByText("已忽略：金额不一致")).toHaveCount(0);
    expect(api.count("POST /api/workbench/exceptions/amount-mismatch/restore")).toBe(1);
    expect(api.lastBody("POST /api/workbench/exceptions/amount-mismatch/restore")).toMatchObject({
      month: "all",
      zone: "paired",
      group_id: "case:CASE-202603-101",
      fingerprint: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    });
    expect(api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeRestore);
    expect(api.count("GET /api/workbench/groups")).toBe(bucketLoadsBeforeRestore + 2);
    await expect(page.getByTestId("zone-unpaired").getByRole("button", {
      name: "异常 0 | 已忽略 0",
    })).toBeVisible();
    await drawer.getByRole("radio", { name: "进行中的异常" }).click();
    await expect(drawer.getByText("金额不一致").first()).toBeVisible();
    await expect(page.getByTestId("zone-unpaired").getByRole("button", {
      name: "异常 1 | 已忽略 0",
    })).toBeVisible();
    await drawer.getByRole("button", { name: "关闭抽屉" }).click();
    await expect(drawer).toHaveCount(0);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
