# 销项发票收款情况页面设计

日期：2026-05-24

## 背景

用户希望在左侧菜单新增一个销项发票收款跟踪页面。页面参考 `/Users/yu/Desktop/sy/财务运营平台/界面.xlsx` 中 `（待收款）销项发票和收款流水`、`Sheet6` 和 `Sheet7`，但表格设计需要沿用已设计/已实现的 `进项发票使用情况` 页面范式：大列分组、小列摘要、右侧工作流抽屉、服务端分页筛选排序，不做 Excel 式高密度横向表。

本需求是生产级整合方案，不接受救急或临时方案。实现必须融合现有 `fin-ops-platform` 架构，保持低耦合、高聚合，并使用 MUI 原生高性能组件。

## 已确认口径

- 新页面左侧菜单名称建议为 `销项发票收款情况`。
- 建议路由为 `/output-invoice-collections`。
- 主表口径：一行 = 一张正式销项发票。
- 红字发票和蓝字发票各自独立成行；红冲关系作为结构化关系摘要展示，并在详情抽屉里互相链接。
- 页面表格设计参考 `进项发票使用情况` 页面，不采用三栏卡片式重组方案。
- 主表使用 MUI 原生 `Table` 组件族，固定表格布局，尽量在一个页面宽度内展示，不出现横向滚动。
- 每个小列表头都需要支持字段适配的筛选/排序菜单；筛选、排序、分页均走后端。
- 第一阶段做到 `正式只读 + 预览契约`：
  - 真实查询销项发票、收入流水、关联关系。
  - 后端计算收款状态。
  - 三个按钮打开右侧抽屉。
  - 不保存规则。
  - 不生成正式收据编号。
  - 不保存收据历史。
  - 不做作废/重开。
- 代码架构必须预留后续 `状态规则可编辑落库` 和 `正式收据工作流落库` 的服务边界。
- 第一阶段不新增持久化 read model 表，但 API/DTO 要按 read-model 边界设计，后续可替换为 SQL 物化读模型而不改前端。
- `Sheet6` 的作用是 `销项发票收款情况` 状态类型与自动/手动识别规则说明。第一阶段只读展示，不提供保存按钮。
- `Sheet7` 的作用是 `待出收据` 的预览模板。第一阶段用 React/MUI 按模板渲染收据预览，不直接运行或修改 Excel。
- `待出收据` 预览金额默认取当前选中的收入流水金额。
- 一张发票只有一笔收入流水时，默认用该流水金额生成预览。
- 一张发票有多笔收入流水时，抽屉中先选择一笔流水，再按该流水金额生成预览。
- 没有关联收入流水时，不生成可出收据预览，只展示待收金额参考和原因。
- 红冲/退款类第一阶段不自动出收据，提示需要先确认红冲/退款关系。

## Excel 事实摘录

### `（待收款）销项发票和收款流水`

主表标题为 `（待收款）销项发票收款情况`。

主要区域：

- `销项发票统计`
- `待收款金额合计`
- `统计详请`
- `销项发票收款情况类型设置（按钮）sheet6`
- `收入流水`
- `已出收据（按钮）可看历史收据情况`
- `待出收据（按钮）详见sheet7`

原始字段：

- 销项发票：发票代码、发票号码、数电发票号码、销方识别号、销方名称、购方识别号、购买方名称、开票日期、税收分类编码、特定业务类型、货物或应税劳务名称、规格型号、单位、数量、单价、金额、税率、税额、价税合计、发票来源、发票票种、发票状态、是否正数发票、发票风险等级、开票人、备注。
- 收款状态：销项发票收款情况、待收款金额。
- 收入流水：收款银行、收款日期、收款金额、手动关联项目名称。
- 收据：收据情况。

示例状态包括：

- `已收款（可能一对一或1票对多流水）`
- `待收款，已收部分款（可查看收款详请，和预计收款情况并设置提醒）`
- `待收款`
- `开票后冲红（无流水）（可查看开票相关详请）`
- `开票已收款，冲红并退款（有收入流水）`
- `开票已收款，冲红并退款（有支出流水）`
- `开票后待冲红（手动标记）`

