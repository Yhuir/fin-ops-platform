# 银行明细模块边界与 I/O

日期：2026-07-13

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：银行明细页面读取 `bank_detail` read model；标签、分类、自动规则等写操作通过 service/UoW 触发 scoped dirty refresh。
- 当前缺口：无。模块 README 已登记前端、route、application service、read model/query port、refresh producer 和测试入口；页面读、导出、自动标签规则、分类写入、关系标签展示和下游 tagged-row 读取均有明确 owner 与 I/O。
- 旧代码删除状态：已删除 API/page 旧非 fresh-gated 查询 fallback；`BankDetailsApplicationService` 不再持有宽 `import_service` / `BankDetailsService` 做页面读或候选推断；`Application._bank_detail_available_month_scope_keys(...)` 动态兼容入口已从下游 turnover SQL scope 读取链路移除；关系标签 raw Workbench payload fallback 已删除。

## 职责边界

### 负责

- 银行流水列表、账户筛选、标签/分类展示、自动标签规则、导出。
- 维护 `bank_detail` scoped read model freshness。
- 标签/分类/自动规则写操作返回统一 write target envelope，包含 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets`。
- 为下游 workbench、流水规则批量处理、no-OA legacy、turnover 关系提供银行流水身份和标签读取边界。

### 不负责

- 不拥有银行流水导入流程。
- 不直接维护流水规则批量处理、no-OA、外部往来款或关联台关系事实。
- 不绕过 bank detail service/UoW 直接写标签副作用。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面过滤、月份、账号、标签操作 | `BankDetailsPage.tsx`、`features/bankDetails/api.ts` | API 入参必须映射到明确查询/filter contract；后端只通过 read model/query port 返回页面数据 |
| 页面只读 Audit | `PageBusinessAuditIcon` / AppHealth operations API | admin-only 调用 `page-audit?page=bank-details`；all active bank transactions 是 canonical expected-set，按正式 UUID `transaction_id` 校验交易日期/方向/金额/对方户名/月 scope；row/scope provenance 比较排除仅表示队列游标的易变 `source_version`，但必须保持 schema、source signature、row_count 和 relation source summary 一致；账户余额必须从 canonical 流水重算 identity、笔数、最新余额和最新流水；canonical/shared relation typed edges 先双向相等，再以每条 bank row 的 linked OA/发票存在性、唯一 linked case id 和 linked status 重算页面标签，多个 active case overlap 或任一 linked 标签/case/status 偏差都阻断；candidate 只作为候选展示，不混入已配对证明；全部检查位于同一只读一致性快照，审计 SQL 归 AppHealth PostgreSQL repository，银行明细页面不直接读表或修复 |
| 标签/分类写操作 | route/service | 通过 write UoW 触发受影响 month scope |
| 自动标签规则保存/重跑 | `BankDetailsApplicationService` | 返回 `bank_detail` operation barrier targets；无明确范围时按现有月份 fan-out，不把 `all` 当作页面 fresh 结果 |
| 关系标签投影 | `BankDetailsRelationTagProjectionService` -> `WorkbenchRelationReadFacade.get_by_row_ids(...)` | 只允许按银行流水 row id 读取 relation distribution；可作为展示标签降级读，但不得作为写前事实源、freshness proof 或 raw Workbench payload fallback |
| Worker 关系源端快路径 | `WorkbenchRelationReadModelRepositoryPort` | `bank-detail` SQL projection v10 可通过 `list_active_workbench_relation_source_rows(...)` / `workbench_relation_source_summary_from_source(...)` 读取 active relation source summary，用于关系标签投影和 source-version proof；行读取与 source summary 必须同时携带该月银行流水 legacy row id 与 canonical UUID，summary 以 `month_scope == month OR row_ids overlap` 纳入跨月 relation，保证跨月关系新增、替换和删除都改变 stable source versions；投影边界再归一回页面 row id。该身份/成员语义变化必须提升 read-model schema version，禁止被 unchanged-scope 优化跳过；SQL owner 仍归 workbench-relations repository，下游不得直接读 relation 表，也不得用该快路径做 relation 写前判断 |
| 可用月份 scope 枚举 | `BankDetailAvailableMonthScopeProvider` | PostgreSQL read-model runtime 下只从 `BankDetailReadModelRepositoryPort.bank_detail_scope_keys_for_range(...)` 读取 scope；只有非 SQL/local runtime 才允许回退导入服务扫描，生产/API 页面读不得使用导入扫描证明 fresh |
| 自动分类候选推断 | `BankDetailAutoCategorySuggestionProvider` | 作为显式 provider 注入 `BankDetailsApplicationService`；应用服务本身不直接读取 import service 或 `BankDetailsService.auto_category_input_row(...)` |
| Refresh scope | `bank_detail` manifest | month or `all`；`all` 只允许 fan-out 到 month shards；受控 `force_refresh` 必须由 handler 继续传递给所有 month shard，并由 projection builder 绕过 unchanged-scope fast-path 后重算，不得被当作普通刷新静默忽略 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 银行明细列表/账户/标签 payload | 前端页面 | 必须来自 read model/query port 并带 freshness/status；read model 缺失或非 fresh 时返回 `refreshing/stale/schema_mismatch/missing` 诊断，不回退同步导入扫描 |
| 页面 Audit 状态 | 标题附件 | integrity/freshness/queue 均通过且列表 read model 明确 fresh 才显示成功；issue 数为样本 |
| 自动标签规则写入结果 | 前端页面 | 前端优先等待服务端返回的 `operation_barrier_targets`；缺少/未知 read model status 默认按 `refreshing` 处理 |
| 标签/分类事实写入 | canonical store | `BankDetailsApplicationService` 只依赖显式 `BankTransactionCategoryStorePort.save_bank_transaction_categories(...)`；禁止通过宽 `state_store` 在业务 service 内散写 |
| 标签副作用 | relation/downstream read models | 通过 lifecycle/gateway 传播；`bank-flow-rule-batches` 只能读取 active 标签并维护自身 OA/发票规则 |
| 自动标签规则/分类下游刷新 | cost_statistics / workbench matching | `bank_auto_tag_rules_changed` 和银行明细分类变化必须入队 `workbench_matching` 和 `cost_statistics.read_model.refresh`；成本统计 worker 只能通过 `BankTransactionTagReadFacade` 读取 fresh `bank_detail` scoped read model 后写入 `time_rows.bank_tag_*`，成本统计页面不得直接读取银行明细 API 或规则表 |
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
| Backend service | `bank_details_application_service.py`、`bank_details_service.py`、`bank_detail_*`、`bank_transaction_*`、`bankdetail_write_uow.py` |
| Repository / SQL | `bank_detail_read_model_repository.py`、`bank_detail_sql_projection.py`、`postgres_repositories/read_models.py` |
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
- Wave 3 target envelope 回归：`BankDetailSqlRepositoryTests.test_category_mutation_response_returns_bank_detail_operation_barrier_targets`、`web/src/test/BankDetailsApi.test.ts`。

## 当前缺口和删除条件

- 当前缺口：无。
- 已删除旧查询路径：`accounts_payload(...)`、`transactions_payload(...)` 不再在 SQL payload 缺失或非 SQL runtime 时调用 `BankDetailsService.list_accounts(...)` / `list_transactions(...)`；缺失 repository 或非 fresh scope 统一返回 refresh/status payload。
- 已删除旧宽依赖：`BankDetailsApplicationService` 构造函数不再接收 `import_service`、`bank_details_service` 或 `requires_sql_read_model_runtime`；候选推断和标签字典分别通过显式 provider 注入。
- 已删除旧 scope 兼容：`Application._turnover_bank_transaction_rows_from_sql_read_model(...)` 不再动态读取 `_bank_detail_available_month_scope_keys`，统一通过 `BankDetailAvailableMonthScopeProvider.scope_keys()`。
- 不得删除自动规则 response envelope、前端 unknown-status fail-closed 断言、非 fresh 导出保护和 relation distribution guard。
- 不得删除 worker 关系源端快路径的 repository-port 边界；若恢复为等待 `workbench_relation` read model 分发，Workbench 写后银行明细关系标签会重新受 relation worker 尾延迟影响。

## Canonical facts ownership

- Owned facts: `app.bank_transaction_categories`、`app.bank_transaction_category_events`、`app.bank_transaction_category_confirmations`。
- Shared facts: `app.bank_transactions` 由银行流水导入 owner 正式化；本模块通过受控 write/read port 维护分类、标签和展示上下文。
- Allowed writes: BankDetailsApplicationService、category/rule/confirmation services、bank detail write UoW。
- Allowed reads: bank detail query/read ports、bank transaction identity/category service。
- Downstream outputs: bank_detail、bank_account_balance、bank_flow_rule_batch、turnover_ledger、no_oa_bank_batch、workbench、cost_statistics、search dirty scopes 或 owner producer 输出。
- Forbidden paths: turnover、no-OA 或前端不得直接写银行分类表；read model rows 不得反向成为分类事实源。
- Old code deletion: 旧 snapshot 分类、前端推断分类和直接跨模块分类写入必须删除；migration/audit/rollback 工具保留不算 closure。
- 2026-07-04 删除项：`Application._bank_details_relation_tag_workbench_read_model(...)` 无调用且会绕过 relation distribution/freshness 边界，已删除并由 `test_bank_details_relation_tags_only_read_relation_distribution_facade` 防回归。
- 2026-07-05 删除项：`BankDetailsApplicationService` 页面读 fallback、内置 import/BankDetailsService 候选 fallback、`requires_sql_read_model_runtime` 读路径开关，以及 server 的 `_bank_detail_available_month_scope_keys` 动态兼容入口已删除；由 `test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary`、`test_application_transactions_missing_sql_scope_enqueues_refresh_without_legacy_scan` 和 turnover SQL scope 测试防回归。
