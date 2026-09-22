import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test("administrator inspects another owner's failure, ends handling once and sees refreshed state", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "admin", sessionUsername: "YNSYLP005" });
  let closed = false;
  let commands = 0;
  const job = { job_id: "30445642-a86f-4c66-aff2-e24c7a7edbf0", import_type: "file_import.confirm", created_by: "other-owner", status: "failed", stage: "commit", version: 4, affected_domains: ["imports_invoices"], updated_at: "2026-09-22T04:00:00Z", error_code: "review_required", disposition: null, allowed_actions: ["close"], continue_route: null };
  await page.route("**/api/imports/jobs**", async route => {
    const url = new URL(route.request().url());
    const pagination = { page: 1, page_size: 20, total: closed ? 0 : 1, has_more: false };
    if (url.pathname.endsWith("/dispose")) {
      expect(route.request().postDataJSON()).toEqual({ version: 4, action: "close", reason: "not_needed", note: "已核实，不再继续本次导入" });
      commands++; closed = true;
      return route.fulfill({ json: { status: "failed", version: 5, disposition: { action: "close", reason: "not_needed", note: "已核实，不再继续本次导入", actor_account: "YNSYLP005", actor_name: "管理员", handled_at: "2026-09-22" }, idempotent_replay: false } });
    }
    if (url.pathname.endsWith(job.job_id)) return route.fulfill({ json: { job, files: [], file_pagination: { ...pagination, total: 0 } } });
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
