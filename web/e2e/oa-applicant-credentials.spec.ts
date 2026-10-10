import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { expect, test, type Page } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import type { OaApplicantCredential } from "../src/features/inputInvoiceUsage/oaApplicantCredentials";

const endpoint = "/api/workbench/settings/oa-applicant-credentials";
const initial: OaApplicantCredential = { targetApplicantCode: "chen_xiuyun", targetApplicantName: "陈秀云", oaUsername: "chen_xiuyun", oaUserId: "u1", remark: "报销", credentialStatus: "configured", hasCredential: true, enabled: true, verifiedAt: "2026-10-08T08:00:00Z", version: 1 };
async function setup(page: Page, admin = true, legacy = false) {
  const api = await installDeterministicApiMocks(page, { sessionMode: admin ? "admin" : "user" });
  let records = [{ ...initial, ...(legacy ? { oaUserId: null, oaUsername: "CHEN_XIUYUN", verifiedAt: null } : {}) }];
  const writes: Record<string, unknown>[] = [];
  const requests: { method: string; path: string }[] = [];
  let rejectPassword = true;
  let directoryFailure = false;
  let deleteFailure = false;
  await page.route(`**${endpoint}**`, async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === `${endpoint}/users`) return route.fulfill(directoryFailure
      ? { status: 503, json: { message: "OA 目录暂时不可用" } }
      : { json: { users: [{ userId: "u1", displayName: "陈秀云", username: "chen_xiuyun", active: true }, { userId: "u2", displayName: "周洁莹", username: "YNSYLP006", active: true }, { userId: "u3", displayName: "停用人员", username: "DISABLED", active: false }, { userId: "u4", displayName: "陈秀云", username: "OTHER_ACCOUNT", active: true }] } });
    if (request.method() === "GET") return route.fulfill({ json: { credentials: records } });
    const body = request.postDataJSON(); writes.push(body); requests.push({ method: request.method(), path });
    if (request.method() === "DELETE") {
      expect(body).toEqual({ expectedVersion: records[0].version });
      if (deleteFailure) return route.fulfill({ status: 409, json: { message: "申请人记录已修改，请刷新" } });
      records = []; return route.fulfill({ json: { deleted: true, targetApplicantCode: initial.targetApplicantCode } });
    }
    expect(body).not.toHaveProperty("oaUsername"); expect(body).not.toHaveProperty("targetApplicantName");
    if (rejectPassword) return route.fulfill({ status: 400, json: { error: "invalid_password", message: "密码错误" } });
    const saved = { ...initial, oaUserId: body.oaUserId, targetApplicantName: body.oaUserId === "u2" ? "周洁莹" : "陈秀云", oaUsername: body.oaUserId === "u2" ? "YNSYLP006" : "chen_xiuyun", remark: body.remark, version: 2 };
    records = [saved]; return route.fulfill({ json: { credential: saved } });
  });
  await page.goto("/input-invoice-usage");
  await expect(page.getByRole("button", { name: "OA 草稿预填管理" })).toHaveCount(0);
  await page.getByRole("button", { name: "以发票反提 OA", exact: true }).click();
  await expect(page.getByRole("grid", { name: "反提 OA 候选发票清单" })).toBeVisible();
  return { api, writes, requests, acceptPassword: () => { rejectPassword = false; }, failDirectory: (fail: boolean) => { directoryFailure = fail; }, failDelete: (fail: boolean) => { deleteFailure = fail; } };
}

