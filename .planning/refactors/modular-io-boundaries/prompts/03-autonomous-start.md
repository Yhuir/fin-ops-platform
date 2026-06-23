# Prompt: GSD Autonomous Modular IO Refactor Goal

Copy the full prompt below into Codex to start or resume the autonomous run.

```text
$gsd-autonomous --auto

You are Codex working in /Users/yu/Desktop/fin-ops-platform.

Goal:
Autonomously continue the modular IO boundary refactor until the refactor plan reaches closure. Use GSD discipline end to end: review and full analysis first, then implementation, then review, verification, state update, commit/push to dev, next prompt generation, and immediate continuation to the next safe boundary. I may be away. Do not wait for me unless a hard stop gate is hit.

Planning source rule:
This refactor has multiple planning sources. Read and report them separately; never collapse them into one unqualified percentage.
- `.planning/ROADMAP.md` is the root page-analysis roadmap.
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md` is the modular IO phase roadmap.
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md` is the executable autonomous boundary queue.
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`, `JOURNAL.md`, and `NEXT-PROMPT.md` are execution accounting for the autonomous queue.
- If these files disagree on status, next boundary, completion criteria, or metric source, create and complete a `planning:state-reconciliation-*` slice before doing code or module implementation.

Non-negotiable state-machine rule:
State-machine updates are part of the implementation contract, not optional bookkeeping. Every autonomous slice must update or explicitly audit all relevant state-machine artifacts before it can be considered complete. A slice that changes code/tests/docs but does not update STATE.md, MODULE-QUEUE.md, JOURNAL.md, NEXT-PROMPT.md, and the applicable global/module state-machine definition or "definition unchanged" analysis is incomplete and must not be committed.

