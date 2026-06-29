# Prompt: Canonical Facts Main Closure Controller

**Status:** User-authorized specialized entrypoint
**Use with:** `/goal`
**Purpose:** Run a high-throughput GSD controller to fully modularize the business source of truth: PostgreSQL canonical facts plus the business modules that own them. This prompt is not a read model closure prompt. It must not take over read model runtime ownership from `07-read-model-main-closure-controller.md`.

## Core Judgment

Clear boundaries and I/O reduce cross-module interference, but they are not sufficient by themselves. Closure requires all of these:

- one owner per canonical fact family;
- explicit allowed write ports and read ports;
- forbidden direct writes and forbidden legacy facts;
- state/event/downstream contracts;
- tests or static guards that keep old paths from returning;
- docs that match code.

The goal is modular isolation by evidence, not just a document that says modules are isolated.

## Core Objective

Complete canonical facts modularization closure.

Every PostgreSQL business fact family must have:

- canonical fact family name;
- PostgreSQL tables;
- owner module;
- allowed write entrypoints;
- allowed read entrypoints;
- public surface and internal-only surface;
- input I/O;
- output I/O;
- state machine owner;
- permission and audit owner;
- downstream dirty scope/domain event/operation barrier output;
- repair/migration/backfill owner;
- legacy code removal status;
- tests or guard coverage;
- docs closure.

Old-code policy is strict:

- Old production source-of-truth code must be removed from normal app/API/worker chains, not wrapped, renamed, hidden behind compatibility branches, or documented as acceptable debt.
- A new canonical facts chain is not closed while an old chain can still write, read, recover, bootstrap, refresh, or override the same business fact in production.
- Migration, audit, rollback and one-off repair tooling may remain only as a temporary safety exception when it is outside production hot paths, has an owner, has caller inventory, has dry-run/audit/rollback rules, and has deletion criteria. Such tooling is a deferred item or blocker; it is not closure. The controller must prefer deleting the tool in the same wave when there is no active named operation requiring it.
- If an old code path is not needed for an active, named migration/audit/rollback operation, delete it completely in the same slice instead of isolating it.
- Tests, dev convenience, historical compatibility, inactive migration scripts, uncalled services, or "no current caller" are not valid reasons to keep production-reachable old source-of-truth code. Update or delete tests and callers so the old path can be removed; do not keep old production code alive to satisfy old tests.
- Isolation is only a contamination barrier for the transition window. It is not a target architecture. Any isolated old path must be listed in `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and final reports as `pending-removal` or `blocked-removal`, with the exact reason it was not deleted yet.
- Do not leave dual-write, fallback-read, bootstrap snapshot, compatibility API, legacy repair, local pickle, Mongo snapshot, GridFS fallback, `state:*` JSON, or direct non-owner write code in the new canonical facts chain.
- Static guards or tests must prevent removed production source-of-truth paths from returning.
- Final closure cannot contain any production-reachable `pending-removal` old source-of-truth path. Transitional isolation is allowed only to prevent contamination while preparing deletion; it must either be deleted before closure or reported as a hard blocker.
- Do not treat a legacy route, legacy service, local pickle implementation, Mongo app snapshot path, GridFS fallback reader, full-state snapshot path, direct external adapter source, or compatibility API as harmless just because it has no current caller. If it can be reached from app/API/worker production wiring or can be re-enabled without an explicit tool-only guard, remove it.

Default target state:

- `app.*` business facts are canonical facts.
- `read_model.*` is derived projection only.
- `job.*` and `audit.*` are runtime/audit facts, not business facts.
- Redis, RabbitMQ, frontend events, local pickle, full snapshot, `state:*` JSON and Mongo app snapshot are not business source of truth.
- Read model refresh still follows the 07 read model closure contract. This prompt only declares and uses the existing boundary; it must not redesign it.

## Conflict Policy With 07 Read Model Closure

This prompt may run while `07-read-model-main-closure-controller.md` is active only if file ownership stays separate.

### Read Only From 07

You may read these files to understand contracts, but do not edit them unless the 07 controller is stopped and the user explicitly assigns them to this run:

- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- `backend/src/fin_ops_platform/services/read_model_query_gateway.py`
- `backend/src/fin_ops_platform/services/runtime_queue.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/modules/read-models/`
- `.planning/refactors/modular-io-boundaries/autonomous/`

### Canonical Facts Ownership

This run may edit:

- `.planning/refactors/canonical-facts-boundaries/`
- `docs/architecture/module-boundaries/canonical-facts.md`
- `docs/modules/canonical-facts/`
- `docs/architecture/module-boundaries/README.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/architecture/module-boundaries/maintenance.md`
- `docs/modules/README.md`
- owner module docs under `docs/modules/<owner>/`
- owner module services/repositories/tests when implementing canonical write/read boundary closure.

If a required change would touch a 07-owned shared file, stop that slice and record `blocked-by-read-model-controller`, then choose another canonical facts slice.

## Throughput Mandate

Optimize for short elapsed time.

- Work in macro-waves, not one table or one field at a time.
- Batch all owner-matrix docs in one wave.
- Batch owner module `boundary-io.md` updates by fact family group.
- Batch static guard/test updates by forbidden path class.
- Batch code movement only when one owner boundary and one rollback point are clear.
- Verify at wave gates, not after every paragraph or helper.
- Do not add new abstractions where an existing service, repository, facade, UoW, or module doc can carry the boundary.

Recommended macro-wave order:

1. Global conflict preflight and current-state reconciliation.
2. PostgreSQL schema and canonical fact family inventory.
3. Global canonical facts architecture docs and owner matrix.
4. Owner module docs/I/O closure for all canonical fact families.
5. Legacy source-of-truth removal inventory and deletion plan.
6. Static guard/test wave for forbidden source-of-truth paths.
7. Code boundary closure for the highest-risk direct cross-module writes, excluding 07-owned read model runtime files.
8. Repair/migration/backfill runbook boundary closure.
9. Cross-module regression and docs verification sweep.
10. Final canonical facts closure audit and next prompt generation.

## Start Prompt

Paste this whole section into Codex as a `/goal` prompt:

```text
/goal

