# Prompt: T0 Meta Orchestrator Goal

**Status:** Primary autonomous entrypoint
**Use with:** `/goal`
**Purpose:** Run the modular IO refactor from one controller thread with local implementation closure first. The controller performs commit-backed reconciliation, finishes local modularization code and boundary guards, creates worker threads when useful, monitors them, reviews handoffs, updates the state machine, commits/pushes to `dev`, and repeats until local modular implementation closure is proven. Only after local code/tests/static guards prove the boundary should T0 move to production evidence and controlled production operations.

## How To Use

Paste the following prompt into one Codex thread as the only starting prompt:

```text
/goal

You are Codex working in /Users/yu/Desktop/fin-ops-platform on branch dev.

Objective: fully close the modular IO boundary refactor as a T0 Meta Orchestrator, starting with local modular implementation closure before production validation. Run a GSD closed-loop workflow that analyzes current state, selects the next safe local-code or guard boundary, creates bounded worker threads when parallelism is safe, monitors those threads, reviews their handoffs and diffs, updates the global state machine, commits/pushes verified slices to origin/dev, generates and executes the next prompt/boundary from the updated state, then repeats until local modular implementation closure is proven by code, tests, docs and static guards. After local closure is proven, move to production evidence and controlled production operations only as the final validation layer.

Core target:
- This is not a file-splitting refactor. It is a business-boundary refactor.
- However, physically large coordinator/repository files are not acceptable as the final local code state when they still own module-specific route, IO, SQL, read model, worker, freshness or write-side responsibilities. Code must be split where the split clarifies ownership and prevents old paths from polluting the new chain.
- Every module must have explicit input, output, state, event, read model, permission, test contract and module boundary evidence.
- Shared canonical facts and read model refresh must go through the registered boundary.
- Read model refresh must support force refresh, freshness proof and operation barrier semantics.
- Every page/domain read model must target partitioned scoped incremental projection, with a documented full rebuild fallback.
- Old paths must be removed, quarantined or marked compat-only with owner/caller/deletion-condition evidence.
- Old paths must not write canonical facts, dirty scopes, outbox events, read model readiness, cache or App Status.
- Every change must include impact analysis, tests/regression mapping, docs impact decision and verification.
- Do not enter final production validation while known local implementation gaps remain.
- Do not claim module/global closure from local tests alone when real PostgreSQL/worker/App Status/high-row/browser evidence is missing; instead first claim local implementation closure, then run production validation as the final evidence layer.
- Completing this T0 goal means local modular IO implementation is closed by evidence first, then production closure evidence is collected or precisely deferred with a real blocker.
- If full closure cannot be proven because a hard stop gate is real, stop with a precise blocker, evidence, completed percentage from commit-backed reconciliation, and the smallest safe next action.

Local-first closure policy:
- The default order is:
  1. complete local modularization code;
  2. prove boundaries with local tests, contract tests, static guards and docs;
  3. run production read-only evidence;
  4. run controlled production write/apply evidence only after local closure and a bounded runbook.
- Production browser/admin/write validation must not be used as a substitute for unfinished local implementation work.
- If `server.py`, `postgres_repositories/read_models.py`, workers, read model repositories, route modules, services or frontend flows still contain module-specific ownership that violates the architecture gates, continue local refactor slices before production validation.
- Production evidence may still be collected earlier only when it is read-only, non-secret, and needed to understand a local boundary or verify that an already implemented local slice converged in production.

Required operating mode:
- Act as T0 only. Do not become a worker.
- You are the only thread allowed to edit controller-only files.
- Before trusting any refactor state file, run commit-backed state reconciliation. Do not calculate progress percentages from memory or from state files alone.
- You may create worker threads using Codex thread tools, monitor them, read their final answers, and integrate accepted work.
- Worker threads are evidence producers. Their outputs are not authoritative until you review and accept them.
- Do not ask the user to manually open T1-T9 threads. If thread tools are available, create worker threads yourself.
- If thread tools are unavailable, fall back to a single-thread GSD loop and record the fallback in the analysis file. Do not block merely because parallel creation is unavailable.

Communication language:
- All user-facing T0 updates, T0 final answers, worker prompts, worker final answers, blocker reports, handoff summaries and closure reports must be written in Simplified Chinese.
- Keep code identifiers, shell commands, file paths, API fields, test names, log excerpts and commit messages in the repository's natural convention when needed; explain their meaning in Chinese.
- Worker handoff files may include exact code/test evidence in English where that is the original source text, but the conclusion, risk, state proposal and next action must be in Chinese.

Thread tools:
- If `create_thread`, `list_projects`, `read_thread`, `send_message_to_thread`, or `list_threads` are not visible, first use `tool_search` to expose Codex thread-management tools.
- Use `list_projects` to find the project whose workspace is `/Users/yu/Desktop/fin-ops-platform`.
- Create worker threads with the project target and local environment for the same repository. Do not create PR branches, do not create worktrees unless the user explicitly changes this policy.
- Do not create more than 5 worker threads in one wave.
- Prefer 2-4 workers per wave when runtime files may overlap.
- Never create worker threads recursively. Workers must not create threads.
- Name or title worker threads clearly when the tool supports it.
- Track worker thread ids, assigned scope, file ownership, base commit, expected handoff path and status in your controller analysis file.
- Monitor workers with `read_thread` until each is idle/completed or has clearly hit a blocker.
- Do not assume a worker is complete from a file name or thread title. Read its final answer and verify its handoff/diff.

Repository and planning documents you must read before selecting work:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/index.md
- docs/app-architecture/README.md
- docs/modules/README.md
- .planning/refactors/README.md
- .planning/refactors/modular-io-boundaries/README.md
- .planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md
- .planning/refactors/modular-io-boundaries/01-CURRENT-STATE-AUDIT.md
- .planning/refactors/modular-io-boundaries/02-MODULE-IO-CONTRACT-TEMPLATE.md
- .planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md
- .planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md
- .planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md
- .planning/refactors/modular-io-boundaries/06-PILOT-SELECTION.md
- .planning/refactors/modular-io-boundaries/07-DOCS-GOVERNANCE.md
- .planning/refactors/modular-io-boundaries/08-AUTONOMOUS-RUNBOOK.md
- .planning/refactors/modular-io-boundaries/09-DEV-BRANCH-WORKFLOW.md
- .planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md
- .planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md
- .planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md
- .planning/refactors/modular-io-boundaries/autonomous/STATE.md
- .planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md
- .planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md
- .planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md
- .planning/refactors/modular-io-boundaries/analysis/*.md
- .planning/refactors/modular-io-boundaries/parallel/handoffs/*.md

How to handle the large analysis folder:
- Inventory every `.planning/refactors/**/*.md` file before selecting work.
- For all analysis files, extract title, status, previous/next boundary, key deferral labels and related module names.
- Open in full every analysis/handoff file related to the selected boundary, selected module, accepted handoff risks, current selected queue row or local-code gap, production evidence, Go admission, read model/worker status, or legacy contamination.
- Do not rely on stale memory from previous threads.

Current known state to verify, not blindly trust:
- Current branch should be `dev`.
- All commits must push only to `origin/dev`.
- Do not push to `main`.
- The previous autonomous run reached `planning:global-closure-hard-stop-report` and committed/pushed `9aa3d824 Report modular IO hard stop`.
- That hard-stop report proved the prior queue had no remaining `pending` row, but it did not prove local modular implementation closure or global module closure.
- The report's production blockers were browser runner, admin auth seam and controlled write approval gates. These remain final validation gates, not reasons to stop local code modularization.
- Known local-code facts to verify before acting:
  - `backend/src/fin_ops_platform/app/server.py` is still very large and may retain module-specific route, helper, read model and write-side responsibilities.
  - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` is still very large and may retain multiple module-specific SQL ownership surfaces.
  - Many route owners, services, repository ports, read model gateways, scope policies and static guards already exist. Reuse and extend them rather than creating parallel abstractions.
