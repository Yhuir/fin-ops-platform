---
phase: 35-bank-flow-rule-batch-live-candidates
verified: 2026-07-29T17:45:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 5/6
  gaps_closed:
    - "生产 main release 9aff73707 已部署，May 188500 候选、Page Audit、worker 隔离和 20 次 warm-read P95 均通过。"
  gaps_remaining: []
  regressions: []
gaps: []
---

# Phase 35: 流水规则批量处理实时统一事实源候选 Verification Report

**Phase Goal:** Derive unsubmitted bank-flow rule candidates directly from current canonical bank, classification, rule, settings and active-relation facts on page access; preserve submitted/history facts and canonical relation writes; remove the asynchronous canonical-draft runtime chain.

**Verified:** 2026-07-29T17:45:00Z
**Status:** passed
**Re-verification:** Yes — after production root-cause fix `9aff73707`
**Examined range:** `eebfb699f..9aff73707`

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Unsubmitted candidates are live-derived in one canonical snapshot and never depend on a prewritten draft, worker, replay or cache. | ✓ VERIFIED | Direct canonical page/API/query path and retired runtime negative guards remain intact; quick regression checks pass. |
| 2 | The known 188500 internal-transfer pair appears once in May with the correct two members and single-side amount. | ✓ VERIFIED | Production May API returns exactly one `188500.00` candidate, `bank_flow_rule_batch_c701b64fff0b373f30a8`, with `txn_imported_0024` and `txn_imported_0057`; Bank Details reports both as `internal_transfer`. |
| 3 | Submit/withdraw preserves the existing formal relation UoW, idempotency and history while rereading the live candidate at command time. | ✓ VERIFIED | `PostgresStateStore` creates one outer transaction, passes its `PostgresTransaction` to `PostgresWorkbenchRepository`, and both repository `run_in_transaction` calls directly reuse it because `PostgresTransaction` has no `transaction()` factory. Four mutation failure-injection cases prove zero committed relation/history/batch/event facts. |
| 4 | Audit detects missing expected candidates, UI facets reflect actual candidates, and the canonical-draft owner/producer/event/deploy chain is deleted. | ✓ VERIFIED | Audit omission, runtime deletion, worker registry and no-OA isolation regression tests pass; frontend/UI path was unchanged by the four closure commits. |
| 5 | Targeted local gates, one pushed `main` release and authenticated production probes prove correctness, isolation and sub-second warm reads without Redis or a new read model. | ✓ VERIFIED | `9aff73707` pushed to `origin/main` and deployed as `main-9aff7370-20260730014104`; 20 authenticated warm reads were all HTTP 200 with p50 `354.487ms`, p95/max `456.474ms`; Page Audit is pass/fresh/drained. |
| 6 | 不新增 Redis、read model、表、队列、worker 或缓存版本体系。 | ✓ VERIFIED | Closure commits only repair transaction ownership, local persistence, lifecycle test, cross-month matching and docs; no runtime infrastructure was added. |

**Score:** 6/6 truths verified

## Closed Gap Verification

### 1. PostgreSQL caller-owned UoW

The previous split-transaction blocker is closed.

| Check | Evidence | Status |
|---|---|---|
| Outer transaction ownership | `PostgresStateStore.save_bank_flow_rule_batch_mutation` calls `run_in_transaction(self._connection, write)` once. | ✓ |
| Transaction propagation | `write(transaction)` constructs `PostgresWorkbenchRepository(transaction)` and uses it for relation/history and batch/events. | ✓ |
| No nested/independent transaction | `PostgresTransaction` exposes query/write methods but no `transaction()` method. `run_in_transaction` therefore executes callbacks directly against the supplied object. Introspection check printed `PostgresTransaction.transaction: False`. | ✓ |
| Candidate guard in same transaction | guard receives the same `transaction` before either writer runs. | ✓ |
| Relation/history in same transaction | transaction-bound `PostgresWorkbenchRelationRepository` reaches `run_in_transaction(transaction, write)`, which directly reuses that transaction. | ✓ |
| Batch/events in same transaction | transaction-bound `PostgresWorkbenchRepository.save_bank_flow_rule_batch_items` follows the same direct reuse path. | ✓ |
| Failure rollback | event-write injection covers `single_submit`, `selected_row_submit`, `withdraw`, and `reset_submitted`; each records exactly one transaction, one rollback and empty committed relation/history/batch/events. | ✓ |

The failure-injection repository is a transaction-behavior fake rather than a live PostgreSQL integration. This is sufficient for the local structural proof because the production `PostgresTransaction` reuse branch is directly observable in code; production release smoke remains part of SC5.

### 2. Local StateStore atomic replacement

`ApplicationStateStore.save_bank_flow_rule_batch_mutation` now:

