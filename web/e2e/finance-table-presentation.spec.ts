import { expect, test, type Locator, type Page } from "./fixtures/strictTest";
import {
  bankTransactionsPayload,
  installDeterministicApiMocks,
  oaPendingPaymentRowsPayload,
  outputInvoiceCollectionRowsPayload,
} from "./fixtures/apiMocks";
import type { CashFlow, CashFlowSummary } from "../src/components/cash/CashFlows.types";

async function expectColumnAlignment(table: Locator, role: string, alignment: string) {
  const columns = table.locator(`thead [data-column-role="${role}"]`);
  const cells = table.locator(`tbody [data-column-role="${role}"]`);
  expect(await columns.count(), `${role} header exists`).toBeGreaterThan(0);
  expect(await cells.count(), `${role} data exists`).toBeGreaterThan(0);
  for (const element of [...await columns.all(), ...await cells.all()]) {
    await expect(element).toHaveCSS("text-align", alignment);
  }
}

async function expectStableButton(page: Page, button: Locator) {
  await expect(button).toBeVisible();
  await expect(button).toHaveCSS("border-top-width", "1px");
  const before = await button.boundingBox();
  expect(before).not.toBeNull();
  await button.hover();
  await expect(button).toHaveCSS("border-top-width", "1px");
  const after = await button.boundingBox();
  expect(after).not.toBeNull();
  for (const key of ["x", "y", "width", "height"] as const) {
    expect(Math.abs(after![key] - before![key]), `hover keeps button ${key}`).toBeLessThan(0.5);
  }
  await page.mouse.move(0, 0);
  await button.focus();
  const focused = await button.boundingBox();
  expect(focused).toEqual(before);
}

async function expectAmountHierarchy(primary: Locator, metadata: Locator) {
  const amountBox = await primary.boundingBox();
  const metadataBox = await metadata.boundingBox();
  expect(amountBox).not.toBeNull();
  expect(metadataBox).not.toBeNull();
  expect(metadataBox!.y).toBeGreaterThanOrEqual(amountBox!.y + amountBox!.height);
  const primarySize = await primary.evaluate(node => parseFloat(getComputedStyle(node).fontSize));
  const secondarySize = await metadata.locator(".bank-account-value").evaluate(node => parseFloat(getComputedStyle(node).fontSize));
  expect(primarySize).toBeGreaterThan(secondarySize);
  await expect(metadata.locator(".bank-account-value")).not.toHaveClass(/bank-account-tag/);
  await expect(metadata.locator(".bank-account-value")).toHaveCSS("flex-direction", "row");
}

async function expectNativeTableAlignment(table: Locator, alignments: string[]) {
  await expect(table).toBeVisible();
  for (const [index, alignment] of alignments.entries()) {
    await expect(table.locator("thead th").nth(index)).toHaveCSS("text-align", alignment);
    const cells = table.locator(`tbody tr > :nth-child(${index + 1})`);
    expect(await cells.count()).toBeGreaterThan(0);
    for (const cell of await cells.all()) await expect(cell).toHaveCSS("text-align", alignment);
  }
}

async function installCashPresentationFixture(page: Page) {
  const account = { id: "10000000-0000-4000-8000-000000000001", name: "合成现金账户" };
  const flow: CashFlow = {
    id: "20000000-0000-4000-8000-000000000001", version: 1,
    occurred_on: "2026-09-01", kind: "payment", amount: "12000.00",
    from_account: account, to_account: null, project: null, person_name: "合成经办人",
    category: { id: "30000000-0000-4000-8000-000000000001", name: "合成往来", group: "turnover" },
    content: "合成现金布局核对", source_kind: "manual", task: null,
    income_amount: null, expense_amount: "12000.00", account_running_balance: "0.00",
    remark: null, created_by_account: "E2E", created_by_name: "合成测试",
    created_at: "2026-09-01T08:00:00Z", updated_at: "2026-09-01T08:00:00Z",
  };
  const summary: CashFlowSummary = {
    period: { date_from: "2026-01-01", date_to: "2026-12-31" },
    filtered_totals: { flow_count: 1, income_amount: "0.00", expense_amount: "12000.00", transfer_amount: "0.00" },
    account_balances: [{ account_id: account.id, account_name: account.name, opening_date: "2026-01-01",
      coverage_state: "complete", coverage_start: "2026-01-01", opening_balance: "12000.00",
      balance_at_coverage_start: "12000.00", period_inflow: "0.00", period_outflow: "12000.00", ending_balance: "0.00" }],
  };
  await page.route("**/api/cash/flows?**", route => route.fulfill({
    contentType: "application/json", body: JSON.stringify({ rows: [flow], summary, pagination: { page: 1, page_size: 50, total: 1 } }),
  }));
}