### `Sheet6`

Sheet6 标题为 `销项发票收款情况类型设置`。它定义状态分类、描述、需要的功能、销项发票/流水事实要求，以及关联台匹配情况。

可确定的规则：

- `已收款（自动识别）`：有销项发票和收入流水，发票金额和收款一致；可能一对一，也可能一票多流水；关联台进入完全匹配栏。
- `待收款，已收部分款（自动识别）`：有销项发票和收入流水，收入流水金额小于销项发票金额；可查看收款详情、预计收款情况和提醒。
- `待收款（手动标记）`：有销项发票，无收入流水；可查预计收款情况并设置提醒。
- `待冲红（手动标记）`：有销项发票，无收入流水，且以后要冲红字发票。
- `开票后冲红（自动识别）`：有销项发票，无收入流水，自动寻找完全对应的负数/正数销项票，自动识别或手动关联；红字发票背后显示蓝字信息，蓝字发票背后显示红字信息。
- `开票已收款，冲红并退款`：正数发票已有收入流水，后来出现红字发票；如果发现支出流水，识别为已退款，否则可进入冲红待退款方向。

本设计推断：Sheet6 是主表 `销项发票收款情况` 列的规则事实源。第一阶段后端可以用静态规则计算状态；后续规则落库时，Sheet6 抽屉升级为版本化规则管理。

### `Sheet7`

Sheet7 是收据模板。主要内容：

- 公司抬头：`云南溯源科技有限公司`
- 标题：`收    据`
- 日期：年、月、日
- `兹收到 ... 交来下列款项`
- 摘要、金额、备注
- 合计人民币大写和小写
- 主管、经手人

本设计推断：Sheet7 是 `待出收据` 的打印/预览模板。第一阶段只渲染预览，不保存正式收据。

## 目标

- 新增 `销项发票收款情况` 页面，以销项发票为主对象查看收款状态、收入流水和收据情况。
- 主表在一个页面宽度内显示核心信息，不出现横向滚动。
- 主表使用与 `进项发票使用情况` 一致的大列/小列结构，降低 Excel 式密度。
- 每张销项发票只显示一行；完整发票字段、收入流水列表、红冲关系和收据信息通过详情或工作流抽屉查看。
- 后端提供服务端分页、筛选、排序、详情、状态规则读取、收据预览和收据历史占位 API。
- 第一阶段不写入规则或收据事实，但预留后续可写服务边界。
- 保持前后端模块边界清晰，不把销项收款职责混入进项发票使用情况、待找发票、往来款或税金页面。

## 非目标

- 第一阶段不保存收款状态规则。
- 第一阶段不生成正式收据编号。
- 第一阶段不保存收据历史。
- 第一阶段不做收据作废/重开。
- 第一阶段不新增持久化 read model 表。
- 第一阶段不实现导出按钮，除非同步实现正式导出 API。
- 不重做关联台三栏匹配流程。
- 不新增新的表格库或 UI 库。
- 不为了展示方便复制业务事实到页面私有存储。

## 推荐架构

采用独立 `销项发票收款情况` 模块，复用 `进项发票使用情况` 的页面范式和少量 UI 小组件。

后端新增三个高聚合服务边界：

- `OutputInvoiceCollectionQueryService`
  - 负责聚合销项发票、收入流水、active pair relations、红冲关系和收款状态 DTO。
- `OutputInvoiceCollectionStatusRuleService`
  - 第一阶段返回 Sheet6 静态规则，并提供 `classify(rowContext)`。
  - 后续升级为规则落库、版本、审计和重算入口。
- `OutputInvoiceReceiptPreviewService`
  - 第一阶段根据 Sheet7 模板生成待出收据预览 DTO。
  - 后续升级为正式收据创建、历史、作废/重开、编号和审计入口。

前端新增独立模块：

