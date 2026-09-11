import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test("supporting documents refresh the exact item, preview, and restore missing evidence after deletion", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user", workbenchOaInvoiceUnparsedScenario: true });
  const initialResponse = page.waitForResponse(r => new URL(r.url()).pathname === "/api/workbench");
  await page.goto("/");
  const initial = await (await initialResponse).json();
  let uploaded = false;
  let reads = 0;
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
      delete group.workbench_anomaly;
      payload.summary.unpaired_exception_count = 0;
    }
    return route.fulfill({ json: payload });
  });
  await page.route("**/api/workbench/oa-invoice-supplements/documents**", route => {
    const request = route.request();
    if (request.method() === "POST") { uploaded = true; return route.fulfill({ json: { documents: [document] } }); }
    if (request.method() === "DELETE") { uploaded = false; return route.fulfill({ json: { status: "deleted" } }); }
    return route.fulfill({ json: { documents: uploaded ? [document] : [] } });
  });
  const zone = page.getByTestId("zone-unpaired");
  await zone.getByRole("button", { name: "录入发票" }).click();
  await page.getByRole("tab", { name: "补充凭证" }).click();
  const drawer = page.getByRole("dialog", { name: "管理凭证" });
  await drawer.getByLabel("上传 JPG、PNG 或 PDF 补充凭证").setInputFiles({ name: document.file_name, mimeType: "image/png", buffer: Buffer.from("test") });
  await expect(drawer.getByRole("link", { name: document.file_name })).toBeVisible();
  await expect.poll(() => reads).toBe(1);
  await drawer.getByRole("button", { name: "关闭录入发票" }).click();
  const files = zone.locator(".workbench-supporting-files");
  await expect(files).toBeVisible();
  await expect(zone.getByRole("button", { name: "录入发票" })).toHaveCount(0);
  expect(await files.evaluate(el => getComputedStyle(el).gridColumn)).toBe("1 / -1");
  await page.screenshot({ path: "/tmp/support-local-wide.png", fullPage: true });
  const popupPromise = page.waitForEvent("popup");
  await files.getByRole("link", { name: document.file_name }).click();
  const popup = await popupPromise;
  await popup.waitForLoadState();
  expect(popup.url()).toContain("doc-e2e/content");
  await popup.close();
  await page.setViewportSize({ width: 390, height: 844 });
  await files.scrollIntoViewIfNeeded();
  expect(await files.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await page.screenshot({ path: "/tmp/support-local-narrow.png" });
  await files.getByRole("button", { name: "管理凭证" }).click();
  await expect(drawer.getByRole("tab", { name: "补充凭证" })).toHaveAttribute("aria-selected", "true");
  await drawer.getByRole("button", { name: `删除 ${document.file_name}` }).click();
  await expect(drawer.getByText("尚未上传补充凭证。", { exact: true })).toBeVisible();
  await expect.poll(() => reads).toBe(2);
  await drawer.getByRole("button", { name: "关闭录入发票" }).click();
  await expect(zone.getByRole("button", { name: "录入发票" })).toBeVisible();
  await expect(files).toHaveCount(0);
});
