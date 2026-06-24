# Next Prompt

Continue after the prompt-generation/thread-creation part of `planning:read-model-module-closure-worker-wave-1-prompts`.

## Current State

- Branch: `dev`
- Last controller commit before thread creation: `71ef441d docs(refactor): prepare read-model closure worker wave`
- Queue semantics remain corrected: slice status is not module closure.
- Row248 wrote `analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`.
- Row249 wrote `analysis/read-model-module-closure-worker-wave-1-prompts-2026-06-25.md` and created four worker threads:
  - W1 Workbench/Relations/Turnover: `019efb08-6669-7eb1-b5a2-166639ce50af`
  - W2 Invoice/OA Family: `019efb08-8ff0-74a1-b0c9-300f39c96f73`
  - W3 Bank/Pending/No-OA/Search: `019efb08-b871-7e00-9c36-8b621210d64b`
  - W4 Cost/Tax: `019efb08-e2a8-7722-8acd-452cd9629269`
- Worker handoffs are not accepted yet.
- Browser/API/high-row smoke and module-specific closure audits remain open.
- No global or module closure is claimed.

## Next Boundary

`planning:read-model-module-closure-worker-wave-1-monitor-and-accept`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean or only contains controller files from this handoff, and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev` before accepting any worker output.
3. Read:
   - `analysis/read-model-module-closure-worker-wave-1-prompts-2026-06-25.md`
   - `analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`
   - `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
   - `analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
   - `analysis/commit-backed-state-reconciliation-2026-06-25.md`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
   - this prompt
   - `12-PARALLEL-ORCHESTRATION.md`
4. Use `read_thread` to monitor W1-W4 until each is complete, idle with handoff, or blocked.
5. For every worker:
   - read the final answer;
   - inspect the assigned handoff file;
   - inspect any direct-dev commits or dirty files;
   - verify no controller-only files were touched;
   - classify evidence as accepted, partial, rejected, blocked, or waiting for write lease.
6. Pull any worker commits from `origin/dev` using `git pull --ff-only origin dev` only when the local tree is clean.
7. Run required verification for accepted worker diffs and at minimum:
   - `bash scripts/verify.sh docs`
   - `git diff --check`
   - `git diff --cached --check` when staging.
8. Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `04-master-goal-controller.md` with accepted/rejected worker status and the next safe boundary.

## Stop Gates

- Do not claim module/global closure from row245, row246, row248 or worker handoffs alone.
- Do not accept a worker handoff without reading its final answer and handoff file.
- Do not accept worker changes that touched controller-only files.
- Do not run production `--apply`, deploy, restart, requeue, repair, replay workers or mutate runtime state in this monitoring slice.
- Stop if current `dev` diverges from `origin/dev` or the worktree contains unrelated dirty files.
