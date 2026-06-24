# Read Model 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- read model refresh 入队前由统一 scope policy/gateway 负责 normalize、validate 和 dedupe；`RuntimeQueueRepository` 继续只负责 PostgreSQL durable queue 持久化。
- 生产旧 runtime 状态的 scope contract 检查/清理由 `ReadModelScopeContractService` 编排，SQL 限定在 `PostgresReadModelScopeContractRepository`，清理后通过 `ReadModelRefreshGateway` 补投规范 replacement scope。
- RabbitMQ real consumers 只负责 transport/wakeup；`job.outbox_events`、`job.read_model_dirty_scopes` 与 `read_model.app_status_readiness` 仍是 read model 状态事实源。Redis payload 只能在 fresh gate 后缓存。
- App Status read model registry、runtime worker registry、migration storage contract、critical SLO smoke 和 deploy env 模板必须通过本地测试交叉约束；新增 read model 不能只登记一个 registry。
- authenticated HTTP SLO gate 的当前 P2/P3 默认目标是首屏 API p95 <= 1000ms，并且必须同时满足 HTTP status、latency 和 freshness：任何 `read_model_status != fresh` 或 `refresh_enqueued=true` 都算失败，不能把快速返回的 refreshing 当作“已同步”。写操作同步门禁使用 operation-to-fresh p95 <= 1000ms、p99 <= 3000ms；历史 5 秒记录仅作为旧基线，不作为当前 closure 上限。
- `bank_detail:all` 不是可读 freshness scope，而是 fan-out 控制 scope；真实 readiness 和 downstream dependency 应以具体月份 shard 或明确 read model status 为准。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-24 - Cost statistics derived lifecycle executor extraction

- 目标：执行 `read-models:cost-statistics-derived-lifecycle-executor-port-extraction`，将成本统计 derived lifecycle executor 从 `Application` 拆到显式 service。
- 影响范围：新增 `CostStatisticsDerivedLifecycleExecutor`、调整 `Application` lifecycle registry/factory、增加 executor unit tests 和 platform runtime boundary guard；不改变成本统计 API/read model/worker/cache 语义。
- 关键决策：成本统计 derived lifecycle 现在由 service 拥有 scope extraction、`pending_invoice_rules_changed` `persist_empty=False`、runtime invalidation、no-warmup generic refresh fallback、metadata propagation 和 `enqueued_jobs` accounting；`Application._derived_lifecycle_cost_statistics_executor(...)` 已删除。
- 文档影响：新增 implementation analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt 和 cost/read-model tests notes。
- 测试覆盖：新增 `tests/test_cost_statistics_derived_lifecycle_executor.py`；新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_cost_statistics_derived_lifecycle_uses_explicit_executor_boundary`。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-derived-lifecycle-executor-port-extraction.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；下一轮必须重新审计 cost statistics local closure。
- 后续事项：执行 `read-models:cost-statistics-post-derived-local-implementation-closure-audit`；Go admission 继续 blocked。

## 2026-06-24 - Cost statistics freshness and barrier audit

- 目标：执行 `read-models:cost-statistics-refresh-freshness-operation-barrier-audit`，审计成本统计 fresh gate、force refresh、parent aggregate、operation barrier、compat worker 和 app-owned helper surface。
- 影响范围：`CostStatisticsQueryService`、`CostStatisticsRuntimeService`、`CostStatisticsReadModelRefreshService`、`CostStatisticsSqlProjectionBuilder`、`Application._derived_lifecycle_cost_statistics_executor(...)`、runtime worker/App Status/scope policy/read model tests、modular IO state；不改变运行时代码。
- 关键决策：现有代码/测试已覆盖 SQL fresh gate、production SQL repository unavailable、scope normalize/validate、parent aggregate from materialized shards、parent waits for missing/stale shards、primary `cost-statistics` worker 与 `cost-tax` compat lane。审计发现本地 implementation gap：`Application._derived_lifecycle_cost_statistics_executor(...)` 仍拥有 cost statistics derived lifecycle invalidation、warmup-vs-refresh fallback 和 `enqueued_jobs` accounting。
- 文档影响：新增 freshness/barrier audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮是 analysis/accounting only；下一轮必须新增/更新 derived lifecycle executor/static guard tests，并复跑 cost statistics runtime/read model tests。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-refresh-freshness-operation-barrier-audit.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；cost statistics derived lifecycle executor extraction 是下一条本地实现边界。
- 后续事项：执行 `read-models:cost-statistics-derived-lifecycle-executor-port-extraction`；Go admission 继续 blocked。

## 2026-06-24 - Cost statistics repository port extraction

- 目标：执行 `read-models:cost-statistics-repository-port-extraction`，为成本统计建立窄 read model repository port。
- 影响范围：`CostStatisticsReadModelRepositoryPort`、`CostStatisticsSqlProjectionBuilder`、`PostgresStateStore.cost_statistics_sql_read_repository`、成本统计 SQL runtime/state-store tests、modular IO state；不改变成本归因、API、UI、worker event、queue、Redis 合同或 parent aggregate 语义。
- 关键决策：新增 port 只暴露 `load_cost_statistics_read_models`、`get_cost_statistics_view`、`save_cost_statistics_read_models`。SQL/table knowledge 继续留在 `PostgresReadModelRepository`；projection builder 和 SQL read wiring 只持有窄 port。
- 文档影响：新增 repository port extraction analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：新增 cost statistics port guard，扩展 PostgresStateStore optional read connection 测试；复跑目标 SQL projection parent/month tests。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-repository-port-extraction.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；cost statistics freshness/barrier 和 app-owned helper audit 仍是下一边界。
- 后续事项：执行 `read-models:cost-statistics-refresh-freshness-operation-barrier-audit`；Go admission 继续 blocked。

## 2026-06-24 - Cost statistics selected after tax offset

- 目标：执行 `read-models:next-pilot-selection-after-tax-offset`，在 `tax_offset` 本地支持 accounted 后选择下一个非 Go modular IO/read model pilot。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、read-models/cost-statistics 实施记录和测试矩阵；不改运行时代码。
- 关键决策：选择 `cost_statistics`。理由是成本统计有高跨页 stale-read 风险、特殊 `active/all` scope grammar、queryable parent aggregate、旧 `cost-tax` compatibility worker lane，且 manifest 已定义窄 repository port contract，适合以 `CostStatisticsReadModelRepositoryPort` 抽取为首切。
- 文档影响：新增 next-pilot selection analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮是 analysis/accounting only；下一轮必须新增/更新 cost statistics repository port guard，并复跑目标 SQL runtime/freshness 测试。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-tax-offset.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；Go/Fiber/Go Worker admission 继续 blocked。
- 后续事项：执行 `read-models:cost-statistics-repository-port-extraction`。

## 2026-06-24 - Tax offset post-full-state local closure audit

- 目标：执行 `read-models:tax-offset-post-full-state-local-implementation-closure-audit`，复核 full-state snapshot quarantine 后 `tax_offset` 是否还存在本地 implementation gap。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、read-models/tax-offset 实施记录和测试矩阵；不改变 tax business/API/UI/worker event/queue/Redis 合同。
- 关键决策：未发现新的本地 implementation gap。`tax_offset` 本地支持在 repository port、fresh gate、force refresh、operation barrier、worker rebuild executor、derived lifecycle executor、cache warmup executor、explicit persistence 和 full-state snapshot quarantine 方面已 accounted；但模块不标记 closed。
- 文档影响：新增 post-full-state local closure audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮是 analysis/accounting only，无运行时代码变化；既有 `tests/test_tax_offset_sql_runtime.py`、`tests/test_tax_offset_worker_rebuild_executor.py`、`tests/test_tax_offset_derived_lifecycle_executor.py`、`tests/test_tax_offset_cache_warmup_executor.py`、`tests/test_platform_runtime_boundary_guards.py` 和 `tests/test_read_model_architecture_guards.py` 构成本地证据。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-post-full-state-local-implementation-closure-audit.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；这不是 module closure。
- 后续事项：执行 `read-models:next-pilot-selection-after-tax-offset`，选择下一个非 Go modular IO/read model pilot；Go admission 继续 blocked。

## 2026-06-24 - Tax offset full-state snapshot quarantine

- 目标：执行 `read-models:tax-offset-full-state-read-model-snapshot-quarantine`，移除 broad `_persist_state(...)` 对 `tax_offset_read_models` 的旧全量状态写入。
- 影响范围：`Application._persist_state(...)`、read model architecture guard、modular IO state；不改变 tax business/API/UI/worker event/queue/Redis 合同。
- 关键决策：`_persist_state(...)` 不再 serializes `tax_offset_read_models`，避免 broad full-state snapshot 成为 read model 第二写入路径。显式 `_persist_tax_offset_read_models_best_effort(...)` 仍作为 runtime/executor persistence dependency 保留；`TaxOffsetReadModelService.from_snapshot(...)` 仍作为 local/Mongo compatibility load path 保留。
- 文档影响：新增 full-state snapshot quarantine analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：扩展 `tests/test_read_model_architecture_guards.py`，新增 guard 证明 `_persist_state(...)` 不再包含 `tax_offset_read_models` 或 `_tax_offset_read_model_service.snapshot()`，且显式 persistence helper 仍存在。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-full-state-read-model-snapshot-quarantine.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。下一条边界是 `read-models:tax-offset-post-full-state-local-implementation-closure-audit`。

## 2026-06-24 - Tax offset final local closure audit found full-state snapshot gap

- 目标：执行 `read-models:tax-offset-final-local-implementation-closure-audit`，复核 cache warmup executor 之后 `tax_offset` 是否只剩生产证据缺口。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、read-models/tax-offset 实施记录；不改 tax business/API/UI/worker event/queue/Redis 合同。
- 关键决策：不能 defer。`Application._persist_state(...)` 仍把 `tax_offset_read_models` 写入 broad full-state snapshot，属于旧全量状态链路写 read model snapshot 的本地 implementation gap；显式 runtime/executor persistence callback 应保留，但 broad `_persist_state(...)` 不应继续成为第二写入路径。
- 文档影响：新增 final local closure audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮是 analysis/accounting only，无运行时代码变化；下一轮 `read-models:tax-offset-full-state-read-model-snapshot-quarantine` 必须新增/更新 static guard，证明 `_persist_state(...)` 不再 serializes `tax_offset_read_models`。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-final-local-implementation-closure-audit.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred，但不能用于绕过本地 full-state snapshot gap。
- 后续事项：执行 `read-models:tax-offset-full-state-read-model-snapshot-quarantine`；Go admission 继续 blocked。

## 2026-06-24 - Tax offset cache warmup executor extraction

- 目标：执行 `read-models:tax-offset-cache-warmup-executor-port-extraction`，把 optional tax offset cache warmup scheduling/job execution 从 `Application` 迁到显式 executor。
- 影响范围：`TaxOffsetCacheWarmupExecutor`、tax offset runtime warmup callback wiring、app cache warmup thin delegate、read model architecture guards、modular IO state；不改变 tax business/API/UI/worker event/queue/schema/Redis 合同。
- 关键决策：`TaxOffsetCacheWarmupExecutor` 现在负责 env gating、month normalize/reverse sort、idempotent background job contract、run-job progress/success/partial-success、month payload load、read model upsert 和 snapshot persistence。`Application._schedule_tax_offset_cache_warmup(...)` 保留为 compat-only thin delegate，`_run_tax_offset_cache_warmup_job(...)` 和 `_tax_offset_cache_warmup_enabled(...)` 已删除并 guarded。
- 文档影响：新增 cache warmup executor extraction analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt；共享 read model 状态机定义不变。
- 测试覆盖：新增 `tests/test_tax_offset_cache_warmup_executor.py`；扩展 `tests/test_read_model_architecture_guards.py`；复跑 tax offset cache warmup API 目标测试。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-cache-warmup-executor-port-extraction.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。下一条边界是 `read-models:tax-offset-final-local-implementation-closure-audit`。

## 2026-06-24 - Tax offset post-derived closure audit found cache warmup gap

- 目标：执行 `read-models:tax-offset-post-derived-local-implementation-closure-audit`，确认 repository port、freshness/barrier、worker rebuild executor 和 derived lifecycle executor 后，`tax_offset` 是否可进入 local support accounted / production evidence deferred。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、read-models/tax-offset 实施记录；不改 tax business/API/UI/worker event/queue/Redis 合同。
- 关键决策：不能 defer。`Application._schedule_tax_offset_cache_warmup(...)` / `_run_tax_offset_cache_warmup_job(...)` 仍拥有可选 cache warmup job scheduling/execution、month payload build、`TaxOffsetReadModelService.upsert_read_model(...)` 和 snapshot persistence 行为；这不是纯 dependency assembly。
- 文档影响：新增 post-derived local closure audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮是 analysis/accounting only，无运行时代码变化；下一轮 `read-models:tax-offset-cache-warmup-executor-port-extraction` 必须新增 executor/service 测试和静态 guard。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-post-derived-local-implementation-closure-audit.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred，但不能用于绕过本地 cache warmup implementation gap。
- 后续事项：执行 `read-models:tax-offset-cache-warmup-executor-port-extraction`；Go admission 继续 blocked。

## 2026-06-24 - Tax offset derived lifecycle executor extraction

- 目标：执行 `read-models:tax-offset-derived-lifecycle-executor-boundary-audit`，把 tax offset derived lifecycle read model/cache execution 从 `Application` 迁到显式 executor。
- 影响范围：`TaxOffsetDerivedLifecycleExecutor`、tax offset derived lifecycle registry wiring、platform runtime boundary guard 和 modular IO state；不改变 tax business/API/UI/worker event/queue/schema/SQL projection builder/Redis 合同。
- 关键决策：`TaxOffsetDerivedLifecycleExecutor.execute_read_model(...)` 维护 read model invalidation result shape；`execute_month_cache(...)` 维护 month extraction 和 cache clear result shape。`Application` 只通过 `_tax_offset_derived_lifecycle_executor()` 组装 runtime service 与 cache clearer，旧 app-owned helper 方法已删除并 guarded。
- 文档影响：新增 derived lifecycle executor analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt；共享 read model 状态机定义不变。
- 测试覆盖：新增 `tests/test_tax_offset_derived_lifecycle_executor.py`；扩展 `tests/test_platform_runtime_boundary_guards.py`；复跑 derived lifecycle service 回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-derived-lifecycle-executor-boundary-audit.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。下一条边界是 `read-models:tax-offset-post-derived-local-implementation-closure-audit`。

## 2026-06-24 - Tax offset worker rebuild executor extraction

- 目标：执行 `read-models:tax-offset-worker-rebuild-executor-port-extraction`，把 `Application.rebuild_tax_offset_read_model_scope(...)` 中的 app-owned worker rebuild 行为迁出到显式 executor/service boundary。
- 影响范围：`TaxOffsetWorkerRebuildExecutor`、tax offset app service assembly、tax offset read model persistence/fresh cache publishing tests、read model architecture guards 和 modular IO state；不改变 tax business/API/UI/worker event/queue/schema/SQL projection builder 合同。
- 关键决策：`TaxOffsetWorkerRebuildExecutor` 现在负责 month scope validation、payload loader、source-version lookup、read model upsert、snapshot persistence、fresh Redis month/summary cache envelope publish 和 `scope_key`/`month`/`entry_count` result。`Application.rebuild_tax_offset_read_model_scope(...)` 保留为 compat-only thin delegate。
- 文档影响：新增 worker rebuild executor extraction analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt；共享 read model 状态机定义不变。
- 测试覆盖：新增 `tests/test_tax_offset_worker_rebuild_executor.py`；扩展 `tests/test_read_model_architecture_guards.py` 的 direct fresh allowlist 和 thin delegate guard；复跑 tax offset API/SQL runtime/read model architecture guard 目标测试。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-worker-rebuild-executor-port-extraction.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。下一条边界是 `read-models:tax-offset-derived-lifecycle-executor-boundary-audit`。

## 2026-06-24 - Tax offset local closure audit found worker rebuild gap

- 目标：执行 `read-models:tax-offset-local-implementation-closure-audit`，确认税金抵扣本地实现支持是否可进入 production evidence defer。
- 影响范围：modular IO analysis/state/queue/next prompt、read-models/tax-offset 实施记录和测试矩阵；不改 tax business/API/UI/worker event/queue/Redis 合同。
- 关键决策：不能 defer。`Application.rebuild_tax_offset_read_model_scope(...)` 仍包含 app-owned worker rebuild、read model persistence 和 fresh Redis month/summary cache publish 行为；这比普通 compat wrapper 更重，必须先抽成显式 executor/service boundary。
- 文档影响：新增 local closure audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮是 analysis/accounting only，无运行时代码变化；下一轮 `read-models:tax-offset-worker-rebuild-executor-port-extraction` 必须新增 executor/service 测试和静态 guard。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-local-implementation-closure-audit.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred，但不能用于绕过本地 app-owned rebuild gap。
- 后续事项：执行 `read-models:tax-offset-worker-rebuild-executor-port-extraction`；Go admission 继续 blocked。

## 2026-06-24 - Tax offset freshness / operation barrier audit

- 目标：执行 `read-models:tax-offset-refresh-freshness-operation-barrier-audit`，审计 `tax_offset` fresh gate、force refresh、all fan-out、operation barrier 和 legacy/app-owned helper 分类。
- 影响范围：`TaxOffsetQueryService`、`TaxOffsetReadModelRefreshService`、scope policy/manifest/worker registration、`TaxOffsetPlanService`、`TaxOffsetPage` operation barrier flow、`FinancialObjectIdentityPolicy` OA 附件发票证据分类和相关测试。
- 关键决策：`tax_offset` SQL reads 继续走 `ReadModelQueryGateway` schema/source-version fresh gate；生产 SQL repository 缺失 fail-closed 为 refreshing/enqueue；`all` 只 fan-out 到月份 shard；计划保存和认证导入前端等待当前月份 operation barrier。审计中发现并修复 OA 附件正式发票 payload 缺 `evidence_type` 时不被 promotion 的缺口：中心 identity policy 现在用 `document_kind` 或 `invoice_type` 判断 formal invoice fallback，显式 receipt/unknown 仍排除。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/tax-offset 实施记录和测试矩阵；共享 read model 状态机定义不变。
- 测试覆盖：新增/更新 `tests/test_object_identity_policy.py`；复跑 tax offset service/API/read model/runtime、refresh gateway、runtime worker scope 和 manifest 目标测试。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-refresh-freshness-operation-barrier-audit.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。下一条边界是 `read-models:tax-offset-local-implementation-closure-audit`。

## 2026-06-24 - Tax offset repository port extraction

- 目标：执行 `read-models:tax-offset-repository-port-extraction`，为 `tax_offset` read model 建立窄 repository port。
- 影响范围：`TaxOffsetReadModelRepositoryPort`、`PostgresStateStore` tax offset read/write wiring、`TaxOffsetSqlProjectionBuilder` tax save path、tax offset SQL runtime/state-store tests 和 modular IO state。
- 关键决策：`TaxOffsetReadModelRepositoryPort` 只暴露 manifest-listed `load_tax_offset_read_models`、`get_tax_offset_view`、`save_tax_offset_read_models`；`PostgresReadModelRepository` 继续作为 SQL/table owner，业务/read model projection 消费侧通过窄 port 隔离。未改变 tax calculation、certified import、plan save、API shape、worker event、Redis 或前端行为。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/tax-offset 实施记录和测试矩阵；共享 read model 状态机定义不变。
- 测试覆盖：新增 `TaxOffsetReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods` 和 `test_projection_builder_saves_tax_scope_through_tax_port`；更新 `PostgresStateStoreTests.test_read_model_repositories_use_optional_read_connection`。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-repository-port-extraction.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。下一条边界是 `read-models:tax-offset-refresh-freshness-operation-barrier-audit`。

## 2026-06-24 - Tax offset selected as next modular IO read model pilot

- 目标：执行 `read-models:next-pilot-selection-after-invoice-lifecycle`，在 `invoice_lifecycle` 本地支持 accounted 后选择下一个非 Go read model 试点。
- 影响范围：modular IO analysis/state/queue/next prompt、read-models/tax-offset 实施记录和测试矩阵；不改运行时代码、SQL、API shape、read model schema、worker 或前端。
- 关键决策：选择 `tax_offset`。它直接消费 invoice lifecycle/certification 状态，plan save、certified import、发票导入和 Workbench relation fan-out 都可能造成用户可见 stale-read；第一条实现边界足够窄，只需围绕 manifest-listed `load_tax_offset_read_models`、`get_tax_offset_view`、`save_tax_offset_read_models` 建立 repository port。
- 文档影响：新增 modular IO selection analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮是 analysis-only slice，无运行时代码变化；下一轮实现必须覆盖 tax offset repository port 不暴露无关 read model 方法，并复跑 tax offset SQL runtime/read model/API 目标测试。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。下一条边界是 `read-models:tax-offset-repository-port-extraction`。

## 2026-06-24 - Invoice lifecycle local implementation closure accounting

- 目标：执行 `read-models:invoice-lifecycle-local-implementation-closure-audit`，确认 `invoice_lifecycle` 在本地可验证范围内是否还有必须先修的实现缺口。
- 影响范围：modular IO analysis/state/queue/next prompt、read-models 实施记录和测试矩阵；不改变 SQL、API、worker、queue schema、lifecycle 规则或前端行为。
- 关键决策：`invoice_lifecycle` 本地支持已 accounted：repository port、facade freshness/non-fresh enqueue、refresh worker all fan-out、source-version before/after checks、manifest/App Status/worker registration、operation barrier exact-month guard、derived lifecycle executor 和 app-owned helper removal 均有证据。真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred，模块不全局关闭，Go admission 继续 blocked。
- 文档影响：新增 modular IO closure audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮是 audit/accounting only，无运行时代码变化，无新增测试；复用 invoice lifecycle facade、refresh、derived executor、operation barrier、manifest、input usage payment-rules 和 static guard 测试作为证据。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。下一条边界是 `read-models:next-pilot-selection-after-invoice-lifecycle`。

## 2026-06-24 - Invoice lifecycle derived lifecycle executor extraction

- 目标：执行 `read-models:invoice-lifecycle-derived-lifecycle-executor-port-extraction`，把 app-owned invoice lifecycle derived lifecycle refresh 执行逻辑抽到显式 executor。
- 影响范围：`InvoiceLifecycleDerivedLifecycleExecutor`、`Application` derived lifecycle domain map、platform runtime boundary guard、invoice lifecycle/domain-events/read-models 文档；不改变 lifecycle 业务规则、payload、source-version、worker event、queue schema、API、前端或生产状态。
- 关键决策：`Application` 只保留依赖组装，向 executor 注入 gateway-backed generic read model refresh callback；scope selection、reason default、metadata filtering、`deleted_counts`、`invalidated_scopes`、`enqueued_jobs` 由 `InvoiceLifecycleDerivedLifecycleExecutor` 维护。旧 `_derived_lifecycle_invoice_lifecycle_executor(...)` 已删除并由静态 guard 防回归。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/domain-events 实施记录和测试矩阵；共享状态机定义不变。
- 测试覆盖：新增 `tests/test_invoice_lifecycle_derived_lifecycle_executor.py`；新增 `PlatformRuntimeBoundaryGuardTests.test_invoice_lifecycle_derived_lifecycle_uses_explicit_executor_boundary`；复跑 derived lifecycle、operation barrier 和 invoice lifecycle refresh 回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-derived-lifecycle-executor-port-extraction.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；下一条边界是 `read-models:invoice-lifecycle-local-implementation-closure-audit`，不能直接声明全局闭环。

## 2026-06-24 - Invoice lifecycle freshness / operation barrier audit

- 目标：执行 `read-models:invoice-lifecycle-refresh-freshness-operation-barrier-audit`，审计 `invoice_lifecycle` 的 fresh gate、force refresh、fan-out `all`、source-version proof、operation barrier 和旧链路污染风险。
- 影响范围：invoice lifecycle facade/refresh/scope-policy/manifest/App Status/worker wiring、operation barrier regression、modular IO state；不改变 lifecycle 业务规则、payload、source-version、worker event、queue schema、API、前端或生产状态。
- 关键决策：`invoice_lifecycle:all` 仍是 fan-out command；facade 没有 queryable all read path，`list_by_month(...)` 要求具体月份，subject/identity lookup 不把 parent `all` 当 fresh proof。`InvoiceLifecycleReadModelRefreshService` 对 `all` 扩展为月份 shards，并在 rebuild 前后检查 source-version currentness。剩余本地实现缺口是 app-owned `_derived_lifecycle_invoice_lifecycle_executor(...)`，该 helper gateway-backed 但应抽成显式 executor。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models 实施记录和测试矩阵；共享 read model/domain-events 状态机定义不变。
- 测试覆盖：新增 `OperationFreshnessBarrierServiceTests.test_invoice_lifecycle_target_uses_exact_month_scope_for_operation_barrier`，证明其它月份 pending outbox 不会阻断当前月份 lifecycle operation barrier target。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-refresh-freshness-operation-barrier-audit.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；下一条边界是 `read-models:invoice-lifecycle-derived-lifecycle-executor-port-extraction`。

## 2026-06-24 - Invoice lifecycle repository port extraction

- 目标：执行 `read-models:invoice-lifecycle-repository-port-extraction`，为 `invoice_lifecycle` read model 建立窄 repository port。
- 影响范围：`InvoiceLifecycleReadModelRepositoryPort`、`InvoiceLifecycleReadFacade` lifecycle row lookup、`InvoiceLifecycleSqlProjectionBuilder` lifecycle save/mark path、invoice lifecycle facade/refresh/manifest tests 和 modular IO state。
- 关键决策：facade 和 SQL projection builder 不再直接消费 broad read repository lifecycle 方法；它们通过 `InvoiceLifecycleReadModelRepositoryPort` 访问 manifest-listed 方法。没有新增 `PostgresStateStore.invoice_lifecycle_sql_read_repository` property，因为当前没有既有 property、construction path 或 caller，需要避免 speculative API。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models 实施记录和测试矩阵；共享 read model 状态机定义不变。
- 测试覆盖：新增 `InvoiceLifecycleReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods`；复跑 invoice lifecycle facade、refresh 和 manifest 回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-repository-port-extraction.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；invoice lifecycle freshness/barrier/legacy live path audit 仍是下一步。

## 2026-06-24 - Invoice lifecycle selected as next modular IO read model pilot

- 目标：执行 `read-models:next-pilot-selection-after-output-invoice-collection`，在销项收款本地实现支持 accounted 后选择下一个非 Go read model 试点。
- 影响范围：modular IO analysis/state/queue/next prompt、read-models 实施记录和测试矩阵；不改运行时代码、API shape、read model schema、worker 或前端。
- 关键决策：选择 `invoice_lifecycle`。它是 pending invoice、input/output usage、OA pending payment、tax offset、cost/search 和 import fan-out 的共享生命周期状态边界；第一条实现边界是 `read-models:invoice-lifecycle-repository-port-extraction`。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt；共享 read model 状态机定义不变。
- 测试覆盖：本轮是 analysis-only slice，无运行时代码变化；下一轮实现必须覆盖 invoice lifecycle repository port 不暴露无关 read model 方法，并复跑 read facade、refresh、manifest 和 page integration 回归。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：未连接真实 PostgreSQL/worker/App Status/high-row/browser；本轮只选择下一试点，不证明 `invoice_lifecycle` 闭环。

## 2026-06-24 - Output invoice collection local implementation closure accounting

- 目标：执行 `read-models:output-invoice-collection-local-implementation-closure-audit`，确认销项收款 read model 本地实现支持是否可进入 production evidence defer。
- 影响范围：modular IO analysis/state/queue/next prompt、read-models/output-invoice-collections 实施记录和测试矩阵；不改变 SQL、API、worker、queue schema、lifecycle、receipt、红蓝票关系或前端行为。
- 关键决策：`output_invoice_collection` 本地支持已 accounted：repository port、rows/filter/export/detail fresh gate、source-version proof、scope policy、worker fan-out、operation barrier、app-level projection helper removal、legacy/live path classification 和测试/文档证据均已记录。真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred，模块不全局关闭，Go admission 继续 blocked。
- 文档影响：新增 modular IO closure audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮无运行时代码变更，无新增测试；复用 output collection API/runtime/architecture guard/frontend/Browser 覆盖作为审计证据。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。下一条边界是 `read-models:next-pilot-selection-after-output-invoice-collection`。

## 2026-06-24 - Output invoice collection relation detail production fail-closed

- 目标：执行 `read-models:output-invoice-collection-relation-detail-production-repository-fail-closed`，补齐销项收款 relation detail 的生产 SQL read-model fail-closed 边界。
- 影响范围：`OutputInvoiceCollectionReadModelDetailService`、`OutputInvoiceCollectionReadModelRepositoryPort`、`PostgresReadModelRepository` output row-id lookup、`OutputInvoiceCollectionApiRoutes`、`Application._get_output_invoice_collection_relation_details_from_sql_read_model(...)`、read-model manifest、output/read-models 测试矩阵和 modular IO state。
- 关键决策：`output_invoice_collection` relation detail 在生产 SQL runtime 下不得 live rebuild；缺 SQL detail repository/lookup 时返回 `202`/refreshing 并通过 gateway enqueue `output_invoice_collection:all`。fresh SQL detail row 使用同一 payload builder，保持 relation detail response shape。
- 文档影响：新增 modular IO analysis，更新 read-models/output-invoice-collections 实施记录、状态机、测试矩阵、autonomous state/queue/next prompt 和主控 prompt。
- 测试覆盖：新增 API contract tests 覆盖 production fail-closed 和 fresh SQL detail row；扩展 repository port/manifest tests 登记 `get_output_invoice_collection_row_by_row_id(...)`。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-relation-detail-production-repository-fail-closed.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。下一条边界仍是 `read-models:output-invoice-collection-local-implementation-closure-audit`。

## 2026-06-24 - Output invoice collection freshness / operation barrier audit

- 目标：执行 `read-models:output-invoice-collection-refresh-freshness-operation-barrier-audit`，核对销项收款 read model fresh gate、force refresh、all fan-out、operation barrier 和旧 helper 分类。
- 影响范围：`OutputInvoiceCollectionLifecycleService`、`OutputInvoiceCollectionReceiptService`、前端 output collection mutation API mapper、页面/抽屉 write-after-read barrier、`Application` app-level output projection helper 和相关测试。
- 关键决策：output collection mutation response 必须返回 `read_model_scope_keys` 和 `freshness_targets`；前端优先等待具体月份 `output_invoice_collection:<YYYY-MM>`，避免 default all-view 写后只等待 fan-out-only `all`。旧 app-level output projection helper 无生产调用者，删除并以 architecture guard 防回归；真实 worker projection owner 继续是 `InvoiceUsageCollectionSqlProjectionBuilder`。
- 文档影响：新增 modular IO analysis，更新 read-models/output-invoice-collections 实施记录、状态机、测试矩阵、autonomous state/queue/next prompt 和主控 prompt。
- 测试覆盖：更新 lifecycle/API/frontend tests 并新增 architecture guard，覆盖 mutation response target、concrete-month operation barrier 和旧 helper removal。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-refresh-freshness-operation-barrier-audit.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。下一条边界是 `read-models:output-invoice-collection-local-implementation-closure-audit`。

## 2026-06-24 - Output invoice collection repository port extraction

- 目标：执行 `read-models:output-invoice-collection-repository-port-extraction`，为销项发票收款 read model 建立窄 repository port。
- 影响范围：`OutputInvoiceCollectionReadModelRepositoryPort`、`PostgresStateStore.output_invoice_collection_sql_read_repository`、`InvoiceUsageCollectionSqlProjectionBuilder` output collection save/mark/prune wiring、invoice usage collection SQL runtime tests 和 output/read-models 测试矩阵。
- 关键决策：`OutputInvoiceCollectionReadModelRepositoryPort` 只暴露 manifest-listed output 方法，不能暴露 input usage、OA pending payment、pending invoice 或 Workbench relation source-version 方法。app-level output projection helper 暂不在本 repository-port slice 删除，进入下一条 freshness/helper audit 分类。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/output-invoice-collections 实施记录和测试矩阵；状态机定义不变。
- 测试覆盖：新增 `OutputInvoiceCollectionReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods`；复跑 invoice usage collection SQL runtime、output API、Postgres state-store read connection 和 app check。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-repository-port-extraction.md`。
- 未测风险：output freshness/helper audit、真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 pending/deferred；模块未全局关闭。

