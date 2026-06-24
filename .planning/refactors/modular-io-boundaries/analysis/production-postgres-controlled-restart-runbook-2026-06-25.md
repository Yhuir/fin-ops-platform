# Production PostgreSQL Controlled Restart Runbook 2026-06-25

**Boundary:** `production:postgres-controlled-restart-runbook`
**Final status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `75fb80c9dd16f903df08b6e5663ddf8289134aa6`

## Target Boundary

Run one bounded production operation to recover PostgreSQL POSIX shared-memory state after read-only evidence showed:

- `/health/ready` timing out;
- app workers/dispatcher in restart loops;
- PostgreSQL active/listening but file logs continuously reporting `could not open shared memory segment "/PostgreSQL.2926794240"`;
- `/dev/shm` having capacity but no `PostgreSQL.*` objects.

This boundary is not a module closure claim. It is a controlled production operation intended to restore the runtime prerequisite needed before collecting reliable production readiness/worker evidence.

## Operation Scope

Allowed operation:

- `systemctl restart postgresql.service` exactly once.

Allowed read-only checks:

- root SSH identity;
- systemd unit status for PostgreSQL, API, selected workers and dispatcher;
- `/health` and `/health/ready` local curl checks;
- PostgreSQL file-log tail with redaction;
- `/dev/shm` PostgreSQL object listing;
- selected worker restart counters.

Forbidden:

- print or source env files;
- print DSNs, passwords, tokens, cookies, private keys or secret env values;
- run `psql` or connect to PostgreSQL with app credentials;
- write DB, queue, dirty scopes, outbox, readiness, Redis, RabbitMQ or production files;
- deploy, change config, requeue, replay, consume or acknowledge worker events;
- restart app/worker services in this boundary unless a later runbook explicitly selects that operation.

## Expected Risk

`systemctl restart postgresql.service` will briefly drop active PostgreSQL connections. The system is already failing to open PostgreSQL shared-memory segments and workers are repeatedly restarting, so this bounded restart is the least invasive operation that can recreate PostgreSQL shared-memory objects without touching app data.

## Pre-Check Commands

```bash
ssh finops-prod-root 'set -u; printf "identity user=%s uid=%s host=%s time=%s\n" "$(whoami)" "$(id -u)" "$(hostname)" "$(date -Is)"'

ssh finops-prod-root 'set -u; echo "== pre units =="; for unit in postgresql.service fin-ops.service fin-ops-worker@workbench.service fin-ops-rabbitmq-dispatcher.service; do echo "-- $unit"; systemctl show "$unit" -p ActiveState -p SubState -p Result -p NRestarts -p MainPID -p ExecMainStatus --no-pager || true; done'

ssh finops-prod-root 'set -u; echo "== pre health =="; for url in http://127.0.0.1:18001/health http://127.0.0.1:18001/health/ready; do echo "-- $url"; curl -sS -m 8 -w "\nHTTP:%{http_code} TIME:%{time_total}\n" "$url" | head -c 4000 || echo "curl_exit=$?"; echo; done'

ssh finops-prod-root 'set -u; echo "== pre dev shm postgres objects =="; find /dev/shm -maxdepth 1 \( -name "PostgreSQL.*" -o -name ".s.PGSQL.*" \) -printf "%f size=%s mode=%m owner=%u group=%g\n" 2>/dev/null | sort | head -80'
```

## Operation Command

```bash
ssh finops-prod-root 'set -u; echo "restart_postgresql_start=$(date -Is)"; systemctl restart postgresql.service; echo "restart_postgresql_exit=$?"; echo "restart_postgresql_end=$(date -Is)"'
```

## Post-Check Commands

```bash
ssh finops-prod-root 'set -u; echo "== post postgresql unit =="; systemctl show postgresql.service -p ActiveState -p SubState -p Result -p NRestarts -p MainPID -p ExecMainStatus --no-pager; echo "== post dev shm postgres objects =="; find /dev/shm -maxdepth 1 \( -name "PostgreSQL.*" -o -name ".s.PGSQL.*" \) -printf "%f size=%s mode=%m owner=%u group=%g mtime=%TY-%Tm-%TdT%TH:%TM:%TS\n" 2>/dev/null | sort | head -80'

ssh finops-prod-root 'set -u; sleep 5; echo "== post selected units =="; for unit in fin-ops.service fin-ops-worker@workbench.service fin-ops-worker@workbench-matching.service fin-ops-worker@workbench-relation.service fin-ops-rabbitmq-dispatcher.service; do echo "-- $unit"; systemctl show "$unit" -p ActiveState -p SubState -p Result -p NRestarts -p MainPID -p ExecMainStatus --no-pager || true; done'

ssh finops-prod-root 'set -u; echo "== post health =="; for url in http://127.0.0.1:18001/health http://127.0.0.1:18001/health/ready; do echo "-- $url"; curl -sS -m 15 -w "\nHTTP:%{http_code} TIME:%{time_total}\n" "$url" | head -c 6000 || echo "curl_exit=$?"; echo; done'

ssh finops-prod-root 'set -u; echo "== post postgres log tail sanitized =="; latest="$(ls -1t /var/lib/pgsql/data/log/* 2>/dev/null | head -1 || true)"; if [ -n "$latest" ]; then printf "latest_log=%s\n" "$latest"; tail -80 "$latest" | sed -E "s#(postgres(ql)?://)[^ ]+#\1[redacted]#g; s#(password=)[^ ]+#\1[redacted]#g; s#(token=)[^ ]+#\1[redacted]#g; s#(cookie=)[^ ]+#\1[redacted]#g; s#(DATABASE_URL=)[^ ]+#\1[redacted]#g; s#(FIN_OPS_POSTGRES_DATABASE_URL=)[^ ]+#\1[redacted]#g"; else echo "no_postgres_file_log_found"; fi'
```

