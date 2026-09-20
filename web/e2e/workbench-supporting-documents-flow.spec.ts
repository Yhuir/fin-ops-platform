import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

test("supporting documents refresh the exact item, preview, and restore missing evidence after deletion", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user", workbenchOaInvoiceUnparsedScenario: true });
  const initialResponse = page.waitForResponse(r => new URL(r.url()).pathname === "/api/workbench");
  await page.goto("/");
  const initial = await (await initialResponse).json();
  let uploaded = false;
  let reads = 0;
  let writes = 0;
  const writeBodies: string[] = [];
  const document = {
    id: "doc-e2e", oa_row_id: "oa-unparsed-20260818", expense_item_id: "oa-unparsed-20260818:item:0",
    file_name: "交通费补充凭证与明细一致的完整文件名.png", content_type: "image/png", size_bytes: 67,
    created_at: "2026-09-11T10:00:00+08:00", created_by: "test-user", sha256: "a".repeat(64),
    content_url: "/api/workbench/oa-invoice-supplements/documents/doc-e2e/content",
  };
  await page.context().route("**/api/workbench/oa-invoice-supplements/documents/doc-e2e/content", route => route.fulfill({
    contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=", "base64"),
  }));
  await page.route("**/api/workbench?*", route => {
    reads += 1;
    const payload = structuredClone(initial);
    if (uploaded) {
      const group = payload.unpaired.groups[0];
      group.oa_rows[0].expense_items[0].supporting_documents = [document];
      group.oa_rows[0].expense_items[0].supporting_document_amount = "40.00";
      group.oa_rows[0].expense_items[0].supporting_document_version = writes;
      delete group.workbench_anomaly;
      payload.summary.unpaired_exception_count = 0;
    }
    return route.fulfill({ json: payload });
  });
  await page.route("**/api/workbench/oa-invoice-supplements/documents**", route => {
    const request = route.request();
    if (request.method() === "POST") {
      writes += 1;
      writeBodies.push(request.postData() ?? "");
      uploaded = writes === 1;
    }
    return route.fulfill({ json: { documents: uploaded ? [document] : [], total_amount: uploaded ? "40.00" : null, version: writes } });
  });
  const zone = page.getByTestId("zone-unpaired");
  await zone.getByRole("button", { name: "录入发票" }).click();
  await page.getByRole("tab", { name: "补充凭证" }).click();
  const drawer = page.getByRole("dialog", { name: "管理凭证" });
  await drawer.getByLabel("上传 JPG、PNG 或 PDF 补充凭证").setInputFiles({ name: document.file_name, mimeType: "image/png", buffer: Buffer.from("test") });
  await expect(drawer.getByText(`${document.file_name}（待保存）`)).toBeVisible();
  expect(reads).toBe(0); expect(writes).toBe(0);
  await drawer.getByRole("textbox", { name: "凭证总金额（元）" }).fill("40");
  await drawer.getByRole("button", { name: "保存凭证" }).click();
  await expect(drawer.getByRole("status")).toHaveText("凭证已保存");
  await expect.poll(() => reads).toBe(1);
  expect(writes).toBe(1);
  expect(writeBodies[0]).toContain('name="total_amount"\r\n\r\n40');
  expect(writeBodies[0]).toContain('name="expected_version"\r\n\r\n0');
  await drawer.getByRole("button", { name: "关闭录入发票" }).click();
  const files = zone.locator(".workbench-supporting-files");
  await expect(files).toBeVisible();
  await expect(files.getByText("凭证金额 40.00")).toBeVisible();
  await expect(files.getByText("差额（OA − 凭证）15.00")).toBeVisible();
  await expect(zone.getByRole("button", { name: "录入发票" })).toHaveCount(0);
  expect(await files.evaluate(el => getComputedStyle(el).gridColumn)).toBe("1 / -1");

  const popupPromise = page.waitForEvent("popup");
  await files.getByRole("link", { name: document.file_name }).click();
  const popup = await popupPromise;
  await popup.waitForLoadState();
  expect(popup.url()).toContain("doc-e2e/content");
  await popup.close();
  await page.setViewportSize({ width: 390, height: 844 });
  await files.scrollIntoViewIfNeeded();
  expect(await files.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);

  await files.getByRole("button", { name: "管理凭证" }).click();
  await expect(drawer.getByRole("tab", { name: "补充凭证" })).toHaveAttribute("aria-selected", "true");
  await drawer.getByRole("button", { name: `删除 ${document.file_name}` }).click();
  await expect(drawer.getByText("尚未上传补充凭证。", { exact: true })).toBeVisible();
  expect(reads).toBe(1); expect(writes).toBe(1);
  await drawer.getByRole("button", { name: "保存凭证" }).click();
  await expect(drawer.getByRole("status")).toHaveText("凭证已保存");
  await expect.poll(() => reads).toBe(2);
  expect(writes).toBe(2);
  expect(writeBodies[1]).toContain('name="retained_document_ids"\r\n\r\n[]');
  expect(writeBodies[1]).toContain('name="expected_version"\r\n\r\n1');
  await drawer.getByRole("button", { name: "关闭录入发票" }).click();
  await expect(zone.getByRole("button", { name: "录入发票" })).toBeVisible();
  await expect(files).toHaveCount(0);
  await expectNoUnexpectedSuccessUiErrors(page);
});

