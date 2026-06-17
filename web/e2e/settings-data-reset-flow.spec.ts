import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("settings data reset browser flow", () => {
  test("runs data reset through impact confirmation, OA password review, job polling, and settings reload", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
    await expect(page.getByRole("tree", { name: "设置分类" })).toBeVisible();
    await expect(page.getByRole("treeitem", { name: /数据重置/ })).toBeVisible();

    await page.getByRole("treeitem", { name: /数据重置/ }).click();
    const dataResetRegion = page.getByRole("region", { name: "数据重置" });
    await expect(dataResetRegion).toBeVisible();
    await expect(dataResetRegion.getByText("高风险操作")).toBeVisible();

    await dataResetRegion.getByRole("button", { name: "清除所有银行流水数据" }).click();
    const impactDialog = page.getByRole("dialog", { name: "确认数据重置" });
    await expect(impactDialog).toBeVisible();
    await expect(impactDialog.getByText("已导入银行流水会被清空")).toBeVisible();
    await impactDialog.getByRole("button", { name: "继续" }).click();

    const passwordDialog = page.getByRole("dialog", { name: "OA 密码复核" });
    await expect(passwordDialog).toBeVisible();
    await passwordDialog.getByLabel("当前 OA 用户密码").fill("oa-password-e2e");

    const settingsFetchCountBeforeReset = api.count("GET /api/workbench/settings");
    const createJobResponse = page.waitForResponse((response) =>
      response.url().includes("/api/workbench/settings/data-reset/jobs") && response.request().method() === "POST",
    );
    await passwordDialog.getByRole("button", { name: "确认清理" }).click();
    expect((await createJobResponse).status()).toBe(202);

    await expect.poll(() => api.count("POST /api/workbench/settings/data-reset/jobs")).toBe(1);
    await expect(dataResetRegion.getByRole("button", { name: /正在清理 app 内部状态。 25%/ })).toBeDisabled();
    await expect.poll(() =>
      api.count("GET /api/workbench/settings/data-reset/jobs/settings-reset-job-e2e-001"),
    ).toBeGreaterThanOrEqual(2);
    await expect.poll(() => api.count("GET /api/workbench/settings")).toBeGreaterThan(settingsFetchCountBeforeReset);
    await expect(page.getByRole("status").filter({ hasText: "已完成数据重置。" })).toBeVisible();
    await expect(page.getByRole("dialog", { name: "OA 密码复核" })).toBeHidden();
  });
});
