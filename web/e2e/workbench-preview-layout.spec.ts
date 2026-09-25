import { expect, test, type Page } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.use({ reducedMotion: "reduce" });

async function expectPreviewPresentation(page: Page) {
  const dialog = page.locator('.relation-preview-drawer');
  const visuals = await dialog.evaluate(el => {
    const before = el.querySelector('.relation-preview-section-before .relation-preview-section-heading')!;
    const after = el.querySelector('.relation-preview-section-after .relation-preview-section-heading')!;
    return {
      headings: [getComputedStyle(before).backgroundColor, getComputedStyle(after).backgroundColor],
      groups: Array.from(el.querySelectorAll('.relation-preview-group')).map(group => ({
        band: group.getAttribute('data-band'), color: getComputedStyle(group).backgroundColor,
      })),
      records: Array.from(el.querySelectorAll('.relation-preview-record')).map(record => {
        const r = record.getBoundingClientRect();
        const content = record.querySelector('.relation-preview-record-content')!;
        const c = content.getBoundingClientRect();
        const money = record.querySelector('.relation-preview-payment')?.getBoundingClientRect();
        return { visible: r.width > 0, textAlign: getComputedStyle(content).textAlign,
          verticalOffset: Math.abs((r.top+r.bottom-c.top-c.bottom)/2),
          moneyOffset: money ? Math.abs((r.left+r.right-money.left-money.right)/2) : 0 };
      }),
    };
  });
  expect(visuals.headings[0]).not.toBe(visuals.headings[1]);
  for (const group of visuals.groups) expect(group.color).toBe(group.band === '0' ? 'rgb(255, 248, 230)' : 'rgb(231, 243, 255)');
  for (const record of visuals.records.filter(r => r.visible)) {
    expect(record.textAlign).toBe('center');
    expect(record.verticalOffset).toBeLessThanOrEqual(1);
    expect(record.moneyOffset).toBeLessThanOrEqual(1);
  }
  await expect(dialog.getByText(/不含税|本次关联/)).toHaveCount(0);
}

async function openConfirm(page: Page) {
  const zone = page.getByTestId("zone-unpaired");
  await zone
    .getByTestId("candidate-group-unpaired-row:oa-o-202603-001")
    .getByRole("row", { name: /陈涛.*智能工厂设备商/ })
    .click();
  await zone
    .getByTestId("candidate-group-unpaired-row:bk-o-202603-001")
    .getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })
    .click();
  await zone
    .getByTestId("candidate-group-unpaired-row:iv-o-202603-001")
    .getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })
    .getByRole("cell")
    .first()
    .click();
  const response = page.waitForResponse((r) =>
    r.url().endsWith("/confirm-link/preview"),
  );
  await zone.getByRole("button", { name: "确认关联", exact: true }).click();
  return (await response).json();
}

