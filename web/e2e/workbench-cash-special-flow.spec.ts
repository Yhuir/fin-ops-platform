import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

const pairedGroupTestId = "candidate-group-paired-case:CASE-202603-101";
const operationBarrierPath = "POST /api/operation-barrier/status";
const workbenchLoadPath = "GET /api/workbench";
const passThroughPath = "/api/workbench/actions/confirm-cash-pass-through";
const ticketPurchasePath = "/api/workbench/actions/confirm-cash-ticket-purchase";
const cancelCashSpecialPath = "/api/workbench/actions/cancel-cash-special";
const workbenchRowIds = ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"];
const workbenchRowTypes = ["oa", "bank", "invoice"];

async function openPairedBankRowMenu(page: Page) {
  const pairedGroup = page.getByTestId(pairedGroupTestId);
  await expect(pairedGroup).toBeVisible();

  const bankRow = pairedGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ });
  await expect(bankRow).toBeVisible();
  await bankRow.getByRole("button", { name: "更多" }).click();

  return { pairedGroup, bankRow };
}

function waitForWorkbenchPost(page: Page, pathname: string) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === pathname && response.request().method() === "POST";
  });
}

function expectWorkbenchRowIds(body: Record<string, unknown>) {
  expect(body.row_ids).toEqual(expect.arrayContaining(workbenchRowIds));
  expect(body.row_ids).toHaveLength(workbenchRowIds.length);
  expect(body.row_types).toEqual(expect.arrayContaining(workbenchRowTypes));
  expect(body.row_types).toHaveLength(workbenchRowTypes.length);
  expect((body.row_ids as string[]).map((rowId, index) => ({
    rowId,
    rowType: (body.row_types as string[])[index],
  }))).toEqual(expect.arrayContaining([
    { rowId: "oa-o-202603-001", rowType: "oa" },
    { rowId: "bk-o-202603-001", rowType: "bank" },
    { rowId: "iv-o-202603-001", rowType: "invoice" },
  ]));
}

test.describe("workbench cash special browser flow", () => {
  test("handles cash pass-through, ticket purchase, and cancel special processing", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
      workbenchInitialRelationConfirmed: true,
      workbenchCashSpecialActions: true,
    });

    await page.goto("/");
    await expect(page.getByTestId(pairedGroupTestId)).toBeVisible();

    const workbenchLoadsBeforePassThrough = api.count(workbenchLoadPath);
    await openPairedBankRowMenu(page);
    const passThroughResponse = waitForWorkbenchPost(page, passThroughPath);
    await page.getByRole("menuitem", { name: "确认为过账" }).click();

    expect((await passThroughResponse).status()).toBe(200);
    await expect(page.getByRole("dialog", { name: "全局操作进度" })).toHaveCount(0);
    await expect(page.getByTestId(pairedGroupTestId)).toBeVisible();

    const passThroughBody = api.lastBody(`POST ${passThroughPath}`);
    expect(passThroughBody).toMatchObject({
      month: "all",
      note: "由关联台确认现金往来过账",
    });
    expectWorkbenchRowIds(passThroughBody);
    expect(api.count(operationBarrierPath)).toBe(0);
    expect(api.count(workbenchLoadPath)).toBe(workbenchLoadsBeforePassThrough + 1);
    await expectNoUnexpectedSuccessUiErrors(page);

    const workbenchLoadsBeforeTicket = api.count(workbenchLoadPath);
    await openPairedBankRowMenu(page);
    await page.getByRole("menuitem", { name: "确认为买票" }).click();

    const ticketDialog = page.getByRole("dialog", { name: "确认买票成本" });
    await expect(ticketDialog).toBeVisible();
    await expect(ticketDialog.getByText("此操作只把买票成本计入成本统计，流水全额不会作为成本入账。")).toBeVisible();
    await expect(ticketDialog.getByLabel("现金往来金额")).toHaveValue("58000");
    await expect(ticketDialog.getByRole("button", { name: "确认买票" })).toBeDisabled();

    await ticketDialog.getByLabel("买票成本（必填）").fill("1800.50");
    await ticketDialog.getByLabel("项目名称（必填）").fill("浏览器买票项目");
    await ticketDialog.getByLabel("费用类型").fill("现金票据");
    await ticketDialog.getByLabel("费用内容").fill("票据服务费");
    await ticketDialog.getByLabel("备注").fill("浏览器确认买票成本");

    const ticketResponse = waitForWorkbenchPost(page, ticketPurchasePath);
    await ticketDialog.getByRole("button", { name: "确认买票" }).click();

    expect((await ticketResponse).status()).toBe(200);
    await expect(page.getByRole("dialog", { name: "确认买票成本" })).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "全局操作进度" })).toHaveCount(0);
    await expect(page.getByTestId(pairedGroupTestId)).toBeVisible();

    const ticketBody = api.lastBody(`POST ${ticketPurchasePath}`);
    expect(ticketBody).toMatchObject({
      month: "all",
      cash_amount: "58000",
      ticket_cost_amount: "1800.50",
      project_name: "浏览器买票项目",
      expense_type: "现金票据",
      expense_content: "票据服务费",
      note: "浏览器确认买票成本",
    });
    expectWorkbenchRowIds(ticketBody);
    expect(api.count(operationBarrierPath)).toBe(0);
    expect(api.count(workbenchLoadPath)).toBe(workbenchLoadsBeforeTicket + 1);
    await expectNoUnexpectedSuccessUiErrors(page);

    const workbenchLoadsBeforeCancel = api.count(workbenchLoadPath);
    await openPairedBankRowMenu(page);
    const cancelResponse = waitForWorkbenchPost(page, cancelCashSpecialPath);
    await page.getByRole("menuitem", { name: "取消现金处理" }).click();

    expect((await cancelResponse).status()).toBe(200);
    await expect(page.getByRole("dialog", { name: "全局操作进度" })).toHaveCount(0);
    await expect(page.getByTestId(pairedGroupTestId)).toBeVisible();

    const cancelBody = api.lastBody(`POST ${cancelCashSpecialPath}`);
    expect(cancelBody).toMatchObject({
      month: "all",
      note: "由关联台取消现金往来特殊处理",
    });
    expectWorkbenchRowIds(cancelBody);
    expect(api.count(operationBarrierPath)).toBe(0);
    expect(api.count(workbenchLoadPath)).toBe(workbenchLoadsBeforeCancel + 1);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