## 2026-06-24 - Output invoice collection next pilot selection

- 目标：执行 `read-models:next-pilot-selection-after-input-invoice-usage`，在进项发票使用本地实现支持 accounted 后选择下一个非 Go read model 试点。
- 影响范围：modular IO analysis/state/queue/next prompt、read-models 和 output-invoice-collections 实施记录；不改运行时代码、API shape、read model schema、worker 或前端。
- 关键决策：选择 `output_invoice_collection`。它是 invoice-usage-collection 页面族里剩余的高风险 read model，涉及 rows/filter/export/detail、lifecycle overlay、receipt facts、红蓝票关系和跨页面同步；第一条实现边界是 `read-models:output-invoice-collection-repository-port-extraction`。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt；共享 read model 状态机定义不变。
- 测试覆盖：本轮是 analysis-only slice，无运行时代码变化；下一轮实现必须覆盖 output repository port 不暴露无关 read model 方法、projection save/mark/prune、rows/filter/export/detail fresh gate 和 existing feature regression。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：未连接真实 PostgreSQL/worker/App Status/high-row/browser；本轮只选择下一试点，不证明 `output_invoice_collection` 闭环。

## 2026-06-24 - Input invoice usage local implementation closure accounting

- 目标：执行 `read-models:input-invoice-usage-local-implementation-closure-audit`，确认进项发票使用 read model 本地实现支持是否可进入 production evidence defer。
- 影响范围：modular IO analysis/state/queue/next prompt、read-models/input-invoice-usage 实施记录和测试矩阵；不改变 SQL、API、worker、queue schema、OA reverse、支付规则或前端行为。
- 关键决策：`input_invoice_usage` 本地支持已 accounted：repository port、route fresh gate、relation-detail fresh gate、source-version proof、scope policy、worker fan-out、operation barrier、legacy projection helper removal 和测试/文档证据均已记录。真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred，模块不全局关闭，Go admission 继续 blocked。
- 文档影响：新增 modular IO closure audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮无运行时代码变更，无新增测试；复用 input usage API/runtime/architecture guard、frontend 和 Browser 覆盖作为审计证据。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。

## 2026-06-24 - Input invoice usage relation detail production repository fail-closed

- 目标：修复进项发票使用 relation detail 在生产 SQL runtime 缺 repository 时可能绕过 read model fresh gate 的缺口。
- 影响范围：`Application._get_input_invoice_usage_relation_details_from_sql_read_model(...)`、`InputInvoiceUsageReadModelDetailService` 和 input usage API tests；不改 read model schema、worker、queue schema、OA reverse 或前端行为。
- 关键决策：rows/filter/export 已有生产 fail-closed guard；relation detail 也必须等价执行。缺 `get_input_invoice_usage_row_by_row_id(...)` 时返回 `202`/refreshing 并入队 `input_invoice_usage:all`，不能 live rebuild 详情。
- 文档影响：新增 modular IO analysis，更新 read-models/input-invoice-usage 实施记录、input usage 测试矩阵和 autonomous state/queue/next prompt；共享 read model 状态定义不变。
- 测试覆盖：新增 `tests/test_input_invoice_usage_api.py::InputInvoiceUsageApiTests::test_relation_details_require_sql_repository_in_production_without_live_rebuild`；复跑 detail fresh/source-version 和 rows fail-closed 回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-input-invoice-usage-relation-detail-production-repository-fail-closed.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。

## 2026-06-24 - Input invoice usage freshness / operation barrier audit

- 目标：执行 `read-models:input-invoice-usage-refresh-freshness-operation-barrier-audit`，核对进项发票使用 read model fresh gate、force refresh、all fan-out、source-version proof、operation barrier 和旧 helper 分类。
- 影响范围：删除 `Application` 上未使用的 input usage rebuild/list/mark projection helper；真实 worker/projection 路径继续由 `InvoiceUsageCollectionReadModelRefreshService`、`InvoiceUsageCollectionSqlProjectionBuilder` 和 `InputInvoiceUsageReadModelRepositoryPort` 承担。
- 关键决策：旧 app-level rebuild 路径没有运行时调用者且会绕开 worker projection builder 直接 live query/save read model，删除优于 compat-only 保留。`input_invoice_usage:all` 继续是 fan-out control scope；all-query freshness proof 来自 month rows/scopes 和 dirty/outbox 状态。
- 文档影响：新增 modular IO analysis，更新 read-models/input-invoice-usage 实施记录、input usage 测试矩阵和 autonomous state/queue/next prompt；共享 read model 状态定义不变。
- 测试覆盖：`tests/test_read_model_architecture_guards.py` 新增 removed-helper guard；invoice usage collection SQL runtime 和 input usage API tests 继续覆盖真实 worker builder、fresh gate、source-version、all fan-out 和 relation detail 行为。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-input-invoice-usage-refresh-freshness-operation-barrier-audit.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。

## 2026-06-24 - Input invoice usage repository port extraction

- 目标：执行 `read-models:input-invoice-usage-repository-port-extraction`，为进项发票使用 read model 建立窄 repository port。
- 影响范围：`InputInvoiceUsageReadModelRepositoryPort`、`PostgresStateStore.input_invoice_usage_sql_read_repository`、`InvoiceUsageCollectionSqlProjectionBuilder` input usage save/mark/prune wiring、runtime worker builder wiring和 invoice usage collection SQL runtime tests。
- 关键决策：`list_input_invoice_usage_scope_shards(...)` 是 source-fact 月份枚举，不属于 manifest repository port contract；保留在 projection builder fan-out 边界。repository port 只暴露 rows/detail/save/mark/prune。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/input-invoice-usage 实施记录和测试矩阵；状态机定义不变。
- 测试覆盖：新增 `InputInvoiceUsageReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods`；复跑 input usage API/projection/freshness 相关目标回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-input-invoice-usage-repository-port-extraction.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；input usage freshness/barrier/helper audit 仍是下一步。

## 2026-06-24 - Input invoice usage next pilot selection

- 目标：执行 `read-models:next-pilot-selection-after-oa-pending-payment`，在 OA 待付款本地实现支持 accounted 后选择下一个非 Go read model 试点。
- 影响范围：modular IO analysis/state/queue/next prompt、read-models 实施记录；不改运行时代码、API shape、read model schema、worker 或前端。
- 关键决策：选择 `input_invoice_usage`。它与 OA 待付款共享 `invoice-usage-collection` worker/projection builder，同时有高 stale-read/cross-page relation 风险；第一条实现边界是 `read-models:input-invoice-usage-repository-port-extraction`。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt；共享 read model 状态机定义不变。
- 测试覆盖：本轮是 analysis-only slice，无运行时代码变化；下一轮实现必须覆盖 input usage port 不暴露无关 read model 方法、rows/detail/filter/export freshness、projection save/mark/prune 和 existing feature regression。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：未连接真实 PostgreSQL/worker/App Status/high-row/browser；本轮只选择下一试点，不证明 `input_invoice_usage` 闭环。

## 2026-06-24 - OA pending payment local implementation closure audit

- 目标：执行 `read-models:oa-pending-payment-local-implementation-closure-audit`，确认 OA 待付款 read model 的 repository port、fresh gate、source-version proof、scope policy、worker fan-out、operation barrier 和 legacy contamination 是否本地闭合。
- 影响范围：删除 `Application` 上 OA pending payment 专属旧 rebuild/list/mark/live helper；真实 worker/projection 路径继续由 `InvoiceUsageCollectionReadModelRefreshService`、`InvoiceUsageCollectionSqlProjectionBuilder` 和 `OaPendingPaymentReadModelRepositoryPort` 承担。
- 关键决策：旧 app-level rebuild 路径没有运行时调用者且会绕开 worker projection builder 直接写 read model，删除优于 compat-only 保留；`oa_pending_payment` 本地实现支持可进入 `production-evidence-deferred`，但全局模块 closure 不成立。
- 文档影响：新增 modular IO analysis，更新 read-models/OA pending payments 实施记录、OA 测试矩阵和 autonomous state/queue/next prompt；共享 read model 状态定义不变。
- 测试覆盖：`tests/test_oa_pending_payment_api.py` 新增 removed-helper guard；OA API fresh gate 与 invoice usage collection SQL runtime tests 继续覆盖真实 worker builder 路径。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-oa-pending-payment-local-implementation-closure-audit.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。

## 2026-06-24 - OA pending payment freshness / operation barrier audit

