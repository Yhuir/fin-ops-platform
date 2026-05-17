# p0-platform-shadow-preflight-20260517

- Status: `GO`
- Generated at: `2026-05-17T11:33:34Z`
- Fixture: `/Users/yu/Desktop/fin-ops-platform/docs/dev/api-fixtures/business-api-shadow-validation.json`
- Platform endpoint count: `16`

## Inputs

| Item | Value |
| --- | --- |
| `python_base_url_present` | `True` |
| `axum_base_url_present` | `True` |
| `database_url_env` | `DATABASE_URL` |
| `database_url_present` | `True` |
| `target_postgres_major_min` | `16` |

## Checks

| Check | Status | Detail |
| --- | --- | --- |
| fixture_validation | `GO` | endpoint_count=16 |
| `python_readiness_check` | `GO` | `{\n  "service": "fin-ops-platform-api",\n  "version": "0.1.0",\n  "status": "ready",\n  "entrypoints": [\n    "/health",\n    "/foundation/seed",\n    "/imports/preview",\n    "/imports/confirm",\n    "/imports/templa...` |
| `psql_version` | `GO` | `psql (PostgreSQL) 17.10 (Homebrew)` |
| `postgres_major_detected` | `observed` | `17` |
| `local_postgres_server` | `GO` | `` |
| `docker_info` | `GO` | `28.5.1` |
| `cargo_sqlx_version` | `NO_GO` | `error: no such command: \`sqlx\`\n\nhelp: a command with a similar name exists: \`fix\`\n\nhelp: view all installed commands with \`cargo --list\`\nhelp: find a package to install \`sqlx\` with \`cargo search cargo-sq...` |

## Fixture Static Checks

- Status: `GO`
- Conflicts: `0`

| Kind | Value | Endpoints | Message |
| --- | --- | --- | --- |
| `none` | `` |  | No static write-order conflicts detected. |

## Runtime Variables

- Status: `GO`
- Required variables: `11`
- Missing variables: `0`

| Variable | Present | Classification | Used by |
| --- | --- | --- | --- |
| `BACKGROUND_JOB_ID` | `True` | `fixture_fact_id` | background-job-acknowledge-request |
| `BANK_TRANSACTION_ID` | `True` | `fixture_fact_id` | project-assign-request |
| `FIN_OPS_SHADOW_OA_DISPLAY_NAME` | `True` | `runtime_parameter` | background-job-acknowledge-request, ledger-detail, ledger-status-update, ledgers-list, project-assign-request, project-detail, projects-create-manual-profile, projects-hub-list, reminder-run-request, reminders-list, s... |
| `FIN_OPS_SHADOW_OA_PASSWORD` | `True` | `auth_secret` | settings-data-reset-create-job, settings-data-reset-direct-queues-job |
| `FIN_OPS_SHADOW_OA_TOKEN` | `True` | `auth_secret` | background-job-acknowledge-request, ledger-detail, ledger-status-update, ledgers-list, project-assign-request, project-detail, projects-create-manual-profile, projects-hub-list, reminder-run-request, reminders-list, s... |
| `FIN_OPS_SHADOW_OA_USERNAME` | `True` | `runtime_parameter` | background-job-acknowledge-request, ledger-detail, ledger-status-update, ledgers-list, project-assign-request, project-detail, projects-create-manual-profile, projects-hub-list, reminder-run-request, reminders-list, s... |
| `FIN_OPS_SHADOW_OA_USER_ID` | `True` | `fixture_fact_id` | background-job-acknowledge-request, ledger-detail, ledger-status-update, ledgers-list, project-assign-request, project-detail, projects-create-manual-profile, projects-hub-list, reminder-run-request, reminders-list, s... |
| `LEDGER_ID` | `True` | `fixture_fact_id` | ledger-detail, ledger-status-update |
| `PROJECT_DELETE_ID` | `True` | `fixture_fact_id` | workbench-settings-project-delete-request |
| `PROJECT_ID` | `True` | `fixture_fact_id` | project-assign-request, project-detail |
| `SHADOW_RUN_ID` | `True` | `run_correlation` | background-job-acknowledge-request, ledger-status-update, project-assign-request, projects-create-manual-profile, reminder-run-request, settings-data-reset-create-job, settings-data-reset-direct-queues-job, workbench-... |

