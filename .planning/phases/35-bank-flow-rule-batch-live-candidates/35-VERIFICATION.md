---
phase: 35-bank-flow-rule-batch-live-candidates
verified: 2026-07-29T16:43:56Z
status: gaps_found
score: 5/6 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/6
  gaps_closed:
    - "Submit/withdraw preserves the existing formal relation UoW, idempotency and history while rereading the live candidate at command time."
    - "受影响 lifecycle test 已更新为断言退休 draft domain 不会恢复，定向与受影响文件回归均通过。"
    - "May 31/June 1 内部转账现在由最早成员月份唯一拥有，相邻月份不重复。"
  gaps_remaining:
    - "Roadmap SC5 的 pushed main release 与 authenticated production correctness/isolation/P95 evidence 尚未执行。"
  regressions: []
gaps:
  - truth: "Targeted local gates, one pushed `main` release and authenticated production probes prove correctness, isolation and sub-second warm reads without Redis or a new read model."
    status: partial
    reason: "本地 targeted gates 已通过，但本次明确禁止 push、deploy 和生产操作；因此 pushed main release、真实 188500、隔离/System Audit、queue/worker 和至少 20 次 sub-second warm-read P95 证据仍不存在。"
    artifacts:
      - path: ".planning/phases/35-bank-flow-rule-batch-live-candidates/35-01-SUMMARY.md"
        issue: "production-validation 仍记录为 pending，未包含 pushed/deployed exact SHA 或认证生产探针结果。"
      - path: "backend/src/fin_ops_platform/services/postgres_repositories/bank_flow_rule_batch_canonical_query.py"
        issue: "性能合同仍需生产数据量下的认证 warm-read 采样；repository 读取月份窗口后由 application service 内存过滤、排序和分页。"
    missing:
      - "在获得授权后 push exact verified main SHA 并执行标准 deploy。"
      - "执行认证生产只读 188500/Audit/旧 runtime 零引用/no-OA 隔离/queue-worker/System Audit 检查。"
      - "记录至少 20 次 warm read 并证明 P95 < 1s；若失败则以 EXPLAIN/查询统计定位。"
---

# Phase 35: 流水规则批量处理实时统一事实源候选 Verification Report

**Phase Goal:** Derive unsubmitted bank-flow rule candidates directly from current canonical bank, classification, rule, settings and active-relation facts on page access; preserve submitted/history facts and canonical relation writes; remove the asynchronous canonical-draft runtime chain.

**Verified:** 2026-07-29T16:43:56Z  
**Status:** gaps_found  
**Re-verification:** Yes — after commits `4f5434576`, `f0e3b741f`, `c1fc045f2`, `3d5059d78`  
**Examined range:** `eebfb699f..3d5059d78`

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Unsubmitted candidates are live-derived in one canonical snapshot and never depend on a prewritten draft, worker, replay or cache. | ✓ VERIFIED | Direct canonical page/API/query path and retired runtime negative guards remain intact; quick regression checks pass. |
| 2 | The known 188500 internal-transfer pair appears once in May with the correct two members and single-side amount. | ✓ VERIFIED（code-level） | Exact May test passes. May 31/June 1 test now returns one stable `188500.00` candidate owned by `2026-05`, and returns none for `2026-06`. |
| 3 | Submit/withdraw preserves the existing formal relation UoW, idempotency and history while rereading the live candidate at command time. | ✓ VERIFIED | `PostgresStateStore` creates one outer transaction, passes its `PostgresTransaction` to `PostgresWorkbenchRepository`, and both repository `run_in_transaction` calls directly reuse it because `PostgresTransaction` has no `transaction()` factory. Four mutation failure-injection cases prove zero committed relation/history/batch/event facts. |
| 4 | Audit detects missing expected candidates, UI facets reflect actual candidates, and the canonical-draft owner/producer/event/deploy chain is deleted. | ✓ VERIFIED | Audit omission, runtime deletion, worker registry and no-OA isolation regression tests pass; frontend/UI path was unchanged by the four closure commits. |
| 5 | Targeted local gates, one pushed `main` release and authenticated production probes prove correctness, isolation and sub-second warm reads without Redis or a new read model. | ✗ FAILED — RELEASE EVIDENCE PENDING | Local gates pass, but push/deploy/production probes are explicitly outside this re-verification and have not occurred. |
| 6 | 不新增 Redis、read model、表、队列、worker 或缓存版本体系。 | ✓ VERIFIED | Closure commits only repair transaction ownership, local persistence, lifecycle test, cross-month matching and docs; no runtime infrastructure was added. |

