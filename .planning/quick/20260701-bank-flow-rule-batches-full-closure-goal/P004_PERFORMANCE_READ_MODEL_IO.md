# P004 Performance And Read Model I/O Closure

Use this as the next bounded execution prompt inside the `/goal` controller.

```text
Goal:
Reduce `bank-flow-rule-batches` page/API latency by eliminating unnecessary all-scope refreshes and tightening read model I/O. Keep behavior and public API shapes stable. Do not split the frontend in this slice.

Evidence to inspect first:
- `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/BASELINE_AUDIT.md`
- `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/P002_IMPLEMENTATION_REPORT.md`
- `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/P003_IMPLEMENTATION_REPORT.md`
- `docs/modules/bank-flow-rule-batches/boundary-io.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py`
- `backend/src/fin_ops_platform/services/bank_batch_application_service.py`
- `backend/src/fin_ops_platform/services/bank_batch_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `tests/test_bank_flow_rule_batch_application_service.py`
- `tests/test_bank_flow_rule_batch_routes.py`
- `tests/test_bank_flow_rule_batch_read_model_refresh_producer.py`
- `tests/test_no_oa_bank_batch_tag_selection_api.py`
- performance-sensitive existing tests around operation freshness/read models.

Known hot spots to verify:
- `BankFlowRuleBatchApplicationService._refresh_bank_flow_rule_batch_runtime_snapshot()` refreshes `scope_key="all"` before detail/withdraw/reset.
- `detail_payload(batch_id)` should be able to refresh only the affected batch/month when the batch can be loaded from bank-flow state/read model.
- `withdraw_batch(batch_id)` should avoid full rebuild when it can resolve the batch and affected months from current bank-flow storage.
- `reset_submitted_bank_flow_rule_batches()` may need all submitted candidates but should not do duplicate all-scope rebuilds after every operation.
- Read model stale checks should use dedicated `bank_flow_rule_batch_source_versions_summary` and avoid row-by-row full scans where a summary can prove unchanged/fresh.

Allowed implementation scope:
- Backend service/read-model/repository performance changes only.
- Add narrow repository/service helpers if they expose clear I/O, e.g. load batch by id, submitted batch summary, scope-key resolver, or source-version summary.
- Tests proving no-OA behavior remains unchanged.
- Docs updates for changed read model/performance contracts.
- No frontend split or UI redesign in this slice.

Architecture constraints:
- Keep `bank_flow_rule_batch` physical tables and read model rows as the bank-flow source of truth.
- Do not read no-OA physical tables or settings as bank-flow runtime fallback.
- Do not hide stale read models as fresh.
- Writes must still return operation barrier targets.
- Optimizations must preserve relation command audit/rollback semantics.
- Avoid broad caches unless they sit behind freshness gates.

Required analysis:
1. Measure or statically classify current API paths:
   - list unsubmitted/submitted;
   - detail;
   - submit-selection;
   - withdraw;
   - reset-submitted;
   - tag-rules GET/PUT;
   - rebaseline dry-run/apply.
2. For each path, document read model source, write model source, refresh trigger, expected complexity, and whether it can avoid full `all` refresh.
3. Identify which paths are already O(1)/scoped and which are O(all rows/all batches).

Required edits:
1. Replace avoidable `scope_key="all"` refreshes with scoped refresh or direct bank-flow batch lookup where safe.
2. Use dedicated bank-flow source version summary for freshness/unchanged checks where available.
3. Ensure reset and rebaseline do one bounded candidate scan, not repeated full rebuilds.
4. Add tests proving:
   - detail no longer forces all-scope refresh when a current batch is available;
   - withdraw refreshes only necessary scope or skips rebuild with valid source data;
   - reset enqueues/persists bank-flow scopes without duplicate all-scope rebuilds;
   - stale/missing read model paths still enqueue refresh and return non-fresh status;
   - no-OA legacy path is unchanged.
5. Update docs with performance contracts and residual measured risks.

Verification to run:
- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_postgres_repositories_boundaries.py -q`
- `git diff --check -- backend/src/fin_ops_platform/services backend/src/fin_ops_platform/app tests docs .planning/quick/20260701-bank-flow-rule-batches-full-closure-goal`

Stop condition:
- The main bank-flow read/write paths have documented complexity and tests for scoped refresh behavior.
- Avoidable all-scope refreshes are removed or explicitly justified in docs.
- Public API behavior and freshness fail-closed semantics remain intact.
- Generate exactly one next prompt `P005_*` based on the resulting diff and tests, but do not create a backlog.
```
