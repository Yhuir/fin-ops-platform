# API Shadow Validation Report Template

- Report: `api-shadow-validation-report-YYYYMMDD`
- Gate: `GO` / `NO_GO`
- Python base URL: `http://127.0.0.1:8001`
- Axum base URL: `http://127.0.0.1:8002`
- Fixture: `docs/dev/api-fixtures/business-api-shadow-validation.json`
- Generated JSON: `api-shadow-validation-report-YYYYMMDD.json`
- JSON template: `docs/dev/api-shadow-validation-report-template.json`
- Readiness evidence path: `docs/operations/backend-refactor/api-shadow-validation-report-YYYYMMDD.{json,md}`

## Gate Rule

The readiness gate is `NO_GO` when any endpoint misses its `expected_status` or has an unexplained status, field, sorting, money-format, date-format, error-shape, or value diff. A diff is explained only when it is explicitly listed in the endpoint fixture `explain_diffs`. Each generated endpoint result carries the fixture `source` statement so reviewers can verify the route is backed by PostgreSQL facts, read models, jobs/outbox, object storage, static contracts, transactional workbench writes, or OA identity rather than app Mongo state.

Endpoint `source` text is machine-checked by both the validator and readiness gate. It must name at least one allowed source family (`PostgreSQL`, `read_model`, `job/outbox`, object storage, static contract, transactional workbench write, or OA identity). The generated JSON also emits `results[].source_categories` using the canonical values `postgres_facts`, `read_model`, `job_outbox`, `object_storage`, `static_contract`, `transactional_workbench_write`, and `oa_identity`. `app Mongo` may appear only in a negative statement such as `no app Mongo read`; using app Mongo as an active source keeps the report at `NO_GO`.

For each endpoint case, the validator sends the Python and Axum requests concurrently so time-sensitive job/read-model responses are sampled from the same validation window.

The runtime shadow command validates `business-api-shadow-validation.json` before sending any HTTP request. If required endpoint fields or `contract_cases` are missing, the generated report is `NO_GO`, `fixture_validation.status` is `NO_GO`, `summary.fixture_error_count` is greater than zero, and the result list contains `fixture_validation` rows instead of live endpoint comparisons.

Fixture validation also checks that every key used in an endpoint sample `query` is listed in `contract_cases.query`, and that any endpoint sample `body` has a non-null `contract_cases.body` description. This prevents local/staging samples from drifting away from the documented contract cases.

`scripts/tools/backend_refactor_readiness_gate.py` ignores `*-template` files and only accepts generated evidence under `docs/operations/backend-refactor/`. The API shadow gate requires a matching `api-shadow-validation-report-YYYYMMDD.json` and `api-shadow-validation-report-YYYYMMDD.md` pair; JSON-only or Markdown-only evidence is `NO_GO`. For JSON reports, top-level `status`, `fixture_validation.status`, `fixture_validation.endpoint_count`, `fixture_validation.endpoint_ids`, `fixture_validation.permission_failure_endpoint_ids`, `summary.total`, `summary.go`, `summary.no_go`, `summary.unexpected_diff_count`, `summary.permission_failure_cases`, `summary.permission_failure_required_count`, `summary.permission_failure_missing_count`, `summary.fixture_error_count`, and every endpoint `results[].status/unexpected_diff_count/source/source_categories` must prove a non-empty all-`GO` full-fixture run. The gate rejects scoped or ambiguous evidence: `filters` must be present, `filters.endpoint_ids` and `filters.risks` must both be arrays, and both arrays must be empty. The unique primary endpoint IDs must exactly match `fixture_validation.endpoint_ids`, every required permission failure ID must have a matching `endpoint_id#permission_failure` result, `summary.permission_failure_cases` must equal the actual permission-failure result count, `summary.permission_failure_required_count` must equal the number of required IDs, and `summary.permission_failure_missing_count` must be `0`. Empty results, missing counters, mismatched counters, partial fixture coverage, invented endpoint IDs, missing permission-failure cases, missing filter metadata, any fixture error, any unexplained diff, missing endpoint source/categories, or any `NO_GO` endpoint keeps the API shadow gate blocked. For the paired Markdown report, the generated `Gate: **GO**` marker is required and `Gate: **NO_GO**` is blocking.

Fixture `defaults.headers` are applied to every endpoint and may use `${ENV_VAR}` placeholders for local/staging tokens. Endpoint `path`, `query`, and JSON `body` also support `${ENV_VAR}` placeholders; path variable values such as project names must be URL encoded before running shadow validation. Reports must not include request header values.

