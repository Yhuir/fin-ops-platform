# 税金抵扣模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：税金抵扣页面读取 `tax_offset` read model，通过 query service/gateway 保证 scoped freshness。
- 当前缺口：税金导入、认证、计划、worker cache warmup 与页面查询耦合较多，变更时必须明确影响面。
- 旧代码删除条件：旧 service/cache 路径不再被 API 或 worker 引用，并有 SQL runtime/e2e 回归。

## 职责边界

### 负责

- 税金抵扣页面查询、认证导入、抵扣计划、税金 read model。
- `tax_offset` scoped incremental projection。
- 与成本统计共享 cost/tax projection worker 时保持独立 scope。
- 抵扣计划保存和认证导入直接确认路径返回 `tax_offset` write target envelope，前端保存/导入后优先等待服务端返回的 operation barrier targets。

### 不负责

- 不拥有成本统计 parent rollup。
- 不直接处理关联台关系事实写入。
- 不在页面里绕过 freshness gate 读取旧缓存。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/筛选 | `TaxOffsetPage.tsx`、`features/tax/api.ts` | 进入 tax offset API/query service |
| 税金导入/认证 | tax certified import services | 写后触发受影响 tax_offset scope；直接确认响应必须返回 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` |
| 抵扣计划保存 | `TaxOffsetPlanService.save_plan(...)` | 验证 source versions 后保存计划，并返回当前月份 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` |
| Refresh scope | `tax_offset` manifest | month or `all`；`all` 是 fan-out command |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 税金抵扣 rows/summary | 前端页面 | query gateway 后 fresh/status |
| 导入/认证结果 | API/worker | 返回 job/result 并触发 dirty scope；同步完成时前端优先等待响应 targets |
| 计划保存结果 | 前端页面 | 保存成功后等待 `read_model_key=tax_offset`、`scope_key=<month>` fresh，再刷新页面数据 |
| Dirty scope | runtime queue | `tax_offset.read_model.refresh` |

## 持久化与投影

- Read model：`tax_offset`
- Projection：`partitioned_scoped_incremental`
- Worker：`tax-offset`，辅助 `cost-tax`
- Query owner：`TaxOffsetQueryService`
- Repository owner：`TaxOffsetReadModelRepositoryPort`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/TaxOffsetPage.tsx` |
| Frontend feature/components | `web/src/features/tax/*`、`web/src/components/tax/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_tax.py` |
| Backend service | `tax_offset_service.py`、`tax_offset_query_service.py`、`tax_offset_runtime_service.py`、`tax_offset_plan_service.py`、`tax_offset_read_model_service.py` |
| Import services | `tax_certified_import_service.py`、`tax_certified_import_application_service.py`、`tax_certified_import_job_service.py` |
| Repository / SQL | `tax_offset_read_model_repository.py`、`cost_tax_sql_projection.py` |
| Worker/read model | `tax_offset_read_model_refresh.py`、`tax_offset_derived_lifecycle_executor.py`、`tax_offset_cache_warmup_executor.py`、`tax_offset_worker_rebuild_executor.py` |
| Tests | `tests/test_tax_offset*.py`、`web/src/test/Tax*.test.*`、`web/e2e/tax-offset-flow.spec.ts` |

## 依赖方向

- 允许依赖：cost/tax projection, read model query gateway, certified import job service。
- 必须通过：TaxOffsetQueryService for reads, application/import service for writes。
- 禁止绕过：直接 SQL 写 read model；把成本统计 parent aggregate 当成税金事实源。

## 测试与验证

- `tests/test_tax_offset_sql_runtime.py`
- `tests/test_tax_offset_api.py`
- `tests/test_tax_offset_read_model_service.py`
- `web/src/test/TaxOffsetPage.test.tsx` 覆盖保存/认证导入后 barrier 等待和刷新。
- `web/e2e/tax-offset-flow.spec.ts`

## 当前缺口和删除条件

- cache warmup/rebuild worker 变更必须同步 runtime registry 和 deploy env。
- 删除旧 cache/read path 前必须证明页面不会读 stale 数据。
- 队列化认证导入的 job result 若未来暴露给页面刷新，也必须携带与直接确认路径等价的 `tax_offset` operation barrier targets。

## Canonical facts ownership

- Owned facts: `app.tax_certified_import_sessions`、`app.tax_certified_import_batches`、`app.tax_certified_import_records`、`app.tax_offset_plans`。
- Allowed writes: certified import confirm、tax plan service、tax offset application service。
- Allowed reads: tax query/application service、tax certified import repository/read ports。
- Downstream outputs: tax_offset、cost_statistics、invoice_lifecycle dirty scopes 或 owner producer 输出。
- Forbidden paths: 其它模块不得直接写认证抵扣或计划表；tax read model 不得反向成为抵扣事实源。
- Old code deletion: 旧认证抵扣 snapshot、旧计划 fallback 和直接 SQL 写税金事实路径必须删除；migration/audit/rollback 工具保留不算 closure。
