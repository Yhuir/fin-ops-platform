import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

function requestPath(requestUrl: string) {
  return new URL(requestUrl).pathname;
}

test.describe("cost statistics relation browser fan-out", () => {
  test("excludes candidate rows and includes a confirmed OA-bank relation without an invoice", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      costStatisticsRelationFanout: true,
      sessionMode: "full_access",
    });

    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible();
    await expect(page.getByText("智能工厂项目")).toHaveCount(0);
    await expect(page.getByText("智能工厂设备尾款")).toHaveCount(0);

    await expect(page.getByRole("button", { name: /智能工厂项目/ })).toHaveCount(0);
    const explorerRequestCountBeforeConfirm = api.count("GET /api/cost-statistics/explorer");

    await confirmWorkbenchRelation(page);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);

    await page.getByRole("link", { name: "成本统计" }).click();
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    expect(api.count("GET /api/cost-statistics/explorer")).toBeGreaterThan(explorerRequestCountBeforeConfirm);

    const linkedProject = page.getByRole("button", { name: /智能工厂项目/ });
    await expect(linkedProject).toBeVisible();
    await expect(linkedProject).toContainText("58000.00");
    await linkedProject.click();

    const linkedExpenseType = page.getByRole("button", { name: /设备货款及材料费/ });
    await expect(linkedExpenseType).toBeVisible();
    await expect(linkedExpenseType).toContainText("58000.00");
    await linkedExpenseType.click();

    const projectRows = page.getByRole("grid", { name: "项目成本明细表" });
    await expect(projectRows).toBeVisible();
    await expect(projectRows).toContainText("智能工厂设备尾款");

    const detailRequest = page.waitForRequest((request) =>
      decodeURIComponent(requestPath(request.url())).endsWith("/api/cost-statistics/allocations/oa:bk-o-202603-001"),
    );
    await projectRows.getByRole("button", { name: /^查看OA 成本归集 智能工厂项目/ }).click();
    expect(new URL((await detailRequest).url()).searchParams.has("project_scope")).toBe(false);

    const detailDialog = page.getByRole("dialog", { name: "OA 成本归集明细" });
    await expect(detailDialog).toBeVisible();
    await expect(detailDialog).toContainText("智能工厂项目");
    await expect(detailDialog).toContainText("智能工厂设备商");
    await expect(detailDialog).toContainText("智能工厂设备尾款");
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
