import { expect, test, type Page } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.use({ reducedMotion: "reduce" });

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
  await expect(
    after.getByText("915300007194052520", { exact: true }),
  ).toBeVisible();
  await expect(after.getByText("不含税 14150.94 · 6%（849.06）")).toBeVisible();
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
