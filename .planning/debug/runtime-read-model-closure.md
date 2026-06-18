---
status: resolved
trigger: "Invoice re-import validation is not fully closed because Runtime Read Model state still has dead-letter, dirty scope, and invalid readiness remnants after the import worker fix."
created: 2026-06-19
updated: 2026-06-19
---

# Debug Session: runtime-read-model-closure

## Symptoms

- Expected behavior: invoice re-import validation can start from a clean runtime state; App Status only shows current import/read model work; durable queue, dirty scopes, and readiness converge without invalid scope leftovers.
- Actual behavior: the import worker/root cause fix drained `import.fact.changed`, but production still has Runtime Read Model remnants: 2 dead-letter outbox events, 1 active dirty scope, non-fresh `bank_detail`/`no_oa_bank_batch` readiness, and invalid bare-month `pending_invoice` readiness rows.
- Error messages: `pending invoice direction must be expense or income.`, `bank_detail_read_model_not_fresh`, `workbench_relation_read_model_not_fresh`, and `runtime worker task exceeded 120s timeout`.
- Timeline: observed during post-fix production verification on 2026-06-19 after release `main-6956b8e2-20260619002659`.
- Reproduction: inspect production `job.outbox_events`, `job.read_model_dirty_scopes`, and `read_model.app_status_readiness` after invoice import cleanup and runtime queue drain.

## Current Focus

- hypothesis: the import chain fix is correct, but Runtime Read Model closure is blocked by two separate issues: stale dependency-refresh ordering from 2026-06-18 and missing `pending_invoice` scope contract validation in `ReadModelRefreshGateway`.
- test: re-enqueue canonical dependency scopes through `ReadModelRefreshGateway`, resolve only covered dead-letters through `runtime_queue_ops`, remove invalid readiness rows through repository/controlled SQL, and add a `pending_invoice` scope policy with tests to prevent future invalid scopes.
- expecting: `job.outbox_events` has no dead_lettered rows, `job.read_model_dirty_scopes` has no non-done rows, `read_model.app_status_readiness` has no invalid `pending_invoice` bare-month rows, and `bank_detail`/`no_oa_bank_batch` month scopes become fresh.
- next_action: monitor the next real invoice re-import; current runtime state is clean and the local code now blocks invalid pending invoice scopes.

## Evidence

- 2026-06-19: production `/health/ready` returned `status=ready`, release consistent, and RabbitMQ dispatcher event types include `import.fact.changed`; this does not prove read model closure because ready omits several read model state details.
- 2026-06-19: latest production import batches are still the 2026-06-18 17:49 batches (`batch_import_0002` through `batch_import_0006`); there is no newer `job.import_jobs` row, so post-cleanup re-import has not happened yet.
- 2026-06-19: `runtime_queue_ops resolve-covered-dead-letters --dry-run` found `pending_invoice.read_model.refresh income:all:2026-02` eligible via `fresh_readiness` and `later_done`, but `no_oa_bank_batch.read_model.refresh 2026-02` ineligible because `active_dirty_scope_exists`.
- 2026-06-19: `read_model.app_status_readiness` has non-fresh `no_oa_bank_batch` rows for `2026-01` through `2026-04` with `bank_detail_read_model_not_fresh`.
- 2026-06-19: `bank_detail` readiness is fresh for `2026-02`, but `2026-01`, `2026-03`, and `2026-04` remain refreshing because they observed `workbench_relation_read_model_not_fresh` before later workbench relation refreshes completed.
- 2026-06-19: `read_model.app_status_readiness` has invalid `pending_invoice` rows for bare months `2026-01` through `2026-06`, all failed with `pending invoice direction must be expense or income.`
- Code evidence: `DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY` validates `cost_statistics` and `no_oa_bank_batch`, but falls back to generic non-empty validation for `pending_invoice`, allowing invalid bare-month scope keys to be enqueued.
- 2026-06-19 01:03-01:04 Asia/Shanghai: controlled production repair enqueued 7 events through `ReadModelRefreshGateway`: `bank_detail` for `2026-01`, `2026-03`, `2026-04`; `no_oa_bank_batch` for `2026-01` through `2026-04`. All completed with fresh readiness and no targeted dirty scope remaining.
- 2026-06-19 01:05 Asia/Shanghai: controlled production repair enqueued `invoice_lifecycle` for `2026-01`, `2026-02`, `2026-04`, `2026-06`; all completed with fresh readiness.
- 2026-06-19: `runtime_queue_ops resolve-covered-dead-letters --dry-run` showed both historical dead-letters eligible via `fresh_readiness` and `later_done`, then `--execute` resolved 2 events with operator reason `runtime_read_model_closure_obsolete_dead_letter`.
- 2026-06-19: deleted 6 invalid bare-month `pending_invoice` readiness rows via repository boundary after confirming they were non-canonical remnants.
- 2026-06-19: final production verification showed `job.outbox_events` status count only `done=156903`, zero `dead_lettered`, zero non-done `job.read_model_dirty_scopes`, and zero non-fresh `read_model.app_status_readiness`.
- 2026-06-19 01:08 Asia/Shanghai: deployed release `main-6956b8e2-20260619010830` containing the `pending_invoice` scope policy; post-deploy `/health/ready` returned ready and points to the new release.
- 2026-06-19 01:09 Asia/Shanghai: post-deploy production verification showed `job.outbox_events` status count only `done=156907`, non-done dirty scopes `0`, non-fresh readiness `0`, invalid pending invoice bare-month readiness `0`.
- 2026-06-19: production code contract check rejects `ReadModelRefreshGateway.enqueue_many("pending_invoice", ["2026-02"], ...)` with `Invalid pending_invoice read model scope_key: 2026-02`.
- 2026-06-19: production import worker check in RabbitMQ mode reports `event_types=["import.process.requested","import.fact.changed"]`, handlers include both, and RabbitMQ routes include `finops.import.fact.changed`.

