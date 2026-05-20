# 待找发票页面与银行流水标签统一管理设计

日期：2026-05-20

## 背景

当前系统已经有银行明细、关联台、发票导入、设置页和税金/核销等能力，但“按银行流水追踪是否有发票、缺票时补录发票并关联流水”的工作仍分散在多个入口。

本次需求是在左侧菜单新增 `待找发票` 页面。页面以银行流水为主对象，展示流水、已关联发票和 OA 申请人；无发票时根据业务规则提供补票入口。补录发票必须进入正式发票库存，并同步到关联台、后续发票导入去重、税金和核销相关能力。

同时，支出侧的 `需要开票`、`流水代替发票`、`无需开票` 三类筛选必须基于银行明细页面的标签。当前银行流水标签在前后端有硬编码枚举，不能满足设置页统一维护和实时更新。因此本设计同步升级银行流水标签体系：标签字典统一由设置页管理，银行明细页、待找发票页和筛选映射共享同一事实源。

## 已确认口径

- 新页面左侧菜单名为 `待找发票`。
- 页面顶部左侧有 `支出流水` / `收入流水` 切换。
- 页面主体是一流水一行，使用 MUI 原生 `Table` 组件族，不使用 `DataGrid`，不新增表格依赖。
- 主体是单栏页面中的三大列：
  - 支出流水或收入流水。
  - 进项发票或销项发票。
  - OA 申请人。
- 流水大列下分 2 个展示单元：
  - 对方户名；第二行显示时间 tag。
  - 金额；第二行显示银行 tag，包含银行名称和账户尾号。
- 发票大列下分 3 个展示单元：
  - 发票号码；第二行显示开票日期 tag。
  - 价税合计。
  - 支出侧显示销方名称，收入侧显示购方名称。
- 一笔流水如果关联多张发票，仍只显示一行，在发票列内纵向列出多张发票。
- 支出侧才有 `需要开票`、`流水代替发票`、`无需开票` 三类筛选；收入侧暂时不需要三类筛选。
- 支出侧 `无需开票` 筛选出的无发票流水不显示补票 `+`。
- 支出侧 `需要开票` 和 `流水代替发票` 筛选出的无发票流水显示补票 `+`。
- `流水代替发票` 可以补票，也可以不补票，是否操作由用户决定；系统不要求额外确认动作。
- 收入侧无销项发票时显示补票 `+`。
- 点击 `+` 输入发票信息后，发票必须成为正式发票库存的一部分，后续能在关联台、发票导入去重、税金和核销相关页面中被看到。
- OA 申请人只来自现有关联台关系；没有 OA 关系显示 `—`。不新增银行流水级申请人字段。
- 银行流水标签统一在设置页管理。设置中可新增标签，并与银行明细页面实时共享。

## 目标

- 新增生产级 `待找发票` 页面，作为从银行流水追踪发票关联和补票的工作入口。
- 建立低耦合后端边界：页面是聚合查询视图，写操作落正式事实模型。
- 手工补票创建正式 `Invoice`，并立即建立 bank+invoice pair relation。
- 支出侧筛选基于设置页维护的银行流水标签映射，不写死在前端。
- 银行流水标签从硬编码枚举升级为后端管理的标签字典，银行明细、设置和待找发票共享。
- 所有影响业务事实的操作必须有权限校验、结构化错误、审计和缓存失效。

## 非目标

- 不重做关联台三栏匹配流程。
- 不把“流水代替发票”做成强制确认状态；第一阶段只作为支出筛选分组。
- 不在收入侧启用三类筛选。
- 不新增银行流水级 OA 申请人字段。
- 不引入新的 UI 组件库或表格库。
- 不把待找发票页面的补票信息存成页面私有数据。

## 推荐方案

采用独立 `待找发票` 聚合查询服务 + 正式发票库存写入 + pair relation 关联的方案。

备选方案比较：

- 扩展 `BankDetailsService`：入口少，但会让银行明细服务承担发票库存、OA 关系和关联台职责，耦合过高。
- 扩展关联台 read model：关联状态实时性好，但页面主对象是银行流水，筛选事实源是银行标签；强绑工作台会让设置和银行明细被关联台语义牵住。
- 推荐方案：新增小而清晰的查询和写服务。读取现有事实源，写入现有正式模型，避免复制业务事实。

