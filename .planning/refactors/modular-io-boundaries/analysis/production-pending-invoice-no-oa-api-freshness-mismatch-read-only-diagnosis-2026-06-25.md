# Production Pending Invoice No-OA API Freshness Mismatch Read-Only Diagnosis - 2026-06-25

**Boundary:** `production:pending-invoice-no-oa-api-freshness-mismatch-read-only-diagnosis`
**Status:** `production-diagnosis-closed`
**Module closure:** `not-module-closed`
**Production mutation:** forbidden
**Worker threads created:** none
**Next boundary:** `production:pending-invoice-no-oa-source-version-contract-deep-diagnosis`

## Goal

Diagnose, with read-only production evidence only, why Row273's user-scope API metadata probe still reported:

- `pending_invoices_rows`: HTTP `200`, `read_model_status=refreshing`, no refresh enqueue;
- `pending_invoices_filter_options`: HTTP `202`, `read_model_status=refreshing`, no refresh enqueue;
- `no_oa_bank_batches`: HTTP `200`, `read_model_status=stale`, refresh enqueued.

This boundary must not mutate production, must not print secrets or payload rows, and must not claim module/global closure.

## Inputs Reviewed

- `analysis/production-read-model-controlled-production-api-browser-runbook-2026-06-25.md`
- `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
- `backend/src/fin_ops_platform/tools/http_slo_probe.py`
- `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
- `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
- `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/services/read_model_freshness.py`
- `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `docs/modules/pending-invoices/README.md`
- `docs/modules/no-oa-bank-batches/README.md`
- `docs/modules/pending-invoices/tests.md`
- `docs/modules/no-oa-bank-batches/tests.md`

## Contract Facts From Code

Pending invoice:

- `PendingInvoiceApiRoutes.rows(...)` returns HTTP `200` for `refreshing` when rows are present; it returns HTTP `202` only when the payload is `refreshing` and has no rows.
- `PendingInvoiceApiRoutes.filter_options(...)` calls `PendingInvoiceReadModelService.filter_options(...)`; if its gate payload is not `fresh`, the route returns HTTP `202`.
- `PendingInvoiceReadModelService.rows(...)` returns `refreshing` without enqueueing when repository `refresh_status` is already not `fresh`.
- It can also return `refreshing` after a source-version mismatch; in that path it calls `enqueue_refreshes_for_scope(...)`, but `ReadModelRefreshGateway` can coalesce API-triggered refresh when an active refresh already exists, so a sanitized API report can show no new refresh enqueue even though the stale gate fired.
- The Row273 query was `/api/pending-invoices/rows?direction=expense&page=1&page_size=50&sort_field=trade_date&sort_direction=desc`; the scope key is `expense:all`.

No-OA:

- `NoOaBankBatchApiRoutes.list_batches(...)` always maps `list_batches_payload(...)` to HTTP `200`.
- `NoOaBankBatchApplicationService.list_batches_payload(...)` returns `read_model_status=stale` when any returned read model row has source-version mismatches from `no_oa_bank_batch_stale_reasons(...)`.
- The no-OA read repository returns `None` only when read model rows are empty and readiness is not fresh; if rows exist, stale status is determined by application-level source-version comparison, not by App Status readiness alone.
- The Row273 query was `/api/no-oa-bank-batches?month=<current-month>&bucket=unsubmitted&page=1&page_size=200`; the read-model scope candidates are `<current-month>` and `all`.

## Allowed Operations

- `ssh finops-prod-root` with bounded commands.
- Public `/health/ready` summary.
- Sourcing deployed production env files with `set +x`, without printing env values.
- Initializing deployed `Application` only to access existing services/repositories/providers in process.
- Read-only repository calls and SQL metadata queries.
- Printing only sanitized status, counts, scope keys, source-version key names, mismatch reason names, and active refresh counts.

## Forbidden Operations

- Calling production API endpoints or service methods that may enqueue read-model refreshes.
- Deploy, restart, reload, requeue, repair, replay, worker drain, queue mutation, readiness mutation, direct SQL mutation, file mutation, browser actions or business writes.
- Printing env files, DSNs, passwords, usernames, bearer tokens, cookies, private keys, response bodies, payload rows, invoice numbers, project names, counterparties, bank account names, transaction ids or business-sensitive values.
- Selecting raw payload columns or row-level business values from production tables.

## Runbook Commands

### 1. Precheck: release and `/health/ready`