test("compares exact groups side by side and keeps notes next to submit without extra requests", async ({
  page,
}, info) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "user" });
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/");
  await openConfirm(page);
  const dialog = page.getByRole("dialog", { name: "确认关联", exact: true });
  const before = dialog.getByTestId("relation-preview-before"),
    after = dialog.getByTestId("relation-preview-after");
  await expect(before.getByRole("rowgroup")).toHaveCount(3);
  await expect(after.getByRole("rowgroup")).toHaveCount(1);
  await expectPreviewPresentation(page);
  const bankRecord = after.locator('[data-pane="bank"] .relation-preview-record');
  await expect(bankRecord.locator('.relation-preview-payment')).toContainText('支');
  await expect(bankRecord.locator('.relation-preview-payment .relation-preview-money')).toHaveText('58000.00');
  await expect(bankRecord.locator('.relation-preview-tag.chip')).toHaveCount(1);
  const geometry = await dialog.evaluate((el) => {
    const a = el
        .querySelector("#relation-preview-before")!
        .getBoundingClientRect(),
      b = el.querySelector("#relation-preview-after")!.getBoundingClientRect();
    const note = el
        .querySelector(".relation-preview-footer-note")!
        .getBoundingClientRect(),
      button = el
        .querySelector(".relation-preview-actions button")!
        .getBoundingClientRect();
    const scroll = el.querySelector(".relation-preview-compare-scroll")!;
    return {
      right: a.right,
      left: b.left,
      dy: Math.abs(a.top - b.top),
      noteRight: note.right,
      buttonLeft: button.left,
      noteBottom: note.bottom,
      buttonBottom: button.bottom,
      overflow: scroll.scrollWidth - scroll.clientWidth,
    };
  });
  expect(geometry.right).toBeLessThanOrEqual(geometry.left + 1);
  expect(geometry.dy).toBeLessThan(2);
  expect(geometry.noteRight).toBeLessThan(geometry.buttonLeft);
  expect(Math.abs(geometry.noteBottom - geometry.buttonBottom)).toBeLessThan(3);
  expect(geometry.overflow).toBeLessThanOrEqual(1);
  await expect(dialog.getByText("待确认", { exact: true })).toHaveCount(0);
  await expect(dialog.locator(".candidate-pane-footer-scroll")).toHaveCount(0);
  const count = api.count("POST /api/workbench/actions/confirm-link/preview");
  await dialog
    .getByRole("textbox", { name: "备注", exact: true })
    .fill("切换视图仍保留");
  await expect
    .poll(async () => (await dialog.boundingBox())!.x)
    .toBeGreaterThanOrEqual(0);
  await dialog.screenshot({
    path: info.outputPath("preview-desktop.png"),
    animations: "disabled",
  });
  await page.setViewportSize({ width: 700, height: 900 });
  await expect(before).toBeVisible();
  await expect(after).toBeHidden();
  await dialog.getByRole("button", { name: "操作后", exact: true }).click();
  await expect(after).toBeVisible();
  await expect(before).toBeHidden();
  await expect(
    dialog.getByRole("textbox", { name: "备注", exact: true }),
  ).toHaveValue("切换视图仍保留");
  await expect(
    dialog.getByRole("button", { name: "确认关联", exact: true }),
  ).toBeInViewport();
  await dialog.screenshot({ path: info.outputPath("preview-narrow.png") });
  expect(api.count("POST /api/workbench/actions/confirm-link/preview")).toBe(
    count,
  );
  expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(0);
  await dialog.getByRole("button", { name: "关闭关联预览" }).click();
  await expect(dialog).toHaveCount(0);
});

test("shows every member in a 2 OA and 15 bank preview with one scroll area and readable invoice fields", async ({
  page,
}, info) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "user" });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const data = await openConfirm(page);
  const template = data.after.groups[0];
  await page.getByRole("button", { name: "关闭关联预览" }).click();
  const oa = Array.from({ length: 2 }, (_, i) => ({
    ...template.oa_rows[0],
    id: `oa-${i}`,
    project_name: "曲靖卷烟厂动力车间设备安装及配套系统技术改造项目",
    project_name_display: "曲靖卷烟厂动力车间设备安装及配套系统技术改造项目",
    amount: "7500.00",
    expense_items: [],
  }));
  const bank = Array.from({ length: 15 }, (_, i) => ({
    ...template.bank_rows[0],
    id: `bank-${i}`,
    amount: "1000.00",
    debit_amount: "1000.00",
    bank_original_amount: "1000.00",
    bank_related_amount: "1000.00",
    counterparty_name: `设备供应商 ${i + 1}`,
  }));
  const invoice = [
    {
      ...template.invoice_rows[0],
      seller_name: "云南设备工程技术服务有限责任公司昆明分公司",
      buyer_name: "云南溯源科技有限公司",
      seller_tax_no: "915300007194052520",
      buyer_tax_no: "915300007194052521",
      total_with_tax: "15000.00",
      amount: "14150.94",
      tax_amount: "849.06",
      tax_rate: "6%",
    },
  ];
  const g = {
    ...template,
    group_id: "large",
    oa_rows: oa,
    bank_rows: bank,
    invoice_rows: invoice,
  };
  data.after.groups = [g];
  data.before.groups = [
    ...oa.map((r) => ({
      ...g,
      group_id: r.id,
      oa_rows: [r],
      bank_rows: [],
      invoice_rows: [],
    })),
    ...bank.map((r) => ({
      ...g,
      group_id: r.id,
      oa_rows: [],
      bank_rows: [r],
      invoice_rows: [],
    })),
    {
      ...g,
      group_id: "invoice",
      oa_rows: [],
      bank_rows: [],
      invoice_rows: invoice,
    },
  ];
  for (const side of ["before", "after"])
    data.amount_summary[side] = {
      oa_total: "15000.00",
      bank_total: "15000.00",
      invoice_total: "15000.00",
    };
  await page.route("**/api/workbench/actions/confirm-link/preview", (route) =>
    route.fulfill({ json: data }),
  );
  await page
    .getByTestId("zone-unpaired")
    .getByRole("button", { name: "确认关联", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "确认关联", exact: true });
  const after = dialog.getByTestId("relation-preview-after");
  await expect(after.getByRole("rowgroup")).toHaveCount(1);
  await expect(after.locator("[data-member-ids]")).toHaveCount(18);
  await expectPreviewPresentation(page);
  await expect(after.getByText("915300007194052520", { exact: true })).toHaveCount(0);
  await expect(after.getByText(/不含税/)).toHaveCount(0);
  const detailsButton = after.getByRole("button", { name: "查看发票详情" });
  await detailsButton.hover();
  const details = page.getByRole("dialog", { name: "发票详情", exact: true });
  await expect(details.getByText("915300007194052520", { exact: true })).toBeVisible();
  await details.hover();
  await expect(details.getByText("云南溯源科技有限公司", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(details).toHaveCount(0);
  await detailsButton.click();
  await expect(details).toBeVisible();
  await expect(details).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(details).toHaveCount(0);
  await dialog.getByRole("heading", { name: "确认关联", exact: true }).hover();
  await dialog.getByRole("textbox").focus();
  await expect(dialog.getByRole("textbox")).toBeFocused();
  await detailsButton.focus();
  await expect(details).toBeVisible();
  await expect(details).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(details).toHaveCount(0);
  await expect(detailsButton).toBeFocused();
  await dialog.getByRole("textbox").focus();
  await detailsButton.focus();
  await expect(details).toBeVisible();
  await expect(details).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(details).toHaveCount(0);
  await expect(detailsButton).toBeFocused();
  const scroller = dialog.locator(".relation-preview-compare-scroll");
  expect(
    await scroller.evaluate((el) => el.scrollWidth - el.clientWidth),
  ).toBeLessThanOrEqual(1);
  await dialog.screenshot({
    path: info.outputPath("preview-large.png"),
    animations: "disabled",
  });
  await scroller.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  await expect(
    after.getByText("设备供应商 15", { exact: true }),
  ).toBeInViewport();
  await expect(after.getByRole("heading", { name: "操作后" })).toBeInViewport();
  await expect(
    dialog.getByRole("button", { name: "确认关联", exact: true }),
  ).toBeInViewport();
  expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(0);
});

