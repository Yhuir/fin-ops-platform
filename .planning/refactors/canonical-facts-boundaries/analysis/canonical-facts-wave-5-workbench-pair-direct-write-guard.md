# Canonical Facts Wave 5: Workbench Pair Direct Write Guard

日期：2026-06-28

## Slice

验证并锁定 Workbench pair relation direct write fallback 不再回到 production app/service 链路。

## Evidence

- Production write owner 是 `WorkbenchRelationCommandService`。
- Domain mutation implementation 仍保留在 `WorkbenchPairRelationService`，但不允许非 owner production caller 直接调用。
- 当前扫描未发现 `app/` 或 `services/` 中除 owner/domain 文件外直接调用：
  - `create_active_relation`
  - `cancel_relation`
  - `record_history`
  - `replace_with_confirmed_relation`

## Change

- `tests/test_platform_runtime_boundary_guards.py`
  - 新增 `test_canonical_workbench_pair_relation_direct_write_fallbacks_do_not_return`。
  - 允许文件仅限：
    - `workbench_pair_relation_service.py`
    - `workbench_relation_command_service.py`
  - 其他 production app/service 文件若重新通过 `pair_relation_service` 直接写 pair relation，会失败。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_workbench_pair_relation_direct_write_fallbacks_do_not_return -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## Closure Note

本 slice 没有删除运行时代码，因为未发现剩余 production direct write fallback。闭环方式是把“已无可删 direct fallback”的事实变成静态 guard。Repair/rollback/persist snapshot 路径仍按各自 owner 文档治理，不等同于 production direct write fallback。
