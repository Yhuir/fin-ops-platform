# Production Read Model Controlled Production API Browser Runbook - 2026-06-25

**Boundary:** `production:read-model-controlled-production-api-browser-runbook`
**Status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`
**Production mutation:** bounded GET-triggered read model refresh enqueues occurred and converged
**Worker threads created:** none
**Next boundary:** `production:pending-invoice-no-oa-api-freshness-mismatch-read-only-diagnosis`

## Goal

Use the sanctioned T0 `ssh finops-prod-root` production evidence gate to collect the strongest safe API/browser/high-row evidence available without printing or storing secrets, response bodies, payload rows or business-sensitive values.

This boundary must not claim module/global closure. It can close as `production-controlled` only for evidence it actually proves. It must keep unproven browser data hydration, admin-only and write-after-read gaps explicit.

## Inputs Reviewed

- `analysis/planning-post-default-api-probe-harness-next-boundary-selection-2026-06-25.md`
- `analysis/contract-read-model-default-api-probe-harness-broadening-2026-06-25.md`
- `analysis/production-read-model-auth-preflight-and-api-smoke-runbook-2026-06-25.md`
- `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
- `backend/src/fin_ops_platform/tools/http_slo_probe.py`
- `backend/src/fin_ops_platform/app/auth.py`
- `backend/src/fin_ops_platform/services/target_oa_applicant_token_provider.py`
- `backend/src/fin_ops_platform/services/oa_applicant_credentials.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/oa_applicant_credentials.py`
- `web/e2e/production-route-shell.spec.ts`
- `web/e2e/production-admin-app-health.spec.ts`
- `docs/operations/monitoring.md`
- `docs/dev/testing-closure-state.md`

## Safety Classification

Allowed:

- `ssh finops-prod-root` with bounded shell commands.
- `/health/ready` readiness summary and active release discovery.
- Sourcing existing production env files with `set +x`, without printing env values.
- Read-only PostgreSQL aggregate queries through deployed runtime configuration.
- Reading `app.oa_applicant_credentials` summaries and decrypting one target applicant credential inside a remote Python process only, without printing username, password, token or credential values.
- OA login inside the same remote Python process to obtain a bearer token in memory.
- API-only `http_slo_probe.collect_http_slo(...)` with user-scope probes, excluding the admin-only `operations_app_health_dashboard` probe, printing only the tool's sanitized JSON report.
- Public page-shell `http_slo_probe` metadata if needed, without response body storage.

Forbidden:

- Printing env files, DSNs, passwords, OA usernames, OA passwords, bearer tokens, cookies, private keys, response bodies, payload rows, invoice numbers, project names, counterparties or other sensitive business values.
- Passing tokens on the shell command line or writing tokens to files.
- Deploy, restart, reload, requeue, repair, replay workers, queue mutation, readiness mutation, direct SQL mutation, production business writes or browser actions that can mutate state.
- Running production Playwright locally with a token copied out of production.
- Treating target-applicant user credentials as admin credentials.

## Runbook Commands

### 1. Precheck: release and `/health/ready`

```bash
ssh finops-prod-root 'set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; echo "release_src=$release_src"; echo "git_commit=$(cat "$release_src/.git_commit" 2>/dev/null || git -C "$release_src" rev-parse HEAD 2>/dev/null || true)"; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
```

Stop if `/health/ready` is unavailable or not ready.

### 2. Precheck: read-only runtime aggregate

```bash
ssh finops-prod-root 'set +x; set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; set -a; [ -f /etc/fin-ops/fin-ops.common.env ] && . /etc/fin-ops/fin-ops.common.env; [ -f /etc/fin-ops/fin-ops.secrets.env ] && . /etc/fin-ops/fin-ops.secrets.env; set +a; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python - <<'"'"'PY'"'"'
import json
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings

conn = PostgresConnection(PostgresSettings.from_env())
queries = {
    "dirty_scopes": "select status, count(*) from job.read_model_dirty_scopes group by status order by status",
    "readiness": "select status, count(*) from read_model.app_status_readiness group by status order by status",
    "read_model_outbox": "select status, count(*) from job.outbox_events where event_type like '%%.read_model.refresh' group by status order by status",
    "dead_letters": "select event_type, count(*) from job.outbox_events where status = 'dead_lettered' and event_type like '%%.read_model.refresh' group by event_type order by event_type",
}
for name, sql in queries.items():
    print(name, conn.fetch_all(sql, ()))
PY'
```

Stop if any active dirty/non-fresh/dead-letter blocker appears.

### 3. User-scope authenticated API metadata probe via target OA applicant credentials

This command uses a remote Python process to:

