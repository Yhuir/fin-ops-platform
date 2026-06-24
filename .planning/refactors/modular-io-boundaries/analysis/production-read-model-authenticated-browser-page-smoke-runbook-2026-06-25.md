# Production Read Model Authenticated Browser Page Smoke Runbook - 2026-06-25

**Boundary:** `production:read-model-authenticated-browser-page-smoke-runbook`
**Status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`
**Production mutation:** read-only browser navigation only; no admin/write probes
**Active release expected:** `dev-turnover-source-version-persistence-20260625`

## Goal

Collect bounded authenticated production browser page evidence after Row292 proved all non-admin user-scope API metadata probes pass with no fresh-gate enqueue.

This boundary exercises only user-scope read-only page navigation. It does not run admin probes, write-flow probes, exports/download checks, deploys, restarts, queue operations, repair/replay, direct SQL writes or readiness mutations.

## Inputs Reviewed

- `analysis/planning-post-full-user-api-smoke-browser-admin-write-evidence-selection-2026-06-25.md`
- `analysis/production-read-model-controlled-production-api-browser-runbook-2026-06-25.md`
- `analysis/production-read-model-full-user-scope-api-metadata-smoke-after-turnover-fixes-2026-06-25.md`
- `web/e2e/production-route-shell.spec.ts`
- `web/e2e/production-admin-app-health.spec.ts`
- `web/playwright.config.ts`
- `web/package.json`
- `web/src/features/authToken.ts`
- `web/src/features/apiClient.ts`
- `web/src/features/session/api.ts`

## Safety Model

The existing production route-shell Playwright spec can set an `Admin-Token` browser cookie from `FIN_OPS_E2E_OA_TOKEN`, then navigate core `/fin-ops/*` routes and fail if:

- the session gate blocks access;
- the page stays in a loading shell;
- any `POST`, `PUT`, `PATCH` or `DELETE` request is observed.

The token must not be copied to the local shell, printed, written to a file or stored in docs. The runbook therefore logs in on the production host and passes the token only as an in-memory environment variable to the Playwright subprocess in the same remote shell.

If the deployed production source lacks a usable Playwright harness/browser runtime, stop and classify as `production-evidence-deferred`; do not copy tokens or install new tooling in this boundary.

## Preconditions

- `dev` and `origin/dev` are aligned.
- `ssh finops-prod-root` works.
- Active release is available under `/opt/fin-ops/current/src` or the latest release source path.
- Target OA applicant credentials remain configured.
- Existing route-shell spec remains read-only.

## Forbidden

- Printing/storing secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows or business identifiers.
- Running `production-admin-app-health.spec.ts` or any admin API/browser probe.
- Running write-flow, import, save, confirm, withdraw, export-download, upload or data-reset scenarios.
- Running browser actions outside read-only route navigation.
- Deploy, restart, requeue, repair, replay, resolve, direct SQL mutation, readiness mutation or `--apply`.
- Installing packages, downloading browser binaries or changing production runtime state to make the smoke pass.
- Claiming module/global closure from this evidence alone.

## Commands

All commands must use `set +x` for secret-bearing shells.

### 1. Precheck: release, health and aggregates

```bash
ssh finops-prod-root 'set +x; set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; echo "release_src=$release_src"; echo "release_name=$(basename "$(dirname "$release_src")")"; echo "git_commit=$(cat "$release_src/RELEASE.json" 2>/dev/null | /opt/fin-ops/venv/bin/python -c "import json,sys; print(json.load(sys.stdin).get(\"git_commit\", \"\"))" 2>/dev/null || git -C "$release_src" rev-parse HEAD 2>/dev/null || true)"; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
ssh finops-prod-root 'set +x; set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; set -a; [ -f /etc/fin-ops/fin-ops.common.env ] && . /etc/fin-ops/fin-ops.common.env; [ -f /etc/fin-ops/fin-ops.secrets.env ] && . /etc/fin-ops/fin-ops.secrets.env; set +a; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python - <<'"'"'PY'"'"'
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings

conn = PostgresConnection(PostgresSettings.from_env())
with conn.connection() as connection:
    with connection.cursor() as cur:
        cur.execute("select status, count(*) from job.read_model_dirty_scopes group by status order by status")
        print("dirty_scopes", cur.fetchall())
        cur.execute("select status, count(*) from read_model.app_status_readiness group by status order by status")
        print("readiness", cur.fetchall())
        cur.execute("select status, count(*) from job.outbox_events where event_type like %s group by status order by status", ("%.read_model.refresh",))
        print("read_model_outbox", cur.fetchall())
        cur.execute("select count(*) as count from job.outbox_events where status = %s and event_type like %s", ("dead_lettered", "%.read_model.refresh"))
        print("read_model_dead_letters", cur.fetchone()["count"])
PY'
```

Stop if `/health/ready` is not ready, any non-done dirty/outbox row appears, any non-fresh readiness row appears or any read-model dead letter exists.

### 2. Check deployed Playwright harness availability without secrets

```bash
ssh finops-prod-root 'set +x; set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; cd "$release_src/web"; if [ -x node_modules/.bin/playwright ]; then echo "playwright_bin=present"; else echo "playwright_bin=missing"; fi; if [ -f e2e/production-route-shell.spec.ts ]; then echo "production_route_shell_spec=present"; else echo "production_route_shell_spec=missing"; fi'
```

Stop as `production-evidence-deferred` if the Playwright binary or route-shell spec is missing. Do not install dependencies in this boundary.

### 3. Authenticated route-shell browser smoke

This command:

1. loads production env without printing values;
2. resolves one enabled target OA applicant credential in memory;
3. logs in to OA in memory;
4. verifies `/api/session/me` is full-access non-admin user scope;
5. runs only `web/e2e/production-route-shell.spec.ts` against `https://www.yn-sourcing.com`;
6. passes the token only as an in-memory environment variable to the Playwright subprocess;
7. prints sanitized route-shell summary and post-run session class only.

```bash
ssh finops-prod-root 'set +x; set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; set -a; [ -f /etc/fin-ops/fin-ops.common.env ] && . /etc/fin-ops/fin-ops.common.env; [ -f /etc/fin-ops/fin-ops.secrets.env ] && . /etc/fin-ops/fin-ops.secrets.env; set +a; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python - <<'"'"'PY'"'"'
import json
import os
import subprocess
from urllib.request import Request, urlopen

from fin_ops_platform.services.oa_applicant_credentials import OaApplicantCredentialService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.oa_applicant_credentials import PostgresOaApplicantCredentialRepository
from fin_ops_platform.services.target_oa_applicant_token_provider import OaLoginClient
from fin_ops_platform.tools import http_slo_probe

release_src = os.getcwd()
web_dir = os.path.join(release_src, "web")
result = {
    "version": 1,
    "mode": "target_oa_applicant_user_scope_browser_route_shell",
}
playwright_bin = os.path.join(web_dir, "node_modules", ".bin", "playwright")
spec_path = os.path.join(web_dir, "e2e", "production-route-shell.spec.ts")
if not os.path.exists(playwright_bin) or not os.path.exists(spec_path):
    result.update({"status": "browser_harness_missing", "playwright_bin": os.path.exists(playwright_bin), "spec": os.path.exists(spec_path)})
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(2)

conn = PostgresConnection(PostgresSettings.from_env())
credential_service = OaApplicantCredentialService(repository=PostgresOaApplicantCredentialRepository(conn))
summaries = [item for item in credential_service._repository.list_credentials() if item.has_credential and item.enabled]
result["configured_target_credential_count"] = len(summaries)
if not summaries:
    result.update({"status": "credential_missing"})
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(2)

token = None
login_errors = []
login_client = OaLoginClient()
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
request = Request("http://127.0.0.1:18001/api/session/me", method="GET", headers=headers)
with urlopen(request, timeout=15) as response:
    session_payload = json.loads(response.read().decode("utf-8"))

session_summary = {
    "http_status": 200,
    "allowed": bool(session_payload.get("allowed")),
    "can_access_app": bool(session_payload.get("can_access_app")),
    "can_mutate_data": bool(session_payload.get("can_mutate_data")),
    "can_admin_access": bool(session_payload.get("can_admin_access")),
    "access_tier": session_payload.get("access_tier"),
}
result["session"] = session_summary
if not session_summary["allowed"] or not session_summary["can_access_app"] or session_summary["can_admin_access"]:
    result.update({"status": "unexpected_session_scope"})
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(2)

env = {
    **os.environ,
    "FIN_OPS_E2E_PRODUCTION_SMOKE": "1",
    "FIN_OPS_E2E_SKIP_WEBSERVER": "1",
    "PLAYWRIGHT_BASE_URL": "https://www.yn-sourcing.com",
    "FIN_OPS_E2E_OA_TOKEN": token,
    "CI": "1",
}
proc = subprocess.run(
    [playwright_bin, "test", "e2e/production-route-shell.spec.ts", "--project=chromium", "--reporter=list"],
    cwd=web_dir,
    env=env,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    timeout=180,
)
output_lines = []
for line in proc.stdout.splitlines():
    if "Admin-Token" in line or "FIN_OPS_E2E_OA_TOKEN" in line or token in line:
        continue
    output_lines.append(line[:240])
result.update({
    "status": "pass" if proc.returncode == 0 else "failed",
    "returncode": proc.returncode,
    "route_shell_spec": "e2e/production-route-shell.spec.ts",
    "admin_probe_excluded": True,
    "write_flow_excluded": True,
    "sanitized_output_tail": output_lines[-40:],
})
print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
raise SystemExit(proc.returncode)
PY'
```

Stop after this command whether it passes or fails. Do not run admin or write smoke in this boundary.

### 4. Postcheck: health and aggregate

Repeat command 1 after the browser smoke. Compare counts with the precheck. If any dirty/outbox/readiness/dead-letter count changes, classify it and stop.

## Expected Result Classes

- `production-controlled`: route-shell browser smoke passes, the session is full-access non-admin user scope, no mutating request is observed by the spec, and pre/post aggregates are unchanged.
- `production-evidence-deferred`: the browser harness is missing, Playwright/browser runtime is unavailable, target applicant login fails, route-shell browser smoke fails, or a GET-triggered refresh/aggregate delta appears.
- `hard stop`: any command would print secrets/payload rows, require admin/write flow, require package install/browser download, or mutate production state outside read-only navigation.

## Execution Evidence

The runbook was committed and pushed before production checks in commit `3089b284`.

### Precheck

Release and health:

```text
release_src=/opt/fin-ops/releases/dev-turnover-source-version-persistence-20260625/src
release_name=dev-turnover-source-version-persistence-20260625
git_commit=8f525563e10972168014356ff410c4fc8456f377
{'status': 'ready'}
```

The first aggregate command had a shell quoting bug around the literal `dead_lettered` status. It failed read-only after printing the first three aggregate groups:

```text
dirty_scopes [{'status': 'done', 'count': 187061}]
readiness [{'status': 'fresh', 'count': 498}]
read_model_outbox [{'status': 'done', 'count': 202956}]
```

The corrected aggregate command first used tuple indexing against a dict row and failed read-only after the same three aggregate groups. The final corrected command used parameterized SQL and dict-field access:

```text
dirty_scopes [{'status': 'done', 'count': 187061}]
readiness [{'status': 'fresh', 'count': 498}]
read_model_outbox [{'status': 'done', 'count': 202956}]
read_model_dead_letters 0
```

### Browser Harness Availability

The deployed production release does not contain an executable Playwright harness or the route-shell spec:

```text
playwright_bin=missing
production_route_shell_spec=missing
```

Per the stop gate, T0 did not install packages, download browser binaries, copy local tests, copy tokens, run local Playwright with a production token, run admin probes, run write-flow probes or execute any browser command.

### Postcheck

Health remained ready:

```text
{'status': 'ready'}
```

Aggregate postcheck was unchanged from precheck:

```text
dirty_scopes [{'status': 'done', 'count': 187061}]
readiness [{'status': 'fresh', 'count': 498}]
read_model_outbox [{'status': 'done', 'count': 202956}]
read_model_dead_letters 0
```

## Result

`production-evidence-deferred`.

Authenticated production browser page smoke could not run because the deployed production source lacks both `web/node_modules/.bin/playwright` and `web/e2e/production-route-shell.spec.ts`. This is a browser harness availability gap, not an API/session/freshness failure. Production health, dirty scopes, readiness, read-model outbox and read-model dead letters stayed clean before and after. Browser/admin/write evidence remains open.

Next boundary:

`planning:post-authenticated-browser-harness-missing-next-boundary-selection`

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service/repository code changed.
3. API contract tests: Row292 already covers non-admin API metadata; this boundary uses `/api/session/me` only to classify session scope.
4. Read model/cache/background job tests: applicable as production pre/post aggregate checks.
5. Frontend component and interaction tests: applicable as authenticated production browser route-shell smoke.
6. End-to-end business-flow integration tests: not applicable for writes; this boundary is read-only navigation only.
7. Existing feature regression tests: applicable through existing `production-route-shell.spec.ts` and docs/diff verification.