Definition of "closure":
- Every boundary in .planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md is either closed with verified code/docs/tests, production-evidence-deferred with explicit evidence gap, go-candidate-deferred with admission evidence, or needs-human-production-gate for a true hard gate.
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md` has no unchecked completion criterion that is required for modular IO closure, or each remaining unchecked criterion has an explicit deferred/block status and next action.
- `.planning/ROADMAP.md` page-analysis phases have been accounted for as root roadmap input. If page-analysis phases remain `Not started`, do not claim root roadmap closure; either generate the next page-analysis planning prompt or explicitly state that modular IO closure is separate from root page-analysis closure.
- .planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md, autonomous/STATE.md, autonomous/MODULE-QUEUE.md, autonomous/JOURNAL.md, and autonomous/NEXT-PROMPT.md reflect the same current state, completed boundary, next boundary, transition reason, evidence, and stop/defer gate.
- State-machine accounting is mandatory for every slice. A slice is not complete until its analysis file records the intended transition, autonomous/STATE.md records the actual transition, MODULE-QUEUE.md records the boundary status, JOURNAL.md records evidence, NEXT-PROMPT.md points at the next executable boundary, and the global/module state-machine files are either updated or explicitly marked not applicable with a reason.
- No completed slice leaves known broken behavior.
- Every pushed dev commit is reviewable, reversible, and merge-to-main ready for the completed slice.
- Old code paths are removed whenever tests/call graph prove they are unused. Retained old paths are quarantined as compat-only with owner, callers, deletion condition, forbidden writes, and tests.
- New links cannot be polluted by old route/service/repository/read model/frontend API/worker paths.
- Shared facts, dirty scopes, outbox, readiness, App Status, operation barrier, force refresh, and read model refresh go through registered boundaries.
- Every page/domain read model is registered toward Partitioned Scoped Read Model + Scoped Incremental Projection, with Workbench active generation preserved as its special atomic publish model.
- Go/Fiber/Go Worker work is only candidate-gated according to 11-GO-HOT-PATH-CARVE-OUT.md. No unauthorized Go migration is allowed.

Hard quality rule for every commit pushed to dev:
Every commit pushed to origin/dev must be safe to replace or merge into main for the completed slice. Before every commit, prove the slice has no known bugs by running targeted tests/checks, reviewing diff, protecting old behavior, checking no secret leakage, confirming no unrelated user changes are staged, and documenting any unavailable verification. If this cannot be proven, do not commit or push that slice.

Repository and branch policy:
- Work only in /Users/yu/Desktop/fin-ops-platform.
- Use the main repository directory directly. Do not create a new worktree.
- Use dev as the autonomous execution and integration branch.
- Do not create a separate codex/* integration branch.
- Do not work on main.
- Do not commit to main.
- Do not push to main.
- Commit and push each passing small boundary slice to origin/dev.
- Never force-push.
- Never rebase dev automatically.
- Never reset dev automatically.
- Never delete branches.
- Never run destructive local operations such as git reset --hard or git checkout -- unless the user explicitly asks for that exact operation.

Required first preflight:
1. Run:
   - pwd
   - git status --short --branch
   - git remote -v
2. Confirm the repository is /Users/yu/Desktop/fin-ops-platform.
3. Confirm the current branch is dev before implementation commits.
4. Fetch origin with prune.
5. Pull origin/dev with --ff-only when the working tree is clean.
6. Merge origin/main into dev only when the working tree is clean and the merge is conflict-free.
7. If merging origin/main into dev conflicts, stop and record blocked-hard-stop/dev-main-alignment-conflict. Do not auto-resolve finance, read model, worker, permission, migration, or generated-lockfile conflicts.

Dirty worktree handling:
- If the worktree is clean, proceed normally.
- If the only dirty files are the interrupted autonomous read-model slice below, treat them as in-progress work that must be inspected, completed, verified, documented, committed, and pushed before selecting another module:
  - backend/src/fin_ops_platform/services/read_model_scope_policy.py
  - backend/src/fin_ops_platform/services/read_model_manifest.py
  - tests/test_read_model_manifest.py
- If other dirty files exist, inspect ownership carefully.
- If dirty files look like user work or unrelated work, stop before staging, formatting, reverting, stashing, committing, or overwriting them.
- If dirty files are clearly from the current interrupted autonomous slice, continue that slice; do not discard them.
- Do not use destructive cleanup. Preserve user changes.

Required reading before any edits:
Read repository guidance:
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

Read every refactor planning file before implementation:
1. Run:
   rg --files .planning/refactors/modular-io-boundaries | sort
2. Read all Markdown files under:
   - .planning/refactors/modular-io-boundaries/
   - .planning/refactors/modular-io-boundaries/analysis/
   - .planning/refactors/modular-io-boundaries/autonomous/
   - .planning/refactors/modular-io-boundaries/prompts/
3. Treat these planning files as execution rules for this refactor:
   - 00-REQUIREMENTS.md
   - 01-CURRENT-STATE-AUDIT.md
   - 02-MODULE-IO-CONTRACT-TEMPLATE.md
   - 03-REFACTOR-STATE-MACHINE.md
   - 04-IMPLEMENTATION-ROADMAP.md
   - 05-IMPACT-AND-TEST-GATES.md
   - 06-PILOT-SELECTION.md
   - 07-DOCS-GOVERNANCE.md
   - 08-AUTONOMOUS-RUNBOOK.md
   - 09-DEV-BRANCH-WORKFLOW.md
   - 10-AUTONOMOUS-STOP-GATES.md
   - 11-GO-HOT-PATH-CARVE-OUT.md
   - autonomous/STATE.md
   - autonomous/MODULE-QUEUE.md
   - autonomous/JOURNAL.md
   - autonomous/NEXT-PROMPT.md

Current resume priority:
- First run planning-state reconciliation preflight across `.planning/ROADMAP.md`, `.planning/refactors/README.md`, `modular-io-boundaries/README.md`, `00-REQUIREMENTS.md`, `03-REFACTOR-STATE-MACHINE.md`, `04-IMPLEMENTATION-ROADMAP.md`, `autonomous/STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, and `NEXT-PROMPT.md`.
- If any of those files disagree on source hierarchy, current state, completed boundary, next boundary, status labels, or completion metric source, finish a `planning:state-reconciliation-*` slice first.
- Current completed boundary in STATE.md is expected to be `planning:state-reconciliation-and-roadmap-alignment`.
- Current next queued boundary is expected to be `go-hot-path:workbench-compute-admission`.
- After finishing the current slice, select the first pending or deferred-retry boundary in MODULE-QUEUE.md, unless a planning-state inconsistency requires another reconciliation slice.

GSD autonomous loop:
Repeat this loop until MODULE-QUEUE.md has no pending/deferred-retry boundary that can be safely advanced.

