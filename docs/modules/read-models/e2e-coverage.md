# Read Models Spec-first E2E Coverage

## 覆盖矩阵

| Spec ID | 状态 | 当前证据 | 缺口 |
| --- | --- | --- | --- |
| `READMODEL-E2E-001` | `covered` | 各页面 Playwright smoke 覆盖 fresh 首屏、summary、筛选、导出入口；`tests/test_read_model_query_gateway.py`、`tests/test_read_model_freshness.py` 覆盖 fresh proof 和 cache contract。 | 真实生产大数据组合由 runtime smoke 继续观察。 |
| `READMODEL-E2E-002` | `partial` | Workbench、bank details、tax offset、cost statistics、input/output invoice、OA pending、no-OA、batch accounting、turnover 等页面已有 non-fresh false-empty 防护；`web/e2e/bank-flow-rule-batches-flow.spec.ts` 覆盖 no-OA `stale -> fresh` 期间保持可见 rows、不显示普通空态并自动重读；`web/e2e/batch-accounting-flow.spec.ts` 覆盖批量账务 relation read model stale 时保留当前银行/OA rows、显示 warning/reason/scope、不显示普通空态且零 mutation；`web/e2e/turnover-ledger-flow.spec.ts` 覆盖 turnover grouped ledger stale 时保留 rows、显示 warning 并禁用确认闭环写入口；共享 gateway 单测覆盖 missing/stale 入队。 | 不是每个页面都有完整 stale/refreshing/missing/failed Browser 组合。 |
| `READMODEL-E2E-003` | `covered` | Workbench、bank details auto-tag、batch accounting、turnover、no-OA、settings、pending invoices 等 Browser flow 覆盖 write -> barrier/fresh reload；`tests/test_operation_freshness_barrier.py` 保护 barrier contract。 | 真实业务写操作的生产 latency 归 `READMODEL-E2E-006`。 |
| `READMODEL-E2E-004` | `partial` | 多个 cross-page fan-out Playwright specs 和 `tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` 覆盖主要 fan-out。 | 全部写入口的真实 durable outbox 样本仍未闭合。 |
| `READMODEL-E2E-005` | `covered` | 2026-06-28 Read Model closure 已执行生产 critical SLO。`read_model_slo_smoke --apply --critical-only --target-ms 5000` grouped run 14/15 pass，唯一 Search miss targeted rerun `499.357ms` pass；scope contract `ok=true`、`violation_count=0`、current uncovered outbox failure count `0`，dirty/outbox/readiness 收敛。`bash scripts/verify.sh infra-smoke` 提供 opt-in apply gate。 | 每个新 release 仍需重新执行；Search 高行数 refresh latency 继续观察；真实业务写操作 latency 归 `READMODEL-E2E-006`。 |
| `READMODEL-E2E-006` | `partial` | `tests/test_write_operation_slo_audit.py`、`tests/test_write_operation_e2e_smoke.py`、`tests/test_write_operation_scenario_discovery.py` 覆盖独立受控业务写工具、approval gate、标准 scenario 发现规则和页面级 `page_write_scenario_policy`。自动 `runtime_sync_closure_gate` 不再接收业务 scenario/ticket，也不修改真实业务关系；它改用隔离 `pg_temp` 写探针、近期真实写审计和只读 canonical page audit。 | 真实业务写 apply 只允许运维人员显式运行独立工具；自动发布门禁不会制造真实审计记录，因此生产写后 1s SLO 的样本覆盖仍取决于近期真实写事件或单独审批 smoke。 |
| `READMODEL-E2E-007` | `covered` | `tests/test_read_model_scope_contract.py`、`scripts/check-read-model-scope-contracts.py`、runtime gate 只读检查覆盖 legacy/current blocker 分类。 | 真实 repair `--apply` 必须按 runbook 审批。 |
| `READMODEL-E2E-008` | `covered-local-production-readonly-partial` | `docs/dev/page-read-model-fact-display-matrix.json` 枚举当前 17 个页面 route/pageKey、read model key、HTTP SLO probe、事实源、配对关系事实源和 Browser/API 证据锚点；`tests/test_page_read_model_fact_display_matrix.py` 校验矩阵与页面注册表、App Status read model registry、HTTP probe registry 和证据文件一致，并阻止当前页面矩阵引用 legacy `no_oa_bank_batch`。 | 该测试证明“每个页面都有 fresh/read fact display 覆盖合同和本地 deterministic 证据”，不等于生产受控写后所有页面强可见；真实 mutating cross-page freshness 仍归 `READMODEL-E2E-006` 和后续写操作影响矩阵。 |
| `READMODEL-E2E-009` | `covered-local-production-gated` | `docs/dev/write-operation-impact-matrix.json` 覆盖 `write_operation_slo_audit` 当前全部 24 个 operation profile，逐项登记 source page、write endpoint、事实源、配对关系事实源、expected outbox scopes、目标 read models/pages、生产 gate policy 和 deterministic 证据；`tests/test_write_operation_impact_matrix.py` 强制矩阵与 audit profile、App Status registry、页面矩阵、standing ticket policy 和证据文件同步。 | 该测试证明“每个写 profile 都有影响矩阵和 SLO gate 合同”，但不执行生产写入；`standing_apply` 仍必须由真实认证、standing ticket 和 `write_operation_e2e_smoke --apply` 证明，导入/设置类写入仍需 staging 或单次审批。 |

说明：`READMODEL-E2E-002/004/006` 的 `partial` 状态表示浏览器组合覆盖或真实业务写入样本不是 100% 枚举覆盖；它不推翻 read model 模块化 PSCIP-L4 闭环。full external PSCIP-L4 / 高性能全域闭环必须额外满足 authenticated HTTP/SSE、隔离写探针、近期真实写审计、写后 outbox/readiness 和页面 API SLO；真实业务写 apply 是独立、显式审批的运维动作，不属于自动 release gate。

## 当前验证入口

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_read_model_readiness_reporter -v
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract tests.test_operation_freshness_barrier -v
PYTHONPATH=backend/src:. python3 -m pytest tests/test_page_read_model_fact_display_matrix.py tests/test_write_operation_impact_matrix.py tests/test_spec_first_e2e_docs.py -q
bash scripts/verify.sh infra-smoke
```

## 下一步

1. 使用自动 release gate 持续验证隔离写、近期真实写审计和只读 canonical audit；只有需要补充真实业务写样本时，才由运维人员使用固定 scenario 和 approval ticket 显式运行独立 write E2E。
2. 后续每次生产 release 后都要重新执行 critical direct apply，防止 `READMODEL-E2E-005` 证据过期。
3. 页面新增写入口时，必须补对应页面 Browser flow，并映射到 `READMODEL-E2E-003/004/006`。