```text
web/src/pages/OutputInvoiceCollectionsPage.tsx
web/src/features/outputInvoiceCollections/
  api.ts
  types.ts
web/src/components/outputInvoiceCollections/
  OutputInvoiceCollectionsTable.tsx
  OutputInvoiceCollectionFilterMenu.tsx
  OutputInvoiceCollectionDetailDrawer.tsx
  CollectionStatusRulesDrawer.tsx
  ReceiptHistoryDrawer.tsx
  ReceiptPreviewDrawer.tsx
```

可以抽取真正通用的小组件到 `web/src/components/invoiceRelations/`，例如可展开单元格、详情抽屉外壳、筛选菜单基础结构。禁止过早抽象成通用“发票关系工作台引擎”。

## 页面信息架构

页面标题：`销项发票收款情况`。

顶部工具栏：

- 关键字搜索。
- 开票日期范围或月份。
- 收款状态快捷筛选。
- `销项发票收款情况类型设置` 按钮，打开 Sheet6 规则抽屉。
- 刷新按钮。
- 第一阶段不展示可点击导出按钮。

筛选和排序：

- 每个小列表头都有菜单入口。
- 文本字段支持包含搜索和排序。
- 枚举字段支持单选或多选、全选、清空和排序。
- 日期字段支持范围筛选和排序。
- 金额字段支持区间筛选和排序。
- 筛选选项来自后端 `filter-options`，前端不硬编码完整业务枚举。
- 筛选、排序、分页必须走后端 API。

主体表格使用四个大列：

1. `销项发票`
2. `收款状态`
3. `收入流水`
4. `收据`

建议列宽：

- `销项发票`：约 42%。
- `收款状态`：约 18%。
- `收入流水`：约 28%。
- `收据`：约 12%。

### 大列 1：销项发票

小列建议：

- `发票号码`
  - 优先显示数电发票号码。
  - 没有数电发票号码时显示 `发票代码 + 发票号码`。
  - 下方显示开票日期 tag。
  - 日期旁显示 `详情` 按钮，打开完整发票详情。
- `购方`
  - 第一行购买方名称。
  - 第二行购买方识别号。
- `价税合计`
  - 显示价税合计。
- `税额/税率`
  - 第一行税额。
  - 第二行税率。
- `业务/货物劳务`
  - 第一行特定业务类型。
  - 第二行货物或应税劳务名称。
  - 超过两行显示展开按钮。

### 大列 2：收款状态

内容：

- 状态 chip。
- 命中依据摘要。
- `已收金额`。
- `待收金额`。
- 规则 ID 或规则说明可在详情/规则抽屉查看。

状态 tone：

- `已收款`：success。
- `待收款，已收部分款`：warning。
- `待收款`：warning 或 info。
- `待冲红`：danger。
- `开票后冲红`：info。
- `开票已收款，冲红并退款`：info 或 warning，取决于是否可证明退款闭环。

第一阶段 `待冲红` 不支持用户手动标记，只在规则抽屉中作为未来状态展示。主表没有收入流水的正数销项票默认算 `待收款`。

### 大列 3：收入流水

小列建议：

- `付款方/日期`
  - 第一行收入流水对方户名。
  - 第二行收款日期 tag。
  - 日期旁显示 `详情` 按钮。
- `收款金额`
  - 单流水显示该流水金额。
  - 多流水显示收款合计，并显示 `多笔` 标记。
- `银行/摘要`
  - 收款银行、账号尾号。
  - 摘要/备注或手动关联项目名称。
  - 完整流水列表进详情抽屉。

### 大列 4：收据

内容：

- 收据状态：`已出收据`、`待出收据`、`暂无流水`、`红冲/退款暂不出具`。
- `已出收据` 按钮打开历史收据抽屉。
- `待出收据` 按钮打开 Sheet7 模板预览抽屉。
- 无收入流水时不展示待出按钮，只显示原因。

## 收款状态规则

第一阶段按“特殊闭环优先、可证明事实优先”计算：

1. `开票已收款，冲红并退款`
   - 正数票已有收入流水。
   - 存在可证明关联的红字票。
   - 找到对应支出退款流水。
   - 如果退款关系无法证明，不强行算已退款。

