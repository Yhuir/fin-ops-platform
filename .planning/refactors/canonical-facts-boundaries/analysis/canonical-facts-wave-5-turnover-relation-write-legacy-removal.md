# Canonical Facts Wave 5: Turnover Relation Write Legacy Removal

日期：2026-06-28

## Slice

删除 Turnover confirm、closure、withdraw 的 production legacy fallback facade/factory。

## Code Change

- `backend/src/fin_ops_platform/app/server.py`
  - `_turnover_ledger_confirm_write_facade()` 不再 fallback 到 `_turnover_ledger_confirm_legacy_fallback_facade()`。
  - `_turnover_ledger_closure_write_facade()` 不再 fallback 到 `_turnover_ledger_closure_legacy_fallback_facade()`。
  - `_turnover_ledger_withdraw_write_facade()` 不再 fallback 到 `_turnover_ledger_withdraw_legacy_fallback_facade()`。
  - 删除上述 legacy fallback factory。
  - 移除 confirm/closure/withdraw legacy fallback imports。
  - Turnover primary write facades 统一通过 `_turnover_ledger_write_queue_repository(state_store)` 获取刷新队列端口：PostgreSQL 模式必须使用 durable transaction-capable queue；本地模式可以使用 `_LocalTurnoverLedgerRefreshQueue` 支撑 primary facade，不恢复旧 fallback。
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
  - 删除 `TurnoverLedgerConfirmLegacyFallbackFacade`。
  - 删除 `TurnoverLedgerClosureLegacyFallbackFacade`。
  - 删除 `TurnoverLedgerConfirmLegacyFallbackAdapterSet`。
  - 删除 `TurnoverLedgerWithdrawLegacyFallbackFacade`。
  - confirm、closure、cash-closure-withdraw、withdraw request boundary 缺少 write facade 时 fail fast。
- `tests/test_platform_runtime_boundary_guards.py`
  - 禁止 production app/API/worker 文件重新出现 confirm/closure/withdraw legacy fallback 类名。
- `tests/test_turnover_ledger_api.py`
  - 更新 wiring characterization。
  - 新增缺 write facade fail-fast 测试。
  - 断言 `Application` 不再暴露 confirm/closure/withdraw legacy fallback factory。
  - 移除旧 fallback 成功路径期待，改为验证 primary write facade、UOW rollback、refresh scope 和缺 facade fail-fast。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py backend/src/fin_ops_platform/app/server.py
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_relation_legacy_fallback_facade_is_removed tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_and_closure_request_boundaries_fail_fast_without_write_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_withdraw_request_boundary_fails_fast_without_write_facade -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
rg -n "TurnoverLedger(Confirm|Closure|Withdraw)LegacyFallback|_turnover_ledger_(confirm|closure|withdraw)_legacy_fallback_facade" backend/src/fin_ops_platform/app backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py
```

结果：targeted tests 通过；完整 Turnover API 套件 146 个测试通过；`rg` 无生产代码命中。

## Remaining Wave 5 Work

Turnover legacy fallback classes are removed from production code. Remaining canonical facts old-path work is outside these Turnover fallback facades: Workbench pair snapshot references, GridFS migration isolation, platform full snapshot/local pickle/App Mongo tooling isolation and final production evidence.
