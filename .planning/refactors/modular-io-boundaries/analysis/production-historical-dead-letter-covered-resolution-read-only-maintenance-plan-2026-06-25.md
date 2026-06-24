# Production Historical Dead Letter Covered Resolution Read Only Maintenance Plan 2026-06-25

**Boundary:** `production:historical-dead-letter-covered-resolution-read-only-maintenance-plan`
**Final status:** `analysis-closed`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `869821fd421f74b667db289b26dc989ce8bdaae1`
**Production release for checks:** `dev-workbench-matching-port-20260625020818`

## Target

Classify the 24 historical read-model `dead_lettered` outbox rows that remain after no-OA and workbench-matching convergence. This boundary must prove whether each row is covered by fresh readiness or later done evidence and produce a bounded apply-or-defer decision.

## Allowed Operations

- Root SSH read-only status and health checks.
- Deployed-runtime read-only PostgreSQL aggregate queries through existing production configuration without printing secrets.
- `runtime_queue_ops resolve-covered-dead-letters --dry-run`.
- Event `inspect` only if needed for read-only evidence.

## Forbidden Operations

- `resolve-covered-dead-letters --execute`.
- `resolve-dead-letter`, `requeue`, `republish`, `release-stale-processing --execute`, `resolve-superseded-processing --execute`.
- Direct DB writes or queue/readiness mutation.
- Worker replay or broad queue consume.
- Printing env files, DSNs, passwords, tokens, cookies, private keys or secret env values.

## Evidence Commands

1. Confirm production health remains clean:

```bash
curl -fsS --max-time 8 https://www.yn-sourcing.com/fin-ops-api/health/ready
```

2. Classify current dead-letter groups and active blocker state with read-only SQL from the deployed release.

3. Run dry-run only:

```bash
ssh finops-prod-root 'release_src=/opt/fin-ops/releases/dev-workbench-matching-port-20260625020818/src; set -a; . /etc/fin-ops/fin-ops.common.env; . /etc/fin-ops/fin-ops.secrets.env; set +a; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops resolve-covered-dead-letters --limit 100 --dry-run'
```

## Expected Evidence

- `/health/ready` remains ready.
- `job.read_model_dirty_scopes` has no non-done rows.
- `read_model.app_status_readiness` has no non-fresh rows.
- `resolve-covered-dead-letters --dry-run` returns `mode=dry-run` and `resolved_count=0`.
- Every current read-model dead-letter is either:
  - eligible with `covered_by` proof and no active dirty scope; or
  - explicitly deferred with missing coverage reason.

## Stop Gates

- Any command would require printing secrets.
- `/health/ready` regresses.
- Any active non-done dirty scope or non-fresh readiness appears.
- Dry-run reports uncovered rows that require code/data diagnosis.
- Dry-run or inspect output contradicts current queue/state evidence.

## Execution Results

Executed read-only production classification against release `dev-workbench-matching-port-20260625020818`.

### Health And Runtime Aggregate

`/health/ready` returned `status=ready` with:

- `queue_backlog={}`;
- `dirty_scopes={"done": 187007}`;
- `failed_jobs=0`;
- `stale_dirty_scope_count=0`;
- required worker missing/stale/mismatch counts all `0`;
- RabbitMQ queue depth, unacked and DLQ counts all `0`;
- `worker_status_counts={"available": 21}`.

Read-only deployed-runtime PostgreSQL aggregate:

- `job.outbox_events`: `done=203145`, `dead_lettered=24`.
- `job.read_model_dirty_scopes`: `done=187007`.
- `read_model.app_status_readiness`: `fresh=498`.
- Active dirty scope samples: `[]`.
- Non-fresh readiness samples: `[]`.

### Dead-Letter Groups

Current read-model dead-letter groups:

