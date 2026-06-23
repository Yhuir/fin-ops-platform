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
- Last completed boundary: workbench-relations:server-oa-invoice-offset-relation-read-port-extraction.
- Last status: implementation-closed.
- Queue semantics are corrected: Status is slice status; Module Closure is broader module closure.
- bank_detail completed the current local implementation support slices through the collaborator audit, but bank_detail is not full module closed.
- bank_detail production PostgreSQL/worker/App Status/high-row/browser evidence remains unavailable and deferred.
- workbench_relation is selected as the next read model implementation pilot.
- WorkbenchRelationReadModelRepositoryPort is now wired into app/worker/projection builder relation read-model paths.
- WorkbenchRelationDerivedLifecycleExecutor now owns derived lifecycle refresh enqueue payload behavior.
- Transaction pair relation persist now uses `PostgresWorkbenchRelationRepository`.
- WorkbenchRelationCommandRepositoryAdapter now owns command repository snapshot merge/apply behavior.
- WorkbenchPairRelationPersistService now owns non-transactional pair relation persist/schedule/background/timing behavior.
- WorkbenchPairRelationRollbackRestoreService now owns pair relation snapshot rollback restore behavior.
- WorkbenchExceptionRollbackRestoreService now owns exception/pair/candidate/override rollback restore behavior.
- Batch-accounting restore callback now delegates to WorkbenchPairRelationRollbackRestoreService in in-memory mode.
- No-OA normal relation writes are command-service gated and active reads mostly use `relation_facade`.
- No-OA application snapshot/version/persist/rollback pair service usage now goes through `NoOaPairRelationSnapshotPort`.
- No-OA domain repair/read active relation reads go through `NoOaRelationRepairReadPort`.
- WorkbenchWriteFacade pair service call sites are classified.
- WorkbenchWriteFacade active relation reads, withdraw preview fallback and pair snapshots now go through `WorkbenchWriteRelationReadSnapshotPort`.
- Core confirm/cancel writes are already command-service gated by existing guards.
- WorkbenchWriteFacade cash special metadata mutation now goes through `WorkbenchWriteRelationSpecialMetadataMutationPort`.
- WorkbenchWriteFacade no longer stores or accepts broad `pair_relation_service`.
- Workbench matching/orchestrator active relation reads now go through `WorkbenchMatchingRelationReadPort` backed by existing command-boundary reads.
- Workbench payload/live-row active relation reads now go through `WorkbenchPayloadRelationReadPort`.
- Workbench/no-OA source-version relation snapshot reads now go through `WorkbenchRelationSourceVersionProvider`.
- OA invoice offset sync active relation reads now go through `WorkbenchOaInvoiceOffsetRelationReadPort`.
- Remaining write-adjacent reads include OA attachment context repair, confirm-link context expansion and auto-pair conflict checks.
- The next pending boundary is workbench-relations:server-oa-attachment-repair-relation-read-port-extraction.
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
Start with workbench-relations:server-auto-pair-conflict-relation-read-port-extraction unless planning-state reconciliation finds an inconsistency first.

For workbench-relations:server-auto-pair-conflict-relation-read-port-extraction:
- Read `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-confirm-link-context-relation-read-port-extraction.md`.
- Read `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-repair-precondition-relation-read-port-audit.md`.
- Read `docs/modules/workbench-relations/README.md`, `state-machine.md`, `tests.md`, and `implementation-notes.md`.
- Inspect `backend/src/fin_ops_platform/app/server.py`, `tests/test_workbench_v2_api.py`, and `tests/test_platform_runtime_boundary_guards.py`.
- Use CodeGraph/text search for `_auto_pair_conflicts_with_manual_relation`, `get_active_relation_by_row_id`, and manual relation conflict checks.
- Add or reuse an explicit relation read port for auto-pair conflict precondition relation reads.
- Move `_auto_pair_conflicts_with_manual_relation(...)` direct relation read behind that port.
- Preserve manual relation conflict semantics and auto-pair behavior.
- Add static guard coverage for this method.
- Do not change relation writes, read model freshness, dirty scopes, operation barriers, API response shape or frontend behavior.
- Do not declare `workbench_relation` module closed.
- Do not implement Go/Fiber/Go Worker.
- Produce an analysis/accounting file.
- Update MODULE-QUEUE.md, STATE.md, JOURNAL.md, and NEXT-PROMPT.md.
- Run focused auto-pair conflict/static guard tests, app check, docs verification and diff checks as applicable.
- Commit and push to origin/dev.
- Continue to the next pending boundary if verification passes.

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
