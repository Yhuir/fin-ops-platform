# 银行明细状态机

> 修改 `银行明细` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。银行明细同时消费银行原始流水、自动标签规则、关系 read model 和账户余额 read model。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 银行流水 | `imported` | import normalized payload / durable transaction row | 导入确认后进入；后续只能通过派生 read model 展示标签、关系和余额。 |
| 自动标签解析 | `internal_transfer` | `BankTransactionAutoCategoryService` 内部往来规则 | 系统规则 priority 1 命中后停止普通规则；不能被人工补分类覆盖。 |
| 自动标签解析 | `auto_matched` | 当前 active 自动标签规则 | 单一候选确定命中；展示为自动标签，不开放候选确认或人工补分类。 |
| 自动标签解析 | `needs_confirmation` | 当前 active 自动标签规则和 candidate list | 用户只能从当前候选中确认；确认后进入 `manual_confirmed` 展示语义，撤销后回到当前规则重算。 |
| 自动标签解析 | `unmatched` | 当前 active 自动标签规则 | 可人工补分类；补分类后以 `manual` 来源参与 effective category。 |
| 自动标签解析 | `manual_confirmed` | `app.bank_transaction_category_confirmations` | 来自候选确认或 unmatched 人工补分类；清除/撤销后回到当前自动规则重算。 |
| 自动标签规则 | `active` | `bank_transaction_tags` snapshot | GET/PUT/file replacement/reapply 读取；PUT 可改 label、priority、rules、status。 |
| 自动标签规则 | `archived` | `bank_transaction_tags` snapshot | 不参与新命中；可作为历史回显；被引用时归档需要同步移除下游规则引用并审计。 |
| 关系标签 | `unlinked` / `relation-tagged` | Workbench relation distribution / relation projection | 关联台、批量账务、免 OA、往来款等写入或撤回后由 read model 刷新。 |
| 账户余额 | `has_balance` / `missing_balance` | `read_model.bank_account_balances` | 导入、删除、重导或原始 balance 字段变化触发刷新；标签规则变化不改变余额事实。 |

关键规则：

- 页面不得本地推断标签结果；必须消费后端返回的 `effective_*`、`category_resolution_status` 和候选列表。
- `needs_confirmation` 只能提交当前 `auto_candidate_categories` 中的候选；同一 code 存在多第三层候选时必须同时提交并校验 `category_third_label`。
- `category-assignment` 只允许当前解析状态为 `unmatched` 的流水；禁止用它覆盖 `auto_matched`、`needs_confirmation` 或 `internal_transfer`。
- 标签/分类写操作必须写审计并触发 bank detail read model 和相关下游 dirty/outbox；不能只更新页面状态。
- 账户余额 read model 独立于 bank detail rows；日期筛选只影响账户流水数量，不改变 latest balance。

禁止流转：

- 禁止前端把全量标签字典当候选确认列表。
- 禁止规则保存后在 API 请求热路径同步扫描全量银行流水。
- 禁止 read model stale/schema mismatch/missing 时把空 rows 当成真实空列表。
- 禁止 stale 的账户余额 payload 覆盖页面已有 fresh balance。
- 禁止从 legacy candidate matches 读取 relation tag 来替代 active relation distribution。

## UI 状态

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | 首次加载 accounts / transactions / rules | 展示加载态；已有 payload 前不渲染假空。 |
| row loading | 筛选、分页、搜索、账户切换时请求 transactions | 可保留旧 rows 直到新响应；响应 status 决定是否标记 refreshing/stale。 |
| empty | fresh transactions payload 且 `rows=[]` | 只有 fresh 后才代表当前筛选真实无流水。 |
| error | API mapper、route、规则保存、导出、确认/人工补分类失败 | 展示业务错误；abort-like request 不显示错误。 |
| refreshing | accounts 或 transactions 返回 `read_model_status=refreshing` | 可保留旧 rows/余额并自动重试；规则保存/重应用显示刷新反馈。 |
| stale / schema mismatch / missing | 后端 freshness gate 返回非 fresh 状态 | 页面展示陈旧/刷新中语义，不暴露底层 SQL 细节；不能把旧 payload 当最终事实。 |
| permission disabled/hidden | `permissions.can_save`、session mutation 权限 | 规则保存、重应用、确认、人工补分类、导出写审计等动作按权限禁用或拒绝。 |

