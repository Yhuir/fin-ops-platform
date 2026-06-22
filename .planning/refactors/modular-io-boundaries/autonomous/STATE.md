# Autonomous State

**Created:** 2026-06-23
**Mode:** unattended best-effort
**Target branch:** `dev`
**Working directory:** `/Users/yu/Desktop/fin-ops-platform`
**Branch policy:** direct execution on `dev` in the main repository directory; no separate worktree and no separate `codex/*` integration branch

## Global Status

Current state: `ready-for-autonomous-start`

Go hot-path state: `candidate-gated-not-started`

## Environment Assumptions

- No local `PGSQL_URL`.
- No staging database.
- `ssh finops-prod` works as `finops-deploy`.
- `finops-deploy` has no passwordless sudo.
- `finops-prod-root` is pending interactive `ssh-copy-id` completion; if still unavailable, privileged production validation remains deferred.
- Production validation is non-blocking unless a production write or secret is required.
- Go/Fiber/Go Worker work is candidate-gated by `11-GO-HOT-PATH-CARVE-OUT.md`.
- Target read model strategy is partitioned scoped + scoped incremental.
- Target worker runtime is Go Worker + PostgreSQL dual queue; RabbitMQ is wakeup/transport only.
- Latest branch check found `origin/dev...origin/main = 350 ahead / 91 behind`; user intends to push current `main` first, then align `dev` with `main`.
- The autonomous run may merge `origin/main` into `dev` after `main` is clean and pushed.
- The autonomous run must not reset `dev` to `main`, rebase `dev`, or force-push.

## Current Module

None selected.

## Completed Modules

None.

## Deferred Modules

None.

## Go Candidate Status

No Go candidate has passed admission.

## Last Prompt

None.

## Next Prompt

See `autonomous/NEXT-PROMPT.md` after the autonomous run starts.
