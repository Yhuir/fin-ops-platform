# 银行明细自动标签规则 Excel 表格与平级优先级执行 Prompt

Workspace:

```text
/Users/yu/Desktop/fin-ops-platform
```

Primary specs:

```text
docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md
docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-excel-grid-priority-design.md
```

Reference source file:

```text
/Users/yu/Desktop/sy/财务运营平台/银行明细标签/银行流水标签ui2.numbers
```

## Orchestrator Prompt

```text
/goal Implement the production-grade 银行明细 自动标签规则 Excel-style grouped table UI and priority-level matching semantics described in docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-excel-grid-priority-design.md, while preserving the broader file-backed rule replacement, candidate confirmation, and read-model consistency design in docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md.

You are working in /Users/yu/Desktop/fin-ops-platform on main.

Read first:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/product-specs/bank-details.md
- docs/dev/api-contracts.md
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-excel-grid-priority-design.md
- backend/README.md
- web/README.md
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py
- backend/src/fin_ops_platform/services/app_settings_service.py
- backend/src/fin_ops_platform/app/server.py
- web/src/features/bankDetails/AutoTagRulesDrawer.tsx
- web/src/features/bankDetails/api.ts
- web/src/features/bankDetails/types.ts
- web/src/pages/BankDetailsPage.tsx
- web/src/app/styles.css
- tests/test_bank_transaction_category_service.py
- tests/test_bank_transaction_auto_category_service.py
- tests/test_bank_auto_tag_rules_api.py
- tests/test_app_settings_service.py
- web/src/test/AutoTagRulesDrawer.test.tsx
- web/src/test/BankDetailsApi.test.ts
- web/src/test/BankDetailsPage.test.tsx
- web/src/test/apiMock.ts

Hard requirements:
- Work on main unless a newer direct user instruction says otherwise.
- This is not a temporary UI patch. Produce an integrated production implementation.
- This prompt is complete for main. Do not assume the broader table-redesign implementation already exists. First implement the main table redesign scope from `docs/superpowers/prompts/2026-05-29-bank-auto-tag-rules-table-redesign-execution.md`, then apply the Excel/priority overrides from this prompt.
- If any instruction in `docs/superpowers/prompts/2026-05-29-bank-auto-tag-rules-table-redesign-execution.md` conflicts with this prompt, this prompt wins.
- Keep `bank_transaction_tags` as the ordinary auto-tag rule fact source.
- Preserve `内部往来款` as the system special rule: fixed first row, priority 1, read-only, outside ordinary text rules.
- Ordinary xlsx/file rules default to priority 2. Do not save them as increasing priorities 2, 3, 4, 5 by row.
- Same-priority ordinary rules all attempt matching.
- Priority matching semantics:
  - lower number runs earlier;
  - internal transfer priority 1 runs first and stops on match;
  - for ordinary rules, evaluate one priority level at a time;
  - once a priority level has any matches, stop evaluating lower-priority levels;
  - one match at that level returns `auto_matched`;
  - multiple matches at that level returns `needs_confirmation`;
  - confirmation candidates contain only matched rules from that priority level.
- Remove up/down row movement from the UI and payload assumptions. Priority is the control.
- Priority must be editable for ordinary rules. New rules default to priority 2.
- Ordinary priority 1 must be rejected by backend validation.
- Saving rules sorts them into the correct display order by priority and stable grouping. The UI should not depend on manual up/down state.
- Preserve stable xlsx/file order within the same priority and primary-label group. Do not alphabetically reorder labels unless there is no existing stable order for new rules.
- Implement xlsx-style grouped table UI:
  - same primary label with multiple sub labels renders as one vertically merged primary-label cell;
  - grouping is by `priority + primary label`; if the same primary label has children at different priorities, render separate groups rather than spanning across priority levels;
  - use real `rowSpan` or an equivalently semantic structure, not CSS-only hidden duplicate text;
  - editing the merged primary label updates all child rules in that group;
  - child rows edit their own sub label, fields, conditions, direction, priority, and operation.
- `选择查询的项` multi-select must include `全选` and `清空` inside the dropdown/popup itself, not as separate buttons below the table cell.
- `全选` means all visible semantic fields are selected in the saved payload. Do not save hidden legacy `all_text` from new UI interactions. `all_text` is read-only legacy compatibility.
- Multi-line condition values must display in full in the table. Do not replace them with `共 N 项`, preview truncation, or ellipsis.
- Different primary-label groups must have visibly distinct, professional colors. Do not use very pale colors that are hard to distinguish.
- Desktop wide-screen editing is the target. Do not add a mobile-specific card UI; just ensure narrow screens do not break catastrophically.
- Do not convert the bank details main table or this drawer to DataGrid.
- Do not introduce a new third-party table/drag/drop library.
- Do not restore the old all-tags manual classification dropdown.
- Preserve unrelated user changes. Never revert files you did not intentionally edit.

Recommended serial/parallel execution:

1. Serial baseline:
   - Confirm branch and cleanliness: `git branch --show-current && git status --short`.
   - Read both specs and current tests.
   - Run focused tests if fast:
     `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_bank_transaction_category_service tests.test_bank_transaction_auto_category_service tests.test_bank_auto_tag_rules_api tests.test_app_settings_service -v`
     and
     `cd web && npm test -- --run AutoTagRulesDrawer.test.tsx BankDetailsApi.test.ts BankDetailsPage.test.tsx`.

2. Serial main table-redesign foundation:
   - Execute the main scope from `docs/superpowers/prompts/2026-05-29-bank-auto-tag-rules-table-redesign-execution.md` if it is not already present on main.
   - This includes:
     - parser/normalizer for `银行流水标签ui2` fixture or exported source;
     - file-backed replacement of ordinary app rules;
     - code reuse by primary/sub label;
     - archiving file-external ordinary rules;
     - candidate evaluator 0/1/many states;
     - bank detail row candidate confirmation UI/API;
     - confirmation/revoke APIs;
     - durable confirmation fact source and audit;
     - read model columns/projection for candidates, confirmation, effective label, status, and rule version;
     - dirty scope/lifecycle refresh and downstream consistency.
   - Apply this prompt's overrides while implementing main scope:
     - ordinary file rules default priority 2;
     - no up/down UI;
     - full condition display;
     - Excel grouped table UI;
     - priority-bucket evaluator semantics.
   - Do not proceed to final verification until both the main table-redesign scope and this Excel/priority override scope are implemented.

3. Serial backend priority semantics:
   - Add/adjust tests first in `tests/test_bank_transaction_auto_category_service.py`:
     - same priority multiple matches -> `needs_confirmation`;
     - higher priority match stops lower priority;
     - single match at current priority -> `auto_matched`;
     - priority 2 has no match and priority 3 has one/many -> priority 3 result applies;
     - internal transfer still wins before ordinary rules.
   - Update `backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py` to evaluate ordinary rules by priority buckets.
   - Preserve current evidence/candidate payload shape and rule version behavior.

4. Serial backend rule normalization and API validation:
   - Add/adjust tests in `tests/test_bank_transaction_category_service.py`, `tests/test_bank_auto_tag_rules_api.py`, and `tests/test_app_settings_service.py`.
   - Ensure file replacement/default ordinary rules persist priority 2.
   - Ensure old missing-priority ordinary rules display/save as priority 2.
   - Reject ordinary rule priority 1, 0, negative, decimal, and non-numeric strings with structured validation. Missing priority defaults to 2 only for new-rule/history compatibility paths.
   - Ensure GET payload priority labels are consistent: system 1, ordinary default 2.
   - Ensure PUT persists explicit priority values and sorts deterministically.
   - Preserve or introduce a stable ordering field/metadata so same-priority rules reopen in xlsx order.
   - Ensure archived ordinary rules remain accessible, do not auto-match, and normalize missing priority to 2 when restored.

5. Serial frontend contract update:
   - Update `web/src/features/bankDetails/types.ts`, `web/src/features/bankDetails/api.ts`, and `web/src/test/apiMock.ts` first.
   - Ensure priority mapping supports default 2 and explicit values.
   - Update mocks so ordinary rules are priority 2.
   - Define visible match fields and confirm `全选` expands to those visible field values, not `all_text`.
   - Only after this contract is stable, proceed to drawer implementation.

6. Serial frontend drawer implementation:
   - Modify `web/src/features/bankDetails/AutoTagRulesDrawer.tsx` and `web/src/app/styles.css`:
     - build grouped row model;
     - render rowSpan primary-label cells;
     - split the same primary label into separate rowSpan groups when priorities differ;
     - remove up/down buttons;
     - add priority input;
     - move select all/clear into select menu;
     - full-display condition lists;
     - group color styling.

7. Serial frontend tests:
   - Update `web/src/test/AutoTagRulesDrawer.test.tsx` to assert:
     - grouped primary-label cell appears once for multiple child rules;
     - same primary label with different priorities renders as two groups, not one cross-priority rowSpan;
     - editing primary label changes all child rules in saved payload;
     - select all/clear are inside the dropdown;
     - no up/down controls exist;
     - new rule priority defaults to 2;
     - ordinary priority 1 cannot be saved silently; frontend blocks or surfaces structured backend validation;
     - system row priority 1 is read-only and the system row is not submitted as an ordinary rule;
     - full condition text is rendered, not `共 N 项` or ellipsis;
     - group colors differ for adjacent primary labels.
   - Update `web/src/test/BankDetailsApi.test.ts` only if API mapping changes.
   - Update `web/src/test/BankDetailsPage.test.tsx` only for integration fallout.

8. Serial docs:
   - Update `docs/product-specs/bank-details.md`:
     - Excel-style grouped table;
     - rowSpan primary labels;
     - priority 1 internal, priority 2 ordinary default;
     - same-priority multi-match semantics.
   - Update `docs/dev/api-contracts.md`:
     - ordinary priority validation;
     - priority-level evaluator semantics;
     - UI payload expectations if relevant.

9. Final verification:
   - `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_bank_transaction_category_service tests.test_bank_transaction_auto_category_service tests.test_bank_auto_tag_rules_api tests.test_app_settings_service -v`
   - `cd web && npm test -- --run AutoTagRulesDrawer.test.tsx BankDetailsApi.test.ts BankDetailsPage.test.tsx`
   - `cd web && npm run build`
   - `git diff --check`
   - Required unless blocked: run the app or a Storybook/test harness and visually inspect the drawer at a desktop viewport. Capture or describe evidence for rowSpan grouping, full词条 display, group colors, in-dropdown `全选/清空`, no text overlap, and no up/down controls. If this cannot be run, state the exact blocker.

Expected final report:
- Changed files.
- Exact priority semantics implemented.
- How xlsx-style grouping is rendered.
- How primary-label group edits synchronize children.
- How select all/clear moved inside the multi-select.
- How full condition text display is guaranteed.
- Exact tests run and results.
- Any residual risk.
```

