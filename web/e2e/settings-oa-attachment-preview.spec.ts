import { expect, test, type Page } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

const searchPath = "/api/workbench/settings/oa/manual-search";
const rowId = "oa-exp-historical-1922";
const emptySummary = {
  attachment_status: "unparsed", attachment_file_count: 2, importable_invoice_count: 0,
  unrecognized_attachment_count: 0, pending_attachment_count: 2,
  failed_attachment_count: 0, unsupported_attachment_count: 0,
};
const readySummary = {
  ...emptySummary, attachment_status: "ready", importable_invoice_count: 1,
  unrecognized_attachment_count: 1, pending_attachment_count: 0,
};

async function installPreviewScenario(page: Page, options: { imported?: boolean; partialFirst?: boolean; inProgressPayment?: boolean } = {}) {
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  const calls = { preview: 0, refresh: 0, polls: 0, exactReads: 0, imports: 0 };
  let summary = { ...emptySummary };
  let operationCount = 0;
  let operationPolls = 0;
  const row = () => ({
    row_id: rowId, oa_no: "1922", applicant: "胡珺", application_date: "2025-12-03",
    form_type: options.inProgressPayment ? "payment_request" : "expense_claim",
    form_type_label: options.inProgressPayment ? "支付申请" : "日常报销",
    status: options.inProgressPayment ? "in_progress" : "completed",
    status_label: options.inProgressPayment ? "进行中" : "已完成",
    project_name: "历史 OA 附件测试项目", reason: "油费及付款凭证", amount: "200.00", ...summary,
    import_status: options.imported ? "imported" : "not_imported", imported_at: null,
    can_import: !options.imported && !options.inProgressPayment, disabled_reason: "",
    items: [{ date: "2025-10-15", amount: "200.00", content: "油费", project_name: "历史 OA 附件测试项目", reason: "油费", ...summary }],
  });
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith("/oa/manual-imports") && request.method() === "POST") calls.imports += 1;
  });
  await page.route("**/api/workbench/settings/oa/manual-search**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === searchPath) {
      expect(request.method()).toBe("GET");
      if (url.searchParams.get("q") === rowId) {
        calls.exactReads += 1;
        expect(url.searchParams.get("page_size")).toBe("2");
      }
      return route.fulfill({ json: { rows: [row()], total: 1, page: 0, page_size: 20 } });
    }
    if (url.pathname === `${searchPath}/prepare-attachments` || url.pathname === `${searchPath}/refresh-attachments`) {
      expect(request.method()).toBe("POST");
      expect(request.postDataJSON()).toEqual({ row_ids: [rowId] });
      if (url.pathname.endsWith("/prepare-attachments")) calls.preview += 1;
      else calls.refresh += 1;
      operationCount += 1;
      operationPolls = 0;
      return route.fulfill({ status: 202, json: {
        event_id: `attachment-task-${operationCount}`, status: "queued", row_ids: [rowId], affected_scope_keys: options.imported ? ["2025-12"] : [],
      } });
    }
    if (url.pathname === `${searchPath}/refresh-attachments/attachment-task-${operationCount}`) {
      expect(request.method()).toBe("GET");
      calls.polls += 1;
      operationPolls += 1;
      if (operationPolls === 1) return route.fulfill({ json: {
        event_id: `attachment-task-${operationCount}`, status: "processing", row_ids: [rowId], affected_scope_keys: options.imported ? ["2025-12"] : [],
      } });
      const partial = options.partialFirst && operationCount === 1;
      summary = partial ? { ...readySummary, attachment_status: "partial", unrecognized_attachment_count: 0, failed_attachment_count: 1 } : { ...readySummary };
      return route.fulfill({ json: {
        event_id: `attachment-task-${operationCount}`, status: "done", row_ids: [rowId], affected_scope_keys: options.imported ? ["2025-12"] : [],
        result: {
          rows: [{ row_id: rowId, ...summary }], promotion_summary: {},
          errors: partial ? [{ row_id: rowId, code: "attachment_parse_failed", message: "一个附件解析失败，请重试" }] : [],
        },
      } });
    }
    throw new Error(`Unexpected OA attachment request: ${request.method()} ${url.pathname}`);
  });
  await page.goto("/settings");
  await page.getByRole("tab", { name: "OA导入设置", exact: true }).click();
  const region = page.getByRole("region", { name: "OA全量搜索导入" });
  await region.getByLabel("搜索关键字", { exact: true }).fill("胡");
  await region.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(region.getByText("待解析", { exact: true })).toBeVisible();
  return { calls, region };
}

