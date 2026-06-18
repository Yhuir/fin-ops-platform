import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("input invoice usage browser flow", () => {
  test("creates an OA reverse draft from a selected invoice subset and records submitted history", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/input-invoice-usage");
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "进项发票使用情况" })).toBeVisible();
    await expect(page.getByRole("table", { name: "进项发票使用情况表" })).toBeVisible();

    const row = page.getByRole("row", { name: /SD-INV-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("浏览器进项供应商").first()).toBeVisible();
    await expect(row.getByText("待处理")).toBeVisible();

    await page.getByRole("button", { name: "以发票反提 OA" }).click();
    const workflow = page.getByLabel("以发票反提 OA 工作流", { exact: true });
    await expect(workflow).toBeVisible();
    await expect(page.getByRole("tab", { name: "待处理" })).toHaveAttribute("aria-selected", "true");
    await expect(workflow.getByRole("table", { name: "反提 OA 候选发票清单" })).toBeVisible();
    await expect(workflow.getByLabel("选择候选发票 SD-INV-E2E-001")).toBeChecked();
    await expect(workflow.getByLabel("选择候选发票 SD-INV-E2E-002")).toBeChecked();

    await workflow.getByLabel("选择候选发票 SD-INV-E2E-002").uncheck();
    await expect(workflow.getByText("已选 1 张")).toBeVisible();

    const subsetPreviewRequest = page.waitForRequest((request) =>
      request.url().includes("/api/input-invoice-usage/oa-reverse/preview")
        && request.method() === "POST"
        && (request.postData() ?? "").includes("input-oa-invoice-e2e-001"),
    );
    const subsetPreviewResponse = page.waitForResponse((response) =>
      response.url().includes("/api/input-invoice-usage/oa-reverse/preview")
        && response.request().method() === "POST",
    );
    const draftResponse = page.waitForResponse((response) =>
      response.url().includes("/api/input-invoice-usage/oa-reverse/oa-draft")
        && response.request().method() === "POST",
    );
    await workflow.getByRole("button", { name: "创建 OA 草稿" }).click();

    const requestBody = JSON.parse((await subsetPreviewRequest).postData() ?? "{}") as { invoiceIds?: string[] };
    expect(requestBody.invoiceIds).toEqual(["input-oa-invoice-e2e-001"]);
    expect((await subsetPreviewResponse).status()).toBe(200);
    expect((await draftResponse).status()).toBe(200);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/preview")).toBeGreaterThanOrEqual(2);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/oa-draft")).toBe(1);

    const confirmDialog = page.getByRole("dialog", { name: "OA 草稿提交确认" });
    await expect(confirmDialog).toBeVisible();
    await expect(confirmDialog.getByRole("link", { name: "打开 OA 草稿" })).toHaveAttribute(
      "href",
      "https://oa.example.test/draft/input-e2e",
    );

    const manualStatusResponse = page.waitForResponse((response) =>
      response.url().includes("/api/input-invoice-usage/oa-reverse/batches/input-oa-reverse-batch-e2e-001/manual-oa-status")
        && response.request().method() === "POST",
    );
    await confirmDialog.getByRole("button", { name: /我已在OA系统提交该草稿\s+OA正在进行中/ }).click();
    expect((await manualStatusResponse).status()).toBe(200);

    await expect(workflow.getByText("已进入已提交历史。")).toBeVisible();
    await expect(page.getByRole("tab", { name: "已提交" })).toHaveAttribute("aria-selected", "true");
    await expect(workflow.getByRole("table", { name: "陈秀云已提交发票" })).toBeVisible();
    await expect(workflow.getByText("SD-INV-E2E-001")).toBeVisible();
    await expect(workflow.getByText("浏览器进项供应商一")).toBeVisible();
    await expect(workflow.getByText("input-oa-reverse-batch-e2e-001")).toHaveCount(0);
    expect(api.count("GET /api/input-invoice-usage/oa-reverse/submitted-history")).toBeGreaterThanOrEqual(1);
  });
});
