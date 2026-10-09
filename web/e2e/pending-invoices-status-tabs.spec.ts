import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks, pendingInvoiceRowsPayload } from "./fixtures/apiMocks";
import { pendingAcquisitionFixture } from "../src/test/pendingInvoiceFixtures";

const codes = ["paid_pending_invoice", "paid_invoiced", "invoice_not_fully_paid", "invoice_amount_missing", "bank_statement_as_invoice", "no_invoice_required", "income_pending_invoice", "income_invoiced", "income_no_invoice_required", "cash_income"];

test("continuous hierarchy partitions bank counts and share status/export query state", async ({ page }, info) => {
  await installDeterministicApiMocks(page, { sessionMode: "user" });
  const errors: string[] = [];
  const queries: URL[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const template = pendingInvoiceRowsPayload(false).rows[0];
  const rows = codes.map((code, index) => ({ ...structuredClone(template), id: `status-${index}`,
    bank_transaction: { ...structuredClone(template.bank_transaction), id: `status-${index}` },
    invoice_acquisition_status: { ...template.invoice_acquisition_status, code },
  }));
  await page.route("**/api/pending-invoices/rows?**", async route => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("include_statistics") !== "true") queries.push(url);
    const direction = url.searchParams.get("direction") ?? "all";
    const scoped = rows.filter((_, index) => direction === "all" || (direction === "expense" ? index < 6 : index >= 6));
    const filters = JSON.parse(url.searchParams.get("filters") ?? "[]") as {field:string; values:string[]}[];
    const statuses = filters.find(filter => filter.field === "status_code")?.values;
    const selected = scoped.filter(row => !statuses || statuses.includes(row.invoice_acquisition_status.code));
    const counts = pendingAcquisitionFixture(scoped);
    await route.fulfill({ json: { ...pendingInvoiceRowsPayload(false), direction, rows: selected,
      pagination: { page: 1, page_size: 50, total: selected.length },
      acquisition_summary: { ...counts, scope_status_counts: pendingAcquisitionFixture(rows).status_counts, bank_count: selected.length },
      summary: { source_summary: {bank_transaction_rows:10,expense_rows:6,income_rows:4,current_direction_rows:scoped.length,excluded_direction_rows:10-scoped.length} },
    } });
  });
  await page.goto("/pending-invoices");
  const header = page.getByRole("region", { name: "待找发票分类" });
  await expect(header.getByRole("button", { name:"全部流水 10 笔" })).toHaveAttribute("aria-pressed", "true");
  expect(queries[0].searchParams.has("filters")).toBe(false);
  for (const [scope, label, count, children] of [["expense","支出流水",6,5],["income","收入流水",4,4]] as const) {
    const group = header.getByRole("group", { name: label, exact: true });
    await group.getByRole("button", { name: `${label} ${count} 笔` }).click();
    await expect(group.getByRole("button", { name: `${label} ${count} 笔` })).toHaveAttribute("aria-pressed", "true");
    await expect(group.locator('.table-classification__leaf')).toHaveCount(children);
    for (const button of await group.locator('.table-classification__leaf').all()) {
      const expected = Number((await button.textContent())!.match(/(\d+) 笔/)![1]);
      const before = queries.length;
      const response = page.waitForResponse(r => r.url().includes("/api/pending-invoices/rows?") && !r.url().includes("include_statistics=true"));
      await button.click();
      const payload = await (await response).json();
      expect(payload.acquisition_summary.bank_count).toBe(expected);
      expect(payload.rows).toHaveLength(expected);
      expect(queries.at(-1)!.searchParams.get('direction')).toBe(scope);
      await expect(button).toHaveAttribute("aria-pressed", "true");
      expect(queries.length-before).toBe(1);
      await expect(header.getByRole("button", { name:"全部流水 10 笔" })).toBeVisible();
    }
  }
  for (const width of [1920,1440,1366,1024]) {
    await page.setViewportSize({width,height:900});
    expect(await header.evaluate(el => el.scrollWidth <= el.clientWidth+1)).toBe(true);
    await expect(header).toHaveCSS('border-width', '0px');
    for (const button of await header.getByRole('button').all()) {
      expect(await button.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
      await expect(button).toHaveCSS('border-radius','0px');
    }
    await page.screenshot({path:info.outputPath(`pending-classification-${width}.png`),animations:"disabled"});
  }
  await header.getByRole("button", { name:/^有票·金额待核对 / }).click();
  const preview = page.waitForResponse(r => r.url().includes("/api/pending-invoices/export-summary"));
  await page.getByRole("button", { name:"筛选内容导出" }).click();
  const url = new URL((await preview).url());
  expect(JSON.parse(url.searchParams.get("filters")!)).toEqual([
    { field: "status_code", operator: "in", values: ["invoice_not_fully_paid", "invoice_amount_missing"] },
  ]);
  expect(url.searchParams.get("direction")).toBe("expense");
  expect(errors).toEqual([]);
});
