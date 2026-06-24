# Production App Worker Controlled Restart Readiness Runbook 2026-06-25

**Boundary:** `production:app-worker-controlled-restart-readiness-runbook`
**Final status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `cad71b1cdf8a2c2a5cdb432db120e36510540ebf`

## Target Boundary

Run one bounded production operation to clear app, dispatcher and runtime-worker processes after the preceding PostgreSQL controlled restart recovered `/dev/shm/PostgreSQL.*` objects but `/health/ready` still timed out.

This boundary is not a module closure claim. It is a controlled production operation intended to collect reliable readiness and worker evidence after PostgreSQL shared-memory recovery.

## Operation Scope

Allowed operation:

- Restart exactly these systemd units once:
  - `fin-ops.service`
  - `fin-ops-rabbitmq-dispatcher.service`
  - `fin-ops-worker@oa-sync.service`
  - `fin-ops-worker@workbench.service`
  - `fin-ops-worker@workbench-relation.service`
  - `fin-ops-worker@invoice-lifecycle.service`
  - `fin-ops-worker@workbench-matching.service`
  - `fin-ops-worker@bank-detail.service`
  - `fin-ops-worker@bank-account-balance.service`
  - `fin-ops-worker@no-oa-bank-batch.service`
  - `fin-ops-worker@turnover-ledger.service`
  - `fin-ops-worker@search-pending.service`
  - `fin-ops-worker@search.service`
  - `fin-ops-worker@search-secondary.service`
  - `fin-ops-worker@search-tertiary.service`
  - `fin-ops-worker@pending-invoice.service`
  - `fin-ops-worker@invoice-usage-collection.service`
  - `fin-ops-worker@invoice-lifecycle-secondary.service`
  - `fin-ops-worker@cost-tax.service`
  - `fin-ops-worker@cost-statistics.service`
  - `fin-ops-worker@tax-offset.service`
  - `fin-ops-worker@import.service`

Allowed read-only checks:

- root SSH identity;
- systemd unit status for PostgreSQL, API, dispatcher and the explicit worker unit list;
- `/health` and `/health/ready` local curl checks;
- `/dev/shm` PostgreSQL object listing;
- sanitized recent logs for API, dispatcher and selected failing workers;
- worker unit active/running count and restart counters.

Forbidden:

- print or source env files;
- print DSNs, passwords, tokens, cookies, private keys or secret env values;
- run `psql` or connect to PostgreSQL with app credentials;
- write DB, queue, dirty scopes, outbox, readiness, Redis, RabbitMQ or production files;
- deploy, change config, requeue, replay, consume or acknowledge worker events;
- restart PostgreSQL again in this boundary;
- discover and restart arbitrary `fin-ops-worker@*.service` units outside the explicit list above.

## Expected Risk

The operation briefly interrupts API requests, dispatcher publish wakeups and runtime worker polling. It does not modify database rows, queues, readiness state, dirty scopes, outbox events, RabbitMQ messages, Redis cache or release files. Because selected workers/dispatcher were already repeatedly restarting after PostgreSQL recovery, restarting the fixed runtime unit list is the least invasive operation that can clear stale process-local pools.

## Pre-Check Commands

```bash
ssh finops-prod-root 'set -u; printf "identity user=%s uid=%s host=%s time=%s\n" "$(whoami)" "$(id -u)" "$(hostname)" "$(date -Is)"'

ssh finops-prod-root 'set -u; units="postgresql.service fin-ops.service fin-ops-rabbitmq-dispatcher.service fin-ops-worker@oa-sync.service fin-ops-worker@workbench.service fin-ops-worker@workbench-relation.service fin-ops-worker@invoice-lifecycle.service fin-ops-worker@workbench-matching.service fin-ops-worker@bank-detail.service fin-ops-worker@bank-account-balance.service fin-ops-worker@no-oa-bank-batch.service fin-ops-worker@turnover-ledger.service fin-ops-worker@search-pending.service fin-ops-worker@search.service fin-ops-worker@search-secondary.service fin-ops-worker@search-tertiary.service fin-ops-worker@pending-invoice.service fin-ops-worker@invoice-usage-collection.service fin-ops-worker@invoice-lifecycle-secondary.service fin-ops-worker@cost-tax.service fin-ops-worker@cost-statistics.service fin-ops-worker@tax-offset.service fin-ops-worker@import.service"; echo "== pre units =="; for unit in $units; do echo "-- $unit"; systemctl show "$unit" -p LoadState -p ActiveState -p SubState -p Result -p NRestarts -p MainPID -p ExecMainStatus --no-pager || true; done'

ssh finops-prod-root 'set -u; echo "== pre health =="; for url in http://127.0.0.1:18001/health http://127.0.0.1:18001/health/ready; do echo "-- $url"; curl -sS -m 12 -w "\nHTTP:%{http_code} TIME:%{time_total}\n" "$url" | head -c 6000 || echo "curl_exit=$?"; echo; done'

ssh finops-prod-root 'set -u; echo "== pre postgres shm =="; find /dev/shm -maxdepth 1 \( -name "PostgreSQL.*" -o -name ".s.PGSQL.*" \) -printf "%f size=%s mode=%m owner=%u group=%g\n" 2>/dev/null | sort | head -80'
```

