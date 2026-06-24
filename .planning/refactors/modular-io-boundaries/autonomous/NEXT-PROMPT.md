# Next Prompt

Continue after `production:no-oa-source-version-provider-fix-deploy-and-convergence`.

## Current State

- Branch: `dev`.
- Row284 deployed release `dev-no-oa-source-version-480d2d0e-20260625`.
- Active release `RELEASE.json`:
  - `git_branch=dev`.
  - `git_commit=d117b4519284db00c0fa88bdf7faaa938a5b1f69`.
  - `release_name=dev-no-oa-source-version-480d2d0e-20260625`.
- Deployed commit contains code fix commit `480d2d0ebe3bbf3543a8b0a855ec252fae4bbc1a`.
- Focused authenticated no-OA user-scope API metadata probe now passes:
  - configured target credential count: `2`;
  - session `allowed=true`, `can_access_app=true`, `can_mutate_data=true`, `can_admin_access=false`, `access_tier=full_access`;
  - `no_oa_bank_batches` only;
  - HTTP `200`;
  - `read_model_statuses={"fresh": 1}`;
  - `refresh_enqueued_count=0`;
  - p95 `138.167ms`;
  - focused report `status=pass`.
- Postcheck stayed clean:
  - `/health/ready`: ready;
  - dirty scopes: `done=187057`;
  - readiness: `fresh=498`;
  - read-model outbox: `done=203223`;
  - read-model dead letters: none.
- No response body, payload row, secret, direct DB/queue/readiness mutation, repair, requeue or worker replay occurred.
- Full non-admin user-scope API metadata, browser/admin/write probes and global/module closure remain open.

## Next Boundary

`production:read-model-full-user-scope-api-metadata-smoke-after-no-oa-fix`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Finish committing/pushing Row284 evidence if it is not already committed.
3. Write a bounded production runbook under `analysis/` before running the full user-scope API metadata smoke.
4. Reuse the target OA applicant credential seam inside the remote production process; do not print or store credentials, tokens, cookies or env values.
5. Run only non-admin user-scope `http_slo_probe.DEFAULT_API_PROBES` metadata with `include_samples=False`.

## Full User-Scope API Metadata Scope

Run authenticated metadata-only probes for all default API probes except `auth_scope="admin"`.

Target:

- report `status=pass`;
- every user-scope probe has expected HTTP status;
- read-model-backed probes are fresh;
- `refresh_enqueued_count=0`;
- p95 under each probe target;
- `/health/ready` remains ready;
- dirty scopes remain done;
- readiness remains fresh;
- read-model outbox remains done;
- read-model dead letters remain empty.

## Stop Gates

- Do not run browser/admin/write probes in this boundary.
- Do not print response bodies, `samples`, payload rows, business identifiers, credentials, tokens, cookies, passwords or env values.
- Stop if precheck health/dirty/readiness/outbox/dead-letter state is not clean.
- If any user-scope probe fails, stale, enqueues refresh, or exceeds target, collect only sanitized failing-probe metadata and postcheck evidence.
- Do not claim module/global closure from a full user-scope API metadata pass alone.
