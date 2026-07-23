# 银行明细模块边界与 I/O

日期：2026-07-22

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：银行明细页面读取 `bank_detail` read model；普通标签、分类、自动规则写操作只提交 canonical fact/version/audit，页面访问时由 query freshness gate 精确触发当前 month scope 刷新；显式“重新应用规则”保留有界月份批任务。
- 当前缺口：无。模块 README 已登记前端、route、application service、read model/query port、refresh producer 和测试入口；页面读、导出、自动标签规则、分类写入、关系标签展示和下游 tagged-row 读取均有明确 owner 与 I/O。
- 旧代码删除状态：已删除 API/page 旧非 fresh-gated 查询 fallback；`BankDetailsApplicationService` 不再持有宽 `import_service` / `BankDetailsService` 做页面读或候选推断；`Application._bank_detail_available_month_scope_keys(...)` 动态兼容入口已从下游 turnover SQL scope 读取链路移除；关系标签 raw Workbench payload fallback 已删除；PostgreSQL 分类整表 snapshot 的 delete/reinsert 写入和空标签回填 `unknown` 的兼容分支已删除。

## 职责边界

### 负责

- 银行流水列表、账户筛选、标签/分类展示、自动标签规则、导出。
- 维护 `bank_detail` scoped read model freshness。
- 普通标签/分类/自动规则写操作只返回 canonical 结果及可确定的 `affected_scope_keys` / `read_model_scope_keys`，不返回跨页面 barrier；只有显式“重新应用规则”返回 exact month `freshness_targets` / `operation_barrier_targets`。
- 为下游 workbench、流水规则批量处理、no-OA legacy、turnover 关系提供银行流水身份和标签读取边界。

### 不负责