## Stop Gates

Do not run the restart command if pre-checks show:

- root SSH identity is unavailable;
- any command would require secret/env/DSN access;
- `postgresql.service` is not `active/running`;
- `/dev/shm/PostgreSQL.*` objects are absent again;
- any selected app/dispatcher/worker unit is not loaded;
- the operation would require a deploy, config change, DB write, queue mutation or arbitrary service discovery.

Stop after the restart and classify as `needs-human-production-gate` if:

- `fin-ops.service` cannot return to `active/running`;
- a majority of selected worker units cannot return to `active/running`;
- `/health` stops returning a ready payload;
- post-checks require config changes, DB writes or unbounded worker/queue operations;
- logs expose sensitive payloads that cannot be safely redacted.

## Operation Command

```bash
ssh finops-prod-root 'set -u; units="fin-ops.service fin-ops-rabbitmq-dispatcher.service fin-ops-worker@oa-sync.service fin-ops-worker@workbench.service fin-ops-worker@workbench-relation.service fin-ops-worker@invoice-lifecycle.service fin-ops-worker@workbench-matching.service fin-ops-worker@bank-detail.service fin-ops-worker@bank-account-balance.service fin-ops-worker@no-oa-bank-batch.service fin-ops-worker@turnover-ledger.service fin-ops-worker@search-pending.service fin-ops-worker@search.service fin-ops-worker@search-secondary.service fin-ops-worker@search-tertiary.service fin-ops-worker@pending-invoice.service fin-ops-worker@invoice-usage-collection.service fin-ops-worker@invoice-lifecycle-secondary.service fin-ops-worker@cost-tax.service fin-ops-worker@cost-statistics.service fin-ops-worker@tax-offset.service fin-ops-worker@import.service"; echo "restart_app_worker_start=$(date -Is)"; systemctl restart $units; echo "restart_app_worker_exit=$?"; echo "restart_app_worker_end=$(date -Is)"'
```

## Post-Check Commands

