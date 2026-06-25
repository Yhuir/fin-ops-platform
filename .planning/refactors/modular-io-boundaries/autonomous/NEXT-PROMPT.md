# Next Prompt

Continue the user-authorized `main-read-model-closure` run from the expanded 2026-06-26 controller.

## Current State

- Branch: `main`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260626-050615`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest reconciliation: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-26.md`.
- Latest wave summary: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-7-legacy-quarantine-and-production-evidence-runbook-2026-06-26.md`.
- Production evidence runbook: `docs/operations/read-model-production-evidence-runbook.md`.
- Admin Token was acquired through secure popup for the current controller session. Never print, hash, encode, persist or copy it into prompts, logs, files, docs, shell history, screenshots, test fixtures or worker prompts.
- User has approved production rollout, root SSH production validation, low-risk production samples, production business-operation validation, sample restore, and bounded DB restore for validation samples that lack business inverse.
- Missing business inverse restore path is not a blocker by itself. It must route into the preapproved bounded DB restore protocol; only missing operation-before snapshot, exact predicate, transaction safety, or post-restore verification can hard-stop sample recovery.

## Next Boundary

`main-read-model-closure:wave-8-controlled-production-rollout-and-evidence-sweep`

Goal:

- Deploy current `main` through the approved production rollout path.
- Collect PSCIP-L4 production evidence according to `docs/operations/read-model-production-evidence-runbook.md`.
- Run read-only runtime/read-model/worker evidence first, then bounded low-risk business write samples with restore.

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
4. Verify secure Admin Token remains available only in current process memory/env or secure secret source. Never print it. If unavailable and no secure input exists, hard-stop credential acquisition instead of asking in ordinary chat.

Implementation priorities:

- Before deploy:
  - record local commit and current production release commit;
  - run required local verification if not already current;
  - confirm rollback path.
- Deploy:
  - use `./scripts/deploy-oa.sh`;
  - never force-push or rewrite history;
  - do not write secrets to disk.
- Production evidence:
  - read-only App Health/readiness;
  - dirty scopes/outbox current-effective status;
  - worker heartbeat/required worker readiness;
  - read model SLO smoke and runtime closure gates;
  - scoped high-row latency/query-plan evidence where available.
- Business samples:
  - apply through business API/UI/command, not DB;
  - restore through business inverse when available;
  - if no business inverse exists, use bounded DB restore protocol from the runbook;
  - record metadata only, no sensitive payloads.

Acceptance:

- Do not implement Go, Go Fiber or Go Worker.
- No secret values are printed or written.
- No production DB write except preapproved bounded sample restore when business inverse is unavailable and operation-before snapshot + exact predicate + transaction safety + post-restore verification are established.
- No claim of PSCIP-L4 until production evidence passes.
- If production rollout or evidence hard-stops, record exact blocker and local PSCIP-L3 status.

Verification:

- Use the runbook as source of truth.
- Record commands run and evidence collected in `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-8-controlled-production-rollout-and-evidence-sweep-2026-06-26.md`.
- Commit only docs/evidence records that contain no secrets or sensitive payloads.

End of boundary:

- Update `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-8-controlled-production-rollout-and-evidence-sweep-2026-06-26.md`.
- Update `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`.
- Update this `NEXT-PROMPT.md` with the next executable wave or final closure prompt.
- Commit verified non-secret artifacts on `main`.
- Continue automatically unless a precise hard stop is reached.