You are Codex working in /Users/yu/Desktop/fin-ops-platform.

Objective: fully close the canonical facts modularization refactor. Canonical facts means PostgreSQL business source of truth in app.* plus each business module that owns those facts. This is not the read model closure controller. If 07-read-model-main-closure-controller is active, avoid every read model runtime shared file listed in this prompt and continue with canonical facts docs, owner modules, forbidden source paths, tests and code slices that do not overlap.

Run a GSD closed-loop workflow:
1. analyze current state;
2. select the largest safe canonical facts macro-wave;
3. execute the wave;
4. verify;
5. update planning state;
6. generate exactly one next prompt from the completed state;
7. immediately execute that next prompt unless a hard stop is hit.

Do not stop after writing analysis if a safe canonical facts wave remains.

Primary outcome:
- every canonical fact family has one owner module;
- every owner module has clear write/read I/O;
- non-owner modules cannot write owner facts directly;
- legacy full snapshot, local pickle, state:* JSON, Mongo app snapshot, GridFS fallback, Redis, RabbitMQ, frontend events and read_model.* cannot become source of truth;
- all old production source-of-truth code paths are removed, not merely documented;
- write operations declare downstream domain event, dirty scope, affected scopes/months, operation barrier target or an explicit not-applicable reason;
- docs, tests and static guards prevent old paths from silently returning.

Branch/worktree safety:
- Start by running `git status --short --branch`.
- If the working tree has unrelated dirty files, do not overwrite them. Continue only with non-overlapping files or stop with a precise file conflict.
- If another controller is actively editing the same worktree, do not edit. Write analysis only and stop with `blocked-by-shared-worktree`.
- Before editing, acquire a local write lease:
  `mkdir /tmp/fin-ops-canonical-facts-write.lock`
- If the lock exists, do not edit. Continue analysis or stop with `waiting-for-canonical-facts-write-lease`.
- Release the lock with `rmdir /tmp/fin-ops-canonical-facts-write.lock` after commit, after deciding no edits are needed, or before final stop.
- Never force-push, rebase, reset, delete branches, or revert user changes.

Required context to read before editing:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/index.md
- docs/app-architecture/README.md
- docs/app-architecture/runtime-and-ownership.md
- docs/architecture/persistence-and-read-models.md
- docs/architecture/module-boundaries/README.md
- docs/architecture/module-boundaries/inventory.md
- docs/modules/README.md
- docs/modules/read-models/boundary-io.md
- docs/operations/runtime-worker-governance.md
- .planning/refactors/modular-io-boundaries/README.md
- .planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md
- .planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md
- .planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md
- .planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md

Use CodeGraph before code edits:
- `codegraph_status` first.
- `codegraph_context` for the selected canonical fact owner.
- `codegraph_impact` before modifying a shared service, repository, facade, route, UoW, worker-adjacent producer, or module-level helper.
- Use `rg` for literal table names, legacy labels, env keys, route names and state:* keys.