- 不拥有银行流水导入流程。
- 不直接维护流水规则批量处理、no-OA、外部往来款或关联台关系事实。
- 不绕过 bank detail service/UoW 直接写标签副作用。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面过滤、月份、账号、标签操作 | `BankDetailsPage.tsx`、`features/bankDetails/api.ts` | API 入参必须映射到明确查询/filter contract；后端只通过 read model/query port 返回页面数据 |
| 页面只读 Audit | `PageBusinessAuditIcon` / AppHealth operations API | admin-only 调用 `page-audit?page=bank-details`；all active bank transactions 是 canonical expected-set，按正式 UUID `transaction_id` 校验交易日期/方向/金额/对方户名/月 scope；row/scope provenance 比较排除仅表示队列游标的易变 `source_version`，但必须保持 schema、source signature、row_count 和 relation source summary 一致；Audit expected-side 独立从 canonical bank legacy/UUID identities 与 active relation membership overlap 重算跨月 source summary，不复用 projection payload；账户余额必须从 canonical 流水重算 identity、笔数、最新余额和最新流水；canonical/shared relation typed edges 先双向相等，再以每条 bank row 的 linked OA/发票存在性、唯一 linked case id 和 linked status 重算页面标签，多个 active case overlap 或任一 linked 标签/case/status 偏差都阻断；candidate 只作为候选展示，不混入已配对证明；全部检查位于同一只读一致性快照，审计 SQL 归 AppHealth PostgreSQL repository，银行明细页面不直接读表或修复 |
| 标签/分类写操作 | route/service | PostgreSQL 通过 `BankTransactionCategoryMutationWriter(enqueue_refreshes=False)` 在同一事务锁定 canonical 银行流水、定向更新分类/确认事实并写审计；普通页面命令不写 downstream dirty/outbox。local runtime 保留本地 snapshot port |
| 自动标签规则保存/重跑 | `BankDetailsApplicationService` | 普通保存/文件替换只提交 settings CAS/version/audit，不运行 derived lifecycle、不写 refresh queue；页面正常 query 比较当前规则版本后 enqueue 当前 exact month。显式 `reapply` 才枚举已有月份、批量 enqueue `bank_detail` month shards 并返回 barrier；未知范围不 fallback `all` |
| 关系标签投影 | `BankDetailsRelationTagProjectionService` -> `WorkbenchRelationReadFacade.get_by_row_ids(...)` | 只允许按银行流水 row id 读取 relation distribution；可作为展示标签降级读，但不得作为写前事实源、freshness proof 或 raw Workbench payload fallback |
| Worker 关系源端快路径 | `WorkbenchRelationReadModelRepositoryPort` | `bank-detail` SQL projection v10 可通过 `list_active_workbench_relation_source_rows(...)` / `workbench_relation_source_summary_from_source(...)` 读取 active relation source summary，用于关系标签投影和 source-version proof；行读取与 source summary 必须同时携带该月银行流水 legacy row id 与 canonical UUID，summary 以 `month_scope == month OR row_ids overlap` 纳入跨月 relation，保证跨月关系新增、替换和删除都改变 stable source versions；投影边界再归一回页面 row id。该身份/成员语义变化必须提升 read-model schema version，禁止被 unchanged-scope 优化跳过；SQL owner 仍归 workbench-relations repository，下游不得直接读 relation 表，也不得用该快路径做 relation 写前判断 |
| 可用月份 scope 枚举 | `BankDetailAvailableMonthScopeProvider` | PostgreSQL read-model runtime 下只从 `BankDetailReadModelRepositoryPort.bank_detail_scope_keys_for_range(...)` 读取 scope；只有非 SQL/local runtime 才允许回退导入服务扫描，生产/API 页面读不得使用导入扫描证明 fresh |
| 下游月度一致性快照 | `BankTransactionTagReadFacade.snapshot_for_month(...)` -> `BankDetailReadModelRepositoryPort.get_bank_detail_tagged_snapshot(...)` | 输入为目标 `YYYY-MM` 和可选关系成员流水 ID；repository 在一个 `REPEATABLE READ READ ONLY` transaction 内读取目标月全部 tagged rows、跨月补充 ID、涉及 scope 的 freshness/signature/source versions。输出必须分别暴露完整 `rows` 与仅目标月 `month_rows`，使下游既能补齐跨月关系标签，又不会把跨月补充行计入目标月全流水。该 port 是纯读，不写 queue/readiness/read model。 |
| 自动分类候选推断 | `BankDetailAutoCategorySuggestionProvider` | 作为显式 provider 注入 `BankDetailsApplicationService`；应用服务本身不直接读取 import service 或 `BankDetailsService.auto_category_input_row(...)` |
| Refresh scope | `bank_detail` manifest | month or `all`；`all` 只允许 fan-out 到 month shards；受控 `force_refresh` 必须由 handler 继续传递给所有 month shard，并由 projection builder 绕过 unchanged-scope fast-path 后重算，不得被当作普通刷新静默忽略 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 银行明细列表/账户/标签 payload | 前端页面 | 必须来自 read model/query port 并带 freshness/status；标题统计由全部已发布 month shard 的 `raw_payload.statistics` 汇总，固定表示页面未筛选完整集合，不随月份、账户、标签、搜索或分页变化；统计与任一 shard 非 fresh 时返回 `statistics=null` 并入队缺失 shard，禁止回读 canonical/统一事实源填数。read model 缺失或非 fresh 时返回 `refreshing/stale/schema_mismatch/missing` 诊断，不回退同步导入扫描 |
| 页面 Audit 状态 | 标题附件 | integrity/freshness/queue 均通过且列表 read model 明确 fresh 才显示成功；issue 数为样本 |
| 自动标签规则写入结果 | 前端页面 | 普通保存立即完成，当前可见页面递增 query refresh token，并以返回的 `refreshing/stale/fresh` 状态收敛；route unmount 后不保留后台轮询，重新访问时走同一 query gate。显式 `reapply` 必须等待服务端 exact month `operation_barrier_targets` |
| 标签/分类事实写入 | canonical store | PostgreSQL 只通过 `BankTransactionCategoryMutationWriter` -> `PostgresBankTransactionCategoryRepository` 定向写 canonical facts；人工补分类撤销把原 active fact 标记为 `cleared`，不得插入 active `unknown`。`BankTransactionCategoryStorePort` 仅供 local runtime snapshot 持久化，禁止重新接入 PostgreSQL |
| 标签/关系 source proof | `bank_detail` query/worker + `WorkbenchRelationReadFacade` | projection schema v11 在每个 month scope 保存稳定 `bank_transaction_category_source_signature` 和 canonical `workbench_relation_source_versions`。query repository 各用一次 set-based SQL 重算当前标签签名与关系 summary；关系 summary 按 `month_scope == month OR active relation row_ids overlap 当月银行流水 ids` 纳入跨月关系，任一 mismatch 都把 `bank_detail` 判为 non-fresh。页面应用服务同时通过 `source_versions_for_scopes(...)` 一次批量校验共享 `workbench_relation` scopes，并经正式 gateway 只入队失配月份；两个 projection 可并行收敛，不逐月 N+1，也不让银行 worker 等待 relation distribution。自动规则另比较当前 settings rule version 与 scope `bank_auto_tag_rules_version`。全部 proof 都在 Redis 读取前完成，禁止 stale cache 冒充 fresh |
| 标签副作用 | relation/downstream read models | 普通银行页面分类/规则命令不即时写 `bank_detail` 之外任何 downstream dirty/outbox，也不触发 Workbench matching 扩展窗口；每个实际 consumer 必须在自身 query/read facade 依据 canonical dependency version/signature 于访问时收敛。显式批任务和其它拥有独立业务语义的 writer 仍可调用 transaction-bound batch queue，但不得被普通银行页面命令复用 |
| 自动标签规则/分类下游刷新 | bank_flow_rule_batch / cost_statistics / workbench matching | 不再由 `bank_auto_tag_rules_changed all` 或银行页面普通分类命令做跨页面 fan-out。`bank_flow_rule_batch`、`cost_statistics`、Workbench/search/turnover 等 consumer 必须各自证明其实际消费的规则/分类依赖；访问到 mismatch 时只刷新当前 scope。成本统计 worker 仍只能通过 `BankTransactionTagReadFacade` 读取 fresh `bank_detail` scoped read model |
| Tagged snapshot payload | cost_statistics 等下游 projection | `rows` 是目标月 + 指定跨月 ID 的去重集合，`month_rows` 仅属于目标月；同时返回全部涉及 scope 的 status/signatures 供一次性 fail-closed。缺失指定 ID 通过 `missing_transaction_ids` 显式报告，不得从 canonical 表或旧页面 payload 隐式 fallback。 |
| 关系标签展示 | 银行明细列表/下游展示 | 只输出 relation chip/status；不发布 relation 事实、不触发 relation 写入、不绕过 `workbench-relations` freshness/command 边界 |
| 导出文件 | 用户下载 | 复用当前查询边界，不绕过权限 |