- 目标：执行 `read-models:oa-pending-payment-refresh-freshness-operation-barrier-audit`，审计 OA 待付款 read model fresh gate、force refresh、`all` fan-out/month proof、source-version proof 和写后 operation barrier 行为。
- 影响范围：`OaPendingPaymentsPage` 写后 barrier target 选择、OA pending payment/read-models 文档和 modular IO state；不改后端 API shape、OA 支付状态、OA MySQL 写回、payment-admitted source adapter、pending relation promotion、command service 或 worker event semantics。
- 关键决策：`oa_pending_payment:all` 仍是 fan-out control scope。当 mutation 响应包含具体月份和 `all` 时，前端写后 barrier 必须优先等待具体 `oa_pending_payment:<YYYY-MM>`，不能把 fan-out-only `all` 当作优先可见性证明；没有具体 scope 时才 fallback 到当前 visible scope。
- 文档影响：新增 modular IO analysis，更新 read-models/OA pending payments 实施记录、autonomous queue/state/next prompt；状态机定义不变。
- 测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，覆盖 auto-reconcile 与 link-bank 成功后的具体月份 barrier target。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-oa-pending-payment-refresh-freshness-operation-barrier-audit.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 worker drain、App Status target readiness、high-row HTTP 和 browser smoke 仍需生产证据或 defer accounting。

## 2026-06-24 - Bank detail category side-effect port extraction

- 目标：执行 `read-models:bank-detail-category-side-effect-port-extraction`，把银行明细分类写后的 read model refresh / turnover fan-out / Workbench invalidation / audit 从 `Application` callback 抽到显式 side-effect port。
- 影响范围：`BankDetailCategoryMutationSideEffectPort`、`BankDetailsApplicationService._persist_category_mutation(...)`、`server.py` dependency wiring、read-model/bank-details 测试和 modular IO state；不改变 read model schema、worker、queue schema 或 API response shape。
- 关键决策：side-effect port 通过注入的 gateway-backed callbacks 调度 `bank_detail` affected scopes 和 `turnover_ledger:all`，不直接 SQL 写 `job.outbox_events` / `job.read_model_dirty_scopes`，不写 readiness/cache/App Status。
- 文档影响：新增 analysis，更新 read-models/bank-details 实施记录和测试矩阵；共享 read model 状态机定义不变。
- 测试覆盖：更新 static guard 和 bank detail service/API regression，覆盖旧 Application callback 删除、port 注入、port 行为和 operation barrier 目标保持。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-category-side-effect-port-extraction.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 worker drain 和 enqueue-to-fresh SLO 仍是 production evidence deferred。

## 2026-06-24 - Bank detail server read/cache helper quarantine

- 目标：执行 `read-models:bank-detail-server-helper-quarantine`，移除 `server.py` 中已无调用者的银行明细 read/cache helper，并新增架构 guard 防止旧 read model helper 回归。
- 影响范围：`server.py` dead helper removal、`BankDetailsApplicationService` read/cache owner guard、bank-details/read-models 文档和 modular IO state；不改 read model schema、worker、queue schema 或 API response shape。
- 关键决策：bank detail scope summary、auto-tag freshness、refreshing payload、tag dictionary、Redis cache key/get/set 等 helper 的 owner 是 `BankDetailsApplicationService`。`Application._enqueue_bank_detail_read_model_refreshes(...)` 暂时保留为 gateway-backed wrapper，下一步继续处理 category side-effect callback。
- 文档影响：新增 analysis，更新 read-models/bank-details 实施记录和测试矩阵；共享 read model 状态机定义不变。
- 测试覆盖：新增 `PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary`，覆盖 removed helper 不回归、service owner 存在和 refresh wrapper 不直接 SQL 写 job queue。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-server-helper-quarantine.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 worker drain 和 enqueue-to-fresh SLO 仍是 production evidence deferred。

## 2026-06-24 - Bank detail pilot verification / queue correction

- 目标：执行 `read-models:bank-detail-pilot-verification-and-template-revision`，核对银行明细 read model 试点是否满足模块闭环条件，并修正自动推进 Queue 的下一步。
- 影响范围：modular IO planning state、`bank_detail` read model pilot accounting、后续 `server.py` helper quarantine boundary；不改业务代码、API shape、read model schema、worker 或前端。
- 关键决策：`bank_detail` 试点不能标记为模块闭环；已完成的 repository port、freshness/operation barrier 和旧 SQL helper 删除只是窄实现 slice。`server.py` 仍保留 scope/cache/refresh/callback helper，需要下一步登记 owner/caller/deletion condition，并迁移、删除或隔离为 compat-only/gateway-backed wrapper。
- 文档影响：新增 pilot verification analysis，更新 autonomous state/queue/journal/next prompt 和主控 prompt；全局/模块状态机定义不变。
- 测试覆盖：本轮为 docs/planning/accounting slice，复跑 bank detail targeted API/service/read model/operation barrier 回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-pilot-verification-and-template-revision.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；未证明真实 `bank_detail` worker drain 的 enqueue-to-fresh SLO；剩余 helper 迁移/隔离进入 `read-models:bank-detail-server-helper-quarantine`。

## 2026-06-24 - Bank detail legacy SQL helper removal

- 目标：执行 `read-models:bank-detail-legacy-contamination-removal` 的第一步，删除 `server.py` 上已无生产调用者的 bank detail SQL read compat helper。
- 影响范围：`Application._get_bank_detail_accounts_from_sql_read_model(...)`、`Application._get_bank_detail_transactions_from_sql_read_model(...)`、bank auto tag/read model API 回归测试和 modular IO planning state。
- 关键决策：银行明细读路径只保留 `BankDetailsApiRoutes -> BankDetailsApplicationService` 公共边界；测试不再直接调用 `Application` 私有 SQL helper，并新增 guard 断言旧 helper 不存在。
- 文档影响：同步本实施记录、read model 测试矩阵、bank-details 实施记录和 modular IO analysis/state；read model/runtime worker 状态机语义不变。
- 测试覆盖：更新 `tests/test_bank_auto_tag_rules_api.py`，`test_bank_detail_legacy_sql_helpers_are_removed_from_application_boundary` 证明旧 helper 已从 `Application` 边界移除，相关 freshness 测试改走 route/application public boundary。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v`；`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_bank_auto_tag_rules_api.py`。
- 未测风险：未连接真实 PostgreSQL/Redis/RabbitMQ；`server.py` 仍有 scope/cache/refresh 类 bank detail 兼容 helper，后续 pilot verification 需决定继续拆分或登记 compat-only。

## 2026-06-24 - Bank detail freshness / operation barrier boundary

- 目标：执行 `read-models:bank-detail-refresh-freshness-operation-barrier`，让 BankDetails 写后刷新和强制刷新响应显式返回 `read_model_scope_keys` 与 `freshness_targets`。
- 影响范围：`BankDetailsApplicationService` 分类写操作、自动标签规则重应用响应、`OperationFreshnessBarrierService` bank_detail scope 回归测试、modular IO planning state。
- 关键决策：当有具体月份 scope 时，BankDetails operation barrier target 必须使用 `bank_detail:<YYYY-MM>`，不把 fan-out-only `bank_detail:all` 当作 freshness proof；refresh 入队仍通过 `ReadModelRefreshGateway` 和 scope policy registry。
- 文档影响：同步本实施记录和 modular IO analysis/state；read model/runtime worker 状态机语义不变。
- 测试覆盖：新增 `BankDetailSqlRepositoryTests.test_category_mutation_response_returns_bank_detail_operation_barrier_targets`、`OperationFreshnessBarrierServiceTests.test_bank_detail_target_uses_exact_month_scope_for_operation_barrier`，并更新 `BankAutoTagRulesApiTests.test_reapply_endpoint_enqueues_bank_detail_refresh_without_changing_rules`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_operation_freshness_barrier -v`。
- 未测风险：未连接真实 PostgreSQL/Redis/RabbitMQ；未证明真实 worker drain 的 operation-to-fresh SLO；BankDetails 分类写入前端暂未消费后端返回的 `freshness_targets`。
- 后续事项：推进 `read-models:bank-detail-legacy-contamination-removal`，删除或隔离剩余 `server.py` bank_detail legacy helper。

## 2026-06-24 - Bank detail repository port/query boundary

- 目标：执行 `read-models:bank-detail-repository-port-extraction`，为银行明细 read model 查询侧建立窄 repository port，并把 `server.py` 旧 SQL helper 收敛到 `BankDetailsApplicationService`。
- 影响范围：`backend/src/fin_ops_platform/services/bank_detail_read_model_repository.py`、`PostgresStateStore.bank_detail_sql_read_repository`、`server.py` bank detail compat helper、bank detail SQL/runtime 测试和 planning state。
- 关键决策：`PostgresStateStore.bank_detail_sql_read_repository` 不再直接返回共享 `PostgresReadModelRepository`；旧 `server.py` helper 保留为 `compat-only`，但只能委托 application service，不能直接读 repository。Accounts endpoint 对 `list_bank_account_balances` 的读取能力暂时保留为页面 response shape 兼容，不代表 `bank_account_balance` 模块已并入 `bank_detail`。
- 文档影响：同步本实施记录和 modular IO analysis/state；read model 状态机语义不变。
- 测试覆盖：新增 `BankDetailSqlRepositoryTests.test_bank_detail_read_model_port_excludes_unrelated_read_model_methods`、`BankAutoTagRulesApiTests.test_bank_detail_legacy_sql_helpers_delegate_to_application_service_boundary`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`。
- 未测风险：未连接真实 PostgreSQL/Redis/RabbitMQ；未证明 write -> dirty/outbox -> worker -> operation barrier fresh 的完整闭环。
- 后续事项：推进 `read-models:bank-detail-refresh-freshness-operation-barrier`，再处理 `bank_detail` legacy helper removal/quarantine。

## 2026-06-23 - Legacy read path refresh enqueue 污染守卫

- 目标：执行 `read-models:legacy-read-path-removal-guards`，先把 direct `enqueue_read_model_refresh(...)` 调用点做静态分类，阻止后续旧 producer 绕过 `ReadModelRefreshGateway` / scope policy registry。
- 影响范围：`tests/test_read_model_architecture_guards.py`、read-models 测试矩阵和 planning analysis；不改变 SQL、API、worker、前端、Redis/RabbitMQ 或生产 runtime 行为。
- 关键决策：当前允许的 direct enqueue 只限 legacy app wrapper、cost/tax query repository-miss wrapper 和 cost/tax runtime cache invalidation wrapper；这些 wrapper 最终仍委托 gateway。新增 direct enqueue 必须删除、迁移到 gateway，或登记 compat-only owner/reason/deletion condition。
- 文档影响：同步 read-models 测试矩阵和 planning analysis；长期状态语义不变。
- 测试覆盖：新增 `tests/test_read_model_architecture_guards.py::ReadModelArchitectureGuardTests::test_direct_read_model_refresh_enqueue_calls_are_classified`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v`。
- 未测风险：未连接真实 PostgreSQL/Redis/RabbitMQ，未执行生产 worker drain；本轮是静态守卫，不需要生产写或真实 read model 重建证据。
- 后续事项：推进 `reconciliation-workbench:amount-check-query-contract`。

## 2026-06-23 - Search 与 no-OA bank batch read-side 合同守卫

- 目标：执行 `read-models:search-and-no-oa-bank-batch-contract`，把 `search` 与 `no_oa_bank_batch` 的 self-managed freshness、projection strategy、fan-out `all`、worker、permission 和 repository port 边界固化为 manifest guard。
- 影响范围：`tests/test_read_model_manifest.py`、read-models/no-oa 模块文档和 planning analysis；不改变 SQL、API、worker、前端、Redis/RabbitMQ 或生产 runtime 行为。
- 关键决策：Search 保持 `partitioned_scoped_index` 与 `search` primary worker，`search-pending/search-secondary/search-tertiary` 只能作为 auxiliary；no-OA 保持 `scoped_incremental`、`no-oa-bank-batch` primary worker 和 `NoOaBankBatchApplicationService` query owner。两者 `all` 均是 fan-out command，不是可伪造 fresh 的 parent proof。
- 文档影响：同步 read-models 测试矩阵、no-OA 状态机变更记录和 planning analysis；长期状态语义不变。
- 测试覆盖：新增 `tests/test_read_model_manifest.py::ReadModelManifestTests::test_search_and_no_oa_bank_batch_manifest_preserve_read_side_contracts`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_search_pending_sql_runtime tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_read_model_refresh -v`。
- 未测风险：未连接真实 PostgreSQL/Redis/RabbitMQ，未执行生产 worker drain；本轮不需要生产写或真实 read model 重建证据。
- 后续事项：推进 `read-models:legacy-read-path-removal-guards`。

## 2026-06-23 - Cost/tax/turnover summary read model 合同守卫

- 目标：执行 `read-models:cost-tax-ledger-summary-contract`，把 `cost_statistics`、`tax_offset`、`turnover_ledger` 的 query gateway、parent/fan-out semantics、worker、permission 和 repository port 边界固化为 manifest guard。
- 影响范围：`tests/test_read_model_manifest.py`、read-models/cost-statistics/tax-offset/turnover-ledger 模块文档和 planning analysis；不改变 SQL、API、worker、前端、Redis/RabbitMQ 或生产 runtime 行为。
- 关键决策：`cost_statistics` 保持 `queryable_parent_aggregate` 与 `partitioned_scoped_parent_rollup`；`tax_offset` 和 `turnover_ledger` 保持 fan-out/incremental 语义。旧 `cost-tax` 只能是 cost/tax 的兼容 auxiliary worker，不能替代 primary owner。
- 文档影响：同步 read-models 测试矩阵、cost/tax/turnover 状态机变更记录和 planning analysis；长期状态语义不变。
- 测试覆盖：新增 `tests/test_read_model_manifest.py::ReadModelManifestTests::test_cost_tax_and_turnover_manifest_preserve_summary_contracts`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_cost_statistics_sql_runtime tests.test_tax_offset_sql_runtime tests.test_turnover_ledger_query_service tests.test_turnover_ledger_read_model_refresh -v`。
- 未测风险：未连接真实 PostgreSQL/Redis/RabbitMQ，未执行生产 worker drain；本轮不需要生产写或真实 read model 重建证据。
- 后续事项：推进 `read-models:search-and-no-oa-bank-batch-contract`。

## 2026-06-23 - Invoice lifecycle 与发票使用/收款 read model 合同守卫

- 目标：执行 `read-models:invoice-lifecycle-and-usage-contract`，把 `invoice_lifecycle`、`input_invoice_usage`、`output_invoice_collection` 的 scoped incremental、fan-out `all`、owner、permission 和 repository port 边界固化为 manifest guard。
- 影响范围：`tests/test_read_model_manifest.py`、read-models/input-invoice-usage/output-invoice-collections/domain-events-lifecycle 模块文档和 planning analysis；不改变 SQL、API、worker、前端、Redis/RabbitMQ 或生产 runtime 行为。
- 关键决策：`invoice_lifecycle` 是跨页面生命周期分发边界；input/output 页面 read model 继续拥有筛选、分页、导出和 DTO。input/output 可共享 `invoice-usage-collection` worker，但 repository ports、query owner 和 permission owner 必须独立。
- 文档影响：同步 read-models 测试矩阵、input/output/domain-events-lifecycle 状态机变更记录和 planning analysis；长期状态语义不变。
- 测试覆盖：新增 `tests/test_read_model_manifest.py::ReadModelManifestTests::test_invoice_lifecycle_and_usage_manifest_preserve_scoped_contracts`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_invoice_lifecycle_read_model_refresh tests.test_invoice_lifecycle_read_facade tests.test_invoice_lifecycle_page_integration tests.test_invoice_usage_collection_sql_runtime tests.test_input_invoice_usage_api tests.test_output_invoice_collection_api -v`。
- 未测风险：未连接真实 PostgreSQL/Redis/RabbitMQ，未执行生产 worker drain；本轮不需要生产写或真实 read model 重建证据。
- 后续事项：推进 `read-models:cost-tax-ledger-summary-contract`。

## 2026-06-23 - Pending invoice 与 OA 待付款 read model 合同守卫

- 目标：执行 `read-models:pending-invoice-and-oa-pending-payment-contract`，锁定待找发票和 OA 待付款两个页面 read model 的 scope、force refresh、repository port 和 owner 合同。
- 影响范围：`tests/test_read_model_manifest.py`、read-models/pending-invoices/oa-pending-payments 模块文档和 planning analysis；不改变 SQL、API、worker、前端、Redis/RabbitMQ 或生产 runtime 行为。
- 关键决策：`pending_invoice` 继续拒绝裸 `all`，强制使用 page-first-screen force refresh；`oa_pending_payment:all` 继续只作为 fan-out command，默认查询 freshness proof 来自实际 rows/month scopes 与 dirty/outbox 状态。两者 repository port contract 必须保持不相交。
- 文档影响：同步 read-models 测试矩阵、pending-invoices/OA-pending-payments 状态机变更记录和 planning analysis；长期状态语义不变。
- 测试覆盖：新增 `tests/test_read_model_manifest.py::ReadModelManifestTests::test_pending_invoice_and_oa_payment_manifest_preserve_page_scope_contracts`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest -v`。
- 未测风险：本轮不连接真实 PostgreSQL/OA/RabbitMQ，不执行 OA sync、导入或 worker drain；真实生产 worker/SLO 仍由后续 infra-smoke 或发布窗口验证。
- 后续事项：推进 `read-models:invoice-lifecycle-and-usage-contract`。

## 2026-06-23 - Bank detail 与账户余额 read model 合同守卫

- 目标：执行 `read-models:bank-detail-and-bank-account-balance-contract`，锁定银行明细和账户余额两个高频 read model 的 scope、repository port、test owner 和 all-scope 语义，防止后续模块化时把余额事实源和 bank detail rows 混用。
- 影响范围：`backend/src/fin_ops_platform/services/read_model_manifest.py`、`tests/test_read_model_manifest.py`、read-models/bank-details 模块文档和 planning analysis；不改变 SQL、API、worker、前端、Redis/RabbitMQ 或生产 runtime 行为。
- 关键决策：`bank_detail:all` 继续只作为 fan-out command，页面 freshness proof 以月份 shard 或明确 status 为准。`bank_account_balance` 保持独立 scope/event/table/list-save port，交易数量可按页面筛选参考 bank detail rows，但余额金额、余额 readiness 和 balance status 不能由 bank detail rows 替代。
- 文档影响：同步 read-models 测试矩阵、bank-details 状态机变更记录和 planning analysis；长期状态语义不变。
- 测试覆盖：新增 `tests/test_read_model_manifest.py::ReadModelManifestTests::test_bank_detail_and_balance_manifest_keep_separate_contracts`，并把 `bank_account_balance` manifest test owner 修正为 `tests/test_bank_account_balance_read_model.py`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_bank_account_balance_read_model tests.test_bank_details_sql_runtime -v`。
- 未测风险：本轮不连接真实 PostgreSQL，不执行银行导入或 worker drain；真实生产 worker/SLO 仍由后续 infra-smoke 或发布窗口验证。
- 后续事项：推进 `read-models:pending-invoice-and-oa-pending-payment-contract`。

## 2026-06-23 - Workbench active generation 特例合同守卫

- 目标：执行 `read-models:workbench-active-generation-contract`，锁定 Workbench 作为 active generation read model 的特殊合同，防止后续模块化时误套普通 read model rebuild/gateway 语义。
- 影响范围：`tests/test_read_model_manifest.py`、read-models 模块文档和 planning analysis；不改变 Workbench SQL、worker、matching、route、API 或生产 runtime 行为。
- 关键决策：Workbench 保留 `active_generation_scoped_publish` 与 `equivalent_active_generation`，`all` scope 是 active month shard aggregate。manifest 必须覆盖 Workbench view、summary、groups page、group detail、row detail、refresh status、groups freshness status 和 load/save read model ports。
- 文档影响：同步测试矩阵和 planning analysis；长期 Workbench active generation 边界不变。
- 测试覆盖：新增 `tests/test_read_model_manifest.py::ReadModelManifestTests::test_workbench_manifest_preserves_active_generation_exception`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest -v`。
- 未测风险：本轮不连接真实 PostgreSQL，不运行完整 Workbench SQL runtime；既有 Workbench SQL/query facade tests 是后续改 Workbench SQL 时的必跑集。
- 后续事项：推进 `read-models:bank-detail-and-bank-account-balance-contract`。

## 2026-06-23 - Repository port owner map 合同守卫