Create or update these planning artifacts:
- `.planning/refactors/canonical-facts-boundaries/README.md`
- `.planning/refactors/canonical-facts-boundaries/ANALYSIS.md`
- `.planning/refactors/canonical-facts-boundaries/PLAN.md`
- `.planning/refactors/canonical-facts-boundaries/autonomous/STATE.md`
- `.planning/refactors/canonical-facts-boundaries/autonomous/JOURNAL.md`
- `.planning/refactors/canonical-facts-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/canonical-facts-boundaries/analysis/canonical-facts-reconciliation-<date>.md`
- `.planning/refactors/canonical-facts-boundaries/analysis/canonical-facts-wave-<N>-<slug>.md`
- `.planning/refactors/canonical-facts-boundaries/analysis/canonical-facts-final-closure-report-<date>.md`

Long-term docs to create or update:
- `docs/architecture/module-boundaries/canonical-facts.md`
- `docs/modules/canonical-facts/README.md`
- `docs/modules/canonical-facts/boundary-io.md`
- `docs/modules/canonical-facts/state-machine.md`
- `docs/modules/canonical-facts/tests.md`
- `docs/modules/canonical-facts/e2e-spec.md`
- `docs/modules/canonical-facts/e2e-coverage.md`
- `docs/modules/canonical-facts/implementation-notes.md`
- `docs/architecture/module-boundaries/README.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/architecture/module-boundaries/maintenance.md`
- `docs/modules/README.md`
- affected owner module docs under `docs/modules/<owner>/`

Do not edit these files while 07 read model closure is active unless the user explicitly assigns them:
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- `backend/src/fin_ops_platform/services/read_model_query_gateway.py`
- `backend/src/fin_ops_platform/services/runtime_queue.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/modules/read-models/`
- `.planning/refactors/modular-io-boundaries/autonomous/`

Canonical fact family inventory must scan PostgreSQL migrations and current repositories for at least:
- imports/files: `app.import_batches`, `app.import_batch_rows`, `app.import_files`, `app.file_objects`
- invoice pool: `app.invoices`
- bank facts: `app.bank_transactions`, `app.bank_transaction_categories`, `app.bank_transaction_category_events`, `app.bank_transaction_category_confirmations`
- workbench facts: `app.workbench_pair_relations`, `app.workbench_pair_relation_history`, `app.workbench_row_overrides`, `app.workbench_exception_cases`, `app.no_oa_bank_batches`, `app.no_oa_bank_batch_events`, matching/idempotency facts
- OA projection facts: `app.oa_applications`, `app.oa_application_items`, `app.oa_attachments`, `app.oa_sync_*`, `app.oa_attachment_invoice_cache*`, `app.manual_oa_imports`
- tax facts: tax certified import facts and `app.tax_offset_plans`
- ETC facts: `app.etc_*` facts and ETC batch invoice links
- turnover facts: `app.turnover_relations`, `app.turnover_relation_events`, `app.turnover_ledger_extras`
- output invoice collection facts
- input invoice usage OA reverse facts
- OA pending payment bank relation facts
- settings and credentials facts
- runtime/audit facts under `job.*` and `audit.*`, clearly marked as runtime/audit, not business canonical facts

Owner matrix rules:
- A table can have one business owner family.
- A shared repository can know SQL, but it is not the business owner merely because it contains SQL.
- A read model owner is not the canonical fact owner.
- Non-owner modules may read through public ports or explicitly documented direct SQL read paths.
- Non-owner modules may write only through owner command/application service, facade, UoW or explicit adapter.
- Repair/migration/backfill tools must have owner, dry-run, audit, rollback/cleanup and production-path exclusion.

Definition of done:
1. `canonical-facts.md` exists and defines source layers, owner matrix, input I/O, output I/O, forbidden paths and current gaps.
2. `docs/modules/canonical-facts/` exists with README, boundary-io, state-machine, tests, e2e-spec, e2e-coverage and implementation-notes.
3. `docs/architecture/module-boundaries/README.md`, `inventory.md`, `maintenance.md` and `docs/modules/README.md` point to canonical facts before read model implementation work.
4. Every major canonical fact family has an owner module and a documented allowed write/read path.
5. Each affected owner module `boundary-io.md` states owned canonical facts, allowed writers/readers, downstream outputs, forbidden paths and deletion conditions.
6. Old production source-of-truth paths are removed. If a path cannot be removed because it is a required active migration/audit/rollback tool, it must be isolated outside production API/worker hot paths with owner, caller list, dry-run/audit/rollback rules and deletion criteria; that exception is a `pending-removal` or `blocked-removal` item, not closure.
7. No old code can still write, read, recover, bootstrap, refresh, or override canonical business facts in the production app/API/worker chain. If this cannot be proven, stop with a blocker instead of marking closure.
8. Any old code classified as not required for current migration/audit/rollback must be deleted, with tests or static guards proving it cannot re-enter the new canonical facts chain.
9. Compatibility APIs, fallback facades, direct legacy adapters, local snapshot/pickle stores, Mongo/GridFS readers, bootstrap loaders, repair services and historical migration helpers must be deleted when they are production-reachable or not tied to an active named migration/audit/rollback operation.
10. Every isolated old tool path has a concrete next deletion prompt; no final closure may be claimed while any old source-of-truth path remains merely isolated.
11. Final closure must have zero production-reachable legacy source-of-truth code and zero unresolved `pending-removal` legacy source-of-truth items. If any legacy path still exists because deletion requires an external migration/audit/rollback decision, mark the goal blocked with the exact deletion prerequisite instead of marking complete.
12. Static guards or tests exist for any code change that could let a forbidden path return.
13. No 07-owned read model runtime shared file is edited unless explicitly assigned.
14. `bash scripts/verify.sh docs` and `git diff --check` pass.
15. Targeted tests for touched code pass.
16. The final report states exactly what remains blocked by 07 read model closure, if anything.

