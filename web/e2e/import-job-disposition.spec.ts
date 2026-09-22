import { expect, test } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test("administrator inspects another owner's failure, ends handling once and sees refreshed state", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "admin", sessionUsername: "YNSYLP005" });
  let closed = false;
  let commands = 0;
  const job = { job_id: "30445642-a86f-4c66-aff2-e24c7a7edbf0", import_type: "file_import.confirm", created_by: "other-owner", status: "failed", stage: "commit", version: 4, affected_domains: ["imports_invoices"], updated_at: "2026-09-22T04:00:00Z", error_code: "review_required", disposition: null, allowed_actions: ["close"] };
  await page.route("**/api/imports/jobs**", async route => {
    const url = new URL(route.request().url());
    const pagination = { page: 1, page_size: 20, total: closed ? 0 : 1, has_more: false };
    if (url.pathname.endsWith("/dispose")) {
      expect(route.request().postDataJSON()).toEqual({ version: 4, action: "close", reason: "not_needed", note: "已核实，不再继续本次导入" });
      commands++; closed = true;
      return route.fulfill({ json: { status: "failed", version: 5, disposition: { action: "close", reason: "not_needed", note: "已核实，不再继续本次导入", actor_account: "YNSYLP005", actor_name: "管理员", handled_at: "2026-09-22" }, idempotent_replay: false } });
    }
    if (url.pathname.endsWith(job.job_id)) return route.fulfill({ json: { job: closed ? { ...job, version: 5, disposition: { action: "close", reason: "not_needed", note: "已核实，不再继续本次导入", actor_account: "YNSYLP005", actor_name: "管理员", handled_at: "2026-09-22" }, allowed_actions: [] } : job, files: [], file_pagination: { ...pagination, total: 0 } } });
    return route.fulfill({ json: { rows: closed ? [] : [job], pagination } });
  });
  await page.goto("/operations/app-health");
  await expect(page.getByRole("heading", { name: "导入任务诊断" })).toBeVisible();
  await page.getByRole("button", { name: "查看详情", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "导入任务详情" });
  await expect(drawer).toContainText("other-owner");
  await expect(drawer).toContainText("当时所选文件需要复核");
  await expect(drawer.getByRole("link", { name: "继续查看导入预览" })).toHaveCount(0);
  await drawer.getByLabel("补充说明（选填）").fill("已核实，不再继续本次导入");
  await drawer.getByRole("button", { name: "结束处理并关闭提醒" }).click();
  await expect(drawer).toContainText("本次任务已结束处理；原执行结果和历史记录保留。");
  await expect(drawer.getByRole("button", { name: "结束处理并关闭提醒" })).toHaveCount(0);
  await expect(page.getByText("无待处理导入任务", { exact: true })).toBeVisible();
  expect(commands).toBe(1);
});

test("platform user handles another creator's preview from the global shared drawer without import-page access", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user", sessionUsername: "E2EUSER001", allowedPageKeys: ["cost-statistics"] });
  const id = "30445642-a86f-4c66-aff2-e24c7a7edbf0";
  const job = { job_id: id, import_type: "file_import.confirm", created_by: "another-creator", status: "awaiting_confirmation", stage: "prepare", version: 2, affected_domains: ["imports_invoices"], updated_at: "2026-09-22T04:00:00Z", error_code: null, disposition: null, allowed_actions: [] };
  await page.route("**/api/imports/jobs**", route => route.fulfill({ json: new URL(route.request().url()).pathname.endsWith(id)
    ? { job, files: [], file_pagination: { page: 1, page_size: 20, total: 0, has_more: false } }
    : { rows: [job], pagination: { page: 1, page_size: 20, total: 1, has_more: false } } }));
  await page.route("**/api/background-jobs/import*", route => route.fulfill({ json: { job: { job_id: `import:${id}`, type: "file_import", status: "awaiting_confirmation", phase: "prepare", version: 2, source: { session_id: "import_session_e2e_invoice", route: "/imports/invoices" } } } }));
  await page.goto("/cost-statistics");
  await page.locator(".app-sidebar-brand-mark").click();
  await page.getByRole("button", { name: "查看待处理任务", exact: true }).click();
  await page.getByRole("button", { name: "查看详情", exact: true }).click();
  await page.getByRole("button", { name: "查看发票导入预览" }).click();
  const preview = page.getByRole("dialog", { name: "处理导入任务", exact: true });
  await expect(preview.getByText("已恢复指定导入任务，请核对预览。")).toBeVisible();
  await expect(preview.getByRole("button", { name: "确认导入", exact: true })).toBeEnabled();
  expect(new URL(page.url()).pathname).toBe("/cost-statistics");
  const payload = await page.evaluate(async () => (await fetch("/imports/files/sessions/import_session_e2e_invoice")).json());
  let confirmed = 0;
  await page.route("**/imports/files/confirm", async route => {
    expect(route.request().postDataJSON().session_id).toBe("import_session_e2e_invoice");
    confirmed++;
    await route.fulfill({ json: { ...payload, job: { ...payload.job, job_id: `import:${id}`, status: "queued", phase: "commit" } } });
  });
  await preview.getByRole("button", { name: "确认导入", exact: true }).click();
  await expect(preview).toContainText("已开始后台导入");
  expect(confirmed).toBe(1);
  await expectNoUnexpectedSuccessUiErrors(page, { allowText: /历史失败原因|未记录失败原因。/g });
});
