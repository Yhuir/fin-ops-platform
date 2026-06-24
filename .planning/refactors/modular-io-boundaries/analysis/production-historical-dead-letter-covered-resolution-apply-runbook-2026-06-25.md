# Production Historical Dead Letter Covered Resolution Apply Runbook 2026-06-25

**Boundary:** `production:historical-dead-letter-covered-resolution-apply-runbook`
**Final status:** `production-controlled`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `c7bc4788cb273337dbfb68d258accbcd96c19414`
**Production release for checks:** `dev-workbench-matching-port-20260625020818`

## Target

Resolve the 24 historical read-model `dead_lettered` outbox rows that were classified in `production-historical-dead-letter-covered-resolution-read-only-maintenance-plan-2026-06-25.md`.

This boundary must not repair or replay any current business state. It may only mark currently covered historical read-model dead-letter rows through the deployed `runtime_queue_ops resolve-covered-dead-letters` contract after proving that the rows remain covered by fresh readiness and later done events.

## Preconditions From Prior Boundary

- `/health/ready` was ready.
- `job.read_model_dirty_scopes` had only `done=187007`.
- `read_model.app_status_readiness` had only `fresh=498`.
- `job.outbox_events` had `done=203145`, `dead_lettered=24`.
- `resolve-covered-dead-letters --limit 100 --dry-run` returned:
  - `candidate_count=24`;
  - `eligible_count=24`;
  - `resolved_count=0`;
  - every candidate had `active_dirty_count=0`;
  - every candidate had `covered_by=["fresh_readiness", "later_done"]`.

## Allowed Operations

1. Public `/health/ready` check.
2. Root SSH deployed-runtime read-only PostgreSQL aggregate checks through existing production configuration without printing secrets.
3. `runtime_queue_ops resolve-covered-dead-letters --limit 100 --dry-run`.
4. A single guarded apply command only if the dry-run still returns `candidate_count=24` and `eligible_count=24`:

```bash
ssh finops-prod-root 'release_src=/opt/fin-ops/releases/dev-workbench-matching-port-20260625020818/src; set -a; . /etc/fin-ops/fin-ops.common.env; . /etc/fin-ops/fin-ops.secrets.env; set +a; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops resolve-covered-dead-letters --limit 100 --execute --reason historical_covered_dead_letter_resolution_20260625'
```

5. Post-apply read-only health, readiness, dirty-scope, outbox status and dry-run checks.

## Forbidden Operations

- Requeue, republish, repair, worker replay or broad queue consume.
- `release-stale-processing --execute`, `resolve-superseded-processing --execute`, ad hoc `resolve-dead-letter`, readiness mutation or dirty-scope mutation.
- Direct SQL `insert`, `update`, `delete` or DDL.
- Deploy, restart or systemd mutation.
- Printing env files, DSNs, passwords, tokens, cookies, private keys or secret env values.

## Stop Gates

Stop before apply if any of these occur:

- `/health/ready` is not ready.
- Any `job.read_model_dirty_scopes` row is not `done`.
- Any `read_model.app_status_readiness` row is not `fresh`.
- Dry-run output differs from `candidate_count=24`, `eligible_count=24`, `resolved_count=0`.
- Any candidate has `active_dirty_count>0`.
- Any candidate is not covered by both `fresh_readiness` and `later_done`.
- Any command would require secret output.

Stop after apply and diagnose without further mutation if:

- `resolved_count` differs from the current eligible set.
- `/health/ready` regresses.
- Non-done dirty scopes or non-fresh readiness rows appear.
- Dead-letter residue does not decrease as expected.

## Rollback And Cleanup Posture

The apply command uses the repository-supported covered-resolution path for obsolete read-model dead-letter rows. It does not rebuild projections, mutate canonical facts, mutate readiness, mutate dirty scopes, requeue events or replay workers.

Rollback is not expected because the rows are already obsolete and covered by later done events plus fresh readiness. If the apply partially resolves rows or post-checks regress, T0 must stop, preserve the command output and read-only evidence, and diagnose from the audit trail. Do not manually re-dead-letter rows or mutate readiness without a new bounded runbook.

## Expected Post-Check

If no concurrent queue writes occur during the short apply window:

- `/health/ready` remains ready.
- `job.outbox_events` read-model `dead_lettered` count decreases from `24` to `0`.
- `job.outbox_events` `done` count increases from `203145` to about `203169`.
- `job.read_model_dirty_scopes` remains all `done`.
- `read_model.app_status_readiness` remains all `fresh`.
- `resolve-covered-dead-letters --limit 100 --dry-run` returns `candidate_count=0`, `eligible_count=0`, `resolved_count=0`.

Counts may differ only if unrelated production queue activity occurs; any difference must be recorded with evidence and must not hide readiness regression.

## Execution Results

Executed controlled production apply against release `dev-workbench-matching-port-20260625020818`.

### Pre-Apply Checks

