# Prompt: Read Model Main Branch Closure Controller

**Status:** User-authorized specialized entrypoint
**Use with:** `/goal`
**Purpose:** Run a high-throughput GSD controller on `main` to finish the Read Model modularization closure for all page/domain read models. This prompt is for keeping read models and making them fully modular PSCIP systems. It is not the Direct API read-model removal prompt.

## Core Objective

Complete full Read Model modularization closure.

Every page/domain read model must have a clear module boundary, I/O contract, physical owner, scoped incremental projection path, freshness/readiness proof, production evidence, and no known stale-as-fresh behavior.

Default target state:

- Partitioned + Scoped + Incremental Projection.
- Explicit exceptions are allowed only when manifest, docs, tests, runtime behavior and production evidence prove the exception is safe.
- Final closure means PSCIP-L4 for every non-exception read model, and equivalent L4 proof for each exception.

## Throughput Mandate

This run must optimize for short elapsed time.

- Do not run one tiny read model slice, verify, then repeat.
- Do not create one prompt per field, helper, or module when the same boundary exists across many modules.
- Work in macro-waves. Each wave should close one whole boundary class across all affected read models, or at least a coherent group of high-impact modules.
- Prefer bulk scans, bulk edits, grouped commits and grouped verification.
- Verification happens at wave gates, not after every small edit. Use quick syntax/import checks during editing only when they prevent wasted work.
- A wave should normally touch multiple read models, multiple files, or one entire shared surface. If a wave touches only one small file, record why batching was unsafe.
- Do not use broad refactors without a boundary. The batch must still have one owner, one rollback point and one acceptance checklist.

Recommended macro-wave order:

1. Global state reconciliation and gap matrix.
2. Manifest/App Status/worker/RabbitMQ/scope-policy/doc parity for all read models.
3. Physical SQL owner and repository port closure for all non-exception read models.
4. Refresh producer and derived lifecycle convergence for all read models.
5. Query fresh-gate and stale-as-fresh closure for all read APIs.
6. Incremental projection builder and parent/all aggregate closure.
7. Operation barrier/write response target closure.
8. Frontend stale/refreshing/fresh behavior closure for all affected pages.
9. Legacy path retirement/quarantine from `server.py`, old services, old tools and old runbooks.
10. Worker/readiness/runtime convergence.
11. Production or equivalent runtime evidence sweep.
12. Global closure audit and final report.

## Main Branch Rules

This is a user-authorized exception to the dev-branch workflow.

- Start on `main`.
- Ensure `main` is clean and fast-forward synced with `origin/main`.
- Create and push a backup branch before the first implementation commit.
- Work directly on `main`.
- Never force-push.
- Never rewrite history.
- Never commit unrelated dirty files.
- Commit only verified, reviewable macro-wave results.
- If push is rejected, fetch and only fast-forward or do a safe conflict-free normal merge. Finance/read-model/worker/permission/migration conflicts are a hard stop.

Required start:

```bash
git status --short --branch
git fetch origin --prune
git switch main
git pull --ff-only origin main
backup_branch="codex/backup-main-before-read-model-closure-$(date +%Y%m%d-%H%M%S)"
git branch "$backup_branch"
git push origin "$backup_branch"
```

## Required Context

