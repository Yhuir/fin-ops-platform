# Dev Branch Workflow

**Purpose:** Run the autonomous modular IO refactor in the main repository working directory, keep all implementation commits on `dev`, and never push implementation work to `main`.

## Current Policy

Use the main repository directory:

```text
/Users/yu/Desktop/fin-ops-platform
```

Do not create a new worktree for this refactor.

Use `dev` as the autonomous execution and integration branch.

Do not create a separate `codex/*` integration branch unless the user explicitly changes this policy later.

## Preconditions

The user will first commit and push the current `main` changes, including `.planning/`, to `origin/main`.

Autonomous implementation may start only when:

- the repository is in `/Users/yu/Desktop/fin-ops-platform`,
- the current working tree is clean,
- `main` has been pushed to `origin/main`,
- `.planning/` is tracked and available from `origin/main`,
- `origin/dev` and `origin/main` can be aligned without force-push.

If the main working tree has uncommitted user changes, stop. Do not stash, stage, revert, format, or commit them automatically.

## Alignment Policy

Before implementation, align `dev` with `main`.

Allowed default alignment after the user confirms `main` is pushed:

```bash
cd /Users/yu/Desktop/fin-ops-platform
git fetch origin --prune
git switch main
git pull --ff-only origin main
git switch dev
git pull --ff-only origin dev
git merge --no-edit origin/main
git push origin dev
```

This preserves `dev` history and brings in `main`.

Do not reset `dev` to `main` unless the user explicitly approves discarding all `dev`-only history.
Do not rebase `dev` automatically.
Do not force-push.

If `git merge origin/main` conflicts, stop and record `dev-main-alignment-conflict`. Do not auto-resolve finance, read model, worker, permission, or migration conflicts.

## Execution Policy

After alignment:

```bash
git switch dev
git status --short --branch
```

Proceed only if:

- branch is `dev`,
- upstream is `origin/dev`,
- working tree is clean before each module slice,
- `git status --short --branch` does not show `main`,
- `git pull --ff-only origin dev` succeeds.

## Commit Policy

Commit after each small verified module boundary.

Commit requirements:

- Tests/checks relevant to the slice pass, or unavailable checks are documented.
- No known broken code remains.
- No unrelated files are staged.
- No secrets are present.
- State/journal is updated.
- Docs impact is handled.

## Push Policy

Push only to:

```bash
git push origin dev
```

Never push implementation commits to `main`.
Never use `--force` or `--force-with-lease` in autonomous mode.

## Dirty State Handling

Because there is no separate worktree, the main repository directory must stay clean at automation start.

If unrelated dirty files appear during autonomous execution:

- do not stage them,
- do not revert them,
- stop if they make safe commits ambiguous.

If a selected module fails after repair attempts:

```bash
git diff > .planning/refactors/modular-io-boundaries/autonomous/failures/<module>-diff.patch
git stash push -u -m "autonomous-failed-<module>"
```

Then continue only if the working tree is clean and another independent module remains.

## Merge Boundary

Autonomous work may push `dev`.

It must not merge `dev` into `main`.
It must not delete branches.
It must not rewrite history.

Human review or a later explicit command owns merge from `dev` to `main`.
