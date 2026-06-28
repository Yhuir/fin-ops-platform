# 银行明细状态机

> 修改 `银行明细` 相关业务状态、UI 状态、direct API 状态或 legacy projection/worker 下线状态前必须读取本文件。银行明细页面消费 direct API DTO；后端 旧投影/worker 是下线清单/旧诊断。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 银行流水 | `imported` | import normalized payload / durable transaction row | 导入确认后进入；页面通过 direct API 展示标签、关系和余额。 |
| 自动标签解析 | `internal_transfer` | `BankTransactionAutoCategoryService` 内部往来规则 | 系统规则 priority 1 命中后停止普通规则；不能被人工补分类覆盖。 |
| 自动标签解析 | `auto_matched` | 当前 active 自动标签规则 | 单一候选确定命中；展示为自动标签，不开放候选确认或人工补分类。 |
| 自动标签解析 | `needs_confirmation` | 当前 active 自动标签规则和 candidate list | 用户只能从当前候选中确认；确认后进入 `manual_confirmed` 展示语义，撤销后回到当前规则重算。 |
| 自动标签解析 | `unmatched` | 当前 active 自动标签规则 | 可人工补分类；补分类后以 `manual` 来源参与 effective category。 |
| 自动标签解析 | `manual_confirmed` | `app.bank_transaction_category_confirmations` | 来自候选确认或 unmatched 人工补分类；清除/撤销后回到当前自动规则重算。 |
| 自动标签规则 | `active` | `bank_transaction_tags` snapshot | GET/PUT/file replacement/reapply 读取；PUT 可改 label、priority、rules、status。 |
| 自动标签规则 | `archived` | `bank_transaction_tags` snapshot | 不参与新命中；可作为历史回显；被引用时归档需要同步移除下游规则引用并审计。 |
| 关系标签 | `unlinked` / `relation-tagged` | Workbench relation distribution / relation projection | 关联台、批量账务、免 OA、往来款等写入或撤回后，页面通过 direct refetch 或 relation distribution 读取最新关系标签。 |
| 账户余额 | `has_balance` / `missing_balance` | 银行流水事实 / direct account query | 导入、删除、重导或原始 balance 字段变化影响余额；标签规则变化不改变余额事实。 |

关键规则：

- 页面不得本地推断标签结果；必须消费后端返回的 `effective_*`、`category_resolution_status` 和候选列表。
- `needs_confirmation` 只能提交当前 `auto_candidate_categories` 中的候选；同一 code 存在多第三层候选时必须同时提交并校验 `category_third_label`。
- `category-assignment` 只允许当前解析状态为 `unmatched` 的流水；禁止用它覆盖 `auto_matched`、`needs_confirmation` 或 `internal_transfer`。
- 标签/分类写操作必须写审计，并通过 direct refetch、真实下游 lifecycle/outbox 或 affected scope 诊断传播；不能只更新页面状态。
- 账户余额由 direct account query 组装；日期筛选只影响账户流水数量，不改变 latest balance。

禁止流转：

- 禁止前端把全量标签字典当候选确认列表。
- 禁止规则保存后在 API 请求热路径同步扫描全量银行流水。
- 禁止前端根据旧投影同步字段决定空态、刷新态、导出可用性或写入阻断。
- 禁止从 legacy candidate matches 读取 relation tag 来替代 active relation distribution。

## UI 状态

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | 首次加载 accounts / transactions / rules | 展示加载态；已有 payload 前不渲染假空。 |
| row loading | 筛选、分页、搜索、账户切换时请求 transactions | 请求期间展示加载态；响应 payload 直接替换 rows。 |
| empty | direct transactions payload 且 `rows=[]` | 表示当前筛选无流水。 |
| error | API mapper、route、规则保存、导出、确认/人工补分类失败 | 展示业务错误；abort-like request 不显示错误。 |
| permission disabled/hidden | `permissions.can_save`、session mutation 权限 | 规则保存、重应用、确认、人工补分类、导出写审计等动作按权限禁用或拒绝。 |

前端 domain event：

- 银行明细分类确认、撤销、人工补分类和清除后发出 `bankTransactionCategoryUpdated`，携带 affected months。
- 自动标签规则保存/重应用后发出 `bankAutoTagRulesUpdated`，用于同会话或其他页面刷新标签事实。
- 银行明细订阅 `workbenchRelationUpdated`，只有 affected months 命中当前日期筛选时 refetch。
- 前端事件只用于局部 refetch，不证明后端 outbox/background job 已完成。