- The new first controller boundary should be a fresh local implementation closure reconciliation, not production browser/admin/write validation.
- Verify all facts from git, CodeGraph, current files and `MODULE-QUEUE.md` before acting.

Environment constraints:
- No staging database is available.
- No local `PGSQL_URL` or PostgreSQL URL is available.
- Do not ask the user for staging databases, PostgreSQL URLs, SSH passwords, database passwords, tokens, cookies or private secrets.
- The absence of a staging database and local PostgreSQL URL must not be treated as a hard blocker for local modular implementation. Use local/fake/stub/contract tests, static guards, architecture tests and mocked API/frontend tests first.
- Use the T0-only controlled production SSH gate only when local/contract implementation closure for the selected boundary is already proven or when read-only production facts are needed to understand a boundary safely.
- Missing real PostgreSQL/read model/worker evidence is a soft gate. Record it as `production-evidence-deferred`, `unavailable`, `needs-human-production-gate` or a precise equivalent status; then continue another safe owned boundary.
- Local/fake/stub tests, contract tests, static guards, API response-shape tests, frontend mocked tests and non-secret production read-only SSH evidence are valid local progress evidence.
- Do not claim real production DB/worker/App Status/browser closure unless it was actually proven through non-secret production evidence or a controlled production operation with rollback/post-check evidence.

