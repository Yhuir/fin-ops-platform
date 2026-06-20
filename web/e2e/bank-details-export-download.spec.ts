import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectPageReady, gotoAndExpectPageReady, startPageDiagnostics } from "./fixtures/pageReady";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";
import { readXlsxText } from "./fixtures/xlsx";

test.describe("bank details export browser download", () => {
  test("downloads current filtered bank rows with confirmed relation fields", async ({ page }, testInfo) => {
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await gotoAndExpectPageReady(page, "/bank-details", "bank-details-page", { diagnostics });
    const bankRowBefore = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRowBefore.getByText("候选oa")).toBeVisible();
    await expect(bankRowBefore.getByText("候选发票")).toBeVisible();

    await confirmWorkbenchRelation(page);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);

    await page.getByRole("link", { name: "银行明细" }).click();
    await expectPageReady(page, "bank-details-page", {
      diagnostics,
      routeDescription: "return to /bank-details after workbench relation confirmation",
    });
    const bankRowAfter = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRowAfter.getByText("有oa")).toBeVisible();
    await expect(bankRowAfter.getByText("有发票")).toBeVisible();

    await page.getByRole("button", { name: "导出" }).click();
    const exportMenu = page.getByRole("menu", { name: "导出银行明细" });
    await expect(exportMenu).toBeVisible();

    const exportRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return request.method() === "GET" && url.pathname.endsWith("/api/bank-details/transactions/export");
    });
    const download = page.waitForEvent("download");
    await exportMenu.getByRole("menuitem", { name: "导出全部银行" }).click();

    const requestUrl = new URL((await exportRequest).url());
    expect(requestUrl.searchParams.get("mode")).toBe("all");
    expect(requestUrl.searchParams.get("date_from")).toBe("2026-01-01");
    expect(requestUrl.searchParams.get("date_to")).toBe("2026-12-31");

    const downloaded = await download;
    expect(downloaded.suggestedFilename()).toBe("银行明细_全部银行_2026-01-01_2026-12-31.xlsx");
    const downloadPath = testInfo.outputPath(downloaded.suggestedFilename());
    await downloaded.saveAs(downloadPath);
    const content = await readXlsxText(downloadPath);

    expect(content).toContain("bk-o-202603-001");
    expect(content).toContain("智能工厂设备商");
    expect(content).toContain("CASE-202603-101");
    expect(content).toContain("有oa");
    expect(content).toContain("有发票");
    expect(content).toContain("linked");
    expect(content).not.toContain("候选oa");
    expect(content).not.toContain("候选发票");
    expect(api.count("GET /api/bank-details/transactions/export")).toBe(1);
    await expect(page.getByText("已开始下载")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