## Seed Requirements

- Status: `GO`
- Database URL present: `True`
- Failed probes: `0`
- Skipped probes: `6`

| Variable | Kind | Present | PostgreSQL fact | Probe status | Used by |
| --- | --- | --- | --- | --- | --- |
| `BACKGROUND_JOB_ID` | `postgres_fact_id` | `True` | `job.worker_tasks` | `GO` | background-job-acknowledge-request |
| `BANK_TRANSACTION_ID` | `postgres_fact_id` | `True` | `app.bank_transactions` | `GO` | project-assign-request |
| `FIN_OPS_SHADOW_OA_DISPLAY_NAME` | `runtime_parameter` | `True` | `None` | `SKIPPED_NOT_POSTGRES_FACT` | background-job-acknowledge-request, ledger-detail, ledger-status-update, ledgers-list, project-assign-request, project-detail, projects-create-manual-profile, projects-hub-list, reminder-run-request, reminders-list, s... |
| `FIN_OPS_SHADOW_OA_PASSWORD` | `auth_secret` | `True` | `None` | `SKIPPED_NOT_POSTGRES_FACT` | settings-data-reset-create-job, settings-data-reset-direct-queues-job |
| `FIN_OPS_SHADOW_OA_TOKEN` | `auth_secret` | `True` | `None` | `SKIPPED_NOT_POSTGRES_FACT` | background-job-acknowledge-request, ledger-detail, ledger-status-update, ledgers-list, project-assign-request, project-detail, projects-create-manual-profile, projects-hub-list, reminder-run-request, reminders-list, s... |
| `FIN_OPS_SHADOW_OA_USERNAME` | `runtime_parameter` | `True` | `None` | `SKIPPED_NOT_POSTGRES_FACT` | background-job-acknowledge-request, ledger-detail, ledger-status-update, ledgers-list, project-assign-request, project-detail, projects-create-manual-profile, projects-hub-list, reminder-run-request, reminders-list, s... |
| `FIN_OPS_SHADOW_OA_USER_ID` | `fixture_fact_id` | `True` | `None` | `SKIPPED_NOT_POSTGRES_FACT` | background-job-acknowledge-request, ledger-detail, ledger-status-update, ledgers-list, project-assign-request, project-detail, projects-create-manual-profile, projects-hub-list, reminder-run-request, reminders-list, s... |
| `LEDGER_ID` | `postgres_fact_id` | `True` | `app.ledgers` | `GO` | ledger-detail, ledger-status-update |
| `PROJECT_DELETE_ID` | `postgres_fact_id` | `True` | `app.project_profiles` | `GO` | workbench-settings-project-delete-request |
| `PROJECT_ID` | `postgres_fact_id` | `True` | `app.project_profiles` | `GO` | project-assign-request, project-detail |
| `SHADOW_RUN_ID` | `run_correlation` | `True` | `None` | `SKIPPED_NOT_POSTGRES_FACT` | background-job-acknowledge-request, ledger-status-update, project-assign-request, projects-create-manual-profile, reminder-run-request, settings-data-reset-create-job, settings-data-reset-direct-queues-job, workbench-... |

## Auth Requirements

- Status: `GO`
- Source: `Axum middleware/auth.rs and Python app/auth.py`

| Check | Status | Detail |
| --- | --- | --- |
| `PRIMARY_AUTH_HEADERS_PRESENT` | `GO` | `{"missing_headers": []}` |
| `PRIMARY_AUTH_TOKEN_VARIABLE_PRESENT` | `GO` | `{"header_uses_shadow_token": true, "required_variable": "FIN_OPS_SHADOW_OA_TOKEN"}` |
| `OA_IDENTITY_SOURCE_ACCEPTED` | `GO` | `{"accepted_values": ["production_oa_test_user", "staging_oa", "test_oa"], "description": "Production OA test user accepted by updated Prompt04 Prompt 2 criteria; business writes must still target isolated local/shadow...` |
| `AXUM_TRUSTED_PERMISSION_PRESENT` | `GO` | `{"configured_permissions": ["finops:app:view"], "required_permission": "finops:app:view"}` |
| `AXUM_ADMIN_USERNAME_PRESENT_FOR_ADMIN_ROUTES` | `GO` | `{"accepted_admin_usernames": ["YNSYLP005", "test"], "admin_route_count": 7, "trusted_username": "test"}` |
| `AXUM_TRUSTED_HEADERS_ADAPTER_CONFIRMED` | `GO` | `{"axum_base_url_present": true, "local_env_value": "trusted_headers", "remote_confirmation_env": "FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED", "remote_confirmation_value": "trusted_headers"}` |

