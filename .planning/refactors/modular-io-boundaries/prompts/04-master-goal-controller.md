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
- Last completed boundary: read-models:no-oa-bank-batch-refresh-persistence-boundary-extraction.
- Last status: production-evidence-deferred.
- Queue semantics are corrected: Status is slice status; Module Closure is broader module closure.
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
- Remaining later non-Go read model candidates include `search` and `bank_account_balance`.
- No module is globally closed.
- The no-OA refresh persistence boundary is implemented: `NoOaBankBatchReadModelPersistencePort` owns public snapshot persistence delegation for the worker refresh path, and `NoOaBankBatchReadModelRefreshService.handle_runtime_event(...)` no longer directly calls broad `state_store.save_no_oa_bank_batches(...)`.
- The next pending boundary is read-models:no-oa-bank-batch-read-model-repository-port-extraction.
- Go/Fiber/Go Worker candidates remain blocked-by-prerequisite and must not be selected next.

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
Start with read-models:no-oa-bank-batch-read-model-repository-port-extraction unless planning-state reconciliation finds an inconsistency first.

For read-models:no-oa-bank-batch-read-model-repository-port-extraction:
- Read `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-refresh-persistence-boundary-extraction.md`, `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-repository-state-store-boundary-audit.md`, `docs/modules/read-models/README.md`, `docs/modules/read-models/implementation-notes.md`, `docs/modules/read-models/tests.md`, `docs/modules/no-oa-bank-batches/README.md`, `docs/modules/no-oa-bank-batches/state-machine.md`, `docs/modules/no-oa-bank-batches/implementation-notes.md`, `docs/modules/no-oa-bank-batches/tests.md`, `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`, `backend/src/fin_ops_platform/services/read_model_manifest.py`, `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`, and relevant no-OA tests.
- Use CodeGraph for structural lookup before editing.
- Add a narrow `NoOaBankBatchReadModelRepositoryPort` or local-pattern equivalent for manifest-listed `list_no_oa_bank_batch_rows(...)`.
- Wire `NoOaBankBatchApplicationService` list/query construction through the narrow no-OA repository port instead of broad `workbench_sql_read_repository`.
- Preserve list payload shape, missing/stale/fresh/unavailable status behavior, refresh enqueue behavior, pagination behavior and public lifecycle filtering.
- Preserve `PostgresReadModelRepository.list_no_oa_bank_batch_rows(...)` as SQL owner; do not duplicate SQL.
- Add a port guard proving unrelated read model methods are not exposed.
- Update manifest `repository_owner` only if the port becomes the new owner name.
- Do not implement Go/Fiber/Go Worker.
- Do not change business rules, API shapes, worker event names, queue schema, Redis/cache behavior, permissions, audit meaning or frontend behavior.
- Update STATE.md, MODULE-QUEUE.md, JOURNAL.md, NEXT-PROMPT.md, prompts/04-master-goal-controller.md, and affected module docs/tests as applicable.
- Run targeted static evidence collection, app check, no-OA target tests where applicable, docs verification and diff checks.
- Commit and push to origin/dev.
- Continue to the selected first implementation boundary if verification passes.

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
