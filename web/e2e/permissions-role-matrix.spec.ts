import { expect, type Page, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

type PageExpectation = {
  path: string;
  label: string;
  assertReady: (page: Page) => Promise<void>;
};

const mutationCallPattern = /^(POST|PUT|PATCH|DELETE) /;

const readablePages: PageExpectation[] = [
  {
    path: "/",
    label: "关联台",
    assertReady: async (page) => {
      await expect(page.getByText(/未配对\s+\d+\s+项/).first()).toBeVisible();
    },
  },
  {
    path: "/tax-offset",
    label: "税金抵扣",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    },
  },
  {
    path: "/cost-statistics",
    label: "成本统计",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    },
  },
  {
    path: "/bank-details",
    label: "银行明细",
    assertReady: async (page) => {
      await expect(page.getByRole("list", { name: "银行账户" })).toBeVisible();
    },
  },
  {
    path: "/pending-invoices",
    label: "待找发票",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "待找发票" })).toBeVisible();
    },
  },
  {
    path: "/input-invoice-usage",
    label: "进项发票使用情况",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "进项发票使用情况" })).toBeVisible();
    },
  },
  {
    path: "/oa-pending-payments",
    label: "OA待付款核对",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "OA 待付款核对" })).toBeVisible();
    },
  },
  {
    path: "/output-invoice-collections",
    label: "销项发票收款情况",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "销项发票收款情况" })).toBeVisible();
    },
  },
  {
    path: "/no-oa-bank-batches",
    label: "免OA流水批量处理",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "免OA流水批量处理" })).toBeVisible();
    },
  },
  {
    path: "/batch-accounting",
    label: "批量账务",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "日常报销批量账务管理" })).toBeVisible();
    },
  },
  {
    path: "/turnover-ledger",
    label: "外部往来款管理",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "外部往来款管理" })).toBeVisible();
    },
  },
  {
    path: "/etc-tickets",
    label: "ETC票据管理",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "ETC票据" })).toBeVisible();
    },
  },
  {
    path: "/settings",
    label: "设置",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
    },
  },
  {
    path: "/imports/bank-transactions",
    label: "银行流水导入",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "银行流水导入" })).toBeVisible();
    },
  },
  {
    path: "/imports/invoices",
    label: "发票导入",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "发票导入" })).toBeVisible();
    },
  },
  {
    path: "/imports/etc-invoices",
    label: "ETC发票导入",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "ETC发票导入" })).toBeVisible();
    },
  },
];

function mutationCalls(calls: string[]) {
  return calls.filter((entry) => mutationCallPattern.test(entry));
}

test.describe("permissions browser role matrix", () => {
  test("read-export users can open every readable page without mutation APIs", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "read_export_only" });

    for (const pageExpectation of readablePages) {
      await test.step(pageExpectation.label, async () => {
        await page.goto(pageExpectation.path);
        await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
        await pageExpectation.assertReady(page);
      });
    }

    expect(mutationCalls(api.calls)).toEqual([]);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBe(0);
  });

  test("read-export users cannot trigger high-risk write controls", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "read_export_only" });

    await page.goto("/settings");
    await expect(page.getByText("当前账号仅支持查看和导出，不能保存设置。")).toBeVisible();
    await expect(page.getByRole("button", { name: "保存设置" })).toBeDisabled();
    const settingsTree = page.getByRole("tree", { name: "设置分类" });
    await expect(settingsTree.getByRole("treeitem", { name: /访问账户/ })).toHaveCount(0);
    await expect(settingsTree.getByRole("treeitem", { name: /OA申请人凭据/ })).toHaveCount(0);
    await expect(settingsTree.getByRole("treeitem", { name: /数据重置/ })).toHaveCount(0);
    expect(api.count("GET /api/workbench/settings/oa-applicant-credentials")).toBe(0);
    expect(api.count("GET /api/workbench/settings/data-reset/jobs/active")).toBe(0);

    await page.goto("/tax-offset");
    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    await expect(page.getByRole("button", { name: "已认证发票导入" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "保存计划" })).toHaveCount(0);

    await page.goto("/imports/bank-transactions");
    await expect(page.getByText("当前账号仅支持查看和导出，不能导入文件。")).toBeVisible();
    await expect(page.getByRole("button", { name: "开始预览" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "确认导入" })).toBeDisabled();
    await expect(page.locator("input[type='file']")).toBeDisabled();

    await page.goto("/no-oa-bank-batches");
    await expect(page.getByText("当前账号仅支持查看和导出，不能提交、撤回或保存免OA流水批次。")).toBeVisible();
    await expect(page.getByRole("button", { name: "提交批次" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "撤回批次" })).toHaveCount(0);
    await page.getByRole("button", { name: "免OA流水标签管理" }).click();
    const tagDrawer = page.getByRole("dialog", { name: "免OA流水标签管理" });
    await expect(tagDrawer.getByRole("button", { name: "全选" })).toBeDisabled();
    await expect(tagDrawer.getByRole("button", { name: "清空" })).toBeDisabled();
    await expect(tagDrawer.getByRole("button", { name: "保存" })).toBeDisabled();

    expect(mutationCalls(api.calls)).toEqual([]);
  });

  test("full-access users can write business pages but cannot open admin operations", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/settings");
    await expect(page.getByRole("button", { name: "保存设置" })).toBeEnabled();
    const settingsTree = page.getByRole("tree", { name: "设置分类" });
    await expect(settingsTree.getByRole("treeitem", { name: /访问账户/ })).toHaveCount(0);
    await expect(settingsTree.getByRole("treeitem", { name: /数据重置/ })).toHaveCount(0);
    expect(api.count("GET /api/workbench/settings/oa-applicant-credentials")).toBe(0);
    expect(api.count("GET /api/workbench/settings/data-reset/jobs/active")).toBe(0);

    await page.goto("/imports/bank-transactions");
    await expect(page.getByText("当前账号仅支持查看和导出，不能导入文件。")).toHaveCount(0);
    await expect(page.locator("input[type='file']")).toBeEnabled();

    await page.goto("/no-oa-bank-batches");
    await expect(page.getByText("当前账号仅支持查看和导出，不能提交、撤回或保存免OA流水批次。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "提交批次" })).toBeVisible();

    await page.goto("/operations/app-health");
    await expect(page.getByText("当前账号没有管理员权限，不能查看 AppHealth 运维状态。")).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toHaveCount(0);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBe(0);
  });

  test("admin users can open admin settings and AppHealth operations", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });

    await page.goto("/settings");
    const settingsTree = page.getByRole("tree", { name: "设置分类" });
    await expect(settingsTree.getByRole("treeitem", { name: /访问账户/ })).toBeVisible();
    await expect(settingsTree.getByRole("treeitem", { name: /OA申请人凭据/ })).toBeVisible();
    await settingsTree.getByRole("treeitem", { name: /数据重置/ }).click();
    await expect(page.getByRole("region", { name: "数据重置" }).getByText("高风险操作")).toBeVisible();
    expect(api.count("GET /api/workbench/settings/oa-applicant-credentials")).toBeGreaterThan(0);
    expect(api.count("GET /api/workbench/settings/data-reset/jobs/active")).toBeGreaterThan(0);

    await page.goto("/operations/app-health");
    await expect(page.getByRole("heading", { name: "AppHealth 运维状态" })).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toBeVisible();
    expect(api.count("GET /api/operations/app-health-dashboard")).toBeGreaterThan(0);
  });
});