## Runtime / Guard 状态

银行明细当前没有 page-level 旧投影 runtime。页面状态只来自 direct accounts / transactions / rules / export API、权限、浏览器请求状态和真实后台任务诊断。

当前规则：

- 银行流水导入、删除、重导或原始余额变化后，银行明细页面直接重读 accounts/transactions；账户余额由 direct accounts query 从银行流水事实组装，不恢复独立 `bank_account_balance` 旧投影。
- 自动标签规则保存、文件替换、重应用后，页面直接重读银行流水；下游 no-OA、turnover、pending、cost/tax 等通过各自 direct API、真实 lifecycle/outbox 或 affected scope 诊断收敛；Search 通过 direct `/api/search` payload 反映结果。
- 候选确认、撤销、人工补分类、清除后，页面 direct refetch；下游通过 owner service/direct read boundary 读取最新事实。
- 关联台、批量账务、免 OA、往来款关系变更后，银行明细通过 relation distribution、事件提示或下次 direct API 读取获得 relation tag。
- App Health/backfill CLI 和 worker retry 只处理真实后台任务、Workbench matching 或导入/外部同步状态；不触发银行明细 page-level 旧投影 重建。
- `startup_stale_scan` 默认关闭，且不直接刷新银行明细 旧投影；它只标记 workbench matching dirty scopes。
- `bank_detail:all` 不再是页面可读同步事实，也不能由 downstream all-scope dependency defer 自动补投。下游依赖银行明细时必须通过 direct provider 或明确的业务事实缺口处理。
- 历史 `bank_detail` 旧投影中没有某些 transaction id 时，不得因此补投 refresh 或抛 旧 `bank_detail` 同步错误；当前 direct provider 按 canonical 分类事实返回可用标签或明确缺口。
- downstream 标签读取遇到暂不可用 payload 时，只能暴露 direct dependency unavailable / unknown 诊断；不能补投银行明细 page-level 旧投影 refresh。

失败恢复：