```bash
ssh finops-prod-root 'set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; echo "release_src=$release_src"; echo "git_commit=$(cat "$release_src/.git_commit" 2>/dev/null || git -C "$release_src" rev-parse HEAD 2>/dev/null || true)"; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
```

Stop if health is unavailable or not ready.

### 2. Read-only deployed-runtime freshness diagnosis

This command does not call API endpoints and does not call service methods that enqueue refreshes.

```bash
ssh finops-prod-root 'set +x; set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; set -a; [ -f /etc/fin-ops/fin-ops.common.env ] && . /etc/fin-ops/fin-ops.common.env; [ -f /etc/fin-ops/fin-ops.secrets.env ] && . /etc/fin-ops/fin-ops.secrets.env; set +a; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python - <<'"'"'PY'"'"'
import json
from datetime import datetime

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.pending_invoice_read_model_service import PendingInvoiceSourceVersionsProvider
from fin_ops_platform.services.read_model_freshness import source_version_mismatch_reasons


def compact_versions(value):
    if not isinstance(value, dict):
        return {"key_count": 0, "keys": []}
    return {"key_count": len(value), "keys": sorted(str(key) for key in value.keys())}


def active_refresh_count(conn, scope_type, scope_key):
    row = conn.fetch_one(
        """
        select count(*) as count
        from job.read_model_dirty_scopes
        where tenant_id = 'default'
          and scope_type = %s
          and scope_key = %s
          and status <> 'done'
        """,
        (scope_type, scope_key),
    )
    return int(row.get("count") or 0) if isinstance(row, dict) else 0


def dirty_rows(conn, scope_type, scope_keys):
    rows = conn.fetch_all(
        """
        select scope_type, scope_key, status, updated_at::text as updated_at
        from job.read_model_dirty_scopes
        where tenant_id = 'default'
          and scope_type = %s
          and scope_key = any(%s)
        order by scope_key
        """,
        (scope_type, list(scope_keys)),
    )
    return [
        {
            "scope_key": row.get("scope_key"),
            "status": row.get("status"),
            "updated_at": row.get("updated_at"),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def readiness_rows(conn, read_model_key, scope_type, scope_keys):
    rows = conn.fetch_all(
        """
        select read_model_key, scope_type, scope_key, status, updated_at::text as updated_at,
               source_versions
        from read_model.app_status_readiness
        where tenant_id = 'default'
          and read_model_key = %s
          and scope_type = %s
          and scope_key = any(%s)
        order by scope_key
        """,
        (read_model_key, scope_type, list(scope_keys)),
    )
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        result.append(
            {
                "scope_key": row.get("scope_key"),
                "status": row.get("status"),
                "updated_at": row.get("updated_at"),
                "source_versions": compact_versions(row.get("source_versions")),
            }
        )
    return result


def recent_outbox(conn, event_type, scope_type, scope_keys):
    rows = conn.fetch_all(
        """
        select status, coalesce(payload->>'scope_key', payload->>'scopeKey', '') as scope_key, count(*) as count,
               max(created_at)::text as latest_created_at, max(processed_at)::text as latest_processed_at
        from job.outbox_events
        where event_type = %s
          and created_at >= now() - interval '30 minutes'
          and coalesce(payload->>'scope_type', payload->>'scopeType', %s) = %s
          and coalesce(payload->>'scope_key', payload->>'scopeKey', '') = any(%s)
        group by status, coalesce(payload->>'scope_key', payload->>'scopeKey', '')
        order by scope_key, status
        """,
        (event_type, scope_type, scope_type, list(scope_keys)),
    )
    return [
        {
            "scope_key": row.get("scope_key"),
            "status": row.get("status"),
            "count": int(row.get("count") or 0),
            "latest_created_at": row.get("latest_created_at"),
            "latest_processed_at": row.get("latest_processed_at"),
        }
        for row in rows
        if isinstance(row, dict)
    ]


app = Application()
repo = getattr(app, "_pending_invoice_sql_read_repository", None)
conn = getattr(getattr(app, "_state_store", None), "_connection", None)
settings_service = getattr(app, "_app_settings_service", None)
get_settings_payload = getattr(settings_service, "get_settings_payload", None)
settings_provider = get_settings_payload if callable(get_settings_payload) else (lambda: {})
pending_provider = PendingInvoiceSourceVersionsProvider(
    settings_provider=settings_provider,
    attachment_invoice_parser_version_provider=app._current_oa_attachment_invoice_parser_version,
    oa_projection_sync_version_provider=app._current_oa_projection_sync_version,
    repository=repo,
)

pending_query = {
    "direction": ["expense"],
    "page": ["1"],
    "page_size": ["50"],
    "sort_field": ["trade_date"],
    "sort_direction": ["desc"],
}
pending_payload = repo.list_pending_invoice_rows(
    direction="expense",
    filter="all",
    page=1,
    page_size=50,
    sort_field="trade_date",
    sort_direction="desc",
)
pending_expected = pending_provider(query=pending_query, payload=pending_payload if isinstance(pending_payload, dict) else {})
pending_actual = pending_payload.get("source_versions") if isinstance(pending_payload, dict) and isinstance(pending_payload.get("source_versions"), dict) else {}
pending_scope = "expense:all"
pending_section = {
    "scope_key": pending_scope,
    "repository_payload_present": isinstance(pending_payload, dict),
    "repository_refresh_status": pending_payload.get("refresh_status") if isinstance(pending_payload, dict) else None,
    "row_count": len(pending_payload.get("rows") or []) if isinstance(pending_payload, dict) else 0,
    "total": ((pending_payload.get("pagination") or {}).get("total") if isinstance(pending_payload, dict) and isinstance(pending_payload.get("pagination"), dict) else None),
    "expected_source_versions": compact_versions(pending_expected),
    "actual_source_versions": compact_versions(pending_actual),
    "mismatch_reasons": source_version_mismatch_reasons(expected=pending_expected, actual=pending_actual),
    "active_refresh_count": active_refresh_count(conn, "pending_invoice", pending_scope),
    "dirty_scopes": dirty_rows(conn, "pending_invoice", [pending_scope]),
    "readiness": readiness_rows(conn, "pending_invoice", "pending_invoice", [pending_scope]),
    "recent_outbox": recent_outbox(conn, "pending_invoice.read_model.refresh", "pending_invoice", [pending_scope]),
}

no_oa_service = app._no_oa_bank_batch_application_service()
no_oa_scope = datetime.now().strftime("%Y-%m")
no_oa_filters = {"month": no_oa_scope, "bucket": "unsubmitted"}
list_rows = getattr(no_oa_service._no_oa_bank_batch_read_model_repository, "list_no_oa_bank_batch_rows", None)
summary_rows = list_rows({"month": no_oa_scope}) if callable(list_rows) else None
filtered_rows = list_rows(no_oa_filters) if callable(list_rows) else None
sample_rows = []
for row in list(summary_rows or []) + list(filtered_rows or []):
    if isinstance(row, dict):
        sample_rows.append(row)
no_oa_expected = no_oa_service.no_oa_bank_batch_source_versions()
no_oa_reason_set = []
for row in sample_rows:
    reasons = source_version_mismatch_reasons(
        expected=no_oa_expected,
        actual=row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {},
    )
    for reason in reasons:
        if reason not in no_oa_reason_set:
            no_oa_reason_set.append(reason)
no_oa_section = {
    "scope_keys": [no_oa_scope, "all"],
    "repository_available": callable(list_rows),
    "summary_row_count": len(summary_rows or []) if isinstance(summary_rows, list) else None,
    "filtered_row_count": len(filtered_rows or []) if isinstance(filtered_rows, list) else None,
    "expected_source_versions": compact_versions(no_oa_expected),
    "sample_actual_source_version_key_sets": [
        compact_versions(row.get("source_versions"))
        for row in sample_rows[:5]
        if isinstance(row, dict)
    ],
    "mismatch_reasons": no_oa_reason_set,
    "active_refresh_counts": {
        no_oa_scope: active_refresh_count(conn, "no_oa_bank_batch", no_oa_scope),
        "all": active_refresh_count(conn, "no_oa_bank_batch", "all"),
    },
    "dirty_scopes": dirty_rows(conn, "no_oa_bank_batch", [no_oa_scope, "all"]),
    "readiness": readiness_rows(conn, "no_oa_bank_batch", "no_oa_bank_batch", [no_oa_scope, "all"]),
    "recent_outbox": recent_outbox(conn, "no_oa_bank_batch.read_model.refresh", "no_oa_bank_batch", [no_oa_scope, "all"]),
}

print(json.dumps(
    {
        "version": 1,
        "status": "ok",
        "mode": "read_only_freshness_mismatch_diagnosis",
        "pending_invoice": pending_section,
        "no_oa_bank_batch": no_oa_section,
    },
    ensure_ascii=False,
    indent=2,
    sort_keys=True,
))
PY'
```

