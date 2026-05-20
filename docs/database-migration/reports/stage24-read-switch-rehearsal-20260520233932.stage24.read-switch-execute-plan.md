# Stage 24 Read Switch Execute Plan

Run ID: `stage24-read-switch-rehearsal-20260520233932`

This plan was generated only as a dry-run artifact. It was not executed.

## Preconditions

- Same-run shadow-read P0/P1/read errors must be zero.
- Runtime policy must be PASS with blocked_unknown=0.
- No-traffic PostgreSQL mode check must be ready.
- Cutover preflight must pass.
- User must explicitly authorize production service config/env changes and restart.

## Proposed Production Changes, Not Executed

- Release candidate: `/opt/fin-ops/releases/stage23-release-runtime-20260520233335`
- Source path: `/opt/fin-ops/releases/stage23-release-runtime-20260520233335/src`
- Venv path: `/opt/fin-ops/releases/stage23-release-runtime-20260520233335/venv`
- Credential file: `/root/fin_ops_stage23_postgres_runtime.env`
- Runtime DSN: `postgresql://fin_ops_app_runtime:***@127.0.0.1:5432/fin_ops`

Suggested live env values for an authorized execute stage:

```bash
FIN_OPS_APP_STORAGE_BACKEND=postgres
FIN_OPS_APP_READ_BACKEND=postgres
FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary
# FIN_OPS_POSTGRES_DATABASE_URL should be loaded from the root-only credential file, not printed.
```

## Commands Requiring Separate Authorization

```bash
# Backup live service env/unit first.
# Install or point systemd to the approved release candidate.
# Add PostgreSQL runtime env using a root-only secret path.
systemctl daemon-reload
systemctl restart fin-ops.service
```

## Post-Restart Smoke

- `systemctl status fin-ops.service --no-pager`
- `python -m fin_ops_platform.app.main --check` under live service env.
- HTTP smoke: `/health`, `/api/session/me`, `/api/workbench/settings`, `/api/background-jobs/active`, `/api/etc/invoices`.
- Same-run shadow-read after restart.

## Rollback Template

```bash
# Restore previous service env/drop-in/current pointer.
systemctl daemon-reload
systemctl restart fin-ops.service
# Verify local_pickle/app Mongo mode health.
```

## Stop Conditions

- Any P0/P1/read error.
- Runtime policy blocked_unknown.
- PostgreSQL mode check failure.
- Service fails readiness or HTTP smoke.
- Any need to touch OA Mongo `form_data_db.form_data`.
