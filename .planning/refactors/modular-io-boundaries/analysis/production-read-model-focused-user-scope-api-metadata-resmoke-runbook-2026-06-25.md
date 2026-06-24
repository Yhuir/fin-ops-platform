# Production Read Model Focused User-Scope API Metadata Resmoke Runbook - 2026-06-25

**Boundary:** `production:read-model-focused-user-scope-api-metadata-resmoke-runbook`
**Status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`
**Production mutation:** GET-triggered read model refresh enqueue may occur and must be recorded
**Worker threads created:** none
**Previous boundary:** `planning:post-no-oa-category-source-version-diagnosis-next-boundary-selection`

## Goal

Re-run the user-scope authenticated production API metadata smoke after Row277 and Row278 addressed the only Row273 remaining failures:

- `pending_invoices_rows`
- `pending_invoices_filter_options`
- `no_oa_bank_batches`

If these three focused probes pass, optionally run all non-admin user-scope default API probes once to update the broader production API evidence. This boundary must not claim module/global closure.

## Safety Classification

Allowed:

- `ssh finops-prod-root` with bounded commands.
- `/health/ready` readiness summary and active release discovery.
- Sourcing existing production env files with `set +x`, without printing env values.
- Reading target OA applicant credential summaries and decrypting one target applicant credential only inside a remote Python process.
- OA login inside the same remote Python process to hold the bearer token in memory only.
- API-only `http_slo_probe.collect_http_slo(...)` with user-scope probes and `include_samples=False`.
- Sanitized PostgreSQL aggregate summaries for dirty scopes, readiness, outbox and dead letters.

Forbidden:

- Printing or storing env files, DSNs, OA usernames, passwords, bearer tokens, cookies, private keys, response bodies, payload rows, invoice numbers, project names, counterparties, account names or other business identifiers.
- Passing tokens on the shell command line or writing tokens to files.
- Browser/admin/write probes.
- Deploy, restart, repair, replay workers, manual requeue, direct SQL mutation, direct readiness mutation, direct dirty-scope mutation or business writes.

Important bounded side effect:

- GET fresh gates may enqueue normal read-model refreshes if an endpoint is stale. This is not manually initiated, is limited to the selected GET endpoints, and must be captured through pre/post dirty/outbox/readiness evidence.

## Stop Gates

- Stop before executing if `/health/ready` is unavailable or not ready.
- Stop before executing if precheck shows active dirty/outbox/dead-letter blockers unrelated to the selected probes.
- Stop before executing if the only available auth path would print, store or copy tokens/cookies/passwords/env secret values.
- Stop after a focused probe failure; record sanitized failure evidence and do not retry blindly or run the full probe set.
- Stop if postcheck shows health not ready or unresolved non-done read-model outbox/dirty/dead-letter rows.

## Step 1 - Read-Only Production Precheck

Command:

```bash
ssh finops-prod-root 'set -eu
release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"
if [ ! -d "$release_src/backend/src" ]; then
  release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"
fi
release_name="$(basename "$(dirname "$release_src")")"
git_commit="$(cat "$release_src/.git_commit" 2>/dev/null || true)"
echo "precheck_release_name=$release_name"
echo "precheck_git_commit=$git_commit"
curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready \
  | /opt/fin-ops/venv/bin/python -c '"'"'import json,sys; p=json.load(sys.stdin); print({"status":p.get("status"),"release":p.get("release")})'"'"'
set -a
source /etc/fin-ops/fin-ops.common.env
source /etc/fin-ops/fin-ops.secrets.env
set +a
cd "$release_src"
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python - <<'"'"'PY'"'"'
import json
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings

