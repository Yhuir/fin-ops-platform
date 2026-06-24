# Module Contract - Workbench Relations

**Date:** 2026-06-24
**Worker:** T8 Module IO Contracts
**Status:** documentation/accounting closed
**Runtime behavior:** unchanged

## Module Basic Info

| Field | Content |
| --- | --- |
| Module key | `workbench-relations` |
| Module type | Resource module |
| Route | N/A; consumed by Workbench and downstream page APIs |
| Frontend entry | Workbench relation consumers and page feature APIs |
| Backend entry | `WorkbenchRelationCommandService`, `WorkbenchRelationReadFacade`, Workbench route owners |
| Read model | `workbench_relation` |
| Docs entry | `docs/modules/workbench-relations/README.md` |
| Refactor status | Contracted locally; production evidence deferred |

## IO Contract Reconciliation

### Inputs

| Input | Contract |
| --- | --- |
| Relation writes | Must enter `WorkbenchRelationCommandService` or an explicitly registered command port. |
| Relation reads | Downstream modules must use `WorkbenchRelationReadFacade` or a facade-wrapped request context. |
| Workbench group detail query | `GET /api/workbench/groups/detail` HTTP validation and facade delegation are owned by the extracted route owner; freshness proof remains in `WorkbenchQueryFacade.group_detail(...)`. |
| Legacy row detail fallback | Retained as local compatibility fallback only; cannot write relation facts, dirty scopes, readiness, cache or App Status. |

### Outputs

| Output | Contract |
| --- | --- |
| Canonical relation facts | Written to `app.workbench_pair_relations` and history through repository/UoW boundaries. |
| Read model distribution | `workbench_relation` distributes linked/candidate/unlinked relation evidence to downstream pages. |
| Affected scopes | Relation writes must enqueue `workbench_relation` and downstream read model scopes through durable queue contracts. |
| Route query payloads | Route-owner extractions must preserve status codes, payload shape and no-write behavior. |

### State / Events

- Active relation facts are canonical write facts; automatic decisions and candidates are not active relation facts until command service writes them.
- `relation_status='candidate'` is display evidence only.
- Workbench group/row detail route owners are read-only HTTP mapping surfaces.
- Frontend domain events remain refetch hints, not relation truth.

### Public / Internal Surfaces

Public surfaces:

- `WorkbenchRelationCommandService`
- `WorkbenchRelationReadFacade`
- Registered Workbench route owners for HTTP validation/mapping.
- `workbench_relation` read model repository/worker boundaries.

Internal-only surfaces:

- `WorkbenchPairRelationService` as page/service read fact source.
- Direct pair mutation from page modules.
- Legacy route compatibility fallback as write owner.
- `server.py` relation business helpers outside route/dependency wiring.

### Legacy Status

| Legacy path | Status | Constraint |
| --- | --- | --- |
| `WorkbenchRowDetailApiRoutes.legacy_row_detail` | `compat-only` | Local fallback only; guarded against relation writes, dirty/outbox, readiness, cache and App Status side effects. |
| Old Workbench action routes | quarantined compat path | Must not pollute modern `/api/workbench/actions/*` route owner/facade delegation. |
| Direct pair service callers in downstream modules | removed or blocked by guard where proven | Ambiguous finance repair paths require owner/deletion condition before removal. |
| `BatchAccountingService.repair_legacy_case_id_collisions` | test-observed compat repair | No active app/service caller outside service definition; do not remove without finance owner approval. |

### Read Model Refresh / Force Refresh

- `workbench_relation` refresh follows the shared gateway/scope policy and App Status operation barrier contract.
- Relation writes must enqueue affected month scopes and downstream scopes; transactional writers must keep scope writes in the same transaction.
- Force refresh follows `gateway_force_refresh` contract from `READ_MODEL_MANIFEST`.
- Workbench active generation remains a separate special-case read model and must not be mechanically merged into generic relation distribution.

### Partitioned Scoped Incremental Target

`workbench_relation` uses scoped incremental distribution by relation month scope; `all` is fan-out only. The target is local Python worker/read model distribution. Go admission is not active for this module.

## Test Contract

| Category | Applicability | Evidence |
| --- | --- | --- |
| 1. Business core unit tests | Applicable for relation modes/transitions | Existing Workbench relation service and command tests. |
| 2. Service-layer tests | Applicable | Existing command/read facade/repository/UoW tests and route-owner tests. |
| 3. API contract tests | Applicable | Workbench route tests protect group detail and action/row detail behavior. |
| 4. Read model/cache/background job tests | Applicable | `workbench_relation` manifest, refresh, facade and worker tests. |
| 5. Frontend component and interaction tests | Applicable for page flows | Existing Workbench/downstream Browser/Vitest coverage. |
| 6. E2E business-flow integration tests | Applicable | Existing Workbench relation fan-out flows; real production worker drain remains deferred. |
| 7. Existing feature regression tests | Applicable | Legacy quarantine guards and route-owner tests protect compat behavior. |

## Handoff Evidence Consumed

- `T1-server-route-owner.md`
- `T5-legacy-contamination.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/implementation-notes.md`

## Remaining Risk

Real relation table/history replay, production worker drain, App Status readiness, rollback evidence and browser production smoke remain deferred.
