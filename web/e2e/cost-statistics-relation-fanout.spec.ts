import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

function requestPath(requestUrl: string) {
  return new URL(requestUrl).pathname;
}

test.describe("cost statistics relation browser fan-out", () => {
  test("excludes unpaired rows from cost amounts until workbench confirm", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      costStatisticsRelationFanout: true,
      sessionMode: "full_access",
    });

    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    await expect(page.getByRole("grid", { name: "按时间统计表" })).toBeVisible();
    await expect(page.getByText("智能工厂项目")).toHaveCount(0);
    await expect(page.getByText("智能工厂设备尾款")).toHaveCount(0);

    await page.getByRole("button", { name: "按项目" }).click();
    await expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible();
    await expect(page.getByRole("button", { name: /智能工厂项目/ })).toHaveCount(0);
    const explorerRequestCountBeforeConfirm = api.count("GET /api/cost-statistics/explorer");

    await confirmWorkbenchRelation(page);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);

    await page.getByRole("link", { name: "成本统计" }).click();
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    expect(api.count("GET /api/cost-statistics/explorer")).toBeGreaterThan(explorerRequestCountBeforeConfirm);

    await page.getByRole("button", { name: "按项目" }).click();
    const linkedProject = page.getByRole("button", { name: /智能工厂项目/ });
    await expect(linkedProject).toBeVisible();
    await expect(linkedProject).toContainText("58,000.00");
    await linkedProject.click();

    const linkedExpenseType = page.getByRole("button", { name: /设备货款及材料费/ });
    await expect(linkedExpenseType).toBeVisible();
    await expect(linkedExpenseType).toContainText("58,000.00");
    await linkedExpenseType.click();

    const projectRows = page.getByRole("grid", { name: "项目对应流水表" });
    await expect(projectRows).toBeVisible();
    await expect(projectRows).toContainText("智能工厂设备尾款");
    await expect(projectRows).toContainText("智能工厂设备商");

    const detailRequest = page.waitForRequest((request) =>
      requestPath(request.url()).endsWith("/api/cost-statistics/transactions/bk-o-202603-001"),
    );
    await projectRows.getByRole("button", { name: "查看流水 bk-o-202603-001" }).click();
    expect(new URL((await detailRequest).url()).searchParams.get("project_scope")).toBe("active");

    const detailDialog = page.getByRole("dialog", { name: "流水详情" });
    await expect(detailDialog).toBeVisible();
    await expect(detailDialog).toContainText("智能工厂项目");
    await expect(detailDialog).toContainText("智能工厂设备商");
    await expect(detailDialog).toContainText("智能工厂设备尾款");
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
