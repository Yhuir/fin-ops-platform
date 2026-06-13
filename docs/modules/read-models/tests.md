# Read Model 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口、影响面、P0/P1/P2 缺口和未测风险。全局依赖地图见 `../../dev/testing-closure-dependency-map.md`。

## 修改前影响面清单

- 页面入口：无独立页面；所有列表/统计页面都依赖 read model freshness/status 语义。
- API client：`web/src/features/*/api.ts` 中消费 `read_model_status`、`read_model_stale_reasons`、`refresh_enqueued`、`source_versions` 的 API mapper。
- 后端 route：`backend/src/fin_ops_platform/app/server.py` 与 `backend/src/fin_ops_platform/app/routes_*.py` 中所有 read model 查询型 endpoint。
- Service / repository：
  - `backend/src/fin_ops_platform/services/read_model_query_gateway.py`
  - `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
  - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
  - `backend/src/fin_ops_platform/services/read_model_scope_contract.py`
  - `backend/src/fin_ops_platform/services/read_model_readiness.py`
  - `backend/src/fin_ops_platform/services/runtime_queue.py`
  - `backend/src/fin_ops_platform/services/postgres_repositories/read_model_scope_contracts.py`
- Read model：`workbench`、`workbench_relation`、`bank_detail`、`bank_account_balance`、`pending_invoice`、`search`、`invoice_lifecycle`、`input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`cost_statistics`、`tax_offset`、`no_oa_bank_batch`、`turnover_ledger`。
- Worker / dirty scope：`job.read_model_dirty_scopes`、`job.outbox_events`、`RuntimeQueueRepository.enqueue_read_model_refresh(...)`、`runtime_worker_registry.py` 中 read model worker event types。
- Domain event：前端 domain event 只作为刷新提示；read model freshness 和 worker readiness 是事实源。
- 权限 / 审计：本模块不直接做权限判定；风险来自 API route 绕过 read boundary 或 service 直接写 runtime 表。
- 导出 / 文件：导出 API 依赖 fresh gate 后的 rows/summary；导出 shape 由各业务模块测试保护。
- 缓存：Redis 只能缓存 fresh gate 后 payload；`ReadModelQueryGateway` 负责 cache hit/miss 语义。
- 外部依赖：PostgreSQL durable queue 是事实源；Redis/RabbitMQ 不是事实源。
- 可能影响的旧页面：所有依赖 read model 的页面，尤其关联台、银行明细、待找发票、进项/销项/OA 待付款、税金抵扣、成本统计、免 OA、批量账务、往来款和 App Health。
- 可能被哪些上游写入影响：导入确认、关系确认/撤回、规则保存、no-OA 批处理、税金认证导入、设置重置、project scope 变化、read model miss/stale。`startup_stale_scan` 默认关闭；启用时只标记 stale workbench matching dirty scopes，不是用户可见 read model 的直接 refresh 来源。
- 依赖地图引用：`../../dev/testing-closure-dependency-map.md` 的 Read Model / Worker 依赖图、API Contract 风险图和共享风险热点。

## 场景覆盖清单