test("unimported historical OA prepares, polls and reloads counts without creating formal facts", async ({ page }) => {
  const { calls, region } = await installPreviewScenario(page);
  await region.getByLabel("选择 OA 1922", { exact: true }).press("Space");
  await expect(region.getByLabel("选择 OA 1922", { exact: true })).toBeChecked();
  await expect(region.getByText("所选 OA 已识别发票合计 0 张（1 个OA附件解析未完成）", { exact: true })).toBeVisible();
  await region.getByRole("button", { name: "展开 OA 1922 明细" }).click();
  const refresh = region.getByRole("button", { name: "刷新 OA 1922 附件解析" });
  await refresh.click();
  await expect(region.getByRole("status")).toHaveText("正在重新解析 OA 附件");
  await expect(refresh).toBeDisabled();
  await expect(region.getByRole("button", { name: "导入已选OA项" })).toBeDisabled();
  await expect(region.getByRole("status")).toHaveText("附件预览解析完成，正式导入时处理发票入池");
  await expect(region.getByText("所选 OA 已识别发票合计 1 张", { exact: true })).toBeVisible();
  await expect(region.getByText("待解析", { exact: true })).toHaveCount(0);
  await expect(region.getByRole("grid", { name: "OA 1922 明细" })).toContainText("明细已识别发票");
  await expect(region.getByText("未导入", { exact: true })).toBeVisible();
  await expect(refresh).toBeEnabled();
  expect(calls).toEqual({ preview: 1, refresh: 0, polls: 2, exactReads: 1, imports: 0 });
});

test("partial parsing updates visible results and selected totals; retry resolves the failure", async ({ page }) => {
  const { calls, region } = await installPreviewScenario(page, { partialFirst: true });
  await region.getByLabel("选择 OA 1922", { exact: true }).press("Space");
  await expect(region.getByLabel("选择 OA 1922", { exact: true })).toBeChecked();
  const refresh = region.getByRole("button", { name: "刷新 OA 1922 附件解析" });
  await refresh.click();
  await expect(region.getByRole("alert")).toHaveText("一个附件解析失败，请重试");
  await expect(region.getByText("1（未完成）", { exact: true })).toBeVisible();
  await expect(region.getByText("失败 1 个", { exact: true })).toBeVisible();
  await expect(region.getByText("所选 OA 已识别发票合计 1 张（1 个OA附件解析未完成）", { exact: true })).toBeVisible();
  await refresh.click();
  await expect(region.getByRole("status")).toHaveText("附件预览解析完成，正式导入时处理发票入池");
  await expect(region.getByRole("alert")).toHaveCount(0);
  await expect(region.getByText("所选 OA 已识别发票合计 1 张", { exact: true })).toBeVisible();
  expect(calls).toEqual({ preview: 2, refresh: 0, polls: 4, exactReads: 2, imports: 0 });
});

test("already imported OA keeps the formal refresh endpoint", async ({ page }) => {
  const { calls, region } = await installPreviewScenario(page, { imported: true });
  await expect(region.getByLabel("选择 OA 1922", { exact: true })).toBeDisabled();
  await region.getByRole("button", { name: "刷新 OA 1922 附件解析" }).click();
  await expect(region.getByRole("status")).toHaveText("OA 附件刷新完成");
  expect(calls).toEqual({ preview: 0, refresh: 1, polls: 2, exactReads: 1, imports: 0 });
});

test("in-progress source payment can prepare attachments while formal import stays disabled", async ({ page }) => {
  const { calls, region } = await installPreviewScenario(page, { inProgressPayment: true });
  await expect(region.getByLabel("选择 OA 1922", { exact: true })).toBeDisabled();
  await region.getByRole("button", { name: "刷新 OA 1922 附件解析" }).click();
  await expect(region.getByRole("status")).toHaveText("附件预览解析完成，正式导入时处理发票入池");
  await expect(region.getByRole("button", { name: "导入已选OA项" })).toBeDisabled();
  expect(calls).toEqual({ preview: 1, refresh: 0, polls: 2, exactReads: 1, imports: 0 });
});
