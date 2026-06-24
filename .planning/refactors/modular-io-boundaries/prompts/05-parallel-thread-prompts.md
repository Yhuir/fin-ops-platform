# Parallel Thread Prompts

**Status:** Ready for controller-led use
**Source plan:** `../12-PARALLEL-ORCHESTRATION.md`
**Planning input base:** `1402e7c9 docs(server): audit workbench group detail route owner`

## How To Use

Use these prompts only after reading `12-PARALLEL-ORCHESTRATION.md`.

Recommended launch order:

1. Start T0 Controller.
2. Start T1-T8 workers.
3. Let workers auto-progress inside their assigned workstreams.
4. Run T0 Controller again to consume handoffs and update global state.
5. Run T9 Final Closure Audit only after the controller says worker handoffs are accepted.

Workers can auto-progress within their assigned scope. They do not need the user to paste a new prompt for each small internal slice. They must stop when their assigned workstream is complete, blocked, touches controller-only files, or needs reassignment.

Workers do not declare global closure. The controller and final closure audit own that decision.

Do not start T9 while T0-T8 are still running. T9 is a final audit prompt, not a parallel worker prompt.

## Common Worker Rules

All worker prompts inherit these rules:

- Work in `/Users/yu/Desktop/fin-ops-platform`.
- Use branch `dev`.
- Read `AGENTS.md`, `.planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md`, `00-REQUIREMENTS.md`, `03-REFACTOR-STATE-MACHINE.md`, `04-IMPLEMENTATION-ROADMAP.md`, `05-IMPACT-AND-TEST-GATES.md`, `10-AUTONOMOUS-STOP-GATES.md`, and target module docs before edits.
- Use CodeGraph for structural lookup before code changes.
- Follow this work loop inside the assigned workstream: pre-implementation analysis, bounded implementation or evidence collection, self-review, verification, handoff.
- Do not edit controller-only files.
- Do not claim global closure.
- Do not implement Go/Fiber/Go Worker unless the prompt explicitly assigns Go admission and all gates pass.
- Do not perform production writes or read secrets.
- No staging database is available.
- No local `PGSQL_URL` or PostgreSQL URL is available.
- Do not ask the user for staging databases, PostgreSQL URLs, SSH passwords, DB passwords, tokens, cookies or private secrets.
- Missing real PostgreSQL/read model/worker evidence is a soft gate. Record it as `production-evidence-deferred`, `unavailable` or equivalent evidence status and keep working on another safe owned scope.
- Use local/fake/stub tests, contract tests, static guards, API response-shape tests, frontend mocked tests and non-secret production read-only SSH evidence when useful.
- T1-T8 workers may use `ssh finops-prod-root` only for non-secret read-only checks. Do not read or print secrets, DSNs, tokens, cookies, env secret values, private keys or sensitive payloads.
- T1-T8 workers must not execute the Controlled Production Gate. If controlled production evidence is required, stop and request T0 Controller action in the handoff.
- Before editing or commit/push, acquire the write lease: `mkdir /tmp/fin-ops-dev-write.lock`.
- After acquiring the write lease, run `git fetch origin --prune`, `git switch dev`, `git pull --ff-only origin dev`, and confirm a clean `git status --short --branch`.
- Commit/push only verified, bounded, owned changes to `origin/dev`. Every worker commit must be safe to merge into `main` for the completed slice, with old behavior protected by targeted verification or documented as unchanged.
- Always write or update your handoff file under `.planning/refactors/modular-io-boundaries/parallel/handoffs/`.
- Release the write lease with `rmdir /tmp/fin-ops-dev-write.lock`.

## T0 Controller / Integration Prompt

```text
You are Codex working in /Users/yu/Desktop/fin-ops-platform on branch dev.

Objective: act as the parallel orchestration controller for the modular IO refactor. Read:
- AGENTS.md
- .planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md
- .planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md
- .planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md
- .planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md
- .planning/refactors/modular-io-boundaries/08-AUTONOMOUS-RUNBOOK.md
- .planning/refactors/modular-io-boundaries/09-DEV-BRANCH-WORKFLOW.md
- .planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md
- .planning/refactors/modular-io-boundaries/autonomous/STATE.md
- .planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md
- .planning/refactors/modular-io-boundaries/parallel/handoffs/*.md if present

Controller responsibilities:
- Run full state analysis before implementation or state updates.
- Review the previous completed boundary and every new handoff before selecting the next prompt.
- Own all controller-only files listed in 12-PARALLEL-ORCHESTRATION.md.
- Pull origin/dev with --ff-only and verify clean dev.
- Consume worker handoffs.
- Review each worker commit/diff for scope, tests, docs, legacy contamination, read model freshness, operation barrier and stop-gate compliance.
- Accept, reject, or request follow-up for each handoff.
- Own the Controlled Production Gate. T0 may use `ssh finops-prod-root` for bounded production operations only when `12-PARALLEL-ORCHESTRATION.md` gate conditions are met.
- Before any controlled production operation, write a runbook/evidence file that states exact commands, target slice, scope, expected evidence, rollback/cleanup, stop gates and post-checks.
- Prefer dry-run, canary record, test tenant or no-op equivalent. If no safe bounded path exists, record `needs-human-production-gate` or `production-evidence-deferred` instead of forcing the operation.
- Never print or store secrets, DSNs, tokens, cookies, env secret values, private keys or sensitive payloads. Do not perform broad DB mutation, unbounded worker replay, unbounded queue consume, deploy/restart or destructive system/file operations.
- Update STATE.md, MODULE-QUEUE.md, JOURNAL.md, NEXT-PROMPT.md and 04-master-goal-controller.md only after accepting worker evidence.
- Generate the next controller or worker prompt from the current state and accepted handoffs; do not generate next work from stale queue assumptions.
- Keep server-py:workbench-group-detail-route-owner-extraction as the next executable boundary unless accepted handoffs prove a safer next boundary.
- Commit and push controller-only state updates to origin/dev.
- Do not implement runtime code unless no worker is assigned and the next boundary is explicitly controller-owned.

Stop when controller state is updated and pushed, or when a hard stop gate is hit.
```