1. load production env files without printing env values;
2. count configured target OA applicant credentials;
3. login one target applicant in memory;
4. call `/api/session/me` to verify the session class without printing token or username;
5. run `http_slo_probe.collect_http_slo(...)` against user-scope `DEFAULT_API_PROBES`, excluding admin-only probes;
6. print only sanitized status, latency, response-size and read-model/cache metadata.

```bash
ssh finops-prod-root 'set +x; set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; set -a; [ -f /etc/fin-ops/fin-ops.common.env ] && . /etc/fin-ops/fin-ops.common.env; [ -f /etc/fin-ops/fin-ops.secrets.env ] && . /etc/fin-ops/fin-ops.secrets.env; set +a; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python - <<'"'"'PY'"'"'
import json
from urllib.request import Request, urlopen

from fin_ops_platform.services.oa_applicant_credentials import OaApplicantCredentialService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.oa_applicant_credentials import PostgresOaApplicantCredentialRepository
from fin_ops_platform.services.target_oa_applicant_token_provider import OaLoginClient
from fin_ops_platform.tools import http_slo_probe

conn = PostgresConnection(PostgresSettings.from_env())
credential_service = OaApplicantCredentialService(repository=PostgresOaApplicantCredentialRepository(conn))
summaries = [item for item in credential_service._repository.list_credentials() if item.has_credential and item.enabled]
result = {
    "version": 1,
    "mode": "target_oa_applicant_user_scope_http_slo",
    "configured_target_credential_count": len(summaries),
}
if not summaries:
    result.update({"status": "credential_missing", "error": "no_configured_target_oa_applicant_credentials"})
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(2)

login_client = OaLoginClient()
token = None
login_errors = []
for summary in summaries:
    try:
        credential = credential_service.resolve_login_credential(summary.target_applicant_code)
        if credential is None:
            login_errors.append("credential_unavailable")
            continue
        token = login_client.login(credential.oa_username, credential.password)
        break
    except Exception as exc:
        login_errors.append(str(getattr(exc, "code", "") or exc.__class__.__name__))

if not token:
    result.update({"status": "login_failed", "login_error_count": len(login_errors), "login_error_codes": sorted(set(login_errors))[:5]})
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(2)

headers = http_slo_probe._auth_headers(bearer_token=token)
session_request = Request(
    "http://127.0.0.1:18001/api/session/me",
    method="GET",
    headers=headers,
)
with urlopen(session_request, timeout=15) as response:
    session_payload = json.loads(response.read().decode("utf-8"))

user_probes = [probe for probe in http_slo_probe.DEFAULT_API_PROBES if probe.auth_scope != "admin"]
report = http_slo_probe.collect_http_slo(
    base_url="http://127.0.0.1:18001",
    probes=user_probes,
    headers=headers,
    iterations=1,
    warmup=1,
    timeout_seconds=20,
    require_auth=True,
    include_samples=False,
)
result.update({
    "status": report.get("status"),
    "session": {
        "http_status": 200,
        "allowed": bool(session_payload.get("allowed")),
        "can_access_app": bool(session_payload.get("can_access_app")),
        "can_mutate_data": bool(session_payload.get("can_mutate_data")),
        "can_admin_access": bool(session_payload.get("can_admin_access")),
        "access_tier": session_payload.get("access_tier"),
    },
    "api_probe": report,
    "admin_probe_excluded": True,
})
print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
raise SystemExit(0 if report.get("status") == "pass" else 1)
PY'
```

Do not run this command if executing it would require printing credentials. Stop if target credential login is unavailable. If the command exits non-zero after printing a sanitized report, classify from the report rather than retrying blindly.

### 4. Postcheck: health and aggregate

Repeat commands 1 and 2 after the API metadata probe.

## Browser Evidence Decision

The existing production route-shell Playwright spec requires `FIN_OPS_E2E_OA_TOKEN` in the environment. The target-applicant token acquired in command 3 must not be printed, copied to the local shell or written to a file. This boundary therefore does not run local production Playwright with that token.

If the remote production host has an already-installed browser harness that can receive the token in process memory without printing or storing it, a later boundary can use it. This runbook does not assume such a harness exists.

## Expected Result Classes

- `production-controlled`: user-scope authenticated API metadata probe runs successfully, pre/post health aggregates remain clean, and browser/admin/write gaps are explicitly deferred.
- `production-evidence-deferred`: target applicant credential login is unavailable, API probe fails with a real endpoint/status/freshness problem, or no non-secret browser data hydration seam exists.
- `hard stop`: any command would print secrets/payload rows or require broad mutation.

## Execution Results

### Precheck

Release and `/health/ready`:

```text
release_src=/opt/fin-ops/releases/dev-workbench-matching-port-20260625020818/src
git_commit=
{'status': 'ready'}
```