## 服务边界

新增后端查询服务，建议命名为 `PendingInvoiceQueryService`。

职责：

- 读取银行流水。
- 读取有效银行流水标签。
- 读取支出侧三类筛选映射。
- 读取 active pair relations。
- 读取正式发票库存。
- 读取现有关联台/OA 关系中的申请人。
- 输出页面 DTO，一流水一行。

不负责：

- 不直接修改发票。
- 不直接修改 pair relation。
- 不维护页面私有状态。

新增后端写服务，建议命名为 `PendingInvoiceApplicationService`。

职责：

- 为指定银行流水创建正式发票。
- 校验发票唯一性和方向匹配。
- 创建 bank+invoice active pair relation。
- 保存事实模型和关系快照。
- 触发读模型、搜索缓存、银行关系标签投影、税金/核销相关缓存失效。
- 写审计日志。

依赖：

- `ImportNormalizationService`：正式发票和银行流水事实源。
- `InvoiceIdentityService`：发票唯一性和疑似重复判断。
- `WorkbenchPairRelationService`：bank+invoice 关系事实。
- `BankTransactionCategoryService` 或升级后的标签服务：银行流水有效标签。
- `AppSettingsService`：标签字典和待找发票筛选映射。
- 现有 read model invalidation、search cache clear 和 audit 能力。

## 银行流水标签字典

当前银行流水标签 taxonomy 需要从硬编码枚举升级为设置管理的正式字典。

建议模型：

```text
bank_transaction_tag_definitions
  code
  label
  path
  status
  source
  created_at
  updated_at
```

字段语义：

- `code`：稳定业务标识。历史系统标签继续使用原 code。
- `label`：展示名称。
- `path`：树状路径，例如 `["借入", "个人往来款", "待还款"]`。
- `status`：`active` 或 `archived`。停用标签不再可选，但历史数据继续可解析。
- `source`：`system` 或 `custom`。

迁移规则：

- 现有硬编码标签作为 system seed 初始化。
- 老数据中的标签 code 继续有效。
- 自动识别标签仍可由自动分类服务输出，但展示和筛选通过同一标签字典解析。
- 设置页新增标签时生成 custom code，并立即被银行明细和待找发票 API 返回。
- 改名只影响展示，不改历史 code。
- 停用不删除历史引用。

前后端事实源规则：

- 后端是标签字典唯一事实源。前端不再维护可选择标签的硬编码完整列表。
- 标签字典必须带 `version`，每次新增、改名、停用或映射变更递增。
- 银行明细接口应返回或提供同版本标签字典，银行明细标签选择器从 API 数据渲染。
- 待找发票接口返回当前使用的标签字典版本，便于前端判断是否需要刷新。
- 现有前端 `categoryOptions.ts` 只能保留为迁移兜底和测试 fixture，不能继续作为生产标签事实源。
- 现有后端 `BANK_TRANSACTION_CATEGORY_*` 常量在迁移后只能作为 system seed 和自动识别兼容表，不再作为设置和页面的唯一可选项来源。

实时同步规则：

- 设置页保存标签或映射成功后，前端必须广播一个应用内事件，例如 `finops:bank-transaction-tags-updated`，事件包含新 `version`。
- 已打开的银行明细页收到事件后重新拉取标签字典、刷新标签选择器和当前页分类计数。
- 已打开的待找发票页收到事件后重新拉取筛选映射和当前查询结果。
- 同浏览器多标签页场景应通过 `BroadcastChannel` 或现有页面状态广播工具同步；不支持时至少在窗口 focus 时比对 version 并刷新。
- 后端设置保存后必须清理依赖标签字典或筛选映射的服务端缓存。

## 待找发票筛选映射

设置页新增 `pending_invoice_tag_groups`。

固定三组：

```text
requires_invoice              需要开票
bank_statement_as_invoice     流水代替发票
no_invoice_required           无需开票
```

每组维护一组银行流水标签 code。

校验规则：

- 分组只能引用存在且 active 的标签。
- 同一标签第一阶段不允许同时出现在多个分组中。
- 停用标签前，如果仍被分组引用，应提示先移除映射。
- 保存设置后，应清理或失效待找发票相关缓存。

支出侧补票入口规则：