- 目标：执行 `read-models:repository-port-and-sql-owner-split-plan`，在拆分 `postgres_repositories/read_models.py` 前，先把每个 read model 当前占用的 public repository port 方法登记成代码级合同。
- 影响范围：`backend/src/fin_ops_platform/services/read_model_manifest.py`、`tests/test_read_model_manifest.py`、read-models 模块文档和 planning analysis；不改变 SQL、API、worker、Redis/RabbitMQ 或生产 runtime 行为。
- 关键决策：不一次性拆 1 万行级 `read_models.py`。先让 manifest 成为 owner map：每个登记方法必须存在于 `PostgresReadModelRepository`，且只能有一个 read model owner。后续拆分按 key/port 小步迁移。
- 文档影响：同步 README、测试矩阵和 planning analysis；长期 read model 事实源不变。
- 测试覆盖：扩展 `tests/test_read_model_manifest.py`，覆盖 repository port contract 非空、方法存在和单 owner。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest -v`。
- 未测风险：本轮不连接真实 PostgreSQL，不执行 repository SQL，不证明页面行为；这是拆分前的静态 contract guard。
- 后续事项：推进 `read-models:workbench-active-generation-contract`，因为 Workbench active generation 是特殊 read model，必须先锁定后再做通用 page slice。

## 2026-06-23 - Force refresh 与 operation barrier manifest 合同守卫

- 目标：执行 `read-models:refresh-gateway-force-refresh-and-operation-barrier`，把受控强制刷新入口和写后 operation barrier 目标纳入 read model manifest，防止后续新增 read model 只改 worker/App Status 而漏掉刷新闭环。
- 影响范围：`backend/src/fin_ops_platform/services/read_model_manifest.py`、`tests/test_read_model_manifest.py`、read-models 模块文档；不改变 API、SQL、worker、Redis/RabbitMQ 或生产 runtime 行为。
- 关键决策：`read_model_slo_smoke` / deploy-control runbook 是受控 force refresh 入口，apply 时仍必须通过 `ReadModelRefreshGateway`；operation barrier 只读 App Status runtime snapshot，不替代页面 fresh gate。manifest 中显式区分标准 gateway force refresh、Workbench active generation scope 和 pending invoice page-first-screen scope。
- 文档影响：同步 README、测试矩阵和 planning analysis；长期 read model 事实源不变。
- 测试覆盖：扩展 `tests/test_read_model_manifest.py`，覆盖 force refresh contract、operation barrier target 推导、page-first-screen scope 和 refresh event 命名合同；现有 refresh gateway、operation barrier 和 SLO smoke 测试保持通过。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier tests.test_read_model_slo_smoke -v`。
- 未测风险：未连接真实 PostgreSQL、Redis、RabbitMQ，未执行生产 `read_model_slo_smoke --apply`，本轮不需要生产写或生产 worker drain 证据。
- 后续事项：推进 `read-models:repository-port-and-sql-owner-split-plan`，先 owner-map `read_models.py` 并定义 repository port/SQL owner，再小步拆分。

## 2026-06-23 - Read model manifest 与边界库存分析

- 目标：执行 `read-models:manifest-and-boundary-inventory`，在实现前先把所有 App Status read model key 的 owner、IO、scope、event、worker、repository、权限和测试合同登记清楚。
- 影响范围：`.planning/refactors/modular-io-boundaries/analysis/read-model-manifest-and-boundary-inventory.md`、自动队列状态；不改变后端、前端、worker 或生产 runtime 行为。
- 关键决策：先建立 manifest/parity guard，再逐 key 做 query gateway parity、force refresh/operation barrier 和 repository port split；不直接全量拆 `postgres_repositories/read_models.py`，不启动 Go/Fiber 或 Go Worker。
- 文档影响：新增 planning analysis，并在本实施记录中登记本轮分析结论；长期 read model 事实源不变。
- 测试覆盖：本轮是文档/规划分析，无业务行为变化；后续实现必须覆盖 read model/cache/background job、API contract、cross-page freshness 和 legacy contamination guard。
- 验证命令：`bash scripts/verify.sh docs`、`git diff --check`。
- 未测风险：未连接真实 PostgreSQL/Redis/RabbitMQ，未执行生产 SSH/DB 操作；本轮不需要生产证据。
- 后续事项：推进 `read-models:query-gateway-contract-and-status-parity`，优先新增 manifest/parity guard，把 direct fresh、自管 freshness 和 legacy compat-only 路径分类。

## 2026-06-22 - Active repair App Health 与 refresh enqueue 语义收敛

- 目标：修复 App Status 同时展示 Workbench read model “刷新中”和 `Workbench read model generation consistency failed.` 阻断的问题，并让 API `refresh_enqueued` 只表示本次调用真实新增 refresh request。
- 影响范围：`/api/app-health` Workbench generation health 聚合、`ReadModelQueryGateway` API miss/stale 入队语义、App Status popover 和依赖 `refresh_enqueued` 的 HTTP SLO/页面判断。
- 关键决策：Workbench active repair/current-effective 状态优先于旧 consistency failure。`read_model_status=refreshing/rebuilding` 时保留 `consistency_status/last_error` 诊断，但不写 unavailable dependency 或全局 blocked。`ReadModelQueryGateway` 使用 refresh gateway 的 actual enqueue events 判断 `refresh_enqueued`，active scope coalescing 返回 false。
- 文档影响：同步 read-models、runtime-workers 和 reconciliation-workbench 状态机/测试矩阵；durable queue、readiness、Redis/RabbitMQ 边界不变。
- 测试覆盖：新增 `tests/test_app_health_api.py::AppHealthApiTests::test_app_health_keeps_workbench_consistency_failure_busy_during_active_repair`、`tests/test_read_model_query_gateway.py::ReadModelQueryGatewayTests::test_missing_sql_view_does_not_report_new_enqueue_when_scope_is_already_active`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_app_health_api tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_app_status_overview_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_operation_freshness_barrier tests.test_runtime_monitoring -v`。
- 未测风险：本地测试不连接真实生产 PostgreSQL/RabbitMQ/Redis，也不证明具体页面首屏 SQL p95；发布后仍需 authenticated HTTP SLO、App Status/dirty scope 只读观察和必要的 SQL profiling。

## 2026-06-22 - Production runtime parity guards

- 目标：修复生产 schema、worker、RabbitMQ、Redis 与本地测试覆盖“各测各的”缺口，避免新增 read model 后只改 App Status 或 worker registry，漏掉 migration storage contract、critical SLO smoke、RabbitMQ dispatch 或 Redis/deploy env 模板。
- 影响范围：`tests/test_runtime_worker_registry.py`、`tests/test_read_model_slo_smoke.py`、`tests/test_postgres_migrations.py`、`tests/test_deploy_runtime_examples.py`、`tests/test_runtime_redis.py`；不改变生产 runtime 行为，不连接生产数据库，不执行 mutating smoke。
- 关键决策：现有架构不需要重写。PostgreSQL durable queue/readiness 仍是事实源；RabbitMQ 是 transport/wakeup；Redis 只缓存 fresh gate 后 payload。本轮只把本地 parity 门禁补硬：每个 App Status read model 必须匹配 required worker、refresh event、RabbitMQ dispatch event、critical SLO smoke scope 和明确的 migration storage contract。`read_model.bank_account_balances`、`read_model.invoice_lifecycle_rows/scopes` 纳入通用 migration 表基线。
- 文档影响：同步 read-models、runtime-workers 测试矩阵和 `docs/operations/runtime-worker-governance.md`。
- 测试覆盖：新增 `RuntimeWorkerRegistryTests.test_app_status_read_model_registry_matches_worker_and_rabbitmq_contracts`、`ReadModelSloSmokeTests.test_critical_only_plans_every_critical_app_status_read_model`、`PostgresMigrationSqlTests.test_app_status_read_model_storage_contracts_are_declared`、`DeployRuntimeExampleTests.test_shared_rabbitmq_worker_env_does_not_switch_all_workers_to_rabbitmq`、`RuntimeRedisTests.test_production_env_examples_match_runtime_redis_settings_contract`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_registry tests.test_read_model_slo_smoke tests.test_postgres_migrations tests.test_deploy_runtime_examples tests.test_runtime_redis -v`。
- 未测风险：本地 guard 不证明真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain；真实环境仍需 `bash scripts/verify.sh infra-smoke`，并在有真实 DB/RabbitMQ/env 时运行 dry-run/apply/preflight。

## 2026-06-22 - Workbench all-scope active generation 读路径补齐

- 目标：修复 Workbench all-scope 已发布 active generation 后，主读路径仍从 month snapshots 临时合成 payload/summary，导致 all scope 没有复用聚合发布时的业务不变量和 source version proof。
- 影响范围：`PostgresReadModelRepository.get_workbench_view(scope_key="all")`、`_load_all_workbench_view(...)`、`_load_all_workbench_rows_page_view(...)`、`/api/workbench?month=all` 主视图与分页/过滤视图。
- 关键决策：Workbench 保留 active generation 原子发布模型；`all` query scope 不是每次页面读取时重新拼 month shards。读路径在 active all generation 存在时必须读取 active all snapshot/summary，并携带 `active_generation_id`、`read_model_version` 和 `source_versions`。month snapshot 合成只保留为无 active all generation 时的 legacy fallback。
- 文档影响：同步 read-models 和 reconciliation-workbench 模块文档；不改变 durable queue、dirty scope 或 Redis/RabbitMQ 边界。
- 测试覆盖：新增 `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_reads_all_scope_view_from_active_generation_snapshot`、`test_repository_reads_all_scope_filtered_page_from_active_all_summary`；完整 Workbench SQL runtime 覆盖 all-scope 聚合、fallback、分页和 source-version 行为。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`。
- 未测风险：本地未连接真实生产数据库和真实 HTTP；发布后需通过 authenticated all-scope HTTP freshness smoke 与 worker drain 观察确认旧 active generation 已替换。

## 2026-06-22 - Workbench group detail freshness gate 补齐

- 目标：修复 `GET /api/workbench/groups/detail` 从 SQL active generation 读取 group 后直接返回 `read_model_status=fresh`，缺少 source version 和 dirty-scope current-effective proof 的问题。
- 影响范围：`WorkbenchQueryFacade.group_detail(...)`、`PostgresReadModelRepository.get_workbench_group_detail(...)`、direct fresh architecture guard、Workbench SQL runtime/API 测试。
- 关键决策：Workbench 继续保留 active generation 原子发布模型，不改成普通 `ReadModelQueryGateway`；但 group detail 作为自管 freshness 入口，必须和 row detail 等价地携带 active generation `source_versions`、`read_model_status` 和 `read_model_version`。当 source versions stale 或同 scope dirty status 为 refreshing/stale 时，API 不返回旧 group，也不标 fresh，而是入队 `workbench` refresh 并返回带 `read_model_status`/`read_model_stale_reasons` 的 not-found 语义，防止前端展开旧详情。
- 文档影响：同步 read-models 和 reconciliation-workbench 模块文档；长期 active generation 边界不变。
- 测试覆盖：新增 `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests::test_group_detail_stale_source_versions_do_not_return_stale_group`、`test_group_detail_refreshing_status_does_not_return_stale_group`；新增 `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_group_detail_includes_active_generation_freshness_contract`；更新 direct fresh allowlist 理由。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_read_model_architecture_guards -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_group_detail_reads_only_active_generation tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_group_detail_includes_active_generation_freshness_contract tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_workbench_group_detail_api_returns_full_group -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness tests.test_read_model_query_gateway tests.test_read_model_architecture_guards tests.test_workbench_query_facade tests.test_workbench_sql_runtime -v`。
- 未测风险：本地测试不连接真实生产 PostgreSQL/Redis/RabbitMQ；发布后仍需通过 authenticated HTTP/worker drain smoke 验证旧 active generation 是否已重建。

## 2026-06-21 - Read model dependency active 判定与 invalid scope 清理入口

- 目标：修复 downstream read model 在依赖 dirty scope 已 orphan 但无 active outbox 时长期 `refreshing` 的问题，并阻止/清理无效 `pending_invoice:all` 运行时事件。
- 影响范围：runtime queue active 判定、dependency-not-fresh 补刷、pending invoice scope policy、read model SLO smoke、scope contract repair CLI 和 PostgreSQL repository。
- 关键决策：`RuntimeQueueRepository.read_model_refresh_is_active(...)` 只代表“是否存在 pending/processing outbox event”，不再用 dirty scope 伪装 active；dirty scope 是否 stale/fresh 继续由 `read_model_refresh_is_fresh(...)` 判断。`pending_invoice` scope contract 不再接受裸 `all`，合法 aggregate scope 必须带方向，例如 `expense:all` 或 `income:cash_income`。`read_model_slo_smoke --scope ...` 有显式 scope 时不再额外加入页面首屏默认 scope。新增 `scripts/check-read-model-scope-contracts.py --repair invalid-read-model-scopes`，只删除 scope policy 明确判定 invalid 的 policy-managed dirty/outbox/readiness runtime 行，并写入 audit/rollback manifest；不猜测 replacement。
- 文档影响：同步更新 read-model/runtime-worker 测试矩阵和 worker 治理文档。
- 测试覆盖：`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_read_model_refresh_is_active_checks_pending_or_processing_outbox_event`、`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_pending_invoice_policy_rejects_global_all_scope`、`tests/test_read_model_slo_smoke.py::ReadModelSloSmokeTests::test_explicit_pending_invoice_scope_does_not_add_page_first_screen_scope`、`tests/test_read_model_scope_contract.py` invalid scope repair/audit/idempotency tests。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_read_model_scope_contract.py tests/test_read_model_refresh_gateway.py tests/test_runtime_queue.py tests/test_read_model_slo_smoke.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_worker.py tests/test_runtime_monitoring.py tests/test_import_job_queue.py tests/test_import_processing_service.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_bank_detail_for_transaction_month_scopes -q`。
- 未测风险：生产 apply 需要在发布后执行 dry-run/apply/post-check，并观察 backlog 是否被补投的依赖 refresh drain 完成；真实 HTTP 写入 smoke 仍需要有效登录态或 bearer/cookie。

## 2026-06-20 - Orphaned import fact dirty scope repair

- 目标：为真实导入后 App Status 长时间同步中的历史状态补受控清理入口。只读审计发现 `import.fact.changed` outbox 已 `done`，但 `reason=import_facts_changed` 的 dirty scope 仍 pending，且没有 active outbox 可 claim。
- 影响范围：`ReadModelScopeContractService`、`PostgresReadModelScopeContractRepository`、`scripts/check-read-model-scope-contracts.py`；不改变 read model refresh 事实源，不写 fresh readiness。
- 关键决策：新增 `--repair orphaned-import-facts` 模式，默认 dry-run；`--apply` 只删除没有 active `import.fact.changed` outbox 对应的 orphaned legacy dirty scope，并写入审计和 rollback manifest。当前和未来导入链路仍由真实 `*.read_model.refresh` event 和 dirty scope 证明 freshness。
- 测试覆盖：`tests/test_read_model_scope_contract.py::ReadModelScopeContractServiceTests::test_postgres_repository_lists_only_orphaned_import_fact_dirty_scopes`、`test_check_reports_orphaned_import_fact_dirty_scopes_without_writes`、`test_apply_deletes_orphaned_import_fact_dirty_scopes_and_records_audit`、`test_orphaned_import_fact_repair_is_idempotent`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_read_model_scope_contract.py -q`；真实 runtime dry-run：`scripts/check-read-model-scope-contracts.py --repair orphaned-import-facts --json` 返回 42 条 orphaned dirty scope、`cleanup.applied=false`。
- 未测风险：未执行生产 `--apply`；清理后仍需重新跑 App Status/dirty scope 只读检查和 write-operation SLO audit。

## 2026-06-20 - Import fan-out source ordering and pending invoice month shards

- 目标：收敛发票导入后的 read model refresh 长尾，避免旧 outbox event 覆盖新 dirty scope，并把待找发票导入后刷新从全量 aggregate 收窄到影响月份。
- 影响范围：runtime queue superseded cover、import snapshot 保存边界、pending invoice read model refresh scope、银行明细导入 refresh；不改变业务 API payload shape。
- 关键决策：superseded cover 必须是创建顺序晚于当前 event 的同 dedupe event；仅靠 source_version 高低不能跨历史事件域覆盖当前 dirty scope。`save_imports` 保存完整 snapshot 时不再发 read model refresh，当前写操作 fan-out 由 import processing 根据本次 preview/session rows 投递。导入影响月份已知时，pending invoice 使用 month shard scope，缺月份时才回退到历史全量 aggregate；银行明细必须验收真实 `bank_detail.read_model.refresh`，不能只看兼容 `import.fact.changed` ack。
- 后续优化：发票导入方向页 fan-out 改为按本次文件方向命中刷新。`input_invoice` 只投递 `input_invoice_usage` scope，`output_invoice` 只投递 `output_invoice_collection` scope；未命中方向不入队，避免同月无关页面被刷新。后台税金抵扣 scope helper 同步过滤 batch type，银行流水导入不再误投 `tax_offset`。银行流水导入现在以本次导入的 `bank_detail_scope_keys` 为信号同步投递 `bank_account_balance:all`，让账户余额 read model 和银行明细一起进入 durable queue。
- 文档影响：同步 runtime-workers 与 imports-invoices 模块记录；read model durable truth 边界不变。
- 测试覆盖：`tests/test_runtime_queue.py`、`tests/test_postgres_repositories_core.py::test_save_imports_does_not_emit_import_fact_refresh_from_full_snapshot`、`tests/test_import_processing_service.py`、`tests/test_import_job_queue.py`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_skips_unaffected_invoice_relation_read_models`、`tests/test_write_operation_slo_audit.py::WriteOperationSloAuditTests::test_invoice_import_confirmed_profile_allows_direction_specific_relation_refresh`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_queue.py tests/test_runtime_worker.py tests/test_runtime_monitoring.py tests/test_import_job_queue.py tests/test_runtime_worker_registry.py tests/test_read_model_refresh_gateway.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests/test_write_operation_slo_audit.py -q`。
- 未测风险：真实生产数据量下的 enqueue-to-fresh 收益需发布后通过 write-operation SLO audit 和 App Status/dirty scope 只读观察确认。

## 2026-06-19 - Authenticated HTTP probe 发现成本统计 schema 查询漂移

- 目标：推进生产 authenticated runtime gate，并修复 probe 暴露的成本统计 SQL read model 查询与真实表结构不一致问题。
- 影响范围：`read_model.cost_statistics_read_models` 查询合同、`PostgresReadModelRepository.get_cost_statistics_view(...)`、成本统计 authenticated HTTP endpoints、生产 release `main-bf02acc5-coststats-schema-20260619172500`。
- 生产证据：目标 OA 凭据可产生真实 `full_access` 登录态，`/api/session/me` 通过，SSE `/api/app-health/stream` 和 `/api/workbench/events?month=all` first-event 通过；full authenticated HTTP probe 暴露成本统计两个 GET endpoint 返回 `500`，日志为 `column "schema_version" does not exist`。
- 根因：repository 查询选择了 `schema_version` 表列，但 `0006_read_models.sql` 的 `read_model.cost_statistics_read_models` 没有该列；schema version 应从 `payload` / `raw_payload` 读取。已有本地测试没模拟真实表结构缺列。
- 修复与发布：新增成本统计 SQL runtime 回归测试，移除父表 select 中的不存在列，提交 `bf02acc5 Fix cost statistics read model schema query` 并发布 release `main-bf02acc5-coststats-schema-20260619172500`。
- 验证：hotfix worktree `tests/test_cost_statistics_sql_runtime.py tests/test_postgres_repositories_boundaries.py` 通过 `38 passed`；发布后 `/health/ready` ready，`runtime_blocker_count=0`；targeted read model apply 中 `cost_statistics` 和 `output_invoice_collection` 2/2 通过；成本统计 authenticated endpoints 返回 `200`。
- 未闭合项：authenticated HTTP full gate 仍需要 admin 登录态和 `output_invoice_collection:all` freshness 问题后续处理；真实 write-operation apply 仍需要业务审批 ticket。

## 2026-06-19 - Cost statistics direct refresh SLO 失败与批量保存发布复验

