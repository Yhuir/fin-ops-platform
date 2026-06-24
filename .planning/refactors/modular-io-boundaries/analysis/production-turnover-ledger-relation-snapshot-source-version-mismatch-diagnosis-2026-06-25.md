# Production Turnover Ledger Relation Snapshot Source Version Mismatch Diagnosis - 2026-06-25

**Boundary:** `production:turnover-ledger-relation-snapshot-source-version-mismatch-diagnosis`
**Status:** `runbook-prepared`
**Module closure:** `not-module-closed`
**Production mutation:** none planned
**Previous boundary:** `production:turnover-ledger-grouped-metadata-fix-deploy-and-resmoke`

## Goal

Diagnose the focused grouped turnover stale reason:

- `turnover_relation_snapshot_version_mismatch`

Use read-only production metadata to determine whether the mismatch is stale persisted turnover rows, API expected-source drift, worker writer-source drift, or an aggregate/readiness-vs-row-level proof gap.

## Local Contract Facts

- `build_turnover_ledger_source_versions(...)` includes `turnover_relation_snapshot_version`, computed as `WorkbenchReadModelService.snapshot_version(relation_service.snapshot())`.
- `Application._turnover_ledger_source_versions()` provides the expected source versions for `TurnoverLedgerQueryService`.
- `TurnoverLedgerQueryService.list_ledger(...)` routes SQL/read-model payloads through `ReadModelQueryGateway.load(...)`.
- `ReadModelQueryGateway.load(...)` returns public `read_model_status=refreshing`, `refresh_enqueued=true` and `refresh_reason=source_version_mismatch` when `source_version_mismatch_reasons(...)` finds a mismatch.
- Row288 proved the deployed grouped API now exposes that metadata instead of hiding the enqueue.

## Safety Scope

Allowed:

- read-only active release and `/health/ready` checks;
- read-only deployed-runtime Python metadata query using production env without printing env values;
- computing expected source versions, persisted read-model source versions, mismatch reasons and sanitized hashes/key lists;
- read-only aggregate dirty/outbox/readiness/dead-letter checks.

Forbidden:

- authenticated API probes;
- broad user-scope/browser/admin/write probes;
- printing secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows or business identifiers;
- manual refresh, requeue, repair, replay, readiness mutation, direct SQL mutation, worker restart or deploy;
- claiming module/global closure from diagnosis.

## Read-only Evidence Plan

1. Confirm active release and `/health/ready`.
2. Load deployed runtime env without printing values.
3. Build the deployed `Application`.
4. Compute expected turnover source versions via `app._turnover_ledger_source_versions()`.
5. Load only turnover read-model metadata through the existing read repository:
   - `list_turnover_ledger_view(family="all", direction="all", status=None, page=1, page_size=1, scope_key="all")`.
6. Print only:
   - expected source-version keys;
   - actual source-version keys;
   - mismatch reasons;
   - expected/actual hash prefixes for `turnover_relation_snapshot_version`;
   - whether expected and actual `turnover_relation_snapshot_version` are equal;
   - scalar row count/pagination total only;
   - aggregate dirty/outbox/readiness/dead-letter status counts.

## Stop Criteria

Stop after classification. Do not trigger a refresh or rerun focused/full API smoke in this boundary.
