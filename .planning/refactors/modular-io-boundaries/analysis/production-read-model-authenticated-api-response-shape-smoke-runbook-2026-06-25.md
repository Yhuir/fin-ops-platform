# Production Read Model Authenticated API Response-Shape Smoke Runbook

**Boundary:** `production:read-model-authenticated-api-response-shape-smoke-runbook`
**Status:** `production-evidence-deferred`
**Date:** 2026-06-25
**Branch:** `dev`
**Controller:** T0
**Closure:** module/global closure not claimed

## Objective

Collect bounded production read-only API response-shape smoke evidence for read-model-heavy surfaces using the existing `fin_ops_platform.tools.http_slo_probe` metadata-only reporter.

This boundary does not execute browser smoke. Browser smoke remains deferred until this API runbook proves a non-secret authentication path and identifies safe page checks.

## Safety Properties

- Uses GET-only HTTP probes.
- Uses `http_slo_probe`, which reports probe names, URLs, status codes, response byte counts, duration percentiles and optional `read_model_status` / `cache_status` metadata.
- Does not print response bodies.
- Does not print or store auth header values, tokens or cookies.
- Does not deploy, restart, requeue, repair, replay workers, mutate DB rows, mutate queue/readiness state or run `--apply`.
- Post-checks verify `/health/ready`, dirty scopes, readiness and outbox status remain clean after the smoke.

## Preconditions

- `dev` and `origin/dev` are aligned.
- Production root SSH alias `finops-prod-root` is available.
- Active release source path is discoverable without reading secrets.
- Auth must be provided by pre-existing production environment variables consumed by `http_slo_probe`: `FIN_OPS_HTTP_SLO_BEARER_TOKEN`, `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` or `FIN_OPS_HTTP_SLO_COOKIE`.
- If those variables are absent, stop and classify the boundary as `production-evidence-deferred`; do not ask the user for tokens or cookies.

## Commands

All commands must run with `set +x` semantics and must not echo secret values.

### 1. Discover Active Release And Health

```bash
ssh finops-prod-root 'set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; echo "release_src=$release_src"; echo "git_commit=$(cat "$release_src/.git_commit" 2>/dev/null || git -C "$release_src" rev-parse HEAD 2>/dev/null || true)"; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
```

### 2. Check Auth Configuration Without Printing Values

```bash
ssh finops-prod-root 'set +x; set -eu; set -a; [ -f /etc/fin-ops/fin-ops.common.env ] && . /etc/fin-ops/fin-ops.common.env; [ -f /etc/fin-ops/fin-ops.secrets.env ] && . /etc/fin-ops/fin-ops.secrets.env; set +a; configured=0; [ -n "${FIN_OPS_HTTP_SLO_BEARER_TOKEN:-}" ] && configured=1; [ -n "${FIN_OPS_HTTP_SLO_ADMIN_TOKEN:-}" ] && configured=1; [ -n "${FIN_OPS_HTTP_SLO_COOKIE:-}" ] && configured=1; if [ "$configured" -eq 1 ]; then echo "http_slo_auth_configured=yes"; else echo "http_slo_auth_configured=no"; fi'
```

Stop here if the output is `http_slo_auth_configured=no`.

### 3. Run Metadata-Only API Smoke

The smoke excludes page probes and uses one measured iteration with one warmup to bound runtime and payload volume. It writes no file on production and prints only the JSON report.

```bash
ssh finops-prod-root 'set +x; set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; set -a; [ -f /etc/fin-ops/fin-ops.common.env ] && . /etc/fin-ops/fin-ops.common.env; [ -f /etc/fin-ops/fin-ops.secrets.env ] && . /etc/fin-ops/fin-ops.secrets.env; set +a; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.http_slo_probe --base-url http://127.0.0.1:18001 --no-default-page-probe --iterations 1 --warmup 1 --timeout-seconds 15 --target-ms 5000 --json'
```

