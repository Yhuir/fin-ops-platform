# Canonical Facts Wave 5: Turnover Relation Extra Legacy Removal

日期：2026-06-28

## Slice

删除 Turnover relation-extra 的 production legacy fallback facade/factory。

## Code Change

- `backend/src/fin_ops_platform/app/server.py`
  - `_turnover_ledger_relation_extra_write_facade()` 不再 fallback 到 `_turnover_ledger_relation_extra_legacy_fallback_facade()`。
  - 删除 `_turnover_ledger_relation_extra_legacy_fallback_facade()` factory。
  - 移除 `TurnoverLedgerRelationExtraLegacyFallbackFacade` / `TurnoverLedgerRelationExtraLegacyFallbackAdapterSet` imports。
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
  - 删除 `TurnoverLedgerRelationExtraLegacyFallbackFacade`。
  - 删除 `TurnoverLedgerRelationExtraLegacyFallbackAdapterSet`。
  - `TurnoverLedgerRelationExtraRequestBoundaryFacade` 缺少 write facade 时 fail fast。
- `tests/test_platform_runtime_boundary_guards.py`
  - 禁止 production app/API/worker 文件重新出现 `TurnoverLedgerRelationExtraLegacyFallback`。
- `tests/test_turnover_ledger_api.py`
  - 新增缺 write facade fail-fast 测试。
  - 断言 `Application` 不再暴露 relation-extra legacy fallback factory。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_request_boundary_facade_wires_current_extra_reader_and_write_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_request_boundary_fails_fast_without_write_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_legacy_fallback_facade_is_removed -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
rg -n "TurnoverLedgerRelationExtraLegacyFallback|_turnover_ledger_relation_extra_legacy_fallback_facade" backend/src/fin_ops_platform/app backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py
```

结果：targeted tests 通过；`rg` 无生产代码命中。

## Remaining Wave 5 Work

Turnover confirm/closure/withdraw legacy fallback、Workbench pair snapshot references、GridFS migration、platform full snapshot/local pickle/App Mongo tooling isolation 仍未完成。
