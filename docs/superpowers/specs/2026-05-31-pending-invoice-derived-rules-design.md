# 待找发票规则派生与层级抽屉设计

日期：2026-05-31

## 背景

`待找发票` 页面右侧 `待找发票规则设置` 抽屉当前按三组规则直接编辑：

- `需要开票`
- `流水代替发票`
- `无需开票`

用户已确认新的业务口径：财务人员只需要维护“不需要正式发票”的例外标签，剩余银行明细自动标签都属于“需要开票”。因此 `需要开票` 不应继续作为用户可编辑事实，而应由后端根据银行明细自动标签规则的 active 标签全集派生。

本设计必须遵守当前 Python-first 后端重构方向：不新增平行规则表，不绕过 `AppSettingsService`、`pending_invoice_tag_groups`、audit、version 和 pending invoice read model dirty/outbox 链路。

## 已确认需求

- 在 `main` 工作。
- 解决方案必须遵循当前已重构的后端架构模式。
- 优先复用现有封装、服务和字段，不重复造轮子。
- 不做救急/临时方案。
- `待找发票规则设置` 右侧抽屉只允许用户选择两类不需要票的流水标签：
  - `流水代替发票`
  - `无需开票`
- `需要开票` 展示在前两个 block 下方，只读展示。
- `需要开票 = 全部 active 银行明细自动标签 - 流水代替发票 - 无需开票`。
- “全部 active 标签”来源于银行明细页 `自动标签规则` 的统一标签字典，即后端 `bank_transaction_tags.definitions` / `bank_transaction_tags.tags` 中 `status=active` 的标签组合。
- 标签事实身份只使用稳定 `code`。
- 标签层级展示使用 `output_primary_label` / `output_sub_label`。
- 主标签永远不可选择，只作为层级标题展示。
- 子标签可选择。
- 没有子标签的标签，展示为该主标签下缩进的同名子标签。
- 三个分类内不能重复出现同一个 tag code。
- 抽屉整体 UI 缩小，行距、标题间距、padding 收紧。

## 非目标

- 不新增第二套待找发票规则表。
- 不迁移底层字段名，不重命名 `pending_invoice_tag_groups`。
- 不把 `requires_invoice` 物理删除出全部兼容 payload。
- 不在待找发票抽屉中新建、改名或停用银行明细标签。
- 不让前端自行成为业务事实源。
- 不改变待找发票行状态计算的事实来源。
- 不引入 Redis、RabbitMQ 或新 worker 作为本需求的新增正确性依赖。
- 不重构整个设置页或银行明细自动标签规则抽屉。

## 推荐方案

采用方案 B：后端派生 `需要开票`，前端只编辑两个不需要票组。

方案比较：

| 方案 | 内容 | 结论 |
| --- | --- | --- |
| A | 只改前端，保存时前端计算三组并提交 | 不推荐。业务真相仍分散在前端，旧客户端仍可能提交不一致 `requires_invoice`。 |
| B | 后端派生 `requires_invoice`，`PUT` 只信任两个可编辑组，`GET` 返回三组 | 推荐。事实源收敛到后端，兼容旧客户端，复用现有设置/audit/read model 链路。 |
| C | 数据模型迁移为只存两个规则组，删除 `requires_invoice` | 长期干净但当前范围过大，会影响设置页、Workbench settings API、旧数据和测试。 |

## 后端设计

### API 契约

`GET /api/pending-invoices/rules` 继续返回三组：

- `groups.bank_statement_as_invoice`：可编辑，来自持久化设置。
- `groups.no_invoice_required`：可编辑，来自持久化设置。
- `groups.requires_invoice`：只读派生，由后端计算。

`PUT /api/pending-invoices/rules` 的新契约：

- 只信任并保存：
  - `groups.bank_statement_as_invoice.tag_codes`
  - `groups.no_invoice_required.tag_codes`
