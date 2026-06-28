# Read Model Main Closure Wave 7 - legacy quarantine and production evidence runbook

Date: 2026-06-26

## Boundary

`main-read-model-closure:wave-7-legacy-quarantine-and-production-evidence-runbook`

This wave audited the remaining legacy/readiness surfaces and added a long-lived production evidence runbook plus guard coverage.

## Codebase analysis before implementation

- Existing guards already quarantine the main legacy contamination surfaces:
  - `routes_legacy_workbench_actions.py` must remain in `LegacyWorkbenchActionRoutes`, cannot write dirty/outbox directly, and cannot import read model refresh/write facade boundaries.
  - `routes_etc_legacy_batches.py` must remain behind `EtcLegacyBatchApiRoutes` with explicit ports and no whole-`Application` dependency.
  - Workbench row-detail legacy fallback is confined to one route-owner wiring and cannot gain write/runtime side effects.
  - Direct SQL writes to `job.outbox_events` / `job.read_model_dirty_scopes` remain guarded.
  - Frontend default-`fresh` sites are classified by guard.
- CodeGraph impact showed `LegacyWorkbenchActionRoutes`, `EtcLegacyBatchApiRoutes`, and `WorkbenchLegacyApiSqlReadProvider` are still reachable from `server.py` route dispatch/provider wiring. Deleting them in this wave would be a behavior change without caller-removal proof.
- The current unclosed global item is production evidence, not another local target-envelope gap.

## Implementation

- Added `docs/operations/read-model-production-evidence-runbook.md` as a long-lived runbook for PSCIP-L4 production evidence:
  - rollout preconditions,
  - no-secret rules,
  - read-only evidence collection,
  - business write-operation samples,
  - business inverse restore priority,
  - preapproved bounded DB restore protocol,
  - performance evidence,
  - hard-stop gates.
- Linked the runbook from `docs/operations/index.md`.
- Linked the runbook from `docs/modules/read-models/boundary-io.md`.
- Added an architecture guard that requires the runbook to retain the key no-secret, business inverse, bounded DB restore, operation-before snapshot, exact predicate, single transaction, post-restore verification, operation barrier, deploy and PSCIP-L4 markers.

## Legacy deletion / quarantine judgment

- No legacy route was deleted. Current proof shows these surfaces are still normal route/provider entry points and need a dedicated caller-removal migration before deletion.
- This wave strengthened durable guard coverage for the production evidence and restore gates instead of weakening runtime compatibility.

## Verification to run before commit

```bash
PYTHONPATH=backend/src python3 -m unittest -q tests.test_read_model_architecture_guards
bash scripts/verify.sh docs
git diff --check
```

Then run the standard broad read model/runtime/frontend gates before committing.

## Remaining work

- Execute production rollout and evidence collection after local L3 gates pass.
- Use `docs/operations/read-model-production-evidence-runbook.md` for production samples, restoration and PSCIP-L4 classification.
- Legacy route deletion remains separate and requires caller-removal proof.

## Closure status

- Production evidence runbook and guard: local closed.
- Legacy route deletion: deferred by caller evidence.
- Global all-page PSCIP-L4: not claimed.