1. validates candidate guard and explicit batch IDs before persistence;
2. acquires the existing reentrant local pickle lock;
3. merges changed relation facts and replaces the bank-flow batch snapshot in one in-memory payload;
4. calls `_save_local_pickle` once;
5. writes `state.pkl.tmp` and atomically replaces `state.pkl`.

`load_bank_flow_rule_batches` prefers the new `state.pkl` key and retains the legacy dedicated-file fallback for existing local data. Standalone save/load, mutation round-trip and injected atomic-replace failure tests all pass; the failure test reloads a new store instance and sees only the old relation and batch snapshots.

### 3. Lifecycle cleanup

`test_settings_reset_is_explicit_full_history_maintenance` now asserts:

```python
self.assertNotIn("bank_flow_rule_batch_canonical_draft", domains)
```

The exact test and the full affected lifecycle test file pass. No production source reference to the retired lifecycle domain was reintroduced.

### 4. Cross-month unique ownership

`BankBatchService._build_internal_transfer_batches` now groups candidate rows by amount across the repository's bounded month-edge window, pairs within 48 hours, and sets:

- `pair_scope_month = min(outflow_month, inflow_month)`;
- batch identity from that owner month, amount and member IDs;
- evidence `scope_owner_rule=earliest_member_month`;
- single-side `total_amount=Decimal(amount_text)`.

The regression proves:

- May 31 outflow + June 1 inflow produces one candidate for May;
- repeated May reads preserve identity and members;
- amount remains `188500.00`;
- June returns no duplicate candidate;
- active relation occupancy still removes the candidate.

## Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `postgres_state_store.py` | one caller-owned PostgreSQL mutation transaction | ✓ VERIFIED | Same transaction object reaches guard, relation/history and batch/events. |
| `postgres_repositories/workbench_relation.py` | transaction-bound relation/history writer | ✓ VERIFIED | Internal wrapper reuses supplied `PostgresTransaction`; no nested factory exists. |
| `postgres_repositories/workbench.py` | transaction-bound batch/event writer | ✓ VERIFIED | Same reuse behavior; batch and event writes remain in outer transaction. |
| `state_store.py` | local no-half-write mutation | ✓ VERIFIED | one locked payload and one atomic `state.pkl` replacement, with legacy read fallback. |
| `bank_batch_service.py` | cross-month deterministic owner | ✓ VERIFIED | earliest member month is part of scope and identity. |
| `test_postgres_state_store.py` | four mutation rollback proof | ✓ VERIFIED | all four subtests pass with one rollback and empty committed facts. |
| `test_state_store.py` | local load/save and rollback proof | ✓ VERIFIED | legacy domain isolation, successful round-trip and failed-replace preservation pass. |
| `test_derived_data_lifecycle_service.py` | retired domain remains absent | ✓ VERIFIED | stale positive assertion replaced by negative guard. |
| Phase 35 module/boundary docs | describe implemented transaction and cross-month contracts | ✓ VERIFIED | README, boundary I/O, state machine, tests matrix and canonical facts agree with code. |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `PostgresStateStore.save_bank_flow_rule_batch_mutation` | `PostgresWorkbenchRepository` | constructor receives outer `PostgresTransaction` | ✓ WIRED | repaired in `4f5434576`. |
| transaction-bound workbench repository | relation/history writer | `run_in_transaction(PostgresTransaction, ...)` | ✓ WIRED | direct callback branch; no inner transaction factory. |
| transaction-bound workbench repository | batch/event writer | `run_in_transaction(PostgresTransaction, ...)` | ✓ WIRED | direct callback branch; same outer rollback scope. |
| local mutation | relation + bank-flow snapshots | one `_save_local_pickle` | ✓ WIRED | atomic temp-file replacement. |
| canonical query edge window | shared internal-transfer builder | rows across adjacent month boundary | ✓ WIRED | owner month prevents duplicate candidate. |

## Data-Flow Trace (Level 4)