### 4. Post-Checks

```bash
ssh finops-prod-root 'set -eu; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
ssh finops-prod-root 'set +x; set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; set -a; [ -f /etc/fin-ops/fin-ops.common.env ] && . /etc/fin-ops/fin-ops.common.env; [ -f /etc/fin-ops/fin-ops.secrets.env ] && . /etc/fin-ops/fin-ops.secrets.env; set +a; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python - <<'"'"'PY'"'"'
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
conn = PostgresConnection(PostgresSettings.from_env())
with conn.connection() as connection:
    with connection.cursor() as cur:
        cur.execute("select status, count(*) from job.read_model_dirty_scopes group by status order by status")
        print("dirty_scopes", cur.fetchall())
        cur.execute("select status, count(*) from read_model.app_status_readiness group by status order by status")
        print("readiness", cur.fetchall())
        cur.execute("select status, count(*) from job.outbox_events where event_type like '"'"'%.read_model.refresh'"'"' group by status order by status")
        print("read_model_outbox", cur.fetchall())
PY'
```

## Execution Evidence

### Release / Health Precheck

The initial runbook command used `python`, which is not installed on the production shell. It failed before completing the health JSON parse and did not mutate production state:

```text
release_src=/opt/fin-ops/releases/dev-workbench-matching-port-20260625020818/src
bash: line 1: python: command not found
curl: (23) Failed writing body (0 != 10095)
```

The corrected command used `/opt/fin-ops/venv/bin/python` and returned:

```text
release_src=/opt/fin-ops/releases/dev-workbench-matching-port-20260625020818/src
git_commit=unknown
{'status': 'ready'}
```

### Auth Configuration Check

Auth value presence was checked without printing values:

```text
http_slo_auth_configured=no
```

Because no `FIN_OPS_HTTP_SLO_BEARER_TOKEN`, `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` or `FIN_OPS_HTTP_SLO_COOKIE` was configured in the production env files, the authenticated API smoke was not executed.

### Post-Checks

Health remained ready:

```text
{'status': 'ready'}
```

The first DB aggregate attempt used an incorrect table name and failed read-only after printing dirty scope status. The corrected aggregate returned:

```text
dirty_scopes [{'status': 'done', 'count': 187007}]
readiness [{'status': 'fresh', 'count': 498}]
read_model_outbox [{'status': 'done', 'count': 202898}]
```

## Result

`production-evidence-deferred`.

The authenticated API smoke is blocked by missing non-secret HTTP SLO auth configuration. T0 did not ask for tokens/cookies and did not print or store any secret values. No API smoke requests were sent beyond `/health/ready`; no production mutation, deploy, restart, requeue, repair, replay, queue/readiness mutation or direct SQL write occurred.

Next safe boundary:

`production:read-model-public-page-shell-smoke-runbook`

This can exercise public page shell availability without auth secrets, but it will not satisfy authenticated API response-shape closure.

## Stop Gates

- Auth configuration absent.
- Any command would require printing a token, cookie, password, DSN or secret env value.
- `http_slo_probe` attempts to print response bodies or raw business rows.
- `/health/ready` is not ready before smoke.
- Smoke requires POST/PUT/PATCH/DELETE, queue mutation, worker replay, repair, restart or deploy.
- Post-checks show new non-done dirty scopes, non-fresh readiness or non-done read-model outbox rows attributable to the smoke.

## Expected Evidence

- Active release path and commit identity.
- `/health/ready` ready before and after.
- Auth configuration classified as configured or absent without value disclosure.
- If auth configured: metadata-only `http_slo_probe` report with probe count, failed probe count, status code counts, durations and read-model/cache statuses.
- Post-check DB aggregates showing whether dirty scopes/readiness/outbox stayed clean.

## Rollback / Cleanup

No rollback is expected because this is read-only. If a stop gate fires, stop and record the evidence; do not attempt repair or cleanup in this boundary.
