import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { expect, test } from "./fixtures/strictTest";

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === "1";
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
const credentialsApi = "/fin-ops-api/api/workbench/settings/oa-applicant-credentials";
test.use({ screenshot: "off", trace: "off", video: "off" });

test("production applicant management and prefill are reachable inside reverse without writes", async ({ page, baseURL }, info) => {
  test.skip(!enabled || !token, "Requires production read-only verification and local token.");
  test.setTimeout(120_000);
  await page.context().addCookies([{ name: "Admin-Token", value: token!, domain: new URL(baseURL!).hostname, path: "/", secure: true, sameSite: "Lax" }]);
  const writes: string[] = [];
  const samples: { operation: string; durationMs: number }[] = [];
  const credentialReads: string[] = [];
  await page.route("**/*", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method()) && !(request.method() === "POST" && path === "/fin-ops-api/api/input-invoice-usage/oa-reverse/preview")) {
      writes.push(`${request.method()} ${path}`);
      return route.abort("blockedbyclient");
    }
    if (path.startsWith(credentialsApi)) credentialReads.push(path);
    return route.continue();
  });
  await page.goto("/fin-ops/input-invoice-usage");
  await expect(page.locator(".invoice-usage-classification")).toHaveAttribute("aria-busy", "false");
  expect(credentialReads).toEqual([]);
  await expect(page.getByRole("button", { name: "OA 草稿预填管理" })).toHaveCount(0);
  await page.getByRole("button", { name: "以发票反提 OA", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "以发票反提 OA", exact: true })).toBeVisible();
  const list = page.waitForResponse(response => new URL(response.url()).pathname === credentialsApi);
  const users = page.waitForResponse(response => new URL(response.url()).pathname === `${credentialsApi}/users`);
  const start = performance.now();
  await page.getByRole("button", { name: "OA 申请人凭据", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "OA 申请人凭据", exact: true });
  const credentialResponse = await list;
  expect(credentialResponse.status()).toBe(200);
  const credentialPayload = await credentialResponse.json();
  expect(credentialPayload.credentials.every((row: Record<string, unknown>) => Object.keys(row).every(key => !/password|secret|token/i.test(key)))).toBe(true);
  expect((await users).status()).toBe(200);
  await expect(drawer.getByRole("combobox", { name: "OA 申请人 / 登录账号" })).toBeEnabled();
  await expect(drawer.getByLabel("OA 登录密码", { exact: true })).toHaveValue("");
  await expect(drawer.getByRole("button", { name: "保存凭据", exact: true })).toBeDisabled();
  await expect(drawer.getByText(/不回显|重新校验|从 OA 读取/)).toHaveCount(0);
  samples.push({ operation: "credentials-open-to-interactive", durationMs: performance.now() - start });
  expect([...credentialReads].sort()).toEqual([credentialsApi, `${credentialsApi}/users`].sort());
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(page.getByRole("button", { name: "OA 申请人凭据", exact: true })).toBeFocused();
  const prefillResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/fin-ops-api/api/workbench/settings/oa-draft-prefill/input-invoice-usage");
  const prefillStart = performance.now();
  await page.getByRole("button", { name: "OA 草稿预填管理", exact: true }).click();
  expect((await prefillResponse).status()).toBe(200);
  const prefill = page.getByRole("dialog", { name: "OA 草稿预填管理", exact: true });
  await expect(prefill.getByLabel("开户行", { exact: true })).toBeVisible();
  samples.push({ operation: "prefill-open-to-interactive", durationMs: performance.now() - prefillStart });
  await page.keyboard.press("Escape");
  await expect(prefill).toHaveCount(0);
  await expect(page.getByRole("dialog", { name: "以发票反提 OA", exact: true })).toBeVisible();
  await expectNoUnexpectedSuccessUiErrors(page);
  expect(writes).toEqual([]);
  await info.attach("applicant-management-readonly-performance", { body: JSON.stringify({ samples, credentialReads: credentialReads.length, writes: writes.length }), contentType: "application/json" });
});