test("exception details keep voucher files and amount management for the exact OA item", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user", workbenchOaInvoiceUnparsedScenario: true });
  const initialResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/api/workbench");
  await page.goto("/");
  const initial = await (await initialResponse).json();
  const group = initial.unpaired.groups[0];
  const item = group.oa_rows[0].expense_items[0];
  const document = { id: "doc-legacy", oa_row_id: group.oa_rows[0].id, expense_item_id: item.id,
    file_name: "历史凭证.pdf", content_type: "application/pdf", size_bytes: 10, created_at: "2026-09-11T10:00:00+08:00", content_url: "/doc-legacy/content" };
  item.supporting_documents = [document];
  item.supporting_document_amount = null;
  item.supporting_document_version = 2;
  group.workbench_anomaly.items[0].code = "oa_supporting_document_amount_missing";
  group.workbench_anomaly.items[0].label = "待填写凭证金额";
  group.workbench_anomaly.items[0].display_label = "待填写凭证金额";
  await page.route("**/api/workbench?*", route => route.fulfill({ json: initial }));
  await page.route("**/api/workbench/groups?*", route => route.fulfill({ json: {
    month: "all", zone: "unpaired", groups: [group], total: 1, has_more: false, next_cursor: null,
    exception_counts: { total: 1, amount_total: 0, document_only: 1, by_code: {} },
  } }));
  await page.route("**/api/workbench/groups/detail?*", route => route.fulfill({ json: { group } }));
  await page.route("**/api/workbench/oa-invoice-supplements/documents?*", route => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get("oa_row_id")).toBe(document.oa_row_id);
    expect(url.searchParams.get("expense_item_id")).toBe(document.expense_item_id);
    return route.fulfill({ json: { documents: [document], total_amount: null, version: 2 } });
  });
  await page.reload();
  const zone = page.getByTestId("zone-unpaired");
  await zone.getByRole("button", { name: "未配对异常 1 | 已配对异常 0" }).click();
  const exceptions = page.getByRole("dialog", { name: "异常处理" });
  await exceptions.getByRole("radio", { name: "仅资料异常 1" }).click();
  await exceptions.getByRole("button", { name: "展开异常明细" }).click();
  const grid = exceptions.getByRole("grid", { name: "未配对三栏关联表" });
  await expect(grid.getByRole("link", { name: "历史凭证.pdf" })).toBeVisible();
  await expect(grid.getByText("凭证金额 待填写")).toBeVisible();
  await expect(grid.getByText("差额（OA − 凭证）待核对")).toBeVisible();
  await expect(grid.locator('[role="columnheader"]')).not.toHaveCount(0);
  await grid.getByRole("button", { name: "管理凭证" }).click();
  await expect(exceptions).toHaveCount(0);
  const editor = page.getByRole("dialog", { name: "管理凭证" });
  await expect(editor.getByRole("link", { name: "历史凭证.pdf" })).toBeVisible();
  await expect(editor.getByRole("textbox", { name: "凭证总金额（元）" })).toHaveValue("");
  await expect(editor.getByRole("button", { name: "保存凭证" })).toBeDisabled();
  await expect(page.getByRole("dialog")).toHaveCount(1);
});