0. Planning-state reconciliation preflight
   - Read `.planning/ROADMAP.md` and record root page-analysis roadmap progress separately.
   - Read `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md` and record modular IO phase roadmap progress separately.
   - Read `autonomous/MODULE-QUEUE.md` and record autonomous boundary queue progress separately.
   - Confirm `README.md`, `00-REQUIREMENTS.md`, `03-REFACTOR-STATE-MACHINE.md`, `STATE.md`, `JOURNAL.md`, and `NEXT-PROMPT.md` agree on whether the run is planning-only, in-progress, deferred, blocked, or closed.
   - If they disagree, the selected boundary must be `planning:state-reconciliation-*`; update the relevant docs/state/prompt files, verify docs, commit/push, then continue.
   - Do not report a single unqualified "whole refactor" percentage.

State-machine updates are a first-class step in this loop. Do not treat them as a final note or as part of prompt generation only:
- Before implementation, read the global and module state-machine files and record the intended transition in the boundary analysis.
- During implementation, track whether any workflow state, module state, transition guard, freshness status, worker lifecycle, permission state, operation barrier state, force-refresh state, or legacy-retirement state changed.
- After verification and before commit, update the actual transition in `autonomous/STATE.md`, `autonomous/MODULE-QUEUE.md`, `autonomous/JOURNAL.md`, and `autonomous/NEXT-PROMPT.md`.
- If definitions changed, update `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md` or the affected `docs/modules/<module>/state-machine.md` in the same slice.
- If definitions did not change, the analysis file must explicitly say which state-machine files were reviewed and why the definition is unchanged.
- A slice is incomplete if state-machine accounting is missing, even when code, tests, docs, and `NEXT-PROMPT.md` were updated.

1. Review and full analysis
   - Read current STATE.md, JOURNAL.md, MODULE-QUEUE.md, and NEXT-PROMPT.md.
   - Select exactly one narrow boundary.
   - Read the target module docs under docs/modules/<module>/, including README.md, state-machine.md, tests.md, e2e-spec.md, e2e-coverage.md, and implementation-notes.md when present.
   - Read relevant architecture/dev/operations/product docs.
   - Read the global refactor workflow state machine at .planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md before selecting implementation changes.
   - Read every relevant module state machine under docs/modules/<module>/state-machine.md before selecting implementation changes.
   - Use CodeGraph first for structural lookup: owners, callers, callees, call path, impact, public/internal surfaces.
   - Use rg for literal text, route paths, test names, env keys, and documentation references.
   - Produce or update an analysis file under .planning/refactors/modular-io-boundaries/analysis/.
   - Fill impact analysis from 05-IMPACT-AND-TEST-GATES.md before editing code.
   - The analysis file must include a "State machine impact" section before code edits. It must name:
     - the global workflow state before the slice
     - the selected boundary status before the slice
     - the target module state-machine files reviewed
     - whether global workflow state definitions change
     - whether module business/UI/read model/worker state definitions change
     - the success transition
     - the defer/block transition
     - the exact files that must be updated at completion

2. Contract and plan
   - Fill or update the module IO contract using 02-MODULE-IO-CONTRACT-TEMPLATE.md.
   - Before implementation, identify the relevant state machine files:
     - .planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md for the global refactor workflow state machine.
     - docs/modules/<module>/state-machine.md for module business/UI/read model/worker states when the selected boundary changes module state semantics or state transitions.
     - .planning/refactors/modular-io-boundaries/autonomous/STATE.md for the current autonomous execution state.
   - Record the intended state transition in the analysis file before editing code:
     - previous state
     - selected boundary
     - transition guard
     - expected evidence
     - next state on success
     - defer/block state if evidence is missing
   - Every module must explicitly define:
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
   - For read model boundaries, define read_model_key, scope_type, scope_key, partition key, affected scope calculation, freshness proof, parent/aggregate semantics, all-scope semantics, builder owner, full rebuild fallback, source/schema version, and operation barrier target.
   - For Go candidates, fill admission evidence before implementation.