Read these before editing:

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/index.md`
- `docs/app-architecture/README.md`
- `docs/app-architecture/pages.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/modules/README.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/read-models/tests.md`
- `docs/operations/runtime-worker-governance.md`
- `.planning/refactors/README.md`
- `.planning/refactors/modular-io-boundaries/README.md`
- `.planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md`
- `.planning/refactors/modular-io-boundaries/01-CURRENT-STATE-AUDIT.md`
- `.planning/refactors/modular-io-boundaries/02-MODULE-IO-CONTRACT-TEMPLATE.md`
- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`
- `.planning/refactors/modular-io-boundaries/07-DOCS-GOVERNANCE.md`
- `.planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- All latest analysis/handoff files relevant to read-model closure and production evidence.

Use CodeGraph before code edits:

- `codegraph_status` first.
- `codegraph_context` for read-model architecture.
- `codegraph_trace` for write -> dirty/outbox -> worker -> projection -> readiness -> API flows.
- `codegraph_impact` before modifying shared symbols.
- Use `rg` for literal strings, routes, fields, env keys, read model keys and legacy labels.

## Definition Of Done

Final global closure requires all of these:

1. `READ_MODEL_MANIFEST` covers all page/domain read models and matches App Status registry, worker registry, RabbitMQ dispatch, scope policy, docs and tests.
2. Every read model has an explicit contract:
   - read_model_key
   - scope_type
   - partition key
   - scoped incremental projection strategy
   - all/parent scope semantics
   - source_versions/schema_version proof
   - freshness/readiness proof
   - query owner
   - route/API owner
   - service owner
   - repository port owner
   - physical SQL owner
   - refresh producer owner
   - worker owner
   - force refresh entry
   - operation barrier targets
   - frontend stale/refreshing/fresh behavior
   - permission/audit owner
   - tests
   - legacy path status
3. Non-exception read models reach PSCIP-L4.
4. Exception read models reach equivalent L4 and their exception semantics are proved.
5. No known stale-as-fresh path remains.
6. No page hot path falls back to unbounded live scan, full snapshot scan, or fake fresh all-scope.
7. Production or equivalent runtime evidence is collected and stored in a repo report.

## PSCIP Levels

- PSCIP-L0 contract-only: manifest/docs only. Not implementation complete.
- PSCIP-L1 guarded contract: manifest, scope policy, worker registry, docs and guard tests aligned. Not implementation complete.
- PSCIP-L2 local runtime: route/query/service/refresh/worker run by scope; fake/stub/API tests prove no stale-as-fresh. Local implementation only.
- PSCIP-L3 physical modularization: repository port, physical SQL owner, projection builder, refresh producer, worker/readiness and frontend barrier converge by read-model owner; legacy is deleted or compat-only guarded. This is the minimum local implementation closure.
- PSCIP-L4 production evidence: production or equivalent runtime proves App Status, dirty/outbox, worker/readiness, key page APIs and high-row queries converge by scope. This is the minimum global closure.

## PSCIP Contract Rules

Partitioned:

- Projection storage, readiness, source_versions, schema_version, row_count, generated_at and errors are partitioned by bounded business keys.
- Partition key must come from business facts: month, account, direction/filter/month, status group, domain object, config version, all-only scope or explicit exception.
- Page hot paths read target partitions/scopes or materialized parent aggregates only.
- SQL/indexes match scope key, filters, sorting and pagination.

Scoped:

- Query, write result, dirty scope, outbox event, worker job, force refresh, operation barrier target and frontend refetch map to explicit `scope_type + scope_key`.
- Scope passes through `ReadModelScopePolicyRegistry` normalize/validate/dedupe.
- Illegal scope fails fast. It must not degrade to broad `all`.
- `all` is one of: fan-out command, queryable parent aggregate, active-generation aggregate, all-only projection, or forbidden.
- Fan-out-only `all` must not publish fake fresh readiness.

Incremental:

- Normal writes calculate affected scopes and rebuild only affected projection partitions plus necessary parent aggregates.
- Builder/worker is idempotent and supports scoped upsert/delete/prune/retry.
- source_versions/schema_version publish with projection.
- dependency-not-fresh defers/retries. It must not write failed/fresh.
- Full rebuild is only for cold start, backfill, repair, migration or explicit runbook force refresh.

## Exceptions

Allowed known exceptions:

- `workbench`: active generation atomic publish.
- `bank_account_balance`: all-only scoped projection.
- `pending_invoice`: page-first explicit scopes, bare `all` forbidden.
- `cost_statistics`: month shards plus queryable parent aggregate.

Any new exception must update manifest, scope policy, worker/readiness, docs, tests and production evidence.

## Production Verification Is Required

Production validation is in scope for this prompt.

You may use:

- Approved GitHub credentials already configured in the environment.
- Root SSH to the production server when needed.
- Read-only DB/App Status/systemd/worker/log/query-plan checks.
- Bounded production operations only when backed by committed migration or written runbook with explicit scopes, rollback/cleanup and post-checks.
- Admin HTTP/API probes when the user provides an admin token through a secure prompt.

Production evidence must include:

- Current deployed commit and whether it includes the closure commits.
- `/health` and `/health/ready`.
- App Status read model domains/scopes.
- dirty/outbox current-effective blockers.
- readiness rows and source/schema versions.
- worker/service status and recent restart/log evidence.
- key page API smoke for every read model family.
- high-row query plan or latency/performance sample for Workbench, Search, Bank Details, No-OA, Turnover, Cost, Tax and invoice families.
- browser evidence when a production browser runner exists.
- admin-scope evidence when admin token is provided.
- controlled write apply evidence when the user approves exact reversible business objects and rollback/audit acceptance.

## Admin Token Secure Prompt

When an admin token is needed, do not ask the user to paste it in normal chat and do not write it to files.

Use the first available secure path:

1. Codex app popup / secure user input tool if available. Prompt text: `Paste FIN_OPS_HTTP_SLO_ADMIN_TOKEN for this run only`.
2. macOS hidden dialog:

```bash
ADMIN_TOKEN="$(osascript \
  -e 'set r to display dialog "Paste FIN_OPS_HTTP_SLO_ADMIN_TOKEN for this run only" default answer "" with hidden answer buttons {"OK", "Cancel"} default button "OK"' \
  -e 'text returned of r')"
