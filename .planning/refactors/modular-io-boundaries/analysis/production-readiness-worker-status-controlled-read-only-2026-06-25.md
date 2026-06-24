# Production Readiness And Worker Status Controlled Read-Only Evidence 2026-06-25

**Boundary:** `production:readiness-and-worker-status-controlled-read-only-runbook`
**Final status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `bf4271170b70731ec2227467e4f2dd45c889369a`

## Target Boundary

Follow up on accepted T6 production-read-only evidence:

- local/public `/health/ready` timed out;
- `fin-ops-worker@workbench.service` was `activating/auto-restart`;
- full module/global production closure remains blocked until readiness and worker evidence is understood.

## Safety Classification

This is a read-only evidence collection boundary.

Allowed:

- non-secret `ssh finops-prod-root` identity check;
- read-only `curl` checks against local health endpoints;
- read-only `systemctl show` and `systemctl is-active`;
- read-only active release path and file-existence checks;
- bounded `journalctl` excerpts redacted for obvious secret patterns.

Forbidden:

- source or print env files;
- print DSNs, tokens, cookies, private keys or secret env values;
- deploy, restart, stop, start or reload services;
- write PostgreSQL, Redis, RabbitMQ, readiness, queue, dirty scopes, outbox, worker state or production files;
- replay, consume, requeue or acknowledge worker events;
- run authenticated business/API/browser actions.

## Exact Commands

```bash
ssh finops-prod-root 'set -u; printf "identity user=%s uid=%s host=%s time=%s\n" "$(whoami)" "$(id -u)" "$(hostname)" "$(date -Is)"'

ssh finops-prod-root 'set -u; printf "current_release="; readlink -f /opt/fin-ops/current 2>/dev/null || true; test -x /usr/local/sbin/finops-deploy-control && /usr/local/sbin/finops-deploy-control status 2>/dev/null | sed -E "s#(postgres(ql)?://)[^ ]+#\1[redacted]#g; s#(password=)[^ ]+#\1[redacted]#g; s#(token=)[^ ]+#\1[redacted]#g; s#(cookie=)[^ ]+#\1[redacted]#g" | head -80'

ssh finops-prod-root 'set -u; for url in http://127.0.0.1:18001/health http://127.0.0.1:18001/health/ready; do echo "== $url =="; curl -sS -m 12 -w "\nHTTP:%{http_code} TIME:%{time_total}\n" "$url" | head -c 6000 || echo "curl_exit=$?"; echo; done'

ssh finops-prod-root 'set -u; for unit in fin-ops.service fin-ops-worker@workbench.service fin-ops-worker@workbench-matching.service fin-ops-worker@workbench-relation.service fin-ops-worker@bank-detail.service fin-ops-rabbitmq-dispatcher.service; do echo "== $unit =="; systemctl is-active "$unit" || true; systemctl show "$unit" -p ActiveState -p SubState -p Result -p NRestarts -p ExecMainStatus -p ExecMainCode -p MainPID -p RestartUSec -p FragmentPath --no-pager || true; done'

ssh finops-prod-root 'set -u; journalctl -u fin-ops-worker@workbench.service -n 80 --no-pager -o short-iso 2>/dev/null | sed -E "s#(postgres(ql)?://)[^ ]+#\1[redacted]#g; s#(password=)[^ ]+#\1[redacted]#g; s#(token=)[^ ]+#\1[redacted]#g; s#(cookie=)[^ ]+#\1[redacted]#g; s#(DATABASE_URL=)[^ ]+#\1[redacted]#g; s#(FIN_OPS_POSTGRES_DATABASE_URL=)[^ ]+#\1[redacted]#g" | tail -80'
```

## Expected Evidence

- Whether root SSH remains available without printing secrets.
- Whether `/health` and `/health/ready` still return or time out.
- Whether Workbench worker is still restarting.
- Whether selected adjacent worker units are active.
- Redacted recent Workbench worker logs sufficient to classify the failure as current, stale, or requiring a separate human/operational gate.

## Rollback / Cleanup Commands

No rollback or cleanup command is required because the planned commands are read-only.

If any command unexpectedly attempts mutation, stop immediately and do not continue with that command family.

## Stop Gates

Stop and classify as `needs-human-production-gate` if:

- evidence would require reading or printing secret env values;
- diagnosis requires service restart, deploy, queue mutation, readiness mutation or DB writes;
- log output appears to contain sensitive payloads that cannot be safely redacted;
- current worker/readiness behavior cannot be understood without an approved DB wrapper.