```bash
ssh finops-prod-root 'set -u; sleep 15; units="postgresql.service fin-ops.service fin-ops-rabbitmq-dispatcher.service fin-ops-worker@oa-sync.service fin-ops-worker@workbench.service fin-ops-worker@workbench-relation.service fin-ops-worker@invoice-lifecycle.service fin-ops-worker@workbench-matching.service fin-ops-worker@bank-detail.service fin-ops-worker@bank-account-balance.service fin-ops-worker@no-oa-bank-batch.service fin-ops-worker@turnover-ledger.service fin-ops-worker@search-pending.service fin-ops-worker@search.service fin-ops-worker@search-secondary.service fin-ops-worker@search-tertiary.service fin-ops-worker@pending-invoice.service fin-ops-worker@invoice-usage-collection.service fin-ops-worker@invoice-lifecycle-secondary.service fin-ops-worker@cost-tax.service fin-ops-worker@cost-statistics.service fin-ops-worker@tax-offset.service fin-ops-worker@import.service"; echo "== post units =="; for unit in $units; do echo "-- $unit"; systemctl show "$unit" -p LoadState -p ActiveState -p SubState -p Result -p NRestarts -p MainPID -p ExecMainStatus --no-pager || true; done'

ssh finops-prod-root 'set -u; echo "== post health =="; for url in http://127.0.0.1:18001/health http://127.0.0.1:18001/health/ready; do echo "-- $url"; curl -sS -m 30 -w "\nHTTP:%{http_code} TIME:%{time_total}\n" "$url" | head -c 10000 || echo "curl_exit=$?"; echo; done'

ssh finops-prod-root 'set -u; echo "== post postgres shm =="; find /dev/shm -maxdepth 1 \( -name "PostgreSQL.*" -o -name ".s.PGSQL.*" \) -printf "%f size=%s mode=%m owner=%u group=%g mtime=%TY-%Tm-%TdT%TH:%TM:%TS\n" 2>/dev/null | sort | head -80'

ssh finops-prod-root 'set -u; echo "== post selected logs sanitized =="; for unit in fin-ops.service fin-ops-rabbitmq-dispatcher.service fin-ops-worker@workbench.service fin-ops-worker@workbench-matching.service fin-ops-worker@workbench-relation.service fin-ops-worker@bank-detail.service; do echo "-- $unit"; journalctl -u "$unit" -n 40 --no-pager -o short-iso 2>/dev/null | sed -E "s#(postgres(ql)?://)[^ ]+#\1[redacted]#g; s#(password=)[^ ]+#\1[redacted]#g; s#(token=)[^ ]+#\1[redacted]#g; s#(cookie=)[^ ]+#\1[redacted]#g; s#(DATABASE_URL=)[^ ]+#\1[redacted]#g; s#(FIN_OPS_POSTGRES_DATABASE_URL=)[^ ]+#\1[redacted]#g" | tail -40; done'
```

## Rollback / Cleanup Posture

There is no data rollback command because this boundary only restarts process units. If the restart fails, stop further automation, preserve non-secret unit/health/log evidence, and classify `needs-human-production-gate`. Do not attempt config edits, deployment, DB writes, queue replay or readiness mutation as rollback.

## Success Criteria

Classify as `production-controlled` evidence only if:

- the restart command exits `0`;
- `fin-ops.service`, `fin-ops-rabbitmq-dispatcher.service` and all selected worker units are `active/running`;
- PostgreSQL remains `active/running` and `/dev/shm/PostgreSQL.*` remains present;
- `/health` returns ready;
- `/health/ready` returns a concrete HTTP status within the timeout, preferably ready;
- no secrets are printed and no forbidden mutation occurs.

Otherwise classify as `production-evidence-deferred` or `needs-human-production-gate` with exact evidence.

## Evidence Results

Executed at approximately `2026-06-25T01:35-01:38+08:00` through `ssh finops-prod-root`.

### Pre-Checks

Identity:

```text
identity user=root uid=0 host=VM-0-6-opencloudos time=2026-06-25T01:35:31+08:00
```

Pre-unit status:

- `postgresql.service`, `fin-ops.service`, `fin-ops-rabbitmq-dispatcher.service` and all 20 selected `fin-ops-worker@*.service` units were `loaded/active/running`.
- Worker/dispatcher `NRestarts` values were high before the operation, ranging from `861` to `942` for selected runtime services, confirming stale process-loop evidence after the PostgreSQL shared-memory recovery.
- PostgreSQL stayed `active/running` with `MainPID=3346879`.

Pre-health:

- `/health` returned `HTTP:200`, `status=ready`, release `main-bf4405fb-20260623194934`, `runtime_release.consistent=true` and `production_runtime_guard.consistent=true`.
- `/health/ready` returned a concrete `HTTP:200` payload within the timeout instead of the earlier timeout. The sampled payload exposed remaining runtime-infrastructure blockers:
  - `queue_backlog={'dead_lettered': 1}`;
  - `dirty_scopes={'done': 187006, 'pending': 1}`;
  - `failed_jobs=1`;
  - one stale dirty scope: `no_oa_bank_batch:all`;
  - one dead-lettered outbox event: `no_oa_bank_batch.read_model.refresh` / `all`.
- `/dev/shm/PostgreSQL.*` objects were present before app/worker restart.

No stop gate was triggered: root SSH worked, PostgreSQL was running, `/dev/shm/PostgreSQL.*` was present, all selected units were loaded, and no secret/env/DSN access was needed.

### Operation

```text
restart_app_worker_start=2026-06-25T01:36:03+08:00
restart_app_worker_exit=0
restart_app_worker_end=2026-06-25T01:36:03+08:00
```