test("withdraw preview preserves five independent rows and split parent money", async ({ page }, info) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "user", workbenchInitialIncompleteRelation: true });
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/");
  const zone = page.getByTestId("zone-unpaired");
  await zone.getByTestId("candidate-group-unpaired-case:CASE-202603-101")
    .getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
  const response = page.waitForResponse(r => r.url().endsWith("/withdraw-link/preview"));
  await zone.getByRole("button", { name: "撤回关联", exact: true }).click();
  const data = await (await response).json();
  await page.getByRole("button", { name: "关闭关联预览" }).click();
  const template = data.before.groups[0];
  const oa = ["1000000.00", "1497.22"].map((amount, i) => ({
    ...template.oa_rows[0], id: `oa-${i}`, amount, expense_items: [],
    applicant: "刘际涛", project_name: "云南溯源科技", project_name_display: "云南溯源科技",
  }));
  const parts = [
    { id: "principal", amount: "1000000.00", category_code: "principal", category_label: "归还借款", category_path: ["外部往来款付款", "归还借款", "银行往来"] },
    { id: "interest", amount: "1497.22", category_code: "interest", category_label: "利息", category_path: ["费用", "利息"] },
  ];
  const bank = parts.map(part => ({ ...template.bank_rows[0], id: part.id, amount: part.amount,
    parent_row_id: "bank-parent", parent_amount: "1001497.22", is_split: true, bank_split_parts: parts,
    counterparty_name: "中国民生银行贷款户", payment_account_label: "民生银行 账户 9486",
  }));
  const invoice = { ...template.invoice_rows[0], id: "invoice", total_with_tax: "1497.22",
    seller_name: "中国民生银行股份有限公司昆明分行", buyer_name: "云南溯源科技有限公司",
    amount: "1412.47", tax_amount: "84.75", tax_rate: "6%" };
  const g = { ...template, group_id: "combined", oa_rows: oa, bank_rows: bank, invoice_rows: [invoice], display_subgroups: [] };
  data.before.groups = [g];
  data.after.groups = [
    { ...g, group_id: "interest-only", oa_rows: [], bank_rows: [bank[1]], invoice_rows: [] },
    ...oa.map(r => ({ ...g, group_id: r.id, oa_rows: [r], bank_rows: [], invoice_rows: [] })),
    { ...g, group_id: "invoice-only", oa_rows: [], bank_rows: [], invoice_rows: [invoice] },
    { ...g, group_id: "principal-only", oa_rows: [], bank_rows: [bank[0]], invoice_rows: [] },
  ];
  for (const side of ["before", "after"]) data.amount_summary[side] = {
    oa_total: "1001497.22", bank_total: "1001497.22", invoice_total: "1497.22",
  };
  await page.route("**/api/workbench/actions/withdraw-link/preview", route => route.fulfill({ json: data }));
  await zone.getByRole("button", { name: "撤回关联", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "撤回关联", exact: true });
  const before = dialog.getByTestId("relation-preview-before"), after = dialog.getByTestId("relation-preview-after");
  await expect(before.getByRole("rowgroup")).toHaveCount(1);
  await expect(after.getByRole("rowgroup")).toHaveCount(5);
  await expectPreviewPresentation(page);
  await expect(after.getByTestId("pane-bank")).toContainText("1 笔");
  const interest = after.getByTestId("candidate-group-interest-only");
  await expect(interest.getByText("1001497.22", { exact: true })).toBeVisible();
  await expect(interest.locator(".bank-account-tag")).toHaveText("民生9486");
  await expect(interest.getByRole("button", { name: /归还借款拆分金额/ })).toHaveCount(0);
  await expect(dialog.getByText(/本次关联|不含税/)).toHaveCount(0);
  await interest.getByRole("button", { name: "费用 / 利息拆分金额" }).hover();
  await expect(page.getByRole("tooltip")).toHaveText("¥1497.22");
  await dialog.getByRole("heading", { name: "撤回关联", exact: true }).hover();
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await expect(after.getByTestId("candidate-group-principal-only")).toBeInViewport();
  await dialog.screenshot({ path: info.outputPath("preview-withdraw-splits.png"), animations: "disabled" });
  expect(api.count("POST /api/workbench/actions/withdraw-link")).toBe(0);
});

