# Canonical Facts Wave 5: Turnover Bank Row Tags Legacy Class Removal

日期：2026-06-28

## Slice

删除 Turnover bank-row-tags 的 legacy fallback facade/factory 本体。

## Code Change

- `backend/src/fin_ops_platform/app/server.py`
  - `_turnover_ledger_bank_row_tags_write_facade()` 不再 fallback 到 `_turnover_ledger_bank_row_tags_legacy_fallback_facade()`。
  - 删除 `_turnover_ledger_bank_row_tags_legacy_fallback_facade()` factory。
  - 移除 `TurnoverLedgerBankRowTagsLegacyFallbackAdapterSet` / `TurnoverLedgerBankRowTagsLegacyFallbackFacade` imports。
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
  - 删除 `TurnoverLedgerBankRowTagsLegacyFallbackFacade`。
  - 删除 `TurnoverLedgerBankRowTagsLegacyFallbackAdapterSet`。
- `tests/test_platform_runtime_boundary_guards.py`
  - 禁止 production app/API/worker 文件重新出现 `TurnoverLedgerBankRowTagsLegacyFallback`。
- `tests/test_turnover_ledger_api.py`
  - 更新 characterization，断言 `Application` 不再暴露 `_turnover_ledger_bank_row_tags_legacy_fallback_facade`。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_bank_row_tags_request_boundary_facade_wires_validation_and_affected_months_without_legacy_fallback tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_bank_row_tags_request_boundary_fails_fast_without_write_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_bank_row_tags_legacy_fallback_facade_is_removed -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
rg -n "TurnoverLedgerBankRowTagsLegacyFallback|_turnover_ledger_bank_row_tags_legacy_fallback_facade" backend/src/fin_ops_platform/app backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py
```

结果：targeted tests 通过；`rg` 无生产代码命中。

## Remaining Wave 5 Work

Turnover confirm/closure/withdraw/relation-extra/tag-selection legacy fallback、Workbench pair snapshot references、GridFS migration、platform full snapshot/local pickle/App Mongo tooling isolation 仍未完成。
