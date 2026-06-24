# Production Read Model Scope Contract Runtime Dry Run Classification 2026-06-25

**Boundary:** `production:read-model-scope-contract-runtime-dry-run-classification`
**Final status:** `production-controlled`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `e5497c81`
**Production release for checks:** `dev-workbench-matching-port-20260625020818`

## Target

Run the existing production read-model scope-contract checker in dry-run/read-only mode, classify legacy or invalid runtime scope rows, identify whether any row is a current-effective blocker, and produce an apply-or-defer decision.

This boundary exists because row245 found historical legacy `cost` and `tax` dirty-scope rows as `done` rows while the current read-model production matrix was otherwise clean. The row245 matrix did not prove browser/API/high-row or module-specific closure.

## Allowed Operations

- Public `/health/ready` summary.
- Root SSH invocation of `/usr/local/sbin/finops-deploy-control read-model-scope-contract <release> --json`.
- Root SSH invocation of `/usr/local/sbin/finops-deploy-control read-model-scope-contract <release> --repair invalid-read-model-scopes --json`.
- Non-secret read-only deployed-runtime aggregate checks for legacy `cost` / `tax` dirty-scope status counts if needed to classify row245 residue.

## Forbidden Operations

- `--apply`.
- Deploy, restart, reload, stop, start or kill production services.
- Requeue, republish, repair, resolve, worker replay or broad queue consume.
- Direct SQL `insert`, `update`, `delete`, DDL or readiness/dirty-scope/outbox mutation.
- Printing env files, DSNs, passwords, tokens, cookies, private keys or secret env values.
- Guessing unknown scope contracts.

## Evidence Plan

1. Confirm `/health/ready` remains ready.
2. Run the cost-statistics scope contract checker dry-run with `--json`.
3. Run the invalid read-model scope checker dry-run with `--repair invalid-read-model-scopes --json`.
4. If checker output does not include the row245 `cost` / `tax` historical `done` rows, classify them using read-only aggregate evidence from row245 plus current non-done/current-effective checks.
5. Record whether there are:
   - legacy or invalid cost statistics runtime rows;
   - covered historical outbox failures;
   - current uncovered outbox failures;
   - invalid policy-managed read-model scope rows;
   - current-effective `cost` / `tax` blockers.
6. Decide whether `--apply` is needed, should be deferred, or is unnecessary.

## Stop Gates

Stop and classify precisely if:

- `/health/ready` regresses.
- The checker finds current uncovered failures.
- The invalid-scope checker finds current-effective invalid rows that require a cleanup decision broader than dry-run classification.
- Any evidence collection would require production mutation or secret output.
- The checker requires guessing a replacement scope for an unknown contract.

## Execution Results

Executed non-secret production dry-run classification against release `dev-workbench-matching-port-20260625020818`.

### Health Baseline

The first `/health/ready` attempt used the wrong local port `8080` and failed with connection refused. This was a probe error, not an application health result.

Read-only `systemctl show fin-ops.service` showed the API is active on `127.0.0.1:18001`:

- `ActiveState=active`;
- `SubState=running`;
- `NRestarts=0`;
- `ExecMainStatus=0`;
- `ExecStart=/opt/fin-ops/venv/bin/python -m fin_ops_platform.app.main --host 127.0.0.1 --port 18001`.

`/health/ready` on `127.0.0.1:18001` returned:

- `status=ready`;
- release `dev-workbench-matching-port-20260625020818`;
- git commit `b256db3a8fc370ce93e7b51bf62b1cd33176475d`;
- release metadata `consistent=True`;
- production runtime guard `consistent=True`;
- storage backend `postgres`;
- `queue_backlog={}`;
- `dirty_scopes={"done": 187007}`;
- `failed_jobs=0`;
- `stale_dirty_scope_count=0`;
- required worker missing/stale/mismatch counts all `0`;
- `worker_status_counts={"available": 21}`;
- RabbitMQ queue depth, unacked messages and DLQ counts all `0`;
- `read_model_refresh_failure_rate=0.0`.

The two worker problem samples remain old non-required and non-current-effective rows:

- `operator-cost-statistics-drain-after-deploy-20260606`;
- `codex-oa-pending-payment-refresh-2`.

