# Read Model Main Controlled Deploy And Evidence Runbook

Date: 2026-06-25

Boundary: `main-read-model-closure:controlled-main-deploy-and-post-deploy-read-model-evidence-runbook`

Branch: `main`

Current main commit: `9c47f55a02ed1aaf548865d6637bd871e3168ce1`

Backup branch: `codex/backup-main-before-read-model-closure-20260625-230543`

## Decision

PSCIP-L4 is still not proven.

This boundary prepares the safe production rollout and evidence path for current `main`. It does not execute production deploy, service restart, production DB write, queue mutation, readiness mutation, force refresh, worker replay, repair, or mutating HTTP smoke.

Deployment remains an explicit human gate because the current production service is running release commit `67271c7f67291a2fcf393f1fa0ad33be9e84f413`, while current `main` is `9c47f55a02ed1aaf548865d6637bd871e3168ce1`. Production evidence for the older release cannot prove PSCIP-L4 for the latest owner split.

## Scope

This runbook is for a controlled release deploy followed by read model PSCIP-L4 evidence collection.

It is not a code refactor wave. It must not introduce Go, Go Fiber, Go Worker, a sidecar, a new queue framework, manual readiness edits, or manual canonical fact edits.

## Pre-Approval Read-Only Checks

These checks are allowed before deploy approval because they do not mutate production state and must not print secrets.

From the local repo:

```bash
git status --short --branch
git fetch origin --prune
git pull --ff-only origin main
git rev-parse HEAD
```

Expected:

- branch is `main`;
- worktree is clean;
- `HEAD` equals the commit intended for deploy;
- `main` is fast-forward synced with `origin/main`.

From production over SSH, read-only:

```bash
ssh finops-prod-root 'hostname; sudo -n /usr/local/sbin/finops-deploy-control status'
ssh finops-prod-root 'curl -fsS --max-time 5 http://127.0.0.1:18001/health/ready'
ssh finops-prod-root 'curl -fsS --max-time 5 http://127.0.0.1:18001/health'
```

Expected:

- `fin-ops.service` is active;
- current release identity is recorded;
- `/health/ready` returns `status=ready`;
- runtime worker facts are present in `/health`;
- no secret env, DSN, token, cookie, private key, raw business payload, or broad row export is printed.

Optional release dry-run from local repo:

```bash
./scripts/deploy-oa.sh \
  --mode release \
  --host finops-prod \
  --user finops-deploy \
  --frontend-base-path /fin-ops/ \
  --release-name main-9c47f55a-read-model-closure-$(date +%Y%m%d%H%M%S) \
  --no-activate \
  --dry-run
```

The dry-run is only command-shape evidence. It does not upload, validate, activate, restart, migrate, or prove PSCIP-L4.

## Required Approval Gate

Before running any command that activates a release, restarts services, runs migrations, applies read model smoke, applies repair/backfill, or mutates production through HTTP, record explicit approval with:

- approver;
- timestamp;
- target commit;
- target release name;
- allowed operation class;
- rollback contact/path;
- whether mutating write-operation smoke is allowed;
- whether read model SLO smoke `--apply` is allowed.

Without this approval, stop after read-only evidence and keep global closure as `local-implementation-closed-production-evidence-needed`.

## Deploy Command

Use the repository production entrypoint, not ad hoc rsync or direct systemd edits.

```bash
release_name="main-9c47f55a-read-model-closure-$(date +%Y%m%d%H%M%S)"

./scripts/deploy-oa.sh \
  --mode release \
  --host finops-prod \
  --user finops-deploy \
  --frontend-base-path /fin-ops/ \
  --release-name "$release_name"
```

The release path performs the existing guarded sequence:

1. local frontend build with `VITE_APP_BASE_PATH=/fin-ops/`;
2. clean-worktree release archive creation with `RELEASE.json`;
3. remote release upload under `/opt/fin-ops/releases/<release_name>`;
4. deploy-control contract checks;
5. `check-release`;
6. `activate`;
7. PostgreSQL migration through the migrator env;
8. API/worker/dispatcher release drop-ins;
9. runtime worker ensure;
10. frontend publish;
11. service restart;
12. worker readiness wait;
13. backend `/health/ready` check;
14. deploy-control status;
15. public session route proxy check;
16. release cleanup preserving active references.

