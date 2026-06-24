# Production PostgreSQL Shared-Memory Read-Only Diagnosis 2026-06-25

**Boundary:** `production:postgres-shared-memory-read-only-diagnosis`
**Final status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `3a3a9777f3ae4650d834144826634a3c0e7eec6c`

## Target Boundary

Investigate the production PostgreSQL shared-memory / connection failure seen in `production-readiness-worker-status-controlled-read-only-2026-06-25.md`:

```text
psycopg_pool.PoolTimeout: couldn't get a connection after 30.00 sec
connection to server at "127.0.0.1", port 5432 failed:
FATAL: could not open shared memory segment "/PostgreSQL.2926794240": No such file or directory
```

This boundary only collects non-secret read-only OS, systemd, resource and sanitized log evidence. It does not repair production.

## Safety Classification

Allowed:

- `ssh finops-prod-root` identity check.
- Read-only `systemctl show` / `systemctl is-active` for PostgreSQL and fin-ops units.
- Read-only process inspection with `ps`.
- Read-only port/process listing with `ss`.
- Read-only filesystem, memory, shared-memory and kernel parameter inspection: `df`, `free`, `ipcs`, `sysctl`.
- Bounded `journalctl` excerpts with obvious secret-pattern redaction.

Forbidden:

- Source or print env files.
- Print DSNs, tokens, cookies, private keys or secret env values.
- Connect to PostgreSQL using application credentials or secret-bearing DSNs.
- Run `psql`.
- Restart, reload, stop, start, kill or reconfigure PostgreSQL/app/worker services.
- Mutate DB, Redis, RabbitMQ, queue, readiness, dirty scopes, outbox, worker state or production files.
- Replay, consume, requeue or acknowledge worker events.

## Exact Commands

```bash
ssh finops-prod-root 'set -u; printf "identity user=%s uid=%s host=%s time=%s\n" "$(whoami)" "$(id -u)" "$(hostname)" "$(date -Is)"'

ssh finops-prod-root 'set -u; for unit in postgresql.service postgresql-15.service postgresql-16.service postgresql@15-main.service fin-ops.service fin-ops-worker@workbench.service fin-ops-rabbitmq-dispatcher.service; do echo "== $unit =="; systemctl is-active "$unit" 2>/dev/null || true; systemctl show "$unit" -p LoadState -p ActiveState -p SubState -p Result -p NRestarts -p ExecMainStatus -p ExecMainCode -p MainPID -p FragmentPath --no-pager 2>/dev/null || true; done'

ssh finops-prod-root 'set -u; echo "== postgres processes =="; ps -eo pid,ppid,user,stat,etime,%cpu,%mem,comm,args --sort=pid | awk '\''/postgres|postmaster|fin_ops_platform|rabbitmq_dispatcher/ && !/awk/ {print}'\'' | head -120'

ssh finops-prod-root 'set -u; echo "== listening 5432 =="; ss -ltnp 2>/dev/null | awk '\''NR==1 || /:5432/ {print}'\''; echo "== unix sockets postgres =="; ss -lxnp 2>/dev/null | awk '\''NR==1 || /postgres|\\.s\\.PGSQL/ {print}'\'' | head -80'

ssh finops-prod-root 'set -u; echo "== filesystem =="; df -h / /dev/shm /tmp /var /opt 2>/dev/null || true; echo "== memory =="; free -h; echo "== shared memory segments =="; ipcs -m 2>/dev/null | head -80; echo "== semaphore arrays =="; ipcs -s 2>/dev/null | head -80'

ssh finops-prod-root 'set -u; echo "== sysctl shared memory =="; for key in kernel.shmmax kernel.shmall kernel.shmmni kernel.sem vm.overcommit_memory vm.max_map_count; do sysctl "$key" 2>/dev/null || true; done'

ssh finops-prod-root 'set -u; echo "== postgres logs sanitized =="; journalctl -u postgresql.service -u postgresql-15.service -u postgresql-16.service -n 120 --no-pager -o short-iso 2>/dev/null | sed -E "s#(postgres(ql)?://)[^ ]+#\1[redacted]#g; s#(password=)[^ ]+#\1[redacted]#g; s#(token=)[^ ]+#\1[redacted]#g; s#(cookie=)[^ ]+#\1[redacted]#g; s#(DATABASE_URL=)[^ ]+#\1[redacted]#g; s#(FIN_OPS_POSTGRES_DATABASE_URL=)[^ ]+#\1[redacted]#g" | tail -120'

ssh finops-prod-root 'set -u; echo "== postgres file logs sanitized =="; latest="$(ls -1t /var/lib/pgsql/data/log/* 2>/dev/null | head -1 || true)"; if [ -n "$latest" ]; then printf "latest_log=%s\n" "$latest"; tail -160 "$latest" | sed -E "s#(postgres(ql)?://)[^ ]+#\1[redacted]#g; s#(password=)[^ ]+#\1[redacted]#g; s#(token=)[^ ]+#\1[redacted]#g; s#(cookie=)[^ ]+#\1[redacted]#g; s#(DATABASE_URL=)[^ ]+#\1[redacted]#g; s#(FIN_OPS_POSTGRES_DATABASE_URL=)[^ ]+#\1[redacted]#g"; else echo "no_postgres_file_log_found"; fi'

ssh finops-prod-root 'set -u; echo "== dev shm postgres objects =="; find /dev/shm -maxdepth 1 \( -name "PostgreSQL.*" -o -name ".s.PGSQL.*" \) -printf "%f size=%s mode=%m owner=%u group=%g mtime=%TY-%Tm-%TdT%TH:%TM:%TS\n" 2>/dev/null | sort | head -120'
```

## Expected Evidence

