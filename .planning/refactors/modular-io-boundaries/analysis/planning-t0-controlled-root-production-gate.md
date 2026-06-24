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
- T0 may use root SSH for controlled production evidence or controlled production operations after local/contract verification is complete;
- workers may request this gate in handoff, but workers must not execute it;
- T0 must write a bounded runbook/evidence file before controlled production operation;
- T0 must not print/store secrets;
- T0 must prefer read-only checks, deployed-runtime tools, dry-run, no-op, test tenant or canary operations;
- deploy/restart/requeue/readiness mutation/repair apply is allowed only if the selected boundary has a runbook proving the action is bounded, reversible or cleanup-safe, has pre/post checks and has no safer validation path.

## Sufficiency Assessment

Root SSH is generally enough to close production-evidence gaps that require:

- service/worker status;
- health/readiness evidence;
- deployed release/version checks;
- non-secret log excerpts;
- App Status/read model freshness evidence exposed by deployed tools;
- bounded canary/dry-run/no-op validation;
- deployed-runtime commands that use existing server configuration without printing secrets.

Root SSH is not enough by itself when closure would require:

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
