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
  await expect(files.getByText(/本项差额|与同项发票合并核对/)).toHaveCount(0);
  await expect(zone.getByRole("button", { name: "录入发票", exact: true })).toHaveCount(0);
  const supplement = zone.getByRole("button", { name: "录入发票 55 元付款项" });
  await expect(supplement).toHaveText("+");
  await supplement.click();
  await expect(page.getByRole("dialog", { name: "录入发票" })).toBeVisible();
  await page.getByRole("button", { name: "关闭录入发票" }).click();
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
  await expect(grid.getByText(/本项差额|与同项发票合并核对/)).toHaveCount(0);
  await expect(grid.locator('[role="columnheader"]')).not.toHaveCount(0);
  await grid.getByRole("button", { name: "管理凭证" }).click();
  await expect(exceptions).toHaveCount(0);
  const editor = page.getByRole("dialog", { name: "管理凭证" });
  await expect(editor.getByRole("link", { name: "历史凭证.pdf" })).toBeVisible();
  await expect(editor.getByRole("textbox", { name: "凭证总金额（元）" })).toHaveValue("");
  await expect(editor.getByRole("button", { name: "保存凭证" })).toBeDisabled();
  await expect(page.getByRole("dialog")).toHaveCount(1);
});

test("a long multi-OA group uses a compact icon and amount-only popover without additional I/O", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user", workbenchAmountMismatchScenario: true, workbenchInitialRelationConfirmed: true });
  const firstResponse = page.waitForResponse(r => new URL(r.url()).pathname === "/api/workbench");
  await page.goto("/");
  const payload = await (await firstResponse).json();
  const group = payload.unpaired.groups[0];
  const oaTemplate = group.oa_rows[0];
  const invoiceTemplate = group.invoice_rows[0];
  group.group_id = "case:CASE-EXPLANATION";
  group.relation_mode = "batch_accounting";
  group.oa_rows = [];
  group.invoice_rows = [];
  const layouts = [["320", "150.40"], ["150", "182.44"], ["50.22"], ["54", "8", "25", "23", "30"], ["280"]];
  const amounts = ["470.40", "332.44", "50.22", "140", "280"];
  layouts.forEach((values, i) => {
    const id = `oa-explanation-${i}`;
    const items = values.map((amount, j) => ({ id: `${id}:item:${j}`, row_index: String(j), amount,
      project_name: "测试项目", expense_type: "交通费", expense_content: i === 1 && j === 1 ? "顺风车费用" : "高速通行费",
      ...(i === 3 ? { supporting_document_amount: amount, supporting_document_version: 1,
        supporting_documents: [{ id: `document-${j}`, file_name: `${amount}.png`, content_type: "image/png", size_bytes: 1,
          content_url: `/test-document-${j}`, created_at: "2026-09-01T00:00:00+08:00" }] } : {}),
    }));
    group.oa_rows.push({ ...oaTemplate, id, case_id: "CASE-EXPLANATION", amount: amounts[i], applicant: `测试申请人${i}`, expense_items: items });
    items.forEach((item, j) => {
      if (i === 3) return;
      const invoiceAmounts = i === 1 && j === 1 ? ["28.25", "126.16", "14.02", "20.58"]
        : i === 0 && j === 1 ? ["25", "25", "25", "25", "25", "25.40"] : [item.amount];
      invoiceAmounts.forEach((amount, k) => group.invoice_rows.push({ ...invoiceTemplate, id: `invoice-${i}-${j}-${k}`,
        case_id: "CASE-EXPLANATION", amount, total_with_tax: amount, source_oa_id: id, source_expense_item_ids: [item.id],
        workbench_anomalies: [] }));
    });
  });
  group.bank_rows[0].amount = "1273.06";
  group.bank_rows[0].debit_amount = "1273.06";
  group.amount_check = { status: "mismatch", direction: "expense", bank_amount: "1273.06", oa_amount: "1273.06",
    oa_total: "1273.06", bank_total: "1273.06", invoice_total: "1139.63", supporting_document_total: "140.00",
    bank_original_total: "1273.06", bank_related_total: "1273.06",
    evidence_total: "1279.63", evidence_complete: true, amount_delta: "6.57", requires_note: true };
  group.workbench_anomaly.items = [{ ...group.workbench_anomaly.items[0], code: "oa_bank_equal_invoice_more",
    display_label: "OA 流水一致，票多", label: "OA 流水一致，票多", display_scope: "group", display_pane: "group",
    amount_delta: "6.57", oa_total: "1273.06", bank_total: "1273.06", invoice_total: "1139.63", evidence_total: "1279.63",
    bank_original_total: "1273.06", bank_related_total: "1273.06",
    source_oa_ids: group.oa_rows.map((row: { id: string }) => row.id), source_expense_item_ids: [],
    expense_item_differences: [{ expense_item_ids: ["oa-explanation-1:item:1"], oa_total: "182.44", evidence_total: "189.01", amount_delta: "6.57" }] }];
  group.row_counts = { oa: 5, bank: 1, invoice: 14 };
  group.completion = { is_complete: false, missing_row_types: [], blocking_reasons: ["anomaly_review_required"] };
  payload.unpaired.groups = [group];
  await page.route("**/api/workbench?*", route => route.fulfill({ json: payload }));
  await page.reload();
  const zone = page.getByTestId("zone-unpaired");
  const indicator = zone.getByRole("button", { name: "该关联组有 1 项异常，查看详情" });
  await expect(indicator).toHaveText("");
  await expect(zone.locator(".workbench-group-anomaly-heading, .candidate-group-frame")).toHaveCount(0);
  let requests = 0;
  page.on("request", request => { if (new URL(request.url()).pathname.startsWith("/api/workbench")) requests++; });
  const files = zone.locator(".workbench-supporting-files");
  await expect(files).toHaveCount(5);
  await expect(files.getByText(/^凭证金额 /)).toHaveCount(5);
  await expect(files.getByText(/本项差额|与同项发票合并核对/)).toHaveCount(0);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await indicator.scrollIntoViewIfNeeded();
    await expect(indicator).toBeInViewport();
    const iconBox = await indicator.boundingBox();
    expect(iconBox!.height).toBe(28);
    expect(iconBox!.width).toBe(28);
    const grid = indicator.locator("..");
    expect(await grid.evaluate(element => getComputedStyle(element).position)).toBe("relative");
    expect(await indicator.evaluate(element => getComputedStyle(element).position)).toBe("absolute");
    await page.mouse.move(0, 0);
    await indicator.blur();
    await indicator.focus();
    const popover = page.getByRole("dialog", { name: "该关联组异常详情" });
    await expect(popover).toHaveText("OA1273.06银行流水1273.06票据凭证1279.63");
    const box = await popover.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(width);
    await page.keyboard.press("Escape");
    await expect(popover).toHaveCount(0);
  }
  await page.mouse.move(0, 0);
  await indicator.blur();
  await indicator.focus();
  const explanation = page.getByRole("dialog", { name: "该关联组异常详情" });
  await expect(explanation).toHaveText("OA1273.06银行流水1273.06票据凭证1279.63");
  await page.keyboard.press("Escape");
  await expect(explanation).toHaveCount(0);
  expect(requests).toBe(0);
  await expectNoUnexpectedSuccessUiErrors(page);
});