- 如果旧请求仍携带 `groups.requires_invoice` 或旧顶层 `requires_invoice`，后端接受但忽略。
- 保存前后端重新派生 `requires_invoice`，并在响应中返回三组。
- unknown tag、archived tag 校验只作用于两个可编辑持久化组。
- 旧请求中被忽略的 `requires_invoice` 即使包含 unknown 或 archived tag，也不能影响保存结果；它不是用户输入事实。
- 两个可编辑组之间重复同一个 tag code 继续失败。
- `requires_invoice` 不参与输入校验中的“用户选择事实”，但响应中必须满足补集口径。

### 标签全集

active 标签全集由当前 `bank_transaction_tags` 公开 payload 解析：

- 支持 `definitions` 和 `tags` 两种兼容字段。
- 只包含 `status=active` 的标签。
- `code` 为空的标签忽略。
- 展示字段来自：
  - `output_primary_label`
  - `output_sub_label`
  - `label`

### 设置持久化

继续使用现有 `AppSettingsService.update_settings(...)` 和 `pending_invoice_tag_groups`：

- 不新增表。
- 不新增独立 service。
- 版本递增继续跟随当前 tag settings event 机制。
- audit 继续记录 `pending_invoice_tag_groups_updated`。
- 保存后继续触发 `_invalidate_pending_invoice_read_model_scopes(reason=...)`，通过现有 durable queue/outbox 刷新 pending invoice read model。

### 兼容策略

为了避免旧前端、旧测试或缓存请求破坏新业务口径：

- 后端 `PUT` 接受旧 `requires_invoice` 字段但不信任。
- `GET` 的 canonical client contract 是 enriched `groups`。
- `GET` 仍可返回 `pending_invoice_tag_groups` 兼容 payload，但响应中的 `pending_invoice_tag_groups.groups.requires_invoice` 必须镜像本次派生结果，不能暴露底层旧持久化值成为第二事实源。
- 兼容镜像只发生在响应组装中，不代表把派生 `requires_invoice` 当成新的用户输入事实持久化。
- 若底层持久化中已有旧 `requires_invoice`，响应时必须以派生结果覆盖展示和兼容 payload。
- 旧字段兼容只服务迁移平滑，不代表 `requires_invoice` 仍可编辑。

### 状态计算

待找发票状态计算继续沿用现有逻辑：

- 命中 `no_invoice_required`：进入 `无需开票` 状态。
- 命中 `bank_statement_as_invoice`：进入 `流水代替发票` 状态。
- 未命中这两个例外组且没有正式发票关系：自然进入 `已支付待开票` / 需要开票范畴。

`requires_invoice` 仍可能作为待找发票列表筛选值存在，但它的匹配逻辑也必须改为补集：

- `filter=requires_invoice` 匹配 active 标签中未进入 `bank_statement_as_invoice` 或 `no_invoice_required` 的流水。
- 未分类、无 effective tag、unknown tag 或非 active tag 的支出流水不因为补集展示自动归入某个 active tag；它仍按现有 `all` / status 逻辑展示。
- SQL read model projection、legacy query fallback 和 export/filter-options 必须使用同一补集口径，不能继续依赖持久化里的旧 `requires_invoice.tag_codes`。

不需要给 `requires_invoice` 新增第三组输入事实；它是规则设置展示和列表筛选的派生分类，不是用户可编辑事实。

## 前端设计

### 抽屉结构

继续使用 `PendingInvoiceDrawerFrame`，但在规则抽屉传入更窄宽度，例如 `560-600px`，并压缩内部 spacing。

内容顺序：

1. `流水代替发票` block
   - 可交互。
   - 标签树展示。
   - 子标签 checkbox 可选择。
2. `无需开票` block
   - 可交互。
   - 标签树展示。
   - 已在 `流水代替发票` 中选择的 tag disabled。
3. `需要开票` block
   - 只读。
   - 展示派生剩余 active 标签。
   - 不显示 checkbox，不允许点击。

### 层级展示

标签树使用 `outputPrimaryLabel` / `outputSubLabel`：

- 主标签行：不可选择，弱底色或标题样式。
- 子标签行：缩进展示。
- 没有子标签：展示为主标签下的同名子标签。
- 默认展示子标签名称，必要时辅助展示 code 或状态，但 code 不作为主视觉。