## Main Foundation Worker Prompt

```text
/goal Implement the full production-grade bank auto-tag table redesign foundation from docs/superpowers/prompts/2026-05-29-bank-auto-tag-rules-table-redesign-execution.md, applying the Excel-grid and priority overrides from docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-excel-grid-priority-design.md.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read:
- AGENTS.md
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-excel-grid-priority-design.md
- docs/superpowers/prompts/2026-05-29-bank-auto-tag-rules-table-redesign-execution.md
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py
- backend/src/fin_ops_platform/services/app_settings_service.py
- backend/src/fin_ops_platform/services/bank_details_service.py
- backend/src/fin_ops_platform/services/bank_detail_sql_projection.py
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
- backend/src/fin_ops_platform/services/postgres_repositories/workbench.py
- backend/src/fin_ops_platform/app/server.py
- web/src/features/bankDetails/AutoTagRulesDrawer.tsx
- web/src/features/bankDetails/api.ts
- web/src/features/bankDetails/types.ts
- web/src/pages/BankDetailsPage.tsx
- web/src/app/styles.css

Owned scope:
- File parser/replacement for `银行流水标签ui2` normalized fixture/export.
- Rule code reuse and archival of file-external ordinary rules.
- Candidate evaluator 0/1/many states.
- Confirmation/revoke APIs with permission checks and audit.
- Durable confirmation fact source and Postgres migration.
- Bank detail read-model columns/projection for candidates, confirmation, effective label, status, and rule version.
- Dirty scope/lifecycle refresh for rule changes and confirmations.
- Baseline drawer table UI and bank detail candidate confirmation UI.

Overrides that must be applied while implementing the main prompt:
- Ordinary file rules default priority 2, not row-number priority.
- Evaluator uses priority buckets, not first-match-by-row.
- Drawer final UI is Excel grouped table with rowSpan primary labels.
- No up/down buttons.
- Full condition text display, no `共 N 项`.
- `全选/清空` inside the multi-select dropdown.

Run at minimum:
- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_bank_transaction_category_service tests.test_bank_transaction_auto_category_service tests.test_bank_auto_tag_rules_api tests.test_app_settings_service tests.test_bank_details_service tests.test_bank_details_sql_runtime tests.test_postgres_migrations -v`
- `cd web && npm test -- --run AutoTagRulesDrawer.test.tsx BankDetailsApi.test.ts BankDetailsPage.test.tsx`
- `cd web && npm run build`
```

## Backend Worker Prompt

```text
/goal Implement backend priority-level auto-tag matching and rule priority validation for the Excel-style bank auto-tag rules redesign.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read:
- AGENTS.md
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-excel-grid-priority-design.md
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md
- backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/app_settings_service.py
- backend/src/fin_ops_platform/app/server.py
- tests/test_bank_transaction_auto_category_service.py
- tests/test_bank_transaction_category_service.py
- tests/test_bank_auto_tag_rules_api.py
- tests/test_app_settings_service.py