connection = PostgresConnection(PostgresSettings.from_env())
report = {
    "dirty_scopes": connection.fetch_all("select status, count(*)::int as count from job.read_model_dirty_scopes group by status order by status"),
    "readiness": connection.fetch_all("select status, count(*)::int as count from read_model.app_status_readiness group by status order by status"),
    "read_model_outbox": connection.fetch_all("select status, count(*)::int as count from job.outbox_events where event_type like %s group by status order by status", ("%.read_model.refresh",)),
    "dead_letters": connection.fetch_all("select event_type, count(*)::int as count from job.outbox_events where status in ('dead_letter', 'dead_lettered') and event_type like %s group by event_type order by event_type", ("%.read_model.refresh",)),
}
print(json.dumps(report, ensure_ascii=False, sort_keys=True))
PY
'
```

Expected evidence:

- active release name is printed;
- `/health/ready` reports `ready`;
- dirty scopes are all `done`;
- readiness rows are all `fresh`;
- read-model outbox rows are all `done`;
- dead-letter groups are empty.

Rollback/cleanup: none. This is read-only.

## Step 2 - Focused User-Scope API Metadata Probe

Command:

```bash
ssh finops-prod-root 'set +x; set -eu
release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"
if [ ! -d "$release_src/backend/src" ]; then
  release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"
fi
set -a
source /etc/fin-ops/fin-ops.common.env
source /etc/fin-ops/fin-ops.secrets.env
set +a
cd "$release_src"
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python - <<'"'"'PY'"'"'
import json
from urllib.request import Request, urlopen

from fin_ops_platform.services.oa_applicant_credentials import OaApplicantCredentialService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.oa_applicant_credentials import PostgresOaApplicantCredentialRepository
from fin_ops_platform.services.target_oa_applicant_token_provider import OaLoginClient
from fin_ops_platform.tools import http_slo_probe

FOCUSED_NAMES = {"pending_invoices_rows", "pending_invoices_filter_options", "no_oa_bank_batches"}