## 持久化与投影

- Read model：`bank_detail`
- Projection：`partitioned_scoped_incremental`
- Worker：`bank-detail`
- Query owner：`BankDetailsApplicationService`
- Repository owner：`BankDetailReadModelRepositoryPort`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/BankDetailsPage.tsx` |
| Frontend feature | `web/src/features/bankDetails/*`、`web/src/components/BankAccountValue.tsx` |
| Backend route | `backend/src/fin_ops_platform/app/routes_bank_details.py`、`bank_detail_category_api.py`、`bank_detail_backfill.py` |
| Backend service | `bank_details_application_service.py`、`bank_details_service.py`、`bank_detail_*`、`bank_transaction_category_mutation_writer.py`、`bank_transaction_category_refresh.py`、其它 `bank_transaction_*`；不存在 post-commit 分类副作用 port 或平行 Bankdetail UoW |
| Repository / SQL | `bank_detail_read_model_repository.py`、`bank_detail_sql_projection.py`、`postgres_repositories/bank_transaction_category.py`、`postgres_repositories/read_models.py` |
| Worker/read model | `bank_detail_read_model_refresh.py`、`bank_detail_read_model_refresh_producer.py`、`bank_detail_derived_lifecycle_executor.py` |
| Tests | `tests/test_bank_details*.py`、`tests/test_bank_detail*.py`、`web/src/test/BankDetails*.test.*`、`web/e2e/bank-details-*.spec.ts` |

## 依赖方向

- 允许依赖：read model repository、bank account balance read model repository、bank transaction identity/category service、runtime queue、显式 tag dictionary/suggestion provider。
- 必须通过：BankDetailsApplicationService 和 write UoW。
- 禁止绕过：直接写 read model 表、直接从前端推断 fresh、API/page 同步扫描 import service、应用服务重新持有宽 `BankDetailsService` 读页面数据、在导入模块里改银行明细页面投影、为关系标签重新构建 raw Workbench payload。

## 测试与验证

- Service/read model：`tests/test_bank_details_sql_runtime.py`、`tests/test_bank_details_service.py`。
- 可用月份/provider 边界：`tests/test_bank_detail_available_month_scope_provider.py`。
- API/frontend：`tests/test_bank_details_routes.py`、`web/src/test/BankDetailsApi.test.ts`、`web/src/test/BankDetailsPage.test.tsx`。
- E2E：`web/e2e/bank-details-*.spec.ts`。
- 分类原子写/历史修复：`tests/test_bank_transaction_category_postgres_mutation.py`；API/即时 UI 回归：`web/src/test/BankDetailsApi.test.ts`、`web/src/test/BankDetailsPage.test.tsx`。

## 当前缺口和删除条件

- 当前缺口：无。
- 已删除旧查询路径：`accounts_payload(...)`、`transactions_payload(...)` 不再在 SQL payload 缺失或非 SQL runtime 时调用 `BankDetailsService.list_accounts(...)` / `list_transactions(...)`；缺失 repository 或非 fresh scope 统一返回 refresh/status payload。
- 已删除旧宽依赖：`BankDetailsApplicationService` 构造函数不再接收 `import_service`、`bank_details_service` 或 `requires_sql_read_model_runtime`；候选推断和标签字典分别通过显式 provider 注入。
- 已删除旧 scope 兼容：`Application._turnover_bank_transaction_rows_from_sql_read_model(...)` 不再动态读取 `_bank_detail_available_month_scope_keys`，统一通过 `BankDetailAvailableMonthScopeProvider.scope_keys()`。
- 已删除旧 PostgreSQL 分类 snapshot writer：`PostgresWorkbenchRepository.load/save_bank_transaction_categories(...)`、确认写 helper、event 全量替换 helper 和 post-commit `bank_detail_category_side_effects.py` 均不得恢复；生产写只保留定向 repository + transaction-bound batch queue。
- 不得删除显式 reapply response envelope、前端 unknown-status fail-closed 断言、普通保存后的当前页 query reconcile、非 fresh 导出保护和 relation distribution guard；普通保存的 broad lifecycle/barrier 不得恢复。
- 不得删除 worker 关系源端快路径的 repository-port 边界；若恢复为等待 `workbench_relation` read model 分发，Workbench 写后银行明细关系标签会重新受 relation worker 尾延迟影响。

## Canonical facts ownership

- Owned facts: `app.bank_transaction_categories`、`app.bank_transaction_category_events`、`app.bank_transaction_category_confirmations`。
- Shared facts: `app.bank_transactions` 由银行流水导入 owner 正式化；本模块通过受控 write/read port 维护分类、标签和展示上下文。
- Allowed writes: BankDetailsApplicationService、category/rule/confirmation services、bank detail write UoW。
- Allowed reads: bank detail query/read ports、bank transaction identity/category service。
- Downstream outputs: 普通分类/规则命令只输出 canonical version/affected months；`bank_detail` 与其它 consumer 的 dirty scope 由各自访问 freshness gate 精确产生。显式 reapply 只输出 `bank_detail` month shards；其它 owner 的显式 batch producer 不受此规则替代。
- Forbidden paths: turnover、no-OA 或前端不得直接写银行分类表；read model rows 不得反向成为分类事实源。
- Old code deletion: 旧 snapshot 分类、前端推断分类和直接跨模块分类写入必须删除；migration/audit/rollback 工具保留不算 closure。
- 2026-07-04 删除项：`Application._bank_details_relation_tag_workbench_read_model(...)` 无调用且会绕过 relation distribution/freshness 边界，已删除并由 `test_bank_details_relation_tags_only_read_relation_distribution_facade` 防回归。
- 2026-07-05 删除项：`BankDetailsApplicationService` 页面读 fallback、内置 import/BankDetailsService 候选 fallback、`requires_sql_read_model_runtime` 读路径开关，以及 server 的 `_bank_detail_available_month_scope_keys` 动态兼容入口已删除；由 `test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary`、`test_application_transactions_missing_sql_scope_enqueues_refresh_without_legacy_scan` 和 turnover SQL scope 测试防回归。
- 2026-07-22 删除项：PostgreSQL 分类整表 snapshot delete/reinsert、`category_code or "unknown"` 回填、全量 category event replacement 和事务提交后的 best-effort side-effect port 已删除；历史误写数据只能通过 `repair_unknown_bank_transaction_categories` 严格证据工具修复。
- 2026-07-23 删除项：普通银行分类/确认/撤销与自动标签规则保存的 downstream queue、derived lifecycle、跨页面 barrier 和 `all` fallback 已删除；访问时 freshness 由 category/confirmation source signature + settings rule version 独立证明，显式 reapply 保留 exact month 批任务。
