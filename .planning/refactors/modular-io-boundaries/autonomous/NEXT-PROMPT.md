# Next Prompt

Continue after `planning:read-model-authenticated-api-browser-smoke-runbook-selection`.

## Current State

- Branch: `dev`
- T0 accepted read-model worker wave 1 handoffs as local evidence/gap maps only.
- T0 selected the next boundary in `analysis/read-model-authenticated-api-browser-smoke-runbook-selection-2026-06-25.md`.
- Browser/API/high-row smoke and module-specific closure audits remain open.
- Browser smoke is deferred until a non-secret authentication/harness path is proven.
- No global or module closure is claimed.

## Next Boundary

`production:read-model-authenticated-api-response-shape-smoke-runbook`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Read:
   - `analysis/read-model-authenticated-api-browser-smoke-runbook-selection-2026-06-25.md`
   - `analysis/read-model-module-closure-worker-wave-1-acceptance-2026-06-25.md`
   - `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
   - `analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
   - the four accepted handoff files under `parallel/handoffs/`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
   - this prompt
4. Before executing any production command, write a runbook/evidence file under `analysis/` with exact commands, redaction rules, stop gates, expected evidence, rollback/cleanup note and post-checks.
5. Prefer deployed-runtime or HTTP checks that summarize only response-shape metadata and do not print sensitive payload rows.

## Stop Gates

- Do not print/store secrets, DSNs, tokens, cookies, env values or sensitive payload rows.
- Do not run production mutation, deploy, restart, requeue, repair, replay workers or mutate DB/queue/readiness state.
- Stop if authenticated API smoke cannot be performed without secrets or sensitive payload output; classify the boundary as deferred and select another safe boundary.
- Do not claim module/global closure from smoke evidence alone.
