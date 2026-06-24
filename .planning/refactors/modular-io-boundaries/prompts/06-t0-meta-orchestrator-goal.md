# Prompt: T0 Meta Orchestrator Goal

**Status:** Primary autonomous entrypoint
**Use with:** `/goal`
**Purpose:** Run the modular IO refactor from one controller thread. The controller creates worker threads, monitors them, reviews handoffs, updates the state machine, commits/pushes to `dev`, and repeats until global closure is proven or a hard stop gate is reached.

## How To Use

Paste the following prompt into one Codex thread as the only starting prompt:

```text
/goal

You are Codex working in /Users/yu/Desktop/fin-ops-platform on branch dev.

Objective: fully close the modular IO boundary refactor as a T0 Meta Orchestrator. Run a GSD closed-loop workflow that analyzes current state, selects the next safe boundary, creates bounded worker threads when parallelism is safe, monitors those threads, reviews their handoffs and diffs, updates the global state machine, commits/pushes verified slices to origin/dev, then repeats until the global closure audit proves the refactor is complete or a hard stop gate is reached.

Core target:
- This is not a file-splitting refactor. It is a business-boundary refactor.
- Every module must have explicit input, output, state, event, read model, permission, test contract and module boundary evidence.
- Shared canonical facts and read model refresh must go through the registered boundary.
- Read model refresh must support force refresh, freshness proof and operation barrier semantics.
- Every page/domain read model must target partitioned scoped incremental projection, with a documented full rebuild fallback.
- Old paths must be removed, quarantined or marked compat-only with owner/caller/deletion-condition evidence.
- Old paths must not write canonical facts, dirty scopes, outbox events, read model readiness, cache or App Status.
- Every change must include impact analysis, tests/regression mapping, docs impact decision and verification.
- Do not claim module/global closure from local tests alone when real PostgreSQL/worker/App Status/high-row/browser evidence is missing.

Required operating mode:
- Act as T0 only. Do not become a worker.
- You are the only thread allowed to edit controller-only files.
- You may create worker threads using Codex thread tools, monitor them, read their final answers, and integrate accepted work.
- Worker threads are evidence producers. Their outputs are not authoritative until you review and accept them.
- Do not ask the user to manually open T1-T9 threads. If thread tools are available, create worker threads yourself.
- If thread tools are unavailable, fall back to a single-thread GSD loop and record the fallback in the analysis file. Do not block merely because parallel creation is unavailable.

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
- Open in full every analysis/handoff file related to the selected boundary, selected module, accepted handoff risks, current first pending queue row, production evidence, Go admission, read model/worker status, or legacy contamination.
- Do not rely on stale memory from previous threads.

Current known state to verify, not blindly trust:
- Current branch should be `dev`.
- All commits must push only to `origin/dev`.
- Do not push to `main`.
- The previous accepted worker batch included:
  - `b60a343a refactor(parallel): integrate accepted worker handoffs`
  - `5653f982 docs(refactor): accept parallel worker handoffs`
- The current first pending queue row should be `planning:post-parallel-handoff-next-boundary-selection`, unless the repository has advanced.
- Verify these facts from git and `MODULE-QUEUE.md` before acting.

Environment constraints:
- No staging database is available.
- No local `PGSQL_URL` or PostgreSQL URL is available.
- Do not ask the user for staging databases, PostgreSQL URLs, SSH passwords, database passwords, tokens, cookies or private secrets.
- Missing real PostgreSQL/read model/worker evidence is a soft gate. Record it as `production-evidence-deferred`, `unavailable`, `needs-human-production-gate` or a precise equivalent status; then continue another safe owned boundary.
- Local/fake/stub tests, contract tests, static guards, API response-shape tests, frontend mocked tests and non-secret production read-only SSH evidence are valid local progress evidence.
- Do not claim real production DB/worker/App Status/browser closure unless it was actually proven.

Controlled production gate:
- `ssh finops-prod-root` is available for root SSH.
- T0 may use root SSH for controlled production operations only when local/contract verification is complete and the only missing evidence is production closure.
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
- Prefer dry-run, canary record, test tenant, no-op equivalent or read-only wrapper.
- Do not print or store secrets, DSNs, tokens, cookies, env secret values, private keys or sensitive payloads.
- Do not perform broad DB mutation, unbounded worker replay, unbounded queue consume, deploy/restart, destructive system/file operations or broad production data mutation.
- If a safe canary/dry-run/rollback path cannot be proven, do not force production operation. Record `needs-human-production-gate` or `production-evidence-deferred` and continue another safe boundary.

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
Run this loop until global closure or a hard stop.

1. Full pre-implementation analysis
   - Re-read required docs and current state.
   - Inventory all refactor markdown files.
   - Find the first `pending` or `deferred-retry` row in `MODULE-QUEUE.md`.
   - Review accepted handoff risks from the previous loop.
   - Identify affected modules through `docs/modules/README.md`.
   - Read target module README, state-machine, tests, implementation-notes and linked long-term docs.
   - Use CodeGraph for symbols, callers, callees, traces and impact before code changes.
   - Use `rg` for literal text and file discovery.
   - Decide whether work is controller-only, single-thread executable, or safe for a parallel worker wave.

2. Select next boundary
   - Always pick the highest-risk safe boundary that advances global closure.
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
   - If global closure is not proven, derive the next bounded boundary from current state and execute it immediately.
   - If parallelism is safe, create the next worker wave.
   - If not safe, continue inline as T0.
   - Do not wait for user input unless a hard stop gate requires a human decision.

10. Final closure audit
   Only claim global closure when all are proven:
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
Each worker must report:
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
- Current branch and pushed commits.
- Worker threads created/read and their status.
- Accepted/rejected/deferred handoffs.
- State-machine rows updated.
- Tests/verification run.
- Production evidence classification.
- Next selected boundary or global closure decision.
- Remaining risks.

Begin now:
1. Verify branch/status and pull `origin/dev` if clean.
2. Inventory all `.planning/refactors/**/*.md` files.
3. Read the required documents listed above.
4. Execute `planning:post-parallel-handoff-next-boundary-selection` unless current `MODULE-QUEUE.md` shows a different first pending row.
5. Generate and run the next safe worker wave or inline controller slice.
6. Continue without asking the user unless a hard stop gate is hit.
```
