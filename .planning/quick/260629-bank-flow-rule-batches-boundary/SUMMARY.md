# GSD Quick Summary: bank-flow-rule-batches boundary slice

Date: 2026-06-29

## Completed

- Added a planned `bank-flow-rule-batches` module document set.
- Defined boundary/I-O, state machine, tests matrix, E2E spec, E2E coverage mapping, and implementation notes.
- Registered the module in long-lived boundary docs and API contracts.
- Marked legacy no-OA behavior as superseded by the new module for future implementation.

## Decisions Captured

- New module name: `流水规则批量处理`.
- Left-side tags are read-only facts from bank details.
- Right-side rule columns are only `OA` and `发票`.
- Checked means required before paired; empty means not required.
- New or unconfigured bank tags default to requiring both OA and invoice.
- Old `selected_tag_codes` should not be migrated as source facts.
- Legacy submitted no-OA batches need controlled dry-run/apply rebaseline.

## Verification

- `git diff --check` passed.
- `bash scripts/verify.sh docs` passed.
- `rg -n "bank-flow-rule-batches|bank_flow_rule_batch|流水规则批量处理" docs/modules docs/architecture docs/dev .planning/quick/260629-bank-flow-rule-batches-boundary` confirmed the new module references are registered.