前端 domain event：

- 银行明细分类确认、撤销、人工补分类和清除后发出 `bankTransactionCategoryUpdated`，携带 affected months。
- 自动标签规则保存/重应用后发出 `bankAutoTagRulesUpdated`，用于同会话或其他页面刷新标签事实。
- 银行明细订阅 `workbenchRelationUpdated`，只有 affected months 命中当前日期筛选时 refetch。
- 前端事件只用于刷新提示和局部 refetch，不证明后端 dirty scope 已完成或 read model 已 fresh。

## Read Model / Worker 状态

| 状态 | 判定 | 后续动作 |
| --- | --- | --- |
| `fresh` | schema/source version/rule version 与当前事实一致，且没有 active dirty scope | 页面可展示为当前事实；fresh payload 可进入缓存。 |
| `refreshing` | dirty scope pending/processing，或 API 请求触发 refresh enqueue | 页面保留可用旧数据并重试；worker 继续处理。 |
| `stale` | source version、自动标签规则版本或 dirty scope 显示当前 projection 落后 | enqueue/retry refresh；不能把 stale 结果作为最终业务结论。 |
| `schema_mismatch` | read model schema version 落后 | worker/backfill 重建；页面可展示旧 rows 但必须提示刷新中。 |
| `missing` | scope/table 缺失或尚未构建 | enqueue refresh；空 payload 不等于业务空结果。 |
| `failed` / `unavailable` | worker failed、queue/repository 不可用、runtime dependency 缺失 | App Health/接口返回可诊断错误；不得返回假成功。 |

Refresh 触发来源：

- 银行流水导入、删除、重导或原始余额变化：刷新 `bank_detail` 和 `bank_account_balance`。
- 自动标签规则保存、文件替换、重应用：刷新 `bank_detail`，并通过 lifecycle 影响 no-OA、turnover、pending/search、cost/tax 等下游。
- 候选确认、撤销、人工补分类、清除：刷新 `bank_detail`、turnover/cost 等相关派生数据。
- 关联台、批量账务、免 OA、往来款关系变更：刷新 relation distribution，银行明细页面通过事件或下次读取获得 relation tag。
- App Health/backfill CLI 和 worker retry 可触发缺失或陈旧 scope 重建。
- `startup_stale_scan` 默认关闭，且不直接刷新银行明细 read model；它只标记 workbench matching dirty scopes。

失败恢复：

1. 先看 API payload 中的 `read_model_status`、`read_model_scope_keys`、`read_model_stale_reasons` 和 `enqueued_jobs`。
2. 再查 App Health、`job.read_model_dirty_scopes`、`job.outbox_events` 和 worker heartbeat。
3. 如果是账户余额缺失，重跑 `bank_account_balance.read_model.refresh`；不要用 bank detail rows 聚合余额作替代。
4. 如果是 bank detail schema/source/rule version stale，重跑对应 scope 的 `bank_detail.read_model.refresh`。
5. 如果是 relation tag 不更新，先验证 workbench relation distribution 是否 fresh，再检查 bank details relation projection。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 补齐测试闭环状态机 | 自动标签、候选确认、人工补分类、账户余额、relation tag、UI freshness 和 worker 状态边界 | `tests.test_bank_details_service`、`tests.test_bank_auto_tag_rules_api`、`tests.test_bank_details_sql_runtime`、`web/src/test/BankDetailsPage.test.tsx` 等本轮最小闭环 |