`--endpoint-id` and `--risk` may be repeated to run a scoped subset without editing the fixture. The report records selected filters, and an empty selection is `NO_GO`. Scoped reports are useful during investigation but are not accepted as final readiness evidence; the readiness gate only accepts an unfiltered full-fixture run.

When `--include-permission-failures` is set, the validator also runs each endpoint whose `contract_cases.permission_failure` is not `not applicable` with `defaults.permission_failure.request_headers` or endpoint-level `permission_failure.request_headers`. Fixture validation fails before any HTTP request if a required permission-failure case has no `request_headers` object in either place, because the tool would otherwise be unable to construct the downgraded or missing-session request. These cases are reported as `endpoint_id#permission_failure` and must satisfy their own `expected_status`; final readiness evidence must include them for every ID listed in `fixture_validation.permission_failure_endpoint_ids`. An unfiltered full-fixture run that omits `--include-permission-failures` is `NO_GO` when any permission-failure IDs are required; scoped `--endpoint-id` or `--risk` runs may omit them for diagnostics, but those scoped reports are not readiness evidence.

For any 4xx response, the validator checks the JSON body against the active `contract_cases.error_shape`. Shape values such as `"string"`, `"number"`, and `"boolean"` are treated as type assertions; any other non-null value is treated as an exact expected value. Permission-failure cases may override that shape with `defaults.permission_failure.error_shape` or endpoint-level `permission_failure.error_shape`.

For SSE endpoints, set `response_mode: "sse_first_events"` and list expected event names in `contract_cases.sse_events`. The validator samples only those first events, normalizes them under `_sse_events[]`, then closes the stream so infinite streams remain suitable for GO/NO_GO evidence.

Diff values under sensitive-looking fields such as token, password, secret, credential, cookie, authorization, URL/presigned URL, raw file/content, non-JSON body, stack, or traceback paths are emitted as `[REDACTED]`. The diff still counts toward `GO`/`NO_GO`; redaction only prevents report evidence from carrying secrets, access URLs, or raw payload content.

Write-route shadow samples such as no-OA submit/withdraw must run only against isolated local/staging data with disposable fixture IDs and idempotency keys. Do not run write-route shadow validation against production or against shared staging data without a reset plan.

Before sending HTTP requests, run:

```bash
python scripts/tools/api_shadow_validate.py \
  --fixture docs/dev/api-fixtures/business-api-shadow-validation.json \
  --validate-fixture-only
```

## Summary

| Metric | Value |
| --- | --- |
| Total endpoints |  |
| GO |  |
| NO_GO |  |
| Unexpected diffs |  |
| Permission failure cases |  |
| Fixture validation errors |  |
| Endpoint filters |  |
| Risk filters |  |

## Endpoint Results