- 目标：把生产 critical read model apply gate 从 dry-run 推进到真实 enqueue-to-fresh 复验，并处理发现的 `cost_statistics` direct refresh 5 秒 SLO 失败。
- 影响范围：生产 release `main-33a150e7-write-e2e-approval-gate-20260619151922` 到 `main-3d88ce99-coststats-batch-20260619170500` 的 critical read model apply gate、`PostgresReadModelRepository._replace_cost_statistics_rows(...)`、repository boundary tests；不改成本归因业务规则、scope contract、payload shape、API response 或前端。
- 生产证据：`read_model_slo_smoke --critical-only --apply --target-ms 5000 --timeout-seconds 120` 中 15 个 critical scope 均达到 dirty/outbox `done` 且 readiness `fresh` 或 `dirty_done`，证明 worker drain 和 read model 最新状态可以收敛；但 `invoice_lifecycle:2026-04` enqueue-to-fresh 约 5286.961ms、`cost_statistics:active:2026-04` 约 6459.019ms，整体 `status=fail`。随后只重跑两个失败 scope，`invoice_lifecycle` 约 2336.86ms 通过，`cost_statistics:active:2026-04` 仍约 7003.227ms 失败；公网 `health_ready_payload_probe` 仍通过，`runtime_blocker_count=0`。
- 根因调查：`cost_statistics` 失败不是数据不 fresh，而是 handler duration/row 写入尾延迟超过目标。代码路径为 `CostStatisticsSqlProjectionBuilder._publish_cost_statistics_scope(...)` -> `PostgresReadModelRepository.save_cost_statistics_read_models(...)` -> `_replace_cost_statistics_rows(...)`；该方法在删除 scope rows 后对每条 `time_rows` 调用一次 `connection.execute(...)`，仍是逐行 insert/upsert，和此前 invoice lifecycle 慢点同类。
- 修复与发布：新增 RED 测试 `tests/test_postgres_repositories_boundaries.py::test_cost_statistics_rows_are_saved_in_batch`，先证明当前 `executed_many` 为 0；随后把 `_replace_cost_statistics_rows(...)` 改为构造 params 列表并调用 `_execute_many(...)`，保持同一事务、delete、字段、`on conflict (scope_key, row_key)` 更新语义不变。为避免混入主工作区大量未提交变更，基于生产 commit `33a150e7` 创建隔离 clean worktree，提交 `3d88ce99 Optimize cost statistics read model row saves`，通过 release `main-3d88ce99-coststats-batch-20260619170500` 发布激活。
- 发布后复验：新 release 上公网 `health_ready_payload_probe` 通过，`elapsed_ms=104.986`、`runtime_release.consistent=true`、`runtime_blocker_count=0`；`read_model_slo_smoke --critical-only --apply --target-ms 5000 --timeout-seconds 120` 15/15 pass，summary p50 约 490.393ms、p95/max 约 3176.5ms，`cost_statistics:active:2026-04` 降至约 3176.5ms，`invoice_lifecycle:2026-04` 约 1400.792ms。
- 文档影响：更新本实施记录、`docs/modules/cost-statistics/implementation-notes.md` 和 `docs/dev/testing-closure-state.md`；长期架构边界不变。
- 测试覆盖：新增 repository boundary test 覆盖成本统计 rows 批量保存；既有 `tests/test_cost_statistics_sql_runtime.py` 继续保护 payload/readiness/cache 行为。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py::test_cost_statistics_rows_are_saved_in_batch -q` 先 RED 后 PASS；`PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_cost_statistics_sql_runtime.py -q` 通过 37 tests；`PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` 通过。
- 未测风险：direct critical read model refresh SLO 已在生产复验通过；真实业务写操作 SLO、认证态 HTTP SLO 和受控 mutating write scenario 仍未闭环。

## 2026-06-19 - 生产运行时只读巡检补充

- 目标：在不重启、不部署、不执行 mutating smoke 的前提下，补强 Spec-first E2E 总目标里 read model/worker 最新状态的外部证据，并明确仍不能宣称闭环的部分。
- 影响范围：生产 release `main-8b5942e4-http-slo-admin-scope-202606191805` 的 API、RabbitMQ dispatcher、20 个 runtime worker、`health_ready_payload_probe`、`runtime_sync_closure_gate` 和 `read_model_slo_smoke` dry-run；不写业务数据，不 enqueue refresh，不运行 `--apply`。
- 关键决策：只读巡检证明当前 runtime blocker 为 0、API ready、release consistent、API/dispatcher/20 个 worker active，且 runtime gate 的 `runtime_health` pass；但本轮没有提供认证 token，也没有 approval ticket，因此不能把 authenticated HTTP SLO、direct read model enqueue-to-fresh smoke 或真实业务写操作 SLO 标记为完成。
- 生产只读证据：SSH 只读检查显示 API、RabbitMQ dispatcher 和 20 个 `fin-ops-worker@*.service` active；systemd `WorkingDirectory` 均指向 release `main-8b5942e4-http-slo-admin-scope-202606191805/src`。公网 `health_ready_payload_probe` 返回 `status=pass`、`health_status=ready`、`elapsed_ms=144.671`、`runtime_blocker_count=0`、`runtime_release.consistent=true`。加载 systemd env 后 `read_model_slo_smoke --critical-only --target-ms 5000` 返回 `status=dry_run`、`planned_scope_count=15`；PostgreSQL 权威表只读汇总为 `job.outbox_events=[["done", 157060]]`、`job.read_model_dirty_scopes=[["done", 143020]]`、`read_model.app_status_readiness=[["fresh", 169]]`。
- 未闭环证据：`read_model_slo_smoke --critical-only` 本轮未带 `--apply`，只规划 15 个 critical scope，不能替代 enqueue-to-fresh 证明；公网 `runtime_sync_closure_gate` 只读模式中 `runtime_health` 和 `health_ready_payload` 通过，但 `read_model_direct_smoke` 因未 apply 失败，authenticated HTTP/SSE 因缺 bearer/admin token 未闭合，`write_operation_audit` 有 447 个事件样本但 56/56 expectations 未达标或缺样本，`write_operation_e2e` 缺写场景、apply 标志和 approval ticket。
- 文档影响：更新本实施记录和 `docs/dev/testing-closure-state.md`；长期 gate 边界仍以 `docs/operations/monitoring.md` 为准。
- 测试覆盖：本轮只运行生产只读工具，没有新增测试；现有 `tests/test_runtime_sync_closure_gate.py`、`tests/test_write_operation_slo_audit.py`、`tests/test_write_operation_scenario_discovery.py` 和 `tests/test_write_operation_e2e_smoke.py` 继续保护工具合同。
- 验证命令：生产只读命令包括 SSH 只读 systemd 状态检查、`health_ready_payload_probe --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --json`、生产本机加载 systemd env 后 `/opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.read_model_slo_smoke --json --critical-only` dry-run、PostgreSQL 只读状态聚合，以及 `runtime_sync_closure_gate --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --allow-unauthenticated-http --json`。
- 未测风险：还没有认证态 HTTP/API freshness SLO、没有本轮 direct `--apply` enqueue-to-fresh smoke、没有受控 mutating write scenario；最终闭环仍需要真实认证、审批引用和可接受的生产或 staging 写操作样本。

## 2026-06-19 - 当前 release critical direct apply 复验

- 目标：把当前生产 release 的 read model gate 从 dry-run 推进到 direct enqueue-to-fresh 证据，并确认前一轮只读复查后的 worker drain 仍能在 5 秒目标内收敛。
- 影响范围：生产 release `main-8b5942e4-http-slo-admin-scope-202606191805` 的 critical read model refresh queue 和 app status readiness；不执行业务写接口，不改变业务关系。
- 关键决策：`runtime_sync_closure_gate --apply-read-model-smoke` 可以补 read model direct apply 证据，但未传 `--apply-write-scenarios` / `--write-scenario` / approval ticket 时不会触发业务写操作。首轮 full gate 的 `read_model_direct_smoke` 最终 done/fresh 但 2 个 scope 超过 5 秒目标：`invoice_lifecycle:2026-04` 约 7116.852ms、`cost_statistics:active:2026-04` 约 7273.758ms；随后只重跑这两个 scope 2/2 pass；最终完整 `read_model_slo_smoke --apply --critical-only` 15/15 pass。
- 生产证据：聚焦复验中 `invoice_lifecycle:2026-04` 约 1221.935ms、`cost_statistics:active:2026-04` 约 3056.738ms；完整复跑 summary p50 约 580.34ms，p95/max 约 3863.253ms，handler p95/max 约 3535.364ms。复跑后 PostgreSQL 权威表汇总为 `job.outbox_events=[["done", 157126]]`、`job.read_model_dirty_scopes=[["done", 143083]]`、`read_model.app_status_readiness=[["fresh", 169]]`。
- 文档影响：更新本实施记录、`e2e-coverage.md` 和 `docs/dev/testing-closure-state.md`；长期测试入口不变。
- 测试覆盖：本轮执行生产 direct apply gate，没有新增代码测试；既有 `tests/test_read_model_slo_smoke.py`、`tests/test_runtime_sync_closure_gate.py` 和 read model repository tests 继续保护工具合同。
- 验证命令：生产 `runtime_sync_closure_gate --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --allow-unauthenticated-http --apply-read-model-smoke --read-model-target-ms 5000 --health-ready-target-ms 1000 --timeout-seconds 120 --json`；生产 `read_model_slo_smoke --apply --read-model-key invoice_lifecycle --read-model-key cost_statistics --scope invoice_lifecycle=2026-04 --scope cost_statistics=active:2026-04 --target-ms 5000 --timeout-seconds 120 --json`；生产 `read_model_slo_smoke --apply --critical-only --target-ms 5000 --timeout-seconds 120 --json`。
- 未测风险：direct critical read model apply 已闭合；authenticated HTTP/SSE、admin dashboard 和真实业务 write-operation apply 仍未闭合，继续由 `READMODEL-E2E-006` 和 app-health/runtime gate 管理。

## 2026-06-19 - Write-operation audit 只读证据与 scenario discovery

- 目标：在 direct read model refresh SLO 闭环后，继续验证真实业务写操作是否能证明 writer -> durable outbox/dirty scope -> worker -> readiness 的端到端刷新链路。
- 影响范围：生产 `write_operation_slo_audit` 只读审计、`write_operation_scenario_discovery` 只读候选生成、read-models 未测风险；不执行 mutating HTTP，不写业务数据。
- 关键决策：168 小时窗口的 `write_operation_slo_audit --target-ms 1000 --p99-target-ms 3000` 返回 `status=fail`，`event_sample_count=5000`，`expectation_count=56`，`failed=56`，其中 `missing=12`、非 missing 的历史样本大多为 1 秒/3 秒 SLO 超时；这说明历史真实写入样本不能证明当前目标闭环。以 hotfix 激活时间 `2026-06-19T14:58:07+08:00` 作为 `--since` 后，审计返回 `event_sample_count=21`，但 56/56 expectation 都是 `missing`，说明新 release 后还没有高影响真实业务写操作 profile 样本，不能把 direct refresh 证据当作真实业务写链路证据。
- 只读 discovery 结果：生产 `write_operation_scenario_discovery --limit 10` 返回 `status=ready`，候选计数为 turnover 10、Workbench withdraw context 10、no-OA withdraw context 10，并写出 30 个 scenario 到 `/tmp/finops-write-e2e-scenarios-20260619.json`。所有 scenario 都要求真实认证和人工/业务审批后才能 apply。随后 `write_operation_e2e_smoke --scenario /tmp/finops-write-e2e-scenarios-20260619.json` dry-run 通过，`scenario_count=30`，其中 `turnover_manual_closure_or_withdraw` 10 个、`workbench_relation_withdraw` 10 个、`no_oa_bank_batch_withdraw` 10 个；dry-run 未配置 auth 且未带 `--apply`，因此没有执行任何写操作。
- 最小 apply 候选分级：只读解析 discovery/scenario 文件后，turnover 候选 10 个，其中 7 个 `suggested`、2 个 `deterministic`、1 个 `confirmed`，风险均为 `existing_relation_withdraw_requires_manual_business_approval`；Workbench withdraw 候选 10 个均为 `active` 且风险为 `existing_workbench_relation_withdraw_requires_manual_business_approval`；no-OA withdraw 候选 10 个均为 `submitted`，月份集中在 2026-02/2026-03，风险为 `existing_no_oa_batch_withdraw_requires_manual_business_approval`。因此第一条受控 apply smoke 应优先选择 turnover `suggested` relation，而不是先撤 Workbench active 关系或 no-OA submitted 批次。已在生产 `/tmp/finops-write-e2e-scenarios-20260619-minimal-turnover-dryrun.json` 生成只含 1 条 `turnover_manual_closure_or_withdraw` 的 minimal scenario，并通过 `write_operation_e2e_smoke` dry-run：`status=dry_run`、`scenario_count=1`、`auth_configured=false`；计划写入口为 `POST /api/turnover-ledger/relations/turnover_rel_05cac958eb8c7c74/withdraw`，后置探针为 turnover grouped 与 App Health dashboard。该证据仍不是 mutating closure；工具已加审批闸门，正式执行必须同时提供真实认证和 `--approval-ticket` / `FIN_OPS_WRITE_E2E_APPROVAL_TICKET`，否则返回 `approval_missing` 且不会连接 Postgres 或执行 mutating HTTP。
- 文档影响：更新本实施记录和全局 testing closure 状态；长期运维口径仍以 `docs/operations/monitoring.md` 的 write-operation gate 边界为准。
- 测试覆盖：本轮只读运行生产工具，并补强 apply 审批闸门。`tests/test_write_operation_slo_audit.py`、`tests/test_write_operation_scenario_discovery.py`、`tests/test_write_operation_e2e_smoke.py` 继续保护工具合同；`tests/test_runtime_sync_closure_gate.py` 保护最终 closure gate 必须带 `--write-approval-ticket`。
- 生产闸门验证：已发布并激活 release `main-33a150e7-write-e2e-approval-gate-20260619151922`，生产本机对 minimal turnover scenario 执行 `write_operation_e2e_smoke --apply` 但不带 approval，返回 exit code 2、`status=approval_missing`、`error=write_operation_e2e_requires_approval_ticket`、`scenario_count=1`、`approval_configured=false`。该验证没有执行任何业务写操作。
- 发布后 read model/worker 验证：同一 release 上执行 critical `read_model_slo_smoke --critical-only --apply --target-ms 5000 --timeout-seconds 120`，15 个 critical scope 全部通过，summary p50 约 926.619ms、p95/max 约 4960.071ms，handler p95/max 约 4783.4ms。随后只读 DB 汇总显示 `job.outbox_events` 156974 行全为 `done`、`job.read_model_dirty_scopes` 142936 行全为 `done`、`read_model.app_status_readiness` 169 行全为 `fresh`。
- 未测风险：还没有执行受控 mutating scenario；因此真实业务写操作 profile 仍未闭环。下一步必须从 discovery 候选中选择可撤回/可接受审计的测试对象，提供真实 OA/Admin auth 和审批引用，再运行 `write_operation_e2e_smoke --apply --approval-ticket <approval>` 或 `runtime_sync_closure_gate --apply-write-scenarios --write-approval-ticket <approval>`。

## 2026-06-19 - Invoice lifecycle read model 批量保存与生产 SLO 跟进

- 目标：把 Spec-first E2E 真实运行闭环推进到 read model/worker 最新状态验证，并收敛生产 `invoice_lifecycle` critical refresh 超过 5 秒的尾延迟。
- 影响范围：`PostgresReadModelRepository.save_invoice_lifecycle_rows(...)`、生产 critical `read_model_slo_smoke --apply` 证据、read-models 测试矩阵；不改变 invoice lifecycle payload、scope、freshness 或 worker 入队合同。
- 关键决策：真实生产 critical apply 证明 15/15 个关键 scope 都达到 outbox/dirty `done` 且 readiness `fresh`，数据一致性和 worker drain 成功；失败点是 SLO，初次 apply 中 `invoice_lifecycle`、`oa_pending_payment`、`cost_statistics` 超过 5 秒，聚焦重试后只剩 `invoice_lifecycle` 约 5.76 秒。服务器只读分段显示 `invoice_lifecycle` 2026-04 的 projection 读取低于 1 秒，瓶颈在逐行保存 `read_model.invoice_lifecycle_rows`。修复把逐行 insert/upsert 改为 `_execute_many(...)` 批量保存，仍在同一事务内先删除 scope rows、再写 rows、最后 upsert scope。已通过 release `main-99ea9b35-invoice-lifecycle-batch-20260619145710` 激活到生产，发布后 critical apply gate 15/15 pass，summary p95/max 约 3.52 秒，`invoice_lifecycle` 约 1.29 秒。
- 文档影响：更新本实施记录、`tests.md` 和 `docs/dev/testing-closure-state.md`；长期架构边界不变。
- 测试覆盖：新增 `tests/test_postgres_repositories_boundaries.py::test_invoice_lifecycle_rows_are_saved_in_batch_and_scope_is_updated`，证明 invoice lifecycle rows 使用 batch insert/upsert 且 scope 仍在同一事务更新；相关 invoice lifecycle read model/API/page integration 回归继续覆盖 payload/read facade 行为。
- 验证命令：见本轮最终交付说明。
- 未测风险：critical direct refresh SLO 已闭环；真实业务写操作 SLO audit 仍需要有对应业务写入样本或受控 staging 场景，不能用 direct refresh 完全替代真实业务写链路。
- 后续事项：若未来 `invoice_lifecycle` critical scope 再次超过 5 秒，进入 SQL write profiling、索引/constraint/transaction size 分析；同时继续推进真实业务写入 profile 的 SLO audit。

## 2026-06-19 - Pending invoice scope contract 防复发与运行状态闭环

- 目标：关闭发票导入修复后的 Runtime Read Model 残留，防止非法 `pending_invoice` 裸月份 scope 再次进入 durable queue/readiness。
- 影响范围：`ReadModelRefreshGateway` scope policy registry、`pending_invoice.read_model.refresh` 入队边界、生产 `job.outbox_events` / `job.read_model_dirty_scopes` / `read_model.app_status_readiness` 运行状态；不改变 pending invoice projection 业务字段。
- 关键决策：`pending_invoice` 不再使用 generic non-empty scope policy。合法 scope 只能是 `all` 聚合命令，或 `expense|income:<filter>`，或 `expense|income:<filter>:YYYY-MM`；裸月份如 `2026-02`、错误 direction 和非规范月份必须 fail-fast。生产历史残留通过真实 refresh 重新收敛后再用 `runtime_queue_ops resolve-covered-dead-letters` 归档，禁止直接把 dead-letter 改为 done。
- 文档影响：同步 runtime-workers、app-health-operations 和本实施记录；长期事实源仍是 runtime worker governance。
- 测试覆盖：`tests/test_read_model_refresh_gateway.py` 覆盖 pending invoice 合法聚合/base/month scope，以及裸月份、错误 direction、缺 filter、非规范月份的拒绝。
- 验证命令：见本轮最终交付说明。
- 未测风险：本地测试证明未来入队边界；真实重新导入发票还需要用户在清理后的生产环境重新上传文件验证完整业务链路。
- 后续事项：新增 read model scope type 时必须在 scope policy registry 中明确选择 generic 或专用 policy；不能让业务含义明确的 scope 默默落到 generic 非空校验。

## 2026-06-18 - Read model payload contract validator

- 目标：修复 App Health 显示 read model fresh/已同步，但业务页面因旧 Redis 或 SQL payload 缺少当前 API 必需字段而加载失败的问题。
- 影响范围：`ReadModelQueryGateway`、成本统计 explorer 查询服务、read-models 状态机与测试矩阵。
- 关键决策：
  - freshness gate 仍负责 schema/source/readiness；业务 API shape 由 query service 显式传入 `payload_validator`，避免共享网关猜测各业务字段。
  - Redis 命中也必须经过 payload validator；invalid cache 不能直接返回 fresh，应继续读取 SQL view，若 SQL view 合法则回填新缓存。
  - SQL view payload invalid 时返回 canonical empty refreshing payload，带 `read_model_stale_reasons=["api_payload_shape_invalid"]` 和 `refresh_reason`，并通过统一 refresh gateway 入队；不写 fresh Redis cache。
- 文档影响：更新 read-models 状态机、测试矩阵和本实施记录；成本统计模块同步记录 explorer payload contract。
- 测试覆盖：新增 `tests/test_read_model_query_gateway.py::ReadModelQueryGatewayTests::test_invalid_fresh_cache_payload_contract_misses_and_uses_sql_view`、`test_invalid_sql_payload_contract_enqueues_refresh_without_populating_cache`；成本统计 SQL runtime 覆盖 malformed explorer payload。
- 验证命令：见本轮交付说明。
- 未测风险：本地不连接真实 Redis/RabbitMQ/PostgreSQL worker drain；生产已有旧缓存可能需要发布后等待 TTL 或运维清理，但新代码不会继续把 invalid cache 当 fresh 返回。
- 后续事项：新增或改变业务 read model API shape 时，优先在 query service 声明 payload validator，并同步 schema/source version 或重建策略。

## 2026-06-17 - Direct fresh / direct mismatch architecture guard

- 目标：把仍保留在 legacy route、service、repository 中的 direct `read_model_status=fresh` 和 direct `source_version_mismatch_reasons(...)` 路径纳入架构层静态保护，避免未来新增页面绕过 `ReadModelQueryGateway` 或等价 freshness boundary。
- 影响范围：`tests/test_read_model_architecture_guards.py`、`server.py` legacy read model helpers、`NoOaBankBatchApplicationService`、`TaxOffsetPlanService`、read-models 状态机和测试矩阵。
- 关键决策：允许的 direct fresh 位置必须在静态白名单中写明数量和理由；新增或移动 direct fresh 会导致测试失败。所有 direct source version mismatch 比较必须先通过 `require_expected_source_versions(...)` 或等价 fail-fast expected contract；共享 freshness comparator 本身是唯一例外。
- 文档影响：更新 read-models 状态机、测试矩阵和本实施记录。
- 测试覆盖：`tests/test_read_model_architecture_guards.py` 新增 direct fresh inventory guard 和 direct mismatch expected-contract guard；相关业务回归覆盖 pending invoice、OA pending payment、cost/tax offset、workbench、no-OA batch 和 turnover ledger。
- 验证命令：见本轮交付说明。
- 未测风险：静态 guard 保证代码层面不能新增未分类绕行；生产旧 projection 仍必须在发布后通过 worker drain/requeue 真实重建。
- 后续事项：新增 read model 页面优先接入 `ReadModelQueryGateway`；确需自管 freshness 的模块必须同步扩展 guard 和模块测试。

## 2026-06-17 - Read model freshness contract fail-closed

- 目标：从架构层面防止页面或 query service 把缺少 expected/actual freshness 证明的 read model projection 当作 fresh，避免单页补丁后同类 stale bug 反复出现。
- 影响范围：`ReadModelQueryGateway`、`read_model_freshness` resolver、Pending Invoice/OA Pending Payment/Input Invoice Usage 等自管 freshness 服务、Cost Statistics SQL repository schema metadata、read-models 测试矩阵和运维合同。
- 关键决策：查询方必须声明 `expected_source_versions` 或 `expected_schema_version`；缺少 expected contract 直接 fail-fast。已声明 expected schema/source 时，SQL view 或 Redis fresh gate 缺少 actual metadata proof 必须返回 refreshing/stale reason 并入队 refresh，不允许写 fresh cache。自管 read model service 禁止默认空 `source_versions_provider`。
- 文档影响：更新 read-models README、状态机、测试矩阵，以及 app/runtime 运维合同。
- 测试覆盖：新增 `tests/test_read_model_architecture_guards.py` 静态保护 gateway call sites 和空 provider 反模式；扩展 `tests/test_read_model_freshness.py`、`tests/test_read_model_query_gateway.py` 覆盖缺 schema proof、空 expected contract 和 cache miss；扩展 `tests/test_cost_statistics_sql_runtime.py` 覆盖真实 repository 返回 schema metadata。
- 验证命令：见本轮交付说明。
- 未测风险：本地测试不能证明生产旧 projection 已全部重建；发布后仍需 worker drain 或受控 requeue，让旧缺 schema/source metadata 的 projection 重新生成。
- 后续事项：后续新增 read model 页面必须使用 `ReadModelQueryGateway` 或等价 fail-closed resolver；若暂时保留自管 freshness，必须有静态 guard 或模块测试证明 expected contract 非空。

## 2026-06-17 - 业务 projection 版本语义变化必须 bump schema version

- 目标：修复外部往来 grouped read model 旧 projection 继续被当 fresh，导致页面提交旧 `expected_versions=0` 的问题，并把 read model schema/source version 失效要求固化为回归。
- 影响范围：`turnover_ledger` read model source versions、`TurnoverLedgerService` grouped payload、read-models 测试矩阵。
- 关键决策：当业务 payload 字段语义改变到会影响写操作 precondition 时，必须 bump 对应业务 read model schema/source version；不能只修改 live conversion 或前端 mapper。旧 projection 必须通过 source version mismatch 进入 stale/refreshing，并由 worker 重建。
- 文档影响：同步更新 turnover-ledger 模块实施记录、状态机和测试矩阵；本模块记录通用边界。
- 测试覆盖：`tests/test_turnover_ledger_source_versions.py::TurnoverLedgerSourceVersionsTests::test_source_versions_include_all_turnover_and_cross_module_inputs` 锁定 `turnover_ledger_schema_version` bump；`tests/test_turnover_ledger_service.py` 覆盖 grouped flow row 版本 fallback。
- 验证命令：见本轮交付说明。
- 未测风险：本地未执行生产 worker drain；发布后仍需观察 `turnover_ledger:all` old projection stale/rebuild 到 fresh。

## 2026-06-16 - 事务型 producer 补齐成本统计 scope policy

- 目标：修复外部往来 Postgres 事务写路径绕过 read model scope policy，导致 `turnover_relation_changed` 继续生成 legacy `cost_statistics` scope 的风险。
- 影响范围：`TurnoverLedgerDirtyOutboxWriter` 事务入队、`TurnoverLedgerWriteUnitOfWork` source version 映射、成本统计 scope contract repair dry-run。
- 关键决策：非事务 producer 继续走 `ReadModelRefreshGateway`；事务内 producer 在同一事务中复用 `DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY.normalize_and_validate(...)` 后再调用 `enqueue_read_model_refresh_in_transaction`。不把 stale 伪装 fresh，不手工改 readiness。
- 文档影响：更新 read-models、turnover-ledger、cost-statistics 和 P2/P3 closure ledger。
- 测试覆盖：`tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction` 保护事务 producer；`tests/test_read_model_scope_contract.py` 继续覆盖生产 legacy row dry-run/apply。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v`。
- 未测风险：生产 cleanup apply、worker drain 到 fresh、authenticated HTTP SLO 仍需发布后受控验证。
- 后续事项：新增事务型 read model producer 时必须显式复用 scope policy registry 或提供等价 contract 测试。

