---
status: resolved
trigger: "After retrying the Jia Xiaohua three-row turnover closure confirmation, the turnover ledger page becomes very slow, reconciliation workbench does not refresh, and App Health shows blocked with workbench_all_scope_parent_inconsistent / queue failed backlog."
created: "2026-06-21"
updated: "2026-06-21"
---

# Debug Session: turnover-closure-refresh-blocked

## Symptoms

- Expected behavior: Confirming closure from turnover ledger should complete promptly, show the closure on turnover rows, and make the reconciliation workbench reflect the paired active case.
- Actual behavior: After clicking confirm closure, the page waits slowly, the reconciliation workbench does not refresh, and App Health shows blocked.
- Error/status: `workbench_all_scope_parent_inconsistent: generation_metadata_actual_mis...`; read model `1 刷新中`; queue `1 failed / 1 backlog`.
- Reproduction: Select the same three Jia Xiaohua turnover bank rows, click "确认闭环", confirm.

## Current Focus

- hypothesis: The turnover closure write path still enqueues ordinary `workbench:all`, even though the closure API hard-wait targets no longer include Workbench all.
- test: UoW contract should assert known affected months enqueue only month-scoped `workbench` / `workbench_relation` refresh requests.
- expecting: The current implementation fails with `workbench` and `workbench_relation` scope keys containing `["2026-02", "all"]`.
- next_action: resolved; monitor App Health/queue drain after retrying the real flow

## Evidence

- `TurnoverLedgerConfirmRequestBoundaryFacade` already returns hard freshness targets `turnover_ledger:all` plus affected-month `workbench_relation` scopes; it does not ask the page to hard-wait `workbench:all`.
- `TurnoverLedgerPage` uses the API response `freshnessTargets` after POST; if a post-mutation barrier/reload fails, it should surface a warning rather than mark the write failed.
- `WorkbenchReadModelRefreshService` handles ordinary `workbench:all` by enqueueing all shards plus aggregate, while aggregate-only `workbench:all` waits for parent month shards to be fresh before publishing.
- `TurnoverLedgerWriteFacade.confirm_zero_difference_closure(...)` still created dirty/outbox refresh requests with `workbench` and `workbench_relation` scope keys `["2026-02", "all"]`. That ordinary `workbench:all` can race with freshly changed month shards and produce `workbench_all_scope_parent_inconsistent`, matching the App Health blocked screenshot.

## Eliminated

- The API response hard-wait target was not the direct source of `workbench:all`; it had already been narrowed.
- The Workbench refresh service parent-scope guard exists for aggregate-only all, so the broken path was the ordinary all enqueue, not the aggregate-only path itself.

## Resolution

- root_cause: Manual closure confirm dirty/outbox fan-out included ordinary `workbench:all` / `workbench_relation:all` even when affected months were known. Ordinary `workbench:all` is a global shard/aggregate path and can publish a failed all generation while the changed month shards are still refreshing, blocking App Health and leaving the workbench view stale.
- fix: In `TurnoverLedgerWriteFacade.confirm_zero_difference_closure(...)`, use only deduped affected month scopes for `workbench` and `workbench_relation`; keep ordinary `all` only as an unknown-month fallback. The existing month-shard publish path still enqueues aggregate-only `workbench:all`.
- verification: Red/green verified `tests/test_turnover_ledger_uow_contract.py::TurnoverLedgerUoWContractTests::test_target_zero_difference_closure_facade_writes_turnover_and_workbench_pair_relation`; ran `tests/test_turnover_ledger_uow_contract.py`, `tests/test_turnover_relation_service.py tests/test_turnover_workbench_integration.py`, Workbench all aggregate parent-scope defer tests, Workbench relation aggregate-only fallback tests, `bash scripts/verify.sh docs`, and `git diff --check`.
- files_changed: `.planning/debug/turnover-closure-refresh-blocked.md`, `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`, `tests/test_turnover_ledger_uow_contract.py`, `docs/modules/turnover-ledger/implementation-notes.md`, `docs/modules/turnover-ledger/tests.md`.
