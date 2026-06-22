# Prompt: Start Autonomous Modular IO Refactor

Copy the full prompt below into Codex to start the autonomous run.

```text
You are Codex working in /Users/yu/Desktop/fin-ops-platform.

Objective:
Run the modular IO boundary refactor as far as safely possible in autonomous mode. I may be away. Do not wait for me unless a hard stop gate is hit.

Primary constraints:
- Do not work on main.
- Do not commit or push to main.
- Use dev as the direct autonomous execution and integration branch.
- Do not create a separate codex/* integration branch.
- Do not create a new worktree.
- Use the main repository directory /Users/yu/Desktop/fin-ops-platform.
- Start only after the user has committed and pushed current main changes, including .planning/, to origin/main.
- Require a clean working tree before switching branches or starting automation.
- Fetch origin first. origin/dev is the required upstream for dev.
- Align dev with main by merging origin/main into dev after main is pushed.
- Do not reset dev to main automatically.
- Do not rebase dev automatically.
- Commit and push each passing small module/boundary slice to origin dev.
- Never force-push.
- Never record secrets.
- Do not ask me for SSH passwords, DB passwords, tokens, cookies, PGSQL_URL, or staging database.
- Do not require staging DB or local PGSQL_URL. They are unavailable.
- Use local static checks, local fake/stub tests, API contract tests, frontend tests, and non-privileged production read-only SSH checks when useful.
- Remove obsolete legacy code paths when tests and call graph prove they are unused.
- Quarantine retained legacy paths as compat-only with owner, caller list, deletion condition, and tests.
- Prevent old modules from writing new canonical facts, dirty scopes, outbox, read model readiness, cache, or App Status.
- Treat read model force refresh, freshness proof, affected scopes, and operation barrier as production-grade contracts.
- Treat Go / Go Fiber / Go Worker as candidate-gated hot-path carve-out only.
- Do not implement Go/Fiber for modules outside .planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md.
- Do not implement Go/Fiber before performance evidence, IO contract, legacy isolation, shadow run, rollback, and freshness proof gates pass.
- Target read model strategy is Partitioned Scoped Read Model + Scoped Incremental Projection. Workbench keeps active generation.
- Target worker runtime is Go Worker + PostgreSQL dual queue, where dual queue means job.outbox_events plus job.read_model_dirty_scopes. RabbitMQ is optional wakeup/transport only.
- ssh finops-prod is available as finops-deploy, but has no passwordless sudo.
- finops-prod-root may become available after interactive ssh-copy-id. Test it before privileged read-only production validation. If unavailable, treat privileged production validation as deferred evidence, not a blocker.
- Do not perform production writes. If a production write or secret is required, record needs-human-production-gate and continue to another independent module if possible.

Required reading before any edits:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/app-architecture/README.md
- docs/app-architecture/runtime-and-ownership.md
- docs/modules/README.md
- .planning/refactors/modular-io-boundaries/README.md
- .planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md
- .planning/refactors/modular-io-boundaries/02-MODULE-IO-CONTRACT-TEMPLATE.md
- .planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md
- .planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md
- .planning/refactors/modular-io-boundaries/08-AUTONOMOUS-RUNBOOK.md
- .planning/refactors/modular-io-boundaries/09-DEV-BRANCH-WORKFLOW.md
- .planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md
- .planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md
- .planning/refactors/modular-io-boundaries/autonomous/STATE.md
- .planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md

Autonomous loop:
1. Preflight git in the main repository directory, confirm clean state, align dev with origin/main, and switch to dev.
2. Select the first pending module boundary from MODULE-QUEUE.md.
3. Read the module docs and current code/tests.
4. Use CodeGraph for structural lookup before edits.
5. Produce/update module IO audit under .planning/refactors/modular-io-boundaries/analysis/.
6. Fill the legacy retirement/quarantine contract and read model force refresh contract.
7. Fill partitioned scoped incremental projection fields for read model boundaries.
8. If the boundary is a Go candidate, run only Go admission first: candidate list membership, performance evidence, shadow run, Python-vs-Go equivalence, double-write prevention, and rollback.
9. Add/update tests first where practical, including old-path contamination, cross-page freshness, partition/scope, and Python-vs-Go equivalence tests when applicable.
10. Implement the narrowest code/docs refactor that tightens the IO boundary.
11. Remove or quarantine old route/service/repository/read model/frontend paths for the selected boundary.
12. Run targeted verification. Use fake/stub tests instead of real PostgreSQL/staging.
13. Run a diff review and secret scan over changed files.
14. Verify new code does not call old internals and old paths cannot write new facts/refresh state.
15. For Go candidates, verify no authoritative Go implementation starts unless admission gates pass; otherwise mark go-candidate-deferred.
16. Update module docs, autonomous STATE.md, JOURNAL.md, and MODULE-QUEUE.md.
17. Commit only passing reviewable changes.
18. Push to origin dev.
19. Generate/update autonomous/NEXT-PROMPT.md.
20. Continue with the next module.

Failure behavior:
- For a module-specific failure, try up to 3 repair iterations.
- If still failing, preserve evidence, mark the module deferred-module-failure, stash the failed module diff if needed, and continue to the next independent module only if the working tree is clean.
- Missing PGSQL_URL, missing staging DB, missing root SSH, and missing production DB evidence are soft gates. Record production-evidence-deferred and continue.
- Go candidate admission failure is a soft gate. Record go-candidate-deferred and continue with Python boundary hardening or the next independent module.
- Stop only for hard gates in 10-AUTONOMOUS-STOP-GATES.md.

Initial recommended module:
bank-details:auto-tag-category-boundary.

Final response when you stop or finish a wave:
- List modules completed.
- List modules deferred and why.
- List commits and confirm they were pushed to dev.
- List tests run.
- List production evidence collected or deferred.
- State whether any hard stop gate was hit.
```
