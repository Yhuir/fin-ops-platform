# 银行明细自动标签规则管理设计

## 背景

银行明细页面当前展示系统自动分类，并把自动分类作为免 OA 批次、待找发票、往来款、关联台等下游能力的输入。现有产品文档仍写着“银行明细标签只能由 app 自动分配，页面不提供人工分类选择、保存或清空入口”。本轮需求改变的是“自动规则的管理权”，不是恢复逐条流水人工打标签。

目标是让用户在银行明细页面管理自动标签和文本命中规则，同时保持生产级一致性：

- 标签字典只有一个事实源。
- 下游只引用稳定 `tag_code`。
- 标签改名后系统内当前页面和后续导出统一显示新名称。
- 规则保存不在请求线程内重算全量历史流水。
- 银行字段差异由后端语义层处理，用户不直接面对各银行原始列名。

## 范围

本设计覆盖：

- 银行明细页面右上角新增 `自动标签规则` 按钮。
- 右侧滑动抽屉管理自动标签、命中规则、优先级和停用状态。
- 后端标签字典和自动规则模型。
- 自动命中语义字段模型。
- 保存 API、权限、审计、并发冲突和下游刷新。
- 前后端测试、文档和验收标准。

本设计不覆盖：

- 恢复逐条银行流水人工分类。
- 允许用户修改 `内部往来款` 的跨流水配对规则。
- 正则表达式、复杂 AND/OR 条件编辑器。
- 标签物理删除。
- 同步全量重算历史流水。
- 跨设备 WebSocket/SSE 秒级推送。

## 核心口径

### 管理对象

本抽屉管理“会参与银行明细自动命中的标签规则”，不是把历史兼容标签、旧人工分类 taxonomy 或所有设置页标签一次性改造成自动规则。

首版应纳入规则管理的默认标签：

- 手续费。
- 工资。
- 过节费。
- 奖金。
- 税款。
- 代理国库税收收缴。
- 社保款。
- 用户新增的自动标签。

`内部往来款` 作为系统固定行展示，但不进入用户可编辑规则。其他历史兼容标签如果没有自动规则，不应因为本次改造被强制要求填写规则，也不应出现在本抽屉中。实现可以通过 `rules` 是否存在、`auto_rule_enabled` 等等价后端字段区分自动规则标签，但必须保持对现有 `bank_transaction_tags` 读取的向后兼容。

### 标签身份

标签 `code` 是系统内部稳定身份，创建后不可修改。用户只编辑中文标签名和规则。

示例：

```text
code: salary
label: 人员薪酬
```

所有下游业务事实、规则引用、read model、关联台状态都引用 `tag_code`。页面展示和后续导出统一从标签字典解析当前 `label`。用户把“工资”改名为“人员薪酬”后，银行明细、待找发票、免 OA 批次、往来款、关联台等系统内当前页面和后续导出都显示“人员薪酬”。已下载到本地的历史 Excel 文件不会变化。

### 字段命名兼容

本文中的 `tag_code` 是产品语义，指标签字典里的稳定 `code`。实现时不得为了这个术语新增一套平行字段或大规模改名。

现有字段继续沿用：

- 银行明细 DTO/read model 中的 `category_code`、`auto_category_code`、`effective_category_code` 仍表示标签字典 `code`。
- 待找发票规则中的 `tag_codes` 仍表示标签字典 `code`。
- 下游关系、批次或展示 payload 如果已有 `category_code`、`batch_type`、`rule_code` 等字段，应优先复用现有稳定 code 字段，并在展示层用标签字典解析 label。

只有在实现阶段明确需要新增字段且已有字段无法表达当前语义时，才允许增加新字段；不得仅因为规格文字使用 `tag_code` 就迁移所有公共契约。

### 内部往来款

`内部往来款` 是系统内置跨流水配对规则，不进入用户可编辑文本规则体系。

- 在可用区第一行展示。
- 显示 `优先级 0`。
- 标签名为 `内部往来款`。
- 灰色不可交互。
- 不展示规则解释。
- 不可拖拽、不可改名、不可停用。
- 后端仍按现有金额、方向、账户、时间窗口和多解冲突规则优先识别。