- Whether a PostgreSQL systemd unit is active.
- Whether PostgreSQL/postmaster processes exist and how long they have been running.
- Whether port `127.0.0.1:5432` is listening.
- Whether `/dev/shm`, memory, semaphore or shared-memory segment state shows an OS-level resource issue.
- Whether PostgreSQL logs explain the missing shared memory segment without exposing secrets.

## Rollback / Cleanup Commands

None. Commands are read-only.

If any command appears to require mutation or secret output, stop immediately and do not run that command family.

## Stop Gates

Classify as `needs-human-production-gate` if:

- PostgreSQL diagnosis requires reading secret env or application DSN.
- A fix requires service restart/reload, DB repair, config changes, filesystem cleanup or queue/readiness mutation.
- Logs contain sensitive payloads that cannot be safely redacted.
- The shared-memory issue cannot be understood from non-secret read-only OS/systemd evidence.

## Post-Checks

After evidence collection:

- Confirm no production mutation was performed.
- Summarize evidence without secrets.
- Update controller state and next boundary.
- Run `bash scripts/verify.sh docs`, `git diff --check`, and `git diff --cached --check` before commit.

## Evidence Results

Executed at approximately `2026-06-25T01:25+08:00` through `ssh finops-prod-root`.

### Identity

```text
identity user=root uid=0 host=VM-0-6-opencloudos time=2026-06-25T01:25:04+08:00
```

Classification: `production-read-only`.

### Unit State

| Unit | Load/Active/SubState | MainPID | NRestarts | Evidence meaning |
| --- | --- | ---: | ---: | --- |
| `postgresql.service` | `loaded/active/running` | 370441 | 0 | PostgreSQL postmaster is running. |
| `postgresql@15-main.service` | `loaded/inactive/dead` | 0 | 0 | Not the active cluster unit. |
| `fin-ops.service` | `loaded/active/running` | 2004389 | 0 | API process is running. |
| `fin-ops-worker@workbench.service` | `loaded/active/running` | 3339898 | 852 | Worker is currently running but restart counter keeps increasing. |
| `fin-ops-rabbitmq-dispatcher.service` | `loaded/active/running` | 3339705 | 933 | Dispatcher is currently running but restart counter keeps increasing. |

Classification: `production-read-only`; active units do not prove readiness because restart counters are high and `/health/ready` timed out in the previous boundary.

### Process And Socket Evidence

- PostgreSQL postmaster has been running for `11-23:44:49` with PID `370441`.
- PostgreSQL listens on `127.0.0.1:5432`, `[::1]:5432`, `/tmp/.s.PGSQL.5432` and `/var/run/postgresql/.s.PGSQL.5432`.
- Fin-ops worker processes were mostly only seconds old during sampling, consistent with restart loops.

Classification: `production-read-only`; PostgreSQL is reachable at the socket/listener layer, but connection attempts fail inside PostgreSQL shared-memory attachment.

### Filesystem / Memory / IPC Evidence

```text
/dev/shm: 3.7G total, 1.1M used, 3.7G available
Mem: 7.4Gi total, 6.1Gi used, 1.3Gi available
Swap: 19Gi total, 8.8Gi used
ipcs -m: one postgres-owned 56-byte segment with 6 attachments
ipcs -s: no semaphore arrays listed
```

Sysctl values were not obviously restrictive:

```text
kernel.shmmax = 18446744073692774399
kernel.shmall = 18446744073692774399
kernel.shmmni = 4096
kernel.sem = 32000 1024000000 500 32000
vm.overcommit_memory = 0
vm.max_map_count = 65530
```

Classification: `production-read-only`; no disk-full or `/dev/shm` capacity issue was found.

### PostgreSQL Journal Evidence

Systemd journal for PostgreSQL shows the currently active postmaster started on `2026-06-13T01:40:26+08:00`. It also says future PostgreSQL logs are in the PostgreSQL `log` directory.

Classification: `production-read-only`.

### PostgreSQL File Log Evidence

Latest file log: `/var/lib/pgsql/data/log/postgresql-Thu.log`.

The latest PostgreSQL log repeatedly reports:

```text
FATAL: could not open shared memory segment "/PostgreSQL.2926794240": No such file or directory
ERROR: could not open shared memory segment "/PostgreSQL.2926794240": No such file or directory
```

The same error repeated continuously across the sampled tail from `2026-06-25 01:25:44` through `2026-06-25 01:26:14`.

No DSN, token, cookie, password or secret env value was printed by the collected excerpt.

Classification: `production-read-only`; this confirms the worker/app failures are caused by a current PostgreSQL shared-memory attachment failure, not only by app code.

### `/dev/shm` PostgreSQL Object Evidence

The read-only `/dev/shm` object check returned no `PostgreSQL.*` or `.s.PGSQL.*` objects:

```text
== dev shm postgres objects ==
```

Classification: `production-read-only`; PostgreSQL is running, but the expected POSIX dynamic shared-memory object named in the error is absent.

## Result Classification

`production-evidence-deferred`.

Reason:

- The issue is current and production-wide enough to block readiness and worker evidence closure.
- PostgreSQL is active and listening, but connection attempts are failing inside PostgreSQL with missing shared-memory segment errors.
- `/dev/shm` has available capacity but no matching `PostgreSQL.*` objects.
- Restarting/reloading PostgreSQL or app workers is outside this read-only boundary and would be a production mutation.

## Next Safe Boundary

```text
production:postgres-controlled-restart-runbook
```

Purpose:

- Prepare a T0-controlled production operation runbook for a bounded PostgreSQL restart and app/worker post-check.
- Include pre-checks, exact commands, stop gates, rollback/cleanup posture, expected downtime/risk, post-checks and evidence capture.
- Do not proceed if the runbook cannot prove bounded scope or if secrets would be required.

This next boundary is a controlled production operation, not a worker task.