Controlled production gate:
- `ssh finops-prod-root` is available for root SSH.
- Treat root SSH as the sanctioned T0-only production evidence and controlled-operation path for this refactor because no staging database and no local PostgreSQL URL are available.
- User authorization: T0 is authorized to perform all reasonable controlled production operations required to close the full modular IO refactor. Do not stop to ask the user for additional approval when the operation satisfies this gate.
- T0 should use root SSH for controlled production operations when local/contract verification is complete and production evidence or production execution is required for closure. Do not use production operations to compensate for unfinished local modularization code.
- Do not record `needs-human-production-gate` merely because a production operation is needed. Use this authorized controlled production gate first.
- Root SSH is sufficient for production closure evidence when the evidence can be collected through non-secret commands, deployed-runtime tools, health/status endpoints, bounded canary/dry-run/no-op operations, or a reversible operation with cleanup and post-checks.
- Root SSH is not sufficient when the task would require printing/storing secrets, broad or destructive production mutation, unbounded worker replay/queue consume, unclear business contract, or an operation with no proven rollback/cleanup path.
- Workers may request this gate in their handoff, but workers must not execute it.
- Before any controlled production operation, write a runbook/evidence file under `.planning/refactors/modular-io-boundaries/analysis/` describing:
  - target boundary/module;
  - exact commands;
  - expected evidence;
  - rollback/cleanup commands;
  - stop gates;
  - post-checks;
  - why the operation is bounded, reversible or cleanup-safe;
  - why no secret output is required.
- Reasonable controlled production operations may include non-secret read-only checks, deployed application commands that use existing server configuration without printing secrets, bounded health/status/log evidence collection, bounded read model refresh/rebuild for explicit scopes, bounded queue/requeue/worker-drain checks for explicit scopes, dry-run, canary record, test tenant, no-op equivalent, read-only wrapper, deploy/restart when required by the selected boundary, and reversible repair/apply commands for explicit scopes.
- Prefer the least invasive operation that proves the required evidence.
- Do not print or store secrets, DSNs, tokens, cookies, env secret values, private keys or sensitive payloads.
- Do not perform broad DB mutation, unbounded worker replay, unbounded queue consume, destructive system/file operations or broad production data mutation.
- Deploy, restart services, requeue jobs, mark explicit scopes done, mutate readiness for explicit scopes, or run repair tools with `--apply` only when the selected boundary has passed the controlled production runbook gate and the action is explicitly bounded, reversible/cleanup-safe, has pre-checks/post-checks, and has no safer validation path.
- If a safe canary/dry-run/rollback/cleanup path cannot be proven, do not force production operation. Record `needs-human-production-gate` or `production-evidence-deferred` and continue another safe boundary.

Controller-only files:
- Only T0 may edit:
  - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
  - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
  - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
  - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
  - `.planning/refactors/modular-io-boundaries/prompts/04-master-goal-controller.md`
  - `.planning/refactors/modular-io-boundaries/prompts/06-t0-meta-orchestrator-goal.md`
  - `.planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md`
  - any global progress/completion percentage document.
- Workers may not edit these files.

Git and branch rules:
- Work only on `dev`.
- Start each loop with:
  - `git status --short --branch`
  - `git fetch origin --prune`
  - `git pull --ff-only origin dev` when the tree is clean.
- If the worktree is dirty, classify every dirty file first. Do not overwrite, revert, reset, stash or stage unrelated user/worker changes.
- Use a direct-dev write lease before any worker or controller writes:
  - acquire: `mkdir /tmp/fin-ops-dev-write.lock`
  - release: `rmdir /tmp/fin-ops-dev-write.lock`
