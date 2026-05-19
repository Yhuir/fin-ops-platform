# 批量账务金额不一致差额说明子代理 Prompt

Use these prompts with fresh worker agents. Workers are not alone in the codebase: there may be concurrent changes by other workers. They must not revert changes made by others and must keep edits inside their ownership scope.

## Worker 1: Backend Contract and Persistence

```text
/goal Implement backend support for batch accounting amount mismatches with mandatory difference notes in /Users/yu/Desktop/fin-ops-platform. Build a production-grade change backed by existing workbench pair relations and tests.

You are Worker 1. You own only backend files:
- backend/src/fin_ops_platform/services/batch_accounting_service.py
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/services/workbench_candidate_grouping.py if needed to expose relation note/amount_check in grouped workbench payloads
- tests/test_batch_accounting_api.py
- tests/test_workbench_v2_api.py

Do not edit frontend files. Do not revert unrelated working tree changes.

Read first:
- docs/superpowers/specs/2026-05-19-batch-accounting-mismatch-note-design.md
- docs/superpowers/specs/2026-05-18-batch-accounting-design.md
- docs/dev/reconciliation-workbench-v2-data-contracts.md
- backend/src/fin_ops_platform/services/workbench_pair_relation_service.py
- backend/src/fin_ops_platform/app/server.py around /api/batch-accounting and /api/workbench/actions/confirm-link

Requirements:
1. Extend POST /api/batch-accounting/submit to accept note/comment.
2. Recompute bank amount, OA amount, and amount delta server-side.
3. Preserve existing matched-amount behavior: note is not required when amounts match.
4. For amount mismatch:
   - reject missing, empty, or whitespace-only note with HTTP 400;
   - use error code batch_accounting_note_required;
   - include amount_check with status mismatch, direction expense, bank_amount, oa_amount, amount_delta, requires_note true.
5. For mismatch with note:
   - create the existing batch_accounting pair relation;
   - set top-level pair_relation.note to the trimmed note;
   - set pair_relation.amount_check.status = "mismatch";
   - include bank_amount, oa_amount, amount_delta, requires_note true;
   - keep special_metadata.source = "batch_accounting" and existing bank/OA/invoice/year metadata.
6. Pair relation history must preserve submit note and amount_check.
7. Submitted batch payload must expose relation.note and relation.amount_check through relations_by_bank_row_id.
8. Workbench paired payload must follow the exact shape in the spec:
   - group-level `relation_note`;
   - group-level `amount_check`;
   - bank row-level `relation_note`;
   - bank row-level `relation_amount_check`;
   - tag `金额不一致` remains present for mismatch relations.
9. Withdraw must continue to restore prior relations and must not overwrite the original submit note with withdraw reason.
10. If persistence scheduling fails, avoid leaving an in-memory submitted relation that cannot be saved. Align with the existing confirm-link rollback pattern where practical.
11. Mismatch-with-note is人工差额闭环: do not create workbench_exception_cases, ledger/follow-up facts, tasks, or approval flows.

Testing:
- Update the existing mismatch rejection test to require note instead of unconditional rejection.
- Add tests for mismatch without note, whitespace-only note, mismatch with note success, relation/history amount_check persistence, submitted payload exposure, exact workbench paired projection fields, no exception/ledger side effects, and withdraw behavior.
- Run:
  PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api -v
  PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v

Final response must include:
- Status: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED.
- Files changed.
- Tests run and results.
- Any contract assumptions or risks.
```

## Worker 2: Batch Accounting Frontend

```text
/goal Implement frontend support for batch accounting amount mismatches with mandatory difference notes in /Users/yu/Desktop/fin-ops-platform. Keep the existing page structure and add tests.

You are Worker 2. You own only frontend batch-accounting files:
- web/src/pages/BatchAccountingPage.tsx
- web/src/features/batchAccounting/types.ts
- web/src/features/batchAccounting/api.ts
- web/src/test/BatchAccountingPage.test.tsx

Do not edit backend files. Do not edit generic workbench components. Do not revert unrelated working tree changes.

Read first:
- docs/superpowers/specs/2026-05-19-batch-accounting-mismatch-note-design.md
- web/src/pages/BatchAccountingPage.tsx
- web/src/features/batchAccounting/api.ts
- web/src/features/batchAccounting/types.ts
- web/src/test/BatchAccountingPage.test.tsx

Requirements:
1. Keep the current two-column batch accounting layout.
2. Continue showing bank amount, selected OA count, selected OA total, and difference.
3. When a bank row and at least one OA row are selected and the difference is non-zero, show a required input:
   - label: 差额说明
   - helper text: 金额不一致时必须填写，提交后视为人工差额闭环。
   - Do not require a fixed multiline/min-row design.
4. Submit rules:
   - matched amount can submit without note;
   - mismatched amount can submit only when 差额说明.trim() is non-empty.
5. Clear the difference note when switching bank row or switching bucket.
6. Do not clear the difference note when toggling OA rows.
7. Send note in POST /api/batch-accounting/submit.
8. Expand batch accounting API/types so submitted relation note and amount_check are preserved from relations_by_bank_row_id.
9. Submitted bucket should be able to display the selected relation's mismatch status/note after refresh.
10. Do not append the difference note to bank original remarks or OA reason.

Testing:
- Update current tests that expect amount mismatch to keep submit disabled permanently.
- Add tests for:
  - mismatch shows 差额说明 input;
  - blank/whitespace note cannot submit;
  - typed note enables submit;
  - POST body includes note;
  - matched amount still does not require note;
  - submitted payload can render persisted mismatch note/status.
- Run:
  cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx

Final response must include:
- Status: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED.
- Files changed.
- Tests run and results.
- Any API assumptions or risks.
```