3. Tests first where practical
   - Add or update focused tests before behavior-changing code when practical.
   - Always evaluate all seven test categories:
     1. Business core unit tests.
     2. Service-layer tests.
     3. API contract tests.
     4. Read model/cache/background job tests.
     5. Frontend component and interaction tests.
     6. End-to-end business-flow integration tests.
     7. Existing feature regression tests.
   - Add tests for every applicable category.
   - If a category is not applicable, document why in the analysis/state/final summary.
   - For read model changes, include stale/refreshing/fresh/failed behavior, dirty scope, outbox, readiness, operation barrier, force refresh, scope normalization, dedupe/idempotency, cache gating, and cross-page freshness regressions where applicable.
   - For legacy retirement, include call graph/import/API/frontend route guards proving new code does not call old internals and old paths cannot write new facts or refresh state.
   - For Go candidates, include Python-vs-Go equivalence and shadow-mode tests before authoritative Go ownership.

4. Implement narrowly
   - Implement only the selected boundary.
   - Prefer existing local patterns and helpers.
   - Keep route code as HTTP mapping and dependency assembly only.
   - Keep business rules in services.
   - Keep SQL in repositories.
   - Keep worker logic out of HTTP/server/session/Application dependencies.
   - Do not change business semantics, amount rules, status transitions, permissions, audit meaning, API shape, or UI behavior unless explicitly required and tested.
   - Do not do broad file splitting for line-count optics.
   - Do not introduce new abstractions unless they remove real coupling or encode an existing contract.

5. Remove or quarantine legacy paths
   - For every old route/service/repository/read model/frontend API/worker path touched or replaced, classify it as:
     - removed
     - quarantined
     - compat-only
     - blocked-by-human-gate
   - Default to removal when tests and call graph prove it is unused.
   - compat-only paths must have owner, caller list, deletion condition, forbidden write list, and regression tests.
   - Old paths must not write canonical facts, dirty scopes, outbox events, read model readiness, cache, App Status, or new authoritative outputs.
   - New paths must not call old internals or legacy fallbacks unless the contract explicitly registers a temporary compat-only adapter.

6. Enforce shared facts and read model boundaries
   - Canonical facts have one owner.
   - Derived/read model/cache data cannot become the source of truth.
   - All non-transactional read model refresh requests go through ReadModelRefreshGateway and the scope policy registry.
   - Transactional writers must maintain equivalent scope/outbox contract inside the business transaction.
   - Business services must not directly SQL write job.outbox_events or job.read_model_dirty_scopes.
   - Redis may cache only payloads that passed the fresh gate.
   - RabbitMQ is wakeup/transport only; it is never the read model, worker, job, or freshness source of truth.
   - No page may display stale payload as fresh.
   - Writes affecting cross-page consistency must return or expose affected scopes/months/version/job, then the frontend/API must use operation barrier or registered read boundary before claiming sync is complete.

7. Read model target architecture
   - Optimize every page/domain read model toward Partitioned Scoped Read Model + Scoped Incremental Projection.
   - Use full rebuild only for backfill, repair, cold start, or explicit runbook fallback.
   - Parent/all aggregate scopes must not be marked fresh before child shards are fresh.
   - Workbench keeps active generation, month shards, all aggregate, consistency check, and atomic publish. Do not mechanically convert Workbench into a generic read model gateway.
   - Force refresh is a controlled gateway/runbook/API contract, not a UI patch and not "refresh everything".

8. Go/Fiber/Go Worker rules
   - Do not implement Go/Fiber/Go Worker unless the candidate is listed in 11-GO-HOT-PATH-CARVE-OUT.md and admission gates pass.
   - Current target worker runtime is Go Worker + PostgreSQL dual queue:
     - job.outbox_events
     - job.read_model_dirty_scopes
   - RabbitMQ may only be optional wakeup/transport.
   - Fiber is optional internal API for selected compute/read services; it is not a replacement for read models, workers, durable queue, freshness proof, permissions, audit, or canonical write services.
   - Long-running work must not run inside a Fiber request handler.
   - Python and Go workers must not both ack, publish, or write readiness for the same authoritative event/scope.
   - Shadow Go output cannot ack outbox, mark dirty scope done, publish generation, write readiness, or update cache.
   - If admission fails, record go-candidate-deferred and continue with Python boundary hardening or the next module.

