import { expect, test } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

for (const mode of ["invoice", "bank"] as const) {
  test(`${mode}: 33 complete rows expose exactly four issues without enabling confirmation`, async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });
    const audit = { original_count: 33, unique_count: 29, duplicate_count: 0, duplicate_in_file_count: 0,
      duplicate_across_files_count: 0, existing_duplicate_count: 10, importable_count: 19, update_count: 0,
      merge_count: mode === "invoice" ? 10 : 0, suspected_duplicate_count: 0, error_count: 4, confirmable_count: mode === "invoice" ? 29 : 19, skipped_count: mode === "invoice" ? 4 : 14 };
    const rows = Array.from({length: 33}, (_, index) => ({
      file_id: "review-file", row_no: index + 1, category: index < 4 ? "review" : index < 23 ? "new" : "existing",
      record_type: mode === "invoice" ? "invoice" : "bank_transaction", decision: index < 4 ? "error" : index < 23 ? "created" : "duplicate_skipped",
      invoice_no: `2699000000000000${String(index).padStart(4, "0")}`, invoice_date: "2026-09-16",
      seller_name: "云南铁路发展有限公司", buyer_name: "云南溯源科技有限公司", amount: "133.03", tax_amount: "11.97", total_with_tax: "145.00",
      account_no: "622200000000000001", trade_time: "2026-09-16 10:00:00", direction: "outflow", counterparty_name: "云南铁路发展有限公司",
      current_source: "OA附件解析", decision_reason: "关键字段不一致，请核对来源。",
      conflicts: index < 4 && mode === "invoice" ? [{field: "amount", file_value: "133.03", current_value: "145.00"}, {field: "tax_amount", file_value: "11.97", current_value: "0.00"}] : [],
    }));
    await page.route("**/imports/files/sessions/*", route => route.fulfill({json: {
      session: {id: "review-session", imported_by: "other-user", file_count: 1, status: "preview_ready_with_errors", created_at: "2026-09-23", audit},
      files: [{id: "review-file", file_name: "测试发票.xlsx", status: "preview_ready", batch_type: mode === "invoice" ? "input_invoice" : "bank_transaction", row_count: 33, success_count: 19, error_count: 4, suspected_duplicate_count: 0, duplicate_count: 10, updated_count: 0, audit, message: "模板识别成功。", preview_batch_id: "preview-1"}],
      job: {job_id: "import:review-task", status: "needs_review", phase: "prepare", version: 2, source: {session_id: "review-session"}}, duplicate_groups: [],
    }}));
    let reads = 0;
    await page.route("**/imports/files/sessions/*/review-rows?*", route => {
      reads++;
      expect(new URL(route.request().url()).searchParams.get("file_id")).toBe("review-file");
      return route.fulfill({json: {rows, summary: {new: 19, existing: 10, review: 4, batch_duplicate: 0}, total: 33, offset: 0, limit: 100, has_more: false}});
    });
    await page.setViewportSize({width: 1440, height: 1000});
    await page.goto(mode === "invoice" ? "/imports/invoices" : "/imports/bank-transactions");
    await page.locator('input[type="file"]').first().setInputFiles({name: "测试发票.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("fixture")});
    await page.getByLabel(mode === "invoice" ? "票据方向 测试发票.xlsx" : "对应账户 测试发票.xlsx").selectOption(mode === "invoice" ? "input_invoice" : "bank_mapping_8826");
    await page.getByRole("button", {name: "开始预览", exact: true}).click();
    await expect(page.getByLabel("需检查 4", {exact: true})).toBeVisible();
    await expect(page.getByRole("button", {name: "确认导入", exact: true})).toBeDisabled();
    expect(reads).toBe(0);
    await page.getByRole("button", {name: "查看导入明细"}).click();
    const drawer = page.getByRole("dialog", {name: mode === "invoice" ? "发票导入明细" : "流水导入明细"});
    const grid = drawer.getByRole("grid", {name: "导入文件全部明细"});
    await expect(grid.getByRole("row")).toHaveCount(34);
    await expect(grid.locator(".import-review-row--review")).toHaveCount(4);
    await expect(grid.locator(".import-review-row--new")).toHaveCount(19);
    await expect(grid.locator(".import-review-row--existing")).toHaveCount(10);
    await expect(grid.getByRole("columnheader", {name: "文件", exact: true})).toHaveCount(0);
    const issue = grid.locator(".import-review-row--review").first();
    await expect(issue).toContainText("133.03");
    if (mode === "invoice") {
      await issue.locator("summary").click();
      await expect(issue.getByText("App 当前：145.00", {exact: true})).toBeVisible();
      await expect(issue).toContainText("合计 145.00");
    }
    const colors = await grid.locator("tbody tr td:first-child").evaluateAll(cells => [...new Set(cells.map(cell => getComputedStyle(cell).backgroundColor))]);
    expect(colors.length).toBe(3);
    const amount = await issue.locator(".import-review-money").first().boundingBox();
    const bounds = await drawer.boundingBox();
    expect(amount!.x + amount!.width).toBeLessThan(bounds!.x + bounds!.width);
    expect(reads).toBe(1);
    await page.getByRole("button", {name: "关闭抽屉"}).click();
    await expect(drawer).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
}
