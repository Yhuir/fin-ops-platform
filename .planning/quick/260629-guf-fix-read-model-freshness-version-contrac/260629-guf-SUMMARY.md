---
status: complete
---

# Quick Task 260629-guf Summary

Implemented the shared read model freshness/version fix for cross-month relation projection.

## Changed

- Bumped `workbench_relation` projection schema version to `2026-06-cross-month-relation-member-index-v1`.
- Added a regression proving old `workbench_relation_schema_version` scopes rebuild instead of skipping.
- Updated read model architecture docs so every read model scope must prove own projection schema version plus upstream dependency versions.
- Documented the required production refresh order: rebuild `workbench_relation` month shards before downstream read models.

## Verification

- `PYTHONPATH=backend/src pytest tests/test_workbench_relation_sql_projection.py ... -q`
- `PYTHONPATH=backend/src pytest tests/test_workbench_relation_read_facade.py tests/test_input_invoice_usage_api.py -q`
- `PYTHONPATH=backend/src pytest tests/test_input_invoice_usage_service.py tests/test_invoice_usage_collection_sql_runtime.py tests/test_input_invoice_usage_api.py -q`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Deployment

Pending in this run: commit, push, deploy, and production read model refresh verification.