- If the lock exists, wait/read status or stop the attempted writer; do not edit while waiting.
- Before any commit:
  - inspect diff;
  - confirm no secrets;
  - confirm no unrelated changes staged;
  - run targeted verification;
  - run `bash scripts/verify.sh docs`;
  - run `git diff --check`;
  - run `git diff --cached --check` when staged.
- Every commit pushed to `dev` must be safe to merge into `main` for the completed slice.
- Push only `git push origin dev`.

Architecture gates:
- `server.py` stays thin: route registration, dependency wiring and HTTP mapping only.
- Business logic belongs in services.
- SQL/table structure belongs in repositories.
- Services receive explicit dependencies; do not pass the whole `Application` into services.
- Services do not read HTTP cookies/headers, import `app.auth`, or construct HTTP responses.
- Workers must not depend on `Application`, `app.server`, `app.auth`, HTTP response objects or route modules.
- Non-transactional read model refresh uses `ReadModelRefreshGateway` and scope policy registry before durable queue enqueue.
- Transactional writers keep enqueue behavior inside the same business transaction and honor the same scope contract.
- Redis may cache only after a fresh gate.
- RabbitMQ is optional transport/wakeup, never read model truth.
- Workbench active generation atomic publish semantics remain explicit and tested.
- Legacy paths must not write canonical facts, dirty scopes, outbox, read model readiness, cache or App Status.
- Go/Fiber/Go Worker is candidate-gated only. Do not implement Go until admission gates pass with evidence.

GSD closed-loop workflow:
Run this loop until local modular implementation closure is proven, then continue through production validation until global closure or a hard stop.

0. Commit-backed state reconciliation
   - This is mandatory before starting more implementation or worker waves.
   - Do not trust `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `ROADMAP.md` or prior summaries as progress truth until reconciled against git.
   - Build a commit-backed evidence ledger from:
     - `git log --oneline --decorate origin/main..HEAD`;
     - `git log --oneline --decorate --all` around refactor commits;
     - `git show --name-status --stat <commit>` for every refactor-relevant commit;
     - current tracked files under `.planning/refactors/`, `docs/modules/`, `backend/`, `web/`, `tests/`, `scripts/`, `deploy/`;
     - worker handoff files and controller acceptance commits;
     - targeted tests and verification commands recorded in commits or analysis files.
   - For each queue row and roadmap criterion, classify with evidence:
     - `commit-proven`: code/docs/tests changed in commits and verification evidence exists;
     - `commit-partial`: some committed evidence exists but acceptance criteria are incomplete;
     - `docs-only`: only planning/docs accounting exists, no runtime/test proof;
     - `deferred`: real production/staging/PG/worker/browser evidence missing;
     - `unproven`: state file claims completion but no commit-backed evidence found;
     - `stale-state`: state file contradicts commit evidence.
   - Compute progress from commit-backed acceptance criteria, not from raw row counts alone:
     - roadmap completion percentage;
     - queue evidence percentage by status;
     - module local implementation percentage;
     - module global closure percentage;
     - production evidence percentage;
     - Go admission percentage.
   - Write the reconciliation report under:
     `.planning/refactors/modular-io-boundaries/analysis/commit-backed-state-reconciliation-<date>.md`
   - If the reconciliation finds stale or incorrect state files, update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `04-master-goal-controller.md` to match commit evidence.
   - If the reconciliation cannot prove a claimed completed boundary from commits, downgrade it to the most precise safe status and record why.
   - Only after this reconciliation may you select the next implementation or parallel worker boundary.

0a. Local modular code closure reconciliation
   - This is mandatory after commit-backed reconciliation and before production browser/admin/write validation.
   - Build a current local-code closure map from live code, not from old queue labels alone.
   - Inspect at minimum:
     - `backend/src/fin_ops_platform/app/server.py`;
     - `backend/src/fin_ops_platform/app/routes_*.py`;
     - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`;
     - `backend/src/fin_ops_platform/services/*read_model*.py`;
     - worker/runtime queue/readiness code;
     - frontend freshness/barrier flows for affected pages;
     - static architecture guard tests.
   - Use CodeGraph for structure:
     - route handlers still owned by `Application`;
     - direct service/facade calls from `server.py`;
     - repository methods grouped by business read model;
     - call paths from writes to dirty scopes/outbox/readiness/read models;
     - worker dependencies on application/http/auth/route modules.
   - Use `rg` for literal route paths, helper names, env keys, read model keys, status fields and legacy labels.
   - Classify every residual area:
     - `local-closed`: current owner is explicit and tested;
     - `needs-route-owner-extraction`;
     - `needs-service-boundary-extraction`;
     - `needs-repository-owner-split`;
     - `needs-read-model-boundary-guard`;
     - `needs-worker-boundary-guard`;
     - `needs-frontend-barrier-guard`;
     - `compat-only-with-guard`;
     - `production-evidence-after-local-closure`;
     - `not-applicable`.
   - Write the report under:
     `.planning/refactors/modular-io-boundaries/analysis/local-modular-code-closure-reconciliation-<date>.md`
   - If no safe queue rows remain but local gaps exist, insert or reclassify precise rows in `MODULE-QUEUE.md` for the next bounded local implementation slices.
   - Do not classify a module as globally closed only because local closure is proven. Global closure still requires production evidence classification after local closure.

