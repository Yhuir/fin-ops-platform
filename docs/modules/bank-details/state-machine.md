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
| 自动标签解析 | `manual_confirmed` | 候选确认来自 `app.bank_transaction_category_confirmations`；人工补分类来自 active `app.bank_transaction_categories` | 候选确认只能通过 confirmation DELETE 撤销并回到当前规则重算；只有从 `unmatched` 人工补上的分类显示 assignment 撤销，清除后回到 `unmatched` / `待分类`。确定性 `auto_matched` 不显示撤销按钮。 |
| 自动标签规则 | `active` | `bank_transaction_tags` snapshot | GET/PUT/file replacement/reapply 读取；PUT 可改 label、priority、rules、status。 |
| 自动标签规则 | `archived` | `bank_transaction_tags` snapshot | 不参与新命中；可作为历史回显；被引用时归档需要同步移除下游规则引用并审计。 |
| 关系标签 | `unlinked` / `relation-tagged` | Workbench relation distribution / relation projection | 关联台、批量账务、免 OA、往来款等写入或撤回只推进 canonical relation version；银行页访问时由 fresh gate 刷新。 |
| 账户余额 | `has_balance` / `missing_balance` | `read_model.bank_account_balances` | 导入、删除、重导或原始 balance 字段变化触发刷新；标签规则变化不改变余额事实。 |

关键规则：