Wave acceptance checklist:
- No new business source of truth is created.
- No read_model.*, Redis, RabbitMQ, frontend event, local pickle, full snapshot, state:* JSON or Mongo app snapshot becomes source of truth.
- No non-owner direct canonical write is introduced.
- No direct dirty/outbox/readiness redesign is introduced by this controller.
- No old production source-of-truth path remains in the normal app/API/worker chain.
- No hidden API shape or business behavior change.
- Seven test categories are evaluated for each code-changing wave.
- Docs impact is handled.
- Existing unrelated dirty files are not overwritten.

Verification policy:
Always run after docs waves:
```bash
bash scripts/verify.sh docs
git diff --check
```

Run after code waves:
```bash
PYTHONPATH=backend/src python3 -m unittest <targeted tests> -v
bash scripts/verify.sh docs
git diff --check
```

If a command is unavailable, run the closest smaller check and record why.

Hard stops:
- Same worktree is being actively edited by another controller and no safe non-overlapping docs-only work remains.
- Required change would edit 07-owned read model runtime files while 07 is active.
- Canonical owner cannot be inferred from migrations, services, docs or code and guessing would change business behavior.
- Code change would alter API response shape, business rules, permission behavior or production data semantics without explicit requirement.
- Tests fail and cannot be fixed inside the selected canonical facts wave.
- A production operation would require secrets, broad mutation, manual DB edits to canonical facts, fake readiness, unbounded queue/worker replay, or unclear rollback.

Loop rule:
At the end of every wave:
1. Update `STATE.md`.
2. Append `JOURNAL.md`.
3. Write exactly one next executable prompt to `NEXT-PROMPT.md`.
4. Immediately execute that next prompt unless a hard stop was hit.
5. Do not generate multiple speculative prompts.
6. Do not stop after prompt generation while safe work remains.

Final answer in Chinese must include:
- current branch and commit;
- changed files summary;
- canonical fact family owner matrix summary;
- modules whose boundary-io was updated;
- tests added/changed;
- seven test category coverage;
- verification commands;
- files intentionally not touched because of 07 read model closure;
- remaining blockers/deferred items;
- why no read model runtime conflict was introduced;
- proof that old production source-of-truth code was removed from the modular canonical facts chain, or the exact blocker preventing removal.

Start now:
1. Run conflict preflight.
2. Build full canonical facts reconciliation.
3. Execute the largest safe non-overlapping macro-wave.
4. Verify.
5. Generate and execute the next prompt until canonical facts closure is proven or a hard stop is real.
```

## PSCF Levels

Use these levels in state files and reports:

- PSCF-L0 contract-only: docs/owner matrix only.
- PSCF-L1 guarded contract: docs plus static guard or test for the most important forbidden path.
- PSCF-L2 local owner closure: owner module write/read ports are locally testable and non-owner direct writes are blocked or absent.
- PSCF-L3 legacy removal: old production source-of-truth paths are removed. Migration/audit/rollback exceptions may only be isolated as `pending-removal` or `blocked-removal`; they keep the item below closure until deleted or until the user explicitly accepts them as permanent non-production tooling.
- PSCF-L4 production evidence: deployed/runtime evidence proves canonical writes, downstream signals and read model handoff converge without forbidden source paths.

Do not claim PSCF-L4 from docs alone.

## Notes

- Boundary/I/O clarity is necessary, not sufficient. The closure proof is tests, guards, owner ports and old-path removal.
- The fastest safe path is not to merge this with 07. Keep canonical facts focused on `app.*` ownership and let 07 own `read_model.*` runtime closure.
