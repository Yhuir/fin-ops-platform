# server.py ETC legacy batch route owner audit

- Date: 2026-06-25
- Boundary: `server-py:etc-legacy-batch-route-owner-audit`
- Status: `local-implementation-closed`
- Module closure: `implementation-gap-open`
- Production: not used

## Result

Audited legacy `/api/etc/batches*` compatibility ownership and completed the first safe implementation slice.

Added:

- `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py::EtcLegacyBatchApiRoutes`

Moved URL parsing and dispatch for these compatibility routes out of `Application`:

- `GET /api/etc/batches`
- `GET /api/etc/batches/{batch_id}`
- `DELETE /api/etc/batches/{batch_id}`
- `POST /api/etc/batches/draft`
- `POST /api/etc/batches/{batch_id}/draft`
- `POST /api/etc/batches/{batch_id}/confirm-submitted`
- `POST /api/etc/batches/{batch_id}/mark-not-submitted`

`server.py` now delegates the whole legacy batch route group through `_etc_legacy_batch_routes().route(...)`.

## Boundary Decision

The audit found that legacy batch routes are a compatibility surface with mixed responsibilities:

- list/detail are compatibility payload assembly over business batches, submitted batches and import batches;
- draft/confirm/mark-not-submitted mutate OA/submission state and refresh derived data;
- delete fans out to business-batch delete, submission/import cleanup, reconciliation-task cleanup, canonical invoice cleanup, link repair, refresh and persistence.

Moving all handler internals in the same slice would mix route ownership with service-boundary extraction. The safe local slice is therefore a compat route-owner facade:

- route owner owns URL parsing and route dispatch;
- side-effecting handlers remain explicit callbacks for this slice;
- route owner does not receive `Application`;
- static guard prevents direct route dispatch from returning to `server.py`.

## Tests Added Or Changed

Changed:

- `tests/test_platform_runtime_boundary_guards.py`
  - Added `test_etc_legacy_batch_routes_delegate_to_compat_route_owner`.
  - The guard verifies explicit callback injection, no whole-`Application` injection, route/subroute coverage and no direct handler calls from `_handle_request_untracked`.

Existing tests rerun:

- Targeted legacy batch delete regressions.
- Targeted legacy batch list/detail regressions.
- Targeted reconciliation task draft/delete repair regressions.
- Targeted route-owner static guards.

## Seven Test Categories

1. Business core unit tests: covered by existing legacy batch delete/list/draft regressions for submitted/unsubmitted state and task link repair behavior.
2. Service-layer tests: not changed; side-effecting handlers remain in `Application` callbacks for the next boundary.
3. API contract tests: covered by targeted legacy batch endpoint regressions and static route-owner guard.
4. Read model/cache/background job tests: partially covered through refresh-triggering delete/draft regressions; no worker implementation changed.
5. Frontend component and interaction tests: not applicable; API shape and frontend behavior are unchanged.
6. End-to-end business-flow integration tests: covered at backend integration level by import/draft/delete/list/detail chains.
7. Existing feature regression tests: covered by submitted/unsubmitted delete, stale invoice reference repair, list counts, selected detail and attachment checks.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py backend/src/fin_ops_platform/app/server.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_routes_delegate_to_compat_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_import_routes_delegate_to_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_delete_etc_batch_route_deletes_unsubmitted_and_submitted tests.test_etc_backend.EtcApiTests.test_delete_etc_submission_batch_route_cascades_mutable_batch_contents tests.test_etc_backend.EtcApiTests.test_delete_etc_submission_batch_route_repairs_stale_invoice_references tests.test_etc_backend.EtcApiTests.test_etc_batch_query_api_returns_counts_summary_plate_summary_and_items tests.test_etc_backend.EtcApiTests.test_etc_batch_list_only_checks_attachment_status_for_selected_detail tests.test_etc_backend.EtcApiTests.test_unsubmitted_oa_draft_batch_is_listed_and_deletable tests.test_etc_backend.EtcApiTests.test_delete_missing_unsubmitted_oa_draft_batch_repairs_reconciliation_task_link -v
```

Additional verification is required before commit:

```bash
bash scripts/verify.sh docs
git diff --check
git diff --cached --check
```

## Docs Impact

Updated `docs/modules/etc-tickets/implementation-notes.md` because route ownership changed.

Long-term product/API docs are unchanged: route paths, payload shape, permissions, business states and user-facing behavior did not change.

## Remaining Risk

Local implementation gaps remain:

- legacy batch handler internals still live in `Application` as explicit callbacks;
- `DELETE /api/etc/batches/{batch_id}` still owns broad cleanup orchestration in `Application`;
- legacy list/detail payload helpers still live in `Application`;
- ETC invoice list/revoke-submitted routes still live in `Application`;
- production browser/admin/write evidence remains final validation only.

## Next Boundary

`server-py:etc-legacy-batch-delete-side-effect-service-audit`

Audit legacy batch delete side effects and choose the next safe local implementation boundary: cleanup service extraction, operation-result port, or narrower delete callback migration.