### 用户规则优先级

除 `内部往来款` 外，可用标签按优先级从上到下执行，先命中先返回。UI 显示为：

- `优先级 1`
- `优先级 2`
- `优先级 3`

后端可保存为连续排序值，例如 `10, 20, 30`，但 API 返回给前端时必须能稳定恢复列表顺序。保存时后端按提交顺序重写可用标签优先级，避免重复、小数和并发排序漂移。

## 统一语义字段

用户规则不能绑定各银行原始列名。后端必须先把不同银行的文本字段映射到稳定语义字段，再执行规则。

| 字段 ID | UI 名称 | 说明 |
| --- | --- | --- |
| `counterparty_name` | 对方户名 | 所有银行统一字段 |
| `purpose_text` | 用途/交易用途 | 由银行导入映射得到，缺失为空 |
| `summary_text` | 摘要 | 由银行导入映射得到，缺失为空 |
| `note_text` | 备注/附言/客户附言 | 由银行导入映射得到，缺失为空 |
| `detail_text` | 其他明细 | 银行明细扩展文本 |
| `all_text` | 全部文本 | 后端计算合集 |

展示字段不能乱补值，但匹配字段可以进入统一文本合集。例如民生没有“摘要”，页面摘要列仍显示 `-`；民生“客户附言”进入 `note_text` 和 `all_text`，规则仍可命中。

自动命中证据应可追溯。后端至少能记录或返回：

- 命中的标签 code/label。
- 命中的规则 ID 或规则版本。
- 命中的条件类型：精确、包含或排除。
- 命中的语义字段，例如 `note_text`。
- 实际银行原始字段名，例如“客户附言”。
- 命中的字样。

首版证据字段统一命名为 `auto_category_evidence`。它可以进入银行明细行 payload/read model，也可以作为内部调试和审计字段保留；如果对外返回，结构固定为：

```json
{
  "tag_code": "salary",
  "tag_label": "人员薪酬",
  "rule_code": "salary",
  "rule_version": 12,
  "condition_type": "contains",
  "semantic_field": "note_text",
  "semantic_field_label": "备注/附言/客户附言",
  "raw_field_key": "customer_note",
  "raw_field_label": "客户附言",
  "matched_text": "工资"
}
```

`raw_field_key`、`raw_field_label` 在导入数据无法可靠提供时可以为 `null`，但 `semantic_field`、`condition_type` 和 `matched_text` 必须可追溯。

## 标签和规则模型

标签字典扩展为自动规则事实源：

```json
{
  "version": 12,
  "definitions": [
    {
      "code": "salary",
      "label": "人员薪酬",
      "status": "active",
      "source": "system",
      "priority": 10,
      "rules": {
        "match_fields": ["summary_text", "purpose_text", "note_text", "detail_text"],
        "exact": [],
        "contains": ["工资", "薪酬"],
        "excludes": ["社保代扣"]
      }
    }
  ]
}
```

字段口径：

- `code`：稳定 ID，系统内置或后端生成。
- `label`：用户可修改的显示名。
- `status`：`active` 或 `archived`。
- `source`：`system` 或 `custom`。
- `priority`：可用标签排序。
- `rules.match_fields`：统一语义字段集合。
- `rules.exact`：精确命中字样。
- `rules.contains`：包含字样。
- `rules.excludes`：不包含字样。

规则逻辑：

```text
(任一 exact 命中 OR 任一 contains 命中) AND 没有 excludes 命中
```

匹配语义：

- `exact`：任一选中语义字段的完整标准化文本等于任一 exact 字样。
- `contains`：任一选中语义字段包含任一 contains 字样。
- `excludes`：任一选中语义字段包含任一 excludes 字样时排除该标签。
- 标准化至少包括转字符串、去前后空格；不做正则、不做拼音、不做模糊分词。

约束：

