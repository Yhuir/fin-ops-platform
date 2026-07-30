---
quick_id: 260731-79t
title: Production-equivalent Release Gate Verification
status: local_pass_production_pending
date: 2026-07-31
---

# 验证记录

## 本地通过

- `PYTHONPATH=backend/src python3 -m pytest -q tests/test_runtime_sync_closure_gate.py tests/test_write_operation_e2e_smoke.py tests/test_search_sql_runtime.py tests/test_deploy_oa_script.py`
  - 124 passed, 1 skipped
- `PYTHONPATH=backend/src python3 -m pytest -q tests/test_production_external_gate_preflight.py tests/test_deploy_runtime_examples.py tests/test_write_operation_impact_matrix.py`
  - 35 passed
- `bash scripts/verify.sh lint`
- `bash scripts/verify.sh docs`
- `bash -n deploy/oa/bin/finops-deploy-control.sh`
- `git diff --check`

## 测试类别

- 业务核心：可逆 confirm/withdraw/recovery、动态 idempotency key、非法 fixture 合同拒绝。
- Service/后台任务：durable queue、worker/runtime 后置采样与收敛阻断。
- API 合同：页面/API 双 origin、canonical Audit、写操作 evidence 合同。
- Read model/queue：enqueue-to-fresh、dirty/outbox/dead-letter 与 T+300 稳定性。
- 前端交互：不适用；本次不改变页面组件或用户交互。
- E2E：正式部署入口执行真实 PostgreSQL、RabbitMQ、worker、可逆写操作和 canonical Audit。
- 回归：部署 helper、既有 gate、Workbench 搜索结果与 SQL 查询次数。

## 生产待验证

正式发布必须由 `/opt/fin-ops/runtime-smoke/release-gates/<release>/evidence.json` 给出最终 PASS；测试夹具不存在或不安全时不得激活。
