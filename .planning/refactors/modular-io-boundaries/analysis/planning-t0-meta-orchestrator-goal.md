# planning:t0-meta-orchestrator-goal

**Date:** 2026-06-25
**Status:** planning-closed
**Previous boundary:** `planning:parallel-handoff-review-and-state-update`
**Next executable boundary:** `planning:post-parallel-handoff-next-boundary-selection`

## Goal

Convert the parallel workflow from a manually launched T0/T1-T9 prompt set into a single T0 Meta Orchestrator entrypoint that can create, monitor, review and close worker threads by itself.

This is a planning/prompt slice only. It does not change runtime code.

## Evidence Reviewed

- `.planning/refactors/README.md`
- `.planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md`
- `.planning/refactors/modular-io-boundaries/01-CURRENT-STATE-AUDIT.md`
- `.planning/refactors/modular-io-boundaries/02-MODULE-IO-CONTRACT-TEMPLATE.md`
- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`
- `.planning/refactors/modular-io-boundaries/06-PILOT-SELECTION.md`
- `.planning/refactors/modular-io-boundaries/07-DOCS-GOVERNANCE.md`
- `.planning/refactors/modular-io-boundaries/08-AUTONOMOUS-RUNBOOK.md`
- `.planning/refactors/modular-io-boundaries/09-DEV-BRANCH-WORKFLOW.md`
- `.planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md`
- `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
- `.planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/parallel/handoffs/*.md`
- `.planning/refactors/modular-io-boundaries/analysis/*.md` inventory

## Decision

The user no longer needs to manually launch T1-T9 prompts. The recommended unattended entrypoint is:

```text
.planning/refactors/modular-io-boundaries/prompts/06-t0-meta-orchestrator-goal.md
```

The old `05-parallel-thread-prompts.md` file is retained as worker archetype/reference material. It should not be treated as the primary manual launch plan for unattended work.

## Constraints Captured

- No staging database is available.
- No local `PGSQL_URL` or PostgreSQL URL is available.
- T0 must not ask the user for secrets.
- T0 may use `ssh finops-prod-root` for controlled production operations only through the controlled production gate.
- Workers must not execute production mutation or controlled production gates.
- T0 is the only thread that may create worker threads.
- Workers must not create recursive threads.
- T0 must cap worker waves, monitor workers, read final answers and handoffs, review diffs/tests/docs, update state, commit and push to `origin/dev`.

## State Machine Impact

No module state is closed by this slice. The next executable boundary remains:

```text
planning:post-parallel-handoff-next-boundary-selection
```

That boundary should now be executed through the new T0 Meta Orchestrator prompt.

## Verification

Required verification for this planning slice:

```bash
bash scripts/verify.sh docs
git diff --check
```
