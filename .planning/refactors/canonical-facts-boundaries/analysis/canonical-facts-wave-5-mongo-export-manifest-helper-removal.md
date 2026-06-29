# Canonical Facts Wave 5 - Mongo Export Manifest Helper Removal

Date: 2026-06-29

## Scope

Removed orphaned Mongo export manifest helpers:

- `backend/src/fin_ops_platform/tools/export_manifest.py`
- `tests/test_mongo_export_manifest.py`

## Evidence

- After deleting Mongo staging import/transform tools, repository search showed these helpers were referenced only by `tests/test_mongo_export_manifest.py`.
- The helpers existed to serialize App Mongo export NDJSON/manifest artifacts, which are no longer a current canonical-facts migration entrypoint.

## Decision

Delete instead of keeping test-only old export helper code.

## Verification

Passed:

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_mongo_export_manifest_helpers_are_removed
rg -n "export_manifest|NdjsonWriter|ExportSerializationError|safe_jsonable|sha256_file|write_checksums" backend/src tests -g '*.py'
```

The final `rg` match in code/tests is only the removal guard.
