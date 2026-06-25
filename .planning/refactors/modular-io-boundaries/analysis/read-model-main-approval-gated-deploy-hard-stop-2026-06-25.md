# Read Model Main Approval-Gated Deploy Hard Stop

Date: 2026-06-25

Boundary: `main-read-model-closure:approval-gated-current-main-deploy-or-hard-stop`

Branch: `main`

Current main commit checked: `93617a1e74e33e1ff77db6cd68ceb619b9401a76`

Backup branch: `codex/backup-main-before-read-model-closure-20260625-230543`

## Decision

PSCIP-L4 is not proven and cannot be claimed from current evidence.

The pre-approval read-only checks were completed. No explicit production rollout approval was present in this run, so no production deploy, activation, service restart, migration, DB write, queue mutation, readiness mutation, read model SLO `--apply`, force refresh, worker replay, repair, or mutating HTTP smoke was executed.

The blocker is now explicit:

`deploy-approval-required`

## Local Main Preflight

Commands run:

```bash
git status --short --branch
git rev-parse HEAD
git fetch origin --prune
git pull --ff-only origin main
git status --short --branch
```

Result:

- local branch: `main`;
- local worktree was clean before this hard-stop report was written;
- `main` was already up to date with `origin/main`;
- checked commit: `93617a1e74e33e1ff77db6cd68ceb619b9401a76`.

## Production Read-Only Preflight

Commands run over SSH were read-only:

```bash
ssh finops-prod-root 'hostname'
ssh finops-prod-root 'sudo -n /usr/local/sbin/finops-deploy-control status'
ssh finops-prod-root 'curl -fsS --max-time 5 http://127.0.0.1:18001/health/ready'
ssh finops-prod-root 'curl -fsS --max-time 5 http://127.0.0.1:18001/health'
```

Observed:

- host: `VM-0-6-opencloudos`;
- `fin-ops.service`: active;
- `fin-ops-rabbitmq-dispatcher.service`: active;
- active worker services included the expected read model/runtime workers, including `workbench`, `workbench-relation`, `bank-detail`, `bank-account-balance`, `pending-invoice`, `invoice-lifecycle`, `invoice-lifecycle-secondary`, `invoice-usage-collection`, `search`, `search-secondary`, `search-tertiary`, `search-pending`, `cost-statistics`, `tax-offset`, `cost-tax`, `no-oa-bank-batch`, `turnover-ledger`, `import`, `oa-sync`, and `workbench-matching`;
- active API working directory: `/opt/fin-ops/releases/dev-67271c7f-modular-io-gate-r3/src`;
- active worker working directory sampled from `workbench`: `/opt/fin-ops/releases/dev-67271c7f-modular-io-gate-r3/src`;
- `/health/ready.status`: `ready`;
- `/health/ready.runtime_release.consistent`: `true`;
- `/health/ready.runtime_release.release_metadata.release_name`: `dev-67271c7f-modular-io-gate-r3`;
- `/health/ready.runtime_release.release_metadata.git_branch`: `dev`;
- `/health/ready.runtime_release.release_metadata.git_commit`: `67271c7f67291a2fcf393f1fa0ad33be9e84f413`;
- `/health.status`: `ready`;
- `/health.storage.backend`: `postgres`;
- `/health.storage.mode`: `postgres`;
- `/health.runtime_release.consistent`: `true`.

Important limitation:

- `/health` on the current production release exposes a top-level `runtime_infrastructure` key, but the object is empty in the observed payload. It did not provide the worker/dirty/outbox/readiness facts required by the PSCIP-L4 gate.

No secret env values, DSNs, tokens, cookies, private keys, raw business payloads, or broad row exports were printed.

## Deploy Dry-Run Shape

A local dry-run was executed with build skipped and activation disabled:

```bash
./scripts/deploy-oa.sh \
  --mode release \
  --host finops-prod \
  --user finops-deploy \
  --frontend-base-path /fin-ops/ \
  --release-name main-93617a1e-read-model-closure-20260625235508 \
  --no-activate \
  --dry-run \
  --skip-build
```

Result:

- command shape targets `finops-deploy@finops-prod`;
- release directory would be `/opt/fin-ops/releases/main-93617a1e-read-model-closure-20260625235508`;
- dry-run script includes release name validation, deploy-control contract check, storage preflight, release layout validation, and `finops-deploy-control check-release`;
- activation is skipped by construction.

This did not upload, activate, migrate, restart, validate production runtime with current code, or prove PSCIP-L4.

## Why PSCIP-L4 Is Still Blocked

Current production is not running current `main`.

Production release evidence still points to:

`67271c7f67291a2fcf393f1fa0ad33be9e84f413`

Current main checked in this boundary is:

`93617a1e74e33e1ff77db6cd68ceb619b9401a76`

Therefore:

- release identity does not equal current main;
- App Status readiness for current main is not proven;
- dirty scopes/outbox/dead-letter convergence for current main is not proven;
- required worker health for current main is not proven;
- sampled page/API freshness for current main in production is not proven;
- high-row production performance evidence for current main is not proven;
- direct read model SLO `--apply` evidence is missing;
- authenticated HTTP/SSE evidence is missing;
- write-operation audit/E2E evidence is missing.

The previous current-code/local-backend probe over SSH-tunneled production dependencies showed fail-closed behavior, but it also showed `search` stale and `cost_statistics`/`tax_offset` refreshing, and tunnel latency was rejected as production performance evidence. That probe cannot close PSCIP-L4.

## Required Approval To Continue

The next run can continue only after explicit approval provides:

- approver;
- approval timestamp;
- target commit, currently expected to be current `main`;
- target release name;
- allowed operation class, such as deploy only, deploy plus read-model SLO apply, or deploy plus mutating write-operation smoke;
- rollback path/contact;
- whether read model SLO `--apply` is approved;
- whether mutating write-operation E2E smoke is approved;
- any production change window constraint.

Without that approval, the only correct status remains:

`local-implementation-closed-production-evidence-needed`

with blocker:

`deploy-approval-required`

## Non-Actions

This boundary did not:

- deploy current `main`;
- activate a release;
- run migrations;
- restart API, workers, dispatcher, Nginx, PostgreSQL, Redis, RabbitMQ or MinIO;
- write production DB rows;
- mutate `job.outbox_events`, `job.read_model_dirty_scopes`, or `read_model.app_status_readiness`;
- run read model SLO `--apply`;
- run force refresh, backfill or repair;
- replay or requeue worker events;
- run mutating HTTP smoke;
- claim global read model closure.
