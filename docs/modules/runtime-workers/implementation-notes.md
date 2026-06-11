# Runtime Worker 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- Worker lifecycle 触发 read model refresh 时必须走统一 scope policy/gateway 入队；worker 不直接拼接或投递成本统计等 read model 的业务 scope contract。
- 非事务 read model refresh producer 由 architecture guard 约束：不得绕过 `ReadModelRefreshGateway` 直接调用 `RuntimeQueueRepository.enqueue_read_model_refresh(...)`。

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

## 2026-06-11 - 测试闭环矩阵与状态机补齐

- 目标：执行测试闭环 master goal 的 runtime-workers 模块轮次，先审计 worker/queue/readiness/transport 影响面，再补齐模块文档。
- 影响范围：`runtime-workers` 模块文档、状态机、测试矩阵、历史 bug 回归库、模块验证命令。
- 关键决策：本轮未发现 P0 自动化缺口；现有测试已覆盖 worker loop、durable queue、registry/manifest、readiness reporter、runtime monitoring、RabbitMQ envelope/dispatcher/consumer、ops 命令和平台边界守卫。真实 RabbitMQ、真实 Postgres migration、systemd worker drain 保持 documented-risk，由 staging/运维 gate 验证。
- 文档影响：更新 `tests.md` 和 `state-machine.md`；长期 worker/read model 治理事实仍以 `docs/operations/runtime-worker-governance.md` 为准。
- 测试覆盖：沿用 `tests/test_runtime_worker.py`、`tests/test_runtime_worker_registry.py`、`tests/test_runtime_queue.py`、`tests/test_runtime_monitoring.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py`、`tests/test_read_model_readiness_reporter.py`、`tests/test_rabbitmq_runtime.py`、`tests/test_runtime_queue_ops.py`、`tests/test_runtime_state_policy.py`、`tests/test_deploy_runtime_examples.py`、`tests/test_platform_runtime_boundary_guards.py` 和 `tests/test_app_status_readiness_backfill.py`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_worker_registry tests.test_runtime_queue tests.test_runtime_monitoring -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract tests.test_read_model_readiness_reporter -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_runtime tests.test_runtime_queue_ops tests.test_runtime_state_policy tests.test_deploy_runtime_examples -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards tests.test_app_status_readiness_backfill -v`。
- 未测风险：无真实基础设施环境变量时，不运行 `tests/test_runtime_infrastructure_postgres_integration.py`、`tests/test_rabbitmq_integration.py` 和真实 staging preflight。
- 后续事项：下一模块继续处理 `domain-events-lifecycle`。

## 2026-06-10 - Read model refresh producer gateway guard

- 目标：防止 app/API、service、backfill 或 worker lifecycle 新增 producer 时绕过统一 scope policy/gateway。
- 影响范围：非事务 read model refresh 入队调用点、运维脚本、平台 runtime 边界测试。
- 关键决策：已有非事务 producer 分批迁到 `ReadModelRefreshGateway`；事务内 writer 保留同事务 dirty/outbox 语义，不机械改造成普通 gateway。
- 文档影响：更新 runtime-workers 和 read-models 测试矩阵。
- 测试覆盖：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_read_model_refresh_producers_use_scope_gateway_boundary`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`。
- 未测风险：未覆盖真实生产 worker 长时间运行行为。
- 后续事项：无。

## 2026-06-10 - Worker lifecycle 成本统计 scope 归一化

- 目标：修复 worker lifecycle 在 ETC/导入等事件后向 `cost_statistics.read_model.refresh` 投递裸月份/裸 `all`，导致成本统计 SQL projection 拒绝 scope 的问题。
- 影响范围：`_RuntimeWorkerDerivedLifecycle._enqueue_scopes`、read model refresh gateway。
- 关键决策：保留 `RuntimeQueueRepository` durable queue 边界，worker 只通过 gateway 入队；成本统计 scope contract 在入队前统一 normalize、validate、dedupe。
- 文档影响：更新 runtime-workers、read-models、cost-statistics 模块文档和测试矩阵。
- 测试覆盖：新增 `tests/test_runtime_worker_read_model_refresh_scopes.py`，覆盖 worker lifecycle 不再投递 `2026-03`、`2026-04`、`all` 给成本统计，并验证 `tax_offset` 等非成本 read model 不被成本统计规则误改。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`。
- 未测风险：未运行真实 import worker 到 SQL projection 完成的端到端场景。
- 后续事项：已由后续 architecture guard 补齐。