Hard stop if any deploy step fails. Do not manually patch drop-ins, edit readiness, mark outbox done, or fake App Status fresh.

## Immediate Post-Deploy Identity And Health Evidence

Run from production after deploy activation:

```bash
sudo -n /usr/local/sbin/finops-deploy-control status
curl -fsS --max-time 5 http://127.0.0.1:18001/health/ready
curl -fsS --max-time 5 http://127.0.0.1:18001/health
```

Acceptance:

- active API, workers, and dispatcher point at the new release source;
- health release metadata git commit equals current `main`;
- `/health/ready.status` is `ready`;
- required worker missing/stale/mismatch counts are zero;
- RabbitMQ remains transport-only and has no DLQ/current blocker;
- PostgreSQL durable queue/readiness facts are present.

## Read Model Scope Contract Evidence

First run dry-run only:

```bash
sudo -n /usr/local/sbin/finops-deploy-control read-model-scope-contract "$release_name" --json \
  > /tmp/finops-read-model-scope-contract-${release_name}.json
```

Acceptance:

- no invalid current dirty/outbox/readiness scope;
- no uncovered current outbox failure;
- any legacy/covered historical item is classified with proposed action and rollback hint.

If dry-run proposes repair, do not apply in this runbook unless a separate explicit repair approval names the scopes and allowed actions. An apply repair must never write fresh readiness directly.

## Direct Read Model SLO Evidence

Safe dry-run via deploy-control:

```bash
sudo -n /usr/local/sbin/finops-deploy-control read-model-slo-smoke "$release_name" \
  --json \
  --critical-only \
  > /tmp/finops-read-model-slo-smoke-dry-run-${release_name}.json
```

Dry-run proves scope discovery only.

Apply requires explicit approval and must be run from a root session with runtime env, not through deploy-control because deploy-control intentionally refuses `--apply`:

```bash
release_src="$(systemctl show fin-ops.service -P WorkingDirectory)"
cd "$release_src"
set -a
source /etc/fin-ops/fin-ops.common.env
source /etc/fin-ops/fin-ops.secrets.env
set +a
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python \
  -m fin_ops_platform.tools.read_model_slo_smoke \
  --json \
  --apply \
  --critical-only \
  --target-ms 1000 \
  --timeout-seconds 120 \
  --output /tmp/finops-read-model-slo-smoke-apply-${release_name}.json
```

Acceptance for PSCIP-L4 direct worker evidence:

- `planned_scope_count > 0`;
- `result_count > 0`;
- `failed_count = 0`;
- p95 enqueue-to-fresh `<= 1000ms`, or any miss is recorded as a performance blocker;
- post-run `/health/ready`, dirty scopes, outbox, readiness and RabbitMQ DLQ converge.

## Runtime Closure Gate Evidence

Run read-only/preflight first:

```bash
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python \
  -m fin_ops_platform.tools.production_external_gate_preflight \
  --json \
  > /tmp/finops-production-external-gate-preflight-${release_name}.json
```

If external inputs are present and mutating gates are approved:

```bash
export FIN_OPS_HTTP_SLO_ADMIN_TOKEN='<provided out-of-band; do not print>'
export FIN_OPS_WRITE_E2E_APPROVAL_TICKET='<approval ticket>'

PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python \
  -m fin_ops_platform.tools.runtime_sync_closure_gate \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --apply-read-model-smoke \
  --write-scenario /tmp/finops-write-e2e-scenarios.json \
  --apply-write-scenarios \
  --write-approval-ticket "$FIN_OPS_WRITE_E2E_APPROVAL_TICKET" \
  --http-target-ms 1000 \
  --sse-target-ms 1000 \
  --health-ready-target-ms 1000 \
  --read-model-target-ms 1000 \
  --write-target-ms 1000 \
  --output /tmp/finops-runtime-sync-closure-gate-${release_name}.json
```

