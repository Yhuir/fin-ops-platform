# Next Prompt

Continue after `production:turnover-ledger-user-scope-hidden-refresh-enqueue-diagnosis`.

## Current State

- Branch: `dev`.
- Active production release remains `dev-no-oa-source-version-480d2d0e-20260625` at git commit `d117b4519284db00c0fa88bdf7faaa938a5b1f69`.
- Row285 full user-scope API metadata smoke passed 37/37 probes, but aggregate postcheck showed one hidden `turnover_ledger:all` refresh enqueue.
- Row286 focused diagnosis confirmed the issue:
  - focused authenticated `GET /api/turnover-ledger?view=grouped&page=1&page_size=50`;
  - HTTP `200`;
  - elapsed `140.719ms`;
  - top-level `read_model_status=null`;
  - `read_model_scope_key=null`;
  - `read_model_stale_reasons=null`;
  - `refresh_enqueued=null`;
  - `refresh_reason=null`;
  - `cache_status=null`;
  - response contained grouped data counts but payload rows/groups were not printed;
  - postcheck showed dirty/outbox totals increased by one;
  - recent event: `turnover_ledger.read_model.refresh`, `scope_type=turnover_ledger`, `scope_key=all`, `status=done`, latest `2026-06-25 06:52:50.733073+08`;
  - recent dirty scope: `turnover_ledger:all`, `status=done`, latest `2026-06-25 06:52:50.729942+08`.
- Health/readiness/dead letters stayed clean.
- Code evidence:
  - `Application._handle_api_turnover_ledger(...)` directly returns the read facade payload.
  - `TurnoverLedgerApiRoutes._normalize_grouped_payload(...)` preserves top-level keys when they exist.
  - `TurnoverLedgerQueryService.list_ledger(...)` would expose `ReadModelQueryGateway` metadata when it uses the SQL/read-model payload path.
  - `TurnoverLedgerService.list_grouped_ledger(...)` is legacy/live grouped generation and does not add read-model metadata.
- Diagnosis: grouped GET can still return legacy grouped payload without freshness metadata while causing a read-model refresh side effect.
- Browser/admin/write probes and global/module closure remain open.

## Next Boundary

`read-models:turnover-ledger-grouped-query-metadata-boundary-fix`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Finish committing/pushing Row286 evidence if it is not already committed.
3. Read turnover ledger module docs and tests before code edits:
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/tests.md`
   - relevant implementation notes if present.
4. Inspect current tests around:
   - `tests/test_turnover_ledger_api.py::test_get_turnover_ledger_enqueues_refresh_for_stale_sql_read_model_source_versions`;
   - grouped view tests around `test_get_turnover_ledger_grouped_view_returns_groups`;
   - `tests/test_turnover_ledger_query_service.py`.
5. Implement the smallest local fix so `view=grouped` does not silently fall back to legacy/live grouped payload without read-model metadata in PostgreSQL/runtime contexts.

## Implementation Scope

Preserve grouped response shape for fresh SQL/read-model payloads, but make freshness metadata and refresh enqueue status observable.

Acceptable directions to evaluate:

- Convert flat SQL read-model payload to grouped payload while preserving `read_model_status`, `read_model_scope_key`, `read_model_stale_reasons`, `refresh_enqueued`, `refresh_reason`, `source_versions` and related metadata.
- If SQL/read-model grouped data is missing or stale in PostgreSQL/runtime contexts, return the gateway's refreshing/metadata payload instead of falling back to live legacy grouped generation.
- Keep local/non-PostgreSQL compatibility behavior only where explicitly required by existing tests.

## Required Verification

- Add/update focused regression tests for grouped GET metadata and no silent legacy enqueue.
- Run targeted turnover ledger tests and any touched architecture guards.
- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check` before commit.

## Stop Gates

- Do not broaden into browser/admin/write probes in this boundary.
- Do not change business grouping semantics beyond preserving existing grouped shape and adding/retaining metadata.
- Do not duplicate SQL table ownership or bypass `TurnoverLedgerQueryService` / `ReadModelQueryGateway`.
- Do not claim module/global closure from local fix/tests alone; production redeploy/re-smoke must be a separate boundary.
