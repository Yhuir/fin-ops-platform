# Next Prompt

Continue after `planning:read-model-module-closure-worker-wave-1-monitor-and-accept`.

## Current State

- Branch: `dev`
- Last accepted worker handoff commits:
  - W1 `bf03ba98 docs(read-models): add workbench closure wave handoff`
  - W2 `82eb8919 docs(read-models): add invoice oa closure handoff`
  - W3 `cfc495f1 docs(read-models): add W3 closure wave handoff`
  - W4 `525818ba docs(read-models): add cost tax wave1 handoff`
- T0 acceptance file: `analysis/read-model-module-closure-worker-wave-1-acceptance-2026-06-25.md`
- Queue semantics remain corrected: slice status is not module closure.
- Worker handoffs are accepted as local evidence/gap maps only.
- Browser/API/high-row smoke and module-specific closure audits remain open.
- No global or module closure is claimed.

## Next Boundary

`planning:read-model-authenticated-api-browser-smoke-runbook-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Read:
   - `analysis/read-model-module-closure-worker-wave-1-acceptance-2026-06-25.md`
   - `analysis/read-model-module-closure-worker-wave-1-prompts-2026-06-25.md`
   - `analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`
   - `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
   - `analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
   - the four accepted handoff files under `parallel/handoffs/`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
   - this prompt
   - `12-PARALLEL-ORCHESTRATION.md`
4. Build a bounded planning/runbook slice for authenticated API response-shape, browser first-screen/stale/export/detail and high-row evidence.
5. Keep the slice controller-owned until the runbook identifies independent non-overlapping worker-safe smoke files or proves T0-only production read-only execution is required.

## Stop Gates

- Do not claim module/global closure from worker handoffs, row245 or row246.
- Do not run production mutation, deploy, restart, requeue, repair, replay workers or mutate runtime state in this planning slice.
- Do not read or print secrets, DSNs, tokens, cookies or sensitive payloads.
- Stop if current `dev` diverges from `origin/dev` or the worktree contains unrelated dirty files.