conn = PostgresConnection(PostgresSettings.from_env())
credential_service = OaApplicantCredentialService(repository=PostgresOaApplicantCredentialRepository(conn))
summaries = [item for item in credential_service._repository.list_credentials() if item.has_credential and item.enabled]
result = {
    "version": 1,
    "mode": "focused_target_oa_applicant_user_scope_http_slo",
    "configured_target_credential_count": len(summaries),
    "focused_probe_names": sorted(FOCUSED_NAMES),
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
session_request = Request("http://127.0.0.1:18001/api/session/me", method="GET", headers=headers)
with urlopen(session_request, timeout=15) as response:
    session_payload = json.loads(response.read().decode("utf-8"))

focused_probes = [probe for probe in http_slo_probe.DEFAULT_API_PROBES if probe.name in FOCUSED_NAMES]
focused_report = http_slo_probe.collect_http_slo(
    base_url="http://127.0.0.1:18001",
    probes=focused_probes,
    headers=headers,
    iterations=1,
    warmup=1,
    timeout_seconds=20,
    require_auth=True,
    include_samples=False,
)
result.update({
    "status": focused_report.get("status"),
    "session": {
        "http_status": 200,
        "allowed": bool(session_payload.get("allowed")),
        "can_access_app": bool(session_payload.get("can_access_app")),
        "can_mutate_data": bool(session_payload.get("can_mutate_data")),
        "can_admin_access": bool(session_payload.get("can_admin_access")),
        "access_tier": session_payload.get("access_tier"),
    },
    "focused_api_probe": focused_report,
    "admin_probe_excluded": True,
})
if focused_report.get("status") == "pass":
    user_probes = [probe for probe in http_slo_probe.DEFAULT_API_PROBES if probe.auth_scope != "admin"]
    full_report = http_slo_probe.collect_http_slo(
        base_url="http://127.0.0.1:18001",
        probes=user_probes,
        headers=headers,
        iterations=1,
        warmup=1,
        timeout_seconds=20,
        require_auth=True,
        include_samples=False,
    )
    result["full_user_scope_api_probe"] = full_report
    result["status"] = "pass" if full_report.get("status") == "pass" else "full_user_scope_failed"

print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
raise SystemExit(0 if result.get("status") == "pass" else 1)
PY
'
```

Expected evidence:

- target credential count is non-zero;
- `/api/session/me` returns allowed full-access user scope and `can_admin_access=false`;
- focused probe status is `pass`;
- if full user-scope probe runs, all non-admin probes pass;
- output includes no response bodies or secrets.

Rollback/cleanup: none for API calls. If GET fresh gates enqueue refreshes, postcheck must prove dirty/outbox/readiness converged.

## Step 3 - Production Postcheck

Repeat Step 1 after the API probe.

Expected evidence:

- `/health/ready` remains `ready`;
- dirty scopes are all `done`;
- readiness rows are all `fresh`;
- read-model outbox rows are all `done`;
- dead-letter groups are empty.

## Execution Results

Executed by T0 through `ssh finops-prod-root` after writing this runbook.

### Precheck

The first precheck command printed release and health successfully, then stopped on the dead-letter aggregate query because the local shell invocation stripped SQL quotes around `'dead_letter'` / `'dead_lettered'`.

No write occurred. T0 reran the precheck through a local heredoc piped to `ssh finops-prod-root 'bash -s'` to preserve SQL quoting.

Successful precheck:

- active release: `dev-pending-invoice-source-17d13466-20260625`
- `/health/ready`: `ready`
- dirty scopes: `done=187054`
- readiness: `fresh=498`
- read-model outbox: `done=202949`
- read-model dead letters: none

### Focused User-Scope API Metadata Probe

The target OA applicant credential seam remained available:

- configured target credential count: `2`
- `/api/session/me`: `200`
- session allowed: `true`
- `can_access_app=true`
- `can_mutate_data=true`
- `can_admin_access=false`
- `access_tier=full_access`
- admin-only probe excluded: `true`

The focused probe used one warmup and one measured iteration for exactly the three Row273 remaining failures. It did not print token/cookie/password/env values, response bodies or payload rows.

Focused result:

- status: `fail`
- probe count: `3`
- sample count: `3`
- failed probe count: `1`
- max p95 ms: `660.208`

Focused outcomes:

| Probe | Result | Evidence |
| --- | --- | --- |
| `pending_invoices_rows` | pass | HTTP `200`, `read_model_status=fresh`, `refresh_enqueued_count=0`, p95 `660.208ms` |
| `pending_invoices_filter_options` | pass | HTTP `200`, `read_model_status=fresh`, `refresh_enqueued_count=0`, p95 `129.211ms` |
| `no_oa_bank_batches` | fail | HTTP `200`, `read_model_status=stale`, `refresh_enqueued_count=1`, p95 `143.406ms` |

Because the focused set failed, T0 obeyed the stop gate and did not run the full non-admin user-scope default API probes.

### Postcheck

Postcheck stayed clean after the focused probe:

- active release: `dev-pending-invoice-source-17d13466-20260625`
- `/health/ready`: `ready`
- dirty scopes: `done=187055`
- readiness: `fresh=498`
- read-model outbox: `done=202950`
- read-model dead letters: none
- recent 10-minute dirty activity: `no_oa_bank_batch done=1`
- recent 10-minute read-model outbox activity: `no_oa_bank_batch.read_model.refresh done=1`

The single GET-triggered no-OA refresh converged to done. No manual enqueue, requeue, repair, replay, direct DB mutation, readiness mutation, deploy, restart, browser/admin/write probe, secret output or payload-row output occurred.

## Result

Decision: `production-evidence-deferred`.

This boundary proved:

- Row277 fixed the pending invoice production API metadata gap from Row273: both pending invoice probes now return fresh user-scope metadata.
- The T0 target OA applicant user-scope credential seam still works without printing/storing credentials or tokens.
- Production health, dirty scopes, readiness, read-model outbox and dead letters stayed clean after the focused probe.
- The GET-triggered no-OA refresh converged to done.

This boundary did not prove:

- full user-scope authenticated API closure, because `no_oa_bank_batches` still returns `read_model_status=stale`;
- browser data hydration closure;
- admin-only App Health closure;
- write-after-read convergence;
- module/global closure.

Next safe action:

- Select a read-only no-OA API stale diagnosis boundary that explains why `GET /api/no-oa-bank-batches?month=2026-06&bucket=unsubmitted&page=1&page_size=200` still reports `stale` after the current row-level category source-version mismatch has cleared and the GET-triggered refresh converged.
