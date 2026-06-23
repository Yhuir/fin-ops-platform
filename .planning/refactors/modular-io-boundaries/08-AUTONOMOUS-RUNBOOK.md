# Autonomous Runbook

**Purpose:** Define an unattended execution loop for modular IO refactoring.
**Mode:** Best-effort autonomous progress without staging DB or local `PGSQL_URL`.
**Safety rule:** Continue automatically through local/fake/stub validated work; never pretend missing production DB/worker evidence is complete.

## Operating Model

The autonomous loop must optimize for safe forward progress:

- Work on one narrow module boundary at a time.
- Use `dev` as the direct execution branch, never `main`.
- Use the main repository directory; do not create a new worktree.
- Start only after the main repository working tree is clean and current `main` has been pushed.
- Prefer tests and contracts over broad rewrites.
- Remove or quarantine legacy paths as part of the same module slice.
- Treat read model force refresh and freshness proof as production-grade contracts, not UI-level patches.
- Treat Go / Go Fiber / Go Worker as candidate-gated hot-path carve-out only.
- Do not introduce Go for modules outside `11-GO-HOT-PATH-CARVE-OUT.md`.
- Treat `.planning/ROADMAP.md`, `04-IMPLEMENTATION-ROADMAP.md`, and `autonomous/MODULE-QUEUE.md` as separate progress sources; never collapse them into a single unqualified completion percentage.
- If roadmap/status/prompt files disagree, run a planning-state reconciliation slice before implementation.
- Treat queue status as slice status, not module closure. Analysis/guard/inventory/regression slices can be closed while implementation closure remains open.
- Do not select Go hot-path candidates while implementation-pending or implementation-gap-open boundaries remain ahead of them.
- Commit and push only passing, reviewable slices.
- Do not require staging DB or local `PGSQL_URL`.
- `finops-prod-root` is available for privileged read-only checks.
- Do not perform production writes.
- If production evidence is unavailable, record it and continue to the next safe module.

## Required Inputs

The agent must read these files before starting:

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `.planning/ROADMAP.md`
- `.planning/refactors/README.md`
- `docs/app-architecture/README.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/modules/README.md`
- `.planning/refactors/modular-io-boundaries/README.md`
- `.planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md`
- `.planning/refactors/modular-io-boundaries/02-MODULE-IO-CONTRACT-TEMPLATE.md`
- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`
- `.planning/refactors/modular-io-boundaries/09-DEV-BRANCH-WORKFLOW.md`
- `.planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md`
- `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`

## Loop Summary

```text
Preflight
  -> Planning-state reconciliation check
  -> Select next executable boundary
  -> Audit current module IO
  -> Fill or update module contract
  -> Add/update tests
  -> Implement narrow refactor
  -> Run verification
  -> Review diff and impact
  -> Update docs/state
  -> Commit
  -> Push to Dev branch
  -> Generate next prompt
  -> Continue
```

## Preflight

1. Confirm the main repository working tree is clean.
2. Fetch origin and align `dev` with `origin/main` according to `09-DEV-BRANCH-WORKFLOW.md`.
3. Switch to `dev`.
4. Confirm branch is `dev`, not `main`.
5. Confirm no secret values are present in planned commands.
6. Read `.planning/ROADMAP.md`, `04-IMPLEMENTATION-ROADMAP.md`, `autonomous/STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, and `NEXT-PROMPT.md`; if current state, next boundary, status labels or completion metric sources disagree, select a `planning:state-reconciliation-*` slice before normal implementation.
7. Run a cheap sanity check:

```bash
git status --short
python3 --version
node --version || true
```

If the main repository is dirty or `dev` cannot be aligned safely, stop. That is a hard safety gate.

## Boundary Selection

Pick the first boundary in `autonomous/MODULE-QUEUE.md` whose status is `pending` or `deferred-retry`.

Default order is the table order in `autonomous/MODULE-QUEUE.md`. Do not use a hard-coded historical list.

Skip `blocked-by-prerequisite` items. In particular, Go hot-path candidates stay blocked until all admission prerequisites in `11-GO-HOT-PATH-CARVE-OUT.md` are satisfied and no earlier implementation-pending modular IO boundary remains.

Do not treat these statuses as module implementation closure:

- `analysis-closed`
- `contract-guard-closed`
- `static-guard-closed`
- `regression-guard-closed`
- `route-guard-closed`
- `inventory-guard-closed`
- `planning-closed`

Skipped modules must be marked in `autonomous/STATE.md` with a reason.

## Per-Module Cycle

### 1. Audit

For the selected module:

- Read `docs/modules/<module>/README.md`.
- Read `state-machine.md`, `tests.md`, `e2e-spec.md`, `e2e-coverage.md` if present.
- Use CodeGraph for structural lookup.
- Use `rg` only for literal text and test discovery.
- Produce or update an audit file under `.planning/refactors/modular-io-boundaries/analysis/`.

### 2. Contract

Fill the relevant parts of `02-MODULE-IO-CONTRACT-TEMPLATE.md`.

The contract must cover inputs, outputs, state, events, read models, force refresh, legacy retirement/quarantine, permissions, audit records, public/internal surfaces, testing contract, and environment limitations.

If the selected boundary is a Go candidate, the contract must also cover candidate key, Go shape, Fiber usage, Python reference implementation, shadow run, Python-vs-Go equivalence, PostgreSQL dual queue, double-write prevention and rollback.

### 3. Tests First

Before code migration, add or update the smallest useful tests:

