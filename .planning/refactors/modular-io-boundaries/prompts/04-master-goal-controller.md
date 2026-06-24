# Prompt: Modular IO Refactor Master Goal Controller

Copy the full prompt below into Codex to start or resume the autonomous run.

```text
$gsd-autonomous --auto

You are Codex working in /Users/yu/Desktop/fin-ops-platform.

Goal:
Autonomously continue the production-grade modular IO boundary refactor until true closure or a hard stop gate is reached. This is a closed-loop GSD controller: review and full analysis first, then one bounded implementation/planning slice, then review, verification, state-machine accounting, commit/push to dev, next prompt generation, and immediate continuation.

I may be away. Do not wait for me unless a hard stop gate is hit.

Hard branch rules:
- Work only in /Users/yu/Desktop/fin-ops-platform.
- Use the main repository directory directly. Do not create a worktree.
- Work only on branch dev.
- Commit and push only to origin/dev.
- Do not work on main.
- Do not commit to main.
- Do not push to main.
- Never force-push, rebase dev automatically, reset dev automatically, delete branches, or run destructive cleanup.
- Every pushed dev commit must be safe to merge into main for the completed slice, with no known broken behavior.

Preflight before any implementation:
1. Run pwd, git status --short --branch, git remote -v.
2. Confirm current directory is /Users/yu/Desktop/fin-ops-platform.
3. Confirm branch is dev.
4. Fetch origin with prune.
5. If the worktree is clean, pull origin/dev with --ff-only.
6. If the worktree is clean, merge origin/main into dev only when the merge is conflict-free.
7. If origin/main merge conflicts, stop and record blocked-hard-stop/dev-main-alignment-conflict. Do not auto-resolve finance, read model, worker, permission, migration, lockfile, generated-file, or planning-state conflicts.

Dirty worktree rule:
- If dirty files exist, inspect ownership before writing.
- If dirty files look like user work or unrelated work, stop before staging, formatting, reverting, stashing, committing, or overwriting them.
- If dirty files are clearly from the current autonomous slice, continue that slice.
- Preserve user changes.

Required reading before edits:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- .planning/ROADMAP.md
- .planning/refactors/README.md
- docs/index.md
- docs/app-architecture/README.md
- docs/app-architecture/runtime-and-ownership.md
- docs/modules/README.md
- docs/dev/index.md
- docs/operations/index.md
- every Markdown file under .planning/refactors/modular-io-boundaries/
- every Markdown file under .planning/refactors/modular-io-boundaries/analysis/
- every Markdown file under .planning/refactors/modular-io-boundaries/autonomous/
- every Markdown file under .planning/refactors/modular-io-boundaries/prompts/

Planning source hierarchy:
- .planning/ROADMAP.md is the root page-analysis roadmap.
- .planning/refactors/README.md is the refactor index.
- .planning/refactors/modular-io-boundaries/README.md is this refactor package entry.
- 00-REQUIREMENTS.md defines production-grade modular IO requirements.
- 03-REFACTOR-STATE-MACHINE.md defines legal states, transitions, and completion semantics.
- 04-IMPLEMENTATION-ROADMAP.md defines modular IO phase roadmap progress.
- autonomous/MODULE-QUEUE.md is the executable boundary queue.
- autonomous/STATE.md, autonomous/JOURNAL.md, and autonomous/NEXT-PROMPT.md are execution accounting.

Do not collapse these sources into one unqualified completion percentage.

Current state expected on start:
- Branch: dev.
- Last completed controller step: read-model auth preflight and API smoke runbook.
- Last status: worker wave 1 accepted as local evidence/gap maps; authenticated API smoke deferred for missing non-secret auth config; public page-shell smoke passed for 17 default `/fin-ops/*` routes; Workbench active-generation query-plan evidence is collected; all public API probes are auth-gated with 401.
- Queue semantics are corrected: Status is slice status; Module Closure is broader module closure.
- Parallel orchestration is documented in `12-PARALLEL-ORCHESTRATION.md`; this master prompt remains the single-thread controller entry. Do not run multiple copies of this master prompt against `dev`.
- T0 accepted T1-T8 parallel handoffs and integrated them in commit `b60a343a`.
- `server-py:workbench-group-detail-route-owner-extraction` is now implementation-closed locally.
- `planning:commit-backed-state-reconciliation` is complete in `analysis/commit-backed-state-reconciliation-2026-06-25.md`.
- `production:read-model-production-evidence-matrix-read-only-sweep` is complete in `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`: all App Status read-model readiness rows are fresh, all dirty scopes are done, read-model outbox events are done, no read-model dead letters remain, current workers have fresh heartbeats, read-model row-count/source-version tables are queryable, and Workbench high-row table counts are visible.
- `production:read-model-scope-contract-runtime-dry-run-classification` is complete in `analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`: `/health/ready` is ready on active API port `18001`, cost-statistics scope contract dry-run returned `ok=true` with `violation_count=0` and no current uncovered failures, invalid read-model scope dry-run returned `ok=true` with `invalid_scope_count=0`, and legacy `cost`/`tax` rows are historical `done` dirty scopes only.
- `planning:post-scope-contract-runtime-classification-next-boundary-selection` is complete in `analysis/planning-post-scope-contract-runtime-classification-next-boundary-selection-2026-06-25.md`: final closure, production cleanup, immediate worker creation and Go admission were rejected as premature; the next boundary had to map module closure evidence and file ownership first.
- `planning:read-model-module-closure-evidence-ownership-map` is complete in `analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`: row248 mapped read-model-heavy modules to route/API surfaces, local docs/test owners, row245/246 production facts, remaining authenticated API/browser/high-row gaps and four worker ownership/handoff scopes. No worker thread, production command, runtime mutation or closure claim occurred.
- `planning:read-model-module-closure-worker-wave-1-prompts` and `planning:read-model-module-closure-worker-wave-1-monitor-and-accept` are complete. T0 accepted W1 `bf03ba98`, W2 `82eb8919`, W3 `cfc495f1` and W4 `525818ba` as local evidence/gap maps only in `analysis/read-model-module-closure-worker-wave-1-acceptance-2026-06-25.md`.
- `planning:read-model-authenticated-api-browser-smoke-runbook-selection` is complete in `analysis/read-model-authenticated-api-browser-smoke-runbook-selection-2026-06-25.md`: T0 selected a production read-only API response-shape smoke runbook as the next boundary and deferred browser smoke until non-secret auth/harness proof.
- `production:read-model-authenticated-api-response-shape-smoke-runbook` is deferred in `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`: `/health/ready` was ready, but no non-secret HTTP SLO auth env was configured, so API smoke did not run; post-checks kept dirty scopes done, readiness fresh and read-model outbox done.
- `production:read-model-public-page-shell-smoke-runbook` is complete in `analysis/production-read-model-public-page-shell-smoke-runbook-2026-06-25.md`: the initial API-listener base returned 17/17 404 and was classified as wrong-base operator evidence; the public-base rerun returned `status=pass`, `probe_count=17`, `failed_probe_count=0`, `max_p95_ms=27.782`, and all default `/fin-ops/*` page-shell routes returned 200 with `/health/ready` ready before and after.
- `planning:post-public-page-shell-smoke-next-boundary-selection` is complete in `analysis/planning-post-public-page-shell-smoke-next-boundary-selection-2026-06-25.md`: auth retry, browser data smoke, final closure and a new worker wave were rejected as premature; read-only shadow-read rehearsal was selected as the next T0-owned evidence boundary.
- `production:read-model-shadow-read-rehearsal-read-only-runbook` is complete as `production-evidence-deferred` in `analysis/production-read-model-shadow-read-rehearsal-read-only-runbook-2026-06-25.md`: tool availability/read-only guard/redacted output were proven, but current production `local_pickle` is not a comparable primary for PostgreSQL runtime and `workbench_read_models` hit a statement timeout.
- `planning:post-shadow-read-rehearsal-next-boundary-selection` is complete in `analysis/planning-post-shadow-read-rehearsal-next-boundary-selection-2026-06-25.md`: selected a PostgreSQL-native Workbench high-row query-plan/read-only runbook.
- `production:workbench-read-model-high-row-query-plan-read-only-runbook` is complete as `production-controlled` in `analysis/production-workbench-read-model-high-row-query-plan-read-only-runbook-2026-06-25.md`: active Workbench generation rows are bounded, historical tables are large, and active page-like queries use generation/scope indexes under EXPLAIN.
- `planning:post-workbench-high-row-query-plan-next-boundary-selection` is complete in `analysis/planning-post-workbench-high-row-query-plan-next-boundary-selection-2026-06-25.md`: selected unauthenticated API status/shape classification with existing `http_slo_probe`.
- `production:read-model-unauthenticated-api-status-shape-classification-runbook` is complete as `production-evidence-deferred` in `analysis/production-read-model-unauthenticated-api-status-shape-classification-runbook-2026-06-25.md`: all 38 default API probes returned 401, so public API shape closure needs auth or an internal contract harness.
- `planning:post-unauthenticated-api-classification-next-boundary-selection` is complete in `analysis/planning-post-unauthenticated-api-classification-next-boundary-selection-2026-06-25.md`: authenticated HTTP retry, public browser data smoke, another unauthenticated route sweep and final closure were rejected as premature; the next boundary is an internal API contract harness design using existing `Application.handle_request(...)`, route-owner and auth/session test seams.
- `planning:read-model-internal-api-contract-harness-design` is complete in `analysis/planning-read-model-internal-api-contract-harness-design-2026-06-25.md`: the harness design uses `Application.handle_request(...)`, existing unittest default auth plus explicit auth guard negatives, `http_slo_probe.DEFAULT_API_PROBES` as route inventory, and sanitized response envelope/readiness metadata assertions; it rejects Flask test client, production auth bypass and broad payload snapshots.
- `contract:read-model-internal-api-contract-harness-implementation` is complete in `analysis/contract-read-model-internal-api-contract-harness-implementation-2026-06-25.md`: added `tests/test_read_model_api_contract_harness.py`, covering representative local GET envelopes and explicit auth guard negatives through `Application.handle_request(...)`; targeted verification passed with 2 tests and 51 subtests.
- `planning:post-internal-api-contract-harness-next-boundary-selection` is complete in `analysis/planning-post-internal-api-contract-harness-next-boundary-selection-2026-06-25.md`: Row262 local API evidence was reconciled, production auth retry/final closure/full e2e smoke were rejected as premature, and browser data harness coverage mapping was selected next.
- `planning:read-model-browser-data-harness-coverage-map` is complete in `analysis/planning-read-model-browser-data-harness-coverage-map-2026-06-25.md`: existing deterministic Playwright/Vitest/browser evidence, Row262 local API harness coverage, Row245/246/257 production-controlled facts and external-risk gaps were mapped for read-model-heavy modules; the next smallest executable boundary is a targeted existing Playwright subset rerun.
- `browser:read-model-browser-data-targeted-smoke-runbook` is complete in `analysis/browser-read-model-browser-data-targeted-smoke-runbook-2026-06-25.md`: the targeted Playwright subset initially exposed four stale spec assertions, T0 aligned the input-invoice and Workbench specs with current operation-barrier/non-fresh/projection contracts, reran the affected specs with 20/20 passed and the full subset with 53/53 passed.
- `planning:post-browser-data-targeted-smoke-next-boundary-selection` is complete in `analysis/planning-post-browser-data-targeted-smoke-next-boundary-selection-2026-06-25.md`: Row265 local browser evidence was reconciled and full deterministic `npm run e2e:smoke` was selected as the next boundary because smoke is the repository's broad local Browser evidence layer.
- `browser:read-model-full-deterministic-e2e-smoke-runbook` is complete in `analysis/browser-read-model-full-deterministic-e2e-smoke-runbook-2026-06-25.md`: the full deterministic Chromium smoke inventory passed with 175/175 tests in 7.6m and no product/spec/smoke membership change.
- `planning:post-full-deterministic-e2e-smoke-next-boundary-selection` is complete in `analysis/planning-post-full-deterministic-e2e-smoke-next-boundary-selection-2026-06-25.md`: Row267 local smoke evidence was reconciled against remaining external-risk gaps and auth preflight plus metadata-only production API smoke was selected next.
- `production:read-model-auth-preflight-and-api-smoke-runbook` is deferred in `analysis/production-read-model-auth-preflight-and-api-smoke-runbook-2026-06-25.md`: `/health/ready` was ready, but `http_slo_auth_configured=no`, so authenticated API smoke did not run; post-checks kept dirty scopes done, readiness fresh and read-model outbox done.
- The next pending boundary is `planning:post-auth-preflight-next-boundary-selection`.
- Future progress reports must continue using the commit-backed reconciliation baseline, not memory or raw state-file row counts.
- bank_detail local implementation support is accounted for through the collaborator audit, but bank_detail is not full module closed; real PostgreSQL/worker/App Status/high-row/browser evidence remains unavailable and deferred.
- workbench_relation local implementation support surfaces are accounted for, but workbench_relation is not globally closed; real PostgreSQL relation/history, worker dirty/outbox/readiness, App Status, high-row performance and browser smoke evidence remain unavailable and deferred.
- pending_invoice local implementation support is accounted for after repository port, freshness/barrier audit, scope policy filter allowlist and mutation freshness target work; real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- oa_pending_payment local implementation support is accounted for after repository port, freshness/barrier audit and local closure audit; real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- `OaPendingPaymentReadModelRepositoryPort` is wired for rows/detail and projection save/mark/prune paths.
- OA pending payment Workbench relation source-version lookup uses the Workbench relation port.
- OA pending payment rows/filter-options/detail freshness gates return refreshing/unavailable on missing/stale/source mismatch and enqueue through `ReadModelRefreshGateway`.
- OA pending payment `all` refresh is fan-out control scope; worker expansion enqueues concrete month shards and prunes orphan shards.
- Frontend write-after-read operation barrier selection prefers concrete month scopes over fan-out-only `all` when mutation responses return both.
- Unused app-level OA pending payment rebuild/list/mark/live helpers were removed from `Application`.
- input_invoice_usage is selected as the fifth non-Go read model implementation pilot.
- input_invoice_usage shares the invoice-usage-collection worker/projection family with oa_pending_payment and output_invoice_collection.
- input_invoice_usage production rows, filter/export helpers and relation details must not live-scan fallback when SQL read model runtime is required.
- input_invoice_usage:all remains fan-out control scope; all-query freshness proof must come from concrete month rows/scopes and active dirty/outbox state.
- `InputInvoiceUsageReadModelRepositoryPort` is wired for PostgreSQL state-store reads and projection save/mark/prune paths.
- `InvoiceUsageCollectionSqlProjectionBuilder` owns input usage projection rebuild/list/mark/prune behavior.
- `input_invoice_usage` rows/detail/filter/export SQL read paths are fresh-gated and enqueue refresh through `ReadModelRefreshGateway` on miss/stale/source-version mismatch.
- Production SQL runtime relation detail now returns `202`/refreshing and enqueues `input_invoice_usage:all` when the SQL read repository is unavailable, instead of falling back to live detail rebuild.
- `input_invoice_usage:all` remains fan-out control scope; all-query freshness proof comes from concrete month rows/scopes plus active dirty/outbox state.
- Unused app-level input usage projection helpers were removed from `Application`: `list_input_invoice_usage_scope_shards(...)`, `mark_input_invoice_usage_scope_empty(...)`, and `rebuild_input_invoice_usage_read_model_scope(...)`.
- input_invoice_usage local implementation support is accounted for after repository port, fresh gate, relation-detail fresh gate, source-version proof, scope policy, worker fan-out, operation barrier, legacy contamination and tests/docs; real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- output_invoice_collection is the sixth non-Go read model implementation pilot.
- output_invoice_collection shares the invoice-usage-collection worker/projection family with input_invoice_usage and oa_pending_payment.
- `OutputInvoiceCollectionReadModelRepositoryPort` is wired for PostgreSQL state-store reads and projection save/mark/prune paths.
- output_invoice_collection freshness, force-refresh, all fan-out/month proof, operation-barrier and app-level helper audit work is implemented locally: mutation responses expose `read_model_scope_keys`/`freshness_targets`, frontend flows wait on concrete month targets, and unused app-level output projection helpers were removed from `Application`.
- output_invoice_collection production SQL runtime relation detail now returns `202`/refreshing and enqueues `output_invoice_collection:all` when the SQL read repository/detail lookup is unavailable, instead of falling back to live detail rebuild.
- output_invoice_collection local implementation support is accounted for after repository port, rows/filter/export/detail fresh gates, source-version proof, scope policy, worker fan-out, operation barrier, app-level helper removal, legacy/live path classification and tests/docs; real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- invoice_lifecycle is selected as the seventh non-Go read model implementation pilot because it is the shared upstream lifecycle state boundary for pending invoice, input/output usage, OA pending payment, tax, cost/search and import fan-out.
- `InvoiceLifecycleReadModelRepositoryPort` now exposes only the manifest-listed lifecycle read model methods.
- `InvoiceLifecycleReadFacade` uses the narrow port for lifecycle row lookups while preserving unavailable-path behavior for missing repository methods.
- `InvoiceLifecycleSqlProjectionBuilder` uses the narrow port for lifecycle save/mark paths.
- No `PostgresStateStore.invoice_lifecycle_sql_read_repository` property was added because no existing property, construction path or caller exists.
- Invoice lifecycle freshness/barrier audit is closed as a regression guard: facade reads do not expose a queryable `all`, refresh service expands `all` into month shards, source-version currentness is checked before and after rebuild, scope policy accepts month/all only, and App Status/worker/manifest contracts are registered.
- `OperationFreshnessBarrierService` now has an invoice lifecycle regression proving exact month targets are not blocked by other-month pending outbox.
- `InvoiceLifecycleDerivedLifecycleExecutor` now owns invoice lifecycle derived lifecycle refresh execution; `Application` only assembles the gateway-backed enqueue callback.
- `Application._derived_lifecycle_invoice_lifecycle_executor(...)` is removed and guarded from returning.
- invoice_lifecycle local implementation support is accounted for after repository port, freshness/barrier and derived lifecycle executor slices, but real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- tax_offset is selected as the eighth non-Go read model implementation pilot because it directly consumes invoice lifecycle/certification state, has high stale-read risk after plan save/certified import/import fan-out, and has a narrow repository-port first slice.
- `TaxOffsetReadModelRepositoryPort` now exposes only `load_tax_offset_read_models`, `get_tax_offset_view`, and `save_tax_offset_read_models`.
- PostgreSQL state-store tax read/write wiring uses `TaxOffsetReadModelRepositoryPort`, and `PostgresStateStore.tax_offset_sql_read_repository` returns the port over the optional SQL read connection.
- `TaxOffsetSqlProjectionBuilder` saves rebuilt month scopes through the narrow tax offset port.
- Tax offset freshness/barrier audit is complete locally: SQL reads use `ReadModelQueryGateway`, missing SQL repository fails closed in production runtime, `all` refresh fans out to month shards, plan save rejects non-fresh/source-mismatched reads, and the frontend waits on current-month `tax_offset` operation barrier after plan save/certified import.
- The recorded OA attachment invoice API regression was fixed by centralizing `invoice_type=进项发票` / `销项发票` formal invoice evidence fallback in `FinancialObjectIdentityPolicy` when `evidence_type` is missing.
- Tax offset worker rebuild executor extraction is complete: `TaxOffsetWorkerRebuildExecutor` now owns compat worker rebuild, read model persistence and fresh Redis month/summary cache publish behavior.
- `Application.rebuild_tax_offset_read_model_scope(...)` is now dependency assembly plus a thin delegate to `TaxOffsetWorkerRebuildExecutor.rebuild_scope(scope_key)` and is guarded from re-owning rebuild, persistence or direct fresh cache publishing.
- Tax offset derived lifecycle executor extraction is complete: `TaxOffsetDerivedLifecycleExecutor` now owns read model invalidation and month-cache clearing behavior; registry entries use explicit executor methods and removed app-owned helper methods are guarded.
- Tax offset cache warmup executor extraction is complete: `TaxOffsetCacheWarmupExecutor` owns optional cache warmup env gating, month normalization, idempotent background job scheduling, run-job progress/success handling, read model upsert and snapshot persistence.
- `Application._schedule_tax_offset_cache_warmup(...)` remains compat-only thin delegation to the executor.
- `Application._run_tax_offset_cache_warmup_job(...)` and `_tax_offset_cache_warmup_enabled(...)` are removed and guarded from returning.
- Tax offset final local closure audit found a remaining local implementation gap: broad `Application._persist_state(...)` still serializes `tax_offset_read_models` into the legacy full-state snapshot path.
- Tax offset full-state snapshot quarantine is complete: broad `Application._persist_state(...)` no longer serializes `tax_offset_read_models`, while explicit runtime/executor persistence through `_persist_tax_offset_read_models_best_effort(...)` remains available.
- Tax offset post-full-state local closure audit is complete: no remaining local implementation gap was found after full-state snapshot quarantine. Local support is accounted for, but real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- `cost_statistics` is selected as the ninth non-Go read model implementation pilot because it has high cross-page stale-read risk, special `active/all` scope grammar, queryable parent aggregate semantics, an old `cost-tax` compatibility worker lane and a narrow repository-port first slice.
- Cost statistics repository port extraction is complete: `CostStatisticsReadModelRepositoryPort` owns manifest-listed load/get/save, PostgreSQL state-store cost read wiring returns the port, and `CostStatisticsSqlProjectionBuilder` saves through it.
- Cost statistics freshness/barrier audit is analysis-closed: SQL fresh gate, production repository unavailable behavior, scope policy normalization, parent aggregate proof, primary/compat worker split and App Status registry are locally accounted for, but `Application._derived_lifecycle_cost_statistics_executor(...)` still owns derived lifecycle invalidation/warmup-vs-refresh fallback and enqueued-job accounting.
- Cost statistics derived lifecycle executor extraction is complete: `CostStatisticsDerivedLifecycleExecutor` owns invalidation, `pending_invoice_rules_changed` persist-empty behavior, no-warmup refresh fallback metadata and enqueued-job accounting; `Application._derived_lifecycle_cost_statistics_executor(...)` is removed and guarded from returning.
- Cost statistics post-derived local closure audit is analysis-closed: warmup/retry/rebuild app methods are compat-only delegates to `CostStatisticsRuntimeService`.
- Cost statistics full-state snapshot quarantine is complete: broad `Application._persist_state(...)` no longer serializes `cost_statistics_read_models`, while explicit runtime/query persistence through `_persist_cost_statistics_read_models_best_effort(...)` remains available and startup compatibility loading remains.
- Cost statistics post-full-state local closure audit is complete: no remaining local implementation gap was found, local support is accounted for, but real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred and the module is not globally closed.
- `turnover_ledger` is selected as the tenth non-Go read model implementation pilot because it has high user-visible stale grouped-ledger risk, direct Workbench/cost/search fan-out impact and a narrow manifest-listed repository-port first slice.
- Turnover ledger repository port extraction is complete: `TurnoverLedgerReadModelRepositoryPort` owns manifest-listed list/save/clear methods, PostgreSQL state-store turnover read wiring returns the port, `TurnoverLedgerQueryService` app injection uses the turnover-specific port instead of the broad workbench SQL read repository, and worker projection save paths receive the port.
- Turnover ledger freshness/barrier audit is analysis-closed: SQL fresh gate, month/all scope policy, manifest/App Status/worker registration, Workbench relation source-version proof and operation barrier evidence exist, but app-owned clear/refresh helpers remain a local implementation gap.
- Turnover ledger refresh producer/clear extraction is complete: `TurnoverLedgerReadModelRefreshProducer` owns non-transactional turnover refresh enqueue and best-effort clear, enqueue stays behind `ReadModelRefreshGateway`, and clear uses the turnover-specific read repository port instead of broad `_workbench_sql_read_repository`.
- Turnover ledger local implementation support is accounted for after repository port, freshness/barrier audit and refresh producer/clear extraction, but real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred and the module is not globally closed.
- `no_oa_bank_batch` is selected as the eleventh non-Go read model implementation pilot because it has the highest remaining page-level stale-read, Workbench relation adjacency, public snapshot persistence and operation-barrier risk.
- Target verification fixed a stale no-OA refresh-service constructor keyword: `NoOaBankBatchReadModelRefreshService` now passes `pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(...)` to match the current application service contract.
- `search` is selected as the twelfth non-Go read model implementation pilot.
- `SearchReadModelRepositoryPort` owns manifest-listed `search_index(...)` and `save_search_index_rows(...)`.
- PostgreSQL state-store search read wiring and `SearchPendingSqlProjectionBuilder` search save paths use the narrow port.
- App-owned `Application.rebuild_search_index_scope(...)` and `_build_search_index_rows_for_month(...)` were removed; search rebuild ownership remains with `SearchPendingSqlProjectionBuilder`.
- `SearchQueryFreshnessService` owns `/api/search` SQL miss/stale/source-version payload assembly.
- `SearchIndexSourceVersionsProvider` owns search expected source-version proof.
- App-owned `Application._get_search_payload_from_sql_read_model(...)` and `_search_index_expected_source_versions(...)` were removed and guarded from returning.
- `SearchReadModelRefreshProducer` owns search refresh enqueue and invalidation scope normalization.
- App-owned `Application._enqueue_search_read_model_refresh(...)` and `_invalidate_search_read_model_scopes(...)` were removed and guarded from returning.
- Production PostgreSQL `/api/search` without a SQL repository now fails closed instead of live scanning legacy/local state.
- `OAProjectionSyncService` now routes Search refresh fan-out through `SearchReadModelRefreshProducer` instead of direct generic `enqueue_many("search", ...)`.
- Runtime import-state Search refresh fan-out now routes through `SearchReadModelRefreshProducer` instead of generic `_enqueue_scopes("search", ...)`.
- Search worker `search:all` shard fan-out now routes through `SearchReadModelRefreshProducer.enqueue_scope_keys(...)` instead of direct `ReadModelRefreshGateway.enqueue_many("search", ...)`.
- Search local implementation support is accounted for after repository port, query freshness service, refresh producer, production repository-unavailable fail-closed behavior, OA projection sync producer boundary, runtime import-state producer boundary and all-scope worker fan-out producer boundary. The module is not globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- `bank_account_balance` is selected as the thirteenth non-Go read model pilot. Repository port extraction is implemented: `BankAccountBalanceReadModelRepositoryPort` owns manifest-listed scope summary/list/save methods; projection save and Bank Details accounts SQL read paths use the explicit account-balance port.
- `bank_account_balance` refresh/freshness/operation-barrier audit is analysis-closed. Refresh producer extraction is implemented: `BankAccountBalanceReadModelRefreshProducer` owns gateway-backed all-only refresh enqueue, and Application, Bank Details service injection, runtime import-state fan-out, runtime derived lifecycle fan-out and backfill enqueue route through it. Derived lifecycle executor extraction is implemented: `BankAccountBalanceDerivedLifecycleExecutor` owns response assembly. All-only scope policy is implemented at the gateway. Dedicated operation barrier regression is covered. Bank Detail port account-balance compatibility fallback is removed. Local implementation support is accounted for, but real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- No module is globally closed.
- The no-OA refresh persistence boundary is implemented: `NoOaBankBatchReadModelPersistencePort` owns public snapshot persistence delegation for the worker refresh path, and `NoOaBankBatchReadModelRefreshService.handle_runtime_event(...)` no longer directly calls broad `state_store.save_no_oa_bank_batches(...)`.
- The no-OA read model repository port boundary is implemented: `NoOaBankBatchReadModelRepositoryPort` owns no-OA list/query read model repository access, `PostgresStateStore.no_oa_bank_batch_sql_read_repository` exposes the port, and `NoOaBankBatchApplicationService.list_batches_payload(...)` no longer reads through broad `workbench_sql_read_repository`.
- The no-OA freshness/derived lifecycle audit is analysis-closed: refresh enqueue, scope policy, manifest/App Status/worker registration and frontend operation barrier evidence are locally accounted for.
- The no-OA derived lifecycle executor extraction is implemented: `NoOaBankBatchDerivedLifecycleExecutor` owns target scope selection, refresh metadata forwarding and enqueued-job accounting; `Application` only assembles the explicit enqueue dependency.
- The no-OA mutation persistence fallback quarantine is implemented: `NoOaBankBatchApplicationService.persist_mutation(...)` requires `save_no_oa_bank_batch_mutation(...)`, `ApplicationStateStore` exposes the same explicit boundary, and the service-layer broad state-store fallback is guarded from returning.
- The no-OA first local closure audit found broad `Application._persist_state(...)` still serialized `no_oa_bank_batches`; the no-OA full-state snapshot quarantine is implemented and guarded.
- The no-OA post-full-state local closure audit is complete: no remaining local implementation gap was found after deleting dead app-owned source-version/stale-reason helpers. Local support is accounted for, but real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred and the module is not globally closed.
- `go-hot-path:performance-baseline-and-admission-reconciliation` is complete as a planning slice: current local read model support is accounted for or explicitly deferred, but no Go/Fiber/Go Worker candidate has passed admission.
- `go-hot-path:workbench-compute-performance-baseline-contract` is complete as a planning slice: Workbench compute Python reference IO, candidate input/output, state/events/read model dependencies, permissions/audit assumptions, shadow forbidden writes, minimum performance evidence and rollback gates are documented.
- `go-hot-path:workbench-compute-python-reference-contract-guards` is complete as a static guard slice: local tests now guard Workbench compute Python reference state-write ownership and Go shadow/admission forbidden-write queue prerequisites.
- `go-hot-path:workbench-compute-performance-evidence-collector-contract` is complete as an implementation slice: read-only `workbench_compute_evidence` tooling now reports matching duration p95/p99, scope samples, worker heartbeat, candidate/decision counts, active generation row counts, matching-originated enqueue-to-fresh, query timing/EXPLAIN and structured configuration-missing/partial evidence status.
- `go-hot-path:workbench-compute-production-evidence-gate` is complete as a production-evidence-deferred slice: local collector execution returned structured `configuration_missing`; production SSH confirmed active workers but the deployed release lacks the collector, and a deployed-runtime read-only PostgreSQL sampling attempt could not connect. Real candidate-specific Workbench compute evidence remains unavailable.
- `planning:post-workbench-compute-evidence-gate-next-boundary-selection` is complete as a planning slice: Go admission rows were skipped because performance evidence, shadow diff and rollback proof are still missing, and `server-py:residual-route-handler-boundary-audit` was selected as the next non-Go shared-boundary audit.
- `server-py:residual-route-handler-boundary-audit` is complete as an analysis slice: residual `server.py` handler/helper surfaces were classified, Workbench was identified as the largest residual owner group, and `server-py:workbench-legacy-action-handler-quarantine-audit` was selected as the next narrow audit.
- `server-py:workbench-legacy-action-handler-quarantine-audit` is complete as an analysis slice: old `/workbench/actions/*` routes were classified as test-observed compat paths backed by `ManualReconciliationService` and `LedgerService`, modern `/api/workbench/actions/*` wrappers were classified as `WorkbenchWriteFacade` delegates, and `server-py:legacy-workbench-action-route-module-quarantine` was selected as the next narrow implementation boundary.
- `server-py:legacy-workbench-action-route-module-quarantine` is complete as an implementation slice: `LegacyWorkbenchActionRoutes` owns old `/workbench/actions/confirm|difference|exception|offline|offset` payload mapping and reconciliation/ledger calls, `Application` no longer defines the five old app-owned handlers, and modern `/api/workbench/actions/*` wrappers remain facade-backed.
- `server-py:legacy-workbench-exception-helper-dead-code-audit` is complete as an implementation slice: no-caller `_handle_legacy_workbench_exception_via_application(...)` was removed, the unused conflict import was cleaned, and the legacy Workbench action quarantine guard prevents the helper from returning.
- `server-py:modern-workbench-action-route-owner-audit` is complete as an analysis slice: modern `/api/workbench/actions/*` and `/api/workbench/exception/*` wrappers were classified by JSON/auth/freshness/timing responsibility, facade/application-service delegate, tests and target owner.
- `server-py:workbench-exception-preview-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/exception/preview` payload/error mapping while `Application` keeps HTTP dispatch, JSON parsing and response serialization.
- `server-py:workbench-exception-apply-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/exception/apply` facade delegation, actor fallback, request-id forwarding and `exception_apply` action-name mapping while `Application` keeps HTTP dispatch, JSON parsing, freshness guard and response serialization.
- `server-py:workbench-confirm-link-preview-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/actions/confirm-link/preview` facade delegation and invalid-request mapping while `Application` keeps HTTP dispatch, JSON parsing and response serialization.
- `server-py:workbench-confirm-link-submit-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/actions/confirm-link` live facade delegation while `Application` keeps HTTP dispatch, JSON parsing, freshness guard, auth context, request timing and response serialization.
- `server-py:workbench-mark-exception-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/actions/mark-exception` facade delegation while `Application` keeps HTTP dispatch, JSON parsing, freshness guard and response serialization.
- `server-py:workbench-cancel-link-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/actions/cancel-link` live facade delegation while `Application` keeps HTTP dispatch, JSON parsing, freshness guard, auth context, request timing and response serialization.
- `server-py:workbench-withdraw-link-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/actions/withdraw-link` facade delegation while `Application` keeps HTTP dispatch, JSON parsing, freshness guard, auth context and response serialization.
- `server-py:workbench-cash-special-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns cash special facade delegation while `Application` keeps HTTP dispatch, JSON parsing, freshness guard, request-id forwarding and response serialization.
- `server-py:workbench-update-bank-exception-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/actions/update-bank-exception` facade delegation while `Application` keeps HTTP dispatch, JSON parsing, freshness guard and response serialization.
- `server-py:workbench-oa-bank-exception-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/actions/oa-bank-exception` facade delegation while `Application` keeps HTTP dispatch, JSON parsing, freshness guard and response serialization.
- `server-py:workbench-personal-advance-repayment-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/actions/confirm-personal-advance-repayment` facade delegation and request-id forwarding while `Application` keeps HTTP dispatch, JSON parsing, freshness guard and response serialization.
- `server-py:workbench-cancel-exception-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/actions/cancel-exception` facade delegation while `Application` keeps HTTP dispatch, JSON parsing, freshness guard, live-workbench dispatch and response serialization.
- `server-py:workbench-ignore-row-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/actions/ignore-row` facade delegation while `Application` keeps HTTP dispatch, JSON parsing, freshness guard and response serialization.
- `server-py:workbench-unignore-row-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/actions/unignore-row` facade delegation while `Application` keeps HTTP dispatch, JSON parsing, freshness guard and response serialization.
- `server-py:modern-workbench-action-route-owner-post-extraction-audit` is complete as an analysis slice: it found one remaining modern Workbench action preview gap, `Application._handle_api_workbench_withdraw_link_preview(...)` directly delegating to `WorkbenchWriteFacade.preview_withdraw_link(...)`.
- `server-py:workbench-withdraw-link-preview-route-owner-extraction` is complete as an implementation slice: `WorkbenchActionApiRoutes` owns `/api/workbench/actions/withdraw-link/preview` facade delegation while `Application` keeps HTTP dispatch, JSON parsing and response serialization.
- `server-py:modern-workbench-action-route-owner-final-residual-audit` is complete as an analysis slice: it found no remaining app-owned direct `WorkbenchWriteFacade` action delegation in the audited modern Workbench action surface.
- `server-py:workbench-cancel-exception-live-dispatch-noop-cleanup` is complete as an implementation slice: it removed the redundant cancel-exception live-service no-op branch while preserving JSON parsing, freshness guard, route-owner delegation and response serialization.
- `server-py:modern-workbench-action-route-owner-local-closure-audit` is complete as an analysis slice: it found local closure evidence for the audited modern Workbench action route-owner surface, confirmed no direct `_workbench_write_facade().` action call sites remain in app route files, and selected row detail route ownership as the next bounded server.py slice.
- `server-py:workbench-row-detail-route-owner-audit` is complete as an analysis slice: it confirmed the row detail live/cache/SQL fallback and no-write relation boundary are locally tested, found `Application` still owns fallback orchestration, and selected row detail route-owner extraction next.
- `server-py:workbench-row-detail-route-owner-extraction` is complete as an implementation slice: it moved row detail payload/fallback orchestration behind `WorkbenchRowDetailApiRoutes` while preserving response shape, fallback order, row override behavior and production PostgreSQL fallback blocking.
- `server-py:workbench-group-detail-route-owner-audit` is complete as an analysis slice: it confirmed `WorkbenchQueryFacade.group_detail(...)` owns freshness/source-version/read-model-status proof and stale refresh enqueue behavior, found `Application._handle_api_workbench_group_detail(...)` still owns HTTP validation and response mapping, and selected group detail route-owner extraction next.
- `planning:parallel-orchestration-workflow` is complete as a planning slice: it defined controller/worker permissions, direct-dev write lease, worker file ownership, handoff format, final closure audit gate and 10 thread prompts. Worker prompts may auto-progress inside assigned workstreams, but controller owns global state and global closure.
- `planning:parallel-handoff-review-and-state-update` is complete as a planning slice: T0 consumed T1-T8 handoffs, integrated accepted worker evidence in `b60a343a`, accepted T6 as partial production-read-only evidence, and kept Go admission deferred from T7.
- `planning:post-production-baseline-module-closure-wave-selection` is complete as a planning slice: it selected T0-only read-model production evidence matrixing before any worker wave or closure claim.
- `production:read-model-production-evidence-matrix-read-only-sweep` is complete as a production-controlled slice: row245 collected a clean current runtime read-model matrix and identified historical legacy `cost`/`tax` done dirty-scope rows plus remaining browser/API/high-row/module-specific closure gaps.
- `production:read-model-scope-contract-runtime-dry-run-classification` is complete as a production-controlled slice: row246 proved the scope-contract and invalid-scope dry-runs are clean and classified legacy `cost`/`tax` rows as historical `done` dirty scopes only, with no active outbox or readiness residue.
- `planning:post-scope-contract-runtime-classification-next-boundary-selection` is complete as a planning slice: row247 selected an evidence/ownership map before any worker wave or closure claim.
- `planning:read-model-module-closure-evidence-ownership-map` is complete as a planning slice: row248 produced the controller-owned evidence/ownership map and selected a prompt-generation boundary for a four-worker read-model closure evidence wave.
- `planning:read-model-module-closure-worker-wave-1-prompts` created four worker threads, and `planning:read-model-module-closure-worker-wave-1-monitor-and-accept` accepted their handoffs as local evidence/gap maps only.
- `planning:read-model-authenticated-api-browser-smoke-runbook-selection` selected API response-shape smoke first; browser smoke remains deferred until a non-secret auth/harness path is proven.
- `production:read-model-authenticated-api-response-shape-smoke-runbook` is production-evidence-deferred because auth config is absent; no API smoke was run.
- `production:read-model-public-page-shell-smoke-runbook` is production-controlled page-shell availability evidence only; it is not authenticated API response-shape, browser hydration/data, high-row workflow or module-specific closure evidence.
- `planning:post-public-page-shell-smoke-next-boundary-selection` selected a read-only shadow-read rehearsal runbook because it can add production read-path evidence without auth secrets or mutation.
- `production:read-model-shadow-read-rehearsal-read-only-runbook` proved the tool/guard path but deferred closure evidence because the selected primary comparator is not valid for current production PostgreSQL runtime.
- `planning:post-shadow-read-rehearsal-next-boundary-selection` selected direct Workbench high-row SQL evidence because it follows the concrete Row255 timeout.
- `production:workbench-read-model-high-row-query-plan-read-only-runbook` collected aggregate/index/EXPLAIN evidence only; it does not prove authenticated API, browser hydration/data, export/detail or module closure.
- `planning:post-workbench-high-row-query-plan-next-boundary-selection` selected API classification next. It is not final authenticated API closure.
- `production:read-model-unauthenticated-api-status-shape-classification-runbook` proved public API probes are uniformly auth-gated, not that API response shapes are closed.
- The next pending boundary is `planning:post-unauthenticated-api-classification-next-boundary-selection`.
- Go/Fiber/Go Worker implementation remains blocked until candidate-specific performance evidence, shadow-run proof, rollback gates and admission review pass.

Completion semantics:
- analysis-closed closes only analysis/inventory work.
- contract-guard-closed closes only manifest/contract guard work.
- static-guard-closed closes only static guard work.
- regression-guard-closed closes only regression guard work.
- route-guard-closed closes only route guard work.
- inventory-guard-closed closes only inventory guard work.
- implementation-closed closes only one narrow implementation slice.
- planning-closed closes only planning/state/prompt work.
- production-evidence-deferred records a real environment evidence gap; it is not a silent pass.
- None of the above means a module is fully modularized.

Full module closure requires:
- IO contract.
- Public/internal boundary.
- Canonical fact owner.
- Shared fact source.
- Read model contract.
- Freshness proof.
- Force refresh contract.
- Operation barrier contract.
- Legacy removal or compat-only quarantine.
- Permission contract.
- Audit contract.
- Test contract.
- Docs updates.
- Environment evidence or explicit defer status.

Autonomous loop:
0. Reconcile completion truth from commits before selecting work.
   - Before trusting state files, build a commit-backed evidence ledger from git logs, commit diffs, changed files, worker handoffs, controller acceptance commits and recorded verification.
   - Do not calculate completion percentages from memory, `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, roadmap checkbox counts or prior summaries alone.
   - Classify queue rows and roadmap criteria as `commit-proven`, `commit-partial`, `docs-only`, `deferred`, `unproven`, or `stale-state`.
   - Compute roadmap completion percentage, queue evidence percentage by status, module local implementation percentage, module global closure percentage, production evidence percentage and Go admission percentage with numerator, denominator, criteria and evidence path.
   - Write `.planning/refactors/modular-io-boundaries/analysis/commit-backed-state-reconciliation-<date>.md`.
   - Update stale `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and this prompt before selecting the next implementation or worker wave.
1. Reconcile planning state before selecting work.
   - Read ROADMAP.md, refactor README, modular README, 00-REQUIREMENTS.md, 03-REFACTOR-STATE-MACHINE.md, 04-IMPLEMENTATION-ROADMAP.md, MODULE-QUEUE.md, STATE.md, JOURNAL.md, and NEXT-PROMPT.md.
   - If they disagree on current state, completed boundary, next boundary, status labels, module closure meaning, or completion metrics, execute a planning:state-reconciliation-* slice first.
2. Select exactly one boundary.
   - Pick the first MODULE-QUEUE.md item whose Status is pending.
   - Skip blocked-by-prerequisite items.
   - Do not select Go/Fiber/Go Worker while earlier modular IO/read model implementation-pending or implementation-gap-open work remains.
   - If the selected boundary is too broad, split the queue and execute the first smaller boundary.
3. Analyze before edits.
   - Read target module docs under docs/modules/<module>/.
   - Read relevant architecture/dev/operations/product docs.
   - Read the global and module state-machine files.
   - Use CodeGraph first for structural lookup and impact.
   - Use rg for literal text, route paths, test names, env keys, and docs references.
   - Produce or update an analysis file under .planning/refactors/modular-io-boundaries/analysis/.
   - Analysis must record previous state, selected boundary, transition guard, expected evidence, success transition, defer/block transition, affected docs, seven-category test applicability, and state-machine impact.
4. Implement narrowly or close a planning slice.
   - Implement only the selected boundary.
   - Keep server.py thin: route mapping, dependency wiring, session/auth resolution, and HTTP response mapping only.
   - Keep business rules in services.
   - Keep SQL/table knowledge in repositories.
   - Inject explicit dependencies; do not pass the whole Application into services.
   - Do not change business semantics, amount rules, status transitions, permissions, audit meaning, API shape, or UI behavior unless explicitly required and tested.
   - Do not implement broad file splitting for line-count optics.
5. Remove or quarantine legacy paths.
   - Classify every touched old route/service/repository/read model/frontend API/worker path as removed, quarantined, compat-only, or blocked-by-human-gate.
   - Default to removal when tests and call graph prove it is unused.
   - compat-only paths must have owner, caller list, deletion condition, forbidden write list, and regression tests.
   - Old paths must not write canonical facts, dirty scopes, outbox events, read model readiness, cache, App Status, or new authoritative outputs.
6. Enforce read model boundaries.
   - Canonical facts have one owner.
   - Derived/read model/cache data cannot become the source of truth.
   - Non-transactional read model refresh requests go through ReadModelRefreshGateway and scope policy registry.
   - Transactional writers must maintain equivalent scope/outbox contract inside the business transaction.
   - Business services must not directly SQL write job.outbox_events or job.read_model_dirty_scopes.
   - Redis may cache only payloads that passed the fresh gate.
   - RabbitMQ is wakeup/transport only.
   - No page may display stale payload as fresh.
   - Writes affecting cross-page consistency must expose affected scopes/months/version/job and use operation barrier or registered read boundary before claiming sync completion.
7. Test and verify.
   - Evaluate all seven test categories for every implementation slice:
     1. Business core unit tests.
     2. Service-layer tests.
     3. API contract tests.
     4. Read model/cache/background job tests.
     5. Frontend component and interaction tests.
     6. End-to-end business-flow integration tests.
     7. Existing feature regression tests.
   - Add or update tests for every applicable category.
   - Document non-applicable categories and why.
   - Run targeted tests, app checks, docs verification, and git diff --check as applicable.
8. Update state machine and accounting before commit.
   - Always update STATE.md, MODULE-QUEUE.md, JOURNAL.md, and NEXT-PROMPT.md.
   - If global workflow state definitions changed, update 03-REFACTOR-STATE-MACHINE.md.
   - If module state definitions changed, update affected docs/modules/<module>/state-machine.md.
   - If definitions did not change, analysis must explicitly record reviewed files and why definitions are unchanged.
9. Commit and push.
   - Review git diff.
   - Stage only files from the completed slice.
   - Commit with a focused message.
   - Push to origin/dev.
10. Continue immediately to the next safe boundary unless a hard stop gate is hit.

Immediate next boundary:
Start with `planning:read-model-browser-data-harness-coverage-map`.

Commit-backed baseline:
- `planning:commit-backed-state-reconciliation` is complete in `analysis/commit-backed-state-reconciliation-2026-06-25.md`.
- Use that report as the current progress baseline before assigning workers.
- Do not claim module/global/production/Go closure from raw queue counts; the report currently proves no product module has `Module Closure = closed`, production evidence closure is 0/17 and Go admission is 0/5.

- Read `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`, `analysis/read-model-authenticated-api-browser-smoke-runbook-selection-2026-06-25.md`, `analysis/production-read-model-public-page-shell-smoke-runbook-2026-06-25.md`, `analysis/planning-post-public-page-shell-smoke-next-boundary-selection-2026-06-25.md`, `analysis/production-read-model-shadow-read-rehearsal-read-only-runbook-2026-06-25.md`, `analysis/planning-post-shadow-read-rehearsal-next-boundary-selection-2026-06-25.md`, `analysis/production-workbench-read-model-high-row-query-plan-read-only-runbook-2026-06-25.md`, `analysis/planning-post-workbench-high-row-query-plan-next-boundary-selection-2026-06-25.md`, `analysis/production-read-model-unauthenticated-api-status-shape-classification-runbook-2026-06-25.md`, `analysis/planning-post-unauthenticated-api-classification-next-boundary-selection-2026-06-25.md`, `analysis/planning-read-model-internal-api-contract-harness-design-2026-06-25.md`, `analysis/contract-read-model-internal-api-contract-harness-implementation-2026-06-25.md`, `analysis/planning-post-internal-api-contract-harness-next-boundary-selection-2026-06-25.md`, `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `12-PARALLEL-ORCHESTRATION.md`.
- Produce the read-model browser data harness coverage map and recommend the next smallest executable evidence boundary.
- Use CodeGraph before any implementation-oriented decision about `Application`, auth/session helpers, route-owner classes or existing tests.
- Do not run API probes until a non-secret auth path is configured.
- Do not introduce a Flask test client; this backend uses `Application`, route-owner classes and `ThreadingHTTPServer` / `BaseHTTPRequestHandler`.
- Do not add broad payload snapshots or fixture data just to force every route through one harness.
- Do not run full e2e smoke until the coverage map identifies the target and verification value.
- Do not select payload rows, full row data, secrets, env values, DSNs, tokens or cookies.
- Do not run production `--apply`, deploy, restart, requeue, repair, replay workers or mutate runtime state.
- Do not claim module/global closure from row245, row246, row248 or worker handoffs alone.
- Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and this master prompt with the result and next boundary.

Parallel execution:
- If the user wants multiple Codex threads, do not paste this master prompt into every thread.
- Use `12-PARALLEL-ORCHESTRATION.md` and `prompts/05-parallel-thread-prompts.md`.
- Start exactly one T0 controller and bounded worker prompts.
- Controller-only files must remain controller-owned.
- Workers may auto-progress inside assigned scopes, then write handoffs for controller integration.

Do not resume old `server-py:workbench-group-detail-route-owner-extraction` instructions from this prompt. That boundary is already locally implementation-closed and accepted by the controller. Select any future server route-owner work only after commit-backed reconciliation and next-boundary selection.

Go/Fiber/Go Worker rules:
- Do not implement Go/Fiber/Go Worker unless the candidate is listed in 11-GO-HOT-PATH-CARVE-OUT.md and admission gates pass.
- Do not run Go admission while earlier modular IO/read model implementation-pending or implementation-gap-open boundaries remain.
- Fiber is optional internal API for selected compute/read services; it is not a replacement for read models, workers, durable queue, freshness proof, permissions, audit, or canonical write services.
- Long-running work must not run inside a Fiber request handler.
- Go Worker target remains Go Worker + PostgreSQL dual queue.
- PostgreSQL durable queue remains authoritative.
- RabbitMQ can be future wakeup/transport only.

Production and SSH rules:
- SSH aliases may be used for read-only production evidence if already configured.
- Do not read or print secrets, DSNs, tokens, cookies, env secret values, private keys, or sensitive payloads.
- Do not perform production writes, DB writes, queue mutation, readiness mutation, worker replay/consume, systemd mutation, file mutation, or OA mutation.
- If production write or secret access is required, record needs-human-production-gate and continue another independent module when safe.
- Missing production DB/worker evidence is a soft gate. Record production-evidence-deferred and never claim real production closure for that evidence.
- The plan must not depend on local PGSQL_URL or a staging database.

Hard stop gates:
- Not on branch dev.
- Unrelated/user dirty worktree files.
- Merge conflict from origin/main.
- Need production write, secret, DB mutation, worker replay/consume, queue mutation, or destructive operation.
- Tests reveal a bug that cannot be fixed within the selected slice.
- Boundary is too broad and cannot be safely split without human choice.
- Planning sources conflict and cannot be reconciled from documented facts.

Final reporting if stopped:
- State the last completed boundary.
- State the current queue item.
- State exact blocker or hard stop.
- State tests/verification run.
- State files changed.
- Do not claim full module or global closure unless the closure requirements above are satisfied.
```
