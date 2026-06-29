# Canonical Facts Wave 5: PostgreSQL Full-State Snapshot Deploy Guard

日期：2026-06-28

## Slice

锁定 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT` 不能进入生产部署模板或正常 release 流程。

## Evidence

- `Application.readiness_summary()` 已在 production runtime guard 下把 full-state snapshot flag 标为 `not_ready`。
- `deploy/oa/env/*.env.example`、`deploy/oa/fin_ops.env.example` 和 `deploy/oa/bin/finops-deploy-control.sh` 当前没有配置 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT`。
- `scripts/deploy_oa.py` 仍调用 `finops-deploy-control check-release`。

## Change

- `tests/test_platform_runtime_boundary_guards.py`
  - 新增 `test_deploy_runtime_templates_do_not_enable_postgres_full_state_snapshot`。
  - 扫描 release env templates 和 deploy control script，禁止出现 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT`。
  - 保留 `deploy_oa.py` 必须调用 `check-release` 的轻量断言。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_deploy_runtime_templates_do_not_enable_postgres_full_state_snapshot -v
```

结果：通过。

## Closure Note

本 slice 没有删除 `PostgresStateStore.load_bootstrap_snapshot()`，因为它仍被测试、migration/shadow 和显式 legacy bootstrap 场景引用。生产 closure 现在有两层防线：runtime readiness guard 和 deploy template guard。最终删除仍需要另一个 migration/tooling slice 证明所有 tool-only 调用有 owner、dry-run/audit/rollback 和删除条件。