test("verified save is atomic in the UI, searches OA identities and preserves reverse selection", async ({ page }, testInfo) => {
  const state = await setup(page);
  await page.getByRole("button", { name: "选择本页", exact: true }).click();
  const checkedBefore = await page.getByRole("checkbox", { checked: true }).count();
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "OA 申请人凭据", exact: true });
  await expect(drawer.getByRole("button", { name: "新增申请人", exact: true })).toHaveCount(0);
  await expect(drawer.getByRole("button", { name: "取消编辑", exact: true })).toHaveCount(0);
  await expect(drawer.getByText("陈秀云（报销）", { exact: true })).toBeVisible();
  await expect(drawer.getByText(/不回显|重新校验|从 OA 读取/)).toHaveCount(0);
  const combo = drawer.getByRole("combobox", { name: "OA 申请人 / 登录账号" });
  await combo.fill("YNSYLP006");
  await page.getByRole("option", { name: "周洁莹 · YNSYLP006" }).click();
  await drawer.getByLabel("OA 登录密码", { exact: true }).fill("wrong-password");
  await drawer.getByLabel("备注（选填）").fill("差旅");
  await drawer.getByRole("button", { name: "保存凭据", exact: true }).click();
  await expect(drawer.getByRole("alert")).toContainText("密码错误");
  await expect(drawer.getByLabel("OA 登录密码", { exact: true })).toHaveValue("wrong-password");
  expect(state.writes[0]).toEqual({ oaUserId: "u2", password: "wrong-password", remark: "差旅" });
  expect(state.requests[0]).toEqual({ method: "POST", path: endpoint });
  state.acceptPassword();
  await drawer.getByLabel("OA 登录密码", { exact: true }).fill("correct-password");
  await drawer.getByRole("button", { name: "保存凭据", exact: true }).click();
  await expect(drawer).toBeHidden();
  expect(await page.getByRole("checkbox", { checked: true }).count()).toBe(checkedBefore);
  await expect(page.getByText("凭据已保存", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  await expect(drawer.getByLabel("OA 登录密码", { exact: true })).toHaveValue("");
  await expect(drawer.getByText("周洁莹（差旅）", { exact: true })).toBeVisible();
  await expectNoUnexpectedSuccessUiErrors(page);
  await page.screenshot({ path: testInfo.outputPath("oa-credentials-desktop.png"), fullPage: true });
});

test("editing binds identity, dirty Escape stays in child and deletion removes the whole row", async ({ page }) => {
  await setup(page);
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "OA 申请人凭据", exact: true });
  await drawer.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(drawer.getByLabel("OA 申请人 / 登录账号", { exact: true })).toHaveAttribute("readonly", "");
  await drawer.getByLabel("备注（选填）").fill("更改");
  await page.keyboard.press("Escape");
  const discard = page.getByRole("alertdialog");
  await expect(discard.getByText("放弃未保存的修改？")).toBeVisible();
  await discard.getByRole("button", { name: "取消", exact: true }).click();
  await expect(drawer.getByLabel("备注（选填）")).toHaveValue("更改");
  await drawer.getByRole("button", { name: "删除陈秀云（报销）", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "删除", exact: true }).click();
  await expect(drawer.getByText("暂无申请人")).toBeVisible();
  await expect(drawer.getByLabel("备注（选填）")).toHaveValue("");
  await drawer.getByRole("button", { name: "返回反提", exact: true }).click();
  await expect(drawer).toBeHidden();
  await expect(page.getByRole("dialog", { name: "以发票反提 OA", exact: true })).toBeVisible();
  await expect(page.getByLabel("反提 OA 申请人", { exact: true })).not.toContainText("陈秀云");
  await expect(page.getByRole("button", { name: "创建 OA 草稿", exact: true })).toBeDisabled();
});

test("directory errors are retryable; narrow form remains usable and stopped accounts cannot be selected", async ({ page }, testInfo) => {
  const state = await setup(page);
  state.failDirectory(true);
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "OA 申请人凭据", exact: true });
  await expect(drawer.getByRole("alert")).toContainText("OA 目录暂时不可用");
  await expect(drawer.getByRole("button", { name: "保存凭据" })).toBeDisabled();
  state.failDirectory(false);
  await drawer.getByRole("button", { name: "重新加载" }).click();
  await expect(drawer.getByText("陈秀云（报销）", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  const combo = drawer.getByRole("combobox");
  await combo.fill("DISABLED");
  await expect(page.getByRole("option", { name: /停用人员/ })).toHaveAttribute("aria-disabled", "true");
  await page.keyboard.press("Escape");
  await expect(drawer.getByRole("button", { name: "保存凭据" })).toBeInViewport();
  await expect(drawer.getByRole("button", { name: "返回反提" })).toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath("oa-credentials-mobile.png"), fullPage: true });
});

