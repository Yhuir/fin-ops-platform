import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

test.describe("workbench receipt browser flow", () => {
  test("edits and prints an eligible receipt from either relation zone", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
      workbenchReceiptScenario: true,
    });
    await page.goto("/");

    const pairedAction = page.getByTestId("zone-paired").getByRole("button", {
      name: "编辑并打印收据 CASE-RECEIPT-PAIRED",
    });
    const unpairedAction = page.getByTestId("zone-unpaired").getByRole("button", {
      name: "编辑并打印收据 CASE-RECEIPT-UNPAIRED",
    });
    await expect(pairedAction).toBeEnabled();
    await expect(unpairedAction).toBeEnabled();
    await expect(page.getByText("待补收据")).toHaveCount(0);

    await unpairedAction.click();
    const drawer = page.getByRole("dialog", { name: "编辑收据" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("textbox", { name: "收据 1 付款单位" })).toHaveValue("未配对收据客户");

    const amount = drawer.getByRole("textbox", { name: "收据 1 明细 1 金额" });
    await amount.fill("90");
    await expect(drawer.getByText("明细与收入相差 ¥10.00，调整一致后才能打印。")).toBeVisible();
    await expect(drawer.getByRole("button", { name: "打印收据" })).toBeDisabled();

    await amount.fill("100");
    await drawer.getByRole("textbox", { name: "收据 1 明细 1 摘要" }).fill("编辑后的技术服务费");
    const popupPromise = page.waitForEvent("popup");
    await drawer.getByRole("button", { name: "打印收据" }).click();
    const popup = await popupPromise;

    await expect.poll(() => api.count("POST /api/workbench/actions/print-receipt")).toBe(1);
    expect(api.lastBody("POST /api/workbench/actions/print-receipt")).toMatchObject({
      case_id: "CASE-RECEIPT-UNPAIRED",
      relation_version: 7,
      source_fingerprint: "f".repeat(64),
      issues_acknowledged: false,
      receipts: [{
        receipt_key: "receipt-unpaired",
        payer: "未配对收据客户",
        date: "2026-08-30",
        lines: [{ summary: "编辑后的技术服务费", amount: "100", note: "" }],
      }],
    });
    await expect(drawer.getByText("金额已核对，可以打印")).toBeVisible();
    await popup.close();
    await expectNoUnexpectedSuccessUiErrors(page);
  });

});
