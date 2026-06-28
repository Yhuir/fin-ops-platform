# Next Prompt

Continue the user-authorized `main-read-model-closure` run from the expanded 2026-06-26 controller.

## Current State

- Branch: `main`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260626-050615`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest reconciliation: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-26.md`.
- Latest wave summary: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-8-controlled-production-rollout-and-evidence-sweep-2026-06-26.md`.
- Production evidence runbook: `docs/operations/read-model-production-evidence-runbook.md`.
- Admin Token was not acquired in Wave 8. Never ask for the token in ordinary chat, and never print, hash, encode, persist or copy it into prompts, logs, files, docs, shell history, screenshots, test fixtures or worker prompts.
- User has approved production rollout, root SSH production validation, low-risk production samples, production business-operation validation, sample restore, and bounded DB restore for validation samples that lack business inverse.
- Missing business inverse restore path is not a blocker by itself. It must route into the preapproved bounded DB restore protocol; only missing operation-before snapshot, exact predicate, transaction safety, or post-restore verification can hard-stop sample recovery.
- Wave 8 deployed `main-18a0509f-20260626063245`, proved scope contract `ok=true`, direct critical read model SLO smoke 15/15 pass, final dirty/outbox/readiness all converged, and one `workbench_relation_withdraw` business path with bounded DB restore. This is not public real-auth Admin Token HTTP/SSE/browser closure.

## Next Boundary

`main-read-model-closure:wave-9-public-authenticated-api-sse-and-write-matrix-closure`

Goal:

- Start by attempting secure Admin Token acquisition through a popup or secure credential manager.
- Run public real-authenticated production API/SSE/browser read model freshness proof without persisting the token.
- Expand production write-operation closure beyond the Wave 8 Workbench relation sample, using low-risk turnover/no-OA/OA/import candidates where the operation-before snapshot, exact restore predicate, transaction safety and post-restore verification are available.
- Prefer business restore; when no business restore path exists, use the preapproved bounded DB restore protocol.

Required first steps:

1. Confirm `git status --short --branch`; stop only for unrelated dirty files.
2. Confirm `main` remains fast-forward synced with `origin/main`.
3. Read:
   - `AGENTS.md`
   - `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-7-legacy-quarantine-and-production-evidence-runbook-2026-06-26.md`
   - `docs/operations/read-model-production-evidence-runbook.md`
   - `docs/operations/runtime-worker-governance.md`
   - `deploy/oa/README.md`
4. First attempt secure Admin Token popup or secure credential manager lookup. Never print it. If unavailable and no secure input exists, continue non-token SSH/internal-command/business-command evidence, but mark public authenticated API/SSE/browser proof as `secure-admin-token-needed`; do not claim that proof closed.

Implementation priorities:

- Public authenticated proof:
  - authenticated API response-shape/freshness probes;
  - SSE first event / operation barrier proof;
  - browser/page read model stale/refreshing/fresh behavior if tooling is available.
- Write matrix:
  - use Wave 8 candidate discovery as starting evidence, but revalidate candidates before mutation;
  - apply through business API/UI/command, not DB;
  - restore through business inverse when available;
  - if no business inverse exists, use bounded DB restore protocol from the runbook;
  - record metadata only, no sensitive payloads or raw IDs.
- No-block policy:
  - no staging DB, no local PGSQL URL, missing business inverse, needing SSH, needing rollout, or needing low-risk sample selection is not a blocker;
  - only missing operation-before snapshot, exact predicate, transaction safety, post-restore verification, or a required secure token for public-auth proof can prevent that specific proof from closing.

Acceptance:

- Do not implement Go, Go Fiber or Go Worker.
- No secret values are printed or written.
- No production DB write except preapproved bounded sample restore when business inverse is unavailable and operation-before snapshot + exact predicate + transaction safety + post-restore verification are established.
- No claim of PSCIP-L4 until production evidence passes.
- If secure token input remains unavailable, record public-auth proof as `secure-admin-token-needed`, continue other evidence, and do not claim public-auth closure.

Verification:

- Use the runbook as source of truth.
- Record commands run and evidence collected in `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-9-public-authenticated-api-sse-and-write-matrix-closure-2026-06-26.md`.
- Commit only docs/evidence records that contain no secrets or sensitive payloads.

End of boundary:

- Update `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-9-public-authenticated-api-sse-and-write-matrix-closure-2026-06-26.md`.
- Update `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`.
- Update this `NEXT-PROMPT.md` with the next executable wave or final closure prompt.
- Commit verified non-secret artifacts on `main`.
- Continue automatically unless a precise hard stop is reached.
