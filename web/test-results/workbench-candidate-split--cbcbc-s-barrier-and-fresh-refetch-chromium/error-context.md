# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: workbench-candidate-split-flow.spec.ts >> workbench automatic candidate split browser flow >> splits an open automatic candidate through preview, freshness barrier, and fresh refetch
- Location: e2e/workbench-candidate-split-flow.spec.ts:13:3

# Error details

```
Error: expect(locator).toBeDisabled() failed

Locator: getByRole('dialog', { name: '关联预览' }).getByRole('button', { name: '关闭关联预览' })
Expected: disabled
Timeout: 8000ms
Error: element(s) not found

Call log:
  - Expect "toBeDisabled" with timeout 8000ms
  - waiting for getByRole('dialog', { name: '关联预览' }).getByRole('button', { name: '关闭关联预览' })

```

```yaml
- complementary "主导航":
  - status "浏览器 e2e mock runtime ready"
  - text: 溯源办公系统 财务运营平台
  - button "折叠菜单" [expanded]
  - separator
  - navigation "主导航":
    - region "财务业务":
      - heading "财务业务" [level=2]
      - list "财务业务":
        - listitem:
          - link "关联台":
            - /url: /
        - listitem:
          - link "成本统计":
            - /url: /cost-statistics
        - listitem:
          - link "银行明细":
            - /url: /bank-details
        - listitem:
          - link "OA待付款核对":
            - /url: /oa-pending-payments
        - listitem:
          - link "免OA流水批量处理":
            - /url: /no-oa-bank-batches
        - listitem:
          - link "批量账务":
            - /url: /batch-accounting
        - listitem:
          - link "外部往来款管理":
            - /url: /turnover-ledger
        - listitem:
          - link "ETC票据管理":
            - /url: /etc-tickets
        - listitem:
          - link "税金抵扣":
            - /url: /tax-offset
        - listitem:
          - link "待找发票":
            - /url: /pending-invoices
        - listitem:
          - link "进项发票使用情况":
            - /url: /input-invoice-usage
        - listitem:
          - link "销项发票收款情况":
            - /url: /output-invoice-collections
    - region "系统操作":
      - heading "系统操作" [level=2]
      - list "系统操作":
        - listitem:
          - link "设置":
            - /url: /settings
        - listitem:
          - link "系统状态":
            - /url: /operations/app-health
        - listitem:
          - link "银行流水导入":
            - /url: /imports/bank-transactions
        - listitem:
          - link "发票导入":
            - /url: /imports/invoices
        - listitem:
          - link "ETC发票导入":
            - /url: /imports/etc-invoices
- main:
  - text: 已配对 0 项 已选 0 OA 0 / 0.00 流水 0 / 0.00 发票 0 / 0.00
  - button "清空选择"
  - button "撤回关联" [disabled]
  - group "已配对 0 项栏显示切换":
    - button "OA" [pressed]
    - button "银行流水" [pressed]
    - button "进销项发票" [pressed]
  - button "放大 已配对 0 项"
  - separator
  - separator
  - text: OA 0 条
  - button "OA按时间降序": 时间↓
  - button "搜索 OA"
  - row "申请人 项目名称 金额 对方户名 申请事由":
    - columnheader "申请人":
      - button "拖动 申请人 列"
      - text: 申请人
      - button "筛选 申请人"
    - columnheader "项目名称":
      - button "拖动 项目名称 列"
      - text: 项目名称
      - button "筛选 项目名称"
    - columnheader "金额":
      - button "拖动 金额 列"
      - text: 金额
    - columnheader "对方户名":
      - button "拖动 对方户名 列"
      - text: 对方户名
      - button "筛选 对方户名"
    - columnheader "申请事由":
      - button "拖动 申请事由 列"
      - text: 申请事由
  - text: 银行流水 0 条
  - button "银行流水时间筛选": 时间筛选
  - button "银行流水按时间降序": 时间↓
  - button "搜索 银行流水"
  - row "对方户名 金额 还借款日期 备注":
    - columnheader "对方户名":
      - button "拖动 对方户名 列"
      - text: 对方户名
      - button "筛选 对方户名"
    - columnheader "金额":
      - button "拖动 金额 列"
      - text: 金额
      - button "筛选 金额"
    - columnheader "还借款日期":
      - button "拖动 还借款日期 列"
      - text: 还借款日期
      - button "筛选 还借款日期"
    - columnheader "备注":
      - button "拖动 备注 列"
      - text: 备注
  - button "进销项发票库存统计：系统发票总数 1，人工导入总数 0，普通可见 1，已提交 ETC 隐藏 0，额外 ETC 0，ETC 折叠批次 0，OA附件解析发票 1": 进销项发票
  - text: 0 条
  - button "进销项发票按时间降序": 时间↓
  - button "搜索 进销项发票"
  - row "销方名称/识别号 购方名称/识别号 发票号码 价税合计":
    - columnheader "销方名称/识别号":
      - button "拖动 销方名称/识别号 列"
      - text: 销方名称/ 识别号
      - button "筛选 销方名称/识别号"
    - columnheader "购方名称/识别号":
      - button "拖动 购方名称/识别号 列"
      - text: 购方名称/ 识别号
      - button "筛选 购方名称/识别号"
    - columnheader "发票号码":
      - button "拖动 发票号码 列"
      - text: 发票号码
    - columnheader "价税合计":
      - button "拖动 价税合计 列"
      - text: 价税合计 不含税价格 税率（税额）
  - text: 当前区域暂无候选组。 已加载 0 / 0 未配对 0 项 已选 0 OA 0 / 0.00 流水 0 / 0.00 发票 0 / 0.00
  - button "清空选择"
  - button "确认关联" [disabled]
  - button "异常处理" [disabled]
  - button "撤回关联" [disabled]
  - button "已处理异常0项"
  - button "已忽略0项"
  - group "未配对 0 项栏显示切换":
    - button "OA" [pressed]
    - button "银行流水" [pressed]
    - button "进销项发票" [pressed]
  - button "放大 未配对 0 项"
  - separator
  - separator
  - text: OA 0 条
  - button "OA按时间降序": 时间↓
  - button "搜索 OA"
  - row "申请人 项目名称 金额 对方户名 申请事由":
    - columnheader "申请人":
      - button "拖动 申请人 列"
      - text: 申请人
      - button "筛选 申请人"
    - columnheader "项目名称":
      - button "拖动 项目名称 列"
      - text: 项目名称
      - button "筛选 项目名称"
    - columnheader "金额":
      - button "拖动 金额 列"
      - text: 金额
    - columnheader "对方户名":
      - button "拖动 对方户名 列"
      - text: 对方户名
      - button "筛选 对方户名"
    - columnheader "申请事由":
      - button "拖动 申请事由 列"
      - text: 申请事由
  - text: 银行流水 0 条
  - button "银行流水时间筛选": 时间筛选
  - button "银行流水按时间降序": 时间↓
  - button "搜索 银行流水"
  - row "对方户名 金额 还借款日期 备注":
    - columnheader "对方户名":
      - button "拖动 对方户名 列"
      - text: 对方户名
      - button "筛选 对方户名"
    - columnheader "金额":
      - button "拖动 金额 列"
      - text: 金额
      - button "筛选 金额"
    - columnheader "还借款日期":
      - button "拖动 还借款日期 列"
      - text: 还借款日期
      - button "筛选 还借款日期"
    - columnheader "备注":
      - button "拖动 备注 列"
      - text: 备注
  - button "进销项发票库存统计：系统发票总数 1，人工导入总数 0，普通可见 1，已提交 ETC 隐藏 0，额外 ETC 0，ETC 折叠批次 0，OA附件解析发票 1": 进销项发票
  - text: 0 条
  - button "进销项发票按时间降序": 时间↓
  - button "搜索 进销项发票"
  - row "销方名称/识别号 购方名称/识别号 发票号码 价税合计":
    - columnheader "销方名称/识别号":
      - button "拖动 销方名称/识别号 列"
      - text: 销方名称/ 识别号
      - button "筛选 销方名称/识别号"
    - columnheader "购方名称/识别号":
      - button "拖动 购方名称/识别号 列"
      - text: 购方名称/ 识别号
      - button "筛选 购方名称/识别号"
    - columnheader "发票号码":
      - button "拖动 发票号码 列"
      - text: 发票号码
    - columnheader "价税合计":
      - button "拖动 价税合计 列"
      - text: 价税合计 不含税价格 税率（税额）
  - text: 当前区域暂无候选组。 已加载 0 / 0
```

