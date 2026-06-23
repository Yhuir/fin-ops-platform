# Prompt: Modular IO Refactor Master Goal Controller

Copy the full prompt below into Codex to start or resume the autonomous run.

```text
You are Codex working in /Users/yu/Desktop/fin-ops-platform.

Objective:
Autonomously continue the production-grade modular IO boundary refactor until the refactor reaches true closure or a hard stop gate is hit.

Use GSD discipline. This is a closed-loop controller, not a one-shot task.

Core workflow for every slice:
1. Review and analyze current planning/code state.
2. Reconcile STATE.md, MODULE-QUEUE.md, JOURNAL.md, NEXT-PROMPT.md and state-machine semantics.
3. If planning files disagree, execute a planning:state-reconciliation-* slice first.
4. Otherwise select exactly one bounded boundary from the queue.
5. Analyze target docs/code and write or update an analysis file.
6. Implement only that boundary, or quarantine it if implementation is too broad.
7. Review diff and verification.
8. Update state machine/accounting files.
9. Commit and push the verified slice to origin/dev.
10. Generate the next bounded prompt from updated state.
11. Continue immediately to the next slice unless a hard stop gate is hit.

I may be away. Do not wait for me unless continuing would violate a hard stop gate.

Repository and branch rules:
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
1. Run pwd, git status --short --branch, and git remote -v.
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

Planning source hierarchy:
- .planning/ROADMAP.md is the root page-analysis roadmap.
- .planning/refactors/README.md is the refactor index.
- .planning/refactors/modular-io-boundaries/README.md is this refactor package entry.
- 00-REQUIREMENTS.md defines production-grade modular IO requirements.
- 03-REFACTOR-STATE-MACHINE.md defines legal state transitions and completion semantics.
- 04-IMPLEMENTATION-ROADMAP.md defines phase roadmap progress.
- autonomous/MODULE-QUEUE.md is the executable boundary queue.
- autonomous/STATE.md, autonomous/JOURNAL.md and autonomous/NEXT-PROMPT.md are execution accounting.

Never collapse these sources into one unqualified percentage.

Completion semantics:
- MODULE-QUEUE.md Status is slice status.
- MODULE-QUEUE.md Module Closure is module implementation closure status.
- analysis-closed means analysis/inventory slice closed only.
- contract-guard-closed means manifest/contract guard slice closed only.
- static-guard-closed means static guard slice closed only.
- regression-guard-closed means regression guard slice closed only.
- route-guard-closed means route guard slice closed only.
- inventory-guard-closed means inventory guard slice closed only.
- implementation-closed means one narrow implementation slice closed only.
- planning-closed means planning/state/prompt slice closed only.
- production-evidence-deferred means a real environment evidence gap is recorded, not silently passed.
- None of the labels above means a module is fully modularized.

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

Current corrected state expected on start:
- Latest known dev commit when this prompt was generated: c212f73e refactor(batch-accounting): extract get route owner.
- Last completed boundary: batch-accounting:legacy-route-implementation.
- Last status: implementation-closed.
- Last completed slice extracted read-only GET /api/batch-accounting query normalization and list error mapping into BatchAccountingApiRoutes.
- batch-accounting is not module-closed.
- batch-accounting Module Closure remains implementation-gap-open.
- server.py shared-boundary cleanup remains implementation-gap-open.
- First read model implementation pilot remains bank_detail.
- bank_detail is not module-closed.
- bank_detail Module Closure remains implementation-gap-open.
- The next executable implementation boundary is batch-accounting:submit-withdraw-route-side-effect-port.
- Go hot-path candidates remain blocked-by-prerequisite.
- Do not select GoHotPath next unless the queue was legitimately updated after prerequisite evidence closed.

Boundary selection priority:
1. If ROADMAP, refactor README, modular README, 00-REQUIREMENTS, 03-REFACTOR-STATE-MACHINE, 04-IMPLEMENTATION-ROADMAP, STATE, MODULE-QUEUE, JOURNAL or NEXT-PROMPT disagree on source hierarchy, current state, next boundary, status labels, module closure meaning or completion metric source, select a planning:state-reconciliation-* boundary first.
2. Otherwise pick the first boundary in MODULE-QUEUE.md whose Status is pending.
3. Skip blocked-by-prerequisite items.
4. Do not select Go hot-path candidates while any earlier pending, implementation-pending or implementation-gap-open modular IO boundary exists.
5. If the selected boundary is too broad, split it by updating MODULE-QUEUE.md and immediately execute the first smaller boundary.

Immediate next boundary:
Start with batch-accounting:submit-withdraw-route-side-effect-port unless a planning-state inconsistency is found first.

For batch-accounting:submit-withdraw-route-side-effect-port:
- Read:
  - .planning/refactors/modular-io-boundaries/analysis/completion-semantics-and-queue-reclassification.md
  - .planning/refactors/modular-io-boundaries/analysis/queue-semantics-and-master-goal-prompt-revision.md
  - .planning/refactors/modular-io-boundaries/analysis/batch-accounting-legacy-route-contract.md
  - .planning/refactors/modular-io-boundaries/analysis/batch-accounting-get-route-owner-extraction.md
  - docs/app-architecture/runtime-and-ownership.md
  - docs/modules/README.md
  - docs/modules/batch-accounting/README.md
  - docs/modules/batch-accounting/state-machine.md
  - docs/modules/batch-accounting/tests.md
  - docs/modules/batch-accounting/implementation-notes.md
- Use CodeGraph first for structural lookup of _handle_api_batch_accounting_submit, _handle_api_batch_accounting_withdraw, BatchAccountingService.submit, BatchAccountingService.withdraw, callers, callees, traces and impact.
- Use rg for literal text, route paths, docs references and test names.
- Select the smallest mutation route boundary with a clear owner and existing tests.
- Prefer moving submit/withdraw HTTP DTO parsing and BatchAccountingError mapping into BatchAccountingApiRoutes, while preserving BatchAccountingService as the mutation contract owner.
- If extracting both submit and withdraw is too broad, split MODULE-QUEUE.md into smaller pending slices and execute the first one.
- Preserve API response shape, permissions, audit, read model freshness and frontend behavior.
- Keep server.py limited to HTTP parsing, session/auth resolution, dependency wiring and response mapping.
- Do not do broad line-count splitting.
- Do not migrate unrelated modules in the same slice.
- Do not implement Go/Fiber/Go Worker.
- Produce or update an analysis file under .planning/refactors/modular-io-boundaries/analysis/.
- Update MODULE-QUEUE.md so the next pending item remains a concrete implementation boundary, not Go admission.
- Update STATE.md, JOURNAL.md and NEXT-PROMPT.md.
- Run targeted tests, docs verification and diff checks.
- Commit and push to origin/dev if verification passes.
- Continue immediately to the next pending implementation boundary.

Per-boundary analysis requirements:
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

Contract requirements:
- Fill or update the relevant module IO contract using 02-MODULE-IO-CONTRACT-TEMPLATE.md when the boundary changes module contract.
- Every module boundary must define inputs, outputs, states, events, read model contract, force refresh contract, operation barrier contract, canonical facts, shared fact owner, permissions, audit records, public surface, internal-only surface, allowed dependencies, forbidden dependencies, legacy retirement/quarantine contract, test contract and docs impact.
- For read model boundaries, define read_model_key, scope_type, scope_key, partition key, affected scope calculation, freshness proof, parent/aggregate semantics, all-scope semantics, builder owner, full rebuild fallback, source/schema version and operation barrier target.

Tests and verification:
- Evaluate all seven test categories for every implementation slice:
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

Implementation rules:
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

Legacy removal/quarantine rules:
- For every old route/service/repository/read model/frontend API/worker path touched or replaced, classify it as removed, quarantined, compat-only or blocked-by-human-gate.
- Default to removal when tests and call graph prove it is unused.
- compat-only paths must have owner, caller list, deletion condition, forbidden write list and regression tests.
- Old paths must not write canonical facts, dirty scopes, outbox events, read model readiness, cache, App Status or new authoritative outputs.
- New paths must not call old internals or legacy fallbacks unless the contract explicitly registers a temporary compat-only adapter.

Shared facts and read model rules:
- Canonical facts have one owner.
- Derived/read model/cache data cannot become the source of truth.
- All non-transactional read model refresh requests go through ReadModelRefreshGateway and the scope policy registry.
- Transactional writers must maintain equivalent scope/outbox contract inside the business transaction.
- Business services must not directly SQL write job.outbox_events or job.read_model_dirty_scopes.
- Redis may cache only payloads that passed the fresh gate.
- RabbitMQ is wakeup/transport only; it is never the read model, worker, job or freshness source of truth.
- No page may display stale payload as fresh.
- Writes affecting cross-page consistency must return or expose affected scopes/months/version/job, then the frontend/API must use operation barrier or registered read boundary before claiming sync is complete.

Go/Fiber/Go Worker rules:
- Do not implement Go/Fiber/Go Worker unless the candidate is listed in 11-GO-HOT-PATH-CARVE-OUT.md and admission gates pass.
- Do not run Go admission while earlier implementation-pending or implementation-gap-open modular IO boundaries remain, unless the queue was explicitly reclassified with evidence.
- Fiber is optional internal API for selected compute/read services; it is not a replacement for read models, workers, durable queue, freshness proof, permissions, audit or canonical write services.
- Long-running work must not run inside a Fiber request handler.
- Go Worker target remains Go Worker + PostgreSQL dual queue; PostgreSQL durable queue remains authoritative.
- RabbitMQ can be future wakeup/transport only.

Production and SSH rules:
- SSH aliases may be used for read-only production evidence if already configured.
- Do not read or print secrets, DSNs, tokens, cookies, env secret values, private keys or sensitive payloads.
- Do not perform production writes, DB writes, queue mutation, readiness mutation, worker replay/consume, systemd mutation, file mutation or OA mutation.
- If production write or secret access is required, record needs-human-production-gate and continue to another independent module when safe.
- Missing production DB/worker evidence is a soft gate. Record production-evidence-deferred; never claim real production closure for that evidence.
- The plan must not depend on local PGSQL_URL or a staging database.

State-machine update gate:
- This gate is mandatory before every commit.
- Decide explicitly whether the slice changes any global workflow state, transition, guard, stop/defer condition, completion criterion or queue status semantics.
- Decide explicitly whether the slice changes any module business/UI/read model/worker/operation-barrier/force-refresh/permission/legacy-retirement state.
- If global workflow definition changed, update 03-REFACTOR-STATE-MACHINE.md in the same slice.
- If module state definition changed, update every affected docs/modules/<module>/state-machine.md in the same slice.
- If definitions did not change, record this explicitly in the analysis file with reviewed files and reason.
- Always update progress/accounting state separately:
  - autonomous/STATE.md
  - autonomous/MODULE-QUEUE.md
  - autonomous/JOURNAL.md
  - autonomous/NEXT-PROMPT.md
- A commit is invalid if it updates only NEXT-PROMPT.md without matching STATE.md, MODULE-QUEUE.md, JOURNAL.md and analysis evidence.

Review, commit and push:
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
- Push only to origin/dev.
- After push, confirm branch status is clean and up to date with origin/dev.

Continue:
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