Stop if the command would need to print raw rows/payloads/secrets or mutate production. If it fails due a table/column contract mismatch, record the failing contract and continue from code evidence instead of guessing.

### 3. Postcheck: `/health/ready`

Repeat command 1 after diagnosis to prove read-only probing did not disturb readiness.

## Expected Result Classes

- `production-diagnosis-closed`: read-only metadata identifies the mismatch causes and final health remains ready.
- `production-evidence-deferred`: metadata is insufficient without payload rows or mutation.
- `hard stop`: diagnosis requires secrets, payload rows, mutation, or guessed table contracts.

## Execution Results

### Precheck

Release and `/health/ready`:

```text
release_src=/opt/fin-ops/releases/dev-workbench-matching-port-20260625020818/src
git_commit=
{'status': 'ready'}
```

### Runbook Corrections

The first deployed-runtime script attempted to use `Application()` without a `data_dir`; in this shell context `Application()` correctly built no state store, so `_pending_invoice_sql_read_repository` was `None`. No business payload was printed.

The second correction used `PostgresStateStore(data_dir=default_data_dir(), connection=PostgresConnection(PostgresSettings.from_env()))`, but the import path was wrong (`fin_ops_platform.config.default_data_dir`). No business payload was printed.

The third correction used the correct import path but embedded `tenant_id='default'` as a SQL string literal inside the SSH shell here-doc; shell quoting stripped the literal quotes and PostgreSQL rejected the query. No business payload was printed.

