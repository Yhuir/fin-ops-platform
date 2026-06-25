# Read Model Main Closure Wave 5 - OA-driven freshness targets

Date: 2026-06-26

## Boundary

`main-read-model-closure:wave-5-oa-driven-queued-job-legacy-and-production-evidence-prep`

This wave closed the OA manual import/create/refresh/remove write-to-read freshness boundary. Queued import job completion and production evidence remain separate follow-up boundaries.

## Codebase analysis before implementation

- `OAManualImportService.import_row_ids(...)`, `refresh_attachments(...)`, and `remove_manual_import(...)` already returned business results and `Application._invalidate_after_oa_manual_import_mutation(...)` already triggered derived lifecycle event `oa_attachment_invoice_cache_updated`.
- The same routes did not expose `affected_scope_keys`, `read_model_scope_keys`, `freshness_targets`, or `operation_barrier_targets`, so the frontend could complete UI state transitions without waiting for affected read models to converge.
- The derived lifecycle event fans out to `workbench`, `workbench_relation`, `invoice_lifecycle`, `tax_offset`, `search`, and `cost_statistics`; these are the minimum target read models for OA attachment/manual import mutations.
- `OaManualSearchImportTable` called refresh/import APIs and updated visible rows directly. It did not wait for the operation barrier.
- `removeManualOaImport(...)` exists as an API client path even though the current settings table has no dominant removal UI path; it must keep the same target envelope contract to avoid a compat-only stale path.

## Implementation

- Added an OA manual import write target envelope builder in `Application`:
  - normalizes affected workbench-style scope keys;
  - validates registered read model scope policy contracts;
  - expands `cost_statistics` into its scoped parent/month keys;
  - returns `affected_scope_keys`, `read_model_scope_keys`, `freshness_targets`, and `operation_barrier_targets`.
- Updated OA manual import refresh/create/delete responses to return the target envelope after derived lifecycle invalidation.
- Updated frontend Workbench API mapping for OA manual import refresh/create/remove to preserve scope keys and operation barrier targets.
- Updated `OaManualSearchImportTable` to wait for returned operation barrier targets before showing final refreshed/imported state.
- Added backend and frontend tests proving the target envelope and barrier wait behavior.
- Updated module boundary docs for read models, OA integration, settings, and reconciliation workbench.

## Legacy deletion / quarantine judgment

- No deletion was safe in this wave: the app-owned OA manual import routes still live in `server.py`, and route-owner extraction is a separate route modularization boundary.
- The stale behavior was not a dead file; it was an active response-shape gap. The gap is now closed by target envelope propagation and frontend wait behavior.
- `removeManualOaImport(...)` remains reachable as a compatibility API client path, but no longer bypasses freshness targets.

## Verification performed

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/server.py
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_manual_import_api -v
npm test -- --run src/test/WorkbenchApi.test.ts src/test/SettingsOaManualSearchImportTable.test.tsx
```

## Remaining work

- Queued import job completion must still prove that job result payloads consumed by UI expose operation barrier targets only after affected scopes are knowable.
- A legacy deletion/quarantine sweep still needs to cover live-scan fallback, compat repository methods, and remaining route surfaces from the inventory.
- Production evidence still has not been collected for the current main implementation. The next production wave must use business operations for validation actions and restore samples through business inverse first, or the preapproved bounded DB restore protocol when no business inverse exists.

## Closure status

- OA manual import/write frontend freshness: local PSCIP-L3 closed.
- Global all-page PSCIP-L4: not claimed.
