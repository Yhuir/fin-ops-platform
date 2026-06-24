# planning:parallel-orchestration-workflow

**Date:** 2026-06-24
**Status:** planning-closed
**Previous boundary:** `server-py:workbench-group-detail-route-owner-audit`
**Next executable boundary:** `server-py:workbench-group-detail-route-owner-extraction`

## Goal

Upgrade the modular IO autonomous workflow from a single-thread-only queue into a controller-led parallel orchestration model, without allowing multiple threads to corrupt `dev` or global state files.

This is a planning-only slice. It does not change runtime code.

## Evidence Reviewed

- `.planning/refactors/README.md`
- `.planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md`
- `.planning/refactors/modular-io-boundaries/02-MODULE-IO-CONTRACT-TEMPLATE.md`
- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`
- `.planning/refactors/modular-io-boundaries/08-AUTONOMOUS-RUNBOOK.md`
- `.planning/refactors/modular-io-boundaries/09-DEV-BRANCH-WORKFLOW.md`
- `.planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md`
- `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

## Findings

The current autonomous workflow is deliberately single-threaded:

- it selects the first pending queue row;
- every slice updates shared global state files;
- every slice commits and pushes to `dev`;
- `NEXT-PROMPT.md` represents a single next action.

Opening several autonomous controllers on the same `dev` branch would conflict on shared state and likely reintroduce the exact class of cross-feature regressions this refactor is meant to eliminate.

Parallelism is still useful if global state ownership is centralized. The safe model is one controller thread plus bounded worker threads. Workers can auto-progress inside their assigned workstream, but global progress and final closure remain controller-owned.

## Deliverables

- Added `12-PARALLEL-ORCHESTRATION.md`.
- Added `prompts/05-parallel-thread-prompts.md`.
- Inserted `planning:parallel-orchestration-workflow` into the autonomous queue as a planning-closed slice.
- Kept `server-py:workbench-group-detail-route-owner-extraction` as the next executable implementation boundary.

## State Machine Impact

No global state-machine transitions changed. This slice adds an execution mode on top of `AutonomousContinue`:

```text
AutonomousContinue
  -> ParallelControllerPlanning
  -> ParallelWorkerExecution
  -> ControllerIntegration
  -> GlobalClosureAudit
```

Those labels are orchestration sub-states, not replacements for the existing global or single-module state machines. The existing hard stop gates and completion labels still apply.

## Next Boundary

`server-py:workbench-group-detail-route-owner-extraction` remains the next executable code boundary. It should be assigned to the server route owner worker or executed by the controller if the user chooses to remain single-threaded.

## Verification

Required verification for this planning slice:

```bash
bash scripts/verify.sh docs
git diff --check
```