# Test source

```ts
  1  | import { expect, test } from "./fixtures/strictTest";
  2  | 
  3  | import { installDeterministicApiMocks } from "./fixtures/apiMocks";
  4  | import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
  5  | 
  6  | const workbenchRowIds = [
  7  |   "oa-o-202603-001",
  8  |   "bk-o-202603-001",
  9  |   "iv-o-202603-001",
  10 | ];
  11 | 
  12 | test.describe("workbench automatic candidate split browser flow", () => {
  13 |   test("splits an open automatic candidate through preview, freshness barrier, and fresh refetch", async ({ page }) => {
  14 |     const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
  15 | 
  16 |     await page.goto("/");
  17 | 
  18 |     const openZone = page.getByTestId("zone-open");
  19 |     const pairedZone = page.getByTestId("zone-paired");
  20 |     const openGroup = page.getByTestId("candidate-group-open-case:CASE-202603-101");
  21 |     await expect(openZone).toBeVisible();
  22 |     await expect(openGroup).toBeVisible();
  23 |     await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toHaveCount(0);
  24 | 
  25 |     await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
  26 |     await expect(openZone.getByText("已选 1")).toBeVisible();
  27 |     await expect(openZone.getByText("带入 2")).toBeVisible();
  28 | 
  29 |     await openZone.getByRole("button", { name: "撤回关联" }).click();
  30 |     const previewDialog = page.getByRole("dialog", { name: "关联预览" });
  31 |     await expect(previewDialog).toBeVisible();
  32 |     await expect(previewDialog.getByText("拆分候选预览")).toBeVisible();
  33 |     await expect(previewDialog.getByText("该组是自动候选，确认后会拆分并隐藏这条候选。")).toBeVisible();
  34 |     await expect(previewDialog.getByTestId("relation-preview-before").getByText("待找流水与发票").first()).toBeVisible();
  35 |     await expect(previewDialog.getByTestId("relation-preview-after").getByText("完全关联")).toHaveCount(0);
  36 |     await expect(previewDialog.getByRole("button", { name: "确认拆分" })).toBeEnabled();
  37 | 
  38 |     const previewBody = api.lastBody("POST /api/workbench/actions/withdraw-link/preview");
  39 |     expect(previewBody).toMatchObject({ month: "all" });
  40 |     expect(previewBody.row_ids).toEqual(expect.arrayContaining(workbenchRowIds));
  41 |     expect(previewBody.row_ids).toHaveLength(workbenchRowIds.length);
  42 | 
  43 |     const barrierCallsBeforeSplit = api.count("POST /api/operation-barrier/status");
  44 |     const workbenchGroupCallsBeforeSplit = api.count("GET /api/workbench/groups");
  45 |     await previewDialog.getByRole("textbox", { name: "备注" }).fill("浏览器拆分候选主链路回归");
  46 |     await previewDialog.getByRole("button", { name: "确认拆分" }).click();
  47 | 
  48 |     await expect(previewDialog).toHaveAttribute("aria-busy", "true");
  49 |     await expect(previewDialog.getByText("正在确认拆分...")).toBeVisible();
  50 |     await expect(previewDialog.getByRole("button", { name: "确认拆分" })).toBeDisabled();
  51 |     await expect(previewDialog.getByRole("button", { name: "取消" })).toBeDisabled();
> 52 |     await expect(previewDialog.getByRole("button", { name: "关闭关联预览" })).toBeDisabled();
     |                                                                         ^ Error: expect(locator).toBeDisabled() failed
  53 |     await expect(previewDialog.getByRole("textbox", { name: "备注" })).toBeDisabled();
  54 |     await expect(openGroup).toBeVisible();
  55 | 
  56 |     await expect(page.getByRole("dialog", { name: "关联预览" })).toHaveCount(0);
  57 |     await expect(page.getByTestId("candidate-group-open-case:CASE-202603-101")).toHaveCount(0);
  58 |     await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toHaveCount(0);
  59 |     await expect(openZone.getByText("已选 0")).toBeVisible();
  60 |     await expect(pairedZone.getByText("已选 0")).toBeVisible();
  61 | 
  62 |     const submitBody = api.lastBody("POST /api/workbench/actions/withdraw-link");
  63 |     expect(submitBody).toMatchObject({
  64 |       month: "all",
  65 |       note: "浏览器拆分候选主链路回归",
  66 |       operation_type: "split_candidate",
  67 |       preview_id: "split_candidate:CASE-202603-101",
  68 |       expected_versions: { "decision:CASE-202603-101": 1 },
  69 |     });
  70 |     expect(submitBody.row_ids).toEqual(expect.arrayContaining(workbenchRowIds));
  71 |     expect(submitBody.row_ids).toHaveLength(workbenchRowIds.length);
  72 |     expect(api.count("POST /api/workbench/actions/withdraw-link/preview")).toBe(1);
  73 |     expect(api.count("POST /api/workbench/actions/withdraw-link")).toBe(1);
  74 |     expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(barrierCallsBeforeSplit);
  75 |     expect(api.count("GET /api/workbench/groups")).toBeGreaterThan(workbenchGroupCallsBeforeSplit);
  76 |     await expectNoUnexpectedSuccessUiErrors(page);
  77 |   });
  78 | });
  79 | 
```