test("centers two 8000 payments and one shared invoice within a single yellow relation", async ({ page }, info) => {
  await installDeterministicApiMocks(page, { sessionMode: "user" });
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/");
  const data = await openConfirm(page);
  await page.getByRole("button", { name: "关闭关联预览" }).click();
  const template = data.after.groups[0];
  const oa = ["杨丽萍", "樊祖芳"].map((applicant, i) => ({ ...template.oa_rows[0],
    id: `oa-${i}`, applicant, amount: "8000.00", expense_items: [],
    project_name: "大理卷烟厂动力车间中水处理系统升级改造项目",
    project_name_display: "大理卷烟厂动力车间中水处理系统升级改造项目" }));
  const bank = oa.map((_, i) => ({ ...template.bank_rows[0], id: `bank-${i}`,
    amount: "8000.00", debit_amount: "8000.00", bank_original_amount: "8000.00", bank_related_amount: "8000.00",
    payment_account_label: "平安银行 账户 0093", counterparty_name: "定州六联环保科技有限公司" }));
  const invoice = { ...template.invoice_rows[0], id: "shared-invoice", total_with_tax: "16000.00",
    seller_name: "定州六联环保科技有限公司", amount: "14159.29", tax_amount: "1840.71" };
  const g = { ...template, group_id: "shared", oa_rows: oa, bank_rows: bank, invoice_rows: [invoice],
    display_subgroups: oa.map((o, i) => ({ oa_row_ids: [o.id], bank_row_ids: [bank[i].id] })) };
  data.before.groups = [g];
  data.after.groups = [{ ...g, group_id: "remaining", oa_rows: [oa[1]], display_subgroups: [] },
    { ...g, group_id: "separate", oa_rows: [oa[0]], bank_rows: [], invoice_rows: [], display_subgroups: [] }];
  for (const side of ["before", "after"]) data.amount_summary[side] = { oa_total: "16000.00", bank_total: "16000.00", invoice_total: "16000.00" };
  await page.route("**/api/workbench/actions/confirm-link/preview", route => route.fulfill({ json: data }));
  await page.getByTestId("zone-unpaired").getByRole("button", { name: "确认关联", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "确认关联", exact: true });
  const before = dialog.getByTestId("relation-preview-before");
  await expectPreviewPresentation(page);
  await expect(before.locator('.relation-preview-payment')).toHaveText(['支8000.00', '支8000.00']);
  await expect(before.locator('.bank-account-tag')).toHaveText(['平安0093', '平安0093']);
  const shared = before.locator('[data-pane="invoice"]');
  const first = before.locator('[data-member-ids="oa-0"]');
  const last = before.locator('[data-member-ids="oa-1"]');
  const [i, a, b] = await Promise.all([shared.boundingBox(), first.boundingBox(), last.boundingBox()]);
  expect(Math.abs(i!.y - a!.y)).toBeLessThanOrEqual(1);
  expect(Math.abs(i!.y+i!.height-b!.y-b!.height)).toBeLessThanOrEqual(1);
  await expect(shared.locator('[data-member-ids]')).toHaveCount(1);
  await dialog.screenshot({ path: info.outputPath('preview-shared-8000.png'), animations:'disabled' });
});

