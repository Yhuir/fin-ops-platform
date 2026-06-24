# Production Write-Flow Scenario Discovery Read-Only Runbook - 2026-06-25

**Boundary:** `production:write-flow-scenario-discovery-read-only-runbook`
**Status:** `pending-execution`
**Module closure:** `not-module-closed`
**Production mutation:** none; read-only PostgreSQL scenario discovery only
**Active release expected:** `dev-turnover-source-version-persistence-20260625`

## Goal

Collect bounded read-only production evidence for write-flow scenario availability without executing any write operation, printing business identifiers or writing scenario JSON files.

This boundary classifies whether existing production data contains candidate classes for a later, separately approved controlled write-flow runbook. It is not approval to run `write_operation_e2e_smoke --apply`.

## Inputs Reviewed

- `analysis/planning-controlled-write-flow-evidence-scenario-selection-2026-06-25.md`
- `analysis/production-admin-scope-auth-seam-read-only-classification-2026-06-25.md`
- `backend/src/fin_ops_platform/tools/write_operation_scenario_discovery.py`
- `backend/src/fin_ops_platform/tools/write_operation_e2e_smoke.py`
- `docs/operations/runtime-sync-stage7-2026-06-13.md`
- `docs/operations/runtime-sync-stage8-2026-06-13.md`
- `docs/operations/runtime-sync-stage9-2026-06-13.md`

## Safety Scope

Allowed:

- read-only production release/health/aggregate checks;
- read-only PostgreSQL candidate discovery through the existing `discover_write_operation_scenarios(...)` helper;
- sanitized output containing only status, candidate counts, operation classes, scenario count, and safety booleans/notes.

Forbidden:

- printing/storing secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows, scenario identifiers or business identifiers;
- writing `--output` or `--scenario-output` files;
- running `write_operation_e2e_smoke --apply`;
- executing write endpoints such as confirm, withdraw, save, import, reset or export/download flows;
- browser/admin probes;
- deploy, restart, requeue, repair, replay, direct SQL mutation, readiness mutation, manual mark-done or worker consume/replay;
- claiming module/global closure from read-only discovery alone.

## Commands

All commands must use `set +x`.

### 1. Precheck: release, health and aggregates

```bash
ssh finops-prod-root 'set +x; set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; echo "release_src=$release_src"; echo "release_name=$(basename "$(dirname "$release_src")")"; echo "git_commit=$(cat "$release_src/RELEASE.json" 2>/dev/null | /opt/fin-ops/venv/bin/python -c "import json,sys; print(json.load(sys.stdin).get(\"git_commit\", \"\"))" 2>/dev/null || git -C "$release_src" rev-parse HEAD 2>/dev/null || true)"; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
ssh finops-prod-root 'set +x; set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; set -a; [ -f /etc/fin-ops/fin-ops.common.env ] && . /etc/fin-ops/fin-ops.common.env; [ -f /etc/fin-ops/fin-ops.secrets.env ] && . /etc/fin-ops/fin-ops.secrets.env; set +a; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python - <<'"'"'PY'"'"'
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings

conn = PostgresConnection(PostgresSettings.from_env())
with conn.connection() as connection:
    with connection.cursor() as cur:
        cur.execute("select status, count(*) as count from job.read_model_dirty_scopes group by status order by status")
        print("dirty_scopes", cur.fetchall())
        cur.execute("select status, count(*) as count from read_model.app_status_readiness group by status order by status")
        print("readiness", cur.fetchall())
        cur.execute("select status, count(*) as count from job.outbox_events where event_type like %s group by status order by status", ("%.read_model.refresh",))
        print("read_model_outbox", cur.fetchall())
        cur.execute("select count(*) as count from job.outbox_events where status = %s and event_type like %s", ("dead_lettered", "%.read_model.refresh"))
        print("read_model_dead_letters", cur.fetchone()["count"])
PY'
```

Stop if `/health/ready` is not ready, any non-done dirty/outbox row appears, any non-fresh readiness row appears or any read-model dead letter exists.

### 2. Read-only sanitized write-flow scenario discovery

This command calls the existing discovery helper in process, strips all candidate and scenario details, and prints only aggregate classes/counts/safety flags. It must not pass `--output`, `--scenario-output` or any apply flag.

```bash
ssh finops-prod-root 'set +x; set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; set -a; [ -f /etc/fin-ops/fin-ops.common.env ] && . /etc/fin-ops/fin-ops.common.env; [ -f /etc/fin-ops/fin-ops.secrets.env ] && . /etc/fin-ops/fin-ops.secrets.env; set +a; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python - <<'"'"'PY'"'"'
import json

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.tools.write_operation_scenario_discovery import discover_write_operation_scenarios

conn = PostgresConnection(PostgresSettings.from_env())
raw = discover_write_operation_scenarios(conn, tenant_id="default", limit=10)
candidate_counts = dict(raw.get("candidate_counts") or {})
scenario_count = len((raw.get("scenario_json") or {}).get("scenarios") or [])
operation_classes = sorted(candidate_counts.keys())
available_operation_classes = sorted(key for key, value in candidate_counts.items() if int(value or 0) > 0)
safety = dict(raw.get("safety") or {})
sanitized = {
    "version": 1,
    "mode": "read_only_sanitized_write_operation_discovery",
    "status": raw.get("status"),
    "candidate_counts": candidate_counts,
    "operation_classes": operation_classes,
    "available_operation_classes": available_operation_classes,
    "scenario_count": scenario_count,
    "safety": {
        "mutates_data": bool(safety.get("mutates_data")),
        "requires_real_auth_to_apply": bool(safety.get("requires_real_auth_to_apply")),
        "requires_manual_approval_before_apply": bool(safety.get("requires_manual_approval_before_apply")),
        "notes": list(safety.get("notes") or []),
    },
    "identifiers_printed": False,
    "scenario_file_written": False,
    "write_apply_executed": False,
}
print(json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True))
PY'
```

Stop after this command whether candidates exist or not. Candidate presence does not authorize a write operation.

### 3. Postcheck: health and aggregates

Repeat command 1 after discovery. Counts should remain unchanged.

## Expected Result Classes

- `production-controlled`: read-only discovery succeeds, prints only sanitized aggregate evidence, and pre/post aggregates are unchanged.
- `production-evidence-deferred`: discovery tooling/configuration is unavailable, discovery fails before producing sanitized evidence, or pre/post checks are not clean.
- `hard stop`: any path would require printing identifiers or secrets, writing a scenario file, running `--apply`, or mutating production state.

## Execution Evidence

Pending. The runbook must be committed and pushed before production execution.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service/repository code changed.
3. API contract tests: not applicable; no HTTP/API contract is called in this boundary.
4. Read model/cache/background job tests: applicable as pre/post aggregate checks.
5. Frontend component and interaction tests: not applicable; browser probes are forbidden.
6. End-to-end business-flow integration tests: partially applicable as read-only scenario discovery only; mutating E2E remains blocked pending explicit approval, reviewed reversible object, rollback/idempotency/audit acceptance and suitable auth.
7. Existing feature regression tests: applicable through docs verification and diff checks.
