# Staging Load Test Baseline Report

- Gate: **NO_GO**
- Start time: `2026-05-17T02:05:20Z`
- End time: `2026-05-17T02:05:20Z`
- Target host: `not_configured`
- Execution mode: `validate_only`
- Requests sent: `0`
- Dataset scale: `not_configured`, months `[]`, bank rows `0`, invoice rows `0`, search rows `0`
- Request count: `0`
- Concurrency: `4`
- Error rate: `1.0`
- Latency P50/P95/P99 ms: `0.0/0.0/0.0`
- DB pool stats: unavailable; staging run did not start
- NATS/outbox backlog: unavailable; staging run did not start
- Worker lag seconds: unavailable; staging run did not start
- Read model stale seconds: unavailable; staging run did not start

## Scenario Matrix

| Scenario | Method | Path | Source | Target P95 ms | Requests | P50 | P95 | P99 | Error Rate | Gate |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `healthz` | `GET` | `/healthz` | `static_health` | 20 | 0 | 0.0 | 0.0 | 0.0 | 1.0 | `NO_GO` |
| `readyz` | `GET` | `/readyz` | `dependency_health` | 80 | 0 | 0.0 | 0.0 | 0.0 | 1.0 | `NO_GO` |
| `workbench_month_read_model` | `GET` | `/api/workbench?month={month}` | `read_model` | 800 | 0 | 0.0 | 0.0 | 0.0 | 1.0 | `NO_GO` |
| `search` | `GET` | `/api/search?q={search_query}` | `read_model` | 500 | 0 | 0.0 | 0.0 | 0.0 | 1.0 | `NO_GO` |
| `task_status` | `GET` | `/api/background-jobs/{task_id}` | `job_status` | 300 | 0 | 0.0 | 0.0 | 0.0 | 1.0 | `NO_GO` |
| `import_metadata` | `GET` | `/imports/files/{import_file_id}` | `postgres_facts` | 300 | 0 | 0.0 | 0.0 | 0.0 | 1.0 | `NO_GO` |
| `cost_read_model` | `GET` | `/api/cost-statistics?month={month}` | `read_model` | 800 | 0 | 0.0 | 0.0 | 0.0 | 1.0 | `NO_GO` |
| `tax_read_model` | `GET` | `/api/tax-offset?month={month}` | `read_model` | 800 | 0 | 0.0 | 0.0 | 0.0 | 1.0 | `NO_GO` |

## Configuration Validation

`python3 scripts/tools/backend_refactor_load_test.py --validate-only` failed before sending any requests:

- missing required environment variable: `FIN_OPS_STAGING_BASE_URL`
- missing required environment variable: `FIN_OPS_STAGING_AUTH_TOKEN`
- missing required environment variable: `FIN_OPS_LOAD_TEST_MONTH`
- missing required environment variable: `FIN_OPS_LOAD_TEST_SEARCH_QUERY`
- missing required environment variable: `FIN_OPS_LOAD_TEST_TASK_ID`
- missing required environment variable: `FIN_OPS_LOAD_TEST_IMPORT_FILE_ID`
- missing required environment variable: `FIN_OPS_LOAD_TEST_DATASET_LABEL`
- missing required environment variable: `FIN_OPS_LOAD_TEST_BANK_TRANSACTION_ROWS`
- missing required environment variable: `FIN_OPS_LOAD_TEST_INVOICE_ROWS`
- missing required environment variable: `FIN_OPS_LOAD_TEST_SEARCH_ROWS`

The tool reported `No requests were sent.`

## Decision

GO/NO_GO: `NO_GO`

Rationale:

- No staging URL or staging auth token was configured through environment variables.
- No staging sample month, search query, task id, import file id, or dataset scale was configured.
- No load requests were sent, so no scenario produced P50/P95/P99, error-rate, DB pool, NATS/outbox backlog, worker lag, or read model stale measurements.
- This result avoids production load, OA source database access, traffic switching, and accidental writes outside staging.
