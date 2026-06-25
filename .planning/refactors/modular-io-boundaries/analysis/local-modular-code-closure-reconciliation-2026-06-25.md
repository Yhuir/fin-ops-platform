# Local Modular Code Closure Reconciliation - 2026-06-25

**Boundary:** `planning:local-modular-code-closure-reconciliation`
**Status:** `local-closure-reconciled`
**Production command:** none
**Code mutation:** none
**Worker threads created:** none

## Goal

Restart the modular IO refactor from the corrected local-first T0 prompt. This reconciliation checks the live code state and selects the next local implementation boundary before any production browser/admin/write validation.

## Evidence Read

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/index.md`
- `docs/app-architecture/README.md`
- `docs/modules/README.md`
- `00-REQUIREMENTS.md`
- `03-REFACTOR-STATE-MACHINE.md`
- `04-IMPLEMENTATION-ROADMAP.md`
- `autonomous/STATE.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/NEXT-PROMPT.md`
- `prompts/06-t0-meta-orchestrator-goal.md`
- CodeGraph status and file index
- AST metrics for `server.py` and `postgres_repositories/read_models.py`

## Live Code Facts

CodeGraph is initialized and current enough for structural planning:

- indexed files: `985`
- nodes: `35387`
- edges: `89833`

Current backend local-code facts:

| File / area | Current evidence | Classification |
| --- | --- | --- |
| `backend/src/fin_ops_platform/app/server.py` | `21217` lines, `Application` has `1018` methods, including `205` `_handle_api_*` methods. It still has large residual groups: `workbench=233`, `etc=106`, `import=89`, `read_model=70`, `background_job/job=41`, `settings=29`. | `needs-route-owner-extraction` / `needs-service-boundary-extraction` |
| `backend/src/fin_ops_platform/app/routes_*.py` | Route owner modules exist for bank details, batch accounting, cost statistics, ETC business batches, Workbench actions, no-OA, pending invoices, turnover ledger, tax, output collections and others. | `local-closed` for extracted surfaces, not global closure |
| `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` | `11415` lines, `PostgresReadModelRepository` has `158` methods. Grouping by method names shows Workbench-heavy ownership (`workbench=76`) plus pending/OA/invoice/bank/tax/cost/search/no-OA groups. | `needs-repository-owner-split` |
| `backend/src/fin_ops_platform/services/*read_model*.py` | `46` indexed read-model service/repository/gateway files exist, including manifest, freshness, query gateway, refresh gateway, scope policy and per-module repository ports. | `local-closed` for many ports/gateways; shared SQL owner still open |
| Production browser/admin/write evidence | Previously hard-stopped by runner/admin/write gates. | `production-evidence-after-local-closure` |

## Residual Area Classification

| Residual area | Classification | Reason |
| --- | --- | --- |
| `server.py` ETC import/reconciliation residual handlers | `needs-route-owner-extraction` | `server.py` still owns many ETC/import route handlers while `routes_etc.py` currently covers only a smaller route-owner subset. This is a bounded, non-production local refactor candidate. |
| `server.py` Workbench residual handlers | `needs-route-owner-extraction` | Many Workbench action routes were extracted, but `server.py` still owns broad Workbench query/read-model/status surfaces. Higher risk because Workbench active generation semantics are special. |
| `server.py` settings/data reset/background job residuals | `needs-service-boundary-extraction` | App still owns HTTP-adjacent orchestration and background job helpers that need explicit owner classification before further extraction. |
| `postgres_repositories/read_models.py` Workbench SQL group | `needs-repository-owner-split` | Workbench methods dominate the repository. Any split must preserve active generation atomic publish semantics. |
| `postgres_repositories/read_models.py` smaller module SQL groups | `needs-repository-owner-split` | Many module ports exist, but the shared repository still holds SQL implementation for multiple modules. |
| Existing read model gateways and scope policy | `local-closed` for current contracts | `ReadModelRefreshGateway`, `ReadModelQueryGateway`, manifest and scope policy files exist and have tests. |
| Production validation | `production-evidence-after-local-closure` | Browser/admin/write validation is the final evidence layer, not the next local code step. |

## Next Boundary Selection

Selected next boundary:

`server-py:etc-reconciliation-route-owner-residual-audit`

Why this boundary:

- It is local-code-only and does not require staging, `PGSQL_URL`, secrets or production mutation.
- It targets a concrete `server.py` residual group with high method count (`etc=106`, `import=89`) and existing route-owner precedent in `routes_etc.py`.
- It should produce a narrow extraction plan for one ETC/import/reconciliation route subset instead of a broad line-count rewrite.
- It can be followed by implementation slices with focused static/API regression guards.

Rejected for this immediate boundary:

- Production browser/admin/write validation: local implementation closure is not proven.
- Broad `server.py` splitting: too large and likely to violate ownership boundaries.
- Workbench read-model SQL split first: valuable but higher-risk because Workbench active generation semantics require more careful sequencing.
- Go/Fiber/Go Worker: still candidate-gated and not admitted.

## Required Next Slice

The next slice must:

1. Read `docs/modules/etc-tickets/README.md`, `docs/modules/imports-etc-invoices/README.md`, `docs/modules/reconciliation-workbench/README.md`, and existing ETC tests.
2. Use CodeGraph to inspect `Application` ETC/import handlers and `EtcBusinessBatchApiRoutes`.
3. Classify one bounded handler group as:
   - extract now;
   - compat-only delegate;
   - already route-owned;
   - blocked by unclear contract.
4. Write an analysis file with the proposed first implementation boundary.
5. Do not mutate production.

## Seven Test Category Decision

This reconciliation slice changes planning/controller state only.

- Business core unit tests: not applicable; no business rule changed.
- Service-layer tests: not applicable; no service changed.
- API contract tests: not applicable for this slice; the selected next implementation boundary will need API/static route guards.
- Read model/cache/background job tests: not applicable; no runtime behavior changed.
- Frontend component/interaction tests: not applicable.
- End-to-end business flow tests: not applicable.
- Existing feature regression tests: not applicable for this planning-only slice.

## State-Machine Impact

The existing state machine already distinguishes implementation, verification, production validation and closure. No state definition change is required in this slice. Controller accounting must change because `NEXT-PROMPT.md` still points at the old production hard stop and must be reset to local-first implementation work.
