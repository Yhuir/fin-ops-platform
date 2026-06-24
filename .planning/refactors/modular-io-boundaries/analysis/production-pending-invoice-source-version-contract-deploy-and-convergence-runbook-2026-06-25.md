# Production Pending Invoice Source Version Contract Deploy And Convergence Runbook - 2026-06-25

**Boundary:** `production:pending-invoice-source-version-contract-deploy-and-convergence-runbook`
**Status:** `runbook-written`
**Module closure:** `not-module-closed`
**Production mutation:** bounded deploy plus explicit `pending_invoice:expense:all` refresh smoke only
**Previous boundary:** `read-models:pending-invoice-source-version-contract-alignment`
**Runtime fix commit:** `17d13466d5b4a5c28d55c7fedcd0815a0f21f91f`
**Target release:** `dev-pending-invoice-source-17d13466-20260625`

## Goal

Deploy the Row276 pending invoice source-version contract fix, then prove the production first-screen pending invoice scope can converge without broad repair:

- production code is running commit `17d13466d5b4a5c28d55c7fedcd0815a0f21f91f`;
- `/health/ready` is ready before and after the operation;
- only the explicit `pending_invoice:expense:all` smoke scope is enqueued;
- the `pending_invoice` worker fans out or completes through the registered refresh gateway/queue path;
- sanitized metadata proves rows and filter-options would be fresh for `direction=expense&filter=all` without printing payload rows.

This runbook does not repair or rebuild no-OA. The no-OA `bank_transaction_category_snapshot_version_mismatch` remains a separate boundary.

## Preconditions

- Local branch is `dev`, clean, and includes runtime fix commit `17d13466d5b4a5c28d55c7fedcd0815a0f21f91f`.
- Row276 local verification passed:
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime -v`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api -v`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v`
  - `python3 -m py_compile backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py tests/test_search_pending_sql_runtime.py`
- Production root SSH is available as `ssh finops-prod-root`.
- Release deployment uses the documented `./scripts/deploy-oa.sh` release path and server-side `finops-deploy-control`.

## Stop Gates

Stop before executing or continuing if any command would:

- print or store DSNs, passwords, tokens, cookies, private keys, env secret values or business payload rows;
- perform broad DB mutation, direct readiness mutation, manual mark-done, broad repair, unbounded replay, unbounded queue consume or no-OA repair;
- require deriving pending invoice scope keys by guessing;
- fail `/health/ready` before deploy;
- fail deploy prechecks, migration, activation, worker readiness or post-deploy health;
- leave the selected smoke event failed/dead-lettered/timed out without a clear bounded next diagnosis path.

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
  | /opt/fin-ops/venv/bin/python -c '"'"'import json,sys; p=json.load(sys.stdin); print({"status":p.get("status"),"release":p.get("release"),"read_model_refresh_failure_rate":p.get("read_model_refresh_failure_rate")})'"'"'
sudo -n /usr/local/sbin/finops-deploy-control status
'
```

Expected evidence:

- active release name and commit are printed;
- `/health/ready` reports `ready`;
- deploy-control status succeeds.

Rollback/cleanup: none. This is read-only.

## Step 2 - Deploy Target Release

Command:

```bash
./scripts/deploy-oa.sh --release-name dev-pending-invoice-source-17d13466-20260625
```

Expected evidence:

- local build and release packaging complete;
- remote `check-release` passes;
- remote `activate` passes migration, API readiness and worker readiness;
- frontend hash and public route checks pass;
- deploy-control status reports the target release.

Rollback:

- If activation fails, `deploy-oa.sh` stops at the failing step and does not continue with smoke.
- If activation succeeds but post-checks regress, reactivate the precheck release captured in Step 1:

```bash
ssh finops-prod-root 'sudo -n /usr/local/sbin/finops-deploy-control activate <precheck_release_name>'
```

Use this rollback only for release regression. Do not rollback merely because the smoke exposes a pending invoice data freshness issue.

## Step 3 - Bounded Pending Invoice Enqueue-To-Fresh Smoke

Command:

```bash
ssh finops-prod-root 'set -eu
release_name=dev-pending-invoice-source-17d13466-20260625
release_src="/opt/fin-ops/releases/${release_name}/src"
test -d "$release_src/backend/src"
set -a
source /etc/fin-ops/fin-ops.common.env
source /etc/fin-ops/fin-ops.secrets.env
set +a
cd "$release_src"
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python \
  -m fin_ops_platform.tools.read_model_slo_smoke \
  --json \
  --apply \
  --read-model-key pending_invoice \
  --scope pending_invoice=expense:all \
  --reason row277_pending_invoice_source_version_contract \
  --priority high \
  --trace-id row277-pending-invoice-source-version-contract \
  --target-ms 5000 \
  --timeout-seconds 180 \
  --poll-interval-seconds 0.5
'
```

Expected evidence:

- planned scope count is `1`;
- planned scope is `pending_invoice / expense:all`;
- result status is `pass`, or if it fails the failure is precise and bounded to the selected event/scope.

Mutation and rollback characteristics:

- This command writes one normal durable queue refresh request through `ReadModelRefreshGateway`.
- The worker may rebuild the matching pending invoice month shards and update read-model projection rows for those scopes.
- It does not write canonical facts, App Status manually, readiness manually, no-OA data or arbitrary SQL.
- Read-model projection rebuild is recoverable by rerunning the same gateway-backed refresh after fixing any discovered issue.
- Do not manually mark dirty scopes done or delete outbox rows as rollback.

## Step 4 - Sanitized Pending Invoice Metadata Probe