test("ordinary users cannot open credentials and prefill stays within reverse workflow", async ({ page }) => {
  const state = await setup(page, false);
  await expect(page.getByRole("button", { name: "OA 申请人凭据", exact: true })).toHaveCount(0);
  expect(state.api.calls.some(call => call.includes("oa-applicant-credentials"))).toBe(false);
  await page.getByRole("button", { name: "OA 草稿预填管理" }).click();
  const prefill = page.getByRole("dialog", { name: "OA 草稿预填管理" });
  await expect(prefill.getByLabel("开户行")).toBeDisabled();
  await expect(prefill.getByRole("button", { name: "保存", exact: true })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(prefill).toBeHidden();
  await expect(page.getByRole("dialog", { name: "以发票反提 OA", exact: true })).toBeVisible();
});

test("directory failure leaves verified remark editing available without password or extra reads", async ({ page }, info) => {
  const state = await setup(page);
  state.failDirectory(true);
  let reads = 0;
  page.on("request", request => { if (request.method() === "GET" && request.url().includes(endpoint)) reads += 1; });
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "OA 申请人凭据", exact: true });
  await expect(drawer.getByRole("alert")).toContainText("OA 目录暂时不可用");
  await expect(drawer.getByText("陈秀云（报销）", { exact: true })).toBeVisible();
  await drawer.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(drawer.getByLabel("OA 申请人 / 登录账号", { exact: true })).toHaveValue("陈秀云 · chen_xiuyun");
  await expect(drawer.getByLabel("备注（选填）")).toHaveValue("报销");
  await expect(drawer.getByText("密码已保存，留空保留原密码。")).toBeVisible();
  await expect(drawer.getByRole("button", { name: "保存修改", exact: true })).toBeDisabled();
  await drawer.getByLabel("备注（选填）").fill("新备注");
  await expect(drawer.getByRole("button", { name: "保存修改", exact: true })).toBeEnabled();
  expect(reads).toBe(2);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(drawer.getByRole("button", { name: "保存修改", exact: true })).toBeInViewport();
  await expect(drawer.getByRole("button", { name: "取消编辑", exact: true })).toBeInViewport();
  await page.screenshot({ path: info.outputPath("oa-credentials-edit-mobile.png"), fullPage: true });
  state.acceptPassword();
  await drawer.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(drawer).toBeHidden();
  expect(state.writes).toEqual([{ oaUserId: "u1", remark: "新备注", expectedVersion: 1 }]);
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  await drawer.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(drawer.getByLabel("备注（选填）")).toHaveValue("新备注");
  await expect(drawer.getByLabel("OA 登录密码", { exact: true })).toHaveValue("");
  await expectNoUnexpectedSuccessUiErrors(page);
});