```

3. Terminal fallback:

```bash
stty -echo
printf "FIN_OPS_HTTP_SLO_ADMIN_TOKEN: "
IFS= read -r ADMIN_TOKEN
stty echo
printf "\n"
```

Token handling rules:

- Never print token, cookie, Authorization header, DSN, private key or secret env value.
- Do not commit or store token.
- Use command-local env only: `FIN_OPS_HTTP_SLO_ADMIN_TOKEN="$ADMIN_TOKEN" <probe command>`.
- `unset ADMIN_TOKEN` after the probe.
- Disable shell tracing around token handling.

## Production Operation Rules

Root SSH is allowed for production verification and bounded production operation, but not for manual state hacking.

Allowed:

- Read systemd status and logs.
- Read App Status/health APIs.
- Run committed read-only probe scripts.
- Apply committed migrations through the project deploy/runbook path.
- Run committed bounded repair/backfill/force-refresh commands with explicit scopes and post-checks.
- Restart specific services only when a runbook says so and pre/post health checks are recorded.

Forbidden:

- Printing secrets or raw broad business payloads.
- Manual DB edits to canonical facts.
- Manual readiness/outbox/dirty-scope updates to fake freshness.
- Unbounded truncate/rebuild/force refresh.
- Ad hoc production script not committed or recorded as a runbook.
- Destructive operation without rollback path and explicit scope.

## Initial Reconciliation Report

Before implementation, create:

`.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-<date>.md`

The report must include:

1. Current main commit and backup branch.
2. Current 14-read-model closure matrix with:
   - key
   - page/domain
   - strategy
   - exception status
   - query owner
   - route/API owner
   - repository port owner
   - physical SQL owner
   - refresh producer owner
   - worker owner
   - freshness proof
   - PSCIP level
   - partition storage proof
   - scoped query proof
   - incremental builder proof
   - index/query-plan/performance proof
   - force refresh
   - operation barrier
   - frontend behavior
   - legacy path status
   - production evidence status
3. Classification for each read model:
   - `closed`
   - `local-implementation-closed-production-evidence-needed`
   - `needs-repository-physical-split`
   - `needs-refresh-producer-convergence`
   - `needs-query-fresh-gate-convergence`
   - `needs-operation-barrier-closure`
   - `needs-frontend-freshness-closure`
   - `needs-legacy-removal`
   - `needs-worker-readiness-closure`
   - `blocked`
4. Shared pollution inventory:
   - `server.py`
   - `postgres_repositories/read_models.py`
   - direct `ReadModelRefreshGateway` call sites
   - direct dirty/outbox SQL
   - legacy/local/live scan fallback
   - stale-as-fresh paths
   - frontend default fresh assumptions
5. Macro-wave plan, grouped by boundary class, not one row per tiny helper.

## Wave Acceptance Checklist

Each macro-wave must prove:

- No known stale-as-fresh.
- No new direct dirty/outbox SQL outside allowed owners.
- No new unregistered read model key/scope/event.
- No broad full rebuild as ordinary write-after-sync path.
- No `all` fake fresh.
- No production hot-path full-table/full-snapshot/live-scan fallback.
- Every touched read model has a PSCIP level and next action.
- Every touched high-row query has index/query-plan/test/production-sample path.
- Redis/RabbitMQ are not freshness truth.
- Workers do not depend on `Application`, HTTP, route modules or auth internals.
- Frontend does not default unknown/stale/missing to fresh.
- API shape changes are explicit, tested and documented.
- Seven test categories are evaluated.
- Docs impact is handled.

## Batch Verification Policy

Use the smallest reliable checks, but batch them at wave gates.

Required after global/shared waves:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v
bash scripts/verify.sh docs
git diff --check
```