The fourth correction parameterized the tenant/status literals and produced valid evidence, but printed unaggregated dirty-scope rows and the tool truncated output. The tail still contained the pending invoice diagnosis. T0 reran a bounded aggregate version for stable evidence.

### Read-Only Aggregate Diagnosis

The bounded aggregate command used direct PostgreSQL read repositories only. It did not call production API endpoints and did not call service methods that enqueue refreshes.

Pending invoice result for the Row273 probe scope `expense:all`:

```text
repository_refresh_status=fresh
row_count=50
total=683
active_refresh_count=0
dirty_summary: expense:all done count=551 latest_updated_at=2026-06-25 05:02:07.183806+08
readiness rows for expense:all: []
recent pending_invoice.read_model.refresh: done count=38 latest_created_at=2026-06-25 05:02:07.180933+08 latest_processed_at=2026-06-25 05:02:08.175592+08
```

Pending invoice expected source-version keys:

```text
bank_auto_tag_rules_version
bank_detail_source_versions
oa_attachment_invoice_parser_version
oa_projection_sync_version
pending_invoice_read_model_schema_version
pending_invoice_tag_groups_version
pending_output_invoice_tag_groups_version
workbench_relation_source_versions
```

Pending invoice actual source-version keys:

```text
bank_auto_tag_rules_version
bank_detail_source_versions
invoice_lifecycle_policy_schema_version
oa_attachment_invoice_parser_version
oa_projection_sync_version
pending_invoice_read_model_schema_version
pending_invoice_tag_groups_version
pending_output_invoice_tag_groups_version
workbench_relation_source_versions
```

Pending invoice mismatch reasons:

```text
bank_auto_tag_rules_version_mismatch
bank_detail_source_versions_mismatch
oa_projection_sync_version_mismatch
pending_invoice_read_model_schema_version_mismatch
pending_invoice_tag_groups_version_mismatch
```

Diagnosis:

- The SQL repository payload is present, has rows and reports `refresh_status=fresh`.
- `PendingInvoiceReadModelService.rows(...)` returns `read_model_status=refreshing` because the API expected-source gate detects source-version mismatches between the current code/settings/dependency versions and the stored `read_model.pending_invoice_scopes` source versions.
- `pending_invoices_rows` returned HTTP `200` in Row273 because route `_read_model_status_code(...)` maps `refreshing` plus non-empty rows to `200`.
- `pending_invoices_filter_options` returned HTTP `202` because `filter_options(...)` first gates through `rows(page_size=1)` and returns `202` for any non-fresh gate payload.
- No new refresh was enqueued on the focused retry because active refresh coalescing/just-completed refresh state left no active dirty rows by the read-only diagnosis; the remaining problem is not a stuck dirty scope but a repeated source-version mismatch after refresh completion.

No-OA result for Row273's current-month unsubmitted probe:

```text
scope_keys=[2026-06, all]
summary_row_count=8
filtered_row_count=8
active_refresh_counts: 2026-06=0, all=0
dirty_summary: 2026-06 done count=1 latest_updated_at=2026-06-19 00:45:40.128449+08
dirty_summary: all done count=28067 latest_updated_at=2026-06-25 05:02:09.049344+08
readiness: all fresh updated_at=2026-06-25 05:02:09.052821+08 source_versions keys=[source_version]
recent no_oa_bank_batch.read_model.refresh: done count=2 latest_created_at=2026-06-25 05:02:06.896836+08 latest_processed_at=2026-06-25 05:02:09.054545+08
```