- `exact`、`contains`、`excludes` 都允许为空。
- active 可编辑标签的 `exact` 和 `contains` 不能同时为空。
- active 可编辑标签的 `excludes` 不能单独构成规则。
- active 可编辑标签的 `match_fields` 不能为空；新增标签默认使用 `all_text`，用户可以收窄到具体语义字段。
- archived 标签可以保留不完整历史规则，但重新启用前必须满足 active 校验。
- 条件字样去前后空格、去重，空行忽略。
- `match_fields` 必须来自字段白名单。
- 已停用标签不参与匹配。
- 首版不支持正则、不支持复杂 AND/OR 组合、不支持用户填写或修改 code。

### 默认规则迁移

现有硬编码文本规则必须迁入标签规则字典或由等价适配层读取成同一规则模型，保存后不再维护第二套文本规则事实源。默认规则应保持现有口径：

| 标签 | 默认正向条件 | 默认排除条件 | 默认字段范围 |
| --- | --- | --- | --- |
| 手续费 | 包含：手续费、短信服务费 | 无 | 对方户名、摘要、备注/附言/客户附言 |
| 过节费 | 包含：过节费 | 无 | 摘要、用途/交易用途、备注/附言/客户附言、其他明细 |
| 工资 | 包含：工资 | 无 | 摘要、用途/交易用途、备注/附言/客户附言、其他明细 |
| 奖金 | 包含：奖金、绩效奖、年终奖 | 无 | 摘要、用途/交易用途、备注/附言/客户附言、其他明细 |
| 代理国库税收收缴 | 包含：代理国库税收收缴、国库税收收缴 | 无 | 摘要、用途/交易用途、备注/附言/客户附言、其他明细 |
| 社保款 | 包含：社保款、社保费、社会保险费、缴纳社保 | 无 | 摘要、用途/交易用途、备注/附言/客户附言、其他明细 |
| 税款 | 包含：税款、缴纳税款、电子缴税、税库银、税务局、完税 | 包含：社保及税款、社保和税款、社保税款、社保、税款 | 摘要、用途/交易用途、备注/附言/客户附言、其他明细 |

迁移后必须继续满足原产品口径：普通“服务费”不自动归为手续费；用途或明细扩展字段只含“手续费”也不自动归为手续费，除非用户后来主动修改该规则。

## 抽屉交互

银行明细页面右上角增加按钮：`自动标签规则`。点击后打开右侧抽屉：

- `anchor="right"`。
- 桌面宽度 `60vw`。
- 小屏 `100vw`。
- 最大宽度不超过视口。
- 抽屉内部滚动，页面主体不横向挤压。
- 关闭前如果有未保存修改，弹出确认。

抽屉顶部：

- 标题：`自动标签规则`。
- 副标题显示当前规则版本和刷新状态。
- 左上角切换按钮：`可用` / `停用`。
- 右上角关闭按钮。
- 固定操作区：`新增标签`、`保存`。

### 可用区

- 默认进入可用区。
- 第一行固定显示 `优先级 0 内部往来款 系统内置`，灰色不可交互。
- 其他标签显示 `优先级 1`、`优先级 2`。
- 每行支持改名、编辑规则、上移/下移或拖拽排序。
- 每行有“停用”操作。
- 排序后 UI 立即重排优先级文案，保存前只在本地生效。
- 新增标签默认追加到可用区末尾。
- 新增标签规则为空时显示校验错误，不能保存。

### 停用区

- 通过 `可用 / 停用` 切换进入。
- 只显示停用标签。
- 不显示优先级，显示 `已停用`。
- 显示标签名和规则摘要。
- 可重新启用。
- 重新启用后进入可用区末尾，保存后获得最后优先级。
- 停用区为空时显示空状态。

### 规则编辑

每个标签规则可编辑：

- 匹配字段。
- `精确命中字样`。
- `包含字样`。
- `不包含字样`。

字样输入可使用三组多行输入或 token 输入。保存前必须清理空行和重复项。规则摘要示例：

```text
摘要/用途包含：工资、薪酬；排除：社保代扣
```

## API 设计

新增银行明细标签规则 API：

