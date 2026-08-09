import { expect, type Page, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

type PageExpectation = {
  path: string;
  label: string;
  assertReady: (page: Page) => Promise<void>;
  allowedEnabledWriteControls?: RegExp[];
};

type DynamicWriteControlOpener = {
  id: string;
  label: string;
  verify: (page: Page) => Promise<void>;
};

const mutationCallPattern = /^(POST|PUT|PATCH|DELETE) /;
const enabledWriteControlPattern = /^保存$|保存设置|保存计划|保存规则|保存并刷新|保存外部往来款|保存补充信息|保存凭据|清空密码|新增账户|重新应用规则|新增标签|拖动 .* 列|确认导入|确认对账|确认闭环|确认关联|确认已支付|确认拆分|确认撤回|确认买票|确认为买票|确认为过账|写回|撤回批次|撤回关联|撤回忽略|^忽略$|^恢复$|删除|新建批次|创建 OA 草稿|创建OA草稿|上传|关联OA项|关联支出流水|关联所选记录|接受推荐票根|选择发票|标记无需开票|标记现金收入|标记异常|异常处理|取消异常处理|取消现金处理|提交异常|继续报异常|排除非ETC|手工确认|已认证发票导入|开始预览|数据重置|重置数据|提交OA|提交 OA|提交审批|提交批次|人工提交/;
const etcReadOnlyDisclosureControls = [/^上传文件/, /^已上传文件/];

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
    path: "/bank-flow-rule-batches",
    label: "流水规则批量处理",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
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
    allowedEnabledWriteControls: etcReadOnlyDisclosureControls,
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
    path: "/imports",
    label: "导入中心",
    assertReady: async (page) => {
      await expect(page.getByRole("heading", { name: "导入中心" })).toBeVisible();
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

const importPageWriteControls = [
  "/imports/bank-transactions",
  "/imports/invoices",
  "/imports/etc-invoices",
];

function mutationCalls(calls: string[], allowedReadLikeCalls: RegExp[] = []) {
  return calls
    .filter((entry) => mutationCallPattern.test(entry))
    .filter((entry) => !allowedReadLikeCalls.some((pattern) => pattern.test(entry)));
}

function startStrictBrowserErrorCapture(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => {
    errors.push(`pageerror: ${error.stack || error.message}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(`console.error: ${message.text()}`);
    }
  });
  page.on("requestfailed", (request) => {
    const failure = request.failure()?.errorText ?? "";
    if (failure === "net::ERR_ABORTED") {
      return;
    }
    errors.push(`requestfailed: ${request.method()} ${request.url()} ${failure}`.trim());
  });
  page.on("dialog", async (dialog) => {
    errors.push(`dialog: ${dialog.type()} ${dialog.message()}`);
    await dialog.dismiss().catch(() => undefined);
  });
  return errors;
}

async function enabledWriteControlCandidates(page: Page, allowed: RegExp[] = []) {
  const buttons = await page
    .locator("button:visible, [role='button']:visible, [role='menuitem']:visible")
    .evaluateAll((elements) => elements.map((element) => {
      const disabled = element.matches(":disabled") || element.getAttribute("aria-disabled") === "true";
      const label = [
        element.getAttribute("aria-label"),
        element.getAttribute("title"),
        element.textContent,
      ].filter(Boolean).join(" ").replace(/\s+/g, " ").trim();
      return { disabled, label };
    }));
  const fileInputs = await page
    .locator("input[type='file']")
    .evaluateAll((elements) => elements.map((element) => ({
      disabled: element.matches(":disabled") || element.getAttribute("aria-disabled") === "true",
      label: element.getAttribute("aria-label") || element.getAttribute("title") || "file input",
    })));

  return [...buttons, ...fileInputs]
    .filter((control) => !control.disabled)
    .map((control) => control.label)
    .filter((label) => enabledWriteControlPattern.test(label))
    .filter((label) => !allowed.some((pattern) => pattern.test(label)));
}

async function expectNoEnabledWriteControlCandidates(page: Page, allowed: RegExp[] = []) {
  expect(await enabledWriteControlCandidates(page, allowed)).toEqual([]);
}

async function expectWorkbenchColumnDragDisabled(page: Page) {
  const dragHandles = page.getByRole("button", { name: /^拖动 .* 列$/ });
  await expect(dragHandles.first()).toBeVisible();
  expect(await dragHandles.count()).toBeGreaterThanOrEqual(3);
  expect(await dragHandles.evaluateAll((elements) =>
    elements.every((element) => element instanceof HTMLButtonElement && element.disabled)
  )).toBe(true);

  const firstHandleBox = await dragHandles.first().boundingBox();
  const secondHandleBox = await dragHandles.nth(1).boundingBox();
  expect(firstHandleBox).not.toBeNull();
  expect(secondHandleBox).not.toBeNull();
  if (firstHandleBox && secondHandleBox) {
    await page.mouse.move(firstHandleBox.x + firstHandleBox.width / 2, firstHandleBox.y + firstHandleBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(secondHandleBox.x + secondHandleBox.width / 2, secondHandleBox.y + secondHandleBox.height / 2);
    await page.mouse.up();
  }
  await expect(page.locator("body")).not.toHaveClass(/column-layout-dragging/);
}

async function selectWorkbenchGroupRows(page: Page, zone: "unpaired" | "paired") {
  const zoneLocator = page.getByTestId(`zone-${zone}`);
  const group = page.getByTestId(
    zone === "paired"
      ? "candidate-group-paired-case:CASE-202603-101"
      : "candidate-group-unpaired-row:oa-o-202603-001",
  );
  await expect(zoneLocator).toBeVisible();
  await expect(group).toBeVisible();

  await zoneLocator.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
  await zoneLocator.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
  await zoneLocator.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }).click();
  await expect(zoneLocator.getByText("已选 3")).toBeVisible();

  return { zoneLocator, group };
}

const readExportAllowedReadLikeCalls = [
  /^POST \/api\/input-invoice-usage\/oa-reverse\/preview$/,
];

const readExportDynamicWriteControlOpeners: DynamicWriteControlOpener[] = [
  {
    id: "reconciliation-workbench:unpaired-actions",
    label: "workbench unpaired write controls",
    verify: async (page) => {
      await page.goto("/");
      await expectWorkbenchColumnDragDisabled(page);
      const { zoneLocator: unpairedZone, group: unpairedGroup } = await selectWorkbenchGroupRows(page, "unpaired");
      await expect(unpairedGroup.getByRole("button", { name: "详情" }).first()).toBeVisible();
      await expect(unpairedZone.getByRole("button", { name: "确认关联" })).toBeDisabled();
      await expect(unpairedZone.getByRole("button", { name: "异常处理" })).toBeDisabled();
      await expect(unpairedZone.getByRole("button", { name: "撤回关联" })).toHaveCount(0);
      await expect(unpairedGroup.getByRole("button", { name: "忽略", exact: true })).toHaveCount(0);
      await expect(unpairedGroup.getByRole("button", { name: "标记异常" })).toHaveCount(0);
      await expect(unpairedGroup.getByRole("button", { name: "异常处理" })).toHaveCount(0);
      await expect(unpairedGroup.getByRole("button", { name: "确认关联" })).toHaveCount(0);
      await expect(page.getByRole("dialog", { name: /确认关联|撤回关联/ })).toHaveCount(0);
      await expect(page.getByRole("dialog", { name: "统一异常处理" })).toHaveCount(0);
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
  {
    id: "bank-details:auto-tag-rules",
    label: "bank details auto-tag rules drawer",
    verify: async (page) => {
      await page.goto("/bank-details");
      await expect(page.getByTestId("bank-details-page")).toBeVisible();
      await page.getByRole("button", { name: /自动标签规则/ }).click();
      const autoTagDrawer = page.getByRole("dialog", { name: "自动标签规则" });
      await expect(autoTagDrawer).toBeVisible();
      await expect(autoTagDrawer.getByRole("button", { name: "新增标签" })).toBeDisabled();
      await expect(autoTagDrawer.getByRole("button", { name: "重新应用规则" })).toBeDisabled();
      await expect(autoTagDrawer.getByRole("button", { name: "保存" })).toBeDisabled();
      await expectNoEnabledWriteControlCandidates(page);
      await autoTagDrawer.getByLabel("关闭自动标签规则抽屉").click();
      await expect(autoTagDrawer).toBeHidden();
    },
  },
  {
    id: "cost-statistics:tag-rules",
    label: "cost statistics tag rules drawer",
    verify: async (page) => {
      await page.goto("/cost-statistics");
      await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
      await page.getByRole("button", { name: "成本统计标签规则" }).click();
      const tagRulesDrawer = page.getByRole("dialog", { name: "成本统计标签规则" });
      await expect(tagRulesDrawer).toBeVisible();
      await expect(tagRulesDrawer.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
  {
    id: "bank-details:category-confirmation",
    label: "bank details category confirmation controls",
    verify: async (page) => {
      await page.goto("/bank-details");
      await expect(page.getByTestId("bank-details-page")).toBeVisible();
      const bankRow = page.getByRole("row", { name: /智能工厂设备商/ });
      await expect(bankRow.getByRole("button", { name: "待确认" })).toBeDisabled();
      await expect(page.getByRole("menu", { name: "待确认主标签" })).toHaveCount(0);
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
  {
    id: "bank-flow-rule-batches:tag-drawer",
    label: "bank flow rule tag management drawer",
    verify: async (page) => {
      await page.goto("/bank-flow-rule-batches");
      await expect(page.getByText("当前账号仅支持查看和导出，不能提交、撤回或保存流水规则批次。")).toBeVisible();
      await expect(page.getByRole("button", { name: "提交批次" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "撤回批次" })).toHaveCount(0);
      await page.getByRole("button", { name: "流水规则标签管理" }).click();
      const tagDrawer = page.getByRole("dialog", { name: "流水规则标签管理" });
      await expect(tagDrawer.getByRole("button", { name: "全选" })).toHaveCount(0);
      await expect(tagDrawer.getByRole("button", { name: "清空" })).toHaveCount(0);
      await expect(tagDrawer.getByRole("button", { name: "保存" })).toBeDisabled();
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
  {
    id: "pending-invoices:expense-rules",
    label: "pending invoices expense rules drawer",
    verify: async (page) => {
      await page.goto("/pending-invoices");
      await expect(page.getByRole("heading", { name: "待找发票" })).toBeVisible();
      await expect(page.getByText("当前账号仅支持查看和导出，不能选择发票、修改收入状态或保存规则。")).toBeVisible();
      await page.getByRole("checkbox", { name: "选择流水 智能工厂设备商", exact: true }).check();
      await expect(page.getByRole("button", { name: "选择发票" })).toBeDisabled();
      await page.getByRole("button", { name: "支出待找发票规则设置" }).click();
      const expenseRulesDrawer = page.getByRole("dialog", { name: "支出待找发票规则设置" });
      await expect(expenseRulesDrawer.getByText("当前账号只能查看规则，不能保存。")).toBeVisible();
      await expect(expenseRulesDrawer.getByRole("button", { name: "保存规则" })).toBeDisabled();
      await expectNoEnabledWriteControlCandidates(page);
      await expenseRulesDrawer.getByLabel("关闭规则抽屉").click();
      await expect(expenseRulesDrawer).toBeHidden();
    },
  },
  {
    id: "pending-invoices:income-rules",
    label: "pending invoices income rules drawer",
    verify: async (page) => {
      await page.goto("/pending-invoices");
      await expect(page.getByRole("heading", { name: "待找发票" })).toBeVisible();
      await expect(page.getByText("当前账号仅支持查看和导出，不能选择发票、修改收入状态或保存规则。")).toBeVisible();
      await page.getByRole("radio", { name: /^收入 / }).click();
      await expect(page.getByRole("radio", { name: /^收入 / })).toBeChecked();
      await page.getByRole("button", { name: "收入待找发票规则设置" }).click();
      const incomeRulesDrawer = page.getByRole("dialog", { name: "收入待找发票规则设置" });
      await expect(incomeRulesDrawer).toBeVisible();
      await expect(incomeRulesDrawer.getByText("当前账号只能查看规则，不能保存。")).toBeVisible();
      await expect(incomeRulesDrawer.getByRole("button", { name: "保存规则" })).toBeDisabled();
      await expectNoEnabledWriteControlCandidates(page);
      await incomeRulesDrawer.getByLabel("关闭规则抽屉").click();
      await expect(incomeRulesDrawer).toBeHidden();
    },
  },
  {
    id: "pending-invoices:income-batch",
    label: "pending invoices income batch controls",
    verify: async (page) => {
      await page.goto("/pending-invoices");
      await expect(page.getByRole("heading", { name: "待找发票" })).toBeVisible();
      await expect(page.getByText("当前账号仅支持查看和导出，不能选择发票、修改收入状态或保存规则。")).toBeVisible();
      await page.getByRole("radio", { name: /^收入 / }).click();
      await expect(page.getByRole("row", { name: /收入批量客户A/ })).toBeVisible();
      await page.getByRole("checkbox", { name: "选择流水 收入批量客户A" }).check();
      await page.getByRole("checkbox", { name: "选择流水 收入批量客户B" }).check();
      await expect(page.getByRole("button", { name: "标记无需开票" })).toBeDisabled();
      await expect(page.getByRole("button", { name: "标记现金收入" })).toBeDisabled();
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
  {
    id: "input-invoice-usage:payment-rules",
    label: "input invoice usage payment rules drawer",
    verify: async (page) => {
      await page.goto("/input-invoice-usage");
      await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
      await page.getByRole("button", { name: "发票与支付状态规则设置" }).click();
      const paymentRulesDrawer = page.getByRole("dialog", { name: "发票与支付状态规则设置" });
      await expect(paymentRulesDrawer).toBeVisible();
      await expect(paymentRulesDrawer.getByText("只读")).toBeVisible();
      await expect(paymentRulesDrawer.getByRole("button", { name: "保存并刷新" })).toHaveCount(0);
      await expect(paymentRulesDrawer.getByRole("button", { name: "还原" })).toHaveCount(0);
      await expectNoEnabledWriteControlCandidates(page);
      await paymentRulesDrawer.getByRole("button", { name: "关闭支付状态规则抽屉" }).click();
      await expect(paymentRulesDrawer).toBeHidden();
    },
  },
  {
    id: "input-invoice-usage:oa-reverse",
    label: "input invoice usage OA reverse drawer",
    verify: async (page) => {
      await page.goto("/input-invoice-usage");
      await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
      const previewResponsePromise = page.waitForResponse((response) => {
        const url = new URL(response.url());
        return response.request().method() === "POST"
          && url.pathname.endsWith("/api/input-invoice-usage/oa-reverse/preview");
      });
      await page.getByRole("button", { name: "以发票反提 OA" }).click();
      const previewResponse = await previewResponsePromise;
      expect(previewResponse.status()).toBe(200);
      const previewPayload = await previewResponse.json() as { can_create_draft?: boolean; canCreateDraft?: boolean };
      expect(previewPayload.can_create_draft ?? previewPayload.canCreateDraft).toBe(false);
      const workflow = page.getByLabel("以发票反提 OA 工作流", { exact: true });
      await expect(workflow).toBeVisible();
      await expect(page.getByLabel("以发票反提 OA 提示")).toHaveCount(0);
      await expect(workflow.getByRole("grid", { name: "反提 OA 候选发票清单" })).toBeVisible();
      await expect(workflow.getByRole("button", { name: "创建 OA 草稿" })).toBeDisabled();
      await expectNoEnabledWriteControlCandidates(page, [/^全选候选$/, /^清空选择$/]);
      await page.getByRole("button", { name: "关闭以发票反提 OA 工作流" }).click();
      await expect(workflow).toBeHidden();
    },
  },
  {
    id: "output-invoice-collections:canonical-read-only",
    label: "output invoice canonical read-only page",
    verify: async (page) => {
      await page.goto("/output-invoice-collections");
      await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
      await expect(page.getByRole("button", { name: "收款状态规则" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "收据编号设置" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "状态/提醒" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "红蓝票", exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: /收据/ })).toHaveCount(0);
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
  {
    id: "oa-pending-payments:in-progress",
    label: "OA pending in-progress controls",
    verify: async (page) => {
      await page.goto("/oa-pending-payments");
      await expect(page.getByRole("heading", { name: "OA 待付款核对" })).toBeVisible();
      await page.getByRole("button", { name: /进行中 OA/ }).click();
      await expect(page.getByText("当前账号仅支持查看和导出，不能自动写回 OA 或关联支出流水。")).toBeVisible();
      await expect(page.getByRole("button", { name: "关联支出流水" })).toBeDisabled();
      await expect(page.getByRole("button", { name: /确认已支付并写回|写回 OA/ })).toHaveCount(0);
      await expect(page.getByRole("checkbox", { name: /选择 OA 进行中/ })).toHaveCount(0);
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
  {
    id: "oa-pending-payments:expense-rules",
    label: "OA pending expense rules drawer",
    verify: async (page) => {
      await page.goto("/oa-pending-payments");
      await expect(page.getByRole("heading", { name: "OA 待付款核对" })).toBeVisible();
      await page.getByRole("button", { name: "支出流水无需开票规则设置" }).click();
      const rulesDrawer = page.getByRole("dialog", { name: "支出流水无需开票规则设置" });
      await expect(rulesDrawer).toBeVisible();
      await expect(rulesDrawer.getByText("当前账号只能查看规则，不能保存。")).toBeVisible();
      await expect(rulesDrawer.getByRole("button", { name: "保存规则" })).toBeDisabled();
      await expectNoEnabledWriteControlCandidates(page);
      await rulesDrawer.getByLabel("关闭规则抽屉").click();
      await expect(rulesDrawer).toBeHidden();
    },
  },
  {
    id: "etc-tickets:reconciliation-workflow",
    label: "ETC ticket reconciliation workflow controls",
    verify: async (page) => {
      await page.goto("/etc-tickets");
      await expect(page.getByTestId("etc-ticket-management-page")).toBeVisible();
      await expect(page.getByText(/当前账号仅支持查看和导出，不能创建.*草稿、人工确认、上传、删除或新建.*批次。/)).toBeVisible();
      await expect(page.getByRole("region", { name: "ETC批次流程" })).toBeVisible();
      const uploadRegion = page.getByLabel("ETC对账文件上传");
      await expect(uploadRegion).toBeVisible();
      await expect(page.getByRole("button", { name: "上传信用卡账单" })).toHaveAttribute("aria-disabled", "true");
      await expect(page.getByRole("button", { name: "上传票根网" })).toHaveAttribute("aria-disabled", "true");
      expect(await uploadRegion.locator("input[type='file']").evaluateAll((inputs) =>
        inputs.every((input) => input instanceof HTMLInputElement && input.disabled)
      )).toBe(true);
      await expect(page.getByRole("button", { name: "确认对账" })).toBeDisabled();
      await page.getByRole("button", { name: /人工处理/ }).click();
      const manualReview = page.getByRole("region", { name: "人工核对处理" });
      await expect(manualReview).toBeVisible();
      await expect(manualReview.getByRole("button", { name: "接受推荐票根" })).toBeDisabled();
      await expect(manualReview.getByRole("button", { name: "关联所选记录" })).toBeDisabled();
      await expect(manualReview.getByRole("button", { name: "排除非ETC" })).toBeDisabled();
      await expect(manualReview.getByRole("button", { name: "标记异常" })).toBeDisabled();
      await expect(manualReview.getByRole("button", { name: "手工确认" })).toBeDisabled();
      await expectNoEnabledWriteControlCandidates(page, etcReadOnlyDisclosureControls);
    },
  },
  {
    id: "batch-accounting:oa-selection",
    label: "batch accounting OA selection controls",
    verify: async (page) => {
      await page.goto("/batch-accounting");
      await expect(page.getByRole("heading", { name: "日常报销批量账务管理" })).toBeVisible();
      await expect(page.getByText("当前账号仅支持查看和导出，不能提交或撤回批量账务关联。")).toBeVisible();
      const oaTable = page.getByRole("table", { name: "可关联OA项" });
      await oaTable.getByRole("checkbox", { name: "选择 刘晨 2026-04-02" }).check();
      await oaTable.getByRole("checkbox", { name: "选择 王青 2026-04-03" }).check();
      await expect(page.getByRole("button", { name: "关联OA项与流水" })).toBeDisabled();
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
  {
    id: "turnover-ledger:tag-drawer",
    label: "turnover ledger tag drawer",
    verify: async (page) => {
      await page.goto("/turnover-ledger");
      await expect(page.getByRole("heading", { name: "外部往来款管理" })).toBeVisible();
      await expect(page.getByText("当前账号为只读权限，可查看台账与详情，不能确认或撤销归并。")).toBeVisible();
      await page.getByRole("button", { name: "外部往来款标签设置" }).click();
      const turnoverTagDrawer = page.getByRole("dialog", { name: "外部往来款标签设置" });
      await expect(turnoverTagDrawer.getByText("当前账号仅支持查看和导出，不能保存外部往来款标签设置。")).toBeVisible();
      await expect(turnoverTagDrawer.getByRole("button", { name: "全选" })).toBeDisabled();
      await expect(turnoverTagDrawer.getByRole("button", { name: "清空" })).toBeDisabled();
      await expect(turnoverTagDrawer.getByRole("button", { name: "保存" })).toBeDisabled();
      await expectNoEnabledWriteControlCandidates(page);
      await turnoverTagDrawer.getByLabel("关闭外部往来款标签设置").click();
      await expect(turnoverTagDrawer).toBeHidden();
    },
  },
  {
    id: "turnover-ledger:detail-controls",
    label: "turnover ledger detail controls",
    verify: async (page) => {
      await page.goto("/turnover-ledger");
      await expect(page.getByRole("heading", { name: "外部往来款管理" })).toBeVisible();
      await expect(page.getByText("当前账号为只读权限，可查看台账与详情，不能确认或撤销归并。")).toBeVisible();
      await page.getByRole("button", { name: "展开 云南建设有限公司 流水明细" }).click();
      await expect(page.getByRole("checkbox", { name: "选择流水 turnover-bank-expense-1000" })).toBeDisabled();
      await expect(page.getByRole("button", { name: "编辑流水 turnover-bank-expense-1000" })).toBeDisabled();
      await expect(page.getByRole("button", { name: "确认闭环" })).toBeDisabled();
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
];

const readExportBankDetailsManualAssignmentOpeners: DynamicWriteControlOpener[] = [
  {
    id: "bank-details:manual-category-assignment",
    label: "bank details manual category assignment controls",
    verify: async (page) => {
      await page.goto("/bank-details");
      await expect(page.getByTestId("bank-details-page")).toBeVisible();
      const bankRow = page.getByRole("row", { name: /智能工厂设备商/ });
      await expect(bankRow.getByRole("button", { name: "待分类" })).toBeDisabled();
      await expect(page.getByRole("menu", { name: "待分类主标签" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "保存" })).toHaveCount(0);
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
];

const readExportSubmittedStateWriteControlOpeners: DynamicWriteControlOpener[] = [
  {
    id: "reconciliation-workbench:paired-withdraw-actions",
    label: "workbench paired relation withdraw controls",
    verify: async (page) => {
      await page.goto("/");
      const { zoneLocator: pairedZone, group: pairedGroup } = await selectWorkbenchGroupRows(page, "paired");
      await expect(pairedGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeVisible();
      await expect(pairedZone.getByRole("button", { name: "撤回关联" })).toBeDisabled();
      await expect(pairedGroup.getByRole("button", { name: "更多" })).toHaveCount(0);
      await expect(pairedGroup.getByRole("button", { name: "取消关联" })).toHaveCount(0);
      await expect(pairedGroup.getByRole("button", { name: "异常处理" })).toHaveCount(0);
      await expect(page.getByRole("menuitem", { name: "取消关联" })).toHaveCount(0);
      await expect(page.getByRole("dialog", { name: /确认关联|撤回关联/ })).toHaveCount(0);
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
  {
    id: "reconciliation-workbench:cash-special-actions",
    label: "workbench cash special row actions",
    verify: async (page) => {
      await page.goto("/");
      const { group: pairedGroup } = await selectWorkbenchGroupRows(page, "paired");
      await expect(pairedGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeVisible();
      await expect(pairedGroup.getByRole("button", { name: "更多" })).toHaveCount(0);
      await expect(page.getByRole("menuitem", { name: "确认为过账" })).toHaveCount(0);
      await expect(page.getByRole("menuitem", { name: "确认为买票" })).toHaveCount(0);
      await expect(page.getByRole("menuitem", { name: "取消现金处理" })).toHaveCount(0);
      await expect(page.getByRole("dialog", { name: "确认买票成本" })).toHaveCount(0);
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
  {
    id: "batch-accounting:submitted-withdraw",
    label: "batch accounting submitted withdraw controls",
    verify: async (page) => {
      await page.goto("/batch-accounting");
      await expect(page.getByRole("heading", { name: "日常报销批量账务管理" })).toBeVisible();
      await expect(page.getByText("当前账号仅支持查看和导出，不能提交或撤回批量账务关联。")).toBeVisible();
      await page.getByRole("button", { name: "已提交 1" }).click();
      await expect(page.getByRole("button", { name: "已提交 1" })).toHaveAttribute("aria-pressed", "true");
      await expect(page.getByRole("table", { name: "已关联OA项" })).toBeVisible();
      await expect(page.getByRole("button", { name: "撤回关联" })).toBeDisabled();
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
];

const readExportWorkbenchRecoveryWriteControlOpeners: DynamicWriteControlOpener[] = [
  {
    id: "reconciliation-workbench:exception-drawer",
    label: "workbench unified exception drawer controls",
    verify: async (page) => {
      await page.goto("/");
      const unpairedZone = page.getByTestId("zone-unpaired");
      await expect(unpairedZone).toBeVisible();

      await unpairedZone.getByRole("button", { name: /异常 \d+ \| 已忽略 \d+/ }).click();
      const exceptionDrawer = page.getByRole("dialog", { name: "异常处理" });
      await expect(exceptionDrawer).toBeVisible();
      await exceptionDrawer.getByRole("button", { name: "展开异常明细" }).first().click();
      await expect(exceptionDrawer.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeVisible();
      await expect(exceptionDrawer.getByText("金额不一致").first()).toBeVisible();
      await expect(exceptionDrawer.getByRole("button", { name: "忽略" })).toHaveCount(0);
      await expectNoEnabledWriteControlCandidates(page);
    },
  },
];

test.describe("permissions browser role matrix", () => {
  test("permission-bearing denied users stop at the direct URL and protected API boundary", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "forbidden",
      sessionUsername: "YNSYLP006",
    });

    await page.goto("/fin-ops/");
    await expect(page.getByRole("heading", { name: "无权访问财务运营平台" })).toBeVisible();
    await expect(page.getByTestId("settings-page")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /放大 未配对/ })).toHaveCount(0);
    expect(api.count("GET /api/workbench")).toBe(0);

    const evidence = await page.evaluate(async () => {
      const sessionResponse = await fetch("/api/session/me");
      const session = await sessionResponse.json();
      const protectedResponse = await fetch("/api/workbench?month=all");
      return {
        session,
        protectedStatus: protectedResponse.status,
        protectedBody: await protectedResponse.json(),
      };
    });

    expect(evidence.session).toMatchObject({
      user: { username: "YNSYLP006" },
      roles: ["finance", "business", "finops_full_access"],
      permissions: ["finops:app:view"],
      allowed: false,
      access_tier: "denied",
      can_access_app: false,
      can_mutate_data: false,
      can_admin_access: false,
    });
    expect(evidence).toMatchObject({
      protectedStatus: 403,
      protectedBody: { error: "forbidden" },
    });
    expect(api.count("GET /api/workbench")).toBe(1);
  });

  test("read-export users can open every readable page without mutation APIs", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "read_export_only" });

    for (const pageExpectation of readablePages) {
      await test.step(pageExpectation.label, async () => {
        await page.goto(pageExpectation.path);
        await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
        await pageExpectation.assertReady(page);
        await expectNoEnabledWriteControlCandidates(page, pageExpectation.allowedEnabledWriteControls);
      });
    }

    expect(mutationCalls(api.calls)).toEqual([]);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("read-export users cannot trigger high-risk write controls", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      bankDetailsClassificationMode: "needs_confirmation",
      etcTicketReconciliationWorkflow: true,
      oaPendingPaymentBankLinkFlow: true,
      oaPendingPaymentWritebackPaidFlow: true,
      pendingInvoiceAttachExistingBatchRows: true,
      pendingInvoiceIncomeBatchRows: true,
      sessionMode: "read_export_only",
    });

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

    for (const importPath of importPageWriteControls) {
      await test.step(`${importPath} read-export import controls`, async () => {
        await page.goto(importPath);
        await expect(page.getByText("当前账号仅支持查看和导出，不能导入文件。")).toBeVisible();
        await expect(page.getByRole("button", { name: "开始预览" })).toBeDisabled();
        await expect(page.getByRole("button", { name: "确认导入" })).toBeDisabled();
        await expect(page.locator("input[type='file']")).toBeDisabled();
        await expectNoEnabledWriteControlCandidates(page);
      });
    }

    await page.goto("/etc-tickets");
    await expect(page.getByRole("heading", { name: "ETC票据" })).toBeVisible();
    await expect(page.getByText(/当前账号仅支持查看和导出，不能创建.*草稿、人工确认、上传、删除或新建.*批次。/)).toBeVisible();
    await expect(page.getByRole("button", { name: "新建批次" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "当前账号仅支持查看和导出，不能删除 ETC 批次。" }).first()).toBeDisabled();
    await expectNoEnabledWriteControlCandidates(page, etcReadOnlyDisclosureControls);

    for (const opener of readExportDynamicWriteControlOpeners) {
      await test.step(opener.label, async () => {
        await opener.verify(page);
      });
    }

    expect(mutationCalls(api.calls, readExportAllowedReadLikeCalls)).toEqual([]);
    expect(api.count("POST /api/workbench/settings")).toBe(0);
    expect(api.count("POST /api/bank-details/transactions/bk-o-202603-001/category-confirmation")).toBe(0);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/oa-draft")).toBe(0);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/batches")).toBe(0);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/batches/input-oa-reverse-batch-e2e-001/manual-oa-status")).toBe(0);
    expect(api.count("PUT /api/pending-invoices/rules")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("read-export users cannot trigger submitted-state write controls", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      batchAccountingInitialSubmitted: true,
      sessionMode: "read_export_only",
      workbenchCashSpecialActions: true,
      workbenchInitialRelationConfirmed: true,
    });

    for (const opener of readExportSubmittedStateWriteControlOpeners) {
      await test.step(opener.label, async () => {
        await opener.verify(page);
      });
    }

    expect(mutationCalls(api.calls)).toEqual([]);
    expect(api.count("POST /api/batch-accounting/BA-REL-202604-001/withdraw")).toBe(0);
    expect(api.count("POST /api/workbench/actions/confirm-cash-pass-through")).toBe(0);
    expect(api.count("POST /api/workbench/actions/confirm-cash-ticket-purchase")).toBe(0);
    expect(api.count("POST /api/workbench/actions/cancel-cash-special")).toBe(0);
    expect(api.count("POST /api/workbench/actions/withdraw-link/preview")).toBe(0);
    expect(api.count("POST /api/workbench/actions/withdraw-link")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("read-export users cannot trigger bank detail manual assignment controls", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      bankDetailsClassificationMode: "unmatched",
      sessionMode: "read_export_only",
    });

    for (const opener of readExportBankDetailsManualAssignmentOpeners) {
      await test.step(opener.label, async () => {
        await opener.verify(page);
      });
    }

    expect(mutationCalls(api.calls)).toEqual([]);
    expect(api.count("POST /api/bank-details/transactions/bk-o-202603-001/category-assignment")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("read-export users cannot reclassify automatic bank detail labels", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "read_export_only",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    const bankRow = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRow.getByText("成本 / 设备款")).toBeVisible();
    await expect(bankRow.getByRole("button", { name: "撤销" })).toBeDisabled();
    await expect(page.getByRole("menu", { name: "重新分类主标签" })).toHaveCount(0);
    await expectNoEnabledWriteControlCandidates(page);

    expect(mutationCalls(api.calls)).toEqual([]);
    expect(api.count("POST /api/bank-details/transactions/bk-o-202603-001/category-assignment")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("read-export users cannot trigger workbench recovery write controls", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "read_export_only",
      workbenchAmountMismatchScenario: true,
      workbenchInitialRelationConfirmed: true,
    });

    for (const opener of readExportWorkbenchRecoveryWriteControlOpeners) {
      await test.step(opener.label, async () => {
        await opener.verify(page);
      });
    }

    expect(mutationCalls(api.calls)).toEqual([]);
    expect(api.count("POST /api/workbench/actions/cancel-exception")).toBe(0);
    expect(api.count("POST /api/workbench/actions/unignore-row")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("full-access users can write business pages but cannot open admin operations", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      settingsProjectScopeFanout: true,
    });
    const projectName = "昆明卷烟厂动力设备控制系统升级改造项目";

    await page.goto("/settings");
    await expect(page.getByRole("button", { name: "保存设置" })).toBeEnabled();
    const settingsTree = page.getByRole("tree", { name: "设置分类" });
    await expect(settingsTree.getByRole("treeitem", { name: /访问账户/ })).toHaveCount(0);
    await expect(settingsTree.getByRole("treeitem", { name: /数据重置/ })).toHaveCount(0);
    expect(api.count("GET /api/workbench/settings/oa-applicant-credentials")).toBe(0);
    expect(api.count("GET /api/workbench/settings/data-reset/jobs/active")).toBe(0);
    await settingsTree.getByRole("treeitem", { name: /项目状态/ }).click();
    const activeProjects = page.getByRole("table", { name: "进行中项目" });
    await expect(activeProjects.getByText(projectName)).toBeVisible();
    await activeProjects.getByLabel(`${projectName} 标记完成`).click();
    const saveRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/workbench/settings")
      && request.method() === "POST");
    const saveResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/workbench/settings")
      && response.request().method() === "POST");
    await page.getByRole("button", { name: "保存设置" }).click();
    const saveBody = JSON.parse((await saveRequest).postData() ?? "{}") as {
      completed_project_ids?: string[];
    };
    expect(saveBody.completed_project_ids).toEqual(["settings-cost-project-e2e"]);
    expect(saveBody).not.toHaveProperty("access_control");
    expect(saveBody).not.toHaveProperty("allowed_usernames");
    expect(saveBody).not.toHaveProperty("readonly_export_usernames");
    expect(saveBody).not.toHaveProperty("admin_usernames");
    expect((await saveResponse).status()).toBe(200);
    await expect(page.getByText("已保存关联台设置。")).toBeVisible();
    expect(api.count("POST /api/workbench/settings")).toBe(1);

    const browserErrorCountBeforeDirectAttack = browserErrors.length;
    const directAttack = await page.evaluate(async () => {
      const generic = await fetch("/api/workbench/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ admin_usernames: ["E2EUSER001"] }),
      });
      const dedicated = await fetch("/api/workbench/settings/access-control", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_version: 1,
          accounts: [{ username: "E2EUSER001", access_tier: "full_access" }],
        }),
      });
      const read = await fetch("/api/workbench/settings/access-control");
      return {
        genericStatus: generic.status,
        genericBody: await generic.json(),
        dedicatedStatus: dedicated.status,
        readStatus: read.status,
      };
    });
    expect(directAttack).toMatchObject({
      genericStatus: 400,
      genericBody: { error: "access_control_write_forbidden" },
      dedicatedStatus: 403,
      readStatus: 403,
    });
    const expectedDenialConsoleErrors = browserErrors.splice(browserErrorCountBeforeDirectAttack);
    expect(expectedDenialConsoleErrors).toHaveLength(3);
    expect(expectedDenialConsoleErrors.every((entry) => /status of (400|403)/.test(entry))).toBe(true);

    await page.goto("/imports/bank-transactions");
    await expect(page.getByText("当前账号仅支持查看和导出，不能导入文件。")).toHaveCount(0);
    await expect(page.locator("input[type='file']")).toBeEnabled();

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByText("当前账号仅支持查看和导出，不能提交、撤回或保存流水规则批次。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "提交批次" })).toBeVisible();

    await page.goto("/operations/app-health");
    await expect(page.getByText("当前账号没有管理员权限，不能查看 AppHealth 运维状态。")).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toHaveCount(0);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("admin users can open admin settings and AppHealth operations", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });

    await page.goto("/settings");
    const settingsTree = page.getByRole("tree", { name: "设置分类" });
    await expect(settingsTree.getByRole("treeitem", { name: /访问账户/ })).toBeVisible();
    await expect(settingsTree.getByRole("treeitem", { name: /OA申请人凭据/ })).toBeVisible();
    await settingsTree.getByRole("treeitem", { name: /OA申请人凭据/ }).click();
    const oaCredentialRegion = page.getByRole("region", { name: "OA申请人凭据" });
    await expect(oaCredentialRegion).toBeVisible();
    await expect(oaCredentialRegion.getByText("陈秀云")).toBeVisible();
    await expect(oaCredentialRegion.getByText("已配置")).toBeVisible();
    await oaCredentialRegion.getByRole("textbox", { name: "目标 OA 申请人" }).fill("樊祖芳");
    await oaCredentialRegion.getByRole("textbox", { name: "申请人账号标识" }).fill("fan_zufang");
    await oaCredentialRegion.getByRole("textbox", { name: "OA 登录账号" }).fill("fan_zufang");
    const passwordInput = oaCredentialRegion.getByLabel("OA 登录密码");
    await passwordInput.fill("target-password");
    const credentialRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/workbench/settings/oa-applicant-credentials/fan_zufang")
      && request.method() === "PUT");
    const credentialResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/workbench/settings/oa-applicant-credentials/fan_zufang")
      && response.request().method() === "PUT");
    await oaCredentialRegion.getByRole("button", { name: "保存凭据" }).click();
    const credentialBody = JSON.parse((await credentialRequest).postData() ?? "{}") as {
      targetApplicantName?: string;
      oaUsername?: string;
      password?: string;
    };
    expect(credentialBody).toMatchObject({
      targetApplicantName: "樊祖芳",
      oaUsername: "fan_zufang",
      password: "target-password",
    });
    expect((await credentialResponse).status()).toBe(200);
    await expect(passwordInput).toHaveValue("");
    await expect(oaCredentialRegion.getByText("已保存 OA 申请人凭据。")).toBeVisible();
    await expect(oaCredentialRegion.getByText("樊祖芳")).toBeVisible();
    const credentialInputValues = await oaCredentialRegion.locator("input").evaluateAll((inputs) =>
      inputs.map((input) => input instanceof HTMLInputElement ? input.value : ""));
    expect(credentialInputValues).not.toContain("target-password");
    await expect(oaCredentialRegion.getByText("target-password")).toHaveCount(0);

    const clearCredentialResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/workbench/settings/oa-applicant-credentials/fan_zufang")
      && response.request().method() === "DELETE");
    await oaCredentialRegion.getByRole("button", { name: "樊祖芳 清空密码" }).click();
    expect((await clearCredentialResponse).status()).toBe(200);
    await expect(oaCredentialRegion.getByText("已清空 OA 申请人密码。")).toBeVisible();
    await expect(oaCredentialRegion.getByText("未配置")).toBeVisible();
    await expect(oaCredentialRegion.getByText("target-password")).toHaveCount(0);

    await settingsTree.getByRole("treeitem", { name: /访问账户/ }).click();
    const accessAccountsRegion = page.getByRole("region", { name: "访问账户管理" });
    await expect(accessAccountsRegion).toBeVisible();
    await expect(accessAccountsRegion.getByText("YNSYLP005")).toBeVisible();
    await expect(accessAccountsRegion.getByRole("textbox", { name: "YNSYLP005 账户" })).toHaveCount(0);
    await accessAccountsRegion.getByRole("textbox", { name: "新增访问账户" }).fill("READONLY_E2E_ADMIN");
    await accessAccountsRegion.getByLabel("新增账户权限").selectOption({ label: "只可看和只可导出" });
    await accessAccountsRegion.getByRole("button", { name: "新增账户" }).click();
    await expect(accessAccountsRegion.getByRole("textbox", { name: "READONLY_E2E_ADMIN 账户" })).toBeVisible();
    await expect(accessAccountsRegion.getByLabel("READONLY_E2E_ADMIN 权限级别")).toHaveValue("read_export_only");

    const accessSaveRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/workbench/settings/access-control")
      && request.method() === "PUT");
    const accessSaveResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/workbench/settings/access-control")
      && response.request().method() === "PUT");
    await accessAccountsRegion.getByRole("button", { name: "保存访问账户" }).click();
    const accessSavePayload = JSON.parse((await accessSaveRequest).postData() ?? "{}") as Record<string, unknown>;
    expect(accessSavePayload).toEqual({
      expected_version: 1,
      accounts: [{ username: "READONLY_E2E_ADMIN", access_tier: "read_export_only" }],
    });
    expect((await accessSaveResponse).status()).toBe(200);
    await expect(accessAccountsRegion.getByText("已保存访问账户。")).toBeVisible();

    const settingsSaveRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/workbench/settings")
      && request.method() === "POST");
    const settingsSaveResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/workbench/settings")
      && response.request().method() === "POST");
    await page.getByRole("button", { name: "保存设置" }).click();
    const settingsSaveBody = (await settingsSaveRequest).postData() ?? "";
    const settingsSavePayload = JSON.parse(settingsSaveBody) as Record<string, unknown>;
    expect(settingsSavePayload).not.toHaveProperty("access_control");
    expect(settingsSavePayload).not.toHaveProperty("allowed_usernames");
    expect(settingsSavePayload).not.toHaveProperty("readonly_export_usernames");
    expect(settingsSavePayload).not.toHaveProperty("admin_usernames");
    expect(settingsSaveBody).not.toContain("target-password");
    expect(settingsSaveBody).not.toContain("oa_applicant_credentials");
    expect((await settingsSaveResponse).status()).toBe(200);
    await expect(page.getByText("已保存关联台设置。")).toBeVisible();
    await expect(accessAccountsRegion.getByRole("textbox", { name: "READONLY_E2E_ADMIN 账户" })).toBeVisible();
    await expect(accessAccountsRegion.getByLabel("READONLY_E2E_ADMIN 权限级别")).toHaveValue("read_export_only");

    await settingsTree.getByRole("treeitem", { name: /数据重置/ }).click();
    const dataResetRegion = page.getByRole("region", { name: "数据重置" });
    await expect(dataResetRegion.getByText("高风险操作")).toBeVisible();
    const dataResetJobCreatesBeforeDialogSmoke = api.count("POST /api/workbench/settings/data-reset/jobs");
    await dataResetRegion.getByRole("button", { name: "清除所有银行流水数据" }).click();
    const impactDialog = page.getByRole("dialog", { name: "确认数据重置" });
    await expect(impactDialog).toBeVisible();
    await expect(impactDialog.getByText("已导入银行流水会被清空")).toBeVisible();
    await impactDialog.getByRole("button", { name: "继续" }).click();
    const passwordDialog = page.getByRole("dialog", { name: "OA 密码复核" });
    await expect(passwordDialog).toBeVisible();
    await expect(passwordDialog.getByRole("button", { name: "确认清理" })).toBeDisabled();
    await passwordDialog.getByLabel("当前 OA 用户密码").fill("admin-reset-password");
    await passwordDialog.getByLabel("操作原因").fill("权限矩阵安全验证");
    await expect(passwordDialog.getByRole("button", { name: "确认清理" })).toBeEnabled();
    await passwordDialog.getByRole("button", { name: "取消" }).click();
    await expect(passwordDialog).toBeHidden();
    expect(api.count("GET /api/workbench/settings/oa-applicant-credentials")).toBeGreaterThan(0);
    expect(api.count("PUT /api/workbench/settings/oa-applicant-credentials/fan_zufang")).toBe(1);
    expect(api.count("DELETE /api/workbench/settings/oa-applicant-credentials/fan_zufang")).toBe(1);
    expect(api.count("PUT /api/workbench/settings/access-control")).toBe(1);
    expect(api.count("POST /api/workbench/settings")).toBe(1);
    expect(api.count("GET /api/workbench/settings/data-reset/jobs/active")).toBeGreaterThan(0);
    expect(api.count("POST /api/workbench/settings/data-reset/jobs")).toBe(dataResetJobCreatesBeforeDialogSmoke);

    await page.goto("/operations/app-health");
    await expect(page.getByRole("heading", { name: "AppHealth 运维状态" })).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toBeVisible();
    expect(api.count("GET /api/operations/app-health-dashboard")).toBeGreaterThan(0);

    await page.goto("/output-invoice-collections");
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await expect(page.getByRole("button", { name: "收据编号设置" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "收款状态规则" })).toHaveCount(0);

    api.startSession("READONLY_E2E_ADMIN");
    await page.goto("/settings");
    await expect(page.getByText("当前账号仅支持查看和导出，不能保存设置。")).toBeVisible();
    const readonlySettingsTree = page.getByRole("tree", { name: "设置分类" });
    await expect(readonlySettingsTree.getByRole("treeitem", { name: /访问账户/ })).toHaveCount(0);
    await expect(readonlySettingsTree.getByRole("treeitem", { name: /数据重置/ })).toHaveCount(0);

    api.startSession("YNSYLP005");
    const restoreEvidence = await page.evaluate(async () => {
      const response = await fetch("/api/workbench/settings/access-control", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_version: 2, accounts: [] }),
      });
      return { status: response.status, body: await response.json() };
    });
    expect(restoreEvidence).toEqual({
      status: 200,
      body: {
        version: 3,
        administrator: {
          username: "YNSYLP005",
          access_tier: "admin",
          protected: true,
        },
        accounts: [],
      },
    });
    expect(api.count("PUT /api/workbench/settings/access-control")).toBe(2);
    expect(browserErrors).toEqual([]);

    api.startSession("READONLY_E2E_ADMIN");
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "无权访问财务运营平台" })).toBeVisible();
    await expect(page.getByTestId("settings-page")).toHaveCount(0);
  });
});