## Worker 3: Workbench Paired-Area Tooltip

```text
/goal Render batch accounting amount mismatch notes in the workbench paired area in /Users/yu/Desktop/fin-ops-platform. Show a warning icon beside the bank amount with an accessible tooltip, without adding a new row.

You are Worker 3. You own only workbench frontend mapping/rendering files:
- web/src/features/workbench/types.ts
- web/src/features/workbench/api.ts
- web/src/components/workbench/WorkbenchRecordCard.tsx
- Relevant workbench tests, such as web/src/test/WorkbenchApi.test.ts, web/src/test/WorkbenchSelection.test.tsx, web/src/test/WorkbenchZone.test.tsx, or web/src/test/WorkbenchColumns.test.tsx

Do not edit backend files. Do not edit batch accounting page files unless needed for shared types and coordinated with Worker 2. Do not revert unrelated working tree changes.

Read first:
- docs/superpowers/specs/2026-05-19-batch-accounting-mismatch-note-design.md
- web/src/features/workbench/api.ts
- web/src/features/workbench/types.ts
- web/src/components/workbench/WorkbenchRecordCard.tsx
- web/src/features/workbench/tableConfig.ts

Requirements:
1. Map the exact workbench payload shape from the spec:
   - group `relation_note` -> `WorkbenchCandidateGroup.relationNote`;
   - group `amount_check` -> `WorkbenchCandidateGroup.amountCheck`;
   - bank row `relation_note` -> `WorkbenchRecord.relationNote`;
   - bank row `relation_amount_check` -> `WorkbenchRecord.relationAmountCheck`.
2. In the paired area, render a warning icon beside the bank row amount when:
   - row type is bank;
   - the row relationAmountCheck.status is mismatch;
   - relation note exists or requires_note is true.
3. Tooltip content must include:
   - 金额不一致
   - 银行流水金额
   - OA合计
   - 差额
   - 差额说明
4. Tooltip must support hover, keyboard focus, and click/touch.
5. The icon must have an accessible label, for example 查看金额不一致差额说明.
6. Do not add a new table row.
7. Do not append the difference note to the bank original note/remarks field.
8. Keep existing column layout and saved column semantics stable.

Testing:
- Add or update workbench API mapping tests for relation note/amount_check.
- Add rendering tests proving the paired bank amount shows the warning icon and tooltip text.
- Verify that ordinary matched bank rows do not show the icon.
- Run:
  cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/WorkbenchSelection.test.tsx src/test/WorkbenchZone.test.tsx

Final response must include:
- Status: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED.
- Files changed.
- Tests run and results.
- Any remaining accessibility or payload-shape risks.
```

## Worker 4: Integration Verification

```text
/goal Verify and harden the completed batch accounting mismatch-note implementation in /Users/yu/Desktop/fin-ops-platform after Workers 1-3 finish. Fix only integration defects necessary to meet the approved spec.

You are Worker 4. Start only after Workers 1-3 report DONE or DONE_WITH_CONCERNS. You may edit files touched by those workers only to fix integration defects. Do not add new product scope.

Read first:
- docs/superpowers/specs/2026-05-19-batch-accounting-mismatch-note-design.md
- Worker 1 final report
- Worker 2 final report
- Worker 3 final report

Verification commands:
1. Backend:
   PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api tests.test_workbench_v2_api -v
2. Frontend:
   cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx src/test/WorkbenchApi.test.ts src/test/WorkbenchSelection.test.tsx src/test/WorkbenchZone.test.tsx
3. Build:
   cd web && npm run build

If a failure is due to an implementation gap against the spec, fix the smallest necessary code. If a failure is unrelated, report it clearly and do not broaden scope.

Final response must include:
- Status: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED.
- Files changed.
- Commands run and results.
- Any remaining risks.
```