## 2026-06-16 - Bank detail fan-out scope 与 downstream dependency 边界

- 目标：修复外部往来款管理和免 OA 批次依赖 `bank_detail` 时的 all-scope fan-out 循环，避免页面无数据但 App Status 长时间显示同步中。
- 影响范围：read model dependency defer 语义、`bank_detail` all-scope fan-out、active coalescing reason、bank tag read facade 的 missing transaction 与 blocking scope 语义；不改变 `bank_detail` 月份 shard rebuild 和 readiness 发布规则。
- 关键决策：`bank_detail:all` 只作为显式 fan-out command，不能由 downstream all-scope `bank_detail_read_model_not_fresh` 自动补投；`bank_detail_all_shard` 是 ensure/wakeup 类 reason，目标月份已 active 时不重复 bump dirty source_version。真实写入 reason 仍保持 bump active scope，避免新事实被旧 worker 覆盖。fresh `bank_detail` read model 中没有某些 transaction id 时，不再降级为 non-fresh；缺失 id 作为诊断返回，downstream projection 按无标签处理。非 fresh 依赖读取必须只补投 `dirty_scopes` / signature `dirty_status` 标记的 blocking scope，不能因为一个月份 pending 而重刷所有相关月份。
- 文档影响：同步更新 runtime-workers、bank-details、turnover-ledger 模块。
- 测试覆盖：`tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_bank_detail_all_shard_reason_does_not_bump_active_scope`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes`。
- 验证命令：见本轮最终交付说明。
- 未测风险：真实生产历史 dirty/outbox 需要发布后 drain 观测；如果存在旧版本遗留 dead-letter/processing，必须通过 runtime ops 工具恢复。

## 2026-06-13 - Dependency-not-fresh runtime defer

- 目标：避免 downstream read model 在 source read model 尚未 fresh 时走普通 60s retry/dead-letter，缩短页面从失败恢复到同步的尾延迟。
- 影响范围：`RuntimeWorker`、`RuntimeQueueRepository.defer_event(...)`、worker CLI `--dependency-not-fresh-delay-seconds`；所有抛出 `*_read_model_not_fresh` 的 read model refresh handler 共享受益。
- 关键决策：defer 只延后 outbox event 再 claim，不写 fresh readiness，不缓存 payload；普通异常和真实 handler bug 仍保留原 failure/dead-letter 语义。
- 文档影响：同步更新 read-models 状态机、runtime-workers 状态机/测试矩阵/实施记录。
- 测试覆盖：`tests/test_runtime_worker.py`、`tests/test_runtime_queue.py`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_defer_event_delays_dependency_retry_without_failure_or_dead_letter -v`。
- 未测风险：未在真实生产库重新采集全 app enqueue-to-fresh p95；如果 source projection 本身慢，defer 只能避免长 retry，不能替代 SQL/projection 优化。
- 后续事项：用 closure gate 观察 `runtime_worker.event_deferred` 与各 read model pending age，把持续高频 defer 的 source projection 纳入下一轮优化。

## 2026-06-13 - Workbench relation fan-out priority

- 目标：在 relation 写入 fan-out 中优先刷新 `workbench_relation` source read model，降低 downstream projection 因 relation distribution 未 fresh 而失败重试的概率。
- 影响范围：事务内 relation producer 写入 `job.read_model_dirty_scopes` 与 `job.outbox_events` 的 priority 字段。
- 关键决策：不改变 freshness 事实源，不新增缓存或队列；`workbench_relation` 使用 `high` priority，下游 read model 保持 `normal`。
- 文档影响：同步记录到 workbench-relations 和 runtime-workers；完整 dependency DAG 仍未完成。
- 测试覆盖：`tests/test_workbench_relation_repository.py` 和 runtime queue priority contract tests。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_repository.py -q`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_enqueue_read_model_refresh_increments_and_returns_source_version tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_enqueue_read_model_refresh_in_transaction_preserves_source_version_payload_and_outbox_contract -v`。
- 未测风险：未连接真实生产 PostgreSQL 重新采集 enqueue-to-fresh p95；priority 不能保证跨 lane 的完整依赖顺序。
- 后续事项：补 dependency-aware scheduler/deferral，并运行 `sync_slo_baseline` / `runtime_sync_closure_gate` 对比优化前后指标。

## 2026-06-18 - Workbench all parent shard dependency defer

- 目标：修复 Workbench `all` aggregate-only refresh 在 parent month shard 尚未完成刷新时，把暂态 active generation consistency mismatch 写成 failed all generation 的问题。
- 影响范围：`WorkbenchReadModelRefreshService`、`RuntimeWorker` dependency-not-fresh defer、Workbench read model dirty/outbox 依赖顺序。
- 根因：relation 写入会同时入队受影响月份 `workbench` shard 和 `workbench:all` aggregate；all aggregate 事件携带 `parent_scope_keys`，但 handler 没有检查这些 parent scope 是否仍 pending/processing。用户确认 OA + 两组已闭环外部往来时，新的 canonical relation 已提交，而旧 month generation 仍展示旧 turnover closure open rows，all 聚合的 parent consistency 因 `active_relation_open_membership` 报错。
- 第二轮复现补充：parent scope 不 active 但已有 failed/stale dirty scope 时也不能聚合；refresh-status 和 App Health 还必须把同一 scope 的旧 failed + 当前 pending/processing 合并为 `refreshing`，否则用户会继续看到已被重试覆盖的旧错误。
- 关键决策：`parent_scope_keys` 是依赖声明，不只是诊断字段。handler 在调用 aggregate builder 前先查 `RuntimeQueueRepository.read_model_refresh_is_active(...)` 和 `read_model_refresh_is_fresh(...)`；仍 active 或 not fresh 时抛 `workbench_read_model_not_fresh`，由 worker defer 并补投 dependency refresh，不写 failed readiness/generation。parent fresh 后 consistency 仍失败时继续 fail closed。
- 测试覆盖：新增 `tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_workbench_refresh_handler_defers_all_aggregate_while_parent_scope_refreshing`、`test_workbench_refresh_handler_defers_all_aggregate_while_parent_scope_failed`、`test_workbench_refresh_status_api_treats_requeued_failed_scope_as_refreshing`；`tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_read_model_refresh_is_fresh_checks_no_active_or_failed_dirty_scope` 保护 durable freshness 查询；`tests.test_runtime_worker` 保护 `*_read_model_not_fresh` defer。
- 验证命令：见关联台模块 2026-06-18 实施记录。
- 未测风险：未在真实生产 PostgreSQL 上执行截图 case 回放；发布后若已有旧 failed all aggregate，需要按 runtime worker governance requeue 或归档已覆盖历史 failure。

## 2026-06-13 - authenticated HTTP SLO fresh gate 收紧

- 目标：让全 app 页面“5 秒内已同步”的验收不再只看 HTTP 200/202 和耗时，而是检查真实 read model freshness。
- 影响范围：`http_slo_probe.py` 默认 probe 参数、`runtime_sync_closure_gate.py` 默认 HTTP target、闭环验收报告语义。
- 关键决策：默认 HTTP target 调整为 5000ms；默认探针使用更贴近前端首屏的参数，包括银行明细当前年日期范围和非空 search 查询；probe 只读取显式 `read_model_status`/`readModelStatus`，不把普通业务 `status` 字段误判为 read model 状态；非 fresh 或 refresh enqueued 直接失败。
- 文档影响：更新 read-models 实施记录和测试矩阵。
- 测试覆盖：`tests/test_http_slo_probe.py` 覆盖默认 probe、普通 status 字段、非 fresh/refresh enqueued 失败。
- 验证命令：见最终交付说明。
- 未测风险：authenticated HTTP SLO 的最终证明依赖真实登录态 cookie/token 和生产发布后的接口。
- 后续事项：接入 Prometheus/Grafana 或 OpenTelemetry 后，应把 enqueue-to-fresh latency、HTTP SLO p95、non-fresh count 和 refresh_enqueued count 变成持续指标。

## 2026-06-13 - Required RabbitMQ real consumers 生产切换

- 目标：把 required RabbitMQ eligible read model worker 从 PostgreSQL polling/wakeup 切到 RabbitMQ real consumer，降低 queue wakeup latency，并让 RabbitMQ Management metrics、queue depth、DLQ 和 consumer count 进入 `/health/ready` 观测闭环。
- 影响范围：`run_rabbitmq_staging_preflight` required/optional 检查边界、worker systemd 共享 RabbitMQ env、`RabbitMqConsumer.consume_forever()` interrupt 行为、生产 required worker env 和 RabbitMQ topology。
- 关键决策：preflight 默认只检查 required eligible worker；optional worker 需显式 `--include-optional-workers`。`/etc/fin-ops/fin-ops.rabbitmq-worker.env` 只存共享 `RABBITMQ_URL`，单 worker 是否切换仍由 `/etc/fin-ops/fin-ops.worker.<instance>.env` 的 `FIN_OPS_QUEUE_BACKEND` 决定。RabbitMQ DLQ 中没有 PostgreSQL outbox 对应行的 envelope 视为 transport orphan，先导出审计摘要再清理。
- 文档影响：更新 `docs/operations/runtime-sync-repair-2026-06-12.md`、`docs/operations/runtime-worker-governance.md` 和 `docs/operations/postgresql-runtime.md`。
- 测试覆盖：`tests/test_rabbitmq_staging_preflight.py` 覆盖 optional worker flag；`tests/test_deploy_oa_script.py` 覆盖共享 worker env 加载顺序；`tests/test_rabbitmq_runtime.py` 覆盖 consumer 收到 interrupt 后干净返回。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_staging_preflight tests.test_rabbitmq_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_oa_script tests.test_rabbitmq_staging_preflight tests.test_rabbitmq_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_runtime tests.test_runtime_worker tests.test_deploy_oa_script -v`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --help`；`bash scripts/verify.sh docs`；生产 preflight、topology apply、required worker cutover 和 `/health/ready` 检查。
- 未测风险：Prometheus/Grafana 或 OpenTelemetry 尚未接入；`read_model_refresh_duration_ms.p95` 仍约 17.77s，RabbitMQ 只解决 wakeup/transport，不解决重型 projection 执行耗时或慢 API N+1。
- 后续事项：进入 EXPLAIN/pg_stat 驱动的 relation-details、workbench groups、cost_statistics、pending_invoice 查询优化；再按 fresh gate 引入 Redis fresh-cache，并把 SLO 指标接入持续监控。

## 2026-06-12 - Worker shutdown release processing lease

- 目标：修复发布或 systemd stop 在 worker 已 claim outbox event 后留下 `processing` lease、导致页面等待 300s lock timeout 的尾延迟。
- 影响范围：`RuntimeQueueRepository.release_event()`、`RuntimeWorker.run_forever()` shutdown signal handling、runtime worker 测试和运维说明。
- 关键决策：shutdown 只释放当前 `worker_id` 持有的 `processing` event，恢复 `pending`、清 lock、回退本次 claim 增加的 `attempts`，写 `raw_payload.runtime_shutdown_release`；不释放其他 worker 的 lock，不伪造 done/fresh。
- 文档影响：更新 `docs/operations/runtime-worker-governance.md` 和 `docs/operations/runtime-sync-repair-2026-06-12.md`。
- 测试覆盖：`tests/test_runtime_queue.py::test_release_event_restores_worker_locked_processing_event_to_pending`；`tests/test_runtime_worker.py::test_run_forever_releases_claimed_event_on_shutdown_request`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_queue tests.test_runtime_queue_ops tests.test_rabbitmq_runtime -v`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --help`；`bash scripts/verify.sh docs`；生产发布 `main-3933b00f-stage6-202606122329` 后核对 `/health/ready`、队列表和 `fin-ops-worker@workbench.service` 日志。
- 未测风险：重型 handler 如果被 C 扩展或数据库调用长时间阻塞，Python signal 处理仍可能延迟到控制权返回；`read_model_refresh_duration_ms.p95` 仍约 17.77s，Stage 6 不解决真实重型 rebuild 的执行耗时。
- 后续事项：继续 RabbitMQ real consumers、Redis fresh-cache、EXPLAIN 驱动的索引/分区和 Prometheus/Grafana 或 OpenTelemetry SLO 阶段。

## 2026-06-12 - covered historical dead-letter 归档与 lock-timeout 风险定位

- 目标：把 Stage 4 后剩余的 10 条已被同 scope fresh/done 覆盖的历史 read-model dead-letter 归档，清零 `/health/ready.failed_jobs`，并保持真实后端同步证明。
- 影响范围：`backend/src/fin_ops_platform/tools/runtime_queue_ops.py`、`tests/test_runtime_queue_ops.py`、`RuntimeQueueRepository.resolve_dead_letter_event()` 的运维调用路径、生产 `job.outbox_events.raw_payload.operator_resolution`。
- 关键决策：新增 `resolve-covered-dead-letters --dry-run/--execute`，要求同一 `tenant_id + read_model_key + scope_type + scope_key` 有 `fresh_readiness` 或后续 `done` outbox proof，且同 scope 无 active dirty；execute 仍复用 repository 标记 `done` 并写 `operator_resolution`，不直接 SQL 改状态。
- 文档影响：更新 `docs/operations/runtime-worker-governance.md` 和 `docs/operations/runtime-sync-repair-2026-06-12.md`。
- 测试覆盖：`tests/test_runtime_queue_ops.py` 覆盖 exact-scope proof、无 proof 拒绝、bulk dry-run 不写、bulk execute 只处理 eligible event；`tests/test_runtime_queue.py` 覆盖 repository 写 `operator_resolution`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue_ops tests.test_runtime_queue -v`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_queue_ops resolve-covered-dead-letters --help`；`bash scripts/verify.sh docs`；生产 dry-run/execute/post dry-run 和 `/health/ready`。
- 未测风险：`/api/app-health` 认证态 UI 未用浏览器登录态直接截图验证；`/health/ready.read_model_refresh_duration_ms.p95` 仍是历史滚动窗口约 17.7s，不能证明 SLO 已达成。
- 后续事项：发布过程定位到 worker 被 systemd 重启后会留下 `processing` outbox，依赖 300s lock timeout 回收，必须优先做 worker graceful shutdown、lease release/reclaim 或 deploy restart 顺序修复。

## 2026-06-15 - Workbench all aggregate 自等待修复与操作级 projection