## Eliminated

- hypothesis: invoice import worker is still not processing `import.fact.changed`.
  reason: production import worker registration and RabbitMQ topology now include `import.fact.changed`, and production `import.fact.changed` backlog drained to done.
- hypothesis: no new import has already proved the full re-import loop after cleanup.
  reason: latest production import batches remain the old 2026-06-18 17:49 batch set and `job.import_jobs` has no rows.

## Repair Plan

1. Add `pending_invoice` scope policy to `ReadModelRefreshGateway` so only valid pending invoice scopes are enqueued: `expense|income:<filter>` with optional `:YYYY-MM`, and `all` only as an aggregate expansion scope when the refresh worker supports it.
2. Add tests proving bare months such as `2026-02` are rejected, valid base scopes are accepted, and valid month scopes are accepted.
3. Production repair through supported paths:
   - enqueue `bank_detail` refresh for `2026-01`, `2026-03`, `2026-04` after `workbench_relation` is fresh;
   - enqueue `no_oa_bank_batch` refresh for `2026-01` through `2026-04`;
   - resolve covered dead-letters only with `runtime_queue_ops resolve-covered-dead-letters`;
   - delete invalid bare-month `pending_invoice` readiness rows after confirming they are invalid non-canonical remnants and not current effective scopes.
4. Verify closure:
   - no `dead_lettered` outbox rows;
   - no non-done dirty scopes;
   - no non-fresh readiness rows for `bank_detail`, `no_oa_bank_batch`, or invalid `pending_invoice` bare months;
   - `/health/ready` stays ready;
   - latest import batches remain old until the user re-imports.

## Resolution

- root_cause: Import worker transport routing was fixed earlier, but Runtime Read Model closure still had historical dependency-defer remnants and a missing `pending_invoice` scope contract. The latter allowed bare-month pending invoice scopes to be enqueued and recorded as failed readiness, even though canonical pending invoice scopes include direction/filter and optional month.
- fix:
  - Added a `pending_invoice` read model scope policy: valid scopes are `all`, `expense|income:<filter>`, and `expense|income:<filter>:YYYY-MM`; bare months and invalid directions now fail fast.
  - Replayed production dependency scopes through `ReadModelRefreshGateway` instead of directly writing fresh state.
  - Resolved only covered dead-letters with `runtime_queue_ops resolve-covered-dead-letters`.
  - Removed invalid bare-month `pending_invoice` readiness remnants after confirming canonical pending invoice scopes were fresh.
- verification:
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_refresh_gateway -v`
  - Production: 7 bank/no-OA repair events completed; 4 invoice lifecycle repair events completed.
  - Production: zero dead-letter outbox rows, zero active dirty scopes, zero non-fresh app status readiness rows, `/health/ready` remains ready on release `main-6956b8e2-20260619010830`.
  - Production: invalid pending invoice bare-month scope is rejected by deployed code.
  - Production: latest import batches are still the 2026-06-18 17:49 cleanup target; no post-cleanup re-import has occurred yet.
- files_changed:
  - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
  - `tests/test_read_model_refresh_gateway.py`
  - `docs/modules/read-models/implementation-notes.md`
  - `docs/modules/runtime-workers/implementation-notes.md`
  - `docs/modules/app-health-operations/implementation-notes.md`