2. `开票后冲红`
   - 有可证明正负销项发票关系。
   - 无收入/退款流水。
   - 第一阶段保守识别：金额绝对值匹配，并且备注或号码能关联。

3. `已收款`
   - 有销项发票。
   - 有 active 关联收入流水。
   - 收款合计与发票价税合计在 0.01 内一致。
   - 关联台金额校验可证明匹配。

4. `待收款，已收部分款`
   - 有销项发票。
   - 有 active 关联收入流水。
   - 收款合计小于发票价税合计。

5. `待收款`
   - 有销项发票。
   - 无收入流水。
   - 第一阶段无手动标记能力时作为默认待收状态。

6. `待冲红`
   - 第一阶段只在 Sheet6 规则抽屉中展示为未来手动标记状态。

7. `待处理`
   - 关系存在但不能证明属于上述状态。

## 右侧工作流抽屉

三个按钮均打开右侧抽屉，不使用 `Dialog`，不新增左侧菜单项。

通用要求：

- 使用 MUI `Drawer anchor="right"` 或仓库已有抽屉封装。
- 桌面宽度约 `min(920px, 58vw)`，移动端全屏。
- 抽屉内部滚动，主表不抖动。
- 打开/关闭抽屉不触发表格主数据重取。
- 数据按打开后懒加载，显示 loading/skeleton。
- 工作流抽屉互斥。

### `销项发票收款情况类型设置`

打开 `CollectionStatusRulesDrawer`。

第一阶段只读展示 Sheet6 规则：

- 状态。
- 识别方式：自动、手动、未来。
- 描述。
- 需要的事实：销项发票、流水、红字票、退款流水。
- 关联台匹配要求。
- 优先级。

不展示保存按钮、编辑控件或保存成功状态。

### `已出收据`

打开 `ReceiptHistoryDrawer`。

第一阶段调用历史接口：

- 如果没有正式历史事实源，返回空数组和 `sourceAvailable=false`。
- 前端显示 `暂无系统内历史收据事实`。
- 同时展示当前发票和收入流水摘要。

未来接入历史时，列表字段建议：

- 收据编号。
- 日期。
- 金额。
- 摘要。
- 经手人。
- 状态。
- 来源附件或导出记录。

### `待出收据`

打开 `ReceiptPreviewDrawer`。

规则：

- 单流水：默认用该流水金额生成预览。
- 多流水：先选择本次流水，预览金额随选择变化。
- 无流水：不生成模板，只显示待收金额参考和原因。
- 红冲/退款类：第一阶段阻止自动预览，提示需要先确认红冲/退款关系。

Sheet7 字段映射：

| 模板位置 | 来源 |
| --- | --- |
| 公司抬头 | 固定 `云南溯源科技有限公司`，未来改成公司设置 |
| 日期 | 默认所选收入流水交易日期；无日期用当前日期但标为预览 |
| 兹收到 | 所选流水的对方户名/付款方，银行名称作为辅助 |
| 摘要 | 优先手动关联项目名称，其次发票备注中的项目名称，其次货物或应税劳务名称 |
| 金额 | 所选收入流水金额 |
| 大写金额 | 后端返回 |
| 主管/经手人 | 第一阶段空位或配置默认值，不保存 |

## API 契约

新增 `/api/output-invoice-collections` 分组。

建议接口：

```text
GET /api/output-invoice-collections/rows
GET /api/output-invoice-collections/filter-options
GET /api/output-invoice-collections/invoices/{invoice_id}/detail
GET /api/output-invoice-collections/bank-transactions/{bank_transaction_id}/detail
GET /api/output-invoice-collections/rows/{row_id}/relation-details?kind=bank|red_invoice|receipt
GET /api/output-invoice-collections/status-rules
POST /api/output-invoice-collections/receipt-preview
GET /api/output-invoice-collections/receipts/history?invoice_id=...
```

`rows` 查询参数：

```text
page=1
page_size=50
keyword=...
invoice_date_from=YYYY-MM-DD
invoice_date_to=YYYY-MM-DD
month=YYYY-MM 或 all
filters=<URL encoded JSON array>
sort_field=invoice_date
sort_direction=asc|desc
```

