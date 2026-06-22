# /goal prompt - 260622-rwp Workbench Partial Relations

```text
/goal
Objective: Fully close the repair plan in /Users/yu/Desktop/fin-ops-platform/.planning/quick/260622-rwp-workbench-partial-relations/PLAN.md.

Use GSD discipline and the repository architecture constraints. Work autonomously until the task is implemented, documented, and verified.

Required business outcome:
- Any two-pane relation remains confirmable and persists as canonical app.workbench_pair_relations active relation.
- Ordinary manual_confirmed two-pane relations, including OA+bank, OA+invoice, and bank+invoice, stay in the Workbench open/unpaired zone as canonical case:<case_id> partial relation groups.
- Only OA+bank+invoice three-pane completed relations enter the Workbench paired zone, except explicit backend whitelist exceptions such as no-OA batch/internal transfer, salary or personal auto-closed relations, personal advance repayment settlement, OA invoice offset, batch accounting, ETC summary/batch relation, and processed/closed exception projection.
- Do not delete, downgrade, or fake canonical active relations. Downstream workbench_relation linked distribution must continue to see ordinary two-pane active relations as confirmed facts.
- Do not implement frontend local reclassification. Workbench active generation and backend grouping remain the display fact source.

Execution workflow:
1. Inspect the current plan, module docs, and relevant grouping/write/read-model/frontend code before changing files.
2. Update backend grouping policy by removing broad "confirmed two-pane => paired" behavior and preserving explicit paired exceptions.
3. Update confirm-link operation projection so ordinary two-pane confirm responses project into open_groups while three-pane and explicit exceptions remain paired_groups.
4. Verify SQL active generation/all-scope behavior so partial active relations publish exactly one canonical open owner and do not leak temp/standalone duplicates.
5. Audit frontend API mapping and selection behavior. Prefer tests over runtime changes unless the UI has an actual local paired/open assumption.
6. Add or update tests across business core, service/API projection, read model/all-scope, frontend mapping/selection, and regressions for existing exceptions.
7. Update module documentation and implementation notes. Explicitly mark any old "ordinary active two-pane relation enters paired" conclusion as historical/invalid.
8. Run focused and widened verification. At minimum cover candidate grouping, turnover grouping, SQL runtime targets, auth/idempotency projection targets, frontend Workbench API/selection tests, and docs verification.
9. Before finishing, audit git diff for unrelated user changes. Do not revert user changes. Report unrelated dirty files separately.

Completion criteria:
- All acceptance criteria in PLAN.md are satisfied.
- New and affected regression tests pass.
- Docs reflect the final rule and current architecture.
- Remaining risk is limited to real production/staging data rebuild/smoke that cannot be executed locally.
```
