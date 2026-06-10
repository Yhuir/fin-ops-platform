# 成本统计 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 成本统计 read model refresh scope 只允许 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 和 `all:all`；旧裸月份/裸 `all` 必须在统一 read model refresh gateway 中归一化，不能直接进入 durable queue。
- 生产库中已有的成本统计 legacy/invalid runtime scope 通过 `scripts/check-read-model-scope-contracts.py` 检查；`--apply` 删除旧状态，并补投可归一化的规范 replacement scope。

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

## 2026-06-10 - 成本统计生产旧 scope 检查与清理

- 目标：清理历史 `2026-03`、`2026-04`、裸 `all` 或未知 project scope 造成的成本统计 App Status readiness、dirty scope 和 dead-letter/outbox 污染。
- 影响范围：`read_model.app_status_readiness`、`job.read_model_dirty_scopes`、`job.outbox_events` 中 `cost_statistics` 相关旧状态。
- 关键决策：只删除当前 scope policy registry 不认为是 canonical 的成本统计状态；legacy scope 会通过 gateway 补投 `active/all` replacement scope，invalid scope 不猜测含义。
- 文档影响：更新成本统计测试矩阵和 runtime worker 运维 runbook。
- 测试覆盖：`tests/test_read_model_scope_contract.py` 覆盖检查、删除和 replacement enqueue 去重。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract -v`；`PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help`。
- 未测风险：未在真实生产数据库执行 `--apply`。
- 后续事项：无。

## 2026-06-10 - 成本统计 read model refresh scope contract

- 目标：阻止裸月份/裸 `all` 作为 `cost_statistics.read_model.refresh` scope 进入 durable queue，避免 SQL projection 报 `scope_key must use project_scope:month` 并污染 App Status readiness。
- 影响范围：成本统计 read model refresh 入队 contract、worker lifecycle 触发链路。
- 关键决策：合法成本统计 scope 统一为 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 和 `all:all`。旧裸月份/裸 `all` 只允许在统一 gateway 中归一化；未知 project scope 直接拒绝。
- 文档影响：更新成本统计、read-models、runtime-workers 模块入口和测试矩阵。
- 测试覆盖：`tests/test_read_model_refresh_gateway.py` 覆盖成本统计 policy，`tests/test_runtime_worker_read_model_refresh_scopes.py` 覆盖 worker lifecycle。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_generic_cost_statistics_enqueue_expands_month_scopes -v`。
- 未测风险：阶段 1 未执行真实生产库清理。
- 后续事项：已由后续 scope contract 检查/清理入口补齐。
