# Read Models Spec-first E2E Coverage

## 覆盖矩阵

| Spec ID | 状态 | 当前证据 | 缺口 |
| --- | --- | --- | --- |
| `READMODEL-E2E-001` | `covered` | 各页面 Playwright smoke 覆盖 fresh 首屏、summary、筛选、导出入口；`tests/test_read_model_query_gateway.py`、`tests/test_read_model_freshness.py` 覆盖 fresh proof 和 cache contract。 | 真实生产大数据组合由 runtime smoke 继续观察。 |
| `READMODEL-E2E-002` | `partial` | Workbench、bank details、tax offset、cost statistics、input/output invoice、OA pending、no-OA、batch accounting、turnover 等页面已有 non-fresh false-empty 防护；`web/e2e/bank-flow-rule-batches-flow.spec.ts` 覆盖 no-OA `stale -> fresh` 期间保持可见 rows、不显示普通空态并自动重读；`web/e2e/batch-accounting-flow.spec.ts` 覆盖批量账务 relation read model stale 时保留当前银行/OA rows、显示 warning/reason/scope、不显示普通空态且零 mutation；`web/e2e/turnover-ledger-flow.spec.ts` 覆盖 turnover grouped ledger stale 时保留 rows、显示 warning 并禁用确认闭环写入口；共享 gateway 单测覆盖 missing/stale 入队。 | 不是每个页面都有完整 stale/refreshing/missing/failed Browser 组合。 |
| `READMODEL-E2E-003` | `covered` | Workbench、bank details auto-tag、batch accounting、turnover、no-OA、settings、pending invoices 等 Browser flow 覆盖 write -> barrier/fresh reload；`tests/test_operation_freshness_barrier.py` 保护 barrier contract。 | 真实业务写操作的生产 latency 归 `READMODEL-E2E-006`。 |
| `READMODEL-E2E-004` | `partial` | 多个 cross-page fan-out Playwright specs 和 `tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` 覆盖主要 fan-out。 | 全部写入口的真实 durable outbox 样本仍未闭合。 |
| `READMODEL-E2E-005` | `covered` | 2026-06-28 Read Model closure 已执行生产 critical SLO。`read_model_slo_smoke --apply --critical-only --target-ms 5000` grouped run 14/15 pass，唯一 Search miss targeted rerun `499.357ms` pass；scope contract `ok=true`、`violation_count=0`、current uncovered outbox failure count `0`，dirty/outbox/readiness 收敛。`bash scripts/verify.sh infra-smoke` 提供 opt-in apply gate。 | 每个新 release 仍需重新执行；Search 高行数 refresh latency 继续观察；真实业务写操作 latency 归 `READMODEL-E2E-006`。 |
| `READMODEL-E2E-006` | `partial` | `tests/test_write_operation_slo_audit.py`、`tests/test_write_operation_e2e_smoke.py`、`runtime_sync_closure_gate` 覆盖工具合同和 approval gate。 | 生产真实 write-operation apply 缺审批 ticket 和安全 scenario 样本。 |
| `READMODEL-E2E-007` | `covered` | `tests/test_read_model_scope_contract.py`、`scripts/check-read-model-scope-contracts.py`、runtime gate 只读检查覆盖 legacy/current blocker 分类。 | 真实 repair `--apply` 必须按 runbook 审批。 |

说明：`READMODEL-E2E-002/004/006` 的 `partial` 状态表示浏览器组合覆盖或真实业务写入样本不是 100% 枚举覆盖；它不推翻 read model 模块化 PSCIP-L4 闭环。PSCIP-L4 结论以 manifest/registry/worker/scope policy、freshness fail-closed、operation barrier、生产 scope contract 和 critical SLO 证据为准。

## 当前验证入口

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_read_model_readiness_reporter -v
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract tests.test_operation_freshness_barrier -v
bash scripts/verify.sh infra-smoke
```

## 下一步

1. 为一条低风险业务写 scenario 提供真实认证和审批 ticket，执行 write-operation apply，推进 `READMODEL-E2E-006`。
2. 后续每次生产 release 后都要重新执行 critical direct apply，防止 `READMODEL-E2E-005` 证据过期。
3. 页面新增写入口时，必须补对应页面 Browser flow，并映射到 `READMODEL-E2E-003/004/006`。
