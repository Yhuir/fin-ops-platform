# Module Contract - Reconciliation Workbench

**Date:** 2026-06-24
**Worker:** T8 Module IO Contracts
**Status:** documentation/accounting closed
**Runtime behavior:** unchanged

## Module Basic Info

| Field | Content |
| --- | --- |
| Module key | `reconciliation-workbench` |
| Module type | Page module |
| Route | `/` |
| Frontend entry | Workbench page/components/features |
| Backend entry | Workbench route owners, `WorkbenchQueryFacade`, `WorkbenchWriteFacade` |
| Read model | `workbench` active generation, plus `workbench_relation` distribution |
| Docs entry | `docs/modules/reconciliation-workbench/README.md` |
| Refactor status | Contracted locally; production evidence deferred |

## IO Contract Reconciliation

### Inputs

| Input | Contract |
| --- | --- |
| Workbench query | Must read through Workbench query facade / active generation boundary; route owners only validate HTTP and map response. |
| Workbench write action | Modern `/api/workbench/actions/*` actions delegate to `WorkbenchWriteFacade` and relation command boundaries. |
| Group detail query | `GET /api/workbench/groups/detail` route owner validates `month`, `zone` and `group_id`; freshness/source-version proof remains in `WorkbenchQueryFacade.group_detail(...)`. |
| Legacy action routes | Quarantined compatibility paths; cannot contaminate modern action route owner/facade boundaries. |

### Outputs

| Output | Contract |
| --- | --- |
| Active generation payload | Published atomically; building/failed generations are not user-visible fresh facts. |
| Action response | Must preserve existing payload/status and return operation/freshness targets where writes affect visibility. |
| Relation output | Canonical relation writes and relation distribution are owned by `workbench-relations`. |

### State / Events

- `workbench` remains active generation, not a generic read model rebuild path.
- `workbench_relation` is a separate distribution read model for downstream pages.
- Frontend events are refresh hints only.
- Legacy routes are not new contract surfaces for modern flows.

### Public / Internal Surfaces

Public surfaces:

- Workbench page feature API.
- `WorkbenchQueryFacade` and route-owner HTTP mapping for query routes.
- `WorkbenchWriteFacade` for modern action routes.
- Operation barrier targets returned by write flows.

Internal-only surfaces:

- `server.py` business helpers for Workbench logic.
- Legacy action route internals as modern action owners.
- Direct pair relation writes outside `WorkbenchRelationCommandService`.
- Go/Fiber/Go Worker implementation before admission gates.

### Legacy Status

| Legacy path | Status | Constraint |
| --- | --- | --- |
| Old `/workbench/actions/*` routes | quarantined compat | Test-observed compatibility only; do not expand as modern owner. |
| Workbench row/detail fallback | compat-only where explicitly wired | No writes, queue, readiness, cache or App Status side effects. |
| Legacy exception/action helpers removed in prior slices | removed/guarded | Must not return without explicit new owner decision. |

### Read Model Refresh / Force Refresh

- `workbench` force refresh uses active-generation-specific contract.
- Known affected month writes should target concrete month scopes; `all` aggregate-only refresh is not a broad fan-out substitute when concrete months are known.
- Operation barrier may release on operation projection / relation target as documented by the concrete action; page fresh gate still applies to subsequent reads.

### Partitioned Scoped Incremental Target

`workbench` preserves active generation atomic publish with month shards and an aggregate `all` view built from active shards. `workbench_relation` remains the scoped incremental relation distribution boundary. Go workbench compute admission is deferred until evidence gates pass.

## Test Contract

| Category | Applicability | Evidence |
| --- | --- | --- |
| 1. Business core unit tests | Applicable | Matching/amount/action business tests stay with Workbench services. |
| 2. Service-layer tests | Applicable | Facade/route-owner/action service tests. |
| 3. API contract tests | Applicable | Workbench route tests protect validation and response shape. |
| 4. Read model/cache/background job tests | Applicable | Workbench active generation and relation read model tests. |
| 5. Frontend component and interaction tests | Applicable | Workbench page/action tests and Browser flows. |
| 6. E2E business-flow integration tests | Applicable | Confirm/withdraw/split/exception flows; production worker drain deferred. |
| 7. Existing feature regression tests | Applicable | Legacy route quarantine and action route owner guards. |

## Handoff Evidence Consumed

- `T1-server-route-owner.md`
- `T5-legacy-contamination.md`
- `T7-go-admission-evidence.md`
- `docs/modules/reconciliation-workbench/implementation-notes.md`

## Remaining Risk

Production active generation rebuild, relation fan-out, browser smoke and Go hot-path admission evidence remain deferred.