## Local Runtime Diagnostics

- Status: `GO`
- Failed checks: `0`

| Check | Status | Purpose | Detail |
| --- | --- | --- | --- |
| `preflight_script` | `GO` | repeatable preflight report generation | `/Users/yu/Desktop/fin-ops-platform/scripts/tools/platform_shadow_preflight.py` |
| `runtime_script` | `GO` | health-gated runtime shadow execution | `/Users/yu/Desktop/fin-ops-platform/scripts/tools/platform_shadow_runtime.py` |
| `seed_script` | `GO` | deterministic PostgreSQL seed SQL and env exports | `/Users/yu/Desktop/fin-ops-platform/scripts/tools/platform_shadow_seed.py` |
| `legacy_seed_script` | `GO` | deterministic isolated legacy Python data-dir seed | `/Users/yu/Desktop/fin-ops-platform/scripts/tools/platform_shadow_legacy_seed.py` |
| `legacy_reload_script` | `GO` | token-gated reload of the isolated legacy Python shadow process after reseed | `/Users/yu/Desktop/fin-ops-platform/scripts/tools/platform_shadow_legacy_reload.py` |
| `reseed_hook` | `GO` | runtime before-group cleanup, PostgreSQL seed, legacy seed, and legacy reload orchestration | `/Users/yu/Desktop/fin-ops-platform/scripts/tools/platform_shadow_reseed_hook.py` |
| `shadow_validator` | `GO` | Python-vs-Axum runtime comparison | `/Users/yu/Desktop/fin-ops-platform/scripts/tools/api_shadow_validate.py` |
| `python_start_script` | `GO` | legacy Python shadow service startup | `/Users/yu/Desktop/fin-ops-platform/scripts/start-backend.sh` |
| `seed_output_command` | `GO` | generate deterministic seed SQL/env without applying to PostgreSQL | `python3 scripts/tools/platform_shadow_seed.py --run-id "$SHADOW_RUN_ID" --write-sql /tmp/p0-platform-shadow-seed.sql --write-env /tmp/p0-platform-shadow-env.sh` |
| `seed_output_artifacts` | `GO` | persist deterministic seed SQL/env/probe/report output for repeatable runtime shadow runs | `` |
| `health_probe_commands` | `GO` | probe legacy Python and Axum readiness before running shadow cases | `[{'name': 'python_health', 'url': '$FIN_OPS_SHADOW_PYTHON_BASE_URL/health', 'command': 'curl -fsS "$FIN_OPS_SHADOW_PYTHON_BASE_URL/health"'}, {'name': 'axum_healthz', 'url': '$FIN_OPS_SHADOW_AXUM_BASE_URL/healthz', 'c...` |
| `final_shadow_command` | `GO` | run all 16 platform endpoint primary and permission-failure cases | `python3 scripts/tools/api_shadow_validate.py --fixture /Users/yu/Desktop/fin-ops-platform/docs/dev/api-fixtures/business-api-shadow-validation.json --output-dir docs/operations/backend-refactor --include-permission-fa...` |

## Out Of Scope Dependencies

| Dependency | Status | Reason |
| --- | --- | --- |
| `NATS` | `OUT_OF_SCOPE_FOR_PROMPT_2` | Prompt 2 gates runtime shadow preflight, service health, fixture variables, and Python-vs-Axum API validation only; NATS/Worker replay remains a separate production readiness blocker. |

## Runtime Shadow Input Plan

- Status: `GO`

### Required Environment