核心 DTO：

```ts
type OutputInvoiceCollectionRow = {
  id: string;
  invoiceId: string;
  invoice: {
    displayNo: string;
    invoiceNo: string;
    invoiceCode: string;
    digitalInvoiceNo: string;
    issueDate: string;
    buyerName: string;
    buyerTaxNo: string;
    totalWithTax: string;
    taxAmount: string;
    taxRate: string;
    taxableItemName: string;
    specificBusinessType: string;
    isPositiveInvoice: string;
  };
  collectionStatus: {
    code: string;
    label: string;
    reason: string;
    pendingAmount: string;
    receivedAmount: string;
    tone: "success" | "warning" | "danger" | "info" | "muted";
    ruleId: string;
  };
  bank: {
    primary: BankSummary | null;
    relationCount: number;
    summaries: BankSummary[];
    receivedTotal: string;
    hasMultiple: boolean;
    detailMode: "none" | "single" | "list";
  };
  receipt: {
    statusCode: "issued" | "pending" | "not_available" | "blocked";
    label: string;
    reason: string;
    availableBankTransactionIds: string[];
  };
  redInvoiceRelation: {
    relatedInvoiceIds: string[];
    relationType: "none" | "red_invoice" | "blue_invoice" | "refund";
    confidence: "confirmed" | "suggested" | "none";
  };
};
```

响应建议包含：

- `rows`
- `pagination`
- `summary`
- `filterConfig`
- `readModelStatus`
- `generatedAt`
- `sourceVersion`

第一阶段 `readModelStatus` 可为 `live_query`。后续升级持久 read model 时保持 API 兼容。

## Read Model 策略

第一阶段不新增持久 read model 表。

原因：

- 本期不写规则、不写收据事实，主要聚合已有销项发票、收入流水和 pair relations。
- 先新增持久 read model 会扩大到 dirty scope、worker、refresh queue、缓存一致性、回滚和监控。
- 当前最重要的是固定状态口径、API 契约、详情抽屉和 Sheet6/Sheet7 工作流边界。

必须预留升级路径：

- 前端只依赖 `/api/output-invoice-collections/*` DTO。
- 服务命名使用 `OutputInvoiceCollectionQueryService`，不暴露实时聚合细节。
- API 可返回 `generatedAt`、`sourceVersion`、`readModelStatus`。
- 后续可新增：
  - `read_model.output_invoice_collection_rows`
  - `read_model.output_invoice_collection_relations`
  - `read_model.output_invoice_receipt_statuses`

触发持久 read model 的条件：

- 生产数据下首屏 P95 超过 1.5-2 秒。
- 筛选/排序需要大量 Python 内存扫描。
- 收据历史或状态规则落库后需要稳定跨页面查询。

## 测试与验收

后端测试：

- 一张销项票一行，多货物明细聚合。
- 已收款、部分收款、待收款、红冲、已收后红冲退款。
- 多笔收入流水时收款合计和主流水选择稳定。
- Sheet6 status rules 只读返回。
- receipt preview 使用所选收入流水金额。
- 无流水或红冲退款阻止待出收据预览。
- 历史收据接口在无事实源时返回空和 `sourceAvailable=false`。
- 无效筛选/排序/详情返回结构化 400/404。

前端测试：

- 左侧菜单和路由。
- 主表大列、小列、无 DataGrid。
- 表格不出现横向滚动约束。
- 小列表头筛选/排序菜单支持全选、清空、升序和降序。
- 每个详情按钮打开对应抽屉。
- 三个工作流按钮打开右侧抽屉。
- 多流水待出收据可选择流水，金额随选择变化。
- Sheet6 规则抽屉只读，无保存按钮。
- 无历史收据事实时显示空状态，不伪造历史。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test
cd web && npm run build
```

如果启动本地服务，还要用浏览器检查：

- 主表不横向滚动。
- 抽屉打开/关闭不触发表格重取。
- 抽屉动效平滑。
- 长文本不重叠、不撑破单元格。