9. State-machine sync before verification
   - Re-open the analysis file for the selected boundary and update the state-machine impact section with the actual implementation outcome.
   - Confirm the intended transition recorded before code edits still matches the actual diff.
   - If the diff changed any global workflow definition, update `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md` before running final verification.
   - If the diff changed any module business/UI/read model/worker/operation barrier/force-refresh/permission/legacy-retirement state, update every affected `docs/modules/<module>/state-machine.md` before running final verification.
   - If no state-machine definition changed, record `global state-machine definition unchanged` and/or `module state-machine definition unchanged` in the analysis file with the reviewed files and evidence.
   - Prepare the progress/accounting updates that will be finalized after verification:
     - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
     - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
     - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
     - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

10. Verification
   - Run the smallest sufficient verification for the changed slice.
   - Verification is not complete until the state-machine artifacts have been updated or explicitly audited as unchanged.
   - Prefer documented commands and existing tests.
   - Typical commands include:
     - PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
     - PYTHONPATH=backend/src python3 -m unittest <targeted-tests> -v
     - PYTHONPATH=backend/src python3 -m unittest discover -s tests -v when the blast radius is broad
     - cd web && npm test -- <targeted-tests>
     - cd web && npm run build
     - bash scripts/verify.sh docs when docs changed and the script exists
     - git diff --check
   - If a command is unavailable or too broad for the slice, document exactly why and run the closest targeted substitute.
   - Do not require local PGSQL_URL.
   - Do not require staging DB.
   - Use fake/stub repository, queue, read model gateway, API contract, frontend mock, static checks, and production read-only SSH checks when useful.

11. Production and SSH policy
   - No local PGSQL_URL is available.
   - No staging database is available.
   - Do not ask me for PostgreSQL URLs, staging DBs, SSH passwords, database passwords, tokens, cookies, or private secrets.
   - ssh finops-prod-root is available as root with key login for privileged read-only checks.
   - Use production SSH only for non-secret read-only checks such as service status, file existence, health endpoints, logs without secrets, and runtime status that does not expose credentials.
   - Do not read or print secrets, DSNs, tokens, cookies, env secret values, private keys, or sensitive payloads.
   - Do not perform production writes, DB writes, queue mutation, readiness mutation, worker replay/consume, systemd mutation, file mutation, or OA mutation.
   - If production write or secret access is required, record needs-human-production-gate and continue to another independent module when safe.
   - Missing production DB/worker evidence is a soft gate. Record production-evidence-deferred; never claim real production closure for that evidence.

12. Diff review and security scan
   - Inspect git diff before staging.
   - Confirm every changed file belongs to the selected slice or required docs/state.
   - Confirm no user/unrelated changes are staged.
   - Confirm no secrets are present in changed files, commands, logs, docs, tests, commit messages, or generated artifacts.
   - Confirm old-path removal/quarantine is documented and tested.
   - Confirm shared facts and read model refresh cannot be bypassed.
   - Confirm docs impact is handled.
   - Confirm state-machine accounting is handled:
     - analysis/<boundary>.md has the intended and actual state-machine impact.
     - autonomous/STATE.md, MODULE-QUEUE.md, JOURNAL.md, and NEXT-PROMPT.md agree on current state, boundary status, evidence, and next boundary.
     - 03-REFACTOR-STATE-MACHINE.md is updated when workflow states/transitions/guards changed, or the analysis explicitly says "global state-machine definition unchanged" with evidence.
     - Every affected docs/modules/<module>/state-machine.md is updated when module states/transitions changed, or the analysis explicitly says "module state-machine definition unchanged" with evidence.
   - Do not commit if state-machine accounting is missing, contradictory, or only represented by NEXT-PROMPT.md.