```text
GET /api/bank-details/auto-tag-rules
PUT /api/bank-details/auto-tag-rules
```

不把本能力塞回通用设置页保存接口；通用设置页仍可读取同一标签字典，但规则管理入口在银行明细页面。

### GET 响应

返回：

- 当前 `version`。
- 固定系统行 `内部往来款`。
- 可用标签列表。
- 停用标签列表。
- 规则字段元数据。
- 当前用户权限，例如 `can_save`。

HTTP status：`200 OK`。

Canonical response：

```json
{
  "version": 12,
  "system_rule": {
    "code": "internal_transfer",
    "label": "内部往来款",
    "priority_label": "优先级 0",
    "source": "system",
    "status": "active",
    "editable": false,
    "archivable": false,
    "sortable": false
  },
  "active_rules": [
    {
      "code": "salary",
      "label": "人员薪酬",
      "status": "active",
      "source": "system",
      "priority": 10,
      "priority_label": "优先级 1",
      "rules": {
        "match_fields": ["summary_text", "purpose_text", "note_text", "detail_text"],
        "exact": [],
        "contains": ["工资", "薪酬"],
        "excludes": ["社保代扣"]
      },
      "rule_summary": "摘要/用途/备注/其他明细包含：工资、薪酬；排除：社保代扣",
      "editable": true,
      "archivable": true,
      "sortable": true
    }
  ],
  "archived_rules": [
    {
      "code": "legacy_fee",
      "label": "旧手续费",
      "status": "archived",
      "source": "custom",
      "rules": {
        "match_fields": ["all_text"],
        "exact": [],
        "contains": [],
        "excludes": []
      },
      "rule_summary": "已停用",
      "editable": true,
      "archivable": false,
      "sortable": false
    }
  ],
  "field_options": [
    { "value": "counterparty_name", "label": "对方户名" },
    { "value": "purpose_text", "label": "用途/交易用途" },
    { "value": "summary_text", "label": "摘要" },
    { "value": "note_text", "label": "备注/附言/客户附言" },
    { "value": "detail_text", "label": "其他明细" },
    { "value": "all_text", "label": "全部文本" }
  ],
  "permissions": {
    "can_save": true
  },
  "read_model_status": "fresh"
}
```

`read_model_status` 只在能从现有生命周期状态可靠获得时返回；不能可靠获得时省略，不要伪造。

### PUT 请求

提交整份规则配置：

- `expected_version`。
- active 标签顺序。
- archived 标签。
- 每个标签的 `code`、`label`、`status`、`priority`、`rules`。
- 新增标签不带 `code`，由后端生成并返回。

HTTP status：

- 保存成功：`200 OK`，返回与 GET 相同的规范化 payload。
- 权限不足：`403 Forbidden`。
- 版本冲突：`409 Conflict`。
- 请求结构、字段或规则校验失败：`400 Bad Request`。

Canonical request：

```json
{
  "expected_version": 12,
  "active_rules": [
    {
      "code": "salary",
      "label": "人员薪酬",
      "rules": {
        "match_fields": ["summary_text", "purpose_text", "note_text", "detail_text"],
        "exact": [],
        "contains": ["工资", "薪酬"],
        "excludes": ["社保代扣"]
      }
    },
    {
      "label": "银行手续费",
      "rules": {
        "match_fields": ["counterparty_name", "summary_text", "note_text"],
        "exact": [],
        "contains": ["手续费"],
        "excludes": []
      }
    }
  ],
  "archived_rules": [
    {
      "code": "old_bonus",
      "label": "旧奖金",
      "rules": {
        "match_fields": ["all_text"],
        "exact": [],
        "contains": [],
        "excludes": []
      }
    }
  ]
}
```

PUT 不接受 `system_rule`。如果请求试图提交、修改或停用 `internal_transfer`，返回 `400 invalid_bank_auto_tag_rules_request`。

Canonical error：

