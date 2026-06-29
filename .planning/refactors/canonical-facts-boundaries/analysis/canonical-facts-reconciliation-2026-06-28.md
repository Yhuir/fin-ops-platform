# Canonical Facts Reconciliation 2026-06-28

## Preflight

- Branch: `main`, ahead of `origin/main`.
- Existing dirty files before this wave: prompt README and `08-canonical-facts-main-closure-controller.md`.
- Canonical facts lock: acquired.
- 07 read model conflict policy: do not edit 07-owned runtime shared files.

## Evidence Read

- `README.md`
- `ARCHITECTURE.md`
- `docs/index.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/architecture/persistence-and-read-models.md`
- `docs/architecture/module-boundaries/README.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/modules/README.md`
- PostgreSQL migrations under `backend/src/fin_ops_platform/postgres/migrations/`

## Current Gap

Long-term docs currently document read model and worker contracts, but do not have a separate canonical facts owner matrix. This makes it too easy to confuse read model ownership with business source-of-truth ownership.

## Wave 1 Decision

Execute docs-only foundation:

- add canonical facts architecture contract;
- add `docs/modules/canonical-facts/`;
- update indexes and maintenance rules;
- create canonical facts GSD state;
- do not edit code or 07-owned files.
