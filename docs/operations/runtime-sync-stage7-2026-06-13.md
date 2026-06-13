# Runtime 同步 Stage 7 - 全 App 闭环 Gate

本阶段新增 `fin_ops_platform.tools.runtime_sync_closure_gate`，把前几阶段分散的验证合成一个最终 gate。

## 为什么需要

Stage 3 证明 direct read model smoke 可以在 5 秒内收敛；Stage 4 证明页面/API probe 有覆盖面；Stage 5/6
补齐真实写操作 audit 和 E2E smoke 入口。但这些单项不能单独证明“全 app 每个页面一直已同步且 5 秒内真同步”。

最终必须同时满足：

- runtime health 没有当前 blocker。
- 每个 App Status read model 的 direct enqueue-to-fresh 在 5 秒内。
- 登录态页面 shell 与首屏 API p95 在 1 秒内。
- 最近真实写操作 durable outbox 样本覆盖高影响 operation profile。
- 受控 mutating HTTP scenario 通过，并证明写后 outbox/readiness fresh。

## 新增工具

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_sync_closure_gate --help
```

该工具聚合：

- `RuntimeMonitoringRepository.health_summary()`
- `read_model_slo_smoke.run_smoke(...)`
- `http_slo_probe.collect_http_slo(...)`
- `write_operation_slo_audit.audit_write_operation_slo(...)`
- `write_operation_e2e_smoke.run_write_operation_e2e_smoke(...)`

默认不会执行真实写操作。最终闭环必须显式传入：

- `--apply-read-model-smoke`
- `--write-scenario /tmp/finops-write-e2e-scenarios.json`
- `--apply-write-scenarios`
- `FIN_OPS_HTTP_SLO_ADMIN_TOKEN`、`FIN_OPS_HTTP_SLO_BEARER_TOKEN` 或 `FIN_OPS_HTTP_SLO_COOKIE`

## 当前生产结论

截至 Stage 6 已验证：

- `/health/ready` 为 `ready`。
- RabbitMQ queue/unacked/DLQ 为 0，consumer 为 16。
- required worker missing/stale/mismatch 为 0。
- direct read model smoke 14/14 通过，最慢约 1.153s。
- 非登录态页面 shell 17/17 通过，最大 p95 约 116ms。

仍未闭环：

- 生产 env 未配置 `FIN_OPS_HTTP_SLO_*`，无法证明登录态页面/API p95。
- `app.oa_applicant_credentials` 当前没有 configured 凭据，不能自动通过目标申请人登录 OA 获取 token。
- 24h 写操作 audit 仍缺高影响 operation profile 样本。
- 未提供安全可回滚的 mutating scenario，因此不能执行 `--apply-write-scenarios`。

这说明当前主要缺口不是 Kafka、PgBouncer 或 worker wakeup，而是最终验收材料：真实登录态和可回滚业务对象。

## 验收命令

```bash
export FIN_OPS_HTTP_SLO_ADMIN_TOKEN='真实管理员 Admin-Token'
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_sync_closure_gate \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --apply-read-model-smoke \
  --write-scenario /tmp/finops-write-e2e-scenarios.json \
  --apply-write-scenarios \
  --http-target-ms 1000 \
  --read-model-target-ms 5000 \
  --write-target-ms 5000 \
  --output /tmp/finops-runtime-sync-closure-gate-$(date +%Y%m%d%H%M%S).json
```

只有 `status=pass` 才能宣称全 app 同步闭环完成。`auth_missing`、`write_operation_e2e` 缺 scenario、只
dry-run、或 write audit missing 都是正确的失败结果。

## 本地验证

```bash
PYTHONPATH=backend/src python3 -m pytest \
  tests/test_runtime_sync_closure_gate.py \
  tests/test_write_operation_e2e_smoke.py \
  tests/test_write_operation_slo_audit.py \
  tests/test_http_slo_probe.py \
  tests/test_read_model_slo_smoke.py -q

python3 -m py_compile \
  backend/src/fin_ops_platform/tools/runtime_sync_closure_gate.py \
  backend/src/fin_ops_platform/tools/write_operation_e2e_smoke.py \
  backend/src/fin_ops_platform/tools/http_slo_probe.py \
  backend/src/fin_ops_platform/tools/read_model_slo_smoke.py
```

结果：26 passed；语法检查通过。