## Stop Gates

Do not run the restart command if pre-checks show:

- current branch/worktree cannot safely record evidence after operation;
- SSH root identity is not available;
- operation would require secret/env/DSN access;
- PostgreSQL unit is not loaded as `postgresql.service`;
- commands would mutate DB/queue/readiness or require app/worker restart in the same step.

Stop after the restart and classify as `needs-human-production-gate` if:

- `postgresql.service` fails to return to `active/running`;
- post-checks require DB writes, config changes or service changes beyond this runbook;
- logs expose sensitive payloads that cannot be safely redacted.

## Rollback / Cleanup Posture

There is no data rollback command for a service restart. If PostgreSQL fails to come back, the bounded cleanup posture is to stop further automation, preserve non-secret status/log evidence, and classify `needs-human-production-gate`.

This runbook does not perform database repair, config changes, app restart or worker restart.

## Success Criteria

Classify as `production-controlled` only if:

- PostgreSQL restart exits `0`;
- `postgresql.service` is `active/running`;
- `PostgreSQL.*` objects appear in `/dev/shm` or the missing shared-memory errors stop in the sampled post-log tail;
- `/health/ready` returns a concrete HTTP status instead of timing out, or the remaining readiness issue is clearly outside PostgreSQL shared-memory failure;
- no secrets are printed and no forbidden mutation occurs.

Otherwise classify as `production-evidence-deferred` or `needs-human-production-gate` with exact evidence.

## Evidence Results

Executed at approximately `2026-06-25T01:30+08:00` through `ssh finops-prod-root`.

### Pre-Checks

Identity:

```text
identity user=root uid=0 host=VM-0-6-opencloudos time=2026-06-25T01:29:45+08:00
```

Pre-unit status:

| Unit | Active/SubState | MainPID | NRestarts | Evidence meaning |
| --- | --- | ---: | ---: | --- |
| `postgresql.service` | `active/running` | 370441 | 0 | PostgreSQL was loaded and running before restart. |
| `fin-ops.service` | `active/running` | 2004389 | 0 | API process was running. |
| `fin-ops-worker@workbench.service` | `active/running` | 3346242 | 860 | Worker restart loop still active. |
| `fin-ops-rabbitmq-dispatcher.service` | `active/running` | 3345913 | 941 | Dispatcher restart loop still active. |

Pre-health:

- `/health` returned `status=ready` with runtime release and production guard consistency.
- `/health/ready` timed out after `8.000719s` with `HTTP:000`.
- `/dev/shm` had no `PostgreSQL.*` objects.

No stop gate was triggered before the restart: root SSH worked, `postgresql.service` was loaded, no secrets were required, and the selected operation was exactly one PostgreSQL service restart.

### Operation

```text
restart_postgresql_start=2026-06-25T01:30:09+08:00
restart_postgresql_exit=0
restart_postgresql_end=2026-06-25T01:30:09+08:00
```

Classification: controlled production operation completed.

### Post PostgreSQL State

```text
postgresql.service ActiveState=active SubState=running MainPID=3346879 Result=success
```

`/dev/shm` PostgreSQL objects appeared after restart:

```text
PostgreSQL.1306399422 size=1048576
PostgreSQL.1511106930 size=26976
PostgreSQL.2792738702 size=196736
```

PostgreSQL log tail shows:

```text
LOG: database system is shut down
LOG: starting PostgreSQL 16.12
LOG: listening on IPv4 address "127.0.0.1", port 5432
LOG: database system is ready to accept connections
```

The old missing shared-memory errors appear only before the restart timestamp in the sampled post-log tail. No DSN, token, cookie, password or secret env value was printed.

Classification: `production-controlled` evidence for PostgreSQL shared-memory recovery.

### Post App / Worker State

Selected units after restart:

| Unit | Active/SubState | MainPID | NRestarts | Evidence meaning |
| --- | --- | ---: | ---: | --- |
| `fin-ops.service` | `active/running` | 2004389 | 0 | API process stayed up. |
| `fin-ops-worker@workbench.service` | `active/running` | 3347042 | 861 | Worker restarted once more after pre-check. |
| `fin-ops-worker@workbench-matching.service` | `active/running` | 3347135 | 894 | Worker still recently restarted. |
| `fin-ops-worker@workbench-relation.service` | `active/running` | 3346479 | 903 | Worker still recently restarted. |
| `fin-ops-rabbitmq-dispatcher.service` | `active/running` | 3346731 | 942 | Dispatcher still recently restarted. |

Post-health:

- `/health` still returned `status=ready`.
- `/health/ready` still timed out after `15.001531s` with `HTTP:000`.

Classification: `production-evidence-deferred` for full readiness and worker closure.

## Result Classification

`production-evidence-deferred`.

Reason:

- The controlled PostgreSQL restart succeeded and recreated PostgreSQL shared-memory objects.
- PostgreSQL logs show the new postmaster is ready to accept connections.
- Full production readiness is still not proven because `/health/ready` continues to time out.
- Selected workers/dispatcher remain active but recently restarted; app/worker process pools may still hold stale state or a separate readiness bottleneck may exist.
- This boundary intentionally did not restart app or worker services because that was outside the selected operation.

## Next Safe Boundary

```text
production:app-worker-controlled-restart-readiness-runbook
```

Purpose:

- Prepare a T0-controlled production operation runbook for bounded app/worker restart and readiness post-checks after PostgreSQL shared-memory recovery.
- Keep the operation explicit and bounded: selected app service, dispatcher and worker units only if pre-checks prove it is safe.
- Do not mutate DB, queue, readiness rows, dirty scopes, outbox or business data.
