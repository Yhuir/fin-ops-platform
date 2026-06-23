# Prompt: Modular IO Refactor Master Goal Controller

Copy the full prompt below into Codex to start or resume the autonomous run.

```text
Fully close the modular IO boundary refactor for /Users/yu/Desktop/fin-ops-platform.

Act as the main controller. Use GSD discipline and a closed-loop workflow:

1. Review and analyze current state.
2. Select exactly one bounded boundary.
3. Execute that boundary.
4. Review the diff and verification.
5. Update state machine, queue, journal and next prompt.
6. Commit and push the verified slice to origin/dev.
7. Generate the next bounded prompt from the updated state and execute it immediately.

Continue until the modular IO refactor reaches closure or a hard stop gate is hit. I may be away. Do not wait for me unless continuing would violate a hard stop gate.

Repository:
- Work only in /Users/yu/Desktop/fin-ops-platform.
- Use the main repository directory directly. Do not create a new worktree.
- Use branch dev.
- Do not work on main.
- Do not commit to main.
- Do not push to main.
- Commit and push each passing small boundary slice to origin/dev.
- Never force-push.
- Never rebase dev automatically.
- Never reset dev automatically.
- Never delete branches.
- Never run destructive local operations such as git reset --hard or git checkout -- unless the user explicitly asks for that exact operation.

Preflight:
1. Run:
   - pwd
   - git status --short --branch
   - git remote -v
2. Confirm the repository is /Users/yu/Desktop/fin-ops-platform.
3. Confirm current branch is dev before implementation commits.
4. Fetch origin with prune.
5. Pull origin/dev with --ff-only when the working tree is clean.
6. Merge origin/main into dev only when the working tree is clean and the merge is conflict-free.
7. If merging origin/main into dev conflicts, stop and record blocked-hard-stop/dev-main-alignment-conflict. Do not auto-resolve finance, read model, worker, permission, migration, lockfile or generated-file conflicts.

Dirty worktree handling:
- If the worktree is clean, proceed normally.
- If dirty files exist, inspect ownership carefully before any write.
- If dirty files look like user work or unrelated work, stop before staging, formatting, reverting, stashing, committing or overwriting them.
- If dirty files are clearly from the current autonomous slice, continue that slice; do not discard them.
- Do not use destructive cleanup. Preserve user changes.

Required reading before any edits:
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

Planning source rule:
This refactor has multiple planning sources. Read and report them separately; never collapse them into one unqualified percentage.
- .planning/ROADMAP.md is the root page-analysis roadmap.
- .planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md is the modular IO phase roadmap.
- .planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md is the executable autonomous boundary queue.
- .planning/refactors/modular-io-boundaries/autonomous/STATE.md, JOURNAL.md and NEXT-PROMPT.md are execution accounting.
- MODULE-QUEUE.md Status is slice status, not module closure.
- MODULE-QUEUE.md Module Closure is the implementation closure signal.

Current corrected state:
- Last completed boundary is expected to be read-models:bank-detail-pilot-verification-and-template-revision.
- Last status is expected to be analysis-closed.
- First read model implementation pilot is expected to be bank_detail.
- Next executable boundary is expected to be read-models:bank-detail-server-helper-quarantine.
- The bank_detail pilot is not module-closed. Remaining server.py scope/cache/refresh/callback helper paths must be classified, migrated, removed or quarantined before broader rollout or Go admission.
- Go hot-path candidates are expected to be blocked-by-prerequisite.
- Do not select GoHotPath next unless the queue has been legitimately updated after the bank_detail/read model implementation prerequisites are closed.

Non-negotiable completion semantics:
- analysis-closed means analysis/inventory slice closed only.
- contract-guard-closed means manifest/contract guard slice closed only.
- static-guard-closed means static guard slice closed only.
- regression-guard-closed means regression guard slice closed only.
- route-guard-closed means route guard slice closed only.
- inventory-guard-closed means inventory guard slice closed only.
- implementation-closed means one narrow implementation slice closed only.
- planning-closed means planning/state/prompt slice closed only.
- None of the labels above means a module is fully modularized.
- Full module closure requires the module completion definition in 00-REQUIREMENTS.md and 03-REFACTOR-STATE-MACHINE.md: IO contract, public/internal boundary, canonical facts, read model freshness, force refresh, operation barrier, legacy removal/quarantine, permissions, audit, tests, docs and environment evidence/defer status.

Boundary selection priority:
1. If .planning/ROADMAP.md, refactors README, modular README, 00-REQUIREMENTS.md, 03-REFACTOR-STATE-MACHINE.md, 04-IMPLEMENTATION-ROADMAP.md, STATE.md, MODULE-QUEUE.md, JOURNAL.md or NEXT-PROMPT.md disagree on source hierarchy, current state, next boundary, status labels, module closure meaning or completion metric source, select a planning:state-reconciliation-* boundary first.
2. Otherwise pick the first boundary in MODULE-QUEUE.md whose Status is pending.
3. Skip blocked-by-prerequisite items.
4. Do not select Go hot-path candidates while any earlier pending, implementation-pending or implementation-gap-open modular IO boundary exists.
5. If the selected boundary is too broad, split it by updating MODULE-QUEUE.md and immediately execute the first smaller boundary.

Immediate next boundary:
Start with read-models:bank-detail-server-helper-quarantine unless a planning-state inconsistency is found first.

For read-models:bank-detail-server-helper-quarantine:
- Read:
  - .planning/refactors/modular-io-boundaries/analysis/completion-semantics-and-queue-reclassification.md
  - .planning/refactors/modular-io-boundaries/analysis/read-model-modularization-pre-analysis.md
  - .planning/refactors/modular-io-boundaries/analysis/read-model-manifest-and-boundary-inventory.md
  - .planning/refactors/modular-io-boundaries/analysis/read-model-query-gateway-contract-and-status-parity.md
  - .planning/refactors/modular-io-boundaries/analysis/read-model-refresh-gateway-force-refresh-and-operation-barrier.md
  - .planning/refactors/modular-io-boundaries/analysis/read-model-repository-port-and-sql-owner-split-plan.md
  - .planning/refactors/modular-io-boundaries/analysis/read-model-pilot-gap-audit-and-contract-selection.md
  - .planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-repository-port-extraction.md
  - .planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-refresh-freshness-operation-barrier.md
  - .planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-legacy-contamination-removal.md
  - .planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-pilot-verification-and-template-revision.md
  - docs/modules/read-models/README.md
  - docs/modules/read-models/state-machine.md
  - docs/modules/read-models/tests.md
  - docs/modules/bank-details/README.md
  - docs/modules/bank-details/state-machine.md
  - docs/modules/bank-details/tests.md
  - docs/modules/runtime-workers/README.md
  - docs/modules/runtime-workers/state-machine.md
- Use CodeGraph first for structural lookup of bank_detail remaining helpers, callers, callees, traces and impact.
- Use rg for literal text, route paths, env keys, docs references and test names.
- Keep the implementation boundary narrow:
  - Classify every remaining server.py bank_detail scope/cache/refresh/callback helper by owner, caller list, allowed behavior, forbidden writes, deletion condition and test evidence.
  - Remove or migrate only the smallest helper whose call graph and tests prove it is safe.
  - Register retained paths as compat-only, gateway-backed wrapper, dependency-factory-only or blocked-by-human-production-gate.
  - Preserve API response shape for accounts, transactions and export.
  - Do not add broad new implementation unless classification exposes a concrete small missing boundary and the queue is split first.
  - Keep regression coverage for repository port/query boundary, force refresh gateway/scope-policy usage and exact month operation barrier targets.
  - Do not split all of postgres_repositories/read_models.py.
  - Do not migrate workbench_relation, pending_invoice or oa_pending_payment.
  - Do not implement Go/Fiber/Go Worker.
- Produce or update an analysis file for the implementation slice under .planning/refactors/modular-io-boundaries/analysis/.
- Update MODULE-QUEUE.md so the next pending item remains a concrete implementation boundary, not Go admission.
- Update STATE.md, JOURNAL.md and NEXT-PROMPT.md.
- Run targeted tests, docs verification and diff checks.
- Commit and push to origin/dev if verification passes.
- Continue immediately to the next pending implementation boundary.

Per-boundary loop:

1. Analyze
   - Read current STATE.md, JOURNAL.md, MODULE-QUEUE.md and NEXT-PROMPT.md.
   - Read target module docs under docs/modules/<module>/, including README.md, state-machine.md, tests.md, e2e-spec.md, e2e-coverage.md and implementation-notes.md when present.
   - Read relevant architecture/dev/operations/product docs.
   - Read 03-REFACTOR-STATE-MACHINE.md before selecting implementation changes.
   - Read every affected docs/modules/<module>/state-machine.md before selecting implementation changes.
   - Use CodeGraph first for structural questions.
   - Use rg for literal text and file discovery.
   - Produce or update an analysis file under .planning/refactors/modular-io-boundaries/analysis/.
   - Fill impact analysis from 05-IMPACT-AND-TEST-GATES.md before editing code.
   - Analysis must name previous state, selected boundary, transition guard, expected evidence, success transition, defer/block transition and files to update.

2. Contract
   - Fill or update the relevant module IO contract using 02-MODULE-IO-CONTRACT-TEMPLATE.md.
   - Every module boundary must define:
     - inputs
     - outputs
     - states
     - events
     - read model contract
     - force refresh contract
     - operation barrier contract
     - canonical facts
     - shared fact owner
     - permissions
     - audit records
     - public surface
     - internal-only surface
     - allowed dependencies
     - forbidden dependencies
     - legacy retirement/quarantine contract
     - test contract
     - docs impact
   - For read model boundaries, define read_model_key, scope_type, scope_key, partition key, affected scope calculation, freshness proof, parent/aggregate semantics, all-scope semantics, builder owner, full rebuild fallback, source/schema version and operation barrier target.

3. Tests first where practical
   - Evaluate all seven test categories:
     1. Business core unit tests.
     2. Service-layer tests.
     3. API contract tests.
     4. Read model/cache/background job tests.
     5. Frontend component and interaction tests.
     6. End-to-end business-flow integration tests.
     7. Existing feature regression tests.
   - Add or update tests for every applicable category.
   - If a category is not applicable, document why in the analysis and final summary.
   - For read model changes, include stale/refreshing/fresh/failed behavior, dirty scope, outbox, readiness, operation barrier, force refresh, scope normalization, dedupe/idempotency, cache gating and cross-page freshness regressions where applicable.
   - For legacy retirement, include call graph/import/API/frontend route guards proving new code does not call old internals and old paths cannot write new facts or refresh state.

4. Implement narrowly
   - Implement only the selected boundary.
   - Prefer existing local patterns and helpers.
   - Keep server.py thin: route mapping, dependency wiring and HTTP mapping only.
   - Keep business rules in services.
   - Keep SQL/table knowledge in repositories.
   - Inject explicit service dependencies; do not pass the whole Application into services.
   - Services must not read HTTP cookies/headers, import app.auth or construct HTTP responses.
   - Workers must not depend on Application, app.server, app.auth, HTTP responses, cookies, headers, request/session or route modules.
   - Do not change business semantics, amount rules, status transitions, permissions, audit meaning, API shape or UI behavior unless explicitly required and tested.
   - Do not do broad file splitting for line-count optics.

5. Remove or quarantine legacy paths
   - For every old route/service/repository/read model/frontend API/worker path touched or replaced, classify it as removed, quarantined, compat-only or blocked-by-human-gate.
   - Default to removal when tests and call graph prove it is unused.
   - compat-only paths must have owner, caller list, deletion condition, forbidden write list and regression tests.
   - Old paths must not write canonical facts, dirty scopes, outbox events, read model readiness, cache, App Status or new authoritative outputs.
   - New paths must not call old internals or legacy fallbacks unless the contract explicitly registers a temporary compat-only adapter.

6. Enforce shared facts and read model boundaries
   - Canonical facts have one owner.
   - Derived/read model/cache data cannot become the source of truth.
   - All non-transactional read model refresh requests go through ReadModelRefreshGateway and the scope policy registry.
   - Transactional writers must maintain equivalent scope/outbox contract inside the business transaction.
   - Business services must not directly SQL write job.outbox_events or job.read_model_dirty_scopes.
   - Redis may cache only payloads that passed the fresh gate.
   - RabbitMQ is wakeup/transport only; it is never the read model, worker, job or freshness source of truth.
   - No page may display stale payload as fresh.
   - Writes affecting cross-page consistency must return or expose affected scopes/months/version/job, then the frontend/API must use operation barrier or registered read boundary before claiming sync is complete.

7. Go/Fiber/Go Worker rules
   - Do not implement Go/Fiber/Go Worker unless the candidate is listed in 11-GO-HOT-PATH-CARVE-OUT.md and admission gates pass.
   - Do not even run Go admission while earlier implementation-pending or implementation-gap-open modular IO boundaries remain, unless the queue was explicitly reclassified with evidence.
   - Fiber is optional internal API for selected compute/read services; it is not a replacement for read models, workers, durable queue, freshness proof, permissions, audit or canonical write services.
   - Long-running work must not run inside a Fiber request handler.
   - Python and Go workers must not both ack, publish or write readiness for the same authoritative event/scope.
   - Shadow Go output cannot ack outbox, mark dirty scope done, publish generation, write readiness or update cache.
   - If admission fails, record go-candidate-deferred and continue with Python boundary hardening or the next module.

8. State-machine update gate
   - This gate is mandatory before every commit.
   - Decide explicitly whether the slice changes any global workflow state, transition, guard, stop/defer condition, completion criterion or queue status semantics.
   - Decide explicitly whether the slice changes any module business/UI/read model/worker/operation-barrier/force-refresh/permission/legacy-retirement state.
   - If global workflow definition changed, update 03-REFACTOR-STATE-MACHINE.md in the same slice.
   - If module state definition changed, update every affected docs/modules/<module>/state-machine.md in the same slice.
   - If definitions did not change, record this explicitly in the analysis file with reviewed files and reason.
   - Update progress/accounting state separately:
     - autonomous/STATE.md
     - autonomous/MODULE-QUEUE.md
     - autonomous/JOURNAL.md
     - autonomous/NEXT-PROMPT.md
   - The commit is invalid if it updates only NEXT-PROMPT.md without matching STATE.md, MODULE-QUEUE.md, JOURNAL.md and analysis evidence.

9. Verify
   - Run the smallest sufficient verification for the changed slice.
   - Prefer documented commands and existing tests.
   - Typical commands include:
     - bash scripts/verify.sh docs
     - git diff --check
     - PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
     - PYTHONPATH=backend/src python3 -m unittest <targeted-tests> -v
     - cd web && npm test -- <targeted-tests>
     - cd web && npm run build
   - If a command is unavailable or too broad for the slice, document exactly why and run the closest targeted substitute.
   - Do not require local PGSQL_URL.
   - Do not require staging DB.
   - Use fake/stub repository, queue, read model gateway, API contract, frontend mock, static checks and production read-only SSH checks when useful.

10. Production and SSH policy
   - No local PGSQL_URL is available.
   - No staging database is available.
   - Do not ask me for PostgreSQL URLs, staging DBs, SSH passwords, database passwords, tokens, cookies or private secrets.
   - ssh finops-prod-root is available as root with key login for privileged read-only checks.
   - Use production SSH only for non-secret read-only checks such as service status, file existence, health endpoints, logs without secrets and runtime status that does not expose credentials.
   - Do not read or print secrets, DSNs, tokens, cookies, env secret values, private keys or sensitive payloads.
   - Do not perform production writes, DB writes, queue mutation, readiness mutation, worker replay/consume, systemd mutation, file mutation or OA mutation.
   - If production write or secret access is required, record needs-human-production-gate and continue to another independent module when safe.
   - Missing production DB/worker evidence is a soft gate. Record production-evidence-deferred; never claim real production closure for that evidence.

11. Review, commit and push
   - Inspect git diff before staging.
   - Confirm every changed file belongs to the selected slice or required docs/state.
   - Confirm no unrelated user changes are staged.
   - Scan changed files for secrets.
   - Confirm old-path removal/quarantine is documented and tested.
   - Confirm shared facts and read model refresh cannot be bypassed.
   - Confirm docs impact is handled.
   - Confirm state-machine accounting is handled.
   - Stage only files for the completed slice.
   - Commit with a scoped message.
   - Push only to origin dev.
   - After push, confirm branch status is clean and up to date with origin/dev.

12. Continue
   - Generate or update autonomous/NEXT-PROMPT.md after every closed/deferred/blocked slice.
   - Treat NEXT-PROMPT.md as resume state, but do not stop merely because it was updated.
   - Immediately execute the next prompt unless the current run hit a hard stop gate or no safe module remains.

Hard stop gates:
Stop immediately only when continuing would be unsafe:
- Cannot enter safe direct-dev state.
- Current branch is main.
- Git state is ambiguous enough that committing could include user changes.
- origin/dev cannot fast-forward.
- origin/main merge conflicts into dev.
- A secret is required.
- A production write is required.
- A destructive local operation would be required.
- Business semantics are ambiguous enough to risk finance rules, permissions, amounts, state transitions or audit meaning.
- No independent module remains.
- Go/Fiber migration would violate 11-GO-HOT-PATH-CARVE-OUT.md.

Progress reporting:
Every progress report must separately show:
- Root page-analysis roadmap progress from .planning/ROADMAP.md.
- Modular IO phase roadmap progress from 04-IMPLEMENTATION-ROADMAP.md.
- Autonomous boundary queue slice progress from MODULE-QUEUE.md Status.
- Module implementation closure progress from MODULE-QUEUE.md Module Closure and 04-IMPLEMENTATION-ROADMAP.md Phase 1-7.

Do not report a single unqualified percentage for "the whole refactor plan".

Final report when the full run stops or reaches closure:
- Branch and latest dev commit.
- Slice statuses completed.
- Module closure statuses completed.
- Modules production-evidence-deferred and exact missing evidence.
- Modules go-candidate-deferred or blocked-by-prerequisite and exact gate.
- Modules needs-human-production-gate and exact required approval.
- Legacy paths removed.
- Legacy paths retained as compat-only with deletion condition.
- Read model boundaries completed, including force refresh and freshness proof coverage.
- Go/Fiber/Go Worker candidates admitted, deferred, blocked or not started.
- Tests added/changed and the seven test categories they cover.
- Verification commands run.
- Verification not run and why.
- Production read-only evidence collected.
- Remaining risks.
- Confirmation that no commit was pushed to main and every pushed commit went to origin/dev.
```