test("merged invoice scopes keep 1711 on one row and 16000 across only two installments", async ({ page }, info) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "user" });
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/");
  const data = await openConfirm(page);
  await page.getByRole("button", { name: "关闭关联预览" }).click();
  const template = data.after.groups[0];
  const oa = ["1711.33", "8000.00", "8000.00"].map((amount, i) => ({ ...template.oa_rows[0],
    id: `oa-${i}`, applicant: `申请人${i}`, amount, expense_items: [], project_name: i ? "设备项目" : "ETC项目" }));
  const bank = oa.map((o, i) => ({ ...template.bank_rows[0], id: `bank-${i}`, source_oa_id: o.id,
    amount: o.amount, debit_amount: o.amount, bank_original_amount: o.amount, bank_related_amount: o.amount,
    payment_account_label: "平安银行 0093" }));
  const invoice = ["1711.33", "16000.00"].map((amount, i) => ({ ...template.invoice_rows[0],
    id: `invoice-${i}`, amount, total_with_tax: amount, source_oa_id: "", seller_name: i ? "设备供应商" : "ETC发票47张" }));
  const g = { ...template, group_id: "merged-invoices", oa_rows: oa, bank_rows: bank, invoice_rows: invoice,
    display_subgroups: oa.map((o, i) => ({ oa_row_ids: [o.id], bank_row_ids: [bank[i].id] })),
    invoice_display_scopes: [
      { oa_row_ids: [oa[0].id], bank_row_ids: [bank[0].id], invoice_row_ids: [invoice[0].id] },
      { oa_row_ids: [oa[1].id, oa[2].id], bank_row_ids: [bank[1].id, bank[2].id], invoice_row_ids: [invoice[1].id] },
    ],
  };
  data.after.groups = [g];
  data.before.groups = [
    { ...g, group_id: "etc-before", oa_rows: [oa[0]], bank_rows: [bank[0]], invoice_rows: [invoice[0]], display_subgroups: [], invoice_display_scopes: [] },
    { ...g, group_id: "equipment-before", oa_rows: oa.slice(1), bank_rows: bank.slice(1), invoice_rows: [invoice[1]], display_subgroups: g.display_subgroups.slice(1), invoice_display_scopes: [] },
  ];
  for (const side of ["before", "after"]) data.amount_summary[side] = { oa_total: "17711.33", bank_total: "17711.33", invoice_total: "17711.33" };
  await page.route("**/api/workbench/actions/confirm-link/preview", route => route.fulfill({ json: data }));
  await page.getByTestId("zone-unpaired").getByRole("button", { name: "确认关联", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "确认关联", exact: true });
  await expectPreviewPresentation(page);
  const after = dialog.getByTestId("relation-preview-after");
  const geometry = await after.evaluate(el => {
    const box = (id: string) => {
      const r = el.querySelector(`[data-member-ids="${id}"]`)!.parentElement!.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom };
    };
    return { first: box("oa-0"), bank: box("bank-0"), etc: box("invoice-0"),
      second: box("oa-1"), third: box("oa-2"), equipment: box("invoice-1"),
      header: getComputedStyle(el.querySelector('.relation-preview-columns')!).backgroundColor };
  });
  expect(geometry.etc).toEqual(geometry.first);
  expect(geometry.bank).toEqual(geometry.first);
  expect(geometry.equipment.top).toBe(geometry.second.top);
  expect(geometry.equipment.bottom).toBe(geometry.third.bottom);
  expect(geometry.etc.bottom).toBeLessThanOrEqual(geometry.equipment.top + 1);
  expect(geometry.header).toBe('rgb(15, 39, 66)');
  await expect(after.locator('[data-member-ids="invoice-1"]')).toHaveCount(1);
  await dialog.screenshot({ path: info.outputPath('preview-merged-invoice-scopes.png'), animations: 'disabled' });
  await page.getByRole("button", { name: "关闭关联预览" }).click();
  expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(0);
});
