# Production No-OA Source-Version Provider Fix Deploy And Convergence - 2026-06-25

**Boundary:** `production:no-oa-source-version-provider-fix-deploy-and-convergence`
**Status:** `runbook-written`
**Module closure:** `not-module-closed`
**Production mutation:** bounded release deploy/restart through repository deploy entrypoint; one focused authenticated GET may enqueue only if still stale
**Worker threads created:** none
**Previous boundary:** `production:no-oa-bank-batches-api-stale-reasons-sanitized-probe`

## Goal

Deploy the latest clean `dev` commit containing `480d2d0ebe3bbf3543a8b0a855ec252fae4bbc1a`, which aligns no-OA API source-version expectations with the SQL Workbench projection schema version. The deploy commit may include this pre-deploy runbook as a controller evidence-only change. Then prove the focused authenticated no-OA API fresh gate converges without an extra refresh enqueue.

Target evidence:

- active release points to the latest deployed `dev` commit and that commit contains `480d2d0ebe3bbf3543a8b0a855ec252fae4bbc1a`;
- `/health/ready` is ready;
- read-model dirty scopes are all `done`;
- App Status readiness rows are all `fresh`;
- read-model outbox rows are all `done`;
- read-model dead letters are empty;
- focused `GET /api/no-oa-bank-batches?month=2026-06&bucket=unsubmitted&page=1&page_size=200` returns HTTP `200`, `read_model_status=fresh`, `refresh_enqueued_count=0`, and p95 under `1000ms`.

This boundary must not run broad user-scope probes, browser probes, admin probes or write probes. It must not claim module/global closure.

## Allowed Operations

- `./scripts/deploy-oa.sh --release-name dev-no-oa-source-version-480d2d0e-20260625` from a clean `dev` worktree.
- `ssh finops-prod-root` with bounded pre/post checks.
- `/health/ready` readiness summary and active release/git commit discovery.
- Sourcing existing production env files with `set +x`, without printing env values.
- Reading target OA applicant credential summaries and decrypting one target applicant credential only inside a remote Python process.
- OA login inside the same remote Python process to hold the bearer token in memory only.
- API-only `http_slo_probe.collect_http_slo(...)` with the single `no_oa_bank_batches` probe and `include_samples=False`.
- If the focused API is still stale, one sanitized allowlist extraction of stale metadata: HTTP status, elapsed time, `read_model_status`, `read_model_stale_reasons`, `refresh_enqueued`, `refresh_reason`, and selected scalar pagination counts.
- Sanitized PostgreSQL aggregate summaries for dirty scopes, readiness, outbox and dead letters.

## Forbidden Operations

- Printing or storing env files, DSNs, OA usernames, passwords, bearer tokens, cookies, private keys, response bodies, payload rows, invoice numbers, project names, counterparties, account names, transaction IDs, batch IDs or other business identifiers.
- Passing tokens on the shell command line or writing tokens to files.
- Broad user-scope probes, browser/admin/write probes, worker replay, manual queue consume, repair tools, direct SQL mutation, direct readiness mutation, direct dirty-scope mutation or business writes.
- Deploying from a dirty worktree.
- Using `--allow-dirty`, `--replace-release`, `--mode legacy-current`, manual service edits or manual release activation outside the deploy entrypoint.

## Stop Gates

- Stop before deploy if `git status --short --branch` is not clean on `dev`.
- Stop before deploy if `HEAD` is not `origin/dev` after the pre-deploy runbook evidence commit, or if `git merge-base --is-ancestor 480d2d0ebe3bbf3543a8b0a855ec252fae4bbc1a HEAD` fails.
- Stop before deploy if precheck shows `/health/ready` unavailable/not ready, non-done dirty/outbox rows, non-fresh readiness rows or read-model dead letters.
- Stop before focused API if active release does not point to the deployed commit.
- Stop after the focused API if `no_oa_bank_batches` is not `fresh`, if it enqueues refresh, or if p95 is at/above `1000ms`; collect only sanitized stale reasons and postcheck evidence.
- Stop if postcheck shows health not ready, unresolved non-done read-model outbox/dirty rows, non-fresh readiness rows or dead letters.

## Exact Commands

Local predeploy verification:

```bash
git status --short --branch
git rev-parse HEAD origin/dev
bash scripts/verify.sh docs
git diff --check
```

Production precheck:

```bash
ssh finops-prod-root 'bash -s' <<'REMOTE'
set -euo pipefail
python3 - <<'PY'
# Print only active release/git metadata, health status and aggregate read-model status counts.
PY
REMOTE
```

Deploy:

```bash
./scripts/deploy-oa.sh --release-name dev-no-oa-source-version-480d2d0e-20260625
```

Focused API metadata probe:

```bash
ssh finops-prod-root 'bash -s' <<'REMOTE'
set -euo pipefail
python3 - <<'PY'
# Source production config without printing env values.
# Resolve one configured target OA applicant credential inside this process.
# Login and run only the no_oa_bank_batches API probe with include_samples=False.
# Print only sanitized scalar metadata.
PY
REMOTE
```

Production postcheck:

```bash
ssh finops-prod-root 'bash -s' <<'REMOTE'
set -euo pipefail
python3 - <<'PY'
# Print only active release/git metadata, health status, aggregate read-model status counts,
# recent no-OA dirty/outbox aggregate counts and read-model dead-letter aggregate counts.
PY
REMOTE
```

## Rollback And Cleanup

Primary rollback, only if the deployed release fails activation or post-deploy health cannot recover:

```bash
ssh finops-prod-root 'sudo -n /usr/local/sbin/finops-deploy-control status'
```

If a rollback target is needed, use the previous active release reported by deploy-control status and activate it through the same root-owned helper:

```bash
ssh finops-prod-root 'sudo -n /usr/local/sbin/finops-deploy-control activate <previous-release-name>'
ssh finops-prod-root 'curl -fsS http://127.0.0.1:8200/health/ready >/dev/null'
```

Cleanup of old inactive releases is handled by the deploy entrypoint's `cleanup-releases --keep` step. No manual queue/readiness/dirty-scope cleanup is allowed in this boundary.

## Why This Is Bounded

- The only intended production mutation is deploying one known commit through the repository's documented deploy entrypoint and root-owned deploy-control helper.
- The focused API call is one read-only GET for one explicit month/bucket/page scope; if the fresh gate unexpectedly enqueues, postcheck proves convergence and the boundary remains non-closed.
- No secrets or payload rows are printed because all auth and response reduction happens inside the remote Python process and only allowlisted scalar metadata is emitted.
- No direct database writes, manual refreshes, worker replays or repair commands are allowed.

## Production Evidence

Pending execution by T0 after this runbook is committed or held as the current controller evidence file.
