# Next Prompt

Continue after `planning:post-shadow-read-rehearsal-next-boundary-selection`.

## Current State

- Branch: `dev`
- Authenticated API response-shape smoke is deferred because no non-secret HTTP SLO auth config exists in production env.
- Public unauthenticated page-shell smoke completed against `https://www.yn-sourcing.com`.
- Initial `http://127.0.0.1:18001` page-shell probe was classified as wrong-base operator evidence because the API listener returned 17/17 404 for `/fin-ops/*`.
- Public base rerun passed:
  - `probe_count=17`
  - `failed_probe_count=0`
  - all default `/fin-ops/*` page-shell paths returned 200
  - `max_p95_ms=27.782`
- `/health/ready` remained ready before and after.
- Row254 selected a T0-owned read-only shadow-read rehearsal runbook as the next evidence boundary.
- Row255 executed the rehearsal runbook and classified it as `production-evidence-deferred`:
  - direct shell lacked DB config;
  - runtime env execution returned `gate_recommendation=BLOCKED`;
  - `local_pickle` is not a comparable primary for current production PostgreSQL runtime;
  - `workbench_read_models` hit a PostgreSQL statement timeout;
  - output was redacted/hash based and `/health/ready` stayed ready.
- Row256 selected a PostgreSQL-native Workbench high-row query-plan/read-only runbook as the next boundary because Row255's concrete PostgreSQL-side gap was `workbench_read_models` statement timeout.
- Authenticated API, browser hydration/data, high-row and module-specific closure audits remain open.
- No global or module closure is claimed.

## Next Boundary

`production:workbench-read-model-high-row-query-plan-read-only-runbook`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Read:
   - `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`
   - `analysis/read-model-authenticated-api-browser-smoke-runbook-selection-2026-06-25.md`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
   - this prompt
4. Read `analysis/production-read-model-public-page-shell-smoke-runbook-2026-06-25.md`.
5. Read `analysis/planning-post-public-page-shell-smoke-next-boundary-selection-2026-06-25.md`.
6. Read `analysis/production-read-model-shadow-read-rehearsal-read-only-runbook-2026-06-25.md`.
7. Read `analysis/planning-post-shadow-read-rehearsal-next-boundary-selection-2026-06-25.md`.
8. Write a bounded read-only PostgreSQL runbook before any production command.
9. Use `/health/ready` pre/post checks and `runuser -u postgres -- psql -d fin_ops` with `set default_transaction_read_only = on`, `begin read only` and `rollback`.
10. Collect only aggregate counts, index metadata, bounded EXPLAIN/timeout classification for Workbench high-row read-model queries. Do not select payload rows or mutate production.

## Stop Gates

- Do not print/store secrets, DSNs, tokens, cookies, env values or sensitive payload rows.
- Do not run production mutation, deploy, restart, requeue, repair, replay workers or mutate DB/queue/readiness state.
- Do not claim module/global closure from public page-shell smoke.
