# Production Admin Scope Auth Seam Read-Only Classification - 2026-06-25

**Boundary:** `production:admin-scope-auth-seam-read-only-classification`
**Status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`
**Production mutation:** read-only auth/session classification only

## Goal

Classify whether an existing non-secret admin auth seam is available for admin-scope production evidence, without asking for admin secrets, printing/storing tokens or running browser/write-flow probes.

This boundary is not an admin feature smoke unless a live admin session seam is proven safely first.

## Inputs Reviewed

- `analysis/deployment-production-browser-smoke-harness-packaging-feasibility-audit-2026-06-25.md`
- `analysis/production-read-model-full-user-scope-api-metadata-smoke-after-turnover-fixes-2026-06-25.md`
- `backend/src/fin_ops_platform/app/auth.py`
- `backend/src/fin_ops_platform/services/oa_applicant_credentials.py`
- `backend/src/fin_ops_platform/services/target_oa_applicant_token_provider.py`
- `backend/src/fin_ops_platform/tools/http_slo_probe.py`

## Safety Scope

Allowed:

- read-only production release/health/aggregate checks;
- non-secret environment presence checks for supported HTTP SLO auth variables;
- target OA applicant credential login in a remote production Python process, with token kept in memory only;
- `/api/session/me` calls to classify session permission booleans;
- optional admin endpoint metadata probe only if a live admin session is proven first.

Forbidden:

- printing/storing secrets, tokens, cookies, passwords, env values, response bodies, payload rows or business identifiers;
- browser probes;
- write-flow probes;
- deploy, restart, requeue, repair, replay, direct SQL mutation, readiness mutation or `--apply`;
- inferring admin access from config alone without a live `/api/session/me` proof.

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

Stop if health is not ready or aggregates are not clean.

### 2. Check supported HTTP SLO admin auth configuration without values

```bash
ssh finops-prod-root 'set +x; set -eu; set -a; [ -f /etc/fin-ops/fin-ops.common.env ] && . /etc/fin-ops/fin-ops.common.env; [ -f /etc/fin-ops/fin-ops.secrets.env ] && . /etc/fin-ops/fin-ops.secrets.env; set +a; admin_token_configured=0; generic_cookie_configured=0; [ -n "${FIN_OPS_HTTP_SLO_ADMIN_TOKEN:-}" ] && admin_token_configured=1; [ -n "${FIN_OPS_HTTP_SLO_COOKIE:-}" ] && generic_cookie_configured=1; echo "http_slo_admin_token_configured=$admin_token_configured"; echo "http_slo_cookie_configured=$generic_cookie_configured"'
```

This does not prove admin access; it only classifies whether a supported environment seam is configured.

### 3. Classify target OA applicant sessions

This command logs in configured target OA applicant credentials in memory and prints only sanitized aggregate permission counts.

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
login_client = OaLoginClient()
result = {
    "version": 1,
    "mode": "target_oa_applicant_admin_scope_classification",
    "configured_target_credential_count": len(summaries),
    "session_count": 0,
    "allowed_count": 0,
    "can_access_app_count": 0,
    "can_mutate_data_count": 0,
    "can_admin_access_count": 0,
    "access_tiers": {},
    "login_error_count": 0,
    "login_error_codes": [],
}
login_errors = []
for summary in summaries:
    try:
        credential = credential_service.resolve_login_credential(summary.target_applicant_code)
        if credential is None:
            login_errors.append("credential_unavailable")
            continue
        token = login_client.login(credential.oa_username, credential.password)
        headers = http_slo_probe._auth_headers(bearer_token=token)
        request = Request("http://127.0.0.1:18001/api/session/me", method="GET", headers=headers)
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        login_errors.append(str(getattr(exc, "code", "") or exc.__class__.__name__))
        continue
    result["session_count"] += 1
    result["allowed_count"] += int(bool(payload.get("allowed")))
    result["can_access_app_count"] += int(bool(payload.get("can_access_app")))
    result["can_mutate_data_count"] += int(bool(payload.get("can_mutate_data")))
    result["can_admin_access_count"] += int(bool(payload.get("can_admin_access")))
    tier = str(payload.get("access_tier") or "unknown")
    result["access_tiers"][tier] = int(result["access_tiers"].get(tier, 0)) + 1

result["login_error_count"] = len(login_errors)
result["login_error_codes"] = sorted(set(login_errors))[:5]
result["admin_auth_seam_available"] = result["can_admin_access_count"] > 0
print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
raise SystemExit(0)
PY'
```

