---
status: resolved
trigger: "External turnover ledger confirm closure for three Jia Xiaohua bank transactions fails with 'Bank transaction already belongs to an active turnover closure' although the reconciliation workbench shows those three transactions are not in the same active case."
created: "2026-06-21"
updated: "2026-06-21"
---

# Debug Session: turnover-closure-mismatch

## Symptoms

- Expected behavior: Confirming a matched closure from the external turnover ledger should persist the closure, show a closure period on the external turnover bank rows, and make the reconciliation workbench show the same pairing/case.
- Actual behavior: The external turnover ledger detects an existing pairing/active closure and blocks confirmation.
- Error message: "Bank transaction already belongs to an active turnover closure."
- Reproduction: Select the three Jia Xiaohua bank transactions in the external turnover ledger, click "确认闭环", then confirm.
- User question: Why does the external turnover ledger detect a pairing when the reconciliation workbench does not show those transactions in one active case?

## Current Focus

- hypothesis: External turnover closure conflict detection and reconciliation workbench active-case display use different relationship/read-model facts.
- test: Added a regression for an orphaned local turnover closure with no Workbench active case, then changed exact-row closure overlap handling.
- expecting: Reconfirming the same bank row set reuses the existing turnover relation and writes the missing Workbench `turnover_manual_closure` active case.
- next_action: run broader turnover relation/workbench verification

## Evidence

- timestamp: 2026-06-21
  observation: `TurnoverRelationService.confirm_zero_difference_closure()` calls `_ensure_no_manual_closure_overlap()` before the Workbench command service writes the active relation.
  result: A local confirmed closure can block retry before Workbench has a chance to repair or create `turnover:{relation_id}`.
- timestamp: 2026-06-21
  observation: `test_manual_closure_repairs_orphaned_turnover_closure_without_workbench_case` failed with 400 and `Bank transaction already belongs to an active turnover closure.` before the implementation change.
  result: Reproduced the user-visible failure mode.

## Eliminated

- hypothesis: Existing OA-bank active relations alone block turnover closure.
  reason: Existing tests and `TurnoverLedgerWorkbenchPairPort` allow OA+bank relations to merge into the new `turnover_manual_closure` case.
- hypothesis: The selected three rows fail zero-difference business validation.
  reason: Existing and new tests use the same 200k + 100k income and 300k expense shape and pass zero-difference validation once overlap handling permits retry.

## Resolution

- root_cause: 外部往来本地关系里已经有同一批流水的 manual zero-difference closure，所以本地台账能显示已闭合计；但 Workbench canonical active relation 缺少对应 `turnover:{relation_id}` case，关联台不显示配对。再次确认时，本地 closure overlap 校验先于 Workbench command service 执行，直接报错，无法补写缺失 case。
- fix: `_ensure_no_manual_closure_overlap()` 对完全相同的 `bank_row_ids` 不再阻断，允许复用同一 turnover relation 继续写 Workbench active case；部分重叠仍拒绝。
- verification: Red tests failed before implementation; targeted green tests passed after implementation. `tests.test_turnover_relation_service`, `tests.test_turnover_workbench_integration`, and `tests.test_turnover_ledger_uow_contract` passed together. `tests.test_turnover_ledger_read_model_refresh` passed, but the extra `tests.test_workbench_turnover_grouping` verification has an existing failure in `test_two_pane_turnover_manual_closure_rows_remain_open_even_when_linked`.
- files_changed: `backend/src/fin_ops_platform/services/turnover_relation_service.py`, `tests/test_turnover_relation_service.py`, `tests/test_turnover_workbench_integration.py`, `docs/modules/turnover-ledger/tests.md`, `docs/modules/turnover-ledger/implementation-notes.md`
