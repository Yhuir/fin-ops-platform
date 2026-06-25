# Production Browser Smoke Token Broker Runbook - 2026-06-25

**Boundary:** `deployment:production-browser-smoke-token-broker-runbook`
**Status:** `analysis-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `deployment:production-browser-smoke-runner-runtime-availability-classification`

## Goal

Design a root-owned in-memory target OA token broker protocol for the future dedicated browser runner, without implementing or installing the broker, running production browser smoke, printing tokens or mutating production.

## Inputs Reviewed

- `analysis/deployment-production-browser-smoke-runner-bundle-implementation-2026-06-25.md`
- `analysis/production-read-model-authenticated-browser-page-smoke-runbook-2026-06-25.md`
- `backend/src/fin_ops_platform/services/target_oa_applicant_token_provider.py`
- `backend/src/fin_ops_platform/services/oa_applicant_credentials.py`
- `deploy/oa/README.md`
- `docs/operations/deployment.md`

## Existing Auth Facts

The existing target OA applicant login path:

- uses `OaApplicantCredentialService` to resolve configured target applicant credentials;
- decrypts the credential from PostgreSQL via the repository boundary;
- uses `OaLoginClient` and `OpenSslRsaPasswordEncryptor`;
- requires `FIN_OPS_OA_BASE_URL`, login path, RSA public key and `openssl`;
- returns an OA token from the OA login response.

Prior production classifications proved:

- target OA applicant credentials can log in;
- the sessions are full-access non-admin user scope;
- no admin auth seam exists.

## Broker Protocol

The future broker should be a root-owned helper, installed separately from app releases, for example:

```text
/usr/local/sbin/finops-browser-smoke-token-broker
```

The helper must:

1. run on the production app host, where root-only env and target OA applicant credential decryption are already available;
2. load `/etc/fin-ops/fin-ops.common.env` and `/etc/fin-ops/fin-ops.secrets.env` without echoing values;
3. resolve the active release source path;
4. import deployed backend code through `PYTHONPATH="$release_src/backend/src"`;
5. resolve enabled target OA applicant credentials;
6. log in to OA in memory;
7. call local `/api/session/me` using the token in memory;
8. reject the token if the session is not `allowed`, cannot access app, or has `can_admin_access=true`;
9. hand the token only to a dedicated runner process through a non-logged in-memory channel;
10. emit only sanitized metadata to logs/artifacts.

## Secret Channel Contract

The broker must not print tokens to human-visible stdout/stderr logs.

Approved future handoff shape:

- a runner wrapper opens a private pipe or file descriptor for token input;
- the broker writes the token only to that private descriptor;
- sanitized metadata goes to stdout/stderr or a report file;
- the runner wrapper immediately injects the token into the Playwright child process environment;
- the token variable is removed from the wrapper environment after child process start;
- no shell history, trace, debug log, artifact, JSON report or markdown file contains the token.

Rejected handoff shapes:

- `echo "$TOKEN"` in a shell;
- writing token to a temp file;
- returning token in JSON;
- pasting/copying token into local Playwright;
- storing token in CI secrets as a side effect of the run;
- logging all broker stdout in CI or terminal transcripts if stdout contains token bytes.

## Sanitized Metadata Contract

Allowed broker metadata:

- `broker_status`;
- target credential count;
- selected credential ordinal only, not applicant code/name/username;
- login error count and redacted error codes;
- session booleans: `allowed`, `can_access_app`, `can_mutate_data`, `can_admin_access`;
- `access_tier`;
- token byte count or hash prefix is forbidden because it can become a token oracle.

Forbidden broker metadata:

- token;
- cookie;
- password;
- OA username;
- target applicant code/name;
- DSN/env values;
- response bodies;
- payload rows;
- business identifiers.

## Stop Gates

Stop before token handoff if:

- active release cannot be resolved;
- required env/config is missing;
- credential count is zero;
- login fails;
- `/api/session/me` is unavailable;
- session is not allowed or cannot access app;
- session has `can_admin_access=true`;
- runner wrapper cannot provide a non-logged private token descriptor;
- stdout/stderr redaction cannot be guaranteed;
- any command would require package install, browser download, deployment, app auth changes or production mutation.

## Future Execution Sketch

This is intentionally not executable in this slice. A later implementation must replace placeholders with a reviewed helper and runner wrapper:

```text
runner-wrapper \
  --bundle /path/to/fin-ops-production-browser-smoke.tar.gz \
  --token-broker "ssh finops-prod-root sudo -n /usr/local/sbin/finops-browser-smoke-token-broker --token-fd 3" \
  --base-url https://www.yn-sourcing.com \
  --release-name <active-release-name>
```

The wrapper must keep fd `3` out of logs and must fail closed if the broker writes token bytes to stdout/stderr instead of the private descriptor.

## Pre/Post Checks Required For Future Execution

Before and after any future browser run:

- `/health/ready`;
- `job.read_model_dirty_scopes` grouped by status;
- `read_model.app_status_readiness` grouped by status;
- read-model `job.outbox_events` grouped by status;
- read-model dead-letter count.

Counts must remain unchanged for browser evidence closure. Any GET-triggered refresh, outbox delta, non-fresh readiness or dead letter keeps browser evidence deferred.

## Decision

Do not implement or install the token broker in this slice.

The next safe boundary is:

`deployment:production-browser-smoke-runner-runtime-availability-classification`

That boundary should classify whether any existing controlled runner environment can execute the already-packaged bundle without installing/downloading browsers or receiving token bytes through logs. If no runner exists, browser evidence remains blocked by runner runtime availability rather than app code.

## Docs Impact Assessment

No long-term docs changed in this design slice because no broker command is implemented or approved for execution. The future broker implementation must update:

- `docs/operations/deployment.md`;
- `deploy/oa/README.md`;
- `docs/dev/testing.md`;
- the production browser smoke runbook.

## State-Machine Impact

- Row306 transitions from `pending` to `analysis-closed`.
- Row307 is inserted as `pending`.
- Browser production evidence remains deferred until runner runtime, broker implementation and production execution are complete.
- Admin evidence remains deferred pending a supported admin seam.
- Write apply remains blocked pending approval and reversible-object gates.
- Global/module closure remains open.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service/repository code changed.
3. API contract tests: not applicable; no API contract changed.
4. Read model/cache/background job tests: not applicable; no read model runtime changed.
5. Frontend component and interaction tests: not applicable; token broker design only.
6. End-to-end business-flow integration tests: not executed; production browser execution remains deferred.
7. Existing feature regression tests: applicable through docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check` after staging
