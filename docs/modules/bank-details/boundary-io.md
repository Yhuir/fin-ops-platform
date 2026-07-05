# 银行明细模块边界与 I/O

日期：2026-07-04

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：银行明细页面读取 `bank_detail` read model；标签、分类、自动规则等写操作通过 service/UoW 触发 scoped dirty refresh。
- 当前缺口：模块 README 只登记了前端入口，后端 service/read model 文件已在本文件补齐，后续应同步回 README。关系标签投影已确认只读 `WorkbenchRelationReadFacade` / relation distribution；`Application._bank_details_relation_tag_workbench_read_model(...)` 旧 raw Workbench payload helper 已删除，禁止重新接回银行明细标签链路。
- 旧代码删除条件：没有 API 或页面继续走旧的非 fresh-gated 查询路径。

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
| 页面过滤、月份、账号、标签操作 | `BankDetailsPage.tsx`、`features/bankDetails/api.ts` | API 入参必须映射到明确查询/filter contract |
| 标签/分类写操作 | route/service | 通过 write UoW 触发受影响 month scope |
| 自动标签规则保存/重跑 | `BankDetailsApplicationService` | 返回 `bank_detail` operation barrier targets；无明确范围时按现有月份 fan-out，不把 `all` 当作页面 fresh 结果 |
| 关系标签投影 | `BankDetailsRelationTagProjectionService` -> `WorkbenchRelationReadFacade.get_by_row_ids(...)` | 只允许按银行流水 row id 读取 relation distribution；可作为展示标签降级读，但不得作为写前事实源、freshness proof 或 raw Workbench payload fallback |
| 可用月份 scope 枚举 | `BankDetailAvailableMonthScopeProvider` | PostgreSQL read-model runtime 下优先从 `BankDetailReadModelRepositoryPort.bank_detail_scope_keys_for_range(...)` 读取 scope；只有非 SQL/local runtime 才允许回退导入服务扫描 |
| Refresh scope | `bank_detail` manifest | month or `all`；`all` 只允许 fan-out 到 month shards |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 银行明细列表/账户/标签 payload | 前端页面 | 必须带 freshness/status |
| 自动标签规则写入结果 | 前端页面 | 前端优先等待服务端返回的 `operation_barrier_targets`；缺少/未知 read model status 默认按 `refreshing` 处理 |
| 标签/分类事实写入 | canonical store | `BankDetailsApplicationService` 只依赖显式 `BankTransactionCategoryStorePort.save_bank_transaction_categories(...)`；禁止通过宽 `state_store` 在业务 service 内散写 |
| 标签副作用 | relation/downstream read models | 通过 lifecycle/gateway 传播；`bank-flow-rule-batches` 只能读取 active 标签并维护自身 OA/发票规则 |
| 自动标签规则下游刷新 | cost_statistics / workbench matching | `bank_auto_tag_rules_changed` 必须入队 `workbench_matching` 和 `cost_statistics.read_model.refresh`；成本统计页面只读取刷新后的 `time_rows.bank_tag_*`，不得直接读取银行明细 API 或规则表 |
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

- 允许依赖：read model repository、bank transaction identity/category service、runtime queue。
- 必须通过：BankDetailsApplicationService 和 write UoW。
- 禁止绕过：直接写 read model 表、直接从前端推断 fresh、在导入模块里改银行明细页面投影、为关系标签重新构建 raw Workbench payload。

## 测试与验证

- Service/read model：`tests/test_bank_details_sql_runtime.py`、`tests/test_bank_details_service.py`。
- 可用月份/provider 边界：`tests/test_bank_detail_available_month_scope_provider.py`。
- API/frontend：`tests/test_bank_details_routes.py`、`web/src/test/BankDetailsApi.test.ts`、`web/src/test/BankDetailsPage.test.tsx`。
- E2E：`web/e2e/bank-details-*.spec.ts`。
- Wave 3 target envelope 回归：`BankDetailSqlRepositoryTests.test_category_mutation_response_returns_bank_detail_operation_barrier_targets`、`web/src/test/BankDetailsApi.test.ts`。

## 当前缺口和删除条件

- 将本文件补齐的后端入口同步到模块 README。
- 删除旧查询路径前，必须验证写标签、自动规则、导出和 stale/refreshing UI。
- 后续删除旧路径时，不得删除自动规则 response envelope 或前端 unknown-status fail-closed 断言。

## Canonical facts ownership

- Owned facts: `app.bank_transaction_categories`、`app.bank_transaction_category_events`、`app.bank_transaction_category_confirmations`。
- Shared facts: `app.bank_transactions` 由银行流水导入 owner 正式化；本模块通过受控 write/read port 维护分类、标签和展示上下文。
- Allowed writes: BankDetailsApplicationService、category/rule/confirmation services、bank detail write UoW。
- Allowed reads: bank detail query/read ports、bank transaction identity/category service。
- Downstream outputs: bank_detail、bank_account_balance、bank_flow_rule_batch、turnover_ledger、no_oa_bank_batch、workbench、cost_statistics、search dirty scopes 或 owner producer 输出。
- Forbidden paths: turnover、no-OA 或前端不得直接写银行分类表；read model rows 不得反向成为分类事实源。
- Old code deletion: 旧 snapshot 分类、前端推断分类和直接跨模块分类写入必须删除；migration/audit/rollback 工具保留不算 closure。
- 2026-07-04 删除项：`Application._bank_details_relation_tag_workbench_read_model(...)` 无调用且会绕过 relation distribution/freshness 边界，已删除并由 `test_bank_details_relation_tags_only_read_relation_distribution_facade` 防回归。