| Variable | Status | Sensitive | Required for | Alternative |
| --- | --- | --- | --- | --- |
| `FIN_OPS_SHADOW_PYTHON_BASE_URL` | `GO` | `False` | legacy Python runtime shadow target and /health probe |  |
| `FIN_OPS_SHADOW_AXUM_BASE_URL` | `GO` | `False` | Axum runtime shadow target and /healthz /readyz probes |  |
| `DATABASE_URL` | `GO` | `True` | PostgreSQL 16/17 migration, seed apply, seed fact probes, and local Axum startup |  |
| `FIN_OPS_SHADOW_OA_TOKEN` | `GO` | `True` | legacy Python Authorization header and platform API auth parity |  |
| `FIN_OPS_SHADOW_OA_PASSWORD` | `GO` | `True` | settings data reset runtime samples |  |
| `FIN_OPS_SHADOW_OA_IDENTITY_SOURCE` | `GO` | `False` | audit of OA identity source used by runtime shadow |  |
| `FIN_OPS_OA_IDENTITY_ADAPTER` | `GO` | `False` | local Axum trusted-header identity resolution | FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED=trusted_headers |
| `FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED` | `GO` | `False` | managed Axum shadow service trusted-header attestation | FIN_OPS_OA_IDENTITY_ADAPTER=trusted_headers |
| `BACKGROUND_JOB_ID` | `GO` | `False` | background-job-acknowledge-request |  |
| `BANK_TRANSACTION_ID` | `GO` | `False` | project-assign-request |  |
| `LEDGER_ID` | `GO` | `False` | ledger-detail and ledger-status-update |  |
| `PROJECT_ID` | `GO` | `False` | project-detail and project-assign-request |  |
| `PROJECT_DELETE_ID` | `GO` | `False` | workbench-settings-project-delete-request |  |
| `SHADOW_RUN_ID` | `GO` | `False` | runtime write isolation, idempotency keys, and report correlation |  |

### Command Plan

| Step | Command |
| --- | --- |
| PostgreSQL migration | `for f in rust/fin-ops-api/migrations/000*.sql; do psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"; done` |
| Seed | `python3 scripts/tools/platform_shadow_seed.py --run-id "$SHADOW_RUN_ID" --actor-id "$FIN_OPS_SHADOW_OA_USERNAME" --user-id "$FIN_OPS_SHADOW_OA_USER_ID" --display-name "$FIN_OPS_SHADOW_OA_DISPLAY_NAME" --apply && pytho...` |
| Python service | `FIN_OPS_DEV_ALLOW_LOCAL_SESSION=0 FIN_OPS_TEST_DEFAULT_AUTH=0 FIN_OPS_BACKEND_PORT=8001 FIN_OPS_STORAGE_MODE=auto scripts/start-backend.sh` |
| Axum service | `cd rust/fin-ops-api && FIN_OPS_API_BIND_ADDR=127.0.0.1:8002 FIN_OPS_OA_IDENTITY_ADAPTER=trusted_headers cargo run -p fin-ops-api --bin fin-ops-api` |
| Final shadow validation | `python3 scripts/tools/api_shadow_validate.py --fixture /Users/yu/Desktop/fin-ops-platform/docs/dev/api-fixtures/business-api-shadow-validation.json --output-dir docs/operations/backend-refactor --include-permission-fa...` |

### Health Probe Commands

| Probe | URL | Command |
| --- | --- | --- |
| `python_health` | `$FIN_OPS_SHADOW_PYTHON_BASE_URL/health` | `curl -fsS "$FIN_OPS_SHADOW_PYTHON_BASE_URL/health"` |
| `axum_healthz` | `$FIN_OPS_SHADOW_AXUM_BASE_URL/healthz` | `curl -fsS "$FIN_OPS_SHADOW_AXUM_BASE_URL/healthz"` |
| `axum_readyz` | `$FIN_OPS_SHADOW_AXUM_BASE_URL/readyz` | `curl -fsS "$FIN_OPS_SHADOW_AXUM_BASE_URL/readyz"` |

### Environment Exports