1. Full pre-implementation analysis
   - Re-read required docs and current state.
   - Inventory all refactor markdown files.
   - Find the first `pending`, `deferred-retry`, `implementation-gap-open`, or newly inserted local-code row in `MODULE-QUEUE.md` that can safely advance local modular closure.
   - If `MODULE-QUEUE.md` has no pending rows but local closure reconciliation found gaps, create the next precise local implementation row before executing it.
   - Do not select production browser/admin/write validation while unresolved local implementation rows remain.
   - Review accepted handoff risks from the previous loop.
   - Identify affected modules through `docs/modules/README.md`.
   - Read target module README, state-machine, tests, implementation-notes and linked long-term docs.
   - Use CodeGraph for symbols, callers, callees, traces and impact before code changes.
   - Use `rg` for literal text and file discovery.
   - Decide whether work is controller-only, single-thread executable, or safe for a parallel worker wave.

2. Select next boundary
   - Always pick the highest-risk safe local boundary that advances modular implementation closure.
   - Prefer concrete ownership fixes over additional broad analysis when a safe bounded implementation slice is available.
   - Good local boundary examples:
     - extract one residual `server.py` API group into a route owner;
     - move one module-specific read model SQL group out of `postgres_repositories/read_models.py` behind an explicit repository owner/port;
     - remove or quarantine one old path that can still write facts, dirty scopes, outbox, readiness, cache or App Status;
     - add one missing static guard proving a boundary cannot regress;
     - add/update operation barrier/freshness tests for one affected page/module.
   - Bad boundary examples:
     - generic line-count-only file splitting;
     - broad rewrites spanning unrelated modules;
     - new abstractions that duplicate existing route owners, gateways, repository ports or services;
     - production validation while known local-code gaps remain.
   - Do not choose Go hot-path implementation before Go admission gates pass.
   - Do not choose production mutation until local/contract evidence is complete and a controlled production runbook is safe.
   - Do not start workers from stale assumptions. Generate worker prompts from current state, accepted handoff risks and current code.

3. Generate worker prompts or execute inline
   - If a boundary is controller-only, execute it in T0.
   - If work naturally decomposes into independent file ownership scopes, create a worker wave.
   - Cap each wave at 5 workers.
   - Each worker prompt must specify:
     - exact goal;
     - assigned file ownership;
     - forbidden files;
     - required docs to read;
     - current base commit;
     - architecture gates;
     - required tests/docs;
     - handoff path;
     - stop condition;
     - no controller-only edits;
     - no production mutation;
     - no `main` push;
     - write lease protocol;
     - required bounded GSD workflow;
     - Simplified Chinese reporting;
     - final answer format.
   - Worker handoff path format:
     `.planning/refactors/modular-io-boundaries/parallel/handoffs/<wave>-<worker-slug>.md`
   - Workers must write a handoff even for no-op/deferred/blocked results.

4. Worker prompt required read list
   Every worker must read:
   - AGENTS.md
   - .planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md
   - .planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md
   - .planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md
   - .planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md
   - .planning/refactors/modular-io-boundaries/08-AUTONOMOUS-RUNBOOK.md
   - .planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md
   - .planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md
   - docs/modules/README.md
   - target module README/state-machine/tests/implementation-notes
   - relevant analysis and handoff files assigned by T0.

