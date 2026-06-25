# server-py:turnover-ledger-route-owner-audit

Status: `analysis-closed`

Date: 2026-06-25

## Boundary

Audit remaining `/api/turnover-ledger*` route ownership in `Application` and select the next bounded local implementation slice.

This is a local `server.py` route-owner audit. It does not claim turnover ledger module closure, global modular IO closure, or production PostgreSQL/worker/browser evidence closure.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
- `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`
- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_read_facade.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `docs/modules/turnover-ledger/README.md`
- `docs/modules/turnover-ledger/state-machine.md`
- `docs/modules/turnover-ledger/tests.md`

Commands used for the local audit:

```bash
PYTHONPATH=backend/src python3 - <<'PY'
import ast
from pathlib import Path
p=Path("backend/src/fin_ops_platform/app/server.py")
t=ast.parse(p.read_text())
for n in sorted((n for n in ast.walk(t) if isinstance(n,(ast.FunctionDef, ast.AsyncFunctionDef)) and "turnover_ledger" in n.name.lower()), key=lambda n:n.lineno):
    print(f"{n.lineno}:{n.name}")
PY
rg -n "turnover_ledger|TurnoverLedger|/api/turnover-ledger|_handle_api_turnover" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_turnover_ledger.py tests/test_platform_runtime_boundary_guards.py
```

## Current Route Ownership

`TurnoverLedgerApiRoutes` already owns domain/read helpers for grouped and flat ledger payloads, relation detail, relation extra domain behavior, export preview/export service calls, relation confirm/withdraw domain calls and extra snapshot ownership.

`TurnoverLedgerReadFacade` already wraps route-owner reads and export behavior for `list_ledger(...)`, `get_relation(...)`, `get_relation_extra(...)`, `export_preview(...)` and `export(...)`.

`Application` still owns direct dispatch branches and HTTP callbacks for:

- read/export/GET group:
  - `_handle_api_turnover_ledger(...)`;
  - `_handle_api_turnover_ledger_export_preview(...)`;
  - `_handle_api_turnover_ledger_export(...)`;
  - `_handle_api_turnover_ledger_relation(...)`;
  - `_handle_api_turnover_ledger_relation_extra(...)`;
  - `_handle_api_turnover_ledger_tag_selection(...)`;
- mutation group:
  - `_handle_api_turnover_ledger_tag_selection_update(...)`;
  - `_handle_api_turnover_ledger_bank_row_tags_batch(...)`;
  - `_handle_api_turnover_ledger_relation_extra_update(...)`;
  - `_handle_api_turnover_ledger_confirm(...)`;
  - `_handle_api_turnover_ledger_closure_confirm(...)`;
  - `_handle_api_turnover_ledger_closure_withdraw(...)`;
  - `_handle_api_turnover_ledger_withdraw(...)`.

## Findings

- The read/export/GET callbacks are thin HTTP/query/error/file-response wrappers around `TurnoverLedgerReadFacade`, `TurnoverLedgerApiRoutes` and `AppSettingsService`.
- The mutation callbacks are intentionally thicker: they own mutation session checks, JSON body parsing, actor/tenant/idempotency extraction, facade selection, stale precondition error mapping, validation conflicts and Workbench idempotency errors.
- Existing tests inspect several mutation callbacks directly with `inspect.getsource(...)`, so collapsing mutation routes first would be a broader implementation/testing migration.
- The safest next implementation slice is read/export/GET callback collapse:
  - move GET route dispatch/query parsing and read/export response mapping into a route owner/facade boundary;
  - keep mutation callbacks in `Application` for follow-up audits;
  - preserve read model freshness metadata, export limit errors, filename/XLSX response headers and unknown relation errors.

## Decision

Select `server-py:turnover-ledger-read-export-route-callback-collapse` as the next bounded local implementation slice.

Expected implementation shape:

- add route-owner dispatch for read/export/GET turnover ledger endpoints only;
- inject explicit JSON response, export response and tag-selection payload ports as needed;
- remove app-owned read/export/GET callbacks after migration;
- leave mutation callbacks for later dedicated write-boundary audits;
- add/update Guard and targeted turnover ledger API/read-facade tests.

## Stop Gates For Next Boundary

- Do not change turnover ledger write behavior.
- Do not change stale preconditions, operation barrier targets, Workbench relation command boundaries, export limits or `turnover_ledger` freshness semantics.
- Do not migrate mutation callbacks in the read/export slice.
- Do not run production validation or mutation.