| Variable | Status | Sensitive | Example | Required for |
| --- | --- | --- | --- | --- |
| `FIN_OPS_SHADOW_PYTHON_BASE_URL` | `GO` | `False` | `http://127.0.0.1:8001` | runtime shadow validator |
| `FIN_OPS_SHADOW_AXUM_BASE_URL` | `GO` | `False` | `http://127.0.0.1:8002` | runtime shadow validator |
| `DATABASE_URL` | `GO` | `True` | `postgres://fin_ops_api:[REDACTED]@127.0.0.1:5432/fin_ops_shadow` | local Axum service and PostgreSQL seed probes |
| `FIN_OPS_OA_IDENTITY_ADAPTER` | `GO` | `False` | `trusted_headers` | local Axum trusted-header identity resolution |
| `FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED` | `GO` | `False` | `trusted_headers` | managed/remote Axum shadow service auth-mode attestation |
| `FIN_OPS_SHADOW_OA_IDENTITY_SOURCE` | `GO` | `False` | `production_oa_test_user` | runtime shadow identity-source audit |
| `FIN_OPS_SHADOW_LEGACY_RELOAD_TOKEN` | `GO` | `True` | `generate with openssl rand -hex 24` | local legacy Python shadow reload after per-group reseed |
| `FIN_OPS_SHADOW_LEGACY_DATA_DIR` | `GO` | `False` | `/tmp/fin-ops-platform-shadow-legacy-$SHADOW_RUN_ID` | isolated legacy Python seed and reload source |
| `BACKGROUND_JOB_ID` | `GO` | `False` | `00000000-0000-0000-0000-000000000000` | background-job-acknowledge-request |
| `BANK_TRANSACTION_ID` | `GO` | `False` | `00000000-0000-0000-0000-000000000000` | project-assign-request |
| `FIN_OPS_SHADOW_OA_DISPLAY_NAME` | `GO` | `False` | `<FIN_OPS_SHADOW_OA_DISPLAY_NAME>` | background-job-acknowledge-request, ledger-detail, ledger-status-update, ledgers-list, project-assign-request, project-detail, projects-create-manual-profile, projects-hub-list, reminder-run-request, reminders-list, s... |
| `FIN_OPS_SHADOW_OA_PASSWORD` | `GO` | `True` | `[REDACTED-STAGING-RESET-PASSWORD]` | settings-data-reset-create-job, settings-data-reset-direct-queues-job |
| `FIN_OPS_SHADOW_OA_TOKEN` | `GO` | `True` | `[REDACTED-STAGING-OA-TOKEN]` | background-job-acknowledge-request, ledger-detail, ledger-status-update, ledgers-list, project-assign-request, project-detail, projects-create-manual-profile, projects-hub-list, reminder-run-request, reminders-list, s... |
| `FIN_OPS_SHADOW_OA_USERNAME` | `GO` | `False` | `<FIN_OPS_SHADOW_OA_USERNAME>` | background-job-acknowledge-request, ledger-detail, ledger-status-update, ledgers-list, project-assign-request, project-detail, projects-create-manual-profile, projects-hub-list, reminder-run-request, reminders-list, s... |
| `FIN_OPS_SHADOW_OA_USER_ID` | `GO` | `False` | `<FIN_OPS_SHADOW_OA_USER_ID>` | background-job-acknowledge-request, ledger-detail, ledger-status-update, ledgers-list, project-assign-request, project-detail, projects-create-manual-profile, projects-hub-list, reminder-run-request, reminders-list, s... |
| `LEDGER_ID` | `GO` | `False` | `00000000-0000-0000-0000-000000000000` | ledger-detail, ledger-status-update |
| `PROJECT_DELETE_ID` | `GO` | `False` | `00000000-0000-0000-0000-000000000000` | workbench-settings-project-delete-request |
| `PROJECT_ID` | `GO` | `False` | `00000000-0000-0000-0000-000000000000` | project-assign-request, project-detail |
| `SHADOW_RUN_ID` | `GO` | `False` | `p0-platform-20260517113334` | background-job-acknowledge-request, ledger-status-update, project-assign-request, projects-create-manual-profile, reminder-run-request, settings-data-reset-create-job, settings-data-reset-direct-queues-job, workbench-... |

### Service Start Order