```json
{
  "error": "invalid_auto_tag_rule",
  "message": "自动标签规则校验失败。",
  "field_errors": [
    {
      "path": "active_rules[1].rules.contains",
      "message": "精确命中字样和包含字样不能同时为空。"
    }
  ],
  "references": []
}
```

下游引用阻止停用时：

```json
{
  "error": "bank_transaction_tag_in_use_by_pending_invoice_filter",
  "message": "该银行明细标签仍被下游规则引用，请先解除引用后再停用。",
  "field_errors": [],
  "references": [
    {
      "domain": "pending_invoice_tag_groups",
      "label": "待找发票规则：无需开票",
      "tag_code": "salary"
    }
  ]
}
```

### 后端保存要求

- 校验权限；前端隐藏按钮不是安全边界。
- 校验 `expected_version`；冲突返回 `bank_transaction_tags_version_conflict`。
- 校验标签名非空；同一状态下标签名不能重复。
- 校验规则至少有一个正向条件。
- 校验 `match_fields` 白名单。
- 校验 `excludes` 不能单独存在。
- 校验 `内部往来款` 不在可编辑 payload 中。
- 停用前检查下游配置引用。如果被待找发票规则等配置引用，返回引用位置并拒绝保存。
- 允许停用仅历史流水命中过、但未被下游配置引用的标签。
- 保存成功递增标签版本。
- 保存成功写审计。
- 保存成功后返回新版本和规范化后的规则列表。

审计至少记录：

- actor。
- 旧版本和新版本。
- 新增标签。
- 改名。
- 停用。
- 启用。
- 排序变化。
- 规则变化摘要。

## 刷新与一致性

规则保存不在 API 热路径同步全量重算历史流水。保存成功后：

- 执行派生数据生命周期事件 `bank_auto_tag_rules_changed`，`scope_keys=["all"]`，`reason="bank_auto_tag_rules_changed"`。
- `bank_auto_tag_rules_changed` 至少覆盖这些派生域：`bank_detail_read_model`、`workbench_read_model`、`workbench_candidate_matches`、`workbench_matching_dirty_scopes`、`pending_invoice_read_model`、`cost_statistics_read_model`、`search_cache`。
- `bank_detail_read_model`：enqueue `scope_type="bank_detail"`、`scope_key="all"`，由既有 bank detail refresh fan-out 到月份 shard。
- `pending_invoice_read_model`：调用既有 `_invalidate_pending_invoice_read_model_scopes(reason="bank_auto_tag_rules_changed")`，覆盖 `expense:all`、`expense:requires_invoice`、`expense:bank_statement_as_invoice`、`expense:no_invoice_required`、`income:all`。
- `workbench_read_model`：失效或 enqueue `scope_key="all"`，不能在 PUT 请求内同步重建关联台 read model。
- `workbench_matching_dirty_scopes`：标记所有月份或可枚举月份 dirty；如果只能安全表达全量，先使用 `all`/已知月份展开，不做请求内匹配重建。
- `cost_statistics_read_model` 与 `search_cache`：按现有生命周期 executor 失效或 enqueue。
- 免 OA 批次和往来款如果仍是实时服务读取标签结果，不新增平行 dirty 表；如果实现时发现存在持久缓存或 read model，必须在同一生命周期事件中清理或标记 dirty。
- 页面显示“规则已保存，银行明细正在刷新”。
- 后台 worker 按月份或 `all` scope 重算。
- 刷新完成后页面通过已有 domain event、版本同步或页面聚焦重新拉取。

测试必须证明 PUT 只保存规则和 enqueue/mark dirty，不调用银行流水全量扫描、workbench all payload 重建或同步批次/历史重算。

标签元数据要实时同步到下游读取：

- 银行明细标签字典是唯一事实源。
- 待找发票规则只保存 `tag_code`，不保存标签名副本。
- 标签改名、排序、规则变更后，引用页面下次读取立即使用新标签元数据。
- 如果标签被待找发票规则等下游配置引用，不允许停用或归档；后端返回引用位置。
- 自动命中结果重算通过后台 read model 刷新完成。

## 权限和错误处理

权限：