They are not current blockers.

### Cost Statistics Scope Contract Dry-Run

Command:

```bash
sudo -n /usr/local/sbin/finops-deploy-control read-model-scope-contract \
  dev-workbench-matching-port-20260625020818 \
  --json
```

Result:

- `ok=true`;
- `violation_count=0`;
- `covered_historical_outbox_failure_count=0`;
- `current_uncovered_outbox_failure_count=0`;
- `replacement_scope_keys=[]`;
- `violations=[]`;
- `repair_manifest.items=[]`;
- all `repair_manifest.summary` counters are `0`.

Classification: there are no legacy/invalid cost statistics dirty scopes, outbox events or readiness rows that the current checker classifies as repair candidates. There are no covered historical or current uncovered read-model outbox failures.

### Invalid Read Model Scope Dry-Run

Command:

```bash
sudo -n /usr/local/sbin/finops-deploy-control read-model-scope-contract \
  dev-workbench-matching-port-20260625020818 \
  --repair invalid-read-model-scopes \
  --json
```

Result:

- `ok=true`;
- `invalid_scope_count=0`;
- `items=[]`;
- `cleanup.applied=false`;
- cleanup deleted counts for `job.outbox_events`, `job.read_model_dirty_scopes` and `read_model.app_status_readiness` are all `0`;
- summary counts for the same locations are all `0`.

Classification: there are no current invalid policy-managed read-model scope rows requiring cleanup.

### Legacy `cost` / `tax` Runtime Row Classification

The checker intentionally focuses on current cost-statistics scope contract violations and policy-managed invalid rows. Row245's legacy `cost` / `tax` rows were `done` historical dirty-scope rows, so T0 ran an additional non-secret read-only aggregate using the active release runtime configuration without printing env values or DSNs.

Result:

| Evidence | Result |
| --- | --- |
| `job.read_model_dirty_scopes` for `scope_type='cost'` | `done=8`, latest `2026-06-19 00:46:30.827714+08` |
| `job.read_model_dirty_scopes` for `scope_type='tax'` | `done=8`, latest `2026-06-19 00:46:30.827714+08` |
| non-`done` `cost` / `tax` dirty-scope samples | `[]` |
| active non-`done` `cost` / `tax` read-model outbox rows | `[]` |
| `cost` / `tax` readiness rows | `[]` |

Classification: the legacy `cost` and `tax` rows are historical completed dirty-scope rows only. They are not current-effective blockers, have no active outbox counterpart and have no readiness rows.

## Decision

Decision: `production-controlled`.

No `--apply` is needed in this slice.

Rationale:

- `/health/ready` is ready on the active API port.
- The cost-statistics scope contract dry-run is clean.
- The invalid read-model scope dry-run is clean.
- Row245's legacy `cost` / `tax` residue is historical `done` dirty-scope state only, not a current-effective blocker.

This decision does not claim module/global closure. Browser/API/high-row smoke and module-specific closure audits remain open.

## Next Boundary Selection

Select `planning:post-scope-contract-runtime-classification-next-boundary-selection`.

The next slice should reconcile row245 and row246 evidence and select the safest next closure action, likely either a module-specific production closure audit wave or a bounded browser/API/high-row smoke plan. It should not create workers or claim closure before mapping file ownership and evidence gaps.

## Docs Impact

No long-term docs update is required. This boundary executed existing documented dry-run governance and did not change runtime behavior, API contracts, worker state definitions, read model scope policy, permissions or UI behavior.

## Seven Test Categories

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business logic changed. |
| 2. Service-layer tests | Not applicable | No service/repository/worker code changed. |
| 3. API contract tests | Not applicable | No HTTP contract changed. |
| 4. Read model/cache/background job tests | Covered by production dry-run evidence | This boundary classifies read-model runtime scope-contract state and current-effective blockers. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable | No cross-module business flow changed. |
| 7. Existing feature regression tests | Covered by production dry-run evidence | Safety regression is no current uncovered scope-contract failure or invalid current-effective read-model scope. |

## Verification Plan

- Production dry-run commands listed above.
- Local repository checks before commit:
  - `bash scripts/verify.sh docs`
  - `git diff --check`
  - `git diff --cached --check`