`/health/ready` returned `status=ready` with:

- `queue_backlog={}`;
- `dirty_scopes={"done": 187007}`;
- `failed_jobs=0`;
- `stale_dirty_scope_count=0`;
- required worker missing/stale/mismatch counts all `0`;
- RabbitMQ queue depth, unacked and DLQ counts all `0`;
- `worker_status_counts={"available": 21}`.

Read-only deployed-runtime PostgreSQL aggregate before apply:

- `job.outbox_events`: `done=203145`, `dead_lettered=24`.
- `job.read_model_dirty_scopes`: `done=187007`.
- `read_model.app_status_readiness`: `fresh=498`.
- Active dirty scope samples: `[]`.
- Non-fresh readiness samples: `[]`.

Pre-apply dry-run:

- `mode=dry-run`.
- `candidate_count=24`.
- `eligible_count=24`.
- `resolved_count=0`.
- Every candidate had `active_dirty_count=0`.
- Every candidate had `covered_by=["fresh_readiness", "later_done"]`.

### Apply

Command:

```bash
python -m fin_ops_platform.tools.runtime_queue_ops resolve-covered-dead-letters --limit 100 --execute --reason historical_covered_dead_letter_resolution_20260625
```

Result:

- `mode=execute`.
- `candidate_count=24`.
- `eligible_count=24`.
- `resolved_count=24`.
- Resolved groups:
  - 10 `workbench.read_model.refresh` historical rows for `2025-04`, `2025-09`, `2025-11`, `2025-12`, `2026-01`, `2026-02`, `2026-03`, `2026-04`, `2026-05`, `2026-06`;
  - 13 `no_oa_bank_batch.read_model.refresh` historical rows for `no_oa_bank_batch:all`;
  - 1 `pending_invoice.read_model.refresh` historical row for `pending_invoice:expense:all:2026-05`.

No env values or secret values were printed. The operation used the deployed maintenance command only; no direct SQL mutation, requeue, repair, worker replay, readiness mutation or dirty-scope mutation was executed.

### Post-Apply Checks

`/health/ready` remained `status=ready` with:

- `queue_backlog={}`;
- `dirty_scopes={"done": 187007}`;
- `failed_jobs=0`;
- `stale_dirty_scope_count=0`;
- required worker missing/stale/mismatch counts all `0`;
- RabbitMQ queue depth, unacked and DLQ counts all `0`;
- `worker_status_counts={"available": 21}`.

Read-only deployed-runtime PostgreSQL aggregate after apply:

- `job.outbox_events`: `done=203169`.
- `job.outbox_events`: no `dead_lettered` rows remained.
- Dead-letter groups: `[]`.
- `job.read_model_dirty_scopes`: `done=187007`.
- `read_model.app_status_readiness`: `fresh=498`.
- Active dirty scope samples: `[]`.
- Non-fresh readiness samples: `[]`.

Post-apply dry-run:

- `mode=dry-run`.
- `candidate_count=0`.
- `eligible_count=0`.
- `events=[]`.
- `resolved_count=0`.

Decision: `production-controlled`. Historical read-model dead-letter residue decreased from 24 to 0 without readiness, dirty-scope or health regression. No global/module closure is claimed from this maintenance boundary.

## Docs Impact

No long-term docs update is expected. This boundary exercises an existing maintenance command and does not change API contracts, runtime behavior, read model scope policy, permissions, worker registration or UI behavior.

## Seven Test Categories

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business-rule code changes are planned. |
| 2. Service-layer tests | Not applicable | No service/repository/worker code changes are planned. |
| 3. API contract tests | Not applicable | No HTTP contract changes are planned. |
| 4. Read model/cache/background job tests | Covered by production-controlled evidence | This boundary checks readiness, dirty scopes, outbox residue and the maintenance command dry-run/apply contract. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changes are planned. |
| 6. End-to-end business-flow integration tests | Not applicable | No business flow or projection rebuild is planned. |
| 7. Existing feature regression tests | Covered by post-check evidence | The safety regression is that readiness remains fresh, dirty scopes remain done and `/health/ready` remains ready after resolving obsolete rows. |

## Verification Plan

- `curl -fsS --max-time 8 https://www.yn-sourcing.com/fin-ops-api/health/ready`
- Deployed-runtime read-only PostgreSQL aggregate query for outbox, dirty scope, readiness and dead-letter groups.
- `python -m fin_ops_platform.tools.runtime_queue_ops resolve-covered-dead-letters --limit 100 --dry-run`
- If prechecks pass: `python -m fin_ops_platform.tools.runtime_queue_ops resolve-covered-dead-letters --limit 100 --execute --reason historical_covered_dead_letter_resolution_20260625`
- Repeat health, aggregate and dry-run checks.
- Local repository checks before commit:
  - `bash scripts/verify.sh docs`
  - `git diff --check`
  - `git diff --cached --check`