### 前端状态

前端只维护两个可编辑集合：

- `bankStatementAsInvoice`
- `noInvoiceRequired`

`requiresInvoice` 在前端视图中可由当前 payload 的 `availableTags` 和两个集合即时派生，但保存后仍以服务端响应为准。

保存请求 body 不再发送 `requires_invoice`：

```json
{
  "groups": {
    "bank_statement_as_invoice": { "tag_codes": ["..."] },
    "no_invoice_required": { "tag_codes": ["..."] }
  }
}
```

### 互斥规则

- 同一个 tag code 在两个可编辑组之间互斥。
- 选择到 `流水代替发票` 后，该 tag 在 `无需开票` disabled，并从 `需要开票` 消失。
- 取消选择后，该 tag 自动回到 `需要开票`。
- `需要开票` 永远不可交互。

## 测试设计

### 后端测试

新增或更新 focused tests：

- `GET /api/pending-invoices/rules` 返回派生 `requires_invoice`。
- 派生结果只包含 active 标签全集中未被两个例外组占用的 tag。
- 响应 tags 带 `output_primary_label` / `output_sub_label`。
- `PUT /api/pending-invoices/rules` 只提交两个可编辑组时成功。
- `PUT` 携带旧 `requires_invoice` 时，后端忽略并重算。
- 两个可编辑组重复 tag 返回 `duplicate_pending_invoice_tag_mapping`。
- unknown tag 返回现有 unknown error。
- archived tag 返回现有 archived error。
- `filter=requires_invoice` 按 active 标签补集筛选，而不是读取旧持久化 `requires_invoice.tag_codes`。
- 保存成功后仍 enqueue pending invoice read model refresh scope。

### 前端测试

新增或更新 focused tests：

- `fetchPendingInvoiceRules` 正确映射 active 标签层级字段。
- `savePendingInvoiceRules` 不发送 `requires_invoice`。
- 抽屉展示两个可编辑 block 和一个只读 `需要开票` block。
- 主标签不可选择。
- 没有子标签时展示同名缩进子标签。
- 选择 `流水代替发票` 后，对应 tag 在 `无需开票` disabled，并从 `需要开票` 消失。
- `需要开票` block 无 checkbox、不可交互。
- 保存成功后触发当前待找发票列表刷新。

## 文档设计

需要同步更新：

- `docs/product-specs/pending-invoices.md`
  - 规则章节改为“编辑两个不需要票规则，第三组后端派生展示”。
- `docs/dev/pending-invoices-api.md`
  - `GET` 仍返回三组。
  - `PUT` 只信任两个可编辑组。
  - 旧 `requires_invoice` 输入兼容但忽略并重算。
- 如实际实现触及通用契约，再最小更新 `docs/dev/api-contracts.md`。

## 验证建议

后端 focused tests：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api tests.test_pending_invoice_service tests.test_app_settings_service tests.test_bank_auto_tag_rules_api -v
```

前端 focused tests：

```bash
cd web && npm test -- --run PendingInvoicesApi.test.ts PendingInvoicesPage.test.tsx
```

若共享 tag mapping 有改动，补跑：

```bash
cd web && npm test -- --run BankDetailsApi.test.ts BankDetailsPage.test.tsx
```

最终至少运行：

```bash
git diff --check
```

## 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 旧客户端提交 `requires_invoice` 覆盖新口径 | 后端忽略旧输入并派生响应，测试锁定。 |
| 前端保存两个可编辑组后本地显示与后端不一致 | 保存成功后用后端响应替换本地 payload。 |
| active 标签全集来源不一致 | 后端统一从 `bank_transaction_tags.definitions/tags` 取 `status=active`。 |
| archived/unknown 标签悬挂 | 继续复用 `AppSettingsService` 校验。 |
| 三组重复 | 后端校验两个可编辑组互斥，`requires_invoice` 补集天然互斥。 |
| 影响 pending invoice read model freshness | 保存后复用现有 pending invoice dirty/outbox refresh。 |