Owned files:
- backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/app_settings_service.py if needed
- backend/src/fin_ops_platform/app/server.py only if API error mapping needs adjustment
- tests/test_bank_transaction_auto_category_service.py
- tests/test_bank_transaction_category_service.py
- tests/test_bank_auto_tag_rules_api.py
- tests/test_app_settings_service.py

Tasks:
1. Write failing tests for priority buckets:
   - ordinary rules at priority 2 all match -> needs_confirmation with only priority 2 candidates;
   - priority 2 match exists and priority 3 also matches -> only priority 2 is returned;
   - priority 2 has one match -> auto_matched;
   - priority 2 has no match and priority 3 has one/many -> priority 3 result applies;
   - internal transfer still bypasses ordinary rules.
2. Implement evaluator changes by grouping ordinary active rules by normalized priority.
3. Write failing tests for rule normalization:
   - file replacement creates ordinary priority 2;
   - GET system priority label is 1 and ordinary default is 2;
   - missing ordinary priority defaults to 2;
   - ordinary priority 1, 0, negative, decimal, and non-numeric strings are rejected by PUT with structured field errors;
   - explicit ordinary priority > 1 persists.
   - archived ordinary rules remain accessible, do not auto-match, and normalize missing priority to 2 when restored.
4. Implement normalization/validation.
5. Run:
   `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_bank_transaction_category_service tests.test_bank_transaction_auto_category_service tests.test_bank_auto_tag_rules_api tests.test_app_settings_service -v`