- 目标：修复 `workbench:all` aggregate-only event 已经发布 active generation 后，又因 `job.read_model_dirty_scopes` 中自身 pending 被 `get_workbench_refresh_status("all")` 判为 `refreshing`，导致 `workbench_all_scope_aggregate_not_published` 重试直至 dead-letter 的循环；同时缩短确认/撤回 overlay 的用户可见阻塞时间。
- 影响范围：`WorkbenchSqlProjectionBuilder.refresh_workbench_all_scope_from_active_shards()`、`WorkbenchReadModelRefreshService` aggregate publish gate、`WorkbenchWriteFacade` confirm/withdraw response contract、`ReconciliationWorkbenchPage` operation overlay。
- 关键决策：all aggregate 发布结果新增 `aggregate_published=true` 明确表达 active generation 已成功写出；handler 用该信号完成 dirty scope，再由完成动作让 readiness 收敛。确认/撤回写 API 返回受影响月份的操作级 `workbench_relation` freshness targets 与后端 operation projection，前端等 relation distribution fresh 后应用 projection；`workbench` month shard、`workbench:all` 和下游 read model 后台追赶但不阻塞用户操作，并通过 `*_cross_page` SLO profile 单独监控。
- 运维闭环：生产中已由旧版本产生的 `workbench/all` pending dirty scope 与 `workbench/all` dead-letter outbox 不能直接 SQL 改 green；发布修复后先让 worker 重新处理当前 pending/aggregate，已被后续 done/fresh 覆盖的 dead-letter 使用 `runtime_queue_ops resolve-covered-dead-letters --dry-run/--execute` 归档，并复查 `/health/ready`、dirty/outbox、active generation consistency。
- 验证命令：`python3 -m pytest tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_completes_all_when_aggregate_publish_is_confirmed_despite_self_dirty_status tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_confirm_link_response_returns_operation_freshness_targets_for_affected_scopes tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_link_response_returns_operation_freshness_targets_for_affected_scopes -q`；`npm test -- --run src/test/WorkbenchSelection.test.tsx`；`npm run build`。

## 2026-06-12 - 生产 legacy scope repair apply 与收敛验证

- 目标：发布包含 current-effective App Status、repair manifest 和 production dry-run SQL 修复的 release，并执行受控生产 repair apply，清理旧 `cost_statistics` legacy scope 对 App Status 的污染。
- 影响范围：生产 `job.read_model_dirty_scopes`、`job.outbox_events`、`read_model.app_status_readiness` 中的 legacy cost runtime 行；replacement scope 通过 `ReadModelRefreshGateway` 入队后由 worker 真实重建。
- 关键决策：只有 dry-run 证明 `current_uncovered_outbox_failure_count=0` 才执行 `--apply`；apply 删除 9 条 legacy runtime 行、补投 6 个规范 scope、记录 audit event `98e118a0-0209-4dc0-8ad6-56d30e4e9043`，不手工写 fresh readiness。
- 文档影响：新增 `docs/operations/runtime-sync-repair-2026-06-12.md` 并登记到 operations index。
- 测试覆盖：沿用 `tests/test_read_model_scope_contract.py` 覆盖 dry-run/apply/audit/rollback/current blocker 保留；生产验证覆盖真实 dirty/outbox/readiness 收敛。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract -v`；`PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help`；`bash scripts/verify.sh docs`；生产 `scripts/check-read-model-scope-contracts.py --json`、`--apply --reason production_scope_contract_repair --json`、post-check 和 `/health/ready`。
- 未测风险：`/api/app-health` 未认证请求返回 401，页面认证态 App Status 只通过后端事实源间接验证；剩余 10 条 covered historical dead-letter 未归档，仍会出现在 `/health/ready.failed_jobs`，但不再是 current-effective 页面 blocker。
- 后续事项：下一阶段用独立受控 dead-letter resolve/归档把历史已覆盖失败从 runtime failed count 中移除，然后进入 RabbitMQ real consumers、Redis fresh-cache、索引/分区和持续观测阶段。

## 2026-06-12 - 生产 dry-run SQL pattern 修复与基线记录

- 目标：执行生产只读 dry-run 和同步基线采集，验证 repair manifest 能在真实 PostgreSQL 上运行。
- 影响范围：`PostgresReadModelScopeContractRepository.list_read_model_outbox_failures()`、`tests/test_read_model_scope_contract.py`、生产同步基线文档。
- 关键决策：psycopg SQL 字符串中的 literal `%` 必须写成 `%%`，否则会被当成占位符解析；新增 repository 级测试锁定 `like '%%.read_model.refresh'`。
- 文档影响：新增 `docs/operations/runtime-sync-baseline-2026-06-12.md` 并登记到 operations index。
- 测试覆盖：`tests/test_read_model_scope_contract.py::test_postgres_repository_outbox_failure_query_escapes_psycopg_percent_pattern`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract -v`；生产只读 `scripts/check-read-model-scope-contracts.py --json`。
- 未测风险：本阶段未执行生产 `--apply`；App Status 变绿仍需下一阶段发布、repair、replacement scope 收敛后验证。
- 后续事项：发布包含 current-effective App Status、repair manifest 和本 SQL 修复的 release 后，再执行受控 repair apply。

## 2026-06-12 - Repair manifest 与 current-effective failure 分类

- 目标：把 scope contract dry-run 从单纯 cost statistics legacy 行检查，扩展为可审计 repair manifest，支持区分 legacy/invalid cost statistics runtime 状态、已被 later done/fresh readiness 覆盖的历史 outbox failure，以及仍然 current-effective 的未覆盖 failure。
- 影响范围：`ReadModelScopeContractService`、`PostgresReadModelScopeContractRepository`、`scripts/check-read-model-scope-contracts.py` 输出 contract、read-models 运维文档和测试矩阵。
- 关键决策：`--apply` 只删除非规范 cost statistics runtime 行并补投规范 replacement scope；current uncovered outbox failure 必须保留为真实 blocker，不自动删除、不伪造 fresh。apply 报告带 cleanup、rollback 和 audit event，便于生产修复留痕和回滚。
- 文档影响：更新 read-models `README.md`、`state-machine.md`、`tests.md`，并同步 runtime worker 运维说明。
- 测试覆盖：`tests/test_read_model_scope_contract.py` 新增 repair manifest 分类、audit/rollback、current blocker 保留和幂等 apply 覆盖；平台边界与 runtime queue 回归测试一起运行。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract tests.test_platform_runtime_boundary_guards tests.test_runtime_queue_ops -v`；`PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help`。
- 未测风险：当前本地 shell 未配置 PostgreSQL 连接串，未对真实生产库执行 `scripts/check-read-model-scope-contracts.py --json` dry-run 或 `--apply`。
- 后续事项：下一阶段先在生产连接配置下生成 baseline/dry-run JSON，确认 current uncovered failure 的真实原因，再决定 repair apply、requeue 或 worker/query 修复。

## 2026-06-11 - 测试闭环矩阵与状态机补齐

- 目标：按测试闭环 master goal 将 Read Model 模块迁入标准测试矩阵，明确影响面、场景覆盖、七类测试、历史 bug 回归库、关键 smoke flows、nightly 覆盖和未测风险。
- 影响范围：只改文档；覆盖 `ReadModelQueryGateway`、`ReadModelRefreshGateway`、scope policy/contract、runtime queue、readiness reporter、worker refresh scope 和 App Status readiness 的测试入口说明。
- 关键决策：当前无 P0 自动化缺口；生产真实 PostgreSQL `--apply`、真实 Redis/RabbitMQ/worker drain、业务页面 stale/refreshing UI 行为分别记录为 documented-risk，并交给发布前 dry-run、runtime-workers 和具体页面模块闭环处理。
- 文档影响：更新 `tests.md` 和 `state-machine.md`；全局状态文件记录 read-models 下一步状态。
- 测试覆盖：未新增测试；现有 `tests/test_read_model_freshness.py`、`tests/test_read_model_query_gateway.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_readiness_reporter.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py`、`tests/test_runtime_queue.py`、`tests/test_platform_runtime_boundary_guards.py` 覆盖 P0 边界。
- 验证命令：见本次最终说明。
- 未测风险：未连接真实生产 PostgreSQL 执行 scope contract `--apply`；未在本模块逐页面证明 stale/refreshing UI 行为；未验证真实 Redis/RabbitMQ 网络。
- 后续事项：下一模块处理 `runtime-workers`，继续补 worker/transport/readiness 运行风险。

## 2026-06-10 - Read model scope contract 生产检查与清理

- 目标：为生产库中已有的 legacy/invalid `cost_statistics` dirty scope、outbox event 和 App Status readiness 提供只读检查与受控修复入口。
- 影响范围：`ReadModelScopeContractService`、`PostgresReadModelScopeContractRepository`、`scripts/check-read-model-scope-contracts.py`、平台架构守卫。
- 关键决策：检查按当前 scope policy registry 判定 canonical、legacy 和 invalid；`--apply` 删除非规范旧状态，并通过 `ReadModelRefreshGateway` 去重补投可归一化的 replacement scope。完全非法 scope 只清理，不猜测 replacement。
- 文档影响：更新 read-models、cost-statistics、runtime-workers 和 runtime worker 运维文档。
- 测试覆盖：`tests/test_read_model_scope_contract.py` 覆盖只读检查、受控清理和 replacement scope 去重；`tests/test_platform_runtime_boundary_guards.py` 将新 repository 显式登记为允许写 job runtime 表的平台边界。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract tests.test_platform_runtime_boundary_guards -v`；`PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help`。
- 未测风险：未在真实生产数据库执行 `--apply`；上线操作需先 dry-run 检查报告。
- 后续事项：无。

## 2026-06-10 - Read model refresh scope gateway 阶段 1