| 支出筛选分组 | 无发票时是否显示 `+` |
| --- | --- |
| `需要开票` | 显示 |
| `流水代替发票` | 显示 |
| `无需开票` | 不显示 |
| `全部` 或未命中分组 | 显示 |

收入侧不使用三类筛选。收入流水无销项发票时显示 `+`。

## API 契约

新增 `/api/pending-invoices` 分组。

查询接口：

```text
GET /api/pending-invoices/rows
```

查询参数：

```text
direction=expense|income
filter=all|requires_invoice|bank_statement_as_invoice|no_invoice_required
date_from=YYYY-MM-DD
date_to=YYYY-MM-DD
keyword=...
page=1
page_size=50
```

规则：

- `direction` 必填。
- 支出侧支持三类筛选。
- 收入侧如果传入三类筛选，返回 `400`，避免前端误用。
- 后端负责关键词、分页和筛选。

响应建议：

```text
{
  "direction": "expense",
  "filter": "requires_invoice",
  "rows": [
    {
      "id": "txn_0001",
      "bank_transaction": {
        "id": "txn_0001",
        "counterparty_name": "...",
        "trade_time": "2026-05-20",
        "amount": "1000.00",
        "bank_name": "工商银行",
        "account_last4": "1234",
        "effective_tag_code": "fee",
        "effective_tag_label": "手续费"
      },
      "invoices": [
        {
          "id": "inv_0001",
          "invoice_no": "...",
          "digital_invoice_no": "...",
          "issue_date": "2026-05-20",
          "total_with_tax": "1000.00",
          "seller_name": "...",
          "buyer_name": "...",
          "invoice_type": "input"
        }
      ],
      "oa_applicant": "张三",
      "can_create_invoice": true,
      "relation_case_ids": ["case_..."]
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total": 120
  },
  "summary": {
    "total_rows": 120,
    "missing_invoice_rows": 18,
    "create_invoice_available_rows": 15
  }
}
```

手工补票采用 preview / confirm 两段式接口。补票会创建正式发票并改变关联台、税金和核销可见性，属于高影响动作，不能只靠前端弹窗直接写入。

预览接口：

```text
POST /api/pending-invoices/manual-invoices/preview
```

入参与确认接口一致，但不写任何业务事实。

响应建议：

```text
{
  "preview_id": "pending_invoice_preview_...",
  "request_key": "manual-pending-invoice:txn_0001:...",
  "can_confirm": true,
  "target_invoice_type": "input",
  "bank_transaction_summary": {
    "id": "txn_0001",
    "direction": "expense",
    "counterparty_name": "...",
    "trade_time": "2026-05-20",
    "amount": "1000.00"
  },
  "invoice_identity": {
    "source_unique_key": "...",
    "data_fingerprint": "..."
  },
  "duplicate_check": {
    "status": "clear",
    "matched_invoice_id": null,
    "message": ""
  },
  "relation_impact": {
    "relation_mode": "pending_invoice_manual_invoice",
    "affected_months": ["2026-05"]
  },
  "warnings": []
}
```

确认接口：

```text
POST /api/pending-invoices/manual-invoices
```

入参建议：

```text
{
  "preview_id": "pending_invoice_preview_...",
  "request_id": "client-generated-uuid",
  "bank_transaction_id": "txn_0001",
  "invoice_no": "...",
  "digital_invoice_no": "...",
  "invoice_code": "...",
  "issue_date": "2026-05-20",
  "total_with_tax": "1000.00",
  "tax_amount": "60.00",
  "tax_rate": "6%",
  "seller_name": "...",
  "seller_tax_no": "...",
  "buyer_name": "...",
  "buyer_tax_no": "...",
  "remark": "..."
}
```

后端根据流水方向固定发票类型：

- 支出流水创建进项票。
- 收入流水创建销项票。

确认规则：

- `preview_id` 必须来自同一套后端校验规则，并在短 TTL 内有效。
- `request_id` 必填，用于幂等。前端每次打开补票弹窗生成一次稳定 id，重试沿用同一个 id。
- 后端同时用 `request_id` 和确定性 `request_key` 去重。`request_key` 至少包含银行流水 id、目标发票类型和发票 identity，避免网络重试创建重复发票。
- 确认时必须重新执行 preview 校验，不能信任前端或过期 preview。

响应建议：