13. State-machine update gate
   - This gate is mandatory before every commit. Do not skip it for documentation-only, test-only, manifest-only, or "no behavior change" slices.
   - Decide explicitly whether the slice changes any state-machine definition:
     - global refactor workflow states, transitions, guards, stop gates, defer gates, completion criteria, or autonomous continuation rules.
     - module business states, UI states, read model states, worker states, operation barrier states, force-refresh states, permission states, legacy-retirement states, or state transition evidence.
   - If any global workflow definition changed, update `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md` in the same slice.
   - If any module state definition or transition changed, update every affected `docs/modules/<module>/state-machine.md` in the same slice.
   - If definitions did not change, record this explicitly in `.planning/refactors/modular-io-boundaries/analysis/<boundary>.md` with:
     - reviewed global state-machine file.
     - reviewed module state-machine files.
     - reason definitions are unchanged.
     - evidence that only progress/accounting changed.
   - Update progress/accounting state separately from definition state:
     - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
     - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
     - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
     - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
   - The commit is invalid if it updates only `NEXT-PROMPT.md` without matching `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, and analysis evidence.
   - The commit is invalid if the analysis says "state-machine definition unchanged" but the code/docs changed state names, status values, transition guards, read model freshness states, worker lifecycle states, permission states, or legacy-retirement states.

14. State update
   - Updating state is mandatory after every closed, deferred, blocked, or failed boundary. Do not treat NEXT-PROMPT.md alone as the state machine.
   - Update .planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md when the run introduces, renames, or clarifies any workflow state, transition, guard, stop/defer condition, or completion criterion.
   - If the selected boundary changes business state, UI state, read model state, worker state, operation barrier state, force-refresh state, permission state, or legacy-retirement state, update docs/modules/<module>/state-machine.md in the same slice.
   - If no global or module state-machine definition changes, do not silently skip it; record "definition unchanged" in the analysis file with the reason and reviewed file list.
   - Update the relevant module docs if long-term facts changed.
   - Update .planning/refactors/modular-io-boundaries/analysis/<boundary>.md.
   - Update autonomous/STATE.md.
   - Update autonomous/JOURNAL.md.
   - Update autonomous/MODULE-QUEUE.md.
   - Update autonomous/NEXT-PROMPT.md with the next executable prompt.
   - The state update must record:
     - previous state
     - completed/deferred/blocked boundary
     - status value
     - verification evidence
     - production evidence status
     - legacy removal/quarantine status
     - next boundary
     - next state
   - If a module is complete locally but lacks real production evidence, mark production-evidence-deferred, not closed as production-proven.
   - If a Go candidate fails admission, mark go-candidate-deferred.
   - If a hard gate is hit, mark blocked-hard-stop with concrete evidence and stop.

15. Commit and push
   - Stage only files for the completed slice.
   - Commit with a scoped message such as:
     - refactor(read-models): tighten query freshness manifest guards
     - docs(read-models): record refresh boundary contract
     - test(read-models): guard legacy refresh contamination
   - Push only to origin dev:
     - git push origin dev
   - After push, confirm branch status is clean and up to date with origin/dev.
   - Then continue to the next pending boundary without waiting for me unless a hard stop gate exists.

16. Next prompt execution
   - Generate or update autonomous/NEXT-PROMPT.md after every closed/deferred slice.
   - Treat NEXT-PROMPT.md as resume state, but do not stop merely because it was updated.
   - Immediately execute the next prompt unless the current run hit a hard stop gate or no safe module remains.
   - If context compaction or restart occurs, resume by reading STATE.md, MODULE-QUEUE.md, JOURNAL.md, NEXT-PROMPT.md, git status, and latest commits on dev.

Failure handling:
- For a module-specific failure, attempt up to 3 focused repair iterations if the issue count is decreasing and the work remains scoped.
- If still failing, preserve evidence in analysis/STATE/JOURNAL.
- Do not commit broken code.
- Do not leave the worktree dirty before switching modules.
- If the failed diff is clearly isolated to the module and must be set aside, save a patch under .planning/refactors/modular-io-boundaries/autonomous/failures/ and stash only that failed module diff. Do not stash user changes.
- Continue to the next independent module only when the worktree is clean and doing so is safe.

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
- Business semantics are ambiguous enough to risk finance rules, permissions, amounts, state transitions, or audit meaning.
- No independent module remains.
- Go/Fiber migration would violate 11-GO-HOT-PATH-CARVE-OUT.md.

Final report when the full run stops or reaches closure:
- Branch and latest dev commit.
- Modules completed.
- Modules production-evidence-deferred and exact missing evidence.
- Modules go-candidate-deferred and exact failed admission gate.
- Modules needs-human-production-gate and exact required approval.
- Legacy paths removed.
- Legacy paths retained as compat-only with deletion condition.
- Read model boundaries completed, including force refresh and freshness proof coverage.
- Go/Fiber/Go Worker candidates admitted, deferred, or not started.
- Tests added/changed and the seven test categories they cover.
- Verification commands run.
- Verification not run and why.
- Production read-only evidence collected.
- Remaining risks.
- Confirmation that no commit was pushed to main and every pushed commit went to origin/dev.
```