No-OA row source-version key set for the 8 current-month rows:

```text
bank_auto_tag_rules_version
bank_detail_source_versions
bank_transaction_category_schema_version
bank_transaction_category_snapshot_version
no_oa_bank_batch_schema_version
no_oa_bank_batch_tag_selection_version
oa_attachment_invoice_parser_version
oa_projection_sync_version
pair_relation_snapshot_version
workbench_candidate_match_schema_version
workbench_exception_projection_version
workbench_exception_rules_version
workbench_matching_rules_version
workbench_read_model_schema_version
workbench_relation_source_versions
```

Supplemental hashed key evidence:

```text
readiness all source_version hash: 1fbfa652b37e
row_source_version_hash_sets: one key set across 8 rows with 15 hashed source-version entries
```

Diagnosis:

- `job.read_model_dirty_scopes`, `job.outbox_events` and `read_model.app_status_readiness` are clean for no-OA.
- App Status readiness stores a compact aggregate `source_version` for `no_oa_bank_batch:all`.
- `NoOaBankBatchApplicationService.list_batches_payload(...)` does not use only that readiness aggregate when rows exist; it calls `no_oa_bank_batch_stale_reasons(...)` across returned row payloads and compares row-level `source_versions` with current expected service source versions.
- Therefore Row273's `read_model_status=stale` despite clean readiness/outbox is explained by a stricter application-level row source-version gate, not by an active worker or readiness failure.
- Exact no-OA mismatch keys were not computed in this boundary because constructing the full application service expected-source provider without starting the production `Application` runtime would require a larger dependency assembly. The next boundary should perform that deeper read-only comparison or inspect the refresh writer contract.

### Postcheck

Final `/health/ready`:

```text
{'status': 'ready'}
```

No production API endpoint was called in Row274, and no production mutation was performed.

## Result

Decision: `production-diagnosis-closed`.

This boundary proved:

- pending invoice rows/filter-options failures are caused by API expected-source version mismatches even though the repository payload is `fresh` and populated;
- pending invoice HTTP `200` for rows and HTTP `202` for filter-options are expected route-level consequences of the same `refreshing` gate payload;
- no-OA stale is not caused by dirty/outbox/readiness blockers, because all were clean and no active refresh remained;
- no-OA API freshness is stricter than App Status readiness because it compares row-level source versions through application service logic;
- direct read-only production diagnostics can inspect the mismatch without printing payload rows or mutating production.

This boundary did not prove:

- the exact no-OA expected-vs-actual mismatch key/value pair;
- why completed pending invoice refreshes keep writing source versions that mismatch current API expected versions;
- any production browser/admin/write-after-read closure;
- module/global closure.

## Next Boundary Selection

Select `production:pending-invoice-no-oa-source-version-contract-deep-diagnosis`.

The next boundary should remain read-only and inspect writer/expected-source contracts for:

- pending invoice projection writer source versions vs `PendingInvoiceReadModelService` expected source versions;
- whether Row273-triggered refresh rebuilt the relevant base scope or only month/filter shards;
- exact no-OA expected-vs-row source-version mismatch keys without starting broad production runtime or printing business payloads;
- whether the next safe action should be a code contract fix, a bounded explicit-scope refresh/rebuild runbook, or a production-evidence defer.

## Docs Impact

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No long-term docs update yet. The diagnosis identifies production contract mismatch symptoms, but the durable implementation contract or remediation path is not yet established.

## Seven Test Categories

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business rule changed. |
| 2. Service-layer tests | Not applicable | No service/repository code changed. |
| 3. API contract tests | Applicable as production evidence | Diagnosed Row273 API status/freshness behavior through route/service/repository contracts and read-only production metadata. |
| 4. Read model/cache/background job tests | Applicable as production evidence | Collected dirty/readiness/outbox/source-version metadata for pending invoice and no-OA. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Deferred | No production write-after-read path was run. |
| 7. Existing feature regression tests | Applicable | `/health/ready` remained ready before and after; docs/diff verification still required before commit. |

## Verification

Executed before commit:

- `bash scripts/verify.sh docs` passed.
- `git diff --check` passed.
- Changed-file sensitive-term scan found only safety policy text and env file names; no secret values were printed or committed.
- `git diff --cached --check` must pass after staging.