| 场景 | 是否适用 | 现有测试 | 缺口 | 优先级 |
| --- | --- | --- | --- | --- |
| happy path | 适用 | `tests/test_read_model_query_gateway.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_readiness_reporter.py` | 各业务 read model happy path 由对应模块测试覆盖 | P1 |
| empty state | 适用 | `tests/test_read_model_query_gateway.py::test_missing_sql_view_returns_refreshing_empty_payload_and_enqueues_miss` | 页面空态由业务模块覆盖 | P1 |
| invalid input | 适用 | `tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_scope_contract.py` | 非成本统计 scope policy 目前保持通用 dedupe，具体非法业务 scope 由后续模块判断 | P1 |
| missing field | 适用 | `tests/test_read_model_freshness.py`、`tests/test_read_model_query_gateway.py` | API response 缺字段由业务 API contract tests 继续覆盖 | P1 |
| wrong type | 适用 | `tests/test_read_model_query_gateway.py` 覆盖非 dict view/missing；scope policy 覆盖 normalize | 更细 DTO wrong type 属业务 API 层 | P2 |
| duplicate input | 适用 | `tests/test_read_model_refresh_gateway.py` 覆盖 scope dedupe | durable queue conflict 由 `tests/test_runtime_queue.py` 覆盖 | P1 |
| idempotent repeat | 适用 | `tests/test_runtime_queue.py`、`tests/test_read_model_refresh_gateway.py` | 业务写入 idempotency 属业务模块 | P1 |
| permission denied | 不直接适用 | `tests/test_platform_runtime_boundary_guards.py` 防 service import HTTP auth | 具体 403 shape 由业务 API 测试覆盖 | 不适用 |
| stale version / conflict | 适用 | `tests/test_read_model_freshness.py`、`tests/test_read_model_query_gateway.py` | stale write precondition 属业务模块 | P1 |
| `read_model_status=fresh` | 适用 | `tests/test_read_model_query_gateway.py`、`tests/test_read_model_readiness_reporter.py` | 业务 API fresh payload shape 由业务模块覆盖 | P1 |
| `read_model_status=refreshing` | 适用 | `tests/test_read_model_query_gateway.py`、`tests/test_read_model_readiness_reporter.py` | 页面 refreshing 行为由业务前端测试覆盖 | P1 |
| `read_model_status=stale` | 适用 | `tests/test_read_model_freshness.py` 内部 freshness；public gateway 映射为 refreshing | App Status stale 由 app-health 模块继续审计 | P1 |
| `read_model_status=missing` | 适用 | `tests/test_read_model_query_gateway.py` | App Status missing 由 app-health 模块继续审计 | P1 |
| `read_model_status=failed/unavailable` | 适用 | `tests/test_read_model_readiness_reporter.py`、App Status 测试、`tests/test_read_model_scope_contract.py` 覆盖 outbox failure 是否 current-effective | 各页面 failed/unavailable 展示由业务模块覆盖 | P1 |
| background job queued/running/succeeded/failed | 适用 | `tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_readiness_reporter.py` | 后台任务 UI 属 app-health/background-jobs 模块 | P1 |
| cache hit/cache miss | 适用 | `tests/test_read_model_query_gateway.py` | Redis 真连接不在本地单测覆盖 | P2 |
| external dependency timeout/failure | 不直接适用 | runtime/app-health 模块覆盖依赖状态 | OA/Redis/RabbitMQ/PostgreSQL 真失败需 staging | P2 |
| frontend loading | 间接适用 | 业务页面测试 | 本模块无 UI | 不适用 |
| frontend empty | 间接适用 | 业务页面测试 | 本模块无 UI | 不适用 |
| frontend error | 间接适用 | 业务页面测试 | 本模块无 UI | 不适用 |
| drawer/dialog open/close | 不适用 | N/A | 本模块无 UI | 不适用 |
| filters/sorting/pagination/search | 间接适用 | 业务模块测试 | 本模块只保护 freshness 边界 | P2 |
| export shape | 间接适用 | 业务 export tests | 本模块只保护 fresh gate 语义 | P2 |
| cross-page refresh | 适用 | `tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` | 前端事件和业务 page refresh 在 domain-events/business 模块继续审计 | P1 |
| write operation action attribution | 适用 | `tests/test_workbench_uow_contract.py`、`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_workbench_dirty_queue_wiring.py`、`tests/test_write_operation_slo_audit.py`、`tests/test_write_operation_scenario_discovery.py` | 生产仍需真实登录态和人工批准 scenario 才能执行 mutating gate | P1 |
| old feature regression | 适用 | `tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_scope_contract.py` | 旧业务 shape 由各模块继续覆盖 | P1 |
| historical bug regression | 适用 | `tests/test_read_model_scope_contract.py`、`tests/test_read_model_refresh_gateway.py` | 生产真实库 dry-run 仍需发布前执行 | P2 |
| production data / migration risk | 适用 | `scripts/check-read-model-scope-contracts.py`、`tests/test_read_model_scope_contract.py` 覆盖 repair manifest、audit、rollback 和幂等 apply | 未连接真实生产 PostgreSQL 执行 dry-run/`--apply` | P2 documented-risk |
| performance-sensitive query path | 间接适用 | `tests/test_api_performance_metrics.py`、SQL runtime tests | 本模块未做性能基准；业务 read model SQL 在对应模块覆盖 | P2 |

## 七类测试适用性

| 类别 | 是否适用 | 现有测试入口 | 必须覆盖 | 当前缺口 | 优先级 | 未测风险 |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_read_model_freshness.py`、`tests/test_read_model_refresh_gateway.py` | source version normalize、fresh/stale/missing/schema/source mismatch、scope normalize/validate/dedupe | 无 P0 缺口 | P1 | 新增 read model 特殊 scope policy 时需补业务规则测试 |
| 2. Service-layer tests | 适用 | `tests/test_read_model_query_gateway.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_scope_contract.py`、`tests/test_read_model_readiness_reporter.py` | gateway 委托 queue、cache hit/miss、missing/stale 入队、scope contract 检查/清理、repair manifest、audit、rollback、readiness 成功/失败记录 | 无 P0 缺口 | P1 | 真实 repository/DB 清理需 dry-run |
| 3. API contract tests | 按需适用 | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_generic_cost_statistics_enqueue_expands_month_scopes` 和各业务 API tests | API 必须透出 `read_model_status`、`refresh_enqueued`、`stale_reasons` 等关键字段 | 本模块不拥有单一 HTTP contract；需各模块继续补齐 | P1 | 如果业务 route 绕过 gateway，可能只在模块 API tests 暴露 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_read_model_*`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_runtime_queue.py` | dirty scope/outbox durable truth、worker lifecycle 使用 gateway、Redis 只缓存 fresh payload、readiness scope 状态、current uncovered outbox failure 不被清理 | 无 P0 缺口 | P1 | Redis/RabbitMQ 真连接属于 runtime/staging 风险 |
| 5. Frontend component and interaction tests | 间接适用 | `web/src/test/*Page.test.tsx`、`web/src/test/domainEvents.test.ts` | 页面必须正确消费 fresh/refreshing/stale/empty/error | 本模块无 UI；由业务页面矩阵继续审计 | P1 | 页面可能把 refreshing 空 rows 当真实空结果，需业务模块逐一保护 |
| 6. End-to-end business-flow integration tests | 按需适用 | `tests/test_runtime_worker_read_model_refresh_scopes.py`、各业务 integration tests | 写入 -> dirty scope -> worker/readiness -> 页面/API 的关键路径 | 完整导入到 worker 投影端到端不在本模块集中覆盖 | P2 | 生产 worker drain 和历史数据需 dry-run/smoke |
| 7. Existing feature regression tests | 适用 | `tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_scope_contract.py` | runtime 边界不被绕过；service 不 import HTTP/auth；producer 不绕过 gateway；旧非法 scope 可检测/清理 | 无 P0 缺口 | P1 | 新增 producer 时必须同步边界守卫 |

