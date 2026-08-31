import { expect, test, type Locator, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { dragSelectVisibleText } from "./fixtures/textSelection";

async function expectMouseSelectionCopies(page: Page, target: Locator) {
  const selectedText = (await dragSelectVisibleText(page, target)).trim();
  expect(selectedText.length).toBeGreaterThan(0);

  await page.keyboard.press("ControlOrMeta+C");
  const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
  expect(clipboardText.trim()).toBe(selectedText);
}

function mutationCount(calls: string[]) {
  return calls.filter((entry) => /^(POST|PUT|PATCH|DELETE) /.test(entry)).length;
}

async function expectSelectableGrid(grid: Locator) {
  const table = grid.locator(
    "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' finance-table ')][1]",
  );
  await expect(table).toHaveClass(/finance-table--selectable-text/);
}

test.beforeEach(async ({ context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
});

test("待找发票业务文本可用鼠标选择并复制", async ({ page }) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
  await page.goto("/pending-invoices");
  const grid = page.getByRole("grid", { name: "待找发票四区表" });
  await expect(grid).toBeVisible();
  await expectSelectableGrid(grid);

  const target = page.locator(".pending-invoices-counterparty-name", { hasText: "智能工厂设备商" }).first();
  const mutationsBefore = mutationCount(api.calls);
  await expectMouseSelectionCopies(page, target);

  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(mutationCount(api.calls)).toBe(mutationsBefore);
});

test("进项发票业务文本可用鼠标选择并复制", async ({ page }) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
  await page.goto("/input-invoice-usage");
  const grid = page.getByRole("grid", { name: "进项发票使用情况表" });
  await expect(grid).toBeVisible();
  await expectSelectableGrid(grid);
  const row = grid.getByRole("row", { name: /SD-INV-E2E-0001/ });
  await expect(row).toBeVisible();

  const target = row.locator(".input-invoice-usage-cell-primary", { hasText: "SD-INV-E2E-0001" }).first();
  const mutationsBefore = mutationCount(api.calls);
  await expectMouseSelectionCopies(page, target);

  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(mutationCount(api.calls)).toBe(mutationsBefore);
});

test("销项发票业务文本可用鼠标选择并复制", async ({ page }) => {
  const api = await installDeterministicApiMocks(page, {
    outputInvoiceCollectionListInteractions: true,
    sessionMode: "full_access",
  });
  await page.goto("/output-invoice-collections");
  const grid = page.getByRole("grid", { name: "销项发票收款情况表" });
  await expectSelectableGrid(grid);
  const row = grid.getByRole("row", { name: /XSFP-E2E-0003/ });
  await expect(row).toBeVisible();

  const target = row.getByText("云南驰林科技有限公司", { exact: true }).first();
  const mutationsBefore = mutationCount(api.calls);
  await expectMouseSelectionCopies(page, target);

  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(mutationCount(api.calls)).toBe(mutationsBefore);
});

test("OA 待付款业务文本可用鼠标选择并复制", async ({ page }) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
  await page.goto("/oa-pending-payments");
  const grid = page.getByRole("grid", { name: "OA待付款核对表格" });
  await expectSelectableGrid(grid);
  const row = grid.getByRole("row", { name: /浏览器付款申请人/ });
  await expect(row).toBeVisible();

  const target = row.getByText("浏览器付款申请人", { exact: true }).first();
  const mutationsBefore = mutationCount(api.calls);
  await expectMouseSelectionCopies(page, target);

  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(mutationCount(api.calls)).toBe(mutationsBefore);
});

test("成本统计项目文字可选择且拖选不会切换项目", async ({ page }) => {
  await page.addInitScript(() => {
    const now = Date.now();
    sessionStorage.setItem("finops:pageSession:v1:e2e-user:cost-statistics:explorerState", JSON.stringify({
      version: 4,
      updatedAt: now,
      expiresAt: now + 60 * 60 * 1000,
      value: {
        viewMode: "project",
        projectScopeMode: "month",
        projectScopeYear: "2026",
        projectScopeMonth: "2026-03",
        bankAccountScopeMode: "all",
        bankAccountScopeYear: "2026",
        bankAccountScopeMonth: "2026-03",
        expenseTypeScopeMode: "month",
        expenseTypeScopeYear: "2026",
        expenseTypeScopeMonth: "2026-03",
      },
    }));
  });
  const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
  await page.goto("/cost-statistics");
  const target = page.locator(".cost-explorer-item-main strong", { hasText: "云南溯源科技" }).first();
  await expect(target).toBeVisible();
  const item = target.locator("xpath=ancestor::*[contains(@class,'cost-explorer-item')][1]");
  const classBefore = await item.getAttribute("class");
  const mutationsBefore = mutationCount(api.calls);

  await expectMouseSelectionCopies(page, target);

  expect(await item.getAttribute("class")).toBe(classBefore);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(mutationCount(api.calls)).toBe(mutationsBefore);
});
