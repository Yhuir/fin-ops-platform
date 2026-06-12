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