If write scenarios or approval are missing, run only the non-mutating probes and record the missing evidence. Do not mark global closure complete.

## Read-Only Performance Evidence

Collect production-co-located baseline:

```bash
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python \
  -m fin_ops_platform.tools.sync_slo_baseline \
  --json \
  > /tmp/finops-sync-slo-baseline-${release_name}.json
```

Collect readiness payload probe from a network path:

```bash
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python \
  -m fin_ops_platform.tools.health_ready_payload_probe \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --target-ms 1000 \
  --output /tmp/finops-health-ready-payload-${release_name}.json
```

With admin auth supplied out of band, collect HTTP/SSE p95:

```bash
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python \
  -m fin_ops_platform.tools.http_slo_probe \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --iterations 20 \
  --warmup 2 \
  --target-ms 1000 \
  --output /tmp/finops-http-slo-${release_name}.json

PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python \
  -m fin_ops_platform.tools.sse_smoke_probe \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --target-ms 1000 \
  --output /tmp/finops-sse-smoke-${release_name}.json
```

Acceptance:

- Workbench, search, bank detail, no-OA bank batch, turnover ledger, cost statistics and tax offset have production-co-located query plan, health API performance, HTTP SLO, or closure-gate evidence;
- no high-row page relies on tunnel latency evidence;
- any p95 miss is recorded as `needs-performance-fix` and blocks PSCIP-L4.

## API Freshness Sampling

Use authenticated HTTP SLO output as the primary page/API sample. If additional local service probes are needed, run GET-only probes against `127.0.0.1:18001` and record only status metadata:

- `read_model_status`;
- `read_model_scope_key` / scope keys;
- `source_versions` presence;
- stale reasons;
- `refresh_enqueued`;
- latency.

Do not export raw business rows or attachment payloads.

Acceptance:

- fresh pages have schema/source proof;
- stale/refreshing pages are not reported fresh;
- `search`, `cost_statistics`, and `tax_offset` must no longer remain stale/refreshing after approved convergence, or they remain PSCIP-L4 blockers.

## Rollback

If deploy activation fails or post-deploy readiness regresses:

1. identify the previously active release from deploy-control status, systemd drop-ins, or `/opt/fin-ops/releases`;
2. run:

   ```bash
   sudo -n /usr/local/sbin/finops-deploy-control activate <previous-release-name>
   ```

3. verify `/health/ready`, worker readiness, dirty/outbox/readiness and frontend route checks;
4. do not roll back by hand-editing systemd drop-ins unless deploy-control itself is broken and a separate operator incident runbook is opened.

Migration rollback is not assumed. If a new migration is not backward-compatible, stop before deploy and add an expand/contract migration runbook. Current runbook depends on existing deploy-control migration safety.

## Closure Decision Rules

PSCIP-L4 may be claimed only if all of the following are proven for current `main`:

- production release identity equals current main commit;
- App Status registry/readiness, worker registry, RabbitMQ dispatch and scope policy are aligned;
- dirty scopes, outbox, dead-letter and worker readiness converge;
- direct read model SLO apply has non-empty passing samples;
- authenticated page/API HTTP SLO and SSE smoke pass or have an accepted equivalent;
- high-row read paths have production-co-located performance evidence;
- write-operation audit/E2E evidence is non-empty and passing, or the missing mutating evidence is explicitly classified as a hard stop;
- no sampled endpoint returns stale-as-fresh;
- any repair/backfill was bounded, approved, idempotent, audited and scoped.

If any item is missing, keep status as:

`local-implementation-closed-production-evidence-needed`

or the more specific blocker:

- `external-input-required`;
- `deploy-approval-required`;
- `read-model-convergence-blocked`;
- `performance-evidence-missing`;
- `write-operation-evidence-missing`;
- `production-repair-approval-required`.

## Current Boundary Outcome

Outcome for this boundary:

`runbook-prepared-deploy-approval-required`

No production deploy, restart, migration, DB write, queue mutation, readiness mutation, worker replay, force refresh, repair or mutating HTTP smoke was executed.