## T1 Server Route Owner Worker Prompt

```text
You are Codex working in /Users/yu/Desktop/fin-ops-platform on branch dev.

Objective: continue server route-owner extraction without touching controller-only files.

Assigned scope:
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/app/routes_workbench.py and other route modules only when the route is assigned
- workstream-specific tests, preferably new focused tests instead of shared global state tests
- .planning/refactors/modular-io-boundaries/analysis/server-py-*.md for implementation evidence
- docs/modules/reconciliation-workbench/implementation-notes.md or workbench-relations implementation notes when route ownership facts change
- .planning/refactors/modular-io-boundaries/parallel/handoffs/T1-server-route-owner.md

First boundary:
- server-py:workbench-group-detail-route-owner-extraction

Auto-progress:
- After completing the first boundary, continue only to adjacent server route-owner work that touches the same route-owner file family and does not require controller-only state edits.
- If the next action requires MODULE-QUEUE.md, STATE.md, JOURNAL.md, NEXT-PROMPT.md or master prompt edits, stop and record it in the handoff for the controller.

Do not change response shapes, business rules, freshness behavior, relation writes, active generation semantics, Go/Fiber/Go Worker or production state.
```

## T2 Read Model Contract Closure Worker Prompt

```text
You are Codex working in /Users/yu/Desktop/fin-ops-platform on branch dev.

Objective: close read model contract/documentation/test gaps that do not require controller-only state edits.

Assigned scope:
- docs/modules/read-models/
- docs/modules/<read-model-module>/README.md, tests.md, state-machine.md, implementation-notes.md
- backend read model manifest/tests when contracts need executable guards
- .planning/refactors/modular-io-boundaries/analysis/read-model-*.md
- .planning/refactors/modular-io-boundaries/parallel/handoffs/T2-read-model-contracts.md

Targets:
- Verify every page/domain read model has read_model_key, scope_type, partition key, scoped incremental target, full rebuild fallback and freshness proof recorded.
- Identify missing force refresh / operation barrier contracts.
- Add local contract guards only when low risk and isolated.

Do not edit controller-only files or claim module/global closure.
```

## T3 Worker Queue And App Status Worker Prompt

```text
You are Codex working in /Users/yu/Desktop/fin-ops-platform on branch dev.

Objective: audit and harden worker, durable queue, App Status and operation barrier contracts.

Assigned scope:
- docs/modules/runtime-workers/
- docs/modules/app-health-operations/
- docs/modules/domain-events-lifecycle/
- tests for RuntimeQueueRepository, OperationFreshnessBarrierService, worker registry, App Status registry
- backend worker/registry code only when the change is narrow and contract-preserving
- .planning/refactors/modular-io-boundaries/parallel/handoffs/T3-worker-queue-app-status.md

Targets:
- Prove non-transactional refresh uses ReadModelRefreshGateway/scope policy.
- Prove transactional writers use equivalent durable queue contracts.
- Prove operation barrier targets do not get blocked by unrelated scopes.
- Identify missing worker/App Status registry entries.

Do not implement Go Worker. Do not mutate production queue/readiness.
```

## T4 Frontend Freshness And Operation Barrier Worker Prompt

```text
You are Codex working in /Users/yu/Desktop/fin-ops-platform on branch dev.

Objective: audit and harden frontend stale/refreshing/fresh behavior and operation barrier usage.

Assigned scope:
- web/src/features/
- web/src/pages/
- web/src/components/
- web/src/test/ and web/e2e/ tests for assigned pages
- docs/modules/<assigned-page>/tests.md and implementation-notes.md
- .planning/refactors/modular-io-boundaries/parallel/handoffs/T4-frontend-freshness.md

Targets:
- Find pages that can display stale read model payload as fresh.
- Ensure writes wait for returned operation barrier targets or registered read boundaries.
- Prefer tests over broad UI rewrites.

Do not change backend contracts unless explicitly coordinated with controller.
```