- 可查看用户可以打开抽屉查看规则。
- 无保存权限用户进入只读状态，新增、停用、启用、排序、保存禁用。
- 后端仍必须校验写权限。

错误：

- 无权限：返回 `403 permission_denied`，前端显示只读或明确错误。
- 版本冲突：`bank_transaction_tags_version_conflict`，提示“规则已被其他用户更新，请刷新后重新编辑”。
- 下游引用阻止停用：返回稳定错误码和引用位置，例如“待找发票规则：无需开票”。
- 规则校验失败：返回字段级错误，前端保留本地修改。
- 保存失败：不丢本地修改，允许修正后重试。
- read model 正在刷新：银行明细页面使用现有刷新提示，不阻塞查看。

## 下游影响

必须检查并改造这些下游：

- 银行明细页面类型列和导出。
- 免 OA 批次分类列表、批次详情和提交。
- 待找发票规则和列表状态。
- 往来款管理。
- 关联台自动匹配/异常/关系标签展示。
- 搜索或全局索引中涉及银行标签展示的字段。

原则：

- 保存业务事实时保存 `tag_code`。
- 页面展示时解析当前 `label`。
- 不做全库中文字符串替换。
- 代码中不再硬编码“工资”“手续费”等展示文案作为标签名事实；允许作为默认 seed 或测试样例。

## 测试策略

### 后端测试

- 标签规则保存成功：新增、改名、改规则、排序、停用、启用。
- `code` 后端生成且不可修改。
- `expected_version` 冲突返回明确错误。
- `内部往来款` 不能被 payload 修改、排序、停用。
- 规则校验：正向条件必填、字段白名单、空行去除、重复去重。
- 不同银行原始字段映射到统一语义字段后能正确命中。
- `excludes` 命中时排除标签。
- 优先级先后决定命中结果。
- 停用标签不参与命中。
- 被待找发票规则引用的标签不能停用，并返回引用位置。
- 规则保存后写审计并触发相关 read model dirty。
- 标签改名后 API 返回当前 label，下游引用 `tag_code` 不断裂。

### 前端测试

- 银行明细右上角显示 `自动标签规则` 按钮。
- 打开 60% 右侧抽屉。
- `可用 / 停用` 切换。
- `内部往来款` 位于可用区第一行，灰色不可交互，显示 `优先级 0`。
- 可用标签显示 `优先级 1...`。
- 新增标签、改名、编辑三类规则、排序、停用、重新启用。
- 空正向条件不能保存。
- 保存时提交 `expected_version` 和完整规则配置。
- 版本冲突、下游引用阻止停用、无权限只读状态有明确反馈。
- 保存成功后刷新银行明细列表或触发本地版本同步。

## 文档更新

实现时必须更新：

- `docs/product-specs/bank-details.md`
  - 删除“标签只能由 app 自动分配、页面不提供管理入口”的旧口径。
  - 增加自动标签规则管理、优先级、停用、统一语义字段、刷新链路。
- `docs/product-specs/pending-invoices.md`
  - 明确待找发票只引用 `tag_code`，标签名实时来自银行明细标签字典。
- `docs/dev/api-contracts.md`
  - 增加 `/api/bank-details/auto-tag-rules` 契约。

## 验收标准

- 用户能在银行明细页面打开规则抽屉并管理自动标签。
- 抽屉宽度桌面为页面 60%，小屏全宽。
- `内部往来款` 始终第一，显示 `优先级 0`，灰色不可交互。
- 用户规则按优先级从上到下执行，先命中先返回。
- 每个可用标签前显示 `优先级 1`、`优先级 2` 等小字。
- 银行字段差异由后端语义层处理，用户不需要理解各银行原始列名。
- 改名后银行明细、待找发票、免 OA 批次、往来款、关联台使用新名称。
- 规则保存不做同步全量重算，而是进入后台刷新。
- 标签停用后不再自动命中；如历史流水无其他命中则显示 `-`。
- 被下游配置引用的标签不能停用。
- 权限、审计、并发冲突、失败重试都有明确处理。
- 相关后端和前端测试通过。