The first aggregate command had a runbook query quoting bug on `like '%%.read_model.refresh'`; it printed `dirty_scopes` and `readiness` before failing on the outbox query. The query was corrected to use parameterized SQL and rerun successfully.

Corrected precheck aggregate:

```text
dirty_scopes [{'status': 'done', 'count': 187007}]
readiness [{'status': 'fresh', 'count': 498}]
read_model_outbox [{'status': 'done', 'count': 202898}]
dead_letters []
```

### User-Scope Authenticated API Metadata Probe

The target OA applicant credential seam was available:

- configured target credential count: `2`;
- `/api/session/me` returned `200`;
- session allowed: `true`;
- `can_access_app=true`;
- `can_mutate_data=true`;
- `can_admin_access=false`;
- `access_tier=full_access`;
- admin-only probe excluded: `true`.

The API probe used one warmup and one measured iteration over the 37 user-scope default API probes. It did not print token/cookie/password/env values or response bodies.

Initial result:

```text
status=fail
probe_count=37
sample_count=37
failed_probe_count=7
max_p95_ms=1119.245
```

Initial failed probes:

| Probe | Status counts | Read model status | Refresh enqueued | p95 ms |
| --- | --- | --- | ---: | ---: |
| `pending_invoices_rows` | `200:1` | `refreshing:1` | 0 | 1119.245 |
| `pending_invoices_filter_options` | `202:1` | `refreshing:1` | 0 | 66.582 |
| `tax_offset_summary` | `202:1` | `refreshing:1` | 1 | 49.163 |
| `tax_offset_rows` | `200:1` | `refreshing:1` | 1 | 48.506 |
| `cost_statistics_explorer_all` | `200:1` | `refreshing:1` | 1 | 92.192 |
| `cost_statistics_summary_all` | `200:1` | `refreshing:1` | 1 | 85.435 |
| `no_oa_bank_batches` | `200:1` | `stale:1` | 1 | 172.346 |

All other user-scope API probes passed, including Workbench summary/groups/settings, bank detail accounts/transactions/rules, input usage, OA pending payment, output collections, batch accounting, turnover, ETC/import facts and search.

Although the runbook planned no production mutation, existing GET fresh gates enqueued bounded read-model refreshes for stale/non-fresh scopes. This was not a business write and no direct SQL mutation/requeue/repair/replay was performed, but it is still production queue mutation and is therefore recorded explicitly.

### First Postcheck

`/health/ready` stayed ready. Aggregates after the initial probe:

```text
dirty_scopes [{'status': 'done', 'count': 187029}]
readiness [{'status': 'fresh', 'count': 498}]
read_model_outbox [{'status': 'done', 'count': 202922}]
dead_letters []
```

Recent five-minute refresh activity after the initial probe:

```text
recent_read_model_outbox [
  {'event_type': 'cost_statistics.read_model.refresh', 'status': 'done', 'count': 2},
  {'event_type': 'no_oa_bank_batch.read_model.refresh', 'status': 'done', 'count': 1},
  {'event_type': 'pending_invoice.read_model.refresh', 'status': 'done', 'count': 19},
  {'event_type': 'tax_offset.read_model.refresh', 'status': 'done', 'count': 1},
  {'event_type': 'turnover_ledger.read_model.refresh', 'status': 'done', 'count': 1}
]
recent_dirty [
  {'scope_type': 'cost_statistics', 'status': 'done', 'count': 2},
  {'scope_type': 'no_oa_bank_batch', 'status': 'done', 'count': 1},
  {'scope_type': 'pending_invoice', 'status': 'done', 'count': 17},
  {'scope_type': 'tax_offset', 'status': 'done', 'count': 1},
  {'scope_type': 'turnover_ledger', 'status': 'done', 'count': 1}
]
```

### Focused Retry After Refresh Convergence

After the first postcheck proved dirty/outbox/readiness converged, T0 ran one focused retry over the seven failed user-scope probes.

Focused result:

```text
status=fail
probe_count=7
sample_count=7
failed_probe_count=3
max_p95_ms=934.207
```

Focused retry outcomes:

| Probe | Result | Evidence |
| --- | --- | --- |
| `tax_offset_summary` | pass | `200`, `fresh`, no refresh enqueue |
| `tax_offset_rows` | pass | `200`, `fresh`, no refresh enqueue |
| `cost_statistics_explorer_all` | pass | `200`, `fresh`, no refresh enqueue |
| `cost_statistics_summary_all` | pass | `200`, `fresh`, no refresh enqueue |
| `pending_invoices_rows` | fail | `200`, `refreshing`, no refresh enqueue, p95 `934.207ms` |
| `pending_invoices_filter_options` | fail | `202`, `refreshing`, no refresh enqueue |
| `no_oa_bank_batches` | fail | `200`, `stale`, refresh enqueued once |