If `admin_auth_seam_available=false`, stop and classify admin evidence as deferred. Do not run admin API probes.

### 4. Optional admin endpoint metadata probe

Run only if command 3 proves `admin_auth_seam_available=true`. The command must be added as a follow-up update before execution, because this runbook is expected to stop when no admin seam exists.

### 5. Postcheck

Repeat command 1 after classification. Counts should remain unchanged.

## Expected Result Classes

- `production-controlled`: a live admin session seam is proven and optional admin metadata probe is executed safely with clean postchecks.
- `production-evidence-deferred`: no supported admin HTTP SLO env seam and no target OA applicant credential resolves to `can_admin_access=true`.
- `hard stop`: any path would require printing/storing an admin secret or running browser/write probes.

## Execution Evidence

The runbook was committed and pushed before production execution in commit `37fd45a4`.

### Precheck

Release and health:

```text
release_src=/opt/fin-ops/releases/dev-turnover-source-version-persistence-20260625/src
release_name=dev-turnover-source-version-persistence-20260625
git_commit=8f525563e10972168014356ff410c4fc8456f377
{'status': 'ready'}
```

Aggregate precheck:

```text
dirty_scopes [{'status': 'done', 'count': 187061}]
readiness [{'status': 'fresh', 'count': 498}]
read_model_outbox [{'status': 'done', 'count': 202956}]
read_model_dead_letters 0
```

### Supported Admin Auth Env Presence

No supported HTTP SLO admin auth seam is configured:

```text
http_slo_admin_token_configured=0
http_slo_cookie_configured=0
```

### Target OA Applicant Session Classification

Target OA applicant credentials are available and live, but they are non-admin:

```json
{
  "access_tiers": {
    "full_access": 2
  },
  "admin_auth_seam_available": false,
  "allowed_count": 2,
  "can_access_app_count": 2,
  "can_admin_access_count": 0,
  "can_mutate_data_count": 2,
  "configured_target_credential_count": 2,
  "login_error_codes": [],
  "login_error_count": 0,
  "mode": "target_oa_applicant_admin_scope_classification",
  "session_count": 2,
  "version": 1
}
```

Because no live admin session seam exists, T0 obeyed the runbook stop gate and did not run the optional admin endpoint metadata probe.

### Postcheck

Health remained ready:

```text
{'status': 'ready'}
```

Aggregate postcheck was unchanged:

```text
dirty_scopes [{'status': 'done', 'count': 187061}]
readiness [{'status': 'fresh', 'count': 498}]
read_model_outbox [{'status': 'done', 'count': 202956}]
read_model_dead_letters 0
```

## Result

`production-evidence-deferred`.

Admin-scope production evidence is blocked by auth seam availability. There is no configured `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` or `FIN_OPS_HTTP_SLO_COOKIE`, and both configured target OA applicant live sessions are `full_access` non-admin with `can_admin_access=false`. No admin API probe, browser probe, write-flow probe, secret output or production mutation occurred.

Next boundary:

`planning:controlled-write-flow-evidence-scenario-selection`

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service/repository code changed.
3. API contract tests: applicable as `/api/session/me` live session classification only.
4. Read model/cache/background job tests: applicable as pre/post aggregate checks.
5. Frontend component and interaction tests: not applicable; browser probes are forbidden in this boundary.
6. End-to-end business-flow integration tests: not applicable; no write flow is run.
7. Existing feature regression tests: applicable through docs verification and diff checks.