```text
{
  "invoice_id": "inv_0002",
  "relation_case_id": "case_pending_invoice_...",
  "affected_transaction_ids": ["txn_0001"],
  "affected_invoice_ids": ["inv_0002"],
  "affected_months": ["2026-05"],
  "row": { "...": "updated pending invoice row dto" }
}
```

设置 API 扩展现有 `/api/workbench/settings`：

- 返回 `bank_transaction_tags`。
- 返回 `pending_invoice_tag_groups`。
- 保存时校验标签字典和筛选映射。

## 前端页面设计

新增路由：

```text
/pending-invoices
```

左侧菜单新增 `待找发票`，放在财务业务分组中，建议靠近 `银行明细` 和 `关联台`。

页面组件建议：

- `PendingInvoicesPage`
- `PendingInvoicesTable`
- `PendingInvoiceFilterMenu`
- `ManualInvoiceDialog`

顶部工具区：

- `ToggleButtonGroup`：`支出流水`、`收入流水`。
- 支出模式显示三类筛选菜单：
  - `全部`
  - `需要开票`
  - `流水代替发票`
  - `无需开票`
- 收入模式隐藏三类筛选菜单。
- 可包含关键词搜索、日期范围和刷新按钮，均使用 MUI 原生组件。

主体表格：

- 使用 MUI `Table`、`TableHead`、`TableBody`、`TableRow`、`TableCell`、`TablePagination`。
- 不使用 `DataGrid`。
- 三个大列：
  - `支出流水` 或 `收入流水`
  - `进项发票` 或 `销项发票`
  - `OA申请人`

流水列内部：

- 第一小列：对方户名；第二行 `Chip` 显示时间。
- 第二小列：金额；第二行 `Chip` 显示银行名称和账户尾号。

发票列内部：

- 有发票时，纵向列出所有已关联发票。
- 每张发票三小列：
  - 发票号码；第二行 `Chip` 显示开票日期。
  - 价税合计。
  - 支出侧销方名称；收入侧购方名称。
- 无发票且 `can_create_invoice=true` 时显示 MUI `IconButton` + `AddIcon`。
- 无发票且不可补票时显示 `—` 或简短状态文本。

补票弹窗：

- 使用 MUI `Dialog`、`DialogTitle`、`DialogContent`、`DialogActions`、`TextField`、`DatePicker`。
- 支出模式固定进项发票；收入模式固定销项发票。
- 必填：
  - 发票号码或数电发票号码。
  - 开票日期。
  - 价税合计。
  - 支出侧销方名称。
  - 收入侧购方名称。
- 可选：
  - 发票代码。
  - 税额。
  - 税率。
  - 销方税号。
  - 购方税号。
  - 备注。
- 保存中禁用提交。
- 成功后局部更新当前行。
- 错误展示后端业务消息。
- 提交前必须先调用 preview 接口，显示后端返回的银行流水摘要、目标发票类型、发票 identity、影响月份和重复检查结果。
- 用户在弹窗内确认后才调用写入接口。

## 设置页设计

设置页新增两个 section。

### 银行流水标签

职责：

- 展示系统标签和自定义标签。
- 新增自定义标签。
- 改名。
- 停用。

交互：

- 使用 MUI `List`、`Collapse`、`TextField`、`IconButton`、`Chip`。
- 如果项目未安装 MUI X Tree View，不新增依赖，用 `List` + 缩进 + `Collapse` 实现树状感。
- 停用标签时，如果仍被筛选映射引用，提示先移除映射。

### 待找发票筛选

职责：

- 管理三类支出筛选与银行流水标签的映射。

交互：

- 双栏结构。
- 左栏固定三项：
  - `需要开票`
  - `流水代替发票`
  - `无需开票`
- 右栏展示当前分组绑定的标签项。
- 右上角提供 `+` 和 `-` IconButton。
- `+` 支持从已有标签选择，也支持新建标签后加入当前分组。
- 所有标签变更保存后，银行明细页面和待找发票页面重新读取同一标签字典。

## 写入一致性

手工补票必须由一个后端应用服务动作完成，前端不能拆成“先建发票、再建关联”的多个业务调用。

流程：

