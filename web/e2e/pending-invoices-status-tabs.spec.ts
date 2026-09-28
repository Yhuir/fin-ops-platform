import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks, pendingInvoiceRowsPayload } from "./fixtures/apiMocks";
import { pendingAcquisitionFixture } from "../src/test/pendingInvoiceFixtures";

const codes = ["paid_pending_invoice", "paid_invoiced", "invoice_not_fully_paid", "bank_statement_as_invoice", "no_invoice_required", "income_pending_invoice", "income_invoiced", "income_no_invoice_required", "cash_income"];

test("two native segment rows partition bank counts and share status/export query state", async ({ page }, info) => {
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
    const scoped = rows.filter((_, index) => direction === "all" || (direction === "expense" ? index < 5 : index >= 5));
    const filters = JSON.parse(url.searchParams.get("filters") ?? "[]") as {field:string; values:string[]}[];
    const statuses = filters.find(filter => filter.field === "status_code")?.values;
    const selected = scoped.filter(row => !statuses || statuses.includes(row.invoice_acquisition_status.code));
    const counts = pendingAcquisitionFixture(scoped);
    await route.fulfill({ json: { ...pendingInvoiceRowsPayload(false), direction, rows: selected,
      pagination: { page: 1, page_size: 50, total: selected.length },
      acquisition_summary: { ...counts, bank_count: selected.length },
      summary: { source_summary: {bank_transaction_rows:9,expense_rows:5,income_rows:4,current_direction_rows:scoped.length,excluded_direction_rows:9-scoped.length} },
    } });
  });
  await page.goto("/pending-invoices");
  const directionTabs = page.getByRole("tablist", { name: "待找发票流水范围" });
  const statusTabs = page.getByRole("tablist", { name: "发票获取状态分类" });
  await expect(directionTabs.getByRole("tab", { name:"全部 9 笔" })).toHaveAttribute("aria-selected", "true");
  expect(queries[0].searchParams.has("filters")).toBe(false);
  for (const [label, count, statusCount] of [["全部",9,7],["支出",5,6],["收入",4,5]] as const) {
    await directionTabs.getByRole("tab", { name:`${label} ${count} 笔` }).click();
    await expect(statusTabs.getByRole("tab", { name:`全部状态 ${count} 笔` })).toHaveAttribute("aria-selected", "true");
    await expect(statusTabs.getByRole("tab")).toHaveCount(statusCount);
    const names = await statusTabs.getByRole("tab").allTextContents();
    for (let index=1; index<names.length; index++) {
      const tab = statusTabs.getByRole("tab").nth(index);
      const expected = Number(names[index].match(/(\d+) 笔/)![1]);
      const before = queries.length;
      const response = page.waitForResponse(r => r.url().includes("/api/pending-invoices/rows?") && !r.url().includes("include_statistics=true"));
      await tab.click();
      const payload = await (await response).json();
      expect(payload.acquisition_summary.bank_count).toBe(expected);
      expect(payload.rows).toHaveLength(expected);
      await expect(tab).toHaveAttribute("aria-selected", "true");
      expect(queries.length-before).toBe(1);
      await expect(statusTabs.getByRole("tab", { name:`全部状态 ${count} 笔` })).toBeVisible();
    }
  }
  await directionTabs.getByRole("tab", { name:"全部 9 笔" }).click();
  await expect(statusTabs.getByRole("tab", { name:"全部状态 9 笔" })).toHaveAttribute("aria-selected", "true");
  for (const width of [1600,960]) {
    await page.setViewportSize({width,height:1000});
    await expect(statusTabs.getByRole('tab', { selected: true })).toHaveCount(1);
  await expect(statusTabs.getByRole('tab', { selected: true })).toHaveCSS('background-color', 'rgb(29, 78, 216)');
    expect(await page.locator('.pending-invoices-toolbar').evaluate(el => el.scrollWidth <= el.clientWidth+1)).toBe(true);
    await page.screenshot({path:info.outputPath(`pending-segments-${width}.png`),animations:"disabled"});
  }
  await statusTabs.getByRole("tab", { name:/^金额待核对 / }).click();
  const preview = page.waitForResponse(r => r.url().includes("/api/pending-invoices/export-summary"));
  await page.getByRole("button", { name:"筛选内容导出" }).click();
  const url = new URL((await preview).url());
  expect(url.searchParams.has("filters")).toBe(false);
  expect(errors).toEqual([]);
});
