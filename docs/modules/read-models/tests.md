# Read Model 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_read_model_refresh_gateway.py` | 覆盖 read model refresh scope contract 的 normalize、validate、dedupe 规则。 |
| 2. Service-layer tests | 适用 | `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` | 覆盖 gateway 委托 queue repository、worker lifecycle 使用统一入队边界，以及生产旧 scope contract 检查/清理编排。 |
| 3. API contract tests | 按需适用 | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_generic_cost_statistics_enqueue_expands_month_scopes` | 当前不改变 HTTP response shape；保留 app/API generic enqueue 旧契约回归。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` | 覆盖成本统计 read model refresh scope 入队前规范化，防止非法 dirty/outbox scope，并覆盖旧 readiness/dirty/outbox scope 清理。 |
| 5. Frontend component and interaction tests | 不适用 | N/A | 本变更不改前端页面、控件或 UI 状态。 |
| 6. End-to-end business-flow integration tests | 按需适用 | `tests/test_runtime_worker_read_model_refresh_scopes.py` | 当前阶段以 worker lifecycle 边界测试保护跨模块入队链路；完整导入到 worker 投影端到端可在后续阶段补充。 |
| 7. Existing feature regression tests | 适用 | `tests/test_platform_runtime_boundary_guards.py` | 覆盖现有 runtime 边界不被破坏；非成本统计 read model scope 不被成本统计规则误改；app/service/tool/script producer 不绕过 gateway。 |

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_generic_cost_statistics_enqueue_expands_month_scopes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v
```

## 未测风险

- 未在单测中连接真实生产 PostgreSQL 执行 `scripts/check-read-model-scope-contracts.py --apply`；发布前后需先 dry-run 检查 JSON 报告，再按 runbook 执行受控清理。