| Event type | Scope | Count | Error class |
| --- | --- | ---: | --- |
| `no_oa_bank_batch.read_model.refresh` | `no_oa_bank_batch:all` | 13 | historical FK delete-order failure on `app.no_oa_bank_batch_events_no_oa_bank_batch_id_fkey` |
| `pending_invoice.read_model.refresh` | `pending_invoice:expense:all:2026-05` | 1 | historical PostgreSQL deadlock |
| `workbench.read_model.refresh` | `workbench:2025-04` | 1 | historical permission grant failure on `etc_batch_invoice_links` |
| `workbench.read_model.refresh` | `workbench:2025-09` | 1 | historical permission grant failure on `etc_batch_invoice_links` |
| `workbench.read_model.refresh` | `workbench:2025-11` | 1 | historical permission grant failure on `etc_batch_invoice_links` |
| `workbench.read_model.refresh` | `workbench:2025-12` | 1 | historical permission grant failure on `etc_batch_invoice_links` |
| `workbench.read_model.refresh` | `workbench:2026-01` | 1 | historical permission grant failure on `etc_batch_invoice_links` |
| `workbench.read_model.refresh` | `workbench:2026-02` | 1 | historical permission grant failure on `etc_batch_invoice_links` |
| `workbench.read_model.refresh` | `workbench:2026-03` | 1 | historical permission grant failure on `etc_batch_invoice_links` |
| `workbench.read_model.refresh` | `workbench:2026-04` | 1 | historical permission grant failure on `etc_batch_invoice_links` |
| `workbench.read_model.refresh` | `workbench:2026-05` | 1 | historical permission grant failure on `etc_batch_invoice_links` |
| `workbench.read_model.refresh` | `workbench:2026-06` | 1 | historical permission grant failure on `etc_batch_invoice_links` |

### Dry-Run Covered Resolution

Command:

```bash
python -m fin_ops_platform.tools.runtime_queue_ops resolve-covered-dead-letters --limit 100 --dry-run
```

Result:

- `mode=dry-run`.
- `candidate_count=24`.
- `eligible_count=24`.
- `resolved_count=0`.
- Every candidate had `active_dirty_count=0`.
- Every candidate had `covered_by=["fresh_readiness", "later_done"]`.

Coverage details by group:

- 10 Workbench dead-letter rows are covered by fresh readiness and later done rows for the same month scopes. Later done counts ranged from 25 to 46 depending on month.
- 13 no-OA dead-letter rows are covered by the converged `no_oa_bank_batch:all` fresh readiness and the later done event at `2026-06-25 01:52:57.111992+08:00`.
- 1 pending invoice dead-letter row is covered by fresh readiness and 16 later done events for `expense:all:2026-05`.

## Apply-Or-Defer Decision

Decision: `apply-in-separate-controlled-boundary`.

All 24 historical read-model dead-letter rows are eligible for covered resolution according to the deployed `runtime_queue_ops` dry-run contract, and no current dirty/readiness/health blocker remains. This boundary intentionally did not execute cleanup. The next boundary should write and execute a separate controlled apply runbook for:

`production:historical-dead-letter-covered-resolution-apply-runbook`

The apply boundary may run `resolve-covered-dead-letters --execute` only after:

- rechecking `/health/ready`;
- rechecking no active dirty scopes and all readiness rows fresh;
- re-running the dry-run and confirming `candidate_count=eligible_count=24`;
- documenting rollback/cleanup limits and stop gates;
- confirming no secret output is required.

## Docs Impact

No long-term docs update is required in this read-only classification slice. It uses the existing `runtime_queue_ops` covered-dead-letter contract documented in `docs/operations/runtime-worker-governance.md` and does not change runtime behavior, API contracts, worker state definitions, read model scope policy, permissions or UI behavior.

## Seven Test Categories

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business rules or queue state transition code changed. |
| 2. Service-layer tests | Not applicable | No service/repository/worker code changed. |
| 3. API contract tests | Not applicable | No HTTP contract changed. |
| 4. Read model/cache/background job tests | Covered by production read-only evidence | This slice classified read-model dead-letter coverage using dry-run and readiness/dirty-scope facts; no code test change required. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable | No runtime mutation or business flow changed. |
| 7. Existing feature regression tests | Not applicable | Planning/evidence only; existing `tests/test_runtime_queue_ops.py` remains the code-level guard for the tool contract. |

## Verification

- `curl -fsS --max-time 8 https://www.yn-sourcing.com/fin-ops-api/health/ready`
- Read-only deployed-runtime PostgreSQL aggregate query for outbox, dirty scope, readiness and dead-letter groups.
- `python -m fin_ops_platform.tools.runtime_queue_ops resolve-covered-dead-letters --limit 100 --dry-run`

No DB writes, queue mutation, readiness mutation, requeue, resolve, repair, worker replay, cleanup or secret output occurred.