## Post-Checks

After commands:

- verify no production mutation was performed;
- summarize evidence without secrets;
- update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and the master prompt with the classification;
- run `bash scripts/verify.sh docs`, `git diff --check`, and `git diff --cached --check` before commit.

## Evidence Results

Executed at approximately `2026-06-25T01:21+08:00` through `ssh finops-prod-root`.

### Identity

```text
identity user=root uid=0 host=VM-0-6-opencloudos time=2026-06-25T01:21:00+08:00
```

Classification: `production-read-only`.

### Release / Runtime Status

- Active runtime is still `/opt/fin-ops/releases/main-bf4405fb-20260623194934/src`.
- Release metadata exposed by `/health` still reports `git_commit=bf4405fb9c6612ac91bce03d9216bf0d92118cb7`, `git_branch=main`, `consistent=true`.
- Production runtime guard remains `consistent=true`.
- The deploy-control status output printed env file paths and non-secret environment keys only; no secret values were printed or stored.

Classification: `production-read-only`.

### Health / Readiness

`http://127.0.0.1:18001/health`:

- Returned JSON with `status=ready`.
- Runtime release and production guard were consistent.
- Output was truncated by `head -c 6000`, causing curl write warning `(23) Failed writing body`; this is expected from truncation and not an application failure.

`http://127.0.0.1:18001/health/ready`:

```text
curl: (28) Operation timed out after 12003 milliseconds with 0 bytes received
HTTP:000 TIME:12.003072
```

Classification: `production-evidence-deferred`; readiness convergence remains unproven.

### Selected Unit State

All selected units were `active/running` when sampled, but restart counters were high:

| Unit | Active/SubState | NRestarts | Evidence meaning |
| --- | --- | ---: | --- |
| `fin-ops.service` | `active/running` | 0 | API process currently up. |
| `fin-ops-worker@workbench.service` | `active/running` | 846 | Restart loop recently occurred or is recurring. |
| `fin-ops-worker@workbench-matching.service` | `active/running` | 879 | Restart loop risk applies beyond one worker. |
| `fin-ops-worker@workbench-relation.service` | `active/running` | 889 | Restart loop risk applies beyond one worker. |
| `fin-ops-worker@bank-detail.service` | `active/running` | 895 | Restart loop risk applies beyond Workbench. |
| `fin-ops-rabbitmq-dispatcher.service` | `active/running` | 927 | Dispatcher restart loop risk also present. |

Classification: `production-read-only` evidence of current active state plus unresolved runtime instability.

### Sanitized Workbench Worker Logs

Recent logs show repeated PostgreSQL connection failures and worker restarts. The relevant non-secret errors were:

```text
psycopg_pool.PoolTimeout: couldn't get a connection after 30.00 sec
connection to server at "127.0.0.1", port 5432 failed:
FATAL: could not open shared memory segment "/PostgreSQL.2926794240": No such file or directory
fin-ops-worker@workbench.service: Main process exited, code=exited, status=1/FAILURE
fin-ops-worker@workbench.service: Scheduled restart job, restart counter is at 846
```

No DSN, token, cookie, password or secret env value was printed by the collected excerpt.

Classification: `production-read-only` evidence that the readiness/worker issue is tied to PostgreSQL connection/shared-memory failure, but not enough to close the underlying production issue.

## Result Classification

`production-evidence-deferred`.

Reason:

- `/health/ready` still times out.
- Worker/dispatcher restart counters are high.
- Workbench worker logs show PostgreSQL connection pool timeout and local PostgreSQL shared memory errors.
- Fixing or deeper diagnosing PostgreSQL runtime may require a separate controlled boundary. This slice intentionally did not inspect secret-bearing DB env, connect to the database, restart services, mutate worker state, mutate readiness or write production data.

## Next Safe Boundary

```text
production:postgres-shared-memory-read-only-diagnosis
```

Purpose:

- Prepare a new T0-controlled read-only runbook focused on PostgreSQL runtime health and OS-level shared memory evidence.
- Use only non-secret commands such as `systemctl show` for PostgreSQL units, process/resource status, `df`, `free`, `ipcs`, `sysctl` read-only values and sanitized logs.
- Do not restart PostgreSQL or app services.
- Do not connect to PostgreSQL using secret-bearing DSNs unless a secret-free wrapper already exists and prints only aggregate status.

## Verification Plan

Before committing this slice:

```bash
bash scripts/verify.sh docs
git diff --check
git diff --cached --check
```
