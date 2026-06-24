# Next Prompt

Continue after `production:read-model-authenticated-browser-page-smoke-runbook`.

## Current State

- Branch: `dev`.
- Active production release is `dev-turnover-source-version-persistence-20260625` at git commit `8f525563e10972168014356ff410c4fc8456f377`.
- Row292 full non-admin user-scope API smoke passed all 37 default non-admin probes with 0 failed, 0 non-fresh and 0 refresh-enqueued probes; pre/post dirty scopes, readiness, read-model outbox and dead letters were unchanged.
- Row293 selected read-only authenticated production browser page smoke as the next lowest-risk evidence boundary; admin and write-flow evidence remain deferred.
- Row294 wrote and committed the browser runbook before execution, then ran production prechecks:
  - `/health/ready=ready`;
  - dirty scopes `done=187061`;
  - readiness `fresh=498`;
  - read-model outbox `done=202956`;
  - read-model dead letters `0`.
- Row294 browser harness check found:
  - `playwright_bin=missing`;
  - `production_route_shell_spec=missing`.
- Per runbook stop gate, no browser command ran. T0 did not install packages, download browser binaries, copy tokens, run local Playwright with production token, run admin probes, run write-flow probes, deploy, restart, requeue, repair, replay, mutate DB/readiness/dirty scopes or run `--apply`.
- Row294 postcheck stayed clean:
  - `/health/ready=ready`;
  - dirty scopes `done=187061`;
  - readiness `fresh=498`;
  - read-model outbox `done=202956`;
  - read-model dead letters `0`.
- Browser/admin/write production evidence and global/module closure remain open.

## Next Boundary

`planning:post-authenticated-browser-harness-missing-next-boundary-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row294 evidence if it is not already committed.
3. Reconcile the harness gap:
   - production deploy source currently excludes Playwright binary and e2e spec files;
   - token-safe local Playwright remains forbidden unless a non-secret token/session seam is provided;
   - production browser evidence cannot be claimed from Row294.
4. Select exactly one next bounded boundary.
5. Do not run production browser/admin/write commands in this planning boundary.

## Candidate Directions

- Package or retain a production-safe read-only browser smoke harness in source/deploy, with no package install/download at execution time.
- If packaging is too invasive for the current goal, select admin seam classification or write-flow planning as evidence accounting only.
- Do not claim global/module closure until browser/admin/write evidence is either collected or explicitly classified with accepted stop gates.

## Required Verification

- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Do not print or store secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows or business identifiers.
- Do not execute production browser/admin/write probes in the planning slice.
- Do not add deploy/package changes without first reading deploy docs and assessing docs impact.
- Do not claim module/global closure from harness-missing evidence alone.
