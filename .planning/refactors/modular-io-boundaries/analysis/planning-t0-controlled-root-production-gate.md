# planning:t0-controlled-root-production-gate

**Date:** 2026-06-25
**Status:** planning-closed
**Previous boundary:** `planning:commit-backed-state-reconciliation`
**Next executable boundary:** `planning:commit-backed-state-reconciliation`

## Goal

Clarify that `ssh finops-prod-root` is the sanctioned T0-only production evidence and controlled-operation path for this refactor.

The user does not have a staging database or local PostgreSQL URL. The refactor plan must therefore not depend on those two resources.

## Decision

The primary T0 prompt now states:

- absence of staging DB and local `PGSQL_URL` is not a hard blocker;
- T0 is authorized to perform all reasonable controlled production operations required to close the full modular IO refactor;
- T0 should use root SSH for controlled production evidence or controlled production operations after local/contract verification is complete;
- T0 must not record `needs-human-production-gate` merely because a production operation is needed; it must use the authorized controlled production gate first;
- workers may request this gate in handoff, but workers must not execute it;
- T0 must write a bounded runbook/evidence file before controlled production operation;
- T0 must not print/store secrets;
- T0 must prefer the least invasive operation that proves the required evidence;
- reasonable controlled production operations may include read-only checks, deployed-runtime tools, health/status/log evidence, bounded read model refresh/rebuild for explicit scopes, bounded queue/requeue/worker-drain checks for explicit scopes, dry-run, no-op, test tenant, canary operations, deploy/restart when required by the selected boundary, and reversible repair/apply commands for explicit scopes;
- deploy/restart/requeue/readiness mutation/repair apply is allowed only if the selected boundary has a runbook proving the action is bounded, reversible or cleanup-safe, has pre/post checks and has no safer validation path.

## Sufficiency Assessment

With this authorization, root SSH is intended to be sufficient for the full refactor's reasonable production-operation needs when the operation can be bounded and evidenced. It is enough to close production-evidence gaps that require:

- service/worker status;
- health/readiness evidence;
- deployed release/version checks;
- non-secret log excerpts;
- App Status/read model freshness evidence exposed by deployed tools;
- bounded canary/dry-run/no-op validation;
- deployed-runtime commands that use existing server configuration without printing secrets;
- bounded explicit-scope read model refresh/rebuild verification;
- bounded explicit-scope queue/requeue/worker-drain verification;
- controlled deploy/restart/post-check validation when required by a selected boundary;
- reversible explicit-scope repair/apply validation when required by a selected boundary.

Root SSH still cannot eliminate every possible hard stop. It is not enough by itself when closure would require:

- printing or storing secrets/DSNs/tokens;
- broad or destructive production mutation;
- unbounded queue consume or worker replay;
- unclear business/API/database contract;
- mutation with no proven rollback or cleanup;
- third-party/OA/browser evidence unavailable from the server and not safely automatable.

In those cases, T0 must record `needs-human-production-gate` or `production-evidence-deferred`, continue another safe boundary when possible, and never claim that exact evidence as proven.

## State Machine Impact

No module state is closed by this planning slice. The next executable boundary remains:

```text
planning:commit-backed-state-reconciliation
```

## Verification

Required verification for this planning slice:

```bash
bash scripts/verify.sh docs
git diff --check
```
