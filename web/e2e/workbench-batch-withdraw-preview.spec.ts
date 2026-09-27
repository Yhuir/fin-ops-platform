import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

for (const zoneName of ["paired", "unpaired"] as const) {
  test(`${zoneName} batch withdrawal only writes after header preview confirmation`, async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, { sessionMode: "user", workbenchInitialIncompleteRelation: true });
    const initial = page.waitForResponse(response => new URL(response.url()).pathname === "/api/workbench");
    await page.goto("/");
    const payload = await (await initial).json();
    const source = payload.unpaired.groups.find((group: { group_id: string }) => group.group_id === "case:CASE-202603-101");
    const members = ["batch-bank-1", "batch-bank-2"];
    const batchId = "HEADER-WITHDRAW-TEST";
    const group = { ...source, group_id: "case:BATCH-HEADER", relation_mode: "bank_flow_rule_batch",
      oa_rows: [], invoice_rows: [], formal_member_ids: members, formal_member_types: ["bank", "bank"],
      bank_rows: members.map(id => ({ ...source.bank_rows[0], id, counterparty_name: "批次预览测试商户", debit_amount: "50.00", amount: "50.00",
        special_metadata: { relation_mode: "bank_flow_rule_batch", source_batch_id: batchId, batch_version: 7 } })),
    };
    payload.paired.groups = zoneName === "paired" ? [group] : [];
    payload.unpaired.groups = zoneName === "unpaired" ? [group] : [];
    await page.route("**/api/workbench?*", route => route.fulfill({ json: payload }));
    await page.route(`**/api/bank-flow-rule-batches/${batchId}?view=formal`, route => route.fulfill({ json: {
      batch: { batch_id: batchId, batch_label: "费用", version: 7, status: "submitted", can_withdraw: true, total_amount: "100.00" },
      rows: members.map(id => ({ transaction_id: id, trade_time: "2026-09-27", counterparty_name: "批次预览测试商户", direction_label: "支出", amount: "50.00", summary: "手续费" })),
    } }));
    const writes: unknown[] = [];
    await page.route(`**/api/bank-flow-rule-batches/${batchId}/withdraw`, async route => {
      writes.push(route.request().postDataJSON());
      await page.unroute("**/api/workbench?*");
      await route.fulfill({ json: { affected_months: [], results: [] } });
    });
    await page.reload();
    const zone = page.getByTestId(`zone-${zoneName}`);
    await zone.getByRole("row", { name: /批次预览测试商户/ }).first().getByText("50.00", { exact: true }).click();
    await expect(page.getByRole("button", { name: "撤回当前关联", exact: true })).toHaveCount(0);
    await zone.getByRole("button", { name: "撤回关联", exact: true }).click();
    const preview = page.getByRole("dialog", { name: "撤回关联", exact: true });
    await expect(preview.getByRole("button", { name: "确认撤回" })).toBeEnabled();
    await expect(preview.getByRole("grid", { name: "待撤回批次流水" })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`batch-${zoneName}-preview.png`), animations: "disabled" });
    expect(writes).toHaveLength(0);
    await preview.getByRole("button", { name: "关闭关联预览" }).click();
    expect(writes).toHaveLength(0);
    await zone.getByRole("button", { name: "撤回关联", exact: true }).click();
    await expect(preview.getByRole("button", { name: "确认撤回" })).toBeEnabled();
    await preview.getByRole("button", { name: "确认撤回" }).click();
    await expect(preview.getByRole("status")).toHaveText("关联操作已完成");
    expect(writes).toEqual([{ expected_version: 7, reason: "由关联台撤回流水规则批次" }]);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
}