6. Do not touch frontend files.

Report:
- Files changed.
- Tests added.
- Tests run and results.
- Any backend contract changes frontend must consume.
```

## Frontend Worker Prompt

```text
/goal Implement the Excel-style grouped `自动标签规则` drawer UI with merged primary-label cells, in-menu select-all/clear, editable priority, and full condition display.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read:
- AGENTS.md
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-excel-grid-priority-design.md
- web/src/features/bankDetails/AutoTagRulesDrawer.tsx
- web/src/features/bankDetails/api.ts
- web/src/features/bankDetails/types.ts
- web/src/app/styles.css
- web/src/test/AutoTagRulesDrawer.test.tsx
- web/src/test/BankDetailsApi.test.ts
- web/src/test/BankDetailsPage.test.tsx
- web/src/test/apiMock.ts

Owned files:
- web/src/features/bankDetails/AutoTagRulesDrawer.tsx
- web/src/features/bankDetails/api.ts
- web/src/features/bankDetails/types.ts
- web/src/app/styles.css
- web/src/test/AutoTagRulesDrawer.test.tsx
- web/src/test/BankDetailsApi.test.ts if mapping changes
- web/src/test/BankDetailsPage.test.tsx if integration tests need selector updates
- web/src/test/apiMock.ts

Tasks:
1. Write failing drawer tests:
   - same primary label with multiple sub labels renders one merged primary-label control;
   - same primary label with different priorities renders as separate groups;
   - editing merged primary label updates all child rules in save payload;
   - `全选` and `清空` exist inside the match-field select popup and update selection;
   - `全选` saves all visible semantic fields and does not save hidden legacy `all_text`;
   - up/down buttons are gone;
   - priority input exists and new rules default to 2;
   - system row priority 1 is read-only, system rule is not archivable/editable, and ordinary priority 1 cannot be silently saved;
   - full condition values render in cells, with no `共 N 项` summary and no ellipsis-only preview;
   - adjacent primary-label groups have different visible group styling.
