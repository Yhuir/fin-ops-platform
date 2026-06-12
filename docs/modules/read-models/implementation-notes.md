# Read Model 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- read model refresh 入队前由统一 scope policy/gateway 负责 normalize、validate 和 dedupe；`RuntimeQueueRepository` 继续只负责 PostgreSQL durable queue 持久化。
- 生产旧 runtime 状态的 scope contract 检查/清理由 `ReadModelScopeContractService` 编排，SQL 限定在 `PostgresReadModelScopeContractRepository`，清理后通过 `ReadModelRefreshGateway` 补投规范 replacement scope。

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

## 2026-06-12 - Worker shutdown release processing lease

- 目标：修复发布或 systemd stop 在 worker 已 claim outbox event 后留下 `processing` lease、导致页面等待 300s lock timeout 的尾延迟。
- 影响范围：`RuntimeQueueRepository.release_event()`、`RuntimeWorker.run_forever()` shutdown signal handling、runtime worker 测试和运维说明。
- 关键决策：shutdown 只释放当前 `worker_id` 持有的 `processing` event，恢复 `pending`、清 lock、回退本次 claim 增加的 `attempts`，写 `raw_payload.runtime_shutdown_release`；不释放其他 worker 的 lock，不伪造 done/fresh。
- 文档影响：更新 `docs/operations/runtime-worker-governance.md` 和 `docs/operations/runtime-sync-repair-2026-06-12.md`。
- 测试覆盖：`tests/test_runtime_queue.py::test_release_event_restores_worker_locked_processing_event_to_pending`；`tests/test_runtime_worker.py::test_run_forever_releases_claimed_event_on_shutdown_request`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_queue -v`。
- 未测风险：尚未发布到生产并用真实 systemd stop 验证 release path；重型 handler 如果被 C 扩展或数据库调用长时间阻塞，Python signal 处理仍可能延迟到控制权返回。
- 后续事项：发布后做 controlled worker restart smoke，确认不再产生 300s processing backlog；随后继续 RabbitMQ real consumers 和性能 SLO 阶段。

## 2026-06-12 - covered historical dead-letter 归档与 lock-timeout 风险定位

- 目标：把 Stage 4 后剩余的 10 条已被同 scope fresh/done 覆盖的历史 read-model dead-letter 归档，清零 `/health/ready.failed_jobs`，并保持真实后端同步证明。
- 影响范围：`backend/src/fin_ops_platform/tools/runtime_queue_ops.py`、`tests/test_runtime_queue_ops.py`、`RuntimeQueueRepository.resolve_dead_letter_event()` 的运维调用路径、生产 `job.outbox_events.raw_payload.operator_resolution`。
- 关键决策：新增 `resolve-covered-dead-letters --dry-run/--execute`，要求同一 `tenant_id + read_model_key + scope_type + scope_key` 有 `fresh_readiness` 或后续 `done` outbox proof，且同 scope 无 active dirty；execute 仍复用 repository 标记 `done` 并写 `operator_resolution`，不直接 SQL 改状态。
- 文档影响：更新 `docs/operations/runtime-worker-governance.md` 和 `docs/operations/runtime-sync-repair-2026-06-12.md`。
- 测试覆盖：`tests/test_runtime_queue_ops.py` 覆盖 exact-scope proof、无 proof 拒绝、bulk dry-run 不写、bulk execute 只处理 eligible event；`tests/test_runtime_queue.py` 覆盖 repository 写 `operator_resolution`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue_ops tests.test_runtime_queue -v`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_queue_ops resolve-covered-dead-letters --help`；`bash scripts/verify.sh docs`；生产 dry-run/execute/post dry-run 和 `/health/ready`。
- 未测风险：`/api/app-health` 认证态 UI 未用浏览器登录态直接截图验证；`/health/ready.read_model_refresh_duration_ms.p95` 仍是历史滚动窗口约 17.7s，不能证明 SLO 已达成。
- 后续事项：发布过程定位到 worker 被 systemd 重启后会留下 `processing` outbox，依赖 300s lock timeout 回收，必须优先做 worker graceful shutdown、lease release/reclaim 或 deploy restart 顺序修复。

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
