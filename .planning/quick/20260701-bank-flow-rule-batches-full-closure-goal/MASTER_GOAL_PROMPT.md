# `/goal` Prompt: Bank Flow Rule Batches Full Closure

Copy the block below into Codex `/goal`.

```text
Fully close the `bank-flow-rule-batches` module in `/Users/yu/Desktop/fin-ops-platform`.

Business/module target:
- Page: `流水规则批量处理`
- Frontend route: `/bank-flow-rule-batches`
- API prefix: `/api/bank-flow-rule-batches`
- Read model key: `bank_flow_rule_batch`
- Current status: functionally independent, but not architecture-final.

The closure must eliminate these known gaps:

1. Physical storage final state
   - Introduce independent durable storage for bank-flow rule batches:
     - `app.bank_flow_rule_batches`
     - `app.bank_flow_rule_batch_events`
     - `read_model.bank_flow_rule_batch_rows`
   - Migrate current `relation_mode=bank_flow_rule_batch` rows out of shared no-OA physical storage.
   - Remove bank-flow runtime dependence on historical no-OA physical batch/read-model tables after migration.
   - Keep no-OA legacy paths working for `relation_mode=no_oa_bank_batch`.
   - Preserve relation facts through `WorkbenchRelationCommandService`; do not write relation tables directly.

2. Rule persistence final state
   - Move rule persistence away from `app_settings.no_oa_bank_batch_tag_selection`.
   - Introduce/finish a bank-flow-owned rules family, preferably `app.bank_flow_rule_tag_requirements`, with versioning, audit, active tag validation, optimistic concurrency, and migration from the transitional settings family.
   - `BankFlowRuleBatchApplicationService.update_tag_selection()` must not call `update_no_oa_bank_batch_tag_selection(...)` when closure is complete.
   - The public API must continue to accept/write `rules` and reject `selected_tag_codes` / `selectedTagCodes`.

3. Frontend modular closure
   - Reduce `web/src/pages/BankFlowRuleBatchPage.tsx` from the current monolithic page into cohesive modules with explicit boundaries and I/O.
   - Keep the public route and user-observable behavior unchanged.
   - Prefer existing project patterns and `web/src/features/bankFlowRuleBatches/*` before adding new structure.
   - Split only where it reduces real state coupling:
     - batch list/read model state and pagination
     - tag rules drawer/grid state
     - submit/withdraw/reset/rebaseline mutation controller
     - detail loading
   - Do not do a broad visual redesign unless required by broken behavior.

4. Performance closure
   - Remove or narrow unbounded `scope_key="all"` refreshes in hot paths where a month/batch/case scope is available, especially detail/withdraw/reset.
   - Verify list/read/detail/submit/withdraw/reset read paths use bounded repository queries and appropriate indexes.
   - Add performance guard tests or repository SQL assertions where practical.
   - If a runtime benchmark requires production/staging credentials or real data, document exactly what remains as staging smoke instead of guessing.

5. Test and verification closure
   - Close the documented test gaps:
     - unknown/inactive/duplicate tag validation
     - independent rule audit
     - partial failure rollback / no half-written relation or batch state
     - independent physical read model table/source version/schema version behavior
     - no-OA legacy regression after migration
     - operation barrier/freshness for the new storage
     - frontend interaction coverage after page split
   - Evaluate and report all seven AGENTS.md test categories.
   - Add/update tests only where they protect real behavior or architecture contracts.

6. Documentation closure
   - Update long-term facts, not just `.planning`.
   - Required docs to assess and update when facts change:
     - `docs/modules/bank-flow-rule-batches/README.md`
     - `docs/modules/bank-flow-rule-batches/boundary-io.md`
     - `docs/modules/bank-flow-rule-batches/state-machine.md`
     - `docs/modules/bank-flow-rule-batches/tests.md`
     - `docs/modules/bank-flow-rule-batches/e2e-coverage.md`
     - `docs/architecture/module-boundaries/canonical-facts.md`
     - `docs/architecture/module-boundaries/read-model-contracts.md`
     - `docs/dev/api-contracts.md`
     - `docs/operations/runtime-worker-governance.md` if worker/deploy facts change

Hard repository rules:
- Follow `AGENTS.md`.
- Before changing code, identify affected modules and read their `boundary-io.md`.
- If read model/worker changes are involved, read `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`, and `docs/operations/runtime-worker-governance.md`.
- Use CodeGraph for structural symbol/caller/impact questions.
- Use `rg` for literal text and file discovery.
- Keep `server.py` thin: routing, dependency assembly, and HTTP mapping only.
- Put business logic in `services/`.
- Put SQL/table structure in repositories or migration code, not scattered service logic.
- Inject explicit dependencies; do not pass the whole `Application` into services.
- Services must not read HTTP cookies/headers, import `app.auth`, or construct HTTP responses.
- Workers must not depend on `Application`, HTTP, auth, cookies, headers, responses, or route modules.
- Read model refresh must go through freshness/status/enqueue boundaries.
- Non-transactional refresh must use `ReadModelRefreshGateway` and scope policy registry before durable queue enqueue.
- Transactional writers must keep enqueue behavior inside the same business transaction and honor equivalent scope contracts.
- Redis may cache only fresh-gated payloads.
- RabbitMQ is optional wakeup/transport, not read model truth.
- Preserve Workbench active generation atomic publish semantics.
- Preserve user changes in the worktree.
- Do not leave temporary files, prompt files outside `.planning`, dead code, dead compatibility branches, or unrelated edits.
- Do not add new dependencies unless unavoidable and justified.
- Prefer deletion of obsolete compatibility code after migration over adding more fallbacks.

Closed-loop controller algorithm:

Maintain current state internally:
- objective
- current phase
- known facts and source files
- assumptions
- affected modules
- affected APIs/services/repositories/read models/workers/pages/docs/tests
- files changed
- tests added or changed
- seven-category test coverage decision
- verification commands/results
- open risks
- next action

Loop until complete or genuinely blocked:

1. Analyze current state
   - Inspect current worktree before relying on prior context.
   - Read the authoritative docs for every touched module.
   - Inspect code/tests/migrations/manifest/registry currently on disk.
   - Determine the highest-risk remaining gap.
   - Do not treat previous docs saying “covered” as proof; verify the actual files and tests.

2. Generate exactly one bounded execution prompt
   - Write one prompt for the next action only.
   - Include goal, evidence to inspect, allowed files/modules, architecture constraints, expected edits, tests/docs to consider, and stop condition.
   - Do not generate a backlog of future prompts.
   - Prefer this risk order unless current evidence shows a better next step:
     1. baseline audit and migration design
     2. independent physical storage and migrations
     3. independent rule persistence
     4. read model/worker/query cutover and performance scope narrowing
     5. backend/API/regression test gaps
     6. frontend modular split
     7. docs, E2E, deployment/staging verification closure

3. Execute that prompt immediately
   - Make the smallest production-grade change that moves the final state closer.
   - Remove old logic from the bank-flow path once replacement is proven.
   - Keep no-OA legacy behavior only behind explicit no-OA boundaries.
   - Add/update tests for behavior-changing work.
   - Update docs when boundaries, I/O, read model, worker, API, tests, or old-code deletion status change.

4. Review
   - Inspect diffs.
   - Check for old no-OA logic still in the bank-flow path.
   - Check for unbounded refresh/query paths.
   - Check for duplicated abstractions, dead code, stale docs, missing migrations, missing tests, and contract drift.
   - Run targeted verification first; broaden when risk justifies it.
   - If tests fail, debug systematically and continue.

5. Decide
   - DONE only when every explicit closure item above is implemented, old bank-flow compatibility paths are removed, relevant docs are updated, tests/verification prove the change, and remaining risk is only external staging/runtime smoke.
   - BLOCKED only when a required fact cannot be discovered locally or a required external system/user decision is unavailable after repeated attempts.
   - Otherwise CONTINUE by deriving the next single prompt from current evidence.

Completion evidence checklist:
- No bank-flow runtime storage dependence on no-OA physical batch/read-model tables remains, except one-time migration or explicitly retained legacy tools outside the bank-flow path.
- `BankFlowRuleBatchApplicationService.update_tag_selection()` no longer calls no-OA tag-selection persistence.
- `GET/PUT /api/bank-flow-rule-batches/tag-rules` contract remains stable and rejects `selected_tag_codes`.
- `GET /api/bank-flow-rule-batches` reads independent bank-flow read model storage.
- Submit/withdraw/reset/rebaseline write paths use bank-flow storage and `WorkbenchRelationCommandService`.
- Operation barrier targets use `bank_flow_rule_batch`.
- Read model manifest/worker/registry/scope policy/migrations/docs agree.
- No-OA legacy API/read model tests still pass.
- Frontend page is split into cohesive modules without behavior regression.
- Unknown/inactive/duplicate tags, version conflict, relation command failure, partial persistence failure, stale/missing read model, rebaseline manifest errors, permissions, and no-OA regression are covered by tests where locally testable.
- The seven AGENTS.md test categories are explicitly evaluated in the final answer.

Recommended first bounded execution prompt:
- Use `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/PROMPT_001_BASELINE_AUDIT.md` if present.
- If that file is missing, generate an equivalent baseline audit prompt yourself.

Final response format:
- Result
- Files changed
- Tests added or changed
- Seven test categories covered
- Seven test categories not applicable and why
- Verification commands run
- Docs impact decision
- Remaining untested/staging risk
```