Also run:

- targeted service/API tests for touched modules;
- targeted frontend tests for touched pages;
- targeted repository/query-plan or fake repository contract tests for touched physical SQL owner changes;
- performance evidence for touched high-row paths;
- production evidence sweep after local L3 closure.

If a command is unavailable or too broad, run the closest targeted substitute and record why.

## Hard Stops

Stop and report only when progress would be unsafe or impossible:

- main cannot fast-forward sync safely.
- backup branch cannot be created/pushed.
- unrelated dirty files make safe commit impossible.
- read model scope contract is ambiguous and cannot be inferred.
- production operation requires secret printing or broad destructive mutation.
- production operation would manually fake readiness/freshness.
- admin token is needed but no secure prompt path or user token is available.
- root SSH/DB access fails and no equivalent production-safe path exists after local L3 closure.
- tests fail and cannot be fixed inside the selected macro-wave.
- a change would alter business behavior/API shape without explicit requirement and tests.
- merge conflict touches finance/read-model/worker/permission/migration logic.

Do not hard stop merely because production verification is needed. Production verification is part of this prompt. Try the approved token/SSH/runbook path first.

## State Updates

Update or create these artifacts:

- `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-<date>.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-<N>-<slug>.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-evidence-<date>.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-main-final-closure-report-<date>.md`
- `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

If updating `MODULE-QUEUE.md` or `STATE.md`, label entries as `main-read-model-closure` and do not imply old dev workflow is active.

## Loop Rule

At the end of every wave:

1. Summarize completed wave.
2. Update analysis and journal.
3. Generate the next executable prompt in `NEXT-PROMPT.md`.
4. Immediately execute it unless a hard stop was hit.
5. Do not stop after writing a plan when safe implementation or verification work remains.

## Final Answer Requirement

When complete, answer in Chinese with:

- final main commit
- backup branch
- changed files summary
- per-read-model closure matrix
- tests added/changed
- seven test category coverage
- verification commands
- production evidence collected
- admin-token evidence status
- SSH/root operations performed
- PSCIP-L4 evidence per read model
- performance evidence and high-row risks
- exact deferred/hard-stop items, if any
- why no known stale-as-fresh path remains
- why old code cannot pollute the modular read model chain

## Start

Start now:

1. Sync `main`.
2. Create and push backup branch.
3. Build the full reconciliation report.
4. Execute the largest safe macro-wave.
5. Continue through production verification using secure admin token prompt and/or root SSH as needed.