- 页面不得本地推断标签结果；必须消费后端返回的 `effective_*`、`category_resolution_status` 和候选列表。
- `needs_confirmation` 只能提交当前 `auto_candidate_categories` 中的候选；同一 code 存在多第三层候选时必须同时提交并校验 `category_third_label`。
- `category-assignment` 只允许当前解析状态为 `unmatched` 的流水；禁止用它覆盖 `auto_matched`、`needs_confirmation` 或 `internal_transfer`。
- 标签/分类写操作必须写 canonical fact/version/audit，但不得触发 bank detail 或相关下游 dirty/outbox；当前银行页用 normal GET 收敛，其它页面在访问时收敛。
- 人工补分类清除必须把既有 category fact 标记为 `cleared` 并保留历史 code；active fact 不允许用 `unknown` 代替空分类。前端成功响应后立即显示 `待分类`，随后按 `affected_months` 刷新 read model。
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
- `bank_detail:all` 只表示显式 fan-out 到可用月份 shard；它自身不是页面可读 freshness 事实，也不能由 downstream all-scope dependency defer 自动补投。下游依赖银行明细时必须等待对应月份 shard 或具体 read model freshness。
- fresh `bank_detail` read model 中没有某些 transaction id 时，表示这些行当前没有银行明细标签投影记录；这不是 read model freshness blocker，downstream 标签读取不得因此补投 refresh 或抛 `bank_detail_read_model_not_fresh`。
- downstream 标签读取遇到非 fresh payload 时，只能补投 `dirty_scopes` / signature `dirty_status` 标记的 blocking 月份；不能因为一个月份 pending/processing 而重刷同一批 rows 中已经 fresh 的月份。

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
| 2026-06-16 | 明确 `bank_detail:all` 为 fan-out command | 避免下游 `turnover_ledger:all` / `no_oa_bank_batch:all` 把依赖未 fresh 自动补投成 `bank_detail:all`，造成月份 shard source_version 反复 bump | `tests.test_runtime_worker.RuntimeWorkerTests.test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`tests.test_read_model_refresh_gateway.ReadModelRefreshGatewayTests.test_bank_detail_all_shard_reason_does_not_bump_active_scope` |
| 2026-06-16 | fresh missing transaction 不再阻塞 downstream 标签读取 | 避免 `downstream_bank_tag_read` 对不存在的标签投影行反复补投月份 refresh，导致外部往来/免 OA all scope 永久 refreshing | `tests.test_bank_details_sql_runtime.BankTransactionTagReadFacadeTests.test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows` |
| 2026-06-16 | downstream refresh 只补投 blocking dirty scopes | 避免多个月份依赖中一个 pending 月份把其他 fresh 月份重新打 pending，导致 all scope 永远等不到同时 fresh | `tests.test_bank_details_sql_runtime.BankTransactionTagReadFacadeTests.test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes` |
| 2026-06-18 | 补银行明细真实浏览器导出下载验收 | 不改变状态机；明确导出应消费当前筛选和 relation tag 投影，Browser smoke 覆盖 Workbench confirm 后文件包含 linked relation 字段 | `web/e2e/bank-details-export-download.spec.ts` |
| 2026-06-18 | 补银行明细非 fresh 浏览器诊断验收 | 不改变后端状态机；页面在 transaction read model `refreshing/stale` 时显示业务诊断，非 fresh 空 rows 不进入真实空态，导出返回业务错误 | `web/e2e/bank-details-stale-refreshing.spec.ts` |
| 2026-06-18 | 补筛选导出和只读权限浏览器验收 | 不改变后端状态机；当前账户/关键字/分类筛选必须进入导出请求，`read_export_only` 只能读和导出，分类确认/人工分类/自动标签规则写入口按 session 权限禁用且零 mutation | `web/e2e/bank-details-filtered-export-permissions.spec.ts` |
| 2026-06-21 | 时间选择器简化为年份/月度/全部 | 不改变后端状态机；年份、月份、全部、账户、关键字、分类、page size 和翻页会刷新交易列表，导出沿用业务筛选但不携带当前分页，避免只导出当前页 | `web/src/test/BankDetailsPage.test.tsx`、`web/e2e/bank-details-filtered-export-permissions.spec.ts` |
| 2026-06-18 | 补分类确认和人工补分类浏览器验收 | 不改变后端状态机；`needs_confirmation` 只能确认当前候选并可撤销，`unmatched` 才能人工补外部往来三层分类并可清除，保存/撤销后页面 refetch 回正确状态 | `web/e2e/bank-details-category-flow.spec.ts` |
| 2026-06-18 | 补自动标签规则 drawer 浏览器验收 | 不改变后端状态机；自动标签规则保存/重应用成功后必须等待当前可见月份 `bank_detail` freshness，后置同步 blocked 只能降级为 warning，不能变成保存失败 | `web/e2e/bank-details-auto-tag-rules-flow.spec.ts` |
| 2026-06-18 | 补账户/交易非 fresh 恢复浏览器验收 | 不改变后端状态机；accounts read model 非 fresh 必须能独立 retry 到 fresh，transaction `missing` 空 rows 不能进入真实空态，交易请求短暂失败后用户重新筛选可恢复 rows | `web/e2e/bank-details-stale-refreshing.spec.ts` |
| 2026-06-18 | 补大表格与遮挡浏览器验收 | 不改变状态机；120 行长字段、桌面/窄屏、分类筛选、分类选择浮层、导出菜单和表格横向滚动必须保持可见且未被覆盖 | `web/e2e/bank-details-large-scroll-flow.spec.ts` |
| 2026-06-18 | 补银行明细权限与会话 gate 浏览器验收 | 不改变状态机；`read_export_only` 只能读和导出且零 mutation，`admin` 可执行分类写入，forbidden/expired session 在银行明细路由进入 session gate 且不调用银行明细 protected API | `web/e2e/bank-details-filtered-export-permissions.spec.ts` |
| 2026-06-18 | 补首屏与 fresh 空态浏览器验收 | 不改变状态机；默认当前年 accounts/transactions query、全部账户视图、账户余额、默认列、relation/category 字段和 fresh 空结果空态必须在真实浏览器可见；非 fresh 空态仍走诊断态 | `web/e2e/bank-details-initial-state.spec.ts` |
| 2026-06-23 | 补 `bank_detail` / `bank_account_balance` manifest 合同守卫 | 不改变状态机；锁定银行明细与账户余额独立 scope、repository port、test owner 和 `all` fan-out 语义，防止账户余额 readiness/金额被 bank detail rows 替代 | `tests.test_read_model_manifest.ReadModelManifestTests.test_bank_detail_and_balance_manifest_keep_separate_contracts` |