| Endpoint | Method | Risk | Owner | Source | Gate | Unexpected diffs | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/app-health` | GET | medium | platform-ops |  |  |  |  |
| `/api/app-health/stream` | GET | medium | platform-ops |  |  |  |  |
| `/api/bank-details/accounts` | GET | high | finance-ops |  |  |  |  |
| `/api/bank-details/transactions` | GET | high | finance-ops |  |  |  |  |
| `/api/app-metadata` | GET | low | platform-ops |  |  |  |  |
| `/api/session/me` | GET | medium | platform-ops |  |  |  |  |
| `/api/search` | GET | medium | platform-ops |  |  |  |  |
| `/api/tasks/{task_id}/status` | GET | medium | platform-ops |  |  |  |  |
| `/api/no-oa-bank-batches` | GET | high | finance-ops |  |  |  |  |
| `/api/no-oa-bank-batches/{batch_id}` | GET | high | finance-ops |  |  |  |  |
| `/api/no-oa-bank-batches/{batch_id}/submit` | POST | high | finance-ops |  |  |  |  |
| `/api/no-oa-bank-batches/{batch_id}/withdraw` | POST | high | finance-ops |  |  |  |  |
| `/api/no-oa-bank-batches/submit` | POST | high | finance-ops |  |  |  |  |
| `/api/turnover-ledger` flat | GET | high | finance-ops |  |  |  |  |
| `/api/turnover-ledger` grouped | GET | high | finance-ops |  |  |  |  |
| `/api/turnover-ledger/export-preview` | GET | high | finance-ops |  |  |  |  |
| `/api/turnover-ledger/relations/{relation_id}` | GET | high | finance-ops |  |  |  |  |
| `/api/tax-offset` | GET | medium | tax-ops |  |  |  |  |
| `/api/tax-offset/calculate` | POST | medium | tax-ops |  |  |  |  |
| `/api/tax-offset/certified-imports` | GET | medium | tax-ops |  |  |  |  |
| `/api/etc/import` | POST | medium | tax-ops |  |  |  |  |
| `/api/etc/invoices` | GET | high | tax-ops |  |  |  |  |
| `/api/etc/batches` | GET | high | tax-ops |  |  |  |  |
| `/api/etc/batches/{batch_id}` | GET | high | tax-ops |  |  |  |  |
| `/api/cost-statistics` | GET | medium | cost-ops |  |  |  |  |
| `/api/cost-statistics/explorer` | GET | medium | cost-ops |  |  |  |  |
| `/api/cost-statistics/export-preview` | GET | medium | cost-ops |  |  |  |  |
| `/api/cost-statistics/projects/{project_name}` | GET | medium | cost-ops |  |  |  |  |
| `/api/cost-statistics/transactions/{transaction_id}` | GET | medium | cost-ops |  |  |  |  |
| `/api/workbench` | GET | high | finance-ops |  |  |  |  |
| `/api/workbench/ignored` | GET | high | finance-ops |  |  |  |  |
| `/api/workbench/read-model/status` | GET | high | finance-ops |  |  |  |  |
| `/api/workbench/rows/{row_id}` | GET | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/confirm-link` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/confirm-link/preview` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/cancel-link` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/withdraw-link/preview` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/withdraw-link` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/mark-exception` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/update-bank-exception` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/oa-bank-exception` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/confirm-personal-advance-repayment` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/confirm-cash-pass-through` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/confirm-cash-ticket-purchase` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/cancel-cash-special` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/exception/apply` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/cancel-exception` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/ignore-row` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/actions/unignore-row` | POST | high | finance-ops |  |  |  |  |
| `/api/workbench/settings` | GET | high | platform-ops |  |  |  |  |
| `/api/background-jobs/active` | GET | medium | platform-ops |  |  |  |  |
| `/api/background-jobs/{job_id}` | GET | medium | platform-ops |  |  |  |  |
| `/imports/templates` | GET | medium | platform-ops |  |  |  |  |
| `/imports/batches` | GET | medium | platform-ops |  |  |  |  |
| `/imports/batches/{batch_id}` | GET | medium | platform-ops |  |  |  |  |
| `/imports/files/{file_id}` | GET | medium | platform-ops |  |  |  |  |
| `/api/files/objects/{file_object_id}` | GET | medium | platform-ops |  |  |  |  |
| `/imports/files/upload-preflight` | POST | medium | platform-ops |  |  |  |  |
| `/api/workbench/settings/data-reset/jobs/active` | GET | high | platform-ops |  |  |  |  |
| `/api/workbench/settings/data-reset/jobs/{job_id}` | GET | high | platform-ops |  |  |  |  |
| `/api/oa-sync/status` | GET | medium | platform-ops |  |  |  |  |

## Diff Details

The generated Markdown report includes every unexpected diff from the JSON report:

| Endpoint | Case | Kind | Path | Python | Axum |
| --- | --- | --- | --- | --- | --- |

## Explained Diffs

The generated Markdown report also lists fixture-explained diffs so reviewers can confirm they are intentional and still acceptable:

| Endpoint | Case | Kind | Path | Python | Axum |
| --- | --- | --- | --- | --- | --- |

## Required Evidence

- `cargo test` result:
- `PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py -q` result:
- Shadow command:

```bash
python scripts/tools/api_shadow_validate.py \
  --python-base-url http://127.0.0.1:8001 \
  --axum-base-url http://127.0.0.1:8002 \
  --fixture docs/dev/api-fixtures/business-api-shadow-validation.json \
  --output-dir docs/operations/backend-refactor \
  --include-permission-failures
```

Scoped high-risk run example:

```bash
python scripts/tools/api_shadow_validate.py \
  --python-base-url http://127.0.0.1:8001 \
  --axum-base-url http://127.0.0.1:8002 \
  --fixture docs/dev/api-fixtures/business-api-shadow-validation.json \
  --output-dir docs/operations/backend-refactor \
  --risk high \
  --include-permission-failures
```

## NO_GO Follow-Up

For every unexpected diff, record:

| Endpoint | Diff kind | JSON path | Python value | Axum value | Decision |
| --- | --- | --- | --- | --- | --- |