1. 页面问题先看 direct API payload、route/service/repository 查询和浏览器网络错误。
2. 后端兼容问题再查 App Health、真实 worker heartbeat、`job.outbox_events` 和 direct provider 依赖状态。
3. 如果是账户余额缺失，先查银行流水事实和 direct account query；不要恢复 `bank_account_balance` 旧刷新事件。
4. 如果是 bank detail schema/source/rule version 旧诊断，先查 canonical bank import、category/rule version 和 direct query service；不要重跑 `bank_detail` 旧刷新事件。
5. 如果是 relation tag 不更新，先验证 workbench relation distribution 或 direct relation context，再检查 bank details relation projection。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 补齐测试闭环状态机 | 自动标签、候选确认、人工补分类、账户余额、relation tag、UI 状态和历史 worker 状态边界 | `tests.test_bank_details_service`、`tests.test_bank_auto_tag_rules_api`、`tests.test_bank_details_sql_runtime`、`web/src/test/BankDetailsPage.test.tsx` 等本轮最小闭环 |
| 2026-06-16 | 明确 `bank_detail:all` 为 fan-out command | 避免下游 `turnover_ledger:all` / `no_oa_bank_batch:all` 把依赖未完成 自动补投成 `bank_detail:all`，造成月份 shard source_version 反复 bump | `tests.test_runtime_worker.RuntimeWorkerTests.test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`tests.test_read_model_refresh_gateway.ReadModelRefreshGatewayTests.test_bank_detail_all_shard_reason_does_not_bump_active_scope` |
| 2026-06-16 | 历史 missing transaction 不再阻塞 downstream 标签读取 | 避免 `downstream_bank_tag_read` 对不存在的标签投影行反复补投月份 refresh，导致外部往来/免 OA all scope 永久 refreshing | `tests.test_bank_details_sql_runtime.BankTransactionTagReadFacadeTests.test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows` |
| 2026-06-16 | downstream refresh 只补投 blocking dirty scopes | 避免多个月份依赖中一个 pending 月份把其他已完成月份重新打 pending，导致 all scope 永远等不到同时完成 | `tests.test_bank_details_sql_runtime.BankTransactionTagReadFacadeTests.test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes` |
| 2026-06-18 | 补银行明细真实浏览器导出下载验收 | 不改变状态机；明确导出应消费当前筛选和 relation tag 投影，Browser smoke 覆盖 Workbench confirm 后文件包含 linked relation 字段 | `web/e2e/bank-details-export-download.spec.ts` |
| 2026-06-26 | 银行明细前端移除页面级 旧投影同步状态 | 页面不再消费 accounts/transactions/rules 的 旧投影状态；GET payload 直接展示，规则保存后 direct refetch | `web/src/test/BankDetailsPage.test.tsx`、`web/e2e/bank-details-stale-refreshing.spec.ts` |
| 2026-06-27 | 银行明细后端 page read 移除 SQL 旧投影/cache | accounts/transactions/export 直接走 `BankDetailsService`，不读取 `bank_detail` / `bank_account_balance` SQL 旧投影或 Redis page cache，不返回旧刷新态 202 | `tests/test_bank_auto_tag_rules_api.py`、`tests/test_bank_details_routes.py`、`tests/test_bank_details_sql_runtime.py`、`tests/test_platform_runtime_boundary_guards.py` |
| 2026-06-28 | 删除账户余额 legacy 旧投影 runtime | `bank-account-balance` worker、refresh event、projection/repository/backfill、manifest、App Status 和 deploy env 已删除；accounts API 继续 direct 读取银行流水事实 | `tests/test_runtime_worker_registry.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_manifest.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` |
| 2026-06-18 | 补筛选导出和只读权限浏览器验收 | 不改变后端状态机；当前账户/关键字/分类筛选必须进入导出请求，`read_export_only` 只能读和导出，分类确认/人工分类/自动标签规则写入口按 session 权限禁用且零 mutation | `web/e2e/bank-details-filtered-export-permissions.spec.ts` |
| 2026-06-21 | 时间选择器简化为年份/月度/全部 | 不改变后端状态机；年份、月份、全部、账户、关键字、分类、page size 和翻页会刷新交易列表，导出沿用业务筛选但不携带当前分页，避免只导出当前页 | `web/src/test/BankDetailsPage.test.tsx`、`web/e2e/bank-details-filtered-export-permissions.spec.ts` |
| 2026-06-18 | 补分类确认和人工补分类浏览器验收 | 不改变后端状态机；`needs_confirmation` 只能确认当前候选并可撤销，`unmatched` 才能人工补外部往来三层分类并可清除，保存/撤销后页面 refetch 回正确状态 | `web/e2e/bank-details-category-flow.spec.ts` |
| 2026-06-26 | 前端写后直接刷新银行流水 | 不改变后端 response shape；自动标签规则保存/重应用成功后直接重新请求银行流水，不等待旧操作屏障 | `web/src/test/BankDetailsPage.test.tsx`、`bash scripts/verify.sh docs` |
| 2026-06-18 | 补自动标签规则 drawer 浏览器验收 | 不改变后端状态机；自动标签规则保存/重应用成功后刷新银行流水，后置同步 blocked 不能变成保存失败 | `web/e2e/bank-details-auto-tag-rules-flow.spec.ts` |
| 2026-06-18 | 补账户/交易恢复浏览器验收 | 历史记录；2026-06-26 后页面级 同步状态 UI 已移除，保留网络失败后用户重新筛选恢复 | `web/e2e/bank-details-stale-refreshing.spec.ts` |
| 2026-06-18 | 补大表格与遮挡浏览器验收 | 不改变状态机；120 行长字段、桌面/窄屏、分类筛选、分类选择浮层、导出菜单和表格横向滚动必须保持可见且未被覆盖 | `web/e2e/bank-details-large-scroll-flow.spec.ts` |
| 2026-06-18 | 补银行明细权限与会话 gate 浏览器验收 | 不改变状态机；`read_export_only` 只能读和导出且零 mutation，`admin` 可执行分类写入，forbidden/expired session 在银行明细路由进入 session gate 且不调用银行明细 protected API | `web/e2e/bank-details-filtered-export-permissions.spec.ts` |
| 2026-06-18 | 补首屏与空态浏览器验收 | 不改变状态机；默认当前年 accounts/transactions query、全部账户视图、账户余额、默认列、relation/category 字段和 direct 空结果空态必须在真实浏览器可见 | `web/e2e/bank-details-initial-state.spec.ts` |
| 2026-06-23 | 补 `bank_detail` / `bank_account_balance` manifest 合同守卫 | 历史记录；2026-06-28 已删除独立 `bank_account_balance` manifest，当前由 direct accounts query 和负向守卫保护 | `tests.test_read_model_manifest.ReadModelManifestTests.test_bank_account_balance_manifest_is_removed` |