2. Implement grouped row model:
   - stable group key from `priority + outputPrimaryLabel`;
   - preserve draft row identity;
   - render primary-label `TableCell` with `rowSpan`;
   - synchronize group-level primary-label edits to all children.
3. Replace movement controls with priority input:
   - ordinary rows editable;
   - system row read-only priority 1;
   - save sorts by priority and stable grouping;
   - preserve xlsx/source order inside the same priority group;
   - no up/down UI remains.
4. Move select-all/clear into the MUI Select menu:
   - no separate buttons below the table cell;
   - keep keyboard/click behavior stable;
   - do not include hidden `all_text` as a visible option unless explicitly selected from legacy data;
   - new `全选` actions expand to all visible semantic field values in the saved payload.
5. Render condition values fully:
   - newline list in table cell;
   - no truncation/ellipsis;
   - row height grows as needed.
6. Add group colors:
   - visible but professional palette;
   - readable text contrast;
   - deterministic by group order or stable hash.
7. Run:
   `cd web && npm test -- --run AutoTagRulesDrawer.test.tsx BankDetailsApi.test.ts BankDetailsPage.test.tsx`
   `cd web && npm run build`
8. Required unless blocked: inspect the drawer at a desktop viewport using the local app/browser or a test harness. Verify rowSpan grouping, full condition text, group colors, in-dropdown `全选/清空`, no up/down controls, and no text overlap. State exact blocker if visual inspection cannot be run.
9. Do not touch backend files unless the backend contract changed and the orchestrator approves.

Report:
- Files changed.
- UI behavior implemented.
- Tests added/updated.
- Tests run and results.
- Any remaining visual risk.
```

## Docs And Review Worker Prompt

```text
/goal Update product/API documentation and review the implementation for consistency with the Excel-style bank auto-tag rules design.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read:
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-excel-grid-priority-design.md
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md
- docs/product-specs/bank-details.md
- docs/dev/api-contracts.md
- changed backend/frontend files from the implementation

Owned files:
- docs/product-specs/bank-details.md
- docs/dev/api-contracts.md
- tests only if documentation examples are tested

Tasks:
1. Update product spec:
   - Excel/xlsx grouped table;
   - merged primary-label behavior;
   - full condition display;
   - group colors;
   - priority 1 internal, priority 2 ordinary default;
   - priority-level matching semantics.
2. Update API contracts:
   - `priority`/`priority_label` semantics;
   - ordinary priority 1 validation;
   - priority bucket evaluator behavior;
   - frontend payload notes if needed.
3. Review implementation:
   - no up/down controls remain;
   - no `共 N 项` summaries replace condition text;
   - same-priority matching does not short-circuit by row;
   - lower priority candidates do not leak into higher priority confirmation choices;
   - ordinary file rules default to priority 2.
   - `全选` expands to visible semantic fields and does not save legacy `all_text`.
   - archived rules remain accessible and inactive.
4. Run `git diff --check`.

Report:
- Docs changed.
- Review findings by severity.
- Tests/checks run.
```
