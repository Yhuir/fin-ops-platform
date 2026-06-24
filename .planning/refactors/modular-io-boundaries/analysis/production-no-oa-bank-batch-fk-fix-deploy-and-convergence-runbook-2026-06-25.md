# Production No-OA Bank Batch FK Fix Deploy And Convergence Runbook 2026-06-25

**Boundary:** `production:no-oa-bank-batch-fk-fix-deploy-and-convergence-runbook`
**Final status:** `planned`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `ddf6c636795f2787e2cd62bf89a9df62126b2ee9`

## Target Boundary

Deploy the no-OA FK delete-order fix and prove production convergence for the exact `no_oa_bank_batch:all` blocker identified in:

- `production-no-oa-bank-batch-dead-letter-read-only-diagnosis-2026-06-25.md`
- `read-model-no-oa-bank-batch-event-fk-delete-order-fix-2026-06-25.md`

## Controlled Operation Scope

Allowed operations, in order:

1. Run the repository-supported release deploy from a clean `dev` worktree:

```bash
./scripts/deploy-oa.sh --release-name dev-ddf6c636-no-oa-fk-20260625014906
```

2. Collect non-secret post-deploy evidence:

- active release identity from `/health` and `/health/ready`;
- selected systemd unit status for API, dispatcher and `fin-ops-worker@no-oa-bank-batch.service`;
- read-only PostgreSQL evidence for `job.outbox_events`, `job.read_model_dirty_scopes`, `read_model.app_status_readiness`.

3. If and only if the exact pre-existing event is still `dead_lettered` and the exact dirty scope is still pending after deploy, requeue the latest exact no-OA event using the active release runtime env without printing secrets:

```bash
ssh finops-prod-root 'set -euo pipefail; release_src="$(systemctl show fin-ops.service -P WorkingDirectory)"; cd "$release_src"; set -a; source /etc/fin-ops/fin-ops.common.env; source /etc/fin-ops/fin-ops.secrets.env; set +a; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops requeue --event-id 3bc506fd-5662-4902-a9b9-19b0d8fbe4a6 --reason no_oa_fk_delete_order_fix_deployed'
```

4. Wait for worker convergence and verify exact scope:

- latest `no_oa_bank_batch.read_model.refresh` for `no_oa_bank_batch:all` is `done`, or a later same-scope event is `done`;
- `job.read_model_dirty_scopes` for `no_oa_bank_batch:all` has no active `pending/processing/failed` row;
- `read_model.app_status_readiness` for `no_oa_bank_batch:all` is `fresh`;
- `/health/ready` returns `status=ready`;
- no new no-OA FK violation appears in selected worker logs.

## Forbidden

- Do not print env files, DSNs, passwords, tokens, cookies, private keys or secret env values.
- Do not manually `update`, `insert` or `delete` production DB rows.
- Do not mark dirty scopes done by hand.
- Do not delete dead-letter rows.
- Do not run broad queue replay, broad worker consume/replay, arbitrary repair tools or `--apply` repair commands.
- Do not deploy from a dirty worktree or with `--allow-dirty`.
- Do not force push or deploy `main`.

## Stop Gates

Stop before deploy if:

- local branch is not clean `dev` at `ddf6c636795f2787e2cd62bf89a9df62126b2ee9`;
- `origin/dev` does not match local `HEAD`;
- `bash scripts/verify.sh docs`, targeted tests or `git diff --check` fail;
- deploy would require secrets in local output.

Stop after deploy and classify `needs-human-production-gate` if:

- `./scripts/deploy-oa.sh` fails in check-release/activate/readiness/status/worker ensure;
- `/health` or `/health/ready` cannot prove the active release identity;
- API, dispatcher or no-OA worker does not return `active/running`;
- the exact requeue command would require exposing secrets or running arbitrary SQL;
- requeue fails and no later same-scope done event covers the blocker.

## Rollback / Cleanup Posture

The release deploy helper keeps previous releases. If activation fails, the deploy helper stops at its failing step and reports the step. Do not perform ad hoc rollback in this boundary unless the helper documents and executes it. Preserve non-secret evidence and stop.

The exact event requeue is recoverable because it only returns one existing dead-lettered event to the queue for the same read-model scope after deploying the code fix. If it dead-letters again, stop with evidence; do not retry repeatedly or manually mutate readiness.

## Pre-Deploy Verification

Already passed before writing this runbook:

```bash
PYTHONPATH=backend/src pytest tests/test_postgres_repositories_boundaries.py -q
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_read_model_refresh -v
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/workbench.py
bash scripts/verify.sh docs
git diff --check
git diff --cached --check
```

## Evidence Results

Pending execution after this runbook is committed so `./scripts/deploy-oa.sh` can run from a clean worktree.