- 目标：封住 worker lifecycle 向 `cost_statistics.read_model.refresh` 投递裸月份/裸 `all` 的入口，并建立轻量本地 scope policy/gateway 边界。
- 影响范围：`ReadModelScopePolicyRegistry`、`ReadModelRefreshGateway`、worker lifecycle read model refresh 入队。
- 关键决策：成本统计 scope policy 复用 `CostStatisticsRuntimeService.refresh_scope_keys_from_scope_keys(...)`，接受旧裸月份/裸 `all` 并展开为 `active/all` project scopes；未知 project scope fail fast。非成本统计 read model 暂使用通用 dedupe policy，保持现有 scope shape。
- 文档影响：更新 read-models、runtime-workers、cost-statistics 模块入口和测试矩阵。
- 测试覆盖：`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_generic_cost_statistics_enqueue_expands_month_scopes`、`tests/test_platform_runtime_boundary_guards.py`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_generic_cost_statistics_enqueue_expands_month_scopes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`。
- 未测风险：阶段 1 未包含真实生产库清理。
- 后续事项：已由后续 scope contract 检查/清理入口和架构守卫补齐。
## 2026-06-23 - Read model manifest parity guard

- 目标：把 14 个 App Status read model 的 key、scope type、refresh event、primary/auxiliary worker、query freshness contract、projection strategy、`all` scope 语义、owner 和 test owner 固化为代码级 manifest，作为后续页面 read model 模块化迁移的共享边界。
- 改动：新增 `backend/src/fin_ops_platform/services/read_model_manifest.py`；`ReadModelScopePolicyRegistry` 暴露 `registered_scope_types()` 供 parity guard 使用；新增 `tests/test_read_model_manifest.py` 校验 manifest 与 `APP_STATUS_READ_MODEL_REGISTRY`、`runtime_worker_registry.py`、RabbitMQ dispatch events 和 scope policy registry 一致。
- 边界：本轮不改变任何 API response shape、read model freshness 判定、refresh enqueue、worker claim、SQL repository 或前端行为；不引入 Go/Fiber/Go Worker；不做生产写入。
- 测试覆盖：新增 manifest parity 测试覆盖 service-layer/read model/worker registry 合同；既有 `tests/test_read_model_architecture_guards.py` 继续覆盖 `ReadModelQueryGateway.load(...)` expected contract、direct fresh status 分类和 direct source mismatch expected contract。
- 生产验证：本地无 `PGSQL_URL` 和 staging DB；本轮是静态/单测边界收紧，不需要生产写入。真实 DB/worker drain 不作为本 slice 完成条件。

## 2026-06-19 - Invoice relation all-scope source version 聚合排除历史空 scope

- 目标：修复 invoice relation 类 read model 默认 all 读取中，历史空月份 scope 的旧 source version 污染当前非空 all 页面 freshness 的问题。本次由生产 `output_invoice_collection` authenticated HTTP gate 暴露。
- 根因：`_invoice_relation_scope_row(scope_key="all")` 通过所有月度 scope 的共同 source versions 推导 all source versions；`row_count=0` 的历史空 scope 不贡献任何 rows，却会因为旧 `oa_projection_sync_version` 让共同版本字段被删除，进而让 API 返回 refreshing/stale。由于 all fan-out worker 不会刷新这些无 shard 的历史空 scope，问题可长期存在。
- 修复：当 all scope 存在 `row_count > 0` 的 scope rows 时，只用这些非空 scope rows 判断 cache status 和共同 source versions；没有非空 scope 时保留原 all-empty 行为，避免伪造 fresh。
- 测试覆盖：`tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_output_api_all_scope_ignores_stale_empty_month_scope_versions`；相邻回归 `test_input_api_all_scope_uses_rows_when_month_relation_versions_differ` 和 `test_output_api_stale_returns_refreshing_without_stale_rows` 保持通过。
- 生产验证：release `main-9e9546ac-output-invoice-all-scope-20260619173552` 通过 health ready；生产 DB 中 `output_invoice_collection` current dirty/outbox 为空；两个目标 OA 登录态下 output rows/filter-options 返回 `200 fresh`。
- 后续风险：该规则适用于 invoice relation all-scope 读取；其它 read model 的 all/aggregate scope 仍需按各自 scope contract 独立审计，不能泛化为“所有空 scope 都可忽略”。

## 2026-06-20 - 生产只读 P0/P2 审计与 dry-run helper 安全入口

- 目标：在只有唯一 production PostgreSQL、没有 staging 数据库的条件下，按 P0/P1/P2 安全门推进 read model/worker drain 证据，禁止业务事实写入和未经批准的 `--apply`。
- 生产只读证据：SSH `finops-prod` 以 `finops-deploy` 登录成功；`fin-ops.service`、`fin-ops-rabbitmq-dispatcher.service` 和 20 个 `fin-ops-worker@*.service` 均为 active；`/health` 与 `/health/ready` 返回 ready，`runtime_release.consistent=true`、`production_runtime_guard.consistent=true`、`queue_backend=postgres`、`redis_status=ready`、`workbench_relation_read_model.status=ready`、`workbench_relation_dirty_backlog=0`。
- 生产只读 scope contract：通过 root-owned helper 执行 `read-model-scope-contract <release> --json`，结果 `ok=true`、`violation_count=0`、`current_uncovered_outbox_failure_count=0`，未执行 `--apply`。
- P0 DB 表级闭环：使用 root 只读加载 runtime env 并在 PostgreSQL `BEGIN READ ONLY` 事务中执行固定聚合；`job.outbox_events` 157144 行全部 `done`，非 done 为空，recent `failed` / `dead_lettered` / `publish_failed` 样本为空；`job.read_model_dirty_scopes` 143101 行全部 `done`，非 done 为空；`read_model.app_status_readiness` 169 行全部 `fresh`，覆盖 14 个 read model key。
- P2 dry-run 闭环：安装 root-owned helper `/usr/local/sbin/finops-deploy-control`，SHA256 为 `9e8d57011e0b5b63e136a2159153cb943a31e6987162900a34a849f73eff7e89`，包含 `read-model-slo-smoke` 且拒绝 `--apply`；生产运行 `read-model-slo-smoke codex-http-slo-gzip-probe-3546e985-20260619210708 --json --critical-only --target-ms 5000` 返回 `status=dry_run`、`planned_scope_count=15`、`missing_read_model_keys=[]`，只发现 critical scopes，未 enqueue、未 apply、未写 DB。
- 生产数据质量发现：通过 root-owned helper 执行 `workbench-audit-identity <release> --json --limit 1`，Workbench 自身 `cross_zone_identity_duplicate_group_count=0`、`open_visible_owner_duplicate_group_count=0`、`orphan_relation_group_count=0`；但 OA attachment invoice 层存在 `blocking_issue_count=6`、`oa_attachment_invoice_blocking_duplicate_group_count=6` 的 cross-OA 重复，后续需单独判定是合法重复、解析别名还是导入/缓存去重缺陷。
- 本地安全改动：`deploy/oa/bin/finops-deploy-control.sh` 新增 `read-model-slo-smoke <release-name> [args]`，只调用固定模块 `fin_ops_platform.tools.read_model_slo_smoke` dry-run，并在 release lookup 与 runtime env 加载前拒绝 `--apply`；同版本 helper 已安装到生产 `/usr/local/sbin/finops-deploy-control`。
- 阻断项：P0 DB 表级只读聚合和 P2 critical dry-run 已闭合；direct enqueue-to-fresh `--apply` 仍不在本目标内，只有另有显式审批才可讨论。P1 Browser smoke 已在 app-health-operations 记录中闭合。
- 验证命令：`bash -n deploy/oa/bin/finops-deploy-control.sh`；`PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_oa_script -v`；本地 `read-model-slo-smoke fake-release --apply` 拒绝验证；生产 PostgreSQL `BEGIN READ ONLY` 固定聚合；生产 `sudo -n /usr/local/sbin/finops-deploy-control read-model-slo-smoke codex-http-slo-gzip-probe-3546e985-20260619210708 --json --critical-only --target-ms 5000`。
- 后续事项：6 个 OA attachment invoice cross-OA duplicate 继续走只读语义审计和 source alias/migration identity 修复设计；不要通过 SQL 删除缓存、发票或伪造 readiness。

## 2026-06-20 - OA attachment invoice cross-OA duplicate 只读审计

- 目标：对生产 `workbench-audit-identity` 暴露的 6 个 `oa_attachment_invoice` cross-OA blocking duplicate 做只读深挖，明确它们更像 OA 迁移/同步 alias，还是应进入人工业务去重。
- 只读证据：6 组均为 `classification=cross_oa`，`oa_attachment_invoice_duplicate_classification_counts={"cross_oa": 6}`；Workbench 自身 `cross_zone_identity_duplicate_group_count=0`、`open_visible_owner_duplicate_group_count=0`、`orphan_relation_group_count=0`，问题集中在 OA attachment invoice cache/source identity 层。
- 明细模式：`053002200111:15312761` 出现在 `oa-exp-2005` 与 `oa-exp-69898450db8c0a3633bd748c`，申请人周洁莹、日期 2026-02-01、金额 800.00、项目云南溯源科技一致；`153012525093:00233178` 出现在 `oa-exp-2035` 与 `oa-exp-69a7aeaedb8c0a3633bd74a7`，申请人胡瑢、日期 2026-03-01、金额 248.00、项目一致；其余 4 个 identity 均出现在 `oa-exp-2062` 与 `oa-exp-69c0b43adb8c0a3633bd74c4` 的同一 item 行，申请人刘际涛、日期 2026-03-01、金额 3061.64、项目组合一致。
- 代码判断：`audit_object_identity._classify_oa_attachment_invoice_duplicate_groups(...)` 只有在同一 canonical 发票 identity 映射到多个 `oa_application_id` / OA row/source 时才标为 `cross_oa`；同 OA 内的同一缓存、多实际附件或同实际附件 alias 会被分类为非 blocker。因此这 6 组不能简单视作缓存重复。
- 关键决策：当前不删除 OA attachment invoice cache、不删除发票、不手工改 readiness；下一步先建立 OA source alias / migration identity 证据，确认短号 `oa-exp-20xx` 与长 hash `oa-exp-69...` 是否代表同一 OA 单迁移后的新旧 ID。只有证明确为 alias，才应在 source identity/alias 合并层修复；若不是 alias，则应进入人工业务去重流程。
- 后续事项：新增只读 OA alias audit，比较两端 `oa_application_id`、`oa_source_id`、`row_id`、附件 hash、发票代码号码、金额、申请人、项目和 source row item；修复方案优先放在 OA source identity / attachment cache source mapping，而不是 downstream read model 或手工 SQL 清理。

## 2026-06-20 - 当前 gzip release critical read model apply 复验

- 目标：在唯一 production PostgreSQL 上补齐 P0/P1/P2 之后的 direct read model worker drain 证据；只允许 enqueue read model refresh 和等待 worker 收敛，不执行业务写接口、不删除或修改业务事实。
- 影响范围：生产 release `codex-http-slo-gzip-probe-3546e985-20260619210708` 的 15 个 critical read model scope、runtime queue、App Status readiness；不改变代码。
- 生产只读证据：`fin-ops.service`、`fin-ops-rabbitmq-dispatcher.service` 和 20 个 `fin-ops-worker@*.service` 均为 active；本机 `/health` 与 `/health/ready` 返回 `status=ready`，`runtime_release.consistent=true`、`production_runtime_guard.consistent=true`、`runtime_blocker_count=0`。scope contract 返回 `ok=true`、`violation_count=0`、`current_uncovered_outbox_failure_count=0`。
- Dry-run 证据：`finops-deploy-control read-model-slo-smoke codex-http-slo-gzip-probe-3546e985-20260619210708 --json --critical-only --target-ms 5000` 返回 `status=dry_run`、`planned_scope_count=15`、`missing_read_model_keys=[]`。
- Apply 证据：经显式批准后，在 root session 中直接运行 `read_model_slo_smoke --critical-only --apply --target-ms 5000 --timeout-seconds 90`；首轮 15 个 critical scope 均达到 outbox/dirty `done` 且 readiness `fresh` 或 `dirty_done`，但 5 个 scope 超过 5000ms target：`bank_detail:2026-01` 约 `5797.305ms`、`invoice_lifecycle:2026-04` 约 `9110.171ms`、`input_invoice_usage:2026-06` 约 `5694.337ms`、`cost_statistics:active:2026-04` 约 `7447.847ms`、`turnover_ledger:all` 约 `6478.222ms`。
- 聚焦复验：只重跑上述 5 个慢 scope 后，`bank_detail`、`input_invoice_usage`、`cost_statistics`、`turnover_ledger` 均通过，`invoice_lifecycle:2026-04` 仍约 `5798.987ms`；随后单跑 `invoice_lifecycle:2026-04` 通过，约 `1278.87ms`。
- 最终完整复跑：再次执行完整 critical `read_model_slo_smoke --critical-only --apply --target-ms 5000 --timeout-seconds 90`，15/15 pass，summary p50 约 `693.739ms`、p95/max 约 `4122.628ms`，handler p95/max 约 `3963.749ms`。该结果闭合当前 direct critical read model enqueue-to-fresh 证据。
- 复核：最终生产 PostgreSQL `BEGIN READ ONLY` 聚合显示 `job.outbox_events` 157193 行全部 `done`，`job.read_model_dirty_scopes` 143148 行全部 `done`，`read_model.app_status_readiness` 169 行全部 `fresh`；本轮 retry/full-rerun dirty scopes 全部 `done`。
- 未闭合风险：direct critical read model worker drain 已闭合，但首轮出现过接近 5s 的长尾，后续仍应在 write-operation E2E 或 nightly/发布前 gate 中继续观察。真实业务写操作 attribution 仍需要受控 mutating scenario、审批 ticket 和认证后才能证明，不能用 direct refresh 代替。
- 验证命令：本地 `bash scripts/verify.sh infra-smoke` 通过 77 tests、18 skipped；生产 `read-model-scope-contract --json`；生产 `read-model-slo-smoke --critical-only` dry-run；生产 direct `read_model_slo_smoke --critical-only --apply --target-ms 5000 --timeout-seconds 90` 首轮、聚焦复验、单项复验和完整复跑；生产 PostgreSQL 只读状态聚合；本机 `/health` 与 `/health/ready` 检查。

## 2026-06-20 - 当前 gzip release write-operation scenario 只读 dry-run

- 目标：在不执行业务写操作的前提下，重新发现当前 production 可用于 Write Operation E2E 的最小候选，并验证 scenario contract。
- 影响范围：生产 `write_operation_scenario_discovery`、`write_operation_e2e_smoke` dry-run；不执行 `--apply`、不调用 mutating HTTP、不写业务数据。
- Token 状态：当前本地 shell 和生产 runtime env 都未配置 `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` / `FIN_OPS_E2E_ADMIN_TOKEN` / user bearer/cookie，因此本轮不能验证 admin token 权限，也不能进入 apply。
- 只读 discovery：`write_operation_scenario_discovery --limit 20` 返回 `status=ready`，候选包括 turnover 20、Workbench withdraw 20、no-OA withdraw 20，并写出 `/tmp/finops-write-e2e-scenarios-20260620.json`。
- 最小 dry-run：选取 turnover `suggested` relation `turnover_rel_05cac958eb8c7c74`，生成 `/tmp/finops-write-e2e-scenarios-20260620-minimal-turnover.json`；`write_operation_e2e_smoke --scenario ... --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --json` 返回 `status=dry_run`、`scenario_count=1`、`auth_configured=false`、`approval_configured=false`。
- 关键决策：下一步如果要 apply，必须由用户明确批准具体 scenario `turnover-withdraw-turnover_rel_05cac958eb8c7c74`、提供 approval ticket，并重新提供可用 auth token；否则继续停留在 dry-run，不做 production mutation。

## 2026-06-24 - pending invoice selected as next modular IO read model pilot

- 目标：在 `bank_detail` 和 `workbench_relation` 本地实现支持完成当前 accounting 后，选择下一个非 Go read model 模块化 IO pilot。
- 决策：选择 `pending_invoice`，下一条边界为 `read-models:pending-invoice-repository-port-extraction`。
- 理由：`pending_invoice` 同时消费 `bank_detail_source_versions` 和 `workbench_relation_source_versions`，且有 `expense|income:<filter>[:YYYY-MM]` 特殊 scope；它是用户可见度高、最容易暴露“关系已更新但待找发票仍显示旧 fresh 行”的页面。
- 第一步范围：只抽取窄 `PendingInvoiceReadModelRepositoryPort`，覆盖 rows、filter options、source summary、bank detail/workbench relation source versions、projection save/mark。暂不改变业务状态、API shape、UI、worker runtime 或 Go/Fiber/Go Worker。
- 生产证据：本轮为 analysis-only，不需要生产验证；真实 PostgreSQL/worker/App Status/high-row/browser 证据继续按后续 implementation/verification slice 记录或递延。

## 2026-06-24 - pending invoice read model repository port extraction

- 目标：落实 `read-models:pending-invoice-repository-port-extraction`，让待找发票 read model 的查询和投影保存只依赖待找发票窄 repository port，不继续把完整 `PostgresReadModelRepository` 暴露给待找发票读路径。
- 影响范围：`PendingInvoiceReadModelRepositoryPort`、`PostgresStateStore.pending_invoice_sql_read_repository`、`SearchPendingSqlProjectionBuilder`、runtime worker projection builder wiring 和 `tests/test_search_pending_sql_runtime.py`。
- 关键决策：`PendingInvoiceReadModelRepositoryPort` 只暴露 pending invoice rows、filter options、source summary、bank detail/workbench relation source versions、projection save/mark。Search index 行为继续使用 search repository，不混入 pending invoice port。
- 非目标：不改 pending invoice 业务状态、筛选语义、API shape、UI、worker scope fan-out、Go/Fiber 或 Go Worker。
- 测试覆盖：新增 port contract 测试，证明 port 不暴露 search、bank detail、workbench relation 等无关 read model 方法；保留 pending invoice rows/source-version freshness 与 search index SQL runtime 回归。
- 验证命令：`python3 -m py_compile ...`；`PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime.PendingInvoiceReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_pending_invoice_repository_reads_rows_page_and_summary tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_pending_invoice_api_workbench_relation_source_version_stale_enqueues_refresh tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_search_api_reads_sql_index -v`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`；`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：本轮不连接真实 PostgreSQL，不验证 EXPLAIN、高行数分页、真实 worker drain 或 App Status；这些证据继续由后续 freshness/barrier audit 与生产 evidence/defer slice 处理。
- 后续事项：下一条边界审计 pending invoice freshness、force-refresh、特殊 scope 和 operation barrier，确认 read model 不会在关系或银行明细更新后伪装 fresh。

## 2026-06-24 - pending invoice freshness/barrier audit

- 目标：审计 `pending_invoice` fresh gate、expected source versions、force-refresh/page-first scope、worker base-scope expansion 和 operation barrier 合同。
- 结论：现有 rows/filter-options fresh gate、source-version stale enqueue、manifest force-refresh 合同、SLO page-first scope 和 worker month-shard expansion 已有测试/合同保护。
- 发现的 P0 缺口：`ReadModelScopePolicy` 对 `pending_invoice` 只校验 direction 与 month shape，不校验 direction-specific filter allowlist；非法 `expense:unknown_filter` 可能通过 gateway 后在 projection 阶段失败。下一条边界必须在 gateway scope policy 层 fail fast。
- 发现的 P1 缺口：pending invoice mutation 响应没有统一的 `freshness_targets` 合同；规则保存已有 `read_model_status=refreshing`，attach-existing/income-status 返回 affected months，但 operation barrier target 合同需要单独审/补。
- 非目标：本轮不改业务状态、API shape、UI、worker runtime 或生产数据；Go/Fiber/Go Worker 继续 blocked。

## 2026-06-24 - pending invoice scope policy filter allowlist

- 目标：让 `pending_invoice` refresh scope 在 `ReadModelRefreshGateway` 层拒绝非法 filter group，避免无效 scope 进入 durable queue 后才由 worker/projection 报错。
- 改动：`read_model_scope_policy.py` 新增 pending invoice expense/income allowlist；expense 只接受 `all`、`requires_invoice`、`bank_statement_as_invoice`、`no_invoice_required`，income 只接受 `all`、`requires_invoice`、`no_invoice_required`、`cash_income`。
- 测试覆盖：扩展 `tests/test_read_model_refresh_gateway.py`，证明合法 aggregate/month scope 仍 enqueue/dedupe，非法 `expense:cash_income`、`income:bank_statement_as_invoice` 和 unknown filter 不 enqueue。
- 非目标：不改业务筛选语义、API shape、SQL projection、worker expansion 或 UI。Projection 级 filter 校验仍作为 defense-in-depth。
- 后续事项：继续审/补 pending invoice mutation freshness target contract。

## 2026-06-24 - pending invoice mutation freshness target contract

- 目标：检查待找发票 mutation 后的页面 read model 同步语义，避免写成功后立即读旧 pending invoice rows。
- 结论：规则保存和 attach-existing 已在 `PendingInvoicesPage` 中等待 operation barrier；收入批量状态保存缺少 barrier wait。
- 改动：收入批量状态保存成功后，现在等待 `pending_invoice` 的当前 income filter/month scopes fresh，再 refetch rows；超时按现有规则保存/attach-existing 语义容忍后继续刷新。
- API 决策：不新增后端 `freshness_targets` 字段；当前 `affectedMonths` 足够让页面构造稳定 target，避免扩大 API shape。
- 测试覆盖：`web/src/test/PendingInvoicesPage.test.tsx` 断言收入批量状态保存会请求 `pending_invoice:income:all:2026-05` barrier；保留规则保存 timeout 回归。

## 2026-06-24 - pending invoice local implementation closure audit

- 目标：审计 `pending_invoice` 在 repository port、freshness gate、source-version proof、scope policy、worker fan-out、operation barrier、legacy contamination guard 和测试/docs 方面是否还有本地非 Go 小缺口。
- 结论：本地实现支持已可记为 accounted；未发现必须阻塞下一试点的本地 P0/P1 实现缺口。
- 保留面：`SearchPendingSqlProjectionBuilder.list_pending_invoice_scope_shards(...)` 仍作为 source-fact 月份枚举保留，不属于 pending invoice read-model repository port；未来若需要可单独抽 source-fact/provider port。
- 状态：`read-models:pending-invoice-local-implementation-closure-audit` 进入 `production-evidence-deferred`，但 `pending_invoice` 不标记为 module-closed；真实 PostgreSQL/worker/App Status/high-row/browser 证据仍延期。
- 下一步：先执行 `read-models:next-pilot-selection-after-pending-invoice`，重选下一个非 Go read model pilot；Go admission 继续 blocked。

## 2026-06-24 - OA pending payment selected as next modular IO read model pilot

- 目标：在 `bank_detail`、`workbench_relation`、`pending_invoice` 三个非 Go read model pilot 后，选择下一个试点。
- 决策：选择 `oa_pending_payment`，下一条边界为 `read-models:oa-pending-payment-repository-port-extraction`。
- 理由：`oa_pending_payment` 同时覆盖 completed OA projection、in-progress payment-admitted OA、Workbench relation、invoice lifecycle 和 pending bank claim，是“页面 A 更新、页面 B 不能读旧 fresh”风险较高的用户可见页面；已有 `OaPendingPaymentReadModelService`、manifest 合同和较完整测试，适合延续 repository port 首切模式。
- 首切范围：新增 `OaPendingPaymentReadModelRepositoryPort`，只暴露 manifest 登记的 rows/detail/save/mark/prune 方法，先收窄 SQL read model surface；不改 OA MySQL 写回、payment-admitted source adapter、pending relation promotion、command service、UI 或共享 worker 语义。
- 状态：Go/Fiber/Go Worker admission 继续 blocked。

## 2026-06-24 - OA pending payment repository port extraction

- 目标：为 `oa_pending_payment` 建立窄 read-model repository port，避免 rows/detail 和 projection save/mark/prune 继续依赖宽 `PostgresReadModelRepository` surface。
- 改动：新增 `OaPendingPaymentReadModelRepositoryPort`；`PostgresStateStore.oa_pending_payment_sql_read_repository` 返回该 port；`InvoiceUsageCollectionSqlProjectionBuilder` 的 OA pending payment save/mark/prune 走该 port；worker 构造时注入该 port。
- 边界决策：`workbench_relation_source_versions(...)` 不属于 OA port。`Application._oa_pending_payment_expected_source_versions(...)` 改为从 Workbench relation port 读取 relation source versions，避免 relation 事实污染 OA repository port。
- 保持不变：completed/in-progress 视图、OA MySQL 写回、payment-admitted source adapter、pending relation promotion、command service、UI、shared worker event semantics、API shape 均不变。
- 测试覆盖：新增 `OaPendingPaymentReadModelRepositoryPortTests`；新增 source-version owner 回归；复跑 OA API fresh/stale/source-version 目标测试和 invoice usage collection projection save/mark/prune/fan-out 目标测试。
- 下一步：审计 OA pending payment freshness、force-refresh、all fan-out/month proof 和 operation barrier 行为。

## 2026-06-20 - 当前 gzip release write-operation apply 被业务校验拒绝

- 目标：在用户明确批准后，对单条 turnover minimal scenario 执行 production Write Operation E2E apply，并验证真实写入口、read model/worker fan-out 和 post API probes。
- 影响范围：`turnover-withdraw-turnover_rel_05cac958eb8c7c74`；approval reference `FINOPS-PROD-WRITE-SMOKE-20260620-TURNOVER-001`；不允许自动切换到其它 scenario。
- 执行前快照：目标 relation 在 `app.turnover_relations` 中为 `status=suggested`、version `1`、counterparty `合肥钩知专利代理事务所（特殊普通合伙）`、bank row `txn_imported_1245`、金额 `2925.00`；执行前 outbox/dirty/readiness 全部干净。
- Apply 结果：`write_operation_e2e_smoke --apply` 成功带入认证和 approval，但写步骤 `POST /api/turnover-ledger/relations/turnover_rel_05cac958eb8c7c74/withdraw` 返回 `400 unexpected_status`；工具返回 `status=fail`，post API probes 与 write SLO 被跳过，没有继续执行其它 scenario。
- 执行后复核：relation 仍为 `suggested`、version `1`，无 `app.turnover_relation_events` 新增记录，apply 时间窗口无新增 outbox/dirty，`job.outbox_events` 全部 `done`、`job.read_model_dirty_scopes` 全部 `done`、`read_model.app_status_readiness` 全部 `fresh`。本次没有业务数据落地变更，不需要回滚。
- 关键结论：当前 discovery 选出的 `suggested` turnover relation 不是有效 withdraw apply 候选。已通过隔离 hotfix release `codex-write-scenario-discovery-hotfix-21a734b0-20260620` 发布 `write_operation_scenario_discovery` 修正：turnover 候选只选择 `source=manual` 的 relation，并读取 `raw_payload.normalized_payload.source`，避免 nested `source=system` 的系统候选被误选。发布后生产只读重跑 discovery 显示 turnover 候选 5 个，`turnover_sources=["manual"]`、`non_manual_turnover_candidates=0`；没有执行新的 mutating apply。

## 2026-06-20 - 贾小花 turnover write-operation scenario 复核

- 目标：评估用户指定的贾小花 300,000.00 收支闭环是否可作为真实 Write Operation E2E scenario，并在用户批准后尝试 apply。
- 只读匹配：`turnover_rel_89e8fb47e3ffce91` 为 `confirmed/manual`，三笔银行流水为 `txn_imported_1277` 2026-02-04 收 200,000.00、`txn_imported_1292` 2026-02-04 收 100,000.00、`txn_imported_1344` 2026-03-04 支 300,000.00，counterparty 均为贾小花，relation `settled_amount=300000.00`、`balance_amount=0.00`。
- Apply 结果：使用 production full-access 目标 OA 凭据在远端内存中获取 bearer token，执行 `write_operation_e2e_smoke --apply --approval-ticket FINOPS-PROD-WRITE-SMOKE-20260620-JIAXIAOHUA-TURNOVER-001`；写步骤 `POST /api/turnover-ledger/relations/turnover_rel_89e8fb47e3ffce91/withdraw` 返回 409，因此 write SLO 和 post API probes 未运行。
- 根因：active Workbench relation `case_id=turnover:turnover_rel_89e8fb47e3ffce91` 已包含三笔 bank row 和 `oa-pay-2025`，row types 为 bank/bank/bank/oa。该状态必须从关联台撤回完整关系，外部往来页 withdraw 入口按合同拒绝。
- 复核：relation 仍为 `confirmed`、version `1`；未新增 withdraw event；apply 时间窗口未新增 outbox/dirty；outbox/dirty/readiness 均无非 done / 非 fresh。本次没有业务数据落地变更。
- 后续：若继续推进这个样本，需新建 Workbench withdraw scenario，并由用户单独批准撤回 `case_id=turnover:turnover_rel_89e8fb47e3ffce91` 所代表的完整 active Workbench 关系。

## 2026-06-20 - 贾小花 Workbench 完整关系撤回结果

- 目标：在用户明确批准后，改用关联台 `withdraw-link` 撤回 `case_id=turnover:turnover_rel_89e8fb47e3ffce91` 的完整 active relation，并验证真实写入口、read model/worker fan-out 和 post API。
- 写入口：`POST /api/workbench/actions/withdraw-link`，payload `month=all`、`row_ids=["txn_imported_1344","txn_imported_1292","txn_imported_1277","oa-pay-2025"]`，approval reference `FINOPS-PROD-WRITE-SMOKE-20260620-JIAXIAOHUA-WORKBENCH-001`。
- 结果：写步骤 HTTP 200，约 `762.793ms`；post API probes 通过，Workbench grouped fresh，turnover ledger grouped 200。当前 active Workbench relation 已恢复为 bank-only `turnover_manual_closure`，仅包含三笔 bank row；原含 `oa-pay-2025` 的完整 relation 已撤回。外部往来 relation 本身保持 `confirmed`，余额仍 `0.00`。
- SLO：窄口径 `workbench_relation_withdraw` 通过；严格 `workbench_relation_withdraw_cross_page` 失败，原因是 `workbench:all`、`pending_invoice`、`cost_statistics` 超过 5 秒，且 `invoice_lifecycle`、`input_invoice_usage`、`tax_offset` 未产生该 profile 期待的近期 refresh event。该结果说明真实写入和基础 read model drain 成功，但这个样本不应直接等同于全下游跨页闭环；需要后续拆分“样本不适用 scope”和“真实性能长尾”。
- 2026-06-20 后续归因：`workbench_relation_withdraw_cross_page` 是 broad profile，不适合该 bank/turnover 恢复样本。新增 `workbench_relation_confirm_bank_turnover_cross_page` / `workbench_relation_withdraw_bank_turnover_cross_page` profile：要求 `workbench`、`workbench_relation`、`bank_detail`、`pending_invoice`、`cost_statistics`、`search`，但不要求 invoice-only 的 `invoice_lifecycle`、`input_invoice_usage`、`tax_offset`。本轮慢尾仍保留为 read model/worker 性能风险，不能因为 profile 拆分而视为 5s 写后跨页收敛已闭合。
- 生产只读下钻：bank/turnover profile 下 `pending_invoice` 慢尾不是 handler 本身慢，最终 `runtime_result.duration_ms` 多数只有几十到一百多毫秒；慢尾来自 `bank_detail_read_model_not_fresh` dependency defer，并由多个 pending scope 反复补投同一 `bank_detail:2026-03`，把银行明细 source version 从 `44635` bump 到 `44638`。`RuntimeWorker` 追加 dependency fresh guard：依赖 scope 已 fresh 时记录 `already_fresh`，不再 enqueue 依赖 refresh，避免下游 fan-out 自己制造新的 stale。
- 生产健康：写后 outbox/dirty/readiness 无非 done / 非 fresh；`/health/ready` ready；API、dispatcher 和 20 个 worker active。