**Score:** 5/6 truths verified

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
| Python lint | `bash scripts/verify.sh lint` | `All checks passed!` | ✓ PASS |
| docs verification | `bash scripts/verify.sh docs` | exit 0 | ✓ PASS |
| diff whitespace | `git diff --check d3885d85b..HEAD` | exit 0 | ✓ PASS |
| authenticated production correctness/performance | not run by explicit scope restriction | no evidence | ✗ PENDING |

No full workspace suite was rerun. Re-verification used the four complete affected backend test files plus exact cross-boundary isolation/Audit/runtime checks.

## Probe Execution

No checked-in `probe-*.sh` is declared for Phase 35. Push, deploy and authenticated production probes remain intentionally unexecuted.

| Probe | Result | Status |
|---|---|---|
| Local structural and behavioral closure | 119 tests plus lint/docs/diff gates passed | ✓ PASS |
| Production 188500/Audit/isolation/P95 closure | prohibited in this re-verification | ✗ PENDING |

## Requirements Coverage

`35-01-PLAN.md` declares `requirements: []`; Roadmap success criteria remain the authoritative contract.

| Requirement | Status | Evidence |
|---|---|---|
| Roadmap SC1 | ✓ SATISFIED | direct canonical snapshot/no draft runtime |
| Roadmap SC2 | ✓ SATISFIED（code-level） | May 188500 plus cross-month unique-owner regressions |
| Roadmap SC3 | ✓ SATISFIED | one PostgreSQL UoW and four failure rollback proofs |
| Roadmap SC4 | ✓ SATISFIED | Audit/UI/runtime removal regression |
| Roadmap SC5 | ✗ PARTIAL | local gates pass; push/deploy/production/P95 absent |
| Plan no-new-runtime must-have | ✓ SATISFIED | no new infrastructure |

## Anti-Patterns Found

No new `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, placeholder, empty handler or hardcoded empty user-visible data pattern was found in the four closure commits.

The previous nested/independent transaction anti-pattern and misleading cross-month test contract are removed. The local test name `test_bank_flow_rule_batches_use_independent_local_snapshot_file` is now historical wording—the assertion verifies no-OA/bank-flow domain isolation, while bank-flow storage intentionally moved into atomic `state.pkl`. This is informational and does not affect behavior.

## Remaining Risk

The only remaining contract gap is release evidence. The canonical query still reads the bounded month window and performs candidate building/filtering/sorting/pagination in application memory. Local tests establish correctness but cannot establish production P95 under real row counts, category lateral joins and active-relation cardinality. SC5 therefore remains failed until the authorized exact-SHA deployment and authenticated warm-read measurements complete.

## Human Verification Required

None. The remaining item is objective production release/probe evidence, not subjective visual or UX verification.

## Gaps Summary

The code blockers from the previous verification are closed. Phase 35 is locally ready for the authorized release workflow, but the phase as a whole cannot be marked `passed` because its Roadmap contract explicitly includes a pushed `main` release and authenticated production correctness, isolation and sub-second warm-read proof.

No later milestone phase exists to defer this item.

---

_Verified: 2026-07-29T16:43:56Z_  
_Verifier: the agent (gsd-verifier)_