## T5 Legacy Contamination Sweep Worker Prompt

```text
You are Codex working in /Users/yu/Desktop/fin-ops-platform on branch dev.

Objective: find and remove or quarantine old code paths that can pollute new module IO boundaries.

Assigned scope:
- workstream-specific legacy analysis files
- focused tests proving no new link calls old internal surfaces
- narrow legacy code removals only when CodeGraph/callers/tests prove no active caller remains
- docs/modules/<affected-module>/implementation-notes.md
- .planning/refactors/modular-io-boundaries/parallel/handoffs/T5-legacy-contamination.md

Targets:
- route/service/repository/read model/frontend API legacy paths
- compat-only paths without owner/caller/deletion condition
- old paths that can still write canonical facts, dirty scopes, outbox, readiness, cache or App Status

Do not remove ambiguous finance behavior. Stop when caller evidence is weak.
```

## T6 Production Read-Only Evidence Worker Prompt

```text
You are Codex working in /Users/yu/Desktop/fin-ops-platform on branch dev.

Objective: collect non-secret, read-only production evidence for deferred modules.

Assigned scope:
- .planning/refactors/modular-io-boundaries/analysis/production-*.md
- docs/operations or docs/modules implementation notes only when recording non-secret evidence
- .planning/refactors/modular-io-boundaries/parallel/handoffs/T6-production-read-only-evidence.md

Allowed:
- ssh finops-prod-root for read-only service/log/file existence/health checks.
- public or non-secret health endpoints.

Forbidden:
- reading or printing secrets, DSNs, tokens, cookies or env secret values;
- production DB writes;
- queue mutation;
- readiness mutation;
- worker replay/consume;
- deploy/restart/systemd mutation;
- OA mutation.

T6 cannot execute controlled production operations. If a deferred module needs production mutation, canary write, queue mutation, worker consume/replay or readiness mutation to close evidence, write a request for T0 Controller in this handoff and stop.

Record evidence as local/fake/stub, production-read-only, unavailable or production-evidence-deferred.
```

## T7 Go Admission Evidence Worker Prompt

```text
You are Codex working in /Users/yu/Desktop/fin-ops-platform on branch dev.

Objective: prepare Go/Fiber/Go Worker admission evidence only. Do not implement Go.

Assigned scope:
- .planning/refactors/modular-io-boundaries/analysis/go-hot-path-*.md
- tests/tools for read-only evidence collection
- docs/modules/runtime-workers/ and relevant module implementation notes
- .planning/refactors/modular-io-boundaries/parallel/handoffs/T7-go-admission-evidence.md

Targets:
- candidate list membership
- performance evidence
- IO contract completeness
- legacy isolation
- freshness proof
- shadow run feasibility
- Python-vs-Go equivalence test plan
- rollback gate
- PostgreSQL dual queue constraints

If any gate fails, record go-candidate-deferred evidence. Do not write Go implementation.
```

## T8 Module IO Contracts Worker Prompt

```text
You are Codex working in /Users/yu/Desktop/fin-ops-platform on branch dev.

Objective: fill or reconcile module IO contracts and test contracts for target modules without changing runtime behavior.

Assigned scope:
- docs/modules/<module>/README.md
- docs/modules/<module>/state-machine.md
- docs/modules/<module>/tests.md
- docs/modules/<module>/implementation-notes.md
- .planning/refactors/modular-io-boundaries/analysis/module-contract-*.md
- .planning/refactors/modular-io-boundaries/parallel/handoffs/T8-module-io-contracts.md

Targets:
- input/output/state/event/read model/permission/test contracts
- public/internal surfaces
- legacy status
- read model refresh and force refresh contracts
- partitioned scoped incremental projection target

Do not edit controller-only files or change runtime behavior.
```

## T9 Final Closure Audit Prompt

```text
You are Codex working in /Users/yu/Desktop/fin-ops-platform on branch dev.

Objective: perform final closure audit only after the controller says worker handoffs are accepted.

Do not run this prompt in parallel with active T0-T8 work. If any worker handoff is missing, incomplete, unaccepted or still being produced, stop and tell the controller which handoff is missing.

Read:
- 12-PARALLEL-ORCHESTRATION.md
- 00-REQUIREMENTS.md
- 03-REFACTOR-STATE-MACHINE.md
- 04-IMPLEMENTATION-ROADMAP.md
- autonomous/STATE.md
- autonomous/MODULE-QUEUE.md
- all parallel handoffs
- relevant docs/modules summaries

Audit every global closure gate. Do not assume completion from passing tests or lack of pending rows.

Produce:
- closure report under .planning/refactors/modular-io-boundaries/analysis/final-closure-audit.md
- explicit pass/fail/deferred status for every global acceptance criterion
- recommended next controller action if anything is incomplete

Do not mark global closure unless every requirement is proven by current evidence.
```
