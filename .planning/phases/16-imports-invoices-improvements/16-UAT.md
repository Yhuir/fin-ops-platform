---
status: partial
phase: 16-imports-invoices-improvements
source:
  - docs/modules/imports-invoices/implementation-notes.md
  - docs/modules/imports-bank-transactions/implementation-notes.md
  - docs/modules/read-models/implementation-notes.md
  - docs/modules/runtime-workers/implementation-notes.md
  - .planning/phases/16-imports-invoices-improvements/16-RELEASE-RUNBOOK.md
  - .planning/phases/16-imports-invoices-improvements/16-OPS-EXECUTION-PACK.md
started: 2026-06-21T00:30:19+08:00
updated: 2026-06-21T00:35:28+08:00
---

## Current Test

[testing paused - 2 items outstanding]

## Tests

### 1. Import file API smoke
expected: |
  In-memory invoice and bank XLSX fixtures preview successfully, confirm through `/imports/files/confirm`,
  background `file_import` jobs succeed, and confirmed batches keep the correct import domain, route, batch type, and row count.
result: pass
evidence: |
  `PYTHONPATH=backend/src:. python - <<'PY' ...` returned `status=passed`.
  Cases passed: `input_invoice_file_confirm`, `output_invoice_file_confirm`, `bank_transaction_file_confirm`.
  Preview timings were 5.27ms, 6.2ms, 6.53ms; confirm enqueue timings were 0.7ms, 0.67ms, 0.87ms.

### 2. Import browser E2E smoke
expected: |
  Browser flows for bank transaction import and invoice import cover preview, confirm, slow preview locks,
  corrupt file handling, stale preview, confirm failure, and downstream fresh read model visibility.
result: pass
evidence: |
  `cd web && npx playwright test e2e/imports-invoices-flow.spec.ts e2e/imports-bank-transactions-flow.spec.ts`
  returned 13 passed in 36.6s, and was rerun later with 13 passed in 37.3s.

### 3. Local runtime dependency preflight
expected: |
  Local runtime dependencies are reachable before any real write smoke is attempted.
result: pass
evidence: |
  `./scripts/check-local-runtime.sh --dependencies-only` passed.
  PostgreSQL, Redis, and object storage were ready. PostgreSQL was reached through an SSH tunnel with
  connect+select latency around 359ms on the first run and 397ms on the rerun, so it is valid for functional checks
  but not a production performance benchmark.

### 4. Infra smoke default gate
expected: |
  Default infra smoke runs safely without writing real runtime state, and reports missing external write inputs explicitly.
result: pass
evidence: |
  `bash scripts/verify.sh infra-smoke` passed its contract tests and reported `external_input_required`
  for authenticated HTTP/browser/write-operation apply gates. No real enqueue/apply was executed.

### 5. Real write-operation SLO audit
expected: |
  Recent real invoice/bank import writes produce required durable refresh events and finish under the configured target.
result: issue
reported: "Read-only audit found missing required refresh events and slow completed events in the connected runtime."
severity: major
evidence: |
  `write_operation_slo_audit --operation invoice_import_confirmed --operation bank_import_confirmed --lookback-hours 72 --target-ms 5000`
  returned `status=fail`.
  Missing required samples included `workbench`, `workbench_relation`, `invoice_lifecycle`, and bank-side
  `bank_detail`/`bank_account_balance` in the connected runtime. Slow completed samples included
  `oa_pending_payment` around 26422ms and `cost_statistics` around 19608ms.
  Several missing items are expected to be fixed by the current worktree after deploy because current code now emits
  real bank detail/account balance refreshes and no longer creates snapshot import fact fan-out.

### 6. Orphaned legacy import fact dirty scope dry-run
expected: |
  Historical `import_facts_changed` dirty scopes with no active `import.fact.changed` outbox are detected
  without deleting data, and a rollback manifest is available before any apply.
result: issue
reported: "Dry-run found 42 orphaned legacy import fact dirty scopes in the connected runtime."
severity: major
evidence: |
  `scripts/check-read-model-scope-contracts.py --repair orphaned-import-facts --json` returned
  `orphaned_dirty_scope_count=42`, `cleanup.applied=false`.

### 7. Release and rollback runbook
expected: |
  A concrete release, cleanup, smoke, audit, and rollback runbook exists before any real runtime apply.
result: pass
evidence: |
  Created `.planning/phases/16-imports-invoices-improvements/16-RELEASE-RUNBOOK.md` and
  `.planning/phases/16-imports-invoices-improvements/16-OPS-EXECUTION-PACK.md`.
  It separates read-only checks from `--apply`, defines cleanup approval conditions, records rollback from
  `items[].row`, includes a rollback SQL template, and states completion criteria for true runtime closure.

## Summary

total: 7
passed: 5
issues: 2
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "Recent real invoice/bank import writes produce required durable refresh events and finish under the configured target."
  status: failed
  reason: "Read-only audit found missing required refresh events and slow completed events in the connected runtime."
  severity: major
  test: 5
  root_cause: "Current connected runtime has not yet deployed this worktree's import fan-out fixes, and existing read model handlers still show 19-26s tail latency for cost/OA/direction projections."
  artifacts:
    - path: "backend/src/fin_ops_platform/services/runtime_worker_handlers.py"
      issue: "Current worktree narrows future import fan-out, but connected runtime still contains old event history."
    - path: "backend/src/fin_ops_platform/tools/write_operation_slo_audit.py"
      issue: "Read-only audit correctly fails when required samples are missing or p95/p99 exceeds target."
  missing:
    - "Deploy current import fan-out fixes to staging or approved production window."
    - "Run write-operation SLO audit again after deploy and after orphaned cleanup."
    - "Profile `oa_pending_payment` and `cost_statistics` import-triggered refresh handlers if they still exceed target after fan-out shrink."
  debug_session: ".planning/debug/invoice-upload-workbench-sync.md"

- truth: "Historical `import_facts_changed` dirty scopes with no active `import.fact.changed` outbox are detected without deleting data, and a rollback manifest is available before any apply."
  status: failed
  reason: "Dry-run found 42 orphaned legacy import fact dirty scopes in the connected runtime."
  severity: major
  test: 6
  root_cause: "Old snapshot/import fact fan-out left dirty scope rows after matching legacy outbox events had already completed; no active outbox remains to complete those dirty scopes."
  artifacts:
    - path: "scripts/check-read-model-scope-contracts.py"
      issue: "Added `--repair orphaned-import-facts` dry-run/apply mode."
    - path: "backend/src/fin_ops_platform/services/read_model_scope_contract.py"
      issue: "Added orphaned import fact dirty scope report, apply cleanup, audit, and rollback manifest."
  missing:
    - "Run `scripts/check-read-model-scope-contracts.py --repair orphaned-import-facts --apply --reason production_orphaned_import_fact_cleanup --json` only in an approved window."
    - "Re-run App Status/dirty scope checks after cleanup."
  debug_session: ".planning/debug/invoice-upload-workbench-sync.md"