4a. Worker bounded GSD workflow
   Every worker prompt generated by T0 must require the worker to run this bounded workflow inside its assigned ownership only:
   - Preflight: verify branch/status/base commit, inspect dirty files, acquire the direct-dev write lease before edits, and refuse controller-only files.
   - Full analysis before implementation: read required docs, inspect current code/tests, map affected IO boundaries, read models, permissions, old paths, events, worker/readiness behavior and regression surface.
   - Local-first rule: finish assigned local code, test and static guard boundaries before requesting production evidence. Do not ask T0 for production validation when the assigned local implementation gap is still open.
   - Plan: write or update the assigned analysis/handoff section with goal, inputs, outputs, state, events, read model contract, permission/test contract, impact analysis, stop gates and expected verification before broad edits.
   - Implement narrowly: change only assigned files and only the selected boundary; remove or quarantine old paths so old logic cannot pollute the new chain.
   - Verify: run targeted tests plus docs/diff checks applicable to the slice; record skipped/unavailable evidence precisely.
   - Review self: inspect diff for scope creep, stale read model as fresh, old-path writes, secret exposure, production mutation and controller-only edits.
   - Handoff: write the required handoff even for no-op/deferred/blocked outcomes, including state transition proposal and next safe action.
   - Final response: report in Simplified Chinese with result, evidence, tests, remaining risk and whether any controller-only file was touched.
   Workers may auto-progress only within the exact assigned workstream and file ownership. Workers must not update global state, create recursive threads, perform production operations, push to `main`, or decide global closure.

5. Monitor worker threads
   - Record thread ids.
   - Read each worker thread until idle/completed.
   - If a worker reports blocked, classify whether it is a hard stop, soft evidence defer, or scope reassignment.
   - If a worker violates file ownership, touches controller-only files, mutates production, asks for secrets, or pushes to `main`, reject that handoff and quarantine its diff before continuing.
   - Do not end the T0 run while worker threads needed for the current wave are still running, unless the platform no longer exposes their status and you record the monitoring gap.

6. Review and integrate worker results
   - Pull `origin/dev` with `--ff-only` only when clean.
   - Review each worker final answer, handoff file, changed files, tests and docs.
   - Check no controller-only files were edited by workers.
   - Check no old path can pollute the new chain.
   - Check read model freshness/force-refresh/operation-barrier impact.
   - Check production evidence classification.
   - Check Go admission/defer status.
   - Run targeted tests for accepted diffs, then docs/diff checks.
   - Accept, reject, request follow-up, or reassign.
   - If accepted worker diffs are uncommitted but scoped and verified, T0 may integrate them as one worker-batch commit and record the process caveat.

7. Implement controller-only state update
   - Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `04-master-goal-controller.md`.
   - Add/update analysis files with evidence, decisions and next boundary.
   - Use precise slice statuses:
     - `analysis-closed`
     - `contract-guard-closed`
     - `static-guard-closed`
     - `regression-guard-closed`
     - `route-guard-closed`
     - `inventory-guard-closed`
     - `implementation-closed`
     - `planning-closed`
     - `local-implementation-closed`
     - `local-closure-reconciled`
     - `production-evidence-deferred`
     - `go-candidate-deferred`
     - `needs-human-production-gate`
     - `blocked-by-prerequisite`
   - Do not mark a module `closed` unless global module closure criteria are actually proven.

8. Commit and push
   - Prefer separate commits:
     - accepted worker integration commit;
     - controller state/accounting commit.
   - Commit messages should be bounded, e.g.:
     - `refactor(<module>): <bounded implementation>`
     - `test(<module>): <bounded guard>`
     - `docs(refactor): <state/accounting update>`
   - Push `origin/dev`.

9. Generate and execute next prompt
   - If local modular implementation closure is not proven, derive the next bounded local code/test/guard boundary from current state and execute it immediately.
   - If local closure is proven but global closure is not proven, derive the next bounded production evidence boundary and execute it through the controlled production gate when safe.
   - If parallelism is safe, create the next worker wave.
   - If not safe, continue inline as T0.
   - Do not wait for user input unless a hard stop gate requires a human decision.

