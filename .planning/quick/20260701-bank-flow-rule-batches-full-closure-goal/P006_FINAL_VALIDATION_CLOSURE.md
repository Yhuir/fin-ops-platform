# P006 Final Validation Closure

## Goal

Close final validation drift found after P005:

- `bank-flow-rule-batches` API already rejected legacy `selected_tag_codes`, but the service boundary still accepted it when called directly.
- `rules[]` duplicate `tag_code` could be normalized by overwrite instead of failing fast.
- Long-term test docs still described unknown/inactive/duplicate tag validation as an open gap.

## Scope

- Keep changes inside the bank-flow tag-rule boundary.
- Do not change no-OA legacy tag-selection semantics.
- Do not introduce a new rules table in this slice; current approved persistence target is `app_settings.bank_flow_rule_batch_tag_rules`.

## Expected Edits

- Add service-layer validation in `AppSettingsService.update_bank_flow_rule_batch_tag_rules(...)`.
- Add/adjust tests for:
  - service rejection of legacy `selected_tag_codes`
  - service rejection of duplicate `rules[].tag_code`
  - API mapping of duplicate rule validation to `400`
- Update module/API docs to match current behavior.

## Stop Condition

- Targeted backend tests pass.
- Frontend focused tests/build remain green.
- `git diff --check` passes for touched module scope.
