# P003 Rule Family Cutover

Use this as the next bounded execution prompt inside the `/goal` controller.

```text
Goal:
Move `bank-flow-rule-batches` tag-rule persistence away from the no-OA settings family into a bank-flow-owned rule storage boundary. Do not split the frontend in this slice and do not change public API response shapes except where tests prove a missing existing contract.

Evidence to inspect first:
- `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/BASELINE_AUDIT.md`
- `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/P002_IMPLEMENTATION_REPORT.md`
- `docs/modules/bank-flow-rule-batches/boundary-io.md`
- `docs/modules/no-oa-bank-batches/boundary-io.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py`
- `backend/src/fin_ops_platform/services/app_settings_service.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/settings.py` or the current app-settings repository owner
- `backend/src/fin_ops_platform/app/routes_bank_flow_rule_batches.py`
- `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
- `tests/test_bank_flow_rule_batch_application_service.py`
- `tests/test_bank_flow_rule_batch_routes.py`
- `tests/test_no_oa_bank_batch_tag_selection_api.py`
- `tests/test_postgres_migrations.py`

Allowed implementation scope:
- New PostgreSQL migration for bank-flow rule storage only if current settings persistence is PostgreSQL-backed in this codebase.
- Existing settings/repository/service files needed to add a bank-flow-owned rule I/O boundary.
- `BankFlowRuleBatchApplicationService.update_tag_selection()` and any narrow helper/port needed to stop calling `update_no_oa_bank_batch_tag_selection(...)`.
- Route tests and service tests proving the public `GET/PUT /api/bank-flow-rule-batches/tag-rules` contract remains stable and rejects `selected_tag_codes`.
- No frontend component split.
- No rewrite of no-OA legacy tag-selection behavior.

Architecture constraints:
- Public bank-flow API continues to expose `active_tags`, `rules`, `requirements_by_tag_code`, `version`, `bank_auto_tag_rules_version`, and `permissions`.
- Public bank-flow API continues to reject `selected_tag_codes` / `selectedTagCodes`.
- Legacy `/api/no-oa-bank-batches/*` keeps its no-OA tag-selection behavior and does not read bank-flow-owned rule storage.
- Rule saving must preserve optimistic concurrency, auditability, active tag validation, duplicate/unknown/inactive tag rejection, and default `requires_oa=true` / `requires_invoice=true` for new active tags.
- Rule saving must continue to synchronize existing active `relation_mode=bank_flow_rule_batch` relation metadata through `WorkbenchRelationCommandService`, not by direct SQL.
- No broad dual-write fallback. If a one-time migration from no-OA settings is needed, it must be explicit and documented with a deletion condition.

Required edits:
1. Identify the current authoritative settings persistence boundary and add a bank-flow-owned rule family boundary.
2. Migrate/read existing bank-flow rule data from `app_settings.no_oa_bank_batch_tag_selection.requirements_by_tag_code` into the bank-flow family if needed.
3. Switch `BankFlowRuleBatchApplicationService.update_tag_selection()` and tag-rule reads to the bank-flow rule boundary.
4. Keep no-OA legacy reads/writes on the no-OA family.
5. Add tests proving:
   - bank-flow rules no longer call `update_no_oa_bank_batch_tag_selection(...)`;
   - no-OA tag selection does not call bank-flow rule storage;
   - `selected_tag_codes` remains rejected by bank-flow API;
   - version conflict, unknown tag, duplicate tag, and default active tag behavior remain intact;
   - relation metadata sync still runs after bank-flow rule save.
6. Update docs only for facts changed by this slice.

Verification to run:
- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_routes.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_postgres_migrations.py tests/test_postgres_repositories_boundaries.py -q`
- `git diff --check -- backend/src/fin_ops_platform/postgres/migrations backend/src/fin_ops_platform/services backend/src/fin_ops_platform/app tests docs .planning/quick/20260701-bank-flow-rule-batches-full-closure-goal`

Stop condition:
- Bank-flow tag-rule persistence no longer depends on no-OA settings as the runtime source of truth.
- no-OA legacy tag selection remains unchanged and tested.
- API contract and relation metadata sync tests pass.
- Generate exactly one next prompt `P004_*` based on the resulting diff and tests, but do not create a backlog.
```

