# planning:commit-backed-state-reconciliation

**Date:** 2026-06-25
**Status:** planning-prepared
**Previous boundary:** `planning:parallel-handoff-review-and-state-update`
**Next executable boundary:** `planning:commit-backed-state-reconciliation`

## Goal

Install a mandatory commit-backed reconciliation gate before the next implementation slice or worker wave.

The user challenged whether current refactor state files and completion percentages are accurate. This slice does not compute the final percentages. It changes the controller workflow so the next T0 run must compute them from git commit evidence first.

## Reason

The current refactor state files are execution logs and planning aids, not authoritative proof of completion. They can drift when a slice is marked completed for analysis, prompt generation, static guard, partial production evidence or deferred Go admission.

Future completion reporting must therefore be derived from actual commits, diffs, changed files and verification evidence rather than:

- memory from previous threads;
- `STATE.md` wording;
- `MODULE-QUEUE.md` status counts;
- `JOURNAL.md` summaries;
- roadmap checkbox counts.

## Required Reconciliation Source

T0 must build the evidence ledger from:

- `git log --oneline --decorate origin/main..HEAD`;
- `git log --oneline --decorate --all` around refactor commits;
- `git show --name-status --stat <commit>` for each refactor-relevant commit;
- current tracked files under `.planning/refactors/`, `docs/modules/`, `backend/`, `web/`, `tests/`, `scripts/`, `deploy/`;
- worker handoff files and controller acceptance commits;
- targeted test and verification evidence recorded in commits or analysis files.

## Required Classification

For each queue row and roadmap criterion, T0 must classify evidence as:

- `commit-proven`: code/docs/tests changed in commits and verification evidence exists.
- `commit-partial`: some committed evidence exists but acceptance criteria are incomplete.
- `docs-only`: only planning/docs accounting exists, no runtime/test proof.
- `deferred`: real production/staging/PG/worker/browser evidence is missing.
- `unproven`: state file claims completion but no commit-backed evidence was found.
- `stale-state`: state file contradicts commit evidence.

## Required Percentages

T0 must compute at least:

- roadmap completion percentage;
- queue evidence percentage by status;
- module local implementation percentage;
- module global closure percentage;
- production evidence percentage;
- Go admission percentage.

The percentages must include numerator, denominator, criteria and evidence path. They must not be raw state-file row counts unless the row count is first reconciled to commit evidence.

## Required State Updates

After reconciliation, T0 must update these files if any stale or inaccurate state is found:

- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/prompts/04-master-goal-controller.md`

The report itself must be written to:

```text
.planning/refactors/modular-io-boundaries/analysis/commit-backed-state-reconciliation-<date>.md
```

## State Machine Impact

This planning-prepared slice changes the next executable controller boundary from:

```text
planning:post-parallel-handoff-next-boundary-selection
```

to:

```text
planning:commit-backed-state-reconciliation
```

`planning:post-parallel-handoff-next-boundary-selection` must run only after the commit-backed reconciliation report has been produced and the state files have been corrected.

## Verification

Required verification for this planning slice:

```bash
bash scripts/verify.sh docs
git diff --check
```

Runtime/API behavior is not changed by this slice.