test("saved credentials become editable before the OA directory response arrives", async ({ page }) => {
  await setup(page);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**${endpoint}/users`, async route => {
    await pending;
    await route.fulfill({ json: { users: [] } });
  });
  try {
    await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
    const drawer = page.getByRole("dialog", { name: "OA 申请人凭据", exact: true });
    await drawer.getByRole("button", { name: "编辑", exact: true }).click();
    await expect(drawer.getByLabel("OA 申请人 / 登录账号", { exact: true })).toHaveValue("陈秀云 · chen_xiuyun");
    await drawer.getByLabel("备注（选填）").fill("不等待目录");
    await expect(drawer.getByRole("button", { name: "保存修改", exact: true })).toBeEnabled();
  } finally { release(); }
});

test("unmatched historical identity is displayed but cannot be guessed or submitted", async ({ page }) => {
  const state = await setup(page, true, true);
  await page.route(`**${endpoint}/users`, route => route.fulfill({ json: { users: [] } }));
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "OA 申请人凭据", exact: true });
  await drawer.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(drawer.getByLabel("OA 申请人 / 登录账号", { exact: true })).toHaveValue("陈秀云 · CHEN_XIUYUN");
  await expect(drawer.getByRole("alert")).toContainText("无法唯一匹配");
  await expect(drawer.getByRole("button", { name: "验证并保存", exact: true })).toBeDisabled();
  await drawer.getByRole("button", { name: "取消编辑", exact: true }).click();
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  expect(state.writes).toEqual([]);
});

test("management remains reachable with an unavailable preview and prefill dirty close is contained", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  await page.route("**/api/input-invoice-usage/oa-reverse/preview", route => route.fulfill({ status: 503, json: { message: "预览暂时不可用" } }));
  await page.goto("/input-invoice-usage");
  await page.getByRole("button", { name: "以发票反提 OA", exact: true }).click();
  await expect(page.getByRole("button", { name: "OA 申请人凭据", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  const credentials = page.getByRole("dialog", { name: "OA 申请人凭据", exact: true });
  await expect(credentials.getByText("陈秀云", { exact: true })).toBeVisible();
  await credentials.getByRole("button", { name: "返回反提", exact: true }).click();
  await expect(page.getByRole("button", { name: "OA 申请人凭据", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "OA 草稿预填管理", exact: true }).click();
  const prefill = page.getByRole("dialog", { name: "OA 草稿预填管理" });
  await prefill.getByLabel("开户行", { exact: true }).fill("新的银行");
  await page.keyboard.press("Escape");
  await page.getByRole("alertdialog").getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await expect(prefill.getByLabel("开户行", { exact: true })).toHaveValue("新的银行");
  await page.keyboard.press("Escape");
  await page.getByRole("alertdialog").getByRole("button", { name: "放弃修改", exact: true }).click();
  await expect(prefill).toBeHidden();
  await expect(page.getByRole("dialog", { name: "以发票反提 OA", exact: true })).toBeVisible();
});

test("version conflict reload discards only after confirmation and retries with the current version", async ({ page }) => {
  const state = await setup(page);
  let reads = 0;
  await page.route(`**${endpoint}`, route => {
    reads += 1;
    return route.fulfill({ json: { credentials: [{ ...initial, version: reads === 1 ? 1 : 2 }] } });
  });
  const versions: number[] = [];
  await page.route(`**${endpoint}/chen_xiuyun`, route => {
    const body = route.request().postDataJSON(); versions.push(body.expectedVersion);
    return route.fulfill(body.expectedVersion === 1
      ? { status: 409, json: { message: "凭据已被修改，请重新加载" } }
      : { json: { credential: { ...initial, version: 3 } } });
  });
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "OA 申请人凭据", exact: true });
  await drawer.getByRole("button", { name: "编辑", exact: true }).click();
  await drawer.getByLabel("OA 登录密码", { exact: true }).fill("new-password");
  await drawer.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(drawer.getByRole("alert")).toContainText("凭据已被修改");
  await drawer.getByRole("button", { name: "重新加载", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await expect(drawer.getByLabel("OA 登录密码", { exact: true })).toHaveValue("new-password");
  expect(reads).toBe(1);
  state.failDirectory(true);
  await drawer.getByRole("button", { name: "重新加载", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "放弃修改", exact: true }).click();
  await expect(drawer.getByRole("alert")).toContainText("OA 目录暂时不可用");
  await expect(drawer.getByRole("button", { name: "保存凭据", exact: true })).toBeDisabled();
  state.failDirectory(false);
  await drawer.getByRole("button", { name: "重新加载", exact: true }).click();
  await expect(drawer.getByRole("alert")).toHaveCount(0);
  await expect(drawer.getByLabel("OA 登录密码", { exact: true })).toHaveValue("");
  await drawer.getByRole("button", { name: "编辑", exact: true }).click();
  await drawer.getByLabel("OA 登录密码", { exact: true }).fill("new-password");
  await drawer.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(drawer).toBeHidden();
  expect(versions).toEqual([1, 2]);
});

test("cancel editing restores direct creation, clears save errors and never writes", async ({ page }, info) => {
  const state = await setup(page);
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "OA 申请人凭据", exact: true });
  const combo = drawer.getByRole("combobox");
  await combo.fill("chen_xiuyun");
  await expect(page.getByRole("option", { name: "陈秀云 · chen_xiuyun", exact: true })).toHaveAttribute("aria-disabled", "true");
  await combo.fill("OTHER_ACCOUNT");
  await expect(page.getByRole("option", { name: "陈秀云 · OTHER_ACCOUNT", exact: true })).not.toHaveAttribute("aria-disabled", "true");
  await page.keyboard.press("Escape");
  await drawer.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(drawer.getByLabel("OA 申请人 / 登录账号", { exact: true })).toHaveValue("陈秀云 · chen_xiuyun");
  await drawer.getByRole("button", { name: "取消编辑", exact: true }).click();
  await expect(combo).toBeEnabled();
  await expect(combo).toHaveValue("");
  await expect(drawer.getByLabel("备注（选填）")).toHaveValue("");
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  expect(state.writes).toEqual([]);

  await drawer.getByRole("button", { name: "编辑", exact: true }).click();
  await drawer.getByLabel("OA 登录密码", { exact: true }).fill("wrong-password");
  await drawer.getByLabel("备注（选填）").fill("未保存");
  await drawer.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(drawer.getByRole("alert")).toContainText("密码错误");
  expect(state.requests).toEqual([{ method: "PUT", path: `${endpoint}/${initial.targetApplicantCode}` }]);
  expect(state.writes[0]).toEqual({ oaUserId: "u1", password: "wrong-password", remark: "未保存", expectedVersion: 1 });
  await drawer.getByRole("button", { name: "取消编辑", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "取消", exact: true }).click();
  await expect(drawer.getByLabel("OA 登录密码", { exact: true })).toHaveValue("wrong-password");
  await expect(drawer.getByRole("alert")).toContainText("密码错误");
  await drawer.getByRole("button", { name: "取消编辑", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "放弃修改", exact: true }).click();
  await expect(combo).toHaveValue("");
  await expect(drawer.getByLabel("OA 登录密码", { exact: true })).toHaveValue("");
  await expect(drawer.getByLabel("备注（选填）")).toHaveValue("");
  await expect(drawer.getByRole("alert")).toHaveCount(0);
  await expect(drawer.getByRole("button", { name: "取消编辑", exact: true })).toHaveCount(0);
  expect(state.writes).toHaveLength(1);
  await expectNoUnexpectedSuccessUiErrors(page);
  await page.screenshot({ path: info.outputPath("oa-credentials-direct-create.png"), fullPage: true });
});

test("legacy editing autofills the saved account and verifies with the stored password", async ({ page }, info) => {
  const state = await setup(page, true, true);
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "OA 申请人凭据", exact: true });
  const combo = drawer.getByRole("combobox");
  await combo.fill("chen_xiuyun");
  await expect(page.getByRole("option", { name: "陈秀云 · chen_xiuyun", exact: true })).toHaveAttribute("aria-disabled", "true");
  await page.keyboard.press("Escape");
  // Search text is not a selected account and does not make the draft dirty.
  await drawer.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(drawer.getByLabel("OA 申请人 / 登录账号", { exact: true })).toHaveValue("陈秀云 · CHEN_XIUYUN");
  await expect(drawer.getByText("密码已保存，留空使用原密码验证。")).toBeVisible();
  await expect(drawer.getByLabel("OA 登录密码", { exact: true })).toHaveValue("");
  await expect(drawer.getByRole("button", { name: "验证并保存", exact: true })).toBeEnabled();
  await page.screenshot({ path: info.outputPath("oa-credentials-legacy-edit.png"), fullPage: true });
  // 200% browser zoom halves the logical viewport; CSS zoom on the root does not emulate it.
  await page.setViewportSize({ width: 640, height: 360 });
  await expect(drawer.getByRole("button", { name: "验证并保存", exact: true })).toBeInViewport();
  await drawer.getByLabel("OA 登录密码", { exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath("oa-credentials-legacy-edit-200.png"), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 720 });
  await drawer.getByRole("button", { name: "取消编辑", exact: true }).click();
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await drawer.getByRole("button", { name: "编辑", exact: true }).click();
  state.acceptPassword();
  await drawer.getByRole("button", { name: "验证并保存", exact: true }).click();
  await expect(drawer).toBeHidden();
  expect(state.requests).toEqual([{ method: "PUT", path: `${endpoint}/${initial.targetApplicantCode}` }]);
  expect(state.writes[0]).toEqual({ oaUserId: "u1", remark: "报销", expectedVersion: 1 });
  await expectNoUnexpectedSuccessUiErrors(page);
});

test("failed deletion retains the edit; successful deletion resets it and releases the account", async ({ page }) => {
  const state = await setup(page);
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "OA 申请人凭据", exact: true });
  await drawer.getByRole("button", { name: "编辑", exact: true }).click();
  await drawer.getByLabel("OA 登录密码", { exact: true }).fill("draft-password");
  await drawer.getByLabel("备注（选填）").fill("未保存备注");
  state.failDelete(true);
  await drawer.getByRole("button", { name: "删除陈秀云（报销）", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "删除", exact: true }).click();
  await expect(drawer.getByRole("alert")).toContainText("申请人记录已修改");
  await expect(drawer.getByLabel("OA 申请人 / 登录账号", { exact: true })).toHaveAttribute("readonly", "");
  await expect(drawer.getByLabel("OA 登录密码", { exact: true })).toHaveValue("draft-password");
  await expect(drawer.getByLabel("备注（选填）")).toHaveValue("未保存备注");
  state.failDelete(false);
  await drawer.getByRole("button", { name: "删除陈秀云（报销）", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "删除", exact: true }).click();
  await expect(drawer.getByText("暂无申请人")).toBeVisible();
  await expect(drawer.getByLabel("OA 登录密码", { exact: true })).toHaveValue("");
  await expect(drawer.getByLabel("备注（选填）")).toHaveValue("");
  await expect(drawer.getByRole("button", { name: "取消编辑", exact: true })).toHaveCount(0);
  await expect(drawer.getByRole("alert")).toHaveCount(0);
  await drawer.getByRole("combobox").fill("chen_xiuyun");
  await expect(page.getByRole("option", { name: "陈秀云 · chen_xiuyun", exact: true })).not.toHaveAttribute("aria-disabled", "true");
  await page.keyboard.press("Escape");
  expect(state.requests.map(item => item.method)).toEqual(["DELETE", "DELETE"]);
  await expectNoUnexpectedSuccessUiErrors(page);
});

test("a pending save keeps editing controls locked and preserves the draft on failure", async ({ page }) => {
  await setup(page);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**${endpoint}/${initial.targetApplicantCode}`, async route => {
    await pending;
    await route.fulfill({ status: 400, json: { error: "invalid_password", message: "密码错误" } });
  });
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "OA 申请人凭据", exact: true });
  await drawer.getByRole("button", { name: "编辑", exact: true }).click();
  await drawer.getByLabel("OA 登录密码", { exact: true }).fill("wrong-password");
  try {
    await drawer.getByRole("button", { name: "保存修改", exact: true }).click();
    await expect(drawer.getByRole("button", { name: "取消编辑", exact: true })).toBeDisabled();
    await expect(drawer.getByRole("button", { name: "返回反提", exact: true })).toBeDisabled();
    await expect(drawer.getByRole("button", { name: "编辑", exact: true })).toBeDisabled();
    await expect(drawer.getByLabel("OA 登录密码", { exact: true })).toBeDisabled();
    await page.keyboard.press("Escape");
    await expect(drawer).toBeVisible();
    await expect(page.getByRole("alertdialog")).toHaveCount(0);
  } finally { release(); }
  await expect(drawer.getByRole("alert")).toContainText("密码错误");
  await expect(drawer.getByLabel("OA 登录密码", { exact: true })).toHaveValue("wrong-password");
  await expect(drawer.getByRole("button", { name: "取消编辑", exact: true })).toBeEnabled();
});
