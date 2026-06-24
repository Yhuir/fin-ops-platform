# Next Prompt

Continue after `production:read-model-authenticated-api-response-shape-smoke-runbook`.

## Current State

- Branch: `dev`
- Authenticated API response-shape smoke is deferred because no non-secret HTTP SLO auth config exists in production env.
- `/health/ready` remained ready.
- Post-checks after the deferred smoke path:
  - dirty scopes: `done=187007`
  - read model readiness: `fresh=498`
  - read-model outbox: `done=202898`
- Browser/API/high-row smoke and module-specific closure audits remain open.
- No global or module closure is claimed.

## Next Boundary

`production:read-model-public-page-shell-smoke-runbook`

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
4. Write a bounded production public page-shell smoke runbook/evidence file before executing commands.
5. Use `http_slo_probe --allow-unauthenticated --replace-default-probes` or an equivalent page-shell-only command. Do not run API probes without auth.

## Stop Gates

- Do not print/store secrets, DSNs, tokens, cookies, env values or sensitive payload rows.
- Do not run production mutation, deploy, restart, requeue, repair, replay workers or mutate DB/queue/readiness state.
- Do not claim module/global closure from public page-shell smoke.