## 历史 bug 回归库

| 日期 | Bug | 根因 | 回归测试 | 验证命令 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-06-12 | App Status 不能把已覆盖历史 failure 与当前未覆盖 failure 混为同一类，也不能删除真实 current blocker | 旧 outbox failure 可能已有 later done/fresh readiness 覆盖；另一些失败仍是当前真实阻塞 | `tests/test_read_model_scope_contract.py::test_check_reports_repair_manifest_categories_and_outbox_current_state`、`test_apply_records_audit_with_manifest_cleanup_and_rollback_without_deleting_current_failures`、`test_apply_is_idempotent_after_rows_are_deleted` | `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract -v` | 自动化已覆盖服务层语义；生产真实库 dry-run 仍需执行 |
| 2026-06-10 | legacy/invalid `cost_statistics` dirty/outbox/readiness scope 影响生产 runtime 状态 | 成本统计 scope policy 收敛后旧运行时状态仍保留裸月份/裸 all/非法 scope | `tests/test_read_model_scope_contract.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` | `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v` | 自动化已覆盖；生产 `--apply` 为 documented-risk |

## 关键 smoke flows

- API miss smoke：业务 API 没有 SQL view 时，`ReadModelQueryGateway` 返回 refreshing 空 payload，设置 `refresh_enqueued=true`，并通过 `ReadModelRefreshGateway` 入队规范 scope。
- Source version stale smoke：SQL view 存在但 source/schema 不匹配时，API 不能标 fresh；应返回 refreshing/stale reasons 并入队 refresh，且不能写 Redis fresh cache。
- Worker readiness smoke：read model worker 成功后记录 readiness；失败时记录 failed/unavailable 类状态；fan-out-only 结果不能写假 fresh。
- Scope contract smoke：生产旧 dirty/outbox/readiness scope 可 dry-run 检测，repair manifest 必须区分已覆盖历史 failure 与 current uncovered blocker；`--apply` 只删除非规范旧状态、补投可归一化 replacement scope、记录 audit/rollback，不清理 current uncovered blocker。
- Write operation attribution smoke：Workbench/no-OA 等高影响写操作必须把 action metadata 透传到 durable refresh request，`write_operation_slo_audit` 只能在 required scopes 都按 operation profile fresh 后通过；scenario discovery 生成的 mutating scenario 默认需要人工审批。

## 本模块验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_read_model_readiness_reporter -v
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_platform_runtime_boundary_guards -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_generic_cost_statistics_enqueue_expands_month_scopes -v
bash scripts/verify.sh docs
```

## Nightly CI 覆盖

- `bash scripts/verify.sh all` 会运行全量后端 unittest，因此覆盖上述 read model 模块测试。
- `bash scripts/verify.sh all` 会运行前端 Vitest，因此覆盖页面消费 `read_model_status` 的前端测试。
- `bash scripts/verify.sh docs` 会确认测试闭环文档入口存在。
- Nightly 不连接真实生产 PostgreSQL、Redis、RabbitMQ、OA Mongo；这些风险保留为发布前 dry-run/staging 验证。

## 未测风险

- 未在真实生产 PostgreSQL 上执行 `scripts/check-read-model-scope-contracts.py --json` 或 `--apply`；上线前必须先 dry-run 检查 JSON repair manifest，确认 current uncovered failure 的真实原因，再按 runbook 执行受控清理。
- 本模块不逐个证明所有业务页面对 `refreshing/stale/missing/failed` 的 UI 行为；后续页面模块闭环必须补齐。
- 本模块不验证真实 Redis/RabbitMQ 网络和 worker drain；runtime-workers 与 operations/staging 覆盖。
- `server.py` 仍有 legacy route 分发；每个业务模块需要继续确认 route 是否走 `ReadModelQueryGateway` 或等价 freshness boundary。
