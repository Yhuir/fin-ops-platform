import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

function requestPath(requestUrl: string) {
  return new URL(requestUrl).pathname;
}

test.describe("cost statistics browser flow", () => {
  test("drills into project cost rows and surfaces export row-limit feedback", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    await expect(page.getByRole("grid", { name: "按时间统计表" })).toBeVisible();
    await expect(page.getByRole("button", { name: "查看流水 cost-txn-e2e-003" })).toBeVisible();
    expect(api.count("GET /api/cost-statistics/explorer")).toBeGreaterThanOrEqual(1);

    await page.getByRole("button", { name: "按项目" }).click();
    await expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible();
    await expect(page.getByText("云南溯源科技")).toBeVisible();
    await expect(page.getByText("昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目")).toHaveCount(0);

    const allScopeRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/cost-statistics/explorer")
        && url.searchParams.get("month") === "all"
        && url.searchParams.get("project_scope") === "all";
    });
    await page.getByRole("button", { name: "项目范围：进行中" }).click();
    expect(new URL((await allScopeRequest).url()).searchParams.get("project_scope")).toBe("all");
    await expect(page.getByRole("button", { name: "项目范围：所有项目" })).toBeVisible();
    await expect(page.getByText("昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目")).toBeVisible();

    await page.getByRole("button", { name: /云南溯源科技/ }).first().click();
    await page.getByRole("button", { name: /设备货款及材料费/ }).click();

    const projectRows = page.getByRole("grid", { name: "项目对应流水表" });
    await expect(projectRows).toBeVisible();
    await expect(projectRows.getByRole("button", { name: "查看流水 cost-txn-e2e-001" })).toBeVisible();

    const detailRequest = page.waitForRequest((request) =>
      requestPath(request.url()).endsWith("/api/cost-statistics/transactions/cost-txn-e2e-001"),
    );
    await projectRows.getByRole("button", { name: "查看流水 cost-txn-e2e-001" }).click();
    expect(new URL((await detailRequest).url()).searchParams.get("project_scope")).toBe("all");
    const detailDialog = page.getByRole("dialog", { name: "流水详情" });
    await expect(detailDialog).toBeVisible();
    await expect(detailDialog.getByText("PLC 模块采购").first()).toBeVisible();
    await expect(detailDialog.getByText("浏览器成本统计明细").first()).toBeVisible();
    await detailDialog.getByRole("button", { name: "关闭" }).click();
    await expect(page.getByRole("dialog", { name: "流水详情" })).toHaveCount(0);

    await page.getByRole("button", { name: "导出中心" }).click();
    const exportDialog = page.getByRole("dialog", { name: "导出中心" });
    await expect(exportDialog).toBeVisible();
    await expect(exportDialog.getByText("项目选择")).toBeVisible();

    const previewRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/cost-statistics/export-preview")
        && url.searchParams.get("view") === "project";
    });
    await exportDialog.getByRole("button", { name: "仅预览" }).click();
    const previewUrl = new URL((await previewRequest).url());
    expect(previewUrl.searchParams.get("project_scope")).toBe("all");
    expect(previewUrl.searchParams.getAll("project_name")).toContain("云南溯源科技");
    await expect(exportDialog.getByRole("table", { name: "导出预览表" })).toBeVisible();
    await expect(exportDialog.getByText("预计导出 3 条流水")).toBeVisible();

    const exportResponse = page.waitForResponse((response) =>
      response.url().includes("/api/cost-statistics/export")
        && response.request().method() === "GET",
    );
    await exportDialog.getByRole("button", { name: "导出" }).click();
    expect((await exportResponse).status()).toBe(400);
    await expect(exportDialog.getByText("导出结果超过 20000 行，请缩小筛选范围后重试。")).toBeVisible();
    expect(api.count("GET /api/cost-statistics/export-preview")).toBe(1);
    expect(api.count("GET /api/cost-statistics/export")).toBe(1);
  });
});