test.describe("ordinary page finance presentation", () => {
  test("input invoices keep primary amounts above subdued bank metadata and stable secondary controls", async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, { sessionMode: "admin" });
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/input-invoice-usage");
    const table = page.getByRole("grid", { name: "进项发票使用情况表" });
    await expect(table.getByText("浏览器进项供应商").first()).toBeVisible();
    await expectColumnAlignment(table, "amount", "right");
    await expectColumnAlignment(table, "description", "left");
    for (const index of [0, 1, 5, 6, 7]) {
      await expect(table.locator("thead th").nth(index)).toHaveCSS("text-align", "left");
      await expect(table.locator("tbody tr").first().locator("td, th").nth(index)).toHaveCSS("text-align", "left");
    }
    await expectColumnAlignment(table, "status", "center");
    await expectStableButton(page, page.getByRole("button", { name: "刷新", exact: true }));

    for (const width of [1920, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      const row = table.locator("tbody tr").first();
      const payment = row.locator(".input-invoice-usage-payment-cell");
      const seller = row.locator("td, th").nth(1);
      const paymentBox = await payment.boundingBox();
      const sellerBox = await seller.boundingBox();
      expect(paymentBox).not.toBeNull();
      expect(sellerBox).not.toBeNull();
      expect(paymentBox!.width).toBeLessThanOrEqual(170);
      expect(paymentBox!.width).toBeLessThan(sellerBox!.width);
      const primary = row.locator(".input-invoice-usage-bank-amount-line .input-invoice-usage-money-primary");
      const metadata = row.locator(".input-invoice-usage-bank-tag-row");
      await expect(primary).toHaveText("88.00");
      await expect(metadata.locator(".bank-account-primary")).toHaveText("建行");
      await expect(metadata.locator(".bank-account-secondary")).toHaveText("1138");
      await expectAmountHierarchy(primary, metadata);
      await page.screenshot({ path: testInfo.outputPath(`input-finance-presentation-${width}.png`), fullPage: true });
    }
  });

  test("bank and cash columns align headers with content, including account balance drawers", async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, { sessionMode: "admin" });
    await installCashPresentationFixture(page);
    // Source-bank presentation fields belong only to this visual scenario.
    await page.route("**/api/bank-details/transactions?**", route => {
      const payload = bankTransactionsPayload(false);
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        ...payload, rows: payload.rows.map(row => ({ ...row, bank_short_name: "建行" })),
      }) });
    });
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/bank-details");
    const bank = page.getByRole("grid", { name: "交易流水" });
    await expect(bank.locator("tbody .bank-col-counterparty").first()).toBeVisible();
    await expectColumnAlignment(bank, "identity", "left");
    await expectColumnAlignment(bank, "description", "left");
    await expectColumnAlignment(bank, "amount", "right");
    await expectColumnAlignment(bank, "status", "center");
    const bankAmount = bank.locator("tbody .bank-amount-value").first();
    const bankMetadata = bank.locator("tbody .bank-amount-metadata").first();
    await expect(bankAmount).toHaveText("58000.00");
    await expect(bankMetadata.locator(".bank-account-primary")).toHaveText("建行");
    await expect(bankMetadata.locator(".bank-account-secondary")).toHaveText("1138");
    await expectAmountHierarchy(bankAmount, bankMetadata);
    const exportButton = page.locator(".bank-export-button");
    await expectStableButton(page, exportButton);
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    await expect(exportButton).toBeFocused();
    await expect(exportButton).toHaveCSS("outline-style", "solid");
    await expect(exportButton).toHaveCSS("outline-width", "2px");
    await page.screenshot({ path: testInfo.outputPath("bank-finance-presentation.png"), fullPage: true });

    await page.goto("/cash?section=flows");
    const cash = page.getByRole("grid", { name: "现金流水明细" });
    await expect(cash.getByText("合成现金布局核对")).toBeVisible();
    await expectColumnAlignment(cash, "amount", "right");
    await expectColumnAlignment(cash, "date", "center");
    await expectColumnAlignment(cash, "status", "center");
    await expectColumnAlignment(cash, "action", "center");
    await expectColumnAlignment(cash, "description", "left");
    await page.getByRole("button", { name: "账户期间余额", exact: true }).click();
    const balances = page.getByRole("grid", { name: "账户期间余额" });
    await expectColumnAlignment(balances, "amount", "right");
    await expect(balances.getByText("0.00").first()).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("cash-balance-presentation.png"), fullPage: true });
  });

  test("output and OA keep source amounts primary with inline secondary bank labels", async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, { sessionMode: "admin" });
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.route("**/api/output-invoice-collections/rows?**", route => {
      const payload = outputInvoiceCollectionRowsPayload();
      const first = payload.rows[0];
      const bank = first.bank as { primary: Record<string, unknown> };
      first.bank = { ...bank, original_amount: "5000.00", original_transaction_count: 1,
        primary: { ...bank.primary, original_amount: "5000.00", bank_short_name: "建行" } };
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(payload) });
    });
    await page.route("**/api/oa-pending-payments/rows?**", route => {
      const payload = oaPendingPaymentRowsPayload();
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        ...payload, rows: payload.rows.map(row => ({ ...row,
          bankTransaction: { ...row.bankTransaction, bankShortName: "建行" },
        })),
      }) });
    });

    await page.goto("/output-invoice-collections");
    const output = page.getByRole("grid", { name: "销项发票收款情况表" });
    await expect(output.getByText("XSFP-E2E-0001", { exact: true })).toBeVisible();
    await expectColumnAlignment(output, "amount", "right");
    await expectColumnAlignment(output, "identity", "left");
    await expectColumnAlignment(output, "status", "center");
    const outputRow = output.locator("tbody tr").first();
    const outputAmount = outputRow.locator("td, th").nth(6).locator(".output-invoice-collections-table-text--numeric");
    const outputMetadata = outputRow.locator(".output-invoice-collections-tag-row--right");
    await expect(outputAmount).toHaveText("5000.00");
    await expect(outputMetadata.locator(".bank-account-primary")).toHaveText("建行");
    await expect(outputMetadata.locator(".bank-account-secondary")).toHaveText("8106");
    await expectAmountHierarchy(outputAmount, outputMetadata);
    await expect(outputMetadata.locator(".output-invoice-collections-table-tag")).toHaveCSS("font-weight", "500");
    await page.screenshot({ path: testInfo.outputPath("output-finance-presentation.png"), fullPage: true });

    await page.goto("/oa-pending-payments");
    const oa = page.getByRole("grid", { name: "OA待付款核对表格" });
    await expect(oa.getByText("浏览器付款申请人", { exact: true })).toBeVisible();
    await expectColumnAlignment(oa, "identity", "left");
    await expectColumnAlignment(oa, "status", "center");
    const oaRow = oa.locator("tbody tr").first();
    const oaAmount = oaRow.locator(".oa-pending-payments-bank-amount-line .oa-pending-payments-table-text--numeric");
    const oaMetadata = oaRow.locator(".oa-pending-payments-bank-metadata");
    await expect(oaAmount).toHaveText("8000.00");
    await expect(oaMetadata.locator(".bank-account-primary")).toHaveText("建行");
    await expect(oaMetadata.locator(".bank-account-secondary")).toHaveText("1234");
    await expectAmountHierarchy(oaAmount, oaMetadata);
    await expect(oaMetadata.locator(".finance-direction-tag")).toHaveCSS("font-weight", "500");
    await expect(oaRow.locator(".oa-pending-payments-bank-grid__amount")).toHaveCSS("text-align", "right");
    await expect(oa.locator(".oa-pending-payments-subheader-grid--bank .oa-pending-payments-subheader-grid__amount")).toHaveCSS("text-align", "right");
    await page.screenshot({ path: testInfo.outputPath("oa-finance-presentation.png"), fullPage: true });
  });

  test("native rule and turnover drawer tables preserve semantic column alignment", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "admin", turnoverCostFanout: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/bank-details");
    await page.getByRole("button", { name: /自动标签规则/ }).click();
    const rules = page.getByRole("table", { name: "自动标签规则表格" });
    await expect(rules).toBeVisible();
    await expect(rules.locator(".bank-auto-tag-actions-column")).toHaveCSS("text-align", "center");
    for (const cell of await rules.locator(".bank-auto-tag-actions-cell").all()) {
      await expect(cell).toHaveCSS("text-align", "center");
    }

    await page.goto("/turnover-ledger");
    await page.getByRole("button", { name: "查看云南建设有限公司详情", exact: true }).click();
    const details = page.getByRole("dialog", { name: "云南建设有限公司", exact: true });
    await expectNativeTableAlignment(details.locator(".turnover-closure-table--details"), ["center", "left", "right", "center"]);
    await details.getByRole("button", { name: "关闭往来对象详情", exact: true }).click();
    await page.getByRole("button", { name: "展开 云南建设有限公司 流水明细", exact: true }).click();
    const controls = page.getByRole("grid", { name: "云南建设有限公司的银行流水" }).locator("[data-slot='checkbox-control']");
    await expect(controls).toHaveCount(2);
    for (const control of await controls.all()) await control.click();
    await expect(page.getByText("已选 2 笔", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "确认闭环", exact: true }).click();
    const confirmation = page.getByRole("dialog", { name: "确认外部往来闭环", exact: true });
    await expectNativeTableAlignment(confirmation.locator(".turnover-closure-table--confirmation"), ["center", "left", "center", "right"]);
  });

  test("workbench stays outside the presentation scope after navigating to ordinary pages", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "admin" });
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/");
    await expect(page.locator(".workbench-shell")).toBeVisible();
    await expect(page.locator("main[data-finance-presentation]")).toHaveCount(0);
    const button = page.locator(".workbench-shell .zone-aux-action").first();
    await expect(button).toBeVisible();
    const readStyle = (target: Locator) => target.evaluate(node => {
      const style = getComputedStyle(node);
      return { background: style.backgroundColor, border: style.borderTopWidth, color: style.color, fontSize: style.fontSize };
    });
    const before = await readStyle(button);
    await page.getByRole("link", { name: "银行明细", exact: true }).click();
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await expect(page.locator("main[data-finance-presentation]")).toHaveCount(1);
    await page.getByRole("link", { name: "关联台", exact: true }).click();
    await expect(page.locator(".workbench-shell")).toBeVisible();
    await expect(page.locator("main[data-finance-presentation]")).toHaveCount(0);
    expect(await readStyle(button)).toEqual(before);
  });
});