Classification: controlled production operation completed.

### Immediate Post-Check

Fifteen seconds after the restart:

- `postgresql.service` remained `active/running`.
- `fin-ops.service` returned `active/running` with `MainPID=3350065`, `NRestarts=0`.
- `fin-ops-rabbitmq-dispatcher.service` returned `active/running` with `MainPID=3350062`, `NRestarts=0`.
- All 20 selected `fin-ops-worker@*.service` units returned `active/running`, `Result=success`, `ExecMainStatus=0`, `NRestarts=0`.
- `/dev/shm/PostgreSQL.*` objects remained present after restart.

`/health` and `/health/ready` structured summary:

```text
/health curl_returncode=0 HTTP=200 TIME=0.004956 status=ready
/health/ready curl_returncode=0 HTTP=200 TIME=2.816792 status=ready
release=main-bf4405fb-20260623194934
release_consistent=True
production_runtime_guard_consistent=True
queue_backlog={'dead_lettered': 1}
dirty_scopes={'done': 187006, 'pending': 1}
failed_jobs=1
stale_dirty_scope_count=1
missing_required_worker_count=0
stale_required_worker_count=0
mismatched_required_worker_count=0
rabbitmq_queue_depth=0
rabbitmq_unacked_messages=0
rabbitmq_dlq_count=0
worker_status_counts={'available': 21}
```

Remaining read-model blocker evidence:

```text
stale_dirty_scopes_summary:
scope_type=no_oa_bank_batch scope_key=all status=pending age_seconds~=104519 attempts=0

pending_outbox_events_by_scope_summary:
event_type=no_oa_bank_batch.read_model.refresh status=dead_lettered scope_key=all attempts=5
last_error=update or delete on table "no_oa_bank_batches" violates foreign key constraint "no_oa_bank_batch_events_no_oa_bank_batch_id_fkey" on table "no_oa_bank_batch_events"
```

No DSN, token, cookie, password, secret env value or private key was printed.

### Stability Recheck

Approximately 45 seconds after the restart:

- `fin-ops.service`, `fin-ops-rabbitmq-dispatcher.service`, `fin-ops-worker@workbench.service`, `fin-ops-worker@workbench-matching.service`, `fin-ops-worker@workbench-relation.service`, `fin-ops-worker@bank-detail.service` and `fin-ops-worker@no-oa-bank-batch.service` were still `active/running`, `Result=success`, `NRestarts=0`.
- `/health/ready` returned `HTTP:200` in `0.600410s`, `status=ready`.
- The same single `no_oa_bank_batch:all` pending/dead-letter evidence remained.
- A post-restart grep of selected dispatcher/workbench/bank-detail logs since `2026-06-25 01:36:03` found no new `PoolTimeout`, missing shared-memory, `FATAL`, `Main process exited` or `Failed with result` lines.

### Log Evidence

Selected sanitized logs show the restart itself and previous PostgreSQL pool/shared-memory failures before the operation. After `2026-06-25T01:36:03+08:00`, selected logs only show systemd stop/start lines in the sampled output; no new PostgreSQL shared-memory or pool-timeout failure appeared.

## Result Classification

`production-evidence-deferred`.

Reason:

- The controlled app/dispatcher/worker restart succeeded and all selected runtime units stayed `active/running` with `NRestarts=0` through the stability recheck.
- `/health/ready` recovered from timeout and returned `status=ready` within 3 seconds immediately after restart and within 1 second on the stability recheck.
- Full modular IO production closure is still not claimed because the readiness payload exposes one stale `no_oa_bank_batch:all` dirty scope and one dead-lettered `no_oa_bank_batch.read_model.refresh` outbox event with an FK violation.
- This boundary intentionally did not mutate DB, queue, readiness rows, dirty scopes, outbox, Redis, RabbitMQ messages or release files.

## Next Safe Boundary

```text
production:no-oa-bank-batch-dead-letter-read-only-diagnosis
```

Purpose:

- Diagnose the remaining production blocker using non-secret read-only evidence only.
- Explain the stale dirty scope and dead-lettered outbox event contract around `no_oa_bank_batch:all`.
- Do not requeue, mark done, delete rows, repair FK data or run worker replay until a later controlled production runbook proves the exact scope and cleanup safety.
