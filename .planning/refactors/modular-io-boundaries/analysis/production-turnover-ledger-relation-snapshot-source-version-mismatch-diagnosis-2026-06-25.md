# Production Turnover Ledger Relation Snapshot Source Version Mismatch Diagnosis - 2026-06-25

**Boundary:** `production:turnover-ledger-relation-snapshot-source-version-mismatch-diagnosis`
**Status:** `production-diagnosis-closed`
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

## Production Evidence

Executed by T0 through root SSH. No authenticated API request, refresh, requeue, repair, replay, readiness mutation, direct SQL mutation, worker restart or deploy was performed in this boundary. No secrets, env values, response bodies, payload rows, grouped rows or business identifiers were printed.

### Runtime Metadata Check

- Active release: `dev-turnover-grouped-metadata-20260625`.
- Active release commit: `2dbacf9f6054baabe7084fc87b87511a49bbdb95`.
- `/health/ready`: `ready`.

The first diagnostic attempt used `build_application()` without `data_dir=default_data_dir()` and therefore did not initialize `PostgresStateStore`; it returned `repository_unavailable`. A follow-up type check using the same builder entrypoint as the service confirmed:

- `state_store_class=PostgresStateStore`;
- `query_service_class=TurnoverLedgerQueryService`;
- `read_repository_class=TurnoverLedgerReadModelRepositoryPort`;
- `has_state_store_connection=true`.

### Expected vs Persisted Source Versions

Read-only deployed-runtime diagnosis using `build_application(data_dir=default_data_dir())`:

- Expected source-version keys:
  - `bank_auto_tag_rules_version`;
  - `bank_transaction_category_schema_version`;
  - `bank_transaction_category_snapshot_version`;
  - `oa_projection_sync_version`;
  - `turnover_ledger_extras_snapshot_version`;
  - `turnover_ledger_schema_version`;
  - `turnover_ledger_tag_selection_snapshot_version`;
  - `turnover_relation_schema_version`;
  - `turnover_relation_snapshot_version`.
- Persisted top-level source-version keys additionally included `bank_detail_source_versions` and `workbench_relation_source_versions`.
- Persisted first-row source-version keys matched the persisted top-level key set.
- Top-level mismatch reasons: `turnover_relation_snapshot_version_mismatch`.
- First-row mismatch reasons: `turnover_relation_snapshot_version_mismatch`.
- `turnover_relation_snapshot_version` expected hash prefix: `7c63fec7ba82c80c`.
- `turnover_relation_snapshot_version` persisted top-level hash prefix: `198f5fd5f7ccbb8a`.
- `turnover_relation_snapshot_version` persisted first-row hash prefix: `198f5fd5f7ccbb8a`.
- Expected equals persisted top-level: `false`.
- Expected equals persisted first row: `false`.
- Repository payload `read_model_status_field=fresh`.
- Repository payload `pagination_total=20`.
- Sanitized returned row count for diagnosis page: `1`.

### API Provider vs Projection Provider

A second read-only comparison constructed `TurnoverLedgerSqlProjectionBuilder(connection=PostgresConnection(...))` and called only its runtime `source_versions_provider()`; it did not rebuild or save rows.

- API expected source-version keys and projection provider keys matched.
- API expected vs projection provider mismatch reasons: none.
- API `turnover_relation_snapshot_version` hash prefix: `7c63fec7ba82c80c`.
- Projection provider `turnover_relation_snapshot_version` hash prefix: `7c63fec7ba82c80c`.
- API equals projection provider: `true`.

### Aggregate Postcheck

- Dirty scopes: `done=187060`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=202955`.
- Read-model dead letters: none.
- Turnover dirty aggregate: `done=461`, latest `2026-06-25 07:07:13.844547+08`.
- Turnover outbox aggregate: `done=563`, latest `2026-06-25 07:07:13.851087+08`.

## Result

The mismatch is not API expected-source drift and not SQL projection provider drift: both deployed providers currently compute the same `turnover_relation_snapshot_version` (`7c63fec7ba82c80c` hash prefix). The persisted turnover ledger read model still carries the older relation snapshot source version (`198f5fd5f7ccbb8a` hash prefix) at both top-level and row-level, even after Row288's visible `turnover_ledger:all` refresh reached `done`; App Status readiness still reports all rows `fresh`.

Classification: `persisted-turnover-read-model-source-version-stale-after-refresh`. The next safe boundary is local code inspection and fix around turnover ledger refresh persistence/readiness proof so a completed refresh either persists current source versions or does not leave App Status fresh while row-level source versions are stale.