| Artifact | Data | Source | Result | Status |
|---|---|---|---|---|
| Live candidate list | bank rows/categories/rules/active relations/formal items | one canonical PostgreSQL snapshot | real live candidates | ✓ FLOWING |
| Formal mutation | candidate guard → relation/history → batch/events | one caller-owned PostgreSQL transaction | commit together or rollback together | ✓ ATOMIC |
| Local formal mutation | relation snapshot + batch snapshot | one locked `state.pkl` payload | atomic replacement | ✓ ATOMIC |
| Cross-month transfer | May 31 + June 1 members | ±2-day query edge window + shared builder | May owner only | ✓ FLOWING |

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| eight exact closure tests | exact node IDs across Postgres/local/lifecycle/application service | `8 passed in 0.24s` | ✓ PASS |
| four full affected test files | `pytest -q test_postgres_state_store.py test_state_store.py test_derived_data_lifecycle_service.py test_bank_flow_rule_batch_application_service.py` | `115 passed in 0.37s` | ✓ PASS |
| Audit omission, old runtime deletion, worker registry and no-OA isolation | four exact node IDs | `4 passed in 0.93s` | ✓ PASS |
| expanded affected backend regression | 15 bank-flow/state-store/Audit/runtime/no-OA test files | `462 passed, 1 skipped in 36.72s` | ✓ PASS |
| frontend interaction regression | `BankFlowRuleBatchPage.test.tsx` | `30 passed` | ✓ PASS |
| Python lint | `bash scripts/verify.sh lint` | `All checks passed!` | ✓ PASS |
| docs verification | `bash scripts/verify.sh docs` | exit 0 | ✓ PASS |
| diff whitespace | `git diff --check d3885d85b..HEAD` | exit 0 | ✓ PASS |
| authenticated production correctness | May unsubmitted + Bank Details + Page Audit | one `188500.00`/2-row candidate; both rows `internal_transfer`; Audit pass/fresh/drained with 0 issue | ✓ PASS |
| authenticated production performance | 3 warmups + 20 measured May reads | HTTP 200; p50 `354.487ms`, p95/max `456.474ms`; all <800ms and <1s | ✓ PASS |
| production runtime isolation | systemd state | retired bank-flow worker inactive/disabled; legacy no-OA worker active/enabled | ✓ PASS |

No full workspace suite or browser E2E was rerun. Re-verification used the complete affected backend/API/runtime set, the focused frontend component suite, production build/deploy and authenticated read-only production probes.

## Probe Execution

No checked-in `probe-*.sh` is declared for Phase 35. Production probes used the repository token loader plus read-only authenticated HTTP and systemd status checks; no real candidate was submitted or withdrawn.

| Probe | Result | Status |
|---|---|---|
| Local structural and behavioral closure | 119 tests plus lint/docs/diff gates passed | ✓ PASS |
| Production release | `origin/main` `9aff73707`, release `main-9aff7370-20260730014104` | ✓ PASS |
| Production 188500 | candidate `bank_flow_rule_batch_c701b64fff0b373f30a8`, rows `txn_imported_0024` / `txn_imported_0057`, amount `188500.00`, month `2026-05` | ✓ PASS |
| Production Audit | `pass / fresh / drained`, 0 issue | ✓ PASS |
| Production runtime isolation | retired bank-flow worker inactive/disabled; no-OA worker active/enabled | ✓ PASS |
| Production P95 | 20/20 HTTP 200; p95/max `456.474ms` | ✓ PASS |

## Requirements Coverage

`35-01-PLAN.md` declares `requirements: []`; Roadmap success criteria remain the authoritative contract.

| Requirement | Status | Evidence |
|---|---|---|
| Roadmap SC1 | ✓ SATISFIED | direct canonical snapshot/no draft runtime |
| Roadmap SC2 | ✓ SATISFIED | May 188500 production candidate plus cross-month unique-owner regressions |
| Roadmap SC3 | ✓ SATISFIED | one PostgreSQL UoW and four failure rollback proofs |
| Roadmap SC4 | ✓ SATISFIED | Audit/UI/runtime removal regression |
| Roadmap SC5 | ✓ SATISFIED | exact main release deployed; authenticated correctness, Audit, isolation and P95 evidence passed |
| Plan no-new-runtime must-have | ✓ SATISFIED | no new infrastructure |

## Anti-Patterns Found

No new `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, placeholder, empty handler or hardcoded empty user-visible data pattern was found in the four closure commits.

The previous nested/independent transaction anti-pattern and misleading cross-month test contract are removed. The local test name `test_bank_flow_rule_batches_use_independent_local_snapshot_file` is now historical wording—the assertion verifies no-OA/bank-flow domain isolation, while bank-flow storage intentionally moved into atomic `state.pkl`. This is informational and does not affect behavior.

## Remaining Risk

The authorized real business candidate was not submitted or withdrawn; production mutation correctness therefore remains protected by local transaction/UoW, conflict and rollback tests rather than a mutation of the real `188500` facts. This is deliberate production safety, not a release blocker. Read performance passed the current data volume with substantial margin; future row-count growth should continue to be watched by the existing HTTP SLO tooling.

## Human Verification Required

None. The remaining item is objective production release/probe evidence, not subjective visual or UX verification.

## Gaps Summary

The code, release and production evidence blockers are closed. Phase 35 passes all six observable truths with no Redis, new read model, queue or worker.

---

_Verified: 2026-07-29T17:45:00Z_
_Verifier: the agent (gsd-verifier)_