- Business core tests when rules or state transitions are touched.
- Service/API tests for contract and orchestration.
- Read model/queue fake tests when real DB is unavailable.
- Cross-page freshness tests when a write affects read models used by more than one page.
- Legacy contamination tests or import/call graph checks when old paths are removed or quarantined.
- Partitioned scoped incremental projection tests for read model boundaries.
- Python-vs-Go equivalence and shadow-mode tests for Go candidates.
- Frontend interaction tests for user-visible behavior.
- Regression tests for existing behavior.

No staging DB or `PGSQL_URL` is required. Use fakes/stubs and existing test helpers.

### 4. Implement

Implement only the selected boundary.

Allowed:

- Move route mapping to an existing route module.
- Extract command/query/service boundary when it removes real coupling.
- Add a typed contract/helper if it replaces duplicated implicit behavior.
- Normalize read model refresh through existing gateway boundaries.
- Add or tighten force refresh entry only through a validated gateway/runbook/API contract.
- Add or tighten partitioned scoped incremental projection contracts.
- Evaluate Go candidate admission for listed hot paths.
- Delete old code paths when tests prove no caller remains.
- Quarantine retained legacy paths as `compat-only` when deletion is blocked by compatibility or production evidence.
- Split frontend API/types/view-model code when tests protect behavior.

Forbidden:

- Broad file splitting for line-count optics.
- Changing business behavior without explicit requirement and tests.
- Leaving an active old write path that can update canonical facts, dirty scopes, outbox, readiness, cache, or App Status.
- Letting new code call old module internals or legacy fallbacks.
- Adding page-level "refresh everything" behavior instead of fixing scope/freshness contracts.
- Implementing Go/Fiber/Go Worker outside the candidate list.
- Implementing Go before performance evidence, IO contract, shadow run and rollback gates pass.
- Running long background work inside a Fiber request handler.
- Letting Python and Go workers both ack or publish the same authoritative event/scope.
- Production writes.
- Secret handling changes without a dedicated security plan.
- Main branch commits.

### 5. Verify

Run the smallest sufficient verification set:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
PYTHONPATH=backend/src python3 -m unittest <targeted-tests> -v
cd web && npm test -- <targeted-tests>
cd web && npm run build
```

If a real PostgreSQL/read model/worker check would normally be required, replace it with repository fake/stub tests, gateway contract tests, force refresh contract tests, partition/scope contract tests, API response shape tests, cross-page freshness regression tests, Python-vs-Go equivalence tests for Go candidates, and production read-only evidence if available through `ssh finops-prod-root` without reading secrets or writing production state.

Do not block on missing staging DB or missing `PGSQL_URL`.

### 6. Review

Before commit:

- Inspect `git diff`.
- Confirm no unrelated files are staged.
- Run a secret scan over changed files.
- Confirm removed legacy paths are not referenced; if retained, confirm they are `compat-only` with deletion conditions.
- Confirm no old module can write into new canonical/read model/refresh paths.
- Confirm read model freshness proof and force refresh behavior are tested or explicitly not applicable.
- Confirm partitioned scoped incremental projection is registered or explicitly not applicable.
- For Go candidates, confirm candidate list membership, admission evidence, shadow mode, double-write prevention and rollback.
- Confirm docs impact is handled.
- Confirm state machine status is updated.

### 7. Commit And Push

Commit only passing, reviewable slices.

Commit message format:

```text
refactor(<module>): tighten <boundary> IO contract
```

Push to the configured Dev branch only.

### 8. Continue

After a successful commit/push:

- Mark the boundary with the most specific slice status, for example `analysis-closed`, `contract-guard-closed`, `static-guard-closed`, `regression-guard-closed`, `inventory-guard-closed`, `planning-closed`, `production-evidence-deferred`, `go-candidate-deferred`, or `needs-human-production-gate`.
- Update the separate `Module Closure` value in `MODULE-QUEUE.md`; do not claim `closed` unless the module completion definition in `00-REQUIREMENTS.md` and `03-REFACTOR-STATE-MACHINE.md` is met.
- Append a journal entry.
- Generate next prompt into `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`.
- Continue to the next boundary.

## No-Staging Policy

No staging DB and no local `PGSQL_URL` are not hard blockers.

The autonomous loop must proceed using local static checks, local fake/stub tests, API contract tests, frontend tests, and non-privileged production read-only SSH checks when useful.

The loop must not claim real production DB/worker proof unless such proof was actually collected.

## SSH Policy

Current known SSH state:

- `ssh finops-prod` works as `finops-deploy`.
- `finops-deploy` has no passwordless sudo.
- `ssh finops-prod-root` works as root with key login.

Allowed:

- Non-secret, privileged read-only checks through `finops-prod-root`.
- HTTP health checks that do not need token/cookie.

Forbidden:

- Production writes.
- Reading secrets.
- Printing DSNs, tokens, cookies or env secret values.
- Asking the user for passwords.
- Recording credentials.

## Failure Handling

If a module fails after reasonable repair attempts:

1. Save failure notes in `autonomous/STATE.md`.
2. Do not commit broken code.
3. Stash only the failed module changes if needed.
4. Continue to the next independent module.

Only hard stop gates in `10-AUTONOMOUS-STOP-GATES.md` may end the run.

## Go Candidate Handling

If a selected boundary is a Go hot path:

1. Read `11-GO-HOT-PATH-CARVE-OUT.md`.
2. Confirm the candidate key is listed.
3. Collect or reference performance evidence.
4. Fill Go carve-out contract in `02-MODULE-IO-CONTRACT-TEMPLATE.md`.
5. Add tests before implementation.
6. Start with shadow mode; do not publish authoritative Go output until equivalence passes.
7. If any admission gate fails, mark `go-candidate-deferred` and continue with Python boundary hardening or the next module.
