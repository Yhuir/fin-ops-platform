import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { readXlsxText } from "./fixtures/xlsx";

function bankDetailMutationCalls(calls: string[]) {
  return calls.filter((entry) => /^(POST|PUT|DELETE) \/api\/bank-details/.test(entry));
}

function bankDetailProtectedCalls(calls: string[]) {
  return calls.filter((entry) => /^(GET|POST|PUT|DELETE) \/api\/bank-details/.test(entry));
}

test.describe("bank details filtered export and read-export permissions", () => {
  test("downloads the selected account with current keyword and category filters", async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await page.getByRole("button", { name: /建设银行 1138/ }).click();

    const filteredRowsRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return request.method() === "GET"
        && url.pathname.endsWith("/api/bank-details/transactions")
        && url.searchParams.get("account_key") === "bank-account-1138"
        && url.searchParams.get("keyword") === "智能工厂"
        && url.searchParams.get("category_code") === "equipment_payment";
    });

    await page.getByRole("textbox", { name: "搜索流水" }).fill("智能工厂");
    await page.getByRole("button", { name: /标签筛选/ }).click();
    const categoryMenu = page.getByRole("menu", { name: "银行明细标签筛选" });
    await expect(categoryMenu).toBeVisible();
    await categoryMenu.getByRole("menuitem", { name: /设备款 1/ }).click();
    await filteredRowsRequest;
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "导出" }).click();
    const exportMenu = page.getByRole("menu", { name: "导出银行明细" });
    await expect(exportMenu).toBeVisible();
    await expect(exportMenu.getByRole("menuitem", { name: "导出当前账户" })).toBeEnabled();

    const exportRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return request.method() === "GET" && url.pathname.endsWith("/api/bank-details/transactions/export");
    });
    const download = page.waitForEvent("download");
    await exportMenu.getByRole("menuitem", { name: "导出当前账户" }).click();

    const requestUrl = new URL((await exportRequest).url());
    expect(requestUrl.searchParams.get("mode")).toBe("account");
    expect(requestUrl.searchParams.get("account_key")).toBe("bank-account-1138");
    expect(requestUrl.searchParams.get("keyword")).toBe("智能工厂");
    expect(requestUrl.searchParams.get("category_code")).toBe("equipment_payment");
    expect(requestUrl.searchParams.get("date_from")).toBe("2026-01-01");
    expect(requestUrl.searchParams.get("date_to")).toBe("2026-12-31");

    const downloaded = await download;
    expect(downloaded.suggestedFilename()).toBe("银行明细_当前账户_2026-01-01_2026-12-31.xlsx");
    const downloadPath = testInfo.outputPath(downloaded.suggestedFilename());
    await downloaded.saveAs(downloadPath);
    const content = await readXlsxText(downloadPath);

    expect(content).toContain("bk-o-202603-001");
    expect(content).toContain("智能工厂设备商");
    expect(content).toContain("建设银行 1138");
    expect(content).toContain("设备款");
    await expect(page.getByText("已开始下载")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("exports the selected month and filters after pagination changes without limiting to the current page", async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, {
      bankDetailsTransactionsTotal: 299,
      sessionMode: "full_access",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await expect(page.getByText("1-100 / 299")).toBeVisible();

    await page.getByRole("button", { name: /时间选择 2026年/ }).click();
    const datePicker = page.getByRole("dialog", { name: "银行明细时间选择面板" });
    await datePicker.getByRole("button", { name: "按月" }).click();
    const monthRowsRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return request.method() === "GET"
        && url.pathname.endsWith("/api/bank-details/transactions")
        && url.searchParams.get("date_from") === "2026-03-01"
        && url.searchParams.get("date_to") === "2026-03-31"
        && url.searchParams.get("page") === "1"
        && url.searchParams.get("page_size") === "100";
    });
    await datePicker.getByRole("button", { name: "3月" }).click();
    await monthRowsRequest;
    await expect(page.getByRole("button", { name: /时间选择 2026年3月/ })).toBeVisible();

    await page.getByRole("button", { name: /建设银行 1138/ }).click();
    await page.getByRole("textbox", { name: "搜索流水" }).fill("智能工厂");
    await page.getByRole("button", { name: /标签筛选/ }).click();
    const categoryMenu = page.getByRole("menu", { name: "银行明细标签筛选" });
    await expect(categoryMenu).toBeVisible();

    const filteredRowsRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return request.method() === "GET"
        && url.pathname.endsWith("/api/bank-details/transactions")
        && url.searchParams.get("account_key") === "bank-account-1138"
        && url.searchParams.get("date_from") === "2026-03-01"
        && url.searchParams.get("date_to") === "2026-03-31"
        && url.searchParams.get("keyword") === "智能工厂"
        && url.searchParams.get("category_code") === "equipment_payment"
        && url.searchParams.get("page") === "1"
        && url.searchParams.get("page_size") === "100";
    });
    await categoryMenu.getByRole("menuitem", { name: /设备款 1/ }).click();
    await filteredRowsRequest;
    await page.keyboard.press("Escape");

    const pageSizeRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return request.method() === "GET"
        && url.pathname.endsWith("/api/bank-details/transactions")
        && url.searchParams.get("category_code") === "equipment_payment"
        && url.searchParams.get("page") === "1"
        && url.searchParams.get("page_size") === "25";
    });
    await page.getByLabel("每页行数").selectOption("25");
    await pageSizeRequest;
    await expect(page.getByText("1-25 / 299")).toBeVisible();

    const secondPageRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return request.method() === "GET"
        && url.pathname.endsWith("/api/bank-details/transactions")
        && url.searchParams.get("category_code") === "equipment_payment"
        && url.searchParams.get("page") === "2"
        && url.searchParams.get("page_size") === "25";
    });
    await page.getByLabel("下一页").click();
    await secondPageRequest;
    await expect(page.getByText("26-50 / 299")).toBeVisible();

    await page.getByRole("button", { name: "导出" }).click();
    const exportMenu = page.getByRole("menu", { name: "导出银行明细" });
    await expect(exportMenu).toBeVisible();

    const exportRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return request.method() === "GET" && url.pathname.endsWith("/api/bank-details/transactions/export");
    });
    const download = page.waitForEvent("download");
    await exportMenu.getByRole("menuitem", { name: "导出当前账户" }).click();

    const requestUrl = new URL((await exportRequest).url());
    expect(requestUrl.searchParams.get("mode")).toBe("account");
    expect(requestUrl.searchParams.get("account_key")).toBe("bank-account-1138");
    expect(requestUrl.searchParams.get("date_from")).toBe("2026-03-01");
    expect(requestUrl.searchParams.get("date_to")).toBe("2026-03-31");
    expect(requestUrl.searchParams.get("keyword")).toBe("智能工厂");
    expect(requestUrl.searchParams.get("category_code")).toBe("equipment_payment");
    expect(requestUrl.searchParams.get("page")).toBeNull();
    expect(requestUrl.searchParams.get("page_size")).toBeNull();

    const downloaded = await download;
    expect(downloaded.suggestedFilename()).toBe("银行明细_当前账户_2026-03-01_2026-03-31.xlsx");
    const downloadPath = testInfo.outputPath(downloaded.suggestedFilename());
    await downloaded.saveAs(downloadPath);
    const content = await readXlsxText(downloadPath);

    expect(content).toContain("智能工厂设备商");
    expect(content).toContain("建设银行 1138");
    expect(content).toContain("设备款");
    expect(content).toContain("2026-03-01");
    expect(content).toContain("2026-03-31");
    expect(content).toContain("bank-account-1138");
    expect(content).toContain("智能工厂");
    expect(content).toContain("equipment_payment");
    await expect(page.getByText("已开始下载")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("allows read-export users to download while keeping bank detail write entries disabled", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, {
      bankDetailsClassificationMode: "needs_confirmation",
      sessionMode: "read_export_only",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    const bankRow = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRow.getByRole("button", { name: "待确认" })).toBeDisabled();

    await page.getByRole("button", { name: "导出" }).click();
    const exportMenu = page.getByRole("menu", { name: "导出银行明细" });
    await expect(exportMenu).toBeVisible();
    const download = page.waitForEvent("download");
    await exportMenu.getByRole("menuitem", { name: "导出全部银行" }).click();
    const downloaded = await download;
    const downloadPath = testInfo.outputPath(downloaded.suggestedFilename());
    await downloaded.saveAs(downloadPath);
    expect(await readXlsxText(downloadPath)).toContain("智能工厂设备商");

    await page.getByRole("button", { name: /自动标签规则/ }).click();
    const drawer = page.getByRole("dialog", { name: "自动标签规则" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("button", { name: "新增标签" })).toBeDisabled();
    await expect(drawer.getByRole("button", { name: "重新应用规则" })).toBeDisabled();
    await expect(drawer.getByRole("button", { name: "保存" })).toBeDisabled();

    expect(bankDetailMutationCalls(api.calls)).toEqual([]);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("blocks forbidden sessions before bank detail protected APIs load", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "forbidden" });

    await page.goto("/bank-details");

    await expect(page.getByRole("heading", { name: "无权访问财务运营平台" })).toBeVisible();
    await expect(page.getByText("当前 OA 账号未开通访问权限，请联系管理员处理。")).toBeVisible();
    await expect(page.getByTestId("bank-details-page")).toHaveCount(0);
    expect(bankDetailProtectedCalls(api.calls)).toEqual([]);
  });

  test("blocks expired sessions before bank detail protected APIs load", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "expired" });

    await page.goto("/bank-details");

    await expect(page.getByRole("heading", { name: "OA 会话已失效" })).toBeVisible();
    await expect(page.getByTestId("bank-details-page")).toHaveCount(0);
    expect(bankDetailProtectedCalls(api.calls)).toEqual([]);
  });

  test("allows admin users to perform bank detail category writes", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      bankDetailsClassificationMode: "needs_confirmation",
      sessionMode: "admin",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();

    const row = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(row.getByRole("button", { name: "待确认" })).toBeEnabled();
    await row.getByRole("button", { name: "待确认" }).click();

    const primaryMenu = page.getByRole("menu", { name: "待确认主标签" });
    await expect(primaryMenu).toBeVisible();
    await primaryMenu.getByRole("menuitem", { name: "成本" }).click();

    const candidateMenu = page.getByRole("menu", { name: "成本候选标签" });
    await expect(candidateMenu).toBeVisible();
    await candidateMenu.getByRole("menuitem", { name: "设备款" }).click();
    await page.getByRole("button", { name: "保存" }).click();

    const categoryConfirmationPath = "POST /api/bank-details/transactions/bk-o-202603-001/category-confirmation";
    await expect.poll(() => api.count(categoryConfirmationPath)).toBe(1);
    expect(api.lastBody(categoryConfirmationPath)).toEqual({
      category_code: "equipment_payment",
    });
    await expect.poll(() => api.count("GET /api/bank-details/transactions")).toBeGreaterThanOrEqual(2);
    await expect(row.getByText("成本 / 设备款")).toBeVisible();
    await expect(row.getByRole("button", { name: "撤销" })).toBeEnabled();
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