### Final Postcheck

Final `/health/ready` stayed ready. Aggregates after the focused retry:

```text
dirty_scopes [{'status': 'done', 'count': 187047}]
readiness [{'status': 'fresh', 'count': 498}]
read_model_outbox [{'status': 'done', 'count': 202942}]
dead_letters []
```

Recent five-minute refresh activity at final postcheck:

```text
recent_read_model_outbox [
  {'event_type': 'cost_statistics.read_model.refresh', 'status': 'done', 'count': 2},
  {'event_type': 'no_oa_bank_batch.read_model.refresh', 'status': 'done', 'count': 2},
  {'event_type': 'pending_invoice.read_model.refresh', 'status': 'done', 'count': 38},
  {'event_type': 'tax_offset.read_model.refresh', 'status': 'done', 'count': 1},
  {'event_type': 'turnover_ledger.read_model.refresh', 'status': 'done', 'count': 1}
]
recent_dirty [
  {'scope_type': 'cost_statistics', 'status': 'done', 'count': 2},
  {'scope_type': 'no_oa_bank_batch', 'status': 'done', 'count': 2},
  {'scope_type': 'pending_invoice', 'status': 'done', 'count': 34},
  {'scope_type': 'tax_offset', 'status': 'done', 'count': 1},
  {'scope_type': 'turnover_ledger', 'status': 'done', 'count': 1}
]
```

## Result

Decision: `production-evidence-deferred`.

This boundary proved:

- the T0 root SSH controlled production evidence path works;
- target OA applicant credentials can provide a real user-scope authenticated session without printing/storing tokens;
- the session is full-access user scope, not admin scope;
- 30/37 user-scope API probes passed on the first measured run;
- tax offset and cost statistics stale responses recovered to fresh after bounded API-triggered read-model refresh convergence;
- pre/post production health remained ready;
- all postcheck dirty scopes, read-model outbox rows and readiness rows ended clean, and no read-model dead letters appeared.

This boundary did not prove:

- full user-scope authenticated API closure, because pending invoice rows/filter-options and no-OA bank batches remained non-fresh/stale after focused retry;
- admin-only AppHealth dashboard closure, because the target session has `can_admin_access=false`;
- production browser data hydration, because the only available production Playwright route-shell spec requires a token environment variable and this boundary did not copy the remote token out of production;
- high-row browser behavior;
- write-after-read convergence or business write E2E closure;
- module/global closure.

## Next Boundary Selection

Select `production:pending-invoice-no-oa-api-freshness-mismatch-read-only-diagnosis`.

The next boundary should use only read-only production evidence to diagnose why:

- `pending_invoices_rows` returns `read_model_status=refreshing` with HTTP `200` and no refresh enqueue;
- `pending_invoices_filter_options` returns HTTP `202` / `refreshing` and no refresh enqueue;
- `no_oa_bank_batches` returns `read_model_status=stale` and continues to enqueue refresh even though final dirty/outbox/readiness aggregates are clean.

It should inspect sanitized freshness/status/reason fields and relevant readiness/dirty/outbox/source-version rows without selecting business payload rows, printing secrets or mutating state.

## Docs Impact

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No long-term docs update yet because this boundary collected evidence and found unresolved production API freshness mismatches. Long-term/module docs should be updated only after the next diagnosis identifies a durable contract or implementation fact.

## Seven Test Categories

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business rule changed. |
| 2. Service-layer tests | Not applicable | No service/repository code changed in this boundary. |
| 3. API contract tests | Applicable as production evidence | User-scope authenticated API metadata probe was executed; result is partial/deferred because 3 focused probes remain non-fresh/stale. |
| 4. Read model/cache/background job tests | Applicable as production evidence | Pre/post dirty/readiness/outbox/dead-letter aggregates were collected; API-triggered refreshes converged to done/fresh, but API freshness mismatch remains. |
| 5. Frontend component and interaction tests | Deferred | No production Browser data hydration was run because no non-secret browser token seam was available without copying token out of production. |
| 6. End-to-end business-flow integration tests | Deferred | No production business write or write-after-read scenario was run. |
| 7. Existing feature regression tests | Applicable | Production health stayed ready and postchecks ended clean; docs/diff verification still required before commit. |

## Verification

Executed before commit:

- `bash scripts/verify.sh docs` passed.
- `git diff --check` passed.
- Changed-file sensitive-term scan found only policy text and variable names such as `FIN_OPS_E2E_OA_TOKEN`; no secret values were printed or committed.
- `git diff --cached --check` must pass after staging.
