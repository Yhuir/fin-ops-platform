# Queue Semantics And Master Goal Prompt Revision

**Date:** 2026-06-24
**Boundary:** `planning:queue-semantics-and-master-goal-prompt-revision`
**Status:** `planning-closed`

## Why This Slice Exists

The autonomous queue already separates slice status from module closure, but the current resume prompt still creates two risks:

- It can make `server-py:legacy-handler-extraction-implementation` look like proof that the `bank_detail` pilot is fully closed.
- It does not force every autonomous iteration to reconcile `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and state-machine semantics before implementation.

This slice is planning/accounting only. It does not change runtime behavior.

## Previous State

- Last implementation slice: `read-models:bank-detail-category-side-effect-port-extraction`
- Last implementation status: `implementation-closed`
- Module closure for `bank_detail`: `implementation-gap-open`
- Next executable implementation boundary: `server-py:legacy-handler-extraction-implementation`
- Go candidates: `blocked-by-prerequisite`

## Corrected Semantics

`Status` in `autonomous/MODULE-QUEUE.md` means one narrow slice is complete.

`Module Closure` means whether the broader module is fully modularized and production-ready under the rules in:

- `00-REQUIREMENTS.md`
- `03-REFACTOR-STATE-MACHINE.md`
- `04-IMPLEMENTATION-ROADMAP.md`

Therefore:

- `implementation-closed` does not mean module closed.
- `planning-closed` does not mean implementation closed.
- `production-evidence-deferred` is a soft evidence gap, not a hidden success state.
- Go admission cannot be selected while earlier implementation-pending or implementation-gap-open work remains.

## Queue Correction

This planning slice is inserted before `server-py:legacy-handler-extraction-implementation` so the next Codex controller sees that queue/state/prompt semantics were intentionally reconciled before implementation resumes.

The next executable implementation boundary remains:

`server-py:legacy-handler-extraction-implementation`

This does not close:

- the full `bank_detail` module
- the full read model roadmap
- Phase 1-3 of `04-IMPLEMENTATION-ROADMAP.md`
- any Go hot-path prerequisite

## State Machine Impact

Reviewed:

- `03-REFACTOR-STATE-MACHINE.md`
- `04-IMPLEMENTATION-ROADMAP.md`
- `autonomous/STATE.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No new global or module state is required. Existing labels are sufficient:

- `planning-closed`
- `implementation-gap-open`
- `implementation-pending`
- `blocked-by-prerequisite`

The necessary correction is accounting and prompt control, not a new state-machine transition.

## Impact And Test Gates

Runtime impact: none.

Docs/accounting impact:

- Update `STATE.md` so the latest planning slice is visible.
- Update `MODULE-QUEUE.md` so this reconciliation is not implicit.
- Update `JOURNAL.md` with the correction.
- Update `NEXT-PROMPT.md` with the next safe boundary.
- Update the master goal prompt so autonomous execution must reconcile state and queue semantics before every implementation slice.

Verification:

- Markdown queue/status consistency review.
- Git diff review.
- No application tests required because no runtime code changed.

## Next Prompt

`server-py:legacy-handler-extraction-implementation`

The next controller must start from analysis, select exactly one narrow legacy handler boundary, and either extract it into an existing route/service owner or quarantine it with owner/caller/deletion-condition/forbidden-write evidence.
