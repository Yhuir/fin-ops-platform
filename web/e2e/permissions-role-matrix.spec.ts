import type { Locator } from "@playwright/test";

import { expect, setCheckbox, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

async function expectAccountRowsToRemainSeparated(accountList: Locator) {
  const geometry = await accountList.locator(".settings-access-account-row").evaluateAll((rows) => rows.map((row) => {
    const select = row.querySelector<HTMLElement>(".settings-access-account-select");
    if (!select) throw new Error("Account row is missing its selection control.");
    const rowRect = row.getBoundingClientRect();
    const selectRect = select.getBoundingClientRect();
    const contentRects = Array.from(select.children, (child) => child.getBoundingClientRect());
    return {
      rowTop: rowRect.top,
      rowBottom: rowRect.bottom,
      selectTop: selectRect.top,
      selectBottom: selectRect.bottom,
      contentTop: Math.min(...contentRects.map((rect) => rect.top)),
      contentBottom: Math.max(...contentRects.map((rect) => rect.bottom)),
      clientHeight: select.clientHeight,
      scrollHeight: select.scrollHeight,
    };
  }));

  expect(geometry.length).toBeGreaterThan(1);
  geometry.forEach((row, index) => {
    expect(row.selectTop).toBeGreaterThanOrEqual(row.rowTop - 0.5);
    expect(row.selectBottom).toBeLessThanOrEqual(row.rowBottom + 0.5);
    expect(row.contentTop).toBeGreaterThanOrEqual(row.selectTop - 0.5);
    expect(row.contentBottom).toBeLessThanOrEqual(row.selectBottom + 0.5);
    expect(row.scrollHeight).toBeLessThanOrEqual(row.clientHeight + 1);
    if (index > 0) {
      expect(geometry[index - 1].rowBottom).toBeLessThanOrEqual(row.rowTop + 0.5);
      expect(geometry[index - 1].contentBottom).toBeLessThanOrEqual(row.rowTop + 0.5);
    }
  });
}

test.describe("page access browser matrix", () => {
  test("an account with no assigned page stops at the shell boundary", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "forbidden",
      sessionUsername: "YNSYLP006",
    });

    await page.goto("/fin-ops/");
    await expect(page.getByRole("heading", { name: "无权访问财务运营平台" })).toBeVisible();
    await expect(page.getByTestId("bank-details-page")).toHaveCount(0);
    expect(api.count("GET /api/session/me")).toBeGreaterThan(0);
    expect(api.calls.some((call) => call.includes("/api/workbench") || call.includes("/api/bank-details"))).toBe(false);
  });

  test("a user sees only assigned pages and is redirected to the first permitted page", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
      allowedPageKeys: ["bank-details"],
    });

    await page.goto("/");
    await expect(page).toHaveURL(/\/bank-details$/);
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await expect(page.getByRole("link", { name: "银行明细" })).toBeVisible();
    await expect(page.getByRole("link", { name: "关联台" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "设置" })).toHaveCount(0);

    await page.goto("/settings");
    await expect(page).toHaveURL(/\/bank-details$/);
    expect(api.count("GET /api/workbench/settings/access-control")).toBe(0);
  });

  test("an assigned settings user can use normal settings but cannot manage accounts", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
      allowedPageKeys: ["settings"],
      settingsProjectCostEvidence: true,
    });

    await page.goto("/settings");
    await expect(page.getByTestId("settings-page")).toBeVisible();
    await expect(page.getByRole("button", { name: "保存设置" })).toBeEnabled();
    const tree = page.getByRole("tree", { name: "设置分类" });
    await expect(tree.getByRole("treeitem", { name: /访问账户/ })).toHaveCount(0);
    await expect(tree.getByRole("treeitem", { name: /OA申请人凭据/ })).toHaveCount(0);
    await expect(tree.getByRole("treeitem", { name: /数据重置/ })).toHaveCount(0);
    expect(api.count("GET /api/workbench/settings/access-control")).toBe(0);
  });

  test("005 assigns page access through the OA-backed two-column editor", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });

    await page.goto("/settings");
    const tree = page.getByRole("tree", { name: "设置分类" });
    await tree.getByRole("treeitem", { name: /访问账户/ }).click();

    const region = page.getByRole("region", { name: "访问账户" });
    await expect(region).toBeVisible();
    await expect(region.getByText("YNSYLP005")).toBeVisible();
    await expect(region.getByText("005 为固定权限管理员")).toHaveCount(0);
    await expect(region.getByLabel("账户列表")).toBeVisible();
    await expect(region.getByLabel("页面访问权限")).toBeVisible();

    await region.getByRole("searchbox", { name: "搜索 OA 账户" }).fill("YNSYLP006");
    const addButton = region.getByRole("option", { name: "新增账户 YNSYLP006" });
    await expect(addButton).toBeVisible();
    await addButton.click();

    await expect(region.getByText("YNSYLP006 用户")).toBeVisible();
    await setCheckbox(region.getByRole("checkbox", { name: "关联台" }), true);
    await setCheckbox(region.getByRole("checkbox", { name: "银行明细" }), true);

    const saveRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/workbench/settings/access-control") && request.method() === "PUT");
    await region.getByRole("button", { name: "保存访问权限" }).click();
    expect(JSON.parse((await saveRequest).postData() ?? "{}")).toEqual({
      expected_version: 1,
      accounts: [{
        username: "YNSYLP006",
        page_keys: ["bank-details", "reconciliation-workbench"],
      }],
    });
    await expect(region.getByText("已保存访问账户。")).toBeVisible();

    api.startSession("YNSYLP006");
    await page.goto("/");
    await expect(page.getByText(/未配对\s+\d+\s+项/).first()).toBeVisible();
    await expect(page.getByRole("link", { name: "关联台" })).toBeVisible();
    await expect(page.getByRole("link", { name: "银行明细" })).toBeVisible();
    await expect(page.getByRole("link", { name: "设置" })).toHaveCount(0);
  });

  test("multi-account rows stay separated at desktop and narrow widths", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "admin" });
    await page.setViewportSize({ width: 1600, height: 1000 });

    await page.goto("/settings");
    const tree = page.getByRole("tree", { name: "设置分类" });
    await tree.getByRole("treeitem", { name: /访问账户/ }).click();

    const region = page.getByRole("region", { name: "访问账户" });
    const search = region.getByRole("searchbox", { name: "搜索 OA 账户" });
    for (const username of ["YNSYLP002", "YNSYLP006", "YNSYLP007", "YNSYLP010", "YNSYLP044"]) {
      await search.fill(username);
      const addButton = region.getByRole("option", { name: `新增账户 ${username}` });
      await expect(addButton).toBeVisible();
      await addButton.click();
    }

    const accountList = region.getByLabel("账户列表");
    await expect(accountList.locator(".settings-access-account-row")).toHaveCount(5);
    await expectAccountRowsToRemainSeparated(accountList);

    await page.setViewportSize({ width: 1280, height: 800 });
    await expectAccountRowsToRemainSeparated(accountList);

    await page.setViewportSize({ width: 720, height: 900 });
    await expectAccountRowsToRemainSeparated(accountList);
  });
});