| Step | Name | Command | Readiness |
| --- | --- | --- | --- |
| `1` | `legacy_python_shadow` | `FIN_OPS_DEV_ALLOW_LOCAL_SESSION=0 FIN_OPS_TEST_DEFAULT_AUTH=0 FIN_OPS_BACKEND_PORT=8001 FIN_OPS_STORAGE_MODE=auto scripts/start-backend.sh` | curl -fsS "$FIN_OPS_SHADOW_PYTHON_BASE_URL/health" |
| `2` | `postgres_migrations` | `for f in rust/fin-ops-api/migrations/000*.sql; do psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"; done` | all 0001-0009 migrations applied on PostgreSQL 16/17 shadow database |
| `3` | `platform_postgres_seed` | `python3 scripts/tools/platform_shadow_seed.py --run-id "$SHADOW_RUN_ID" --actor-id "$FIN_OPS_SHADOW_OA_USERNAME" --user-id "$FIN_OPS_SHADOW_OA_USER_ID" --display-name "$FIN_OPS_SHADOW_OA_DISPLAY_NAME" --apply` | generated seed SQL applied; source the generated p0-platform-shadow-env-*.sh file for fixture IDs |
| `4` | `platform_legacy_seed` | `python3 scripts/tools/platform_shadow_legacy_seed.py --run-id "$SHADOW_RUN_ID" --username "$FIN_OPS_SHADOW_OA_USERNAME" --user-id "$FIN_OPS_SHADOW_OA_USER_ID" --data-dir "$FIN_OPS_SHADOW_LEGACY_DATA_DIR"` | legacy Python isolated data-dir seeded before service startup |
| `5` | `axum_shadow` | `cd rust/fin-ops-api && FIN_OPS_API_BIND_ADDR=127.0.0.1:8002 FIN_OPS_OA_IDENTITY_ADAPTER=trusted_headers cargo run -p fin-ops-api --bin fin-ops-api` | curl -fsS "$FIN_OPS_SHADOW_AXUM_BASE_URL/readyz" |
| `6` | `platform_seed_fact_probes` | `run every command in fact_probe_commands until each returns t` | all fact id variables resolve to equivalent seeded PostgreSQL facts |
| `7` | `legacy_shadow_reload_probe` | `python3 scripts/tools/platform_shadow_legacy_reload.py` | reload report status GO |
| `8` | `runtime_shadow_validation` | `python3 scripts/tools/platform_shadow_runtime.py --report-date 20260517` | api_shadow_validate report status GO for all platform endpoint primary and permission cases |

### Fact Probe Commands

| Variable | PostgreSQL fact | Current status | Command |
| --- | --- | --- | --- |
| `BACKGROUND_JOB_ID` | `job.worker_tasks` | `GO` | `psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -At -c "select exists (select 1 from job.worker_tasks where id = '${BACKGROUND_JOB_ID}'::uuid and visibility = 'system')"` |
| `BANK_TRANSACTION_ID` | `app.bank_transactions` | `GO` | `psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -At -c "select exists (select 1 from app.bank_transactions where id = '${BANK_TRANSACTION_ID}'::uuid)"` |
| `LEDGER_ID` | `app.ledgers` | `GO` | `psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -At -c "select exists (select 1 from app.ledgers where id = '${LEDGER_ID}'::uuid and status = 'open')"` |
| `PROJECT_DELETE_ID` | `app.project_profiles` | `GO` | `psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -At -c "select exists (select 1 from app.project_profiles where id = '${PROJECT_DELETE_ID}'::uuid and project_status = 'active')"` |
| `PROJECT_ID` | `app.project_profiles` | `GO` | `psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -At -c "select exists (select 1 from app.project_profiles where id = '${PROJECT_ID}'::uuid and project_status = 'active')"` |

## Findings

| Code | Severity | Message | Required action |
| --- | --- | --- | --- |
| `NONE` | `none` | No blocking findings. | Run runtime shadow command. |

## Blocker Classification

- Local fixable: `0`
- Environment blockers: `0`

## Runtime Shadow Command

```bash
python3 scripts/tools/api_shadow_validate.py --fixture /Users/yu/Desktop/fin-ops-platform/docs/dev/api-fixtures/business-api-shadow-validation.json --output-dir docs/operations/backend-refactor --include-permission-failures --python-base-url http://127.0.0.1:8001 --axum-base-url http://127.0.0.1:8002 --endpoint-id background-job-acknowledge-request --endpoint-id workbench-settings-write-contract --endpoint-id workbench-settings-project-sync-request --endpoint-id workbench-settings-project-create-request --endpoint-id workbench-settings-project-delete-request --endpoint-id settings-data-reset-create-job --endpoint-id settings-data-reset-direct-queues-job --endpoint-id projects-hub-list --endpoint-id projects-create-manual-profile --endpoint-id project-detail --endpoint-id project-assign-request --endpoint-id ledgers-list --endpoint-id ledger-detail --endpoint-id ledger-status-update --endpoint-id reminders-list --endpoint-id reminder-run-request
```
