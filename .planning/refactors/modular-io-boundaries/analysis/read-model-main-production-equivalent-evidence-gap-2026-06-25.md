# Read Model Main Production Or Equivalent Evidence Gap

Date: 2026-06-25

Boundary: `main-read-model-closure:production-or-equivalent-freshness-performance-evidence`

Branch: `main`

Local main commit: `2c7a9eac64c1758e5f7e6bf0de1a6667b3b50f1b`

## Decision

PSCIP-L4 is not proven.

Local PSCIP-L3 owner split is complete, but current production is still running an older release that does not include the main-branch owner split commits. Production or equivalent evidence collected before deploying those commits cannot prove the current `main` implementation.

## Read-Only Production Reachability

A non-secret SSH read-only check reached `finops-prod-root`.

Observed:

- host: `VM-0-6-opencloudos`
- `fin-ops.service`: `active/running`
- service working directory: `/opt/fin-ops/releases/dev-67271c7f-modular-io-gate-r3/src`
- service command: `python -m fin_ops_platform.app.main --host 127.0.0.1 --port 18001`
- `/health/ready` on `127.0.0.1:18001`: `status=ready`, `runtime_release.consistent=true`, no release problems
- production release git commit from health metadata: `67271c7f67291a2fcf393f1fa0ad33be9e84f413`

Repository comparison:

- `67271c7f67291a2fcf393f1fa0ad33be9e84f413` is an ancestor of current `main`.
- Current `main` adds read model owner split commits after that release:
  - `0bead534`
  - `65e4a012`
  - `e242c165`
  - `95963c28`
  - `000d4444`
  - `07f028e1`
  - `46de60c7`
  - `2c7a9eac`

Therefore the current production release cannot prove PSCIP-L4 for the latest main implementation.

## Local Current-Code / Production-Data Functional Probe

Started local backend from current `main` using the existing local Postgres runtime env and an explicit SSH identity file for tunnel setup. No env file contents, DSNs, passwords, tokens, cookies, private keys or business payload exports were printed.

Allowed operations used:

- SSH tunnel forwarding for PostgreSQL/object storage/Redis.
- Local backend on `127.0.0.1:8001`.
- GET-only local API probes against current code.
- Aggregate dependency checks.

No production DB writes, queue mutation, readiness mutation, worker replay, service restart or deploy occurred.

Dependency check result:

- PostgreSQL ready through `ssh_tunnel`.
- Redis ready.
- Object storage ready.
- Script warning: SSH tunnel is valid for functional checks but not production performance benchmarking.
- Script warning: PostgreSQL connect/select latency was high locally.

`scripts/check-local-runtime.sh --all` result:

- Dependency checks passed.
- Workbench summary/groups API check passed:
  - `total=1801`
  - first page groups `10`
  - `open_total=847`
  - `paired_total=72`
- The script returned non-zero because its backend health assertion expects `storage.postgres_status == "ready"`, while current `/health` storage payload reports `{"mode": "postgres", "backend": "postgres"}` without that field. This is a harness/schema mismatch, not proof of read model failure.

## Local API Probe Results

The local current-code probe proves fresh gates do not falsely report fresh for the sampled stale/mismatched scopes, but it also proves PSCIP-L4 is not currently satisfied.

Sample results:

| Endpoint | Result |
| --- | --- |
| `/api/search?q=&scope=all&month=all&limit=5` | `read_model_status=stale`; stale reasons include missing bank auto-tag, OA parser/projection, search schema and Workbench schema versions |
| `/api/bank-details/accounts` | `read_model_status=fresh`; scope keys `["all"]` |
| `/api/no-oa-bank-batches` | `read_model_status=fresh` |
| `/api/tax-offset/summary` | `read_model_status=refreshing`; stale reason includes `oa_projection_sync_version_mismatch` |
| `/api/cost-statistics` | `read_model_status=refreshing`; stale reasons include bank auto-tag, OA projection and Workbench schema mismatches |
| `/api/workbench?month=all&page=1&page_size=5` | `read_model_status=fresh` |

Implication:

- The current code path is fail-closed for the sampled stale/mismatched read models.
- Current `main` plus current production data does not show every read model/page as fresh.
- A valid PSCIP-L4 run must deploy current code to production or an equivalent runtime, let scoped workers converge or run an approved explicit-scope refresh/backfill runbook, then collect readiness/dirty/outbox/API/performance evidence again.

## Performance Evidence Status

No production co-located performance benchmark was collected in this boundary.

Local tunnel observations are not accepted as performance evidence because network/tunnel latency dominates:

- local dependency check reported high PostgreSQL connect/select latency;
- local Workbench API metrics emitted during shutdown showed `/api/workbench/summary` about `1289ms` and `/api/workbench/groups` about `2414ms` to `2595ms` through the tunnel.

These numbers are useful as diagnostic context only. They must not be used as production p95/p99 or query-plan proof.

## Required Next Step

Next boundary should be a controlled production deploy/evidence gate, not a code refactor:

1. Prepare/confirm a deployment runbook for current `main`.
2. Deploy current `main` only with explicit production rollout approval.
3. Run read-only readiness/dirty/outbox/worker sweep after deploy.
4. Run scoped API/browser smoke and high-row query plan/performance probes.
5. If any endpoint remains stale/refreshing, run only an approved explicit-scope refresh/backfill runbook, then re-sweep.

Until then, classify global closure as:

`local-implementation-closed-production-evidence-needed`