1. 校验当前用户有写权限。
2. 校验银行流水存在。
3. 根据流水方向确定目标发票类型。
4. 校验必填字段。
5. 使用 `InvoiceIdentityService` 计算 canonical key 和 fingerprint。
6. 如果命中已存在正式发票，返回结构化冲突，不静默合并。
7. 记录或读取补票命令日志，使用 `request_id` 和 `request_key` 保证重复提交幂等。
8. 通过正式发票库存的 canonical 创建路径创建 `Invoice`。
9. 创建 active pair relation：
   - `row_ids`: `[bank_transaction_id, invoice_id]`
   - `row_types`: `["bank", "invoice"]`
   - `relation_mode`: `pending_invoice_manual_invoice`
10. 保存 import snapshot 和 pair relation snapshot。
11. 将命令日志标记为 completed，记录 invoice id、relation case id 和 affected months。
12. 失效相关 read models 和缓存。
13. 写审计日志。

正式发票库存创建路径：

- 第一阶段必须复用 `ImportNormalizationService.preview_import()` 和 `confirm_import()` 的发票标准化、identity、去重和 source link 逻辑，而不是绕开服务直接构造页面私有 `Invoice`。
- 支出流水使用 `BatchType.INPUT_INVOICE`，收入流水使用 `BatchType.OUTPUT_INVOICE`。
- `source_name` 使用稳定值，例如 `pending_invoice_manual_entry`。
- 创建出的发票必须包含或补齐以下字段：
  - `invoice_type`
  - `invoice_no` 或 `digital_invoice_no`
  - `invoice_date`，由入参 `issue_date` 映射
  - `amount` 和 `signed_amount`
  - `total_with_tax`
  - `seller_name`
  - `buyer_name`
  - `source_unique_key`
  - `data_fingerprint`
  - `source_batch_id`
  - `source_links`
- `source_links.source_type` 继续使用现有正式手工导入来源 `manual_invoice_import`，并在 link 中补充或通过审计记录关联 `pending_invoice_manual_entry`、`bank_transaction_id` 和 `request_key`。这样现有 `InvoiceInventoryStatsService` 可继续把它识别为手工导入发票。
- 如果 `preview_import()` 返回 `DUPLICATE_SKIPPED` 或 `SUSPECTED_DUPLICATE`，补票动作返回 `409 duplicate_invoice`，不自动关联已有发票。
- 补票成功后，新发票必须能被现有 `list_invoices()`、工作台发票行构建、税金/核销查询和后续导入去重读取到。

原子性与恢复：

- Mongo 生产模式下，补票命令日志、正式发票写入、pair relation 写入和审计应在同一个 app Mongo 事务或等效条件写入单元中完成。
- 如果当前部署不支持跨集合事务，必须实现可恢复的命令日志：
  - `pending_invoice_manual_invoice_commands` 记录 `request_id`、`request_key`、状态、invoice id、relation case id、错误和时间戳。
  - 状态至少包括 `started`、`invoice_created`、`relation_created`、`completed`、`failed_recoverable`、`failed_terminal`。
  - 重试同一 `request_id` 时，已 completed 返回原结果；卡在 `invoice_created` 时补建 relation；卡在 `relation_created` 时补做缓存失效和审计完成标记。
  - 发现有 `manual_invoice_import` source link 且带同一 `request_key` 但缺 relation 时，恢复逻辑应补建 relation 或标记为需要人工修复，不能创建第二张发票。
- 本地 state 文件模式只能在单进程锁内执行，并在失败时通过命令日志恢复；不能宣称具备生产级并发保证。
- 测试必须覆盖重复提交、发票已创建但 relation 保存失败、relation 已创建但响应失败后的重试行为。

如果后续需要支持“关联已有发票”，应新增独立动作，不混入本次 `+` 新建发票流程。

## 缓存与联动

补票成功后必须影响：

- 待找发票当前行刷新。
- 关联台 read model 失效或局部刷新。
- 银行明细关系标签投影更新，使 `有发票` tag 实时变化。
- 搜索缓存清理。
- 税金和核销相关读模型按现有机制刷新或标记脏。

设置变更后必须影响：

- 银行明细标签选项。
- 待找发票筛选结果。
- 相关页面的前端缓存或 session 状态。

## 权限与审计

查询接口沿用当前系统可访问权限。

写接口要求全操作权限。只读导出用户：

- 可以查看待找发票页面。
- 不能看到或不能触发补票保存动作。
- 后端仍必须返回 `403`，不能只依赖前端隐藏按钮。

审计事件至少记录：

