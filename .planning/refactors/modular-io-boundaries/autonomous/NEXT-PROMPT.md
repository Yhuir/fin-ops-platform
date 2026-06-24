# Next Prompt

Continue after `planning:post-default-api-probe-harness-next-boundary-selection`.

## Current State

- Branch: `dev`.
- Row267 full deterministic local browser smoke passed: `175/175`.
- Row269 production auth preflight found `/health/ready` ready and `http_slo_auth_configured=no`, so the standard authenticated HTTP SLO API smoke did not run.
- Row271 broadened the local/internal API contract harness across `http_slo_probe.DEFAULT_API_PROBES`.
- Row271 targeted verification passed: `PYTHONPATH=backend/src pytest -q tests/test_read_model_api_contract_harness.py` -> `2 passed`, `84 subtests passed`.
- Row272 reconciled local API/browser evidence with production gaps and selected a controlled production API/browser runbook instead of waiting for human-provided secrets.
- The active T0 goal authorizes `ssh finops-prod-root` as the sanctioned T0-only production evidence path when commands are bounded, non-secret and read-only or cleanup-safe.
- Local deterministic browser evidence and local API harness evidence do not prove production API response shapes, browser data hydration, high-row browser behavior, worker-drain/write-after-read convergence or module/global closure.

## Next Boundary

`production:read-model-controlled-production-api-browser-runbook`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Acquire the direct-dev write lease before editing:
   - `mkdir /tmp/fin-ops-dev-write.lock`
4. Read:
   - `analysis/planning-post-default-api-probe-harness-next-boundary-selection-2026-06-25.md`
   - `analysis/contract-read-model-default-api-probe-harness-broadening-2026-06-25.md`
   - `analysis/production-read-model-auth-preflight-and-api-smoke-runbook-2026-06-25.md`
   - `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
   - `backend/src/fin_ops_platform/tools/http_slo_probe.py`
   - `tests/test_http_slo_probe.py`
   - `tests/test_read_model_api_contract_harness.py`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
5. Write a production runbook/evidence file under `analysis/` before running any production command.
6. The runbook must describe exact commands, expected sanitized evidence, stop gates, post-checks, rollback/cleanup posture and why no secret output is required.
7. If the runbook gates pass, execute only the bounded production commands described in the runbook.
8. Update controller files with result and next boundary.

## Runbook Constraints

- Use `ssh finops-prod-root` and existing deployed runtime configuration only.
- Do not print or store env values, DSNs, tokens, cookies, private keys, response bodies, payload rows or sensitive business data.
- Start and end with `/health/ready`, active release and read-only dirty/readiness/outbox/dead-letter/worker heartbeat checks.
- API response-shape evidence must be metadata-only: status, route classification, envelope keys, read-model status/source-version fields, counts and latency are acceptable.
- Browser/page evidence must be separated from API evidence. If browser data hydration needs a secret-bearing user session or cookie, stop and record that blocker precisely.
- High-row evidence must remain metadata-only and must not store business payload rows.
- Do not deploy, restart, requeue, repair, replay workers, mutate DB/queue/readiness state, or run production business writes in this boundary unless the runbook proves a narrower bounded reversible action and there is no safer validation path.

## Stop Gates

- Not on branch `dev`.
- Dirty worktree with unrelated/user files.
- `HEAD != origin/dev` after fetch/pull.
- Production command would reveal secrets or payload rows.
- Production command would require broad/destructive mutation, unbounded worker replay/consume or unclear rollback/cleanup.
- No non-secret authenticated/internal-equivalent production API or browser evidence seam exists.
- Do not request secrets from the user; record the precise missing seam and continue another safe owned boundary.
- Do not claim module/global closure from local browser/API tests or metadata-only production checks alone.
