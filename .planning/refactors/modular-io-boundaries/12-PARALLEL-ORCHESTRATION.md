# Parallel Orchestration Workflow

**Status:** Planning slice complete
**Purpose:** Allow multiple Codex threads to work toward modular IO closure without corrupting `dev`, global state files, or module ownership boundaries.
**Applies to:** `.planning/refactors/modular-io-boundaries/`, `backend/`, `web/`, `tests/`, `docs/modules/`

## Decision

Parallel execution is allowed only as controller-led orchestration.

Do not run several autonomous master controllers against the same `dev` branch. The existing autonomous flow is intentionally single-queue and updates shared state files on every slice. Multiple uncoordinated controllers would conflict on:

- `autonomous/STATE.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`
- shared static guard tests
- shared files such as `backend/src/fin_ops_platform/app/server.py`

The parallel model is:

```text
Controller thread
  owns global state, dev integration, queue accounting and final closure

Worker threads
  own bounded workstreams, local code/docs/tests inside assigned file scope,
  write handoff reports, and may push direct-dev commits only under the write lease
```

## Auto-Progress Semantics

Worker prompts are autonomous inside their assigned workstream. A worker may continue through multiple narrow slices in that workstream when all of the following are true:

- the next slice is inside the same assigned file ownership,
- no controller-only file must be changed,
- no hard stop gate is hit,
- verification passes,
- the worker can acquire the direct-dev write lease before editing and before commit/push.

Worker prompts do not automatically close the global refactor. When a worker reaches the end of its assigned scope, it must stop after writing its handoff report and, if it made changes, committing/pushing its verified direct-dev slice.

The controller prompt is autonomous across the whole refactor. It consumes worker handoffs, reconciles `dev`, updates global state, assigns more work if needed, and runs final closure audit. If all worker prompts finish, the user should run the controller/final-closure prompt once more unless the controller thread has stayed active and already consumed every handoff.

## Environment Policy

All controller and worker prompts inherit the no-staging operating model:

- No staging database is available.
- No local `PGSQL_URL` or PostgreSQL URL is available.
- Prompts must not ask the user for staging databases, PostgreSQL URLs, SSH passwords, DB passwords, tokens, cookies or private secrets.
- Missing real PostgreSQL/read model/worker evidence is a soft gate, not a hard blocker. Record it as `production-evidence-deferred`, `unavailable` or equivalent evidence status and continue to the next safe owned scope.
- Use local/fake/stub tests, contract tests, static guards, API response-shape tests, frontend mocked tests and production read-only SSH evidence where useful.
- `ssh finops-prod-root` may be used only for non-secret read-only checks such as service status, non-secret logs, deployed file existence, public/non-secret health endpoints and read-only runtime status.
- Production writes, DB writes, queue mutation, readiness mutation, worker replay/consume, systemd mutation, deploy/restart, secret reads and OA mutation are forbidden in the parallel workflow unless a separate human production gate explicitly approves them.

## Controller Permissions

Only the controller may edit these files:

- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/prompts/04-master-goal-controller.md`
- `.planning/refactors/modular-io-boundaries/prompts/05-parallel-thread-prompts.md`
- `.planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md`
- any future global progress/completion percentage document

The controller also owns:

- direct-dev write lease arbitration,
- global queue row insertion/reclassification,
- final decision on whether a worker result is accepted,
- final closure audit,
- merge from `origin/main` into `dev`,
- conflict resolution policy,
- production evidence classification,
- Go candidate admission/defer decisions.

The controller may edit worker handoff files only when reconciling or archiving completed work.

## Worker Permissions

Workers may:

- read all repository docs and code;
- edit only their assigned file ownership;
- add workstream-specific analysis files;
- add workstream-specific tests;
- add or update `docs/modules/<assigned-module>/implementation-notes.md` when the assigned work changes module facts;
- write one handoff report under `.planning/refactors/modular-io-boundaries/parallel/handoffs/`;
- commit and push to `origin/dev` only after acquiring the direct-dev write lease.

Workers must not:

- edit controller-only files;
- edit another worker's handoff;
- renumber `MODULE-QUEUE.md`;
- change global state-machine semantics;
- claim global closure;
- implement Go/Fiber/Go Worker unless explicitly assigned by the controller and the admission gates are already satisfied;
- perform production writes or read secrets;
- push to `main`;
- rebase, reset, force-push, delete branches or run destructive git operations.

## Direct-Dev Write Lease

Because workers share `dev`, write access must be serialized even when analysis can run in parallel.

Before editing or committing, a worker must acquire this local lock:

```bash
mkdir /tmp/fin-ops-dev-write.lock
```

If the directory already exists, the worker must wait or stop with `handoff_status=waiting_for_dev_write_lease`. It must not edit files while waiting.

After acquiring the lock, a worker must run:

```bash
cd /Users/yu/Desktop/fin-ops-platform
git fetch origin --prune
git switch dev
git pull --ff-only origin dev
git status --short --branch
```

It may proceed only if the branch is `dev` and the working tree is clean.

Before commit, the worker must run targeted verification plus:

```bash
bash scripts/verify.sh docs
git diff --check
git status --short
```

After pushing, or after deciding to stop without edits, the worker must release the lock:

```bash
rmdir /tmp/fin-ops-dev-write.lock
```

If a worker crashes while holding the lock, only the controller may remove the stale lock after verifying no process is actively writing and `git status --short --branch` is safe.

## File Ownership

The initial parallel workstreams are:

| Thread | Workstream | Primary ownership | Forbidden shared files |
| --- | --- | --- | --- |
| T0 | Controller / Integration | controller-only files, global state, final closure | none |
| T1 | Server route owner | `backend/src/fin_ops_platform/app/server.py`, route modules for assigned server routes, workstream-specific tests | controller-only files |
| T2 | Read model contract closure | `docs/modules/read-models/`, read model manifest/tests, module read model docs | controller-only files, `server.py` unless assigned |
| T3 | Worker queue/App Status | runtime worker docs, worker registry tests, queue/operation barrier tests | controller-only files |
| T4 | Frontend freshness/barrier | `web/src/features/`, `web/src/pages/`, frontend tests for assigned pages | controller-only files, backend runtime code unless assigned |
| T5 | Legacy contamination sweep | workstream-specific legacy analysis/tests, assigned legacy code paths | controller-only files, unrelated module code |
| T6 | Production read-only evidence | read-only runbooks and evidence reports only | code, tests, controller-only state |
| T7 | Go admission evidence | Go admission analysis, evidence tooling/tests only | Go implementation files unless admission passes |
| T8 | Module docs/contracts | `docs/modules/<assigned-module>/`, module IO contract analysis | controller-only files |
| T9 | Final closure audit | closure report after controller requests it | code files before controller request |

Any file ownership conflict must stop the worker. The controller decides whether to reassign the file or serialize the work.

## Commit And Push Order

Workers that produce code changes may commit directly to `dev` only under the write lease and only when their changes are isolated. Commit messages should include the workstream:

```text
refactor(<module>): <bounded change>
docs(<module>): <bounded audit or contract>
test(<module>): <bounded guard or regression>
```

Workers must push only:

```bash
git push origin dev
```

The controller should periodically:

```bash
git fetch origin --prune
git switch dev
git pull --ff-only origin dev
```

Then it reviews worker commits and updates controller-only global state files in a separate controller commit.

## Worker Handoff Format

Each worker must write exactly one handoff file:

```text
.planning/refactors/modular-io-boundaries/parallel/handoffs/T<n>-<workstream>.md
```

Required content:

```markdown
# T<n> <Workstream> Handoff

**Status:** completed / partial / blocked / no-op
**Branch:** dev
**Base commit:** <commit>
**Head commit:** <commit or none>
**Files changed:** ...
**Controller-only files touched:** must be none

## Scope

## Evidence Read

## Work Completed

## Tests Added Or Changed

## Verification Commands

## Seven Test Categories

## Docs Impact

## Legacy Status

## Read Model / Freshness / Operation Barrier Impact

## Production Evidence Status

## Risks And Follow-up For Controller
```

Workers must not edit `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` or the master controller prompt to record their own completion. The handoff is the worker's source of truth until the controller accepts it.

## Final Closure Audit Gate

The controller may claim global closure only after all of these are proven from current state:

- no unsafe pending work remains in `MODULE-QUEUE.md`;
- every target module has an IO contract or a documented not-applicable reason;
- every target module has a test contract or a documented not-applicable reason;
- legacy paths are removed, quarantined or `compat-only` with owner/caller/deletion-condition evidence;
- old paths cannot write canonical facts, dirty scopes, outbox events, read model readiness, cache or App Status;
- read model force refresh, freshness proof and operation barrier contracts are documented and locally tested where applicable;
- all page/domain read models have partition key, scope key, scoped incremental projection target and full rebuild fallback condition recorded;
- Workbench active generation exception remains explicit and tested;
- Go/Fiber/Go Worker candidates are either admitted with evidence, deferred with evidence, or rejected with evidence;
- worker target state and PostgreSQL dual queue constraints are documented;
- controller has consumed every worker handoff;
- targeted tests and docs verification have run;
- missing production evidence is explicitly `production-evidence-deferred`, not silently accepted as closed;
- final closure report states which evidence is local/fake/stub, production read-only, or deferred.

If any item is incomplete, the controller must continue or produce a new bounded prompt. It must not mark the refactor globally closed.
