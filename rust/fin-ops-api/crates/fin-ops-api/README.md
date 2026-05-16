# fin-ops-api

Axum + Tokio API skeleton for the backend refactor. This crate is intentionally independent from the existing Python backend and only implements phase-1 infrastructure endpoints.

## Local Check

```bash
cargo fmt --all --check
cargo check --workspace
```

## Local Run

```bash
export DATABASE_URL='postgres://fin_ops_api:***@127.0.0.1:5432/fin_ops'
cargo run -p fin-ops-api
```

Replace `***` with a local secret injected outside git. `DATABASE_URL` is required and validated at startup. `/healthz` does not depend on PostgreSQL, while `/readyz` checks the PostgreSQL pool.