- 操作人。
- 操作时间。
- 操作类型。
- 银行流水 id。
- 新发票 id。
- relation case id。
- 输入摘要。
- 影响月份。

标签和筛选映射变更也应记录审计，至少包含变更人、变更前后摘要和影响范围。

## 错误处理

待找发票查询：

- `400 invalid_direction`：方向不是 `expense` 或 `income`。
- `400 invalid_filter_for_income`：收入侧传入支出三类筛选。
- 空结果返回空数组和分页信息。

手工补票：

- `403 permission_denied`：无写权限。
- `404 bank_transaction_not_found`：流水不存在。
- `400 invalid_invoice_payload`：必填字段缺失或金额非法。
- `400 invalid_direction_invoice_type`：方向和发票类型不匹配。
- `409 duplicate_invoice`：发票 canonical key 或 fingerprint 命中已有发票。
- `409 relation_conflict`：该流水或发票已有冲突 active relation。
- `503 persistence_failed`：状态保存失败。

设置保存：

- `400 invalid_bank_transaction_tag`：标签字段非法。
- `400 unknown_tag_code`：筛选映射引用不存在标签。
- `400 archived_tag_referenced`：引用已停用标签。
- `400 duplicate_pending_invoice_group_mapping`：同一标签被映射到多个分组。

## 测试计划

后端单元测试：

- 银行流水标签字典初始化包含现有 system 标签。
- 自定义标签新增、改名、停用和旧 code 兼容。
- 标签字典 version 在新增、改名、停用和映射变更时递增。
- 银行明细接口使用服务端标签字典渲染可选项，不依赖前端硬编码列表。
- 筛选映射校验：不存在标签、停用标签、重复分组引用。
- 待找发票查询：支出/收入切换。
- 待找发票查询：支出三类筛选。
- 待找发票查询：收入侧不接受三类筛选。
- 待找发票查询：一笔流水多张发票仍返回一行。
- `can_create_invoice` 规则：
  - 支出 `无需开票` 无发票为 false。
  - 支出 `需要开票` 无发票为 true。
  - 支出 `流水代替发票` 无发票为 true。
  - 收入无发票为 true。
- 手工补票 preview 返回目标发票类型、发票 identity、重复检查和影响月份。
- 手工补票 confirm 复用 preview 校验规则。
- 手工补票创建正式发票。
- 手工补票通过 `ImportNormalizationService.preview_import()` 和 `confirm_import()` 进入正式库存。
- 手工补票创建 bank+invoice pair relation。
- 手工补票重复发票返回冲突。
- 手工补票重复提交同一 `request_id` 返回同一结果，不创建第二张发票或第二条 relation。
- 手工补票在发票已创建但 relation 保存失败后重试可恢复。
- 手工补票创建的发票能被现有 invoice inventory、工作台发票查询、税金/核销相关查询读取。
- 手工补票无权限返回 `403`。
- 手工补票后缓存失效和 affected months 返回正确。

前端测试：

- 左菜单出现 `待找发票` 并路由到新页面。
- 支出/收入 `ToggleButtonGroup` 切换列标题和 API 参数。
- 页面主体使用 MUI Table 结构渲染三大列。
- 支出侧显示筛选菜单，收入侧隐藏。
- 支出 `无需开票` 无发票行不显示 `+`。
- 支出 `需要开票` 和 `流水代替发票` 无发票行显示 `+`。
- 收入无发票行显示 `+`。
- 多张发票在同一行发票列纵向展示。
- 补票弹窗必填校验和提交 payload 正确。
- 补票弹窗先展示 preview 摘要，再允许用户确认写入。
- 设置页能新增银行流水标签并保存。
- 设置页能维护三类筛选映射。
- 设置页保存新标签后，银行明细页面无需整页 reload 即可重新拉取并显示新标签。
- 设置页保存筛选映射后，待找发票页面无需整页 reload 即可刷新筛选结果。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test
cd web && npm run build
```

## 实施顺序建议

1. 先落标签字典和设置 API 扩展，保证银行明细仍兼容旧标签。
2. 再落待找发票查询服务和只读页面。
3. 再落手工补票写服务和弹窗。
4. 最后补联动刷新、审计和完整回归测试。

这样可以把高风险的标签体系迁移与补票写入分开验证，避免一次性改动过大。