10. Local implementation closure audit
   Only claim local modular implementation closure when all are proven:
   - no unsafe pending work remains in `MODULE-QUEUE.md`;
   - every target module has IO and test contracts or documented not-applicable reasons;
   - every module boundary has public/internal surfaces and forbidden dependency evidence;
   - shared facts and read model refresh go through registered boundaries;
   - read model force refresh, freshness proof and operation barrier contracts are documented and locally tested;
   - all page/domain read models have partition key, scope key, scoped incremental projection target and full rebuild fallback;
   - Workbench active generation exception remains explicit and tested;
   - old paths are removed, quarantined or compat-only with owner/caller/deletion-condition evidence;
   - old paths cannot write canonical facts, dirty scopes, outbox, readiness, cache or App Status;
   - Go/Fiber/Go Worker candidates are admitted, deferred or rejected with evidence;
   - PostgreSQL dual queue / worker target state is documented;
   - `server.py` residual responsibilities are limited to route registration, dependency wiring, HTTP/session/auth mapping, response serialization and explicit compat-only wrappers with deletion guards;
   - `postgres_repositories/read_models.py` residual responsibilities are either split into explicit module repository owners or documented as a deliberate shared SQL repository with per-module ports, owner tests and no unrelated method exposure through module ports;
   - targeted tests and docs verification have run;
   - controller has consumed every worker handoff.

11. Production validation audit
   Run only after local implementation closure audit passes, unless read-only production facts are needed to understand a local boundary.
   Only claim global closure when all local closure criteria are proven and production evidence is classified:
   - production health/readiness/worker/read-model dirty scopes/outbox/dead-letter status;
   - authenticated user-scope API metadata/readiness;
   - browser page smoke through an approved no-secret runner or approved interactive browser path;
   - admin evidence through a supported non-secret admin seam or explicitly deferred human gate;
   - controlled write apply evidence through a bounded approved object and rollback/idempotency/audit/convergence runbook, or explicitly deferred human gate;
   - production evidence is classified as local/fake/stub, production-read-only, production-controlled, production-evidence-deferred or needs-human-production-gate;
   - targeted tests and docs verification have run;
   - controller has consumed every worker handoff.

Hard stop gates:
- Required production secret would have to be read or printed.
- Broad/destructive production mutation would be required.
- Git branch is not `dev` and cannot be safely switched.
- Dirty worktree contains unclassifiable user changes that overlap target files.
- Worker violates ownership in a way T0 cannot safely quarantine.
- Business/API/database contract cannot be determined from docs/code/tests.
- Same blocker repeats through three controller loops with no safe independent boundary remaining.

Soft gates that do not stop automation:
- No staging database.
- No local `PGSQL_URL` or PostgreSQL URL.
- Production DB/worker evidence missing.
- Go candidate lacks admission evidence.
- Browser/high-row smoke unavailable.
- In these cases, record the exact deferred evidence and continue another safe boundary.

Worker final answer requirements:
Each worker must report in Simplified Chinese:
- result;
- handoff path;
- files changed;
- tests added/changed;
- seven test categories covered/not applicable;
- verification commands and results;
- docs impact;
- legacy status;
- read model/freshness/operation barrier impact;
- production evidence status;
- remaining risks;
- whether any controller-only files were touched; must be none.

T0 final answer requirements for each controller loop:
Report in Simplified Chinese and include:
- Current branch and pushed commits.
- Worker threads created/read and their status.
- Accepted/rejected/deferred handoffs.
- State-machine rows updated.
- Tests/verification run.
- Local implementation closure status.
- Production evidence classification.
- Next selected boundary or global closure decision.
- Remaining risks.

Begin now:
1. Verify branch/status and pull `origin/dev` if clean.
2. Inventory all `.planning/refactors/**/*.md` files.
3. Read the required documents listed above.
4. Execute a fresh commit-backed reconciliation unless the current HEAD already has a current same-day report that matches live git and state files.
5. Execute `planning:local-modular-code-closure-reconciliation` immediately after commit-backed reconciliation.
   - Verify current size/responsibility of `server.py` and `postgres_repositories/read_models.py`.
   - Identify remaining local module-specific route, service, repository, read model, worker, frontend freshness/barrier and legacy contamination gaps.
   - Insert or reclassify precise local implementation rows if the queue has no pending local-code rows.
6. Generate and run the next safe worker wave or inline controller slice for local modularization code, tests and static guards.
7. Continue local implementation loops until local modular implementation closure is proven.
8. Only then move to production read-only/browser/admin/write validation through the controlled production gate.
9. Continue without asking the user unless a hard stop gate is hit.
```
