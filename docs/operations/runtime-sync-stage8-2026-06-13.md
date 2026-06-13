# Runtime 同步 Stage 8 - 写操作 Scenario Discovery

Stage 7 closure gate 证明当前剩余缺口集中在：

- 缺真实 OA 登录态，无法跑登录态 HTTP SLO。
- 缺受控、可回滚 mutating scenario，无法跑写操作 E2E。
- 24h 真实写操作 audit 缺高影响 operation profile 样本。

本阶段新增只读 discovery 工具，减少人工找测试对象的风险。

## 新增工具

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_scenario_discovery \
  --output /tmp/finops-write-operation-scenario-discovery-$(date +%Y%m%d%H%M%S).json \
  --scenario-output /tmp/finops-write-e2e-scenarios-$(date +%Y%m%d%H%M%S).json
```

工具行为：

- 只读 PostgreSQL，不执行 HTTP，不写数据库。
- 读取 `app.turnover_relations`、`app.workbench_pair_relations`、`app.no_oa_bank_batches` 的非敏感候选字段。
- 默认只把已被 `write_operation_slo_audit` 覆盖的 `turnover_manual_closure_or_withdraw` 候选写进 scenario JSON。
- `workbench_pair_withdraw_context` 与 `no_oa_bank_batch_withdraw_context` 只输出上下文，避免生成 audit profile 尚未覆盖的“半闭环”。

## 使用边界

生成的 scenario 不是自动批准执行。执行前必须确认：

- 该关系或批次是测试对象，或业务上允许撤回。
- 操作有明确回滚方式或可接受的审计记录。
- 使用真实 OA token/Admin-Token/cookie 执行，不开启 local-dev session，不伪造权限。

最终仍由 Stage 7 gate 判定闭环：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_sync_closure_gate \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --apply-read-model-smoke \
  --write-scenario /tmp/finops-write-e2e-scenarios.json \
  --apply-write-scenarios
```

只有 gate `status=pass` 才能宣称全 app 同步闭环完成。

## 本地验证

```bash
PYTHONPATH=backend/src python3 -m pytest \
  tests/test_write_operation_scenario_discovery.py \
  tests/test_write_operation_e2e_smoke.py \
  tests/test_runtime_sync_closure_gate.py \
  tests/test_write_operation_slo_audit.py -q

python3 -m py_compile \
  backend/src/fin_ops_platform/tools/write_operation_scenario_discovery.py \
  backend/src/fin_ops_platform/tools/write_operation_e2e_smoke.py \
  backend/src/fin_ops_platform/tools/runtime_sync_closure_gate.py
```

结果：18 passed；语法检查通过。
