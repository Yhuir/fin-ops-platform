import { execFileSync } from "node:child_process";
import { createServer, type Server } from "node:http";
import { cp, mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

// Explicit two-build test: run with e2e:release and an actual prior build directory.
let root: string;
let origin: string;
let server: Server;
let candidate: string;
let previous: string;
let dist: string;
let releases: string;

function publish(source: string) {
  execFileSync("python3", ["../scripts/frontend_assets.py", "publish", "--source", source,
    "--dist", dist, "--release-root", releases]);
}

test.beforeEach(async () => {
  const oldBuild = process.env.FIN_OPS_E2E_PREVIOUS_DIST;
  if (!oldBuild) throw new Error("FIN_OPS_E2E_PREVIOUS_DIST must name a real previous production build");
  root = await mkdtemp(join(tmpdir(), "finops-release-browser-"));
  releases = join(root, "releases");
  previous = join(releases, "A/src/web/dist");
  candidate = join(releases, "B/src/web/dist");
  dist = join(root, "live/dist");
  await cp(oldBuild, previous, { recursive: true });
  await cp(resolve("dist"), candidate, { recursive: true });
  await cp(previous, dist, { recursive: true });
  server = createServer(async (req, res) => {
    const path = new URL(req.url!, "http://local.test").pathname;
    const file = path.startsWith("/fin-ops/assets/") ? path.slice("/fin-ops/".length) : "index.html";
    try {
      const data = await readFile(join(dist, file));
      res.setHeader("Content-Type", file.endsWith(".js") ? "application/javascript" : file.endsWith(".css") ? "text/css" : "text/html");
      res.setHeader("Cache-Control", "no-store");
      res.end(data);
    } catch {
      res.writeHead(404); res.end();
    }
  });
  await new Promise<void>(done => server.listen(0, "127.0.0.1", done));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("missing test server address");
  origin = `http://127.0.0.1:${address.port}`;
});

test.afterEach(async () => {
  if (server) await new Promise<void>((done, reject) => { server.close(error => error ? reject(error) : done()); server.closeAllConnections(); });
  if (root) await rm(root, { recursive: true });
});

test("old and new tabs keep loading lazy routes across publish and rollback", async ({ browser }) => {
  const context = await browser.newContext();
  const oldTab = await context.newPage();
  const errors: string[] = [];
  const failures: string[] = [];
  const watch = async (page: typeof oldTab) => {
    await installDeterministicApiMocks(page, { sessionMode: "admin" });
    page.on("pageerror", e => errors.push(e.message));
    page.on("response", r => { if (r.status() >= 400) failures.push(r.url()); });
  };
  await watch(oldTab);
  await oldTab.goto(`${origin}/fin-ops/bank-details`);
  await expect(oldTab.getByRole("heading", { name: "银行明细", exact: true })).toBeVisible();
  publish(candidate);
  await oldTab.getByRole("link", { name: "进项发票使用情况", exact: true }).click();
  await expect(oldTab.getByRole("heading", { name: "进项发票使用情况", exact: true })).toBeVisible();
  const newTab = await context.newPage();
  await watch(newTab);
  await newTab.goto(`${origin}/fin-ops/bank-details`);
  await expect(newTab.getByRole("heading", { name: "银行明细", exact: true })).toBeVisible();
  publish(previous);
  await newTab.getByRole("link", { name: "进项发票使用情况", exact: true }).click();
  await expect(newTab.getByRole("heading", { name: "进项发票使用情况", exact: true })).toBeVisible();
  for (const page of [oldTab, newTab]) {
    await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
    expect(await page.locator("#root").evaluate(el => el.childElementCount)).toBeGreaterThan(0);
  }
  expect(errors).toEqual([]); expect(failures).toEqual([]);
  await context.close();
});

test("failed lazy chunk preserves navigation and manual reload recovers", async ({ page, browserDiagnostics }, testInfo) => {
  publish(candidate);
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto(`${origin}/fin-ops/bank-details`);
  await expect(page.getByRole("heading", { name: "银行明细", exact: true })).toBeVisible();
  const chunk = /\/assets\/InputInvoiceUsagePage-[^/]+\.js$/;
  const assertInjectedChunkFailure = () => {
    // Consume only the two diagnostics required by this deliberately injected 404.
    expect(browserDiagnostics).toEqual([
      { category: "console.error", detail: expect.stringMatching(/^TypeError: Failed to fetch dynamically imported module: http:\/\/127\.0\.0\.1:\d+\/fin-ops\/assets\/InputInvoiceUsagePage-[^/]+\.js$/) },
      { category: "console.error", detail: expect.stringMatching(/^fin-ops route failure \{build: [^,]+, route: \/input-invoice-usage, phase: render, kind: module_load_failed, asset: \/fin-ops\/assets\/InputInvoiceUsagePage-[^/]+\.js\}$/) },
    ]);
    browserDiagnostics.splice(0, 2);
  };
  await page.route(chunk, r => r.fulfill({ status: 404, contentType: "text/plain", body: "not found" }));
  await page.getByRole("link", { name: "进项发票使用情况", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("页面暂时无法显示");
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("route-failure-desktop.png") });
  assertInjectedChunkFailure();
  await page.setViewportSize({ width: 800, height: 900 });
  await expect(page.getByRole("button", { name: "重新加载页面" })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("route-failure-compact.png") });
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.getByRole("link", { name: "银行明细", exact: true }).click();
  await expect(page.getByRole("heading", { name: "银行明细", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "进项发票使用情况", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  assertInjectedChunkFailure();
  await page.unroute(chunk);
  await page.getByRole("button", { name: "重新加载页面" }).click();
  await expect(page.getByRole("heading", { name: "进项发票使用情况", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("retired output member DTO shows an error in an old tab and reload reads the new native-row contract", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'admin' });
  await page.goto(`${origin}/fin-ops/bank-details`);
  await expect(page.getByRole('heading', { name: '银行明细', exact: true })).toBeVisible();
  publish(candidate);
  await page.getByRole('link', { name: '销项发票收款情况', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('配对关系摘要不完整');
  await expect(page.getByRole('navigation', { name: '主导航' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: '销项发票收款情况', exact: true })).toBeVisible();
  await page.locator('.relation-count-button').filter({ hasText: /张/ }).first().click();
  await expect(page.locator('tr[data-relation-group]')).toHaveCount(2);
  await expect(page.getByRole('region', { name: '配对关系', exact: true })).toHaveCount(0);
});
