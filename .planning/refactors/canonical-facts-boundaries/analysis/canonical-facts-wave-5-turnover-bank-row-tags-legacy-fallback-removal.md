# Canonical Facts Wave 5: Turnover Bank Row Tags Legacy Fallback Removal

日期：2026-06-28

## Slice

删除 `TurnoverLedgerBankRowTagsRequestBoundaryFacade` 的 production legacy fallback provider。

## Code Change

- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
  - 移除 `legacy_fallback_provider` constructor dependency。
  - 当 `_turnover_ledger_bank_row_tags_write_facade()` 不可用时 fail fast，不再 fallback 到 legacy facade。
- `backend/src/fin_ops_platform/app/server.py`
  - 移除 `legacy_fallback_provider=self._turnover_ledger_bank_row_tags_legacy_fallback_facade` wiring。
- `tests/test_platform_runtime_boundary_guards.py`
  - 降低 canonical facts legacy source path removal baseline：`legacy_fallback_provider` 在生产代码中归零。
- `tests/test_turnover_ledger_api.py`
  - 更新 wiring characterization。
  - 新增缺 write facade 时 fail-fast 测试。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_bank_row_tags_request_boundary_facade_wires_validation_and_affected_months_without_legacy_fallback tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_bank_row_tags_request_boundary_fails_fast_without_write_facade -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## Remaining Wave 5 Work

本切片只删除 bank-row-tags request boundary 的 legacy fallback provider。Turnover 其它 `*LegacyFallbackFacade` 类、local pair snapshot port、Workbench pair service references、GridFS migration 和 platform snapshot/local pickle 旧路径仍未删除。