Command:

```bash
ssh finops-prod-root 'set -eu
release_name=dev-pending-invoice-source-17d13466-20260625
release_src="/opt/fin-ops/releases/${release_name}/src"
set -a
source /etc/fin-ops/fin-ops.common.env
source /etc/fin-ops/fin-ops.secrets.env
set +a
cd "$release_src"
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python - <<'"'"'PY'"'"'
import hashlib
import json

from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter
from fin_ops_platform.services.pending_invoice_read_model_repository import PendingInvoiceReadModelRepositoryPort
from fin_ops_platform.services.pending_invoice_read_model_service import (
    PendingInvoiceReadModelService,
    PendingInvoiceSourceVersionsProvider,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.read_model_freshness import source_version_mismatch_reasons
from fin_ops_platform.services.search_pending_sql_projection import _settings_payload


def digest(payload):
    encoded = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


connection = PostgresConnection(PostgresSettings.from_env())
broad_repo = PostgresReadModelRepository(connection)
repo = PendingInvoiceReadModelRepositoryPort(broad_repo)
provider = PendingInvoiceSourceVersionsProvider(
    settings_provider=lambda: _settings_payload(connection),
    attachment_invoice_parser_version_provider=MongoOAAdapter._attachment_invoice_cache_parser_version,
    oa_projection_sync_version_provider=lambda: OA_PROJECTION_SYNC_VERSION,
    repository=repo,
)
service = PendingInvoiceReadModelService(
    repository=repo,
    queue_repository=None,
    settings_provider=lambda: _settings_payload(connection),
    source_versions_provider=provider,
)
query = {"direction": ["expense"], "filter": ["all"], "page": ["1"], "page_size": ["1"]}
rows_payload = service.rows(query)
options_payload = service.filter_options({"direction": ["expense"], "filter": ["all"]})
expected = service.expected_source_versions(query=query, payload=rows_payload)
actual = rows_payload.get("source_versions") if isinstance(rows_payload.get("source_versions"), dict) else {}
summary = {
    "rows_status": rows_payload.get("read_model_status"),
    "rows_scope": rows_payload.get("read_model_scope_key"),
    "rows_total": (rows_payload.get("pagination") or {}).get("total"),
    "rows_returned_count": len(rows_payload.get("rows") or []),
    "filter_options_status": options_payload.get("read_model_status"),
    "filter_options_scope": options_payload.get("read_model_scope_key"),
    "expected_key_count": len(expected),
    "actual_key_count": len(actual),
    "expected_hash": digest(expected),
    "actual_hash": digest(actual),
    "stale_reasons": source_version_mismatch_reasons(expected=expected, actual=actual),
    "actual_keys": sorted(actual),
}
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
PY
'
```

Expected evidence:

- `rows_status == "fresh"`;
- `filter_options_status == "fresh"`;
- `rows_scope == "expense:all"`;
- `stale_reasons == []`;
- `actual_keys` includes `invoice_lifecycle_policy_schema_version`, `bank_detail_source_versions` and `workbench_relation_source_versions`;
- no payload rows, invoice ids, counterparties, project names, account names, tokens or env values are printed.

Rollback/cleanup: none. The service is constructed with `queue_repository=None`, so the metadata probe cannot enqueue a refresh even if the payload is stale.

## Step 5 - Post-Check

Command:

```bash
ssh finops-prod-root 'set -eu
curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready \
  | /opt/fin-ops/venv/bin/python -c '"'"'import json,sys; p=json.load(sys.stdin); print({"status":p.get("status"),"release":p.get("release"),"read_model_refresh_failure_rate":p.get("read_model_refresh_failure_rate")})'"'"'
set -a
source /etc/fin-ops/fin-ops.common.env
source /etc/fin-ops/fin-ops.secrets.env
set +a
release_src="/opt/fin-ops/releases/dev-pending-invoice-source-17d13466-20260625/src"
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python - <<'"'"'PY'"'"'
import json
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings

connection = PostgresConnection(PostgresSettings.from_env())
report = {}
report["pending_invoice_dirty_status"] = connection.fetch_all(
    """
    select status, count(*)::int as count
    from job.read_model_dirty_scopes
    where scope_type = 'pending_invoice'
      and (scope_key = 'expense:all' or scope_key like 'expense:all:%')
    group by status
    order by status
    """
)
report["pending_invoice_recent_events"] = connection.fetch_all(
    """
    select status, count(*)::int as count
    from job.outbox_events
    where event_type = 'pending_invoice.read_model.refresh'
      and created_at >= now() - interval '30 minutes'
      and (scope_key = 'expense:all' or scope_key like 'expense:all:%')
    group by status
    order by status
    """
)
report["pending_invoice_readiness"] = connection.fetch_all(
    """
    select status, count(*)::int as count
    from read_model.app_status_readiness
    where read_model_key = 'pending_invoice'
    group by status
    order by status
    """
)
print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
PY
'
```

Expected evidence:

- `/health/ready` remains ready;
- selected pending invoice dirty scopes are `done` only, or any non-done status is explicitly explained by the smoke output;
- recent selected pending invoice outbox events are `done`;
- pending invoice readiness is fresh.

Rollback/cleanup: none for successful convergence. If post-check fails because the new release regressed health, use the release rollback command from Step 2.

## Evidence To Record After Execution

After running this runbook, update this file with:

- actual precheck release and commit;
- deploy command outcome and release identity;
- smoke JSON summary;
- metadata probe JSON;
- post-check summary;
- whether rollback was needed;
- final status proposal for `MODULE-QUEUE.md`.
