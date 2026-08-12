# Workbench 正式关系 E2E 覆盖

日期：2026-08-12

| Spec | 状态 | 证据 |
| --- | --- | --- |
| `WB-REL-E2E-001` | covered | `web/e2e/workbench-relation-fanout.spec.ts`：confirm 后 bank details linked tags |
| `WB-REL-E2E-002` | covered | `web/e2e/pending-invoices-fanout.spec.ts`：confirm 后 pending invoices linked status |
| `WB-REL-E2E-003` | covered | `web/e2e/batch-accounting-flow.spec.ts`：submit/withdraw 与 relation barrier |
| `WB-REL-E2E-004` | covered | `web/e2e/turnover-ledger-flow.spec.ts`：closure/withdraw 与 grouped recovery |
| `WB-REL-E2E-005` | API/service covered | `tests/test_bank_details_service.py`、`tests/test_pending_invoice_service.py`、`tests/test_input_invoice_usage_oa_reverse_service.py`：非正式输入不驱动 linked-only 状态 |
| `WB-REL-E2E-006` | covered | `web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts` |
| `WB-REL-E2E-007` | covered | `web/e2e/workbench-network-recovery-flow.spec.ts`：幂等与冲突保护 |
| `WB-REL-E2E-008` | covered | `web/e2e/workbench-relations-oa-pending-fanout.spec.ts`、`output-invoice-red-relation-fanout.spec.ts`、`input-invoice-relation-fanout.spec.ts`、`cost-statistics-relation-fanout.spec.ts`、`workbench-relations-tax-offset-isolation.spec.ts` |
| `WB-REL-E2E-009` | covered | `web/e2e/bank-details-export-download.spec.ts`、`pending-invoices-export-download.spec.ts` |
| `WB-REL-E2E-010` | production audit covered | `tests/test_audit_workbench_relation_display_tool.py`、`scripts/audit-workbench-relation-display.sh` |
| `WB-REL-E2E-011` | covered | `tests/test_workbench_auth_context_idempotency.py`、`tests/test_workbench_write_characterization.py`、`tests/test_workbench_v2_api.py` 覆盖 canonical 成员矩阵、同类型/不等额确认和 note-only gate；`web/src/test/WorkbenchSelection.test.tsx` 覆盖同栏选择 |
| `WB-REL-E2E-012` | covered | `tests/test_workbench_relation_command_service.py` 覆盖 exact preview/submit、topology/history fingerprint、canonical/case reuse/unique owner 冲突与幂等重放；`tests/test_workbench_pair_relation_service.py::test_withdraw_restored_relation_version_advances_past_existing_topology_version`；`tests/test_workbench_relation_repository.py::test_relation_member_lock_includes_case_identity_and_persisted_members_in_stable_order`；`tests/test_workbench_write_characterization.py` 覆盖 HTTP 400/409 映射和稳定拓扑恢复；`web/src/test/WorkbenchSelection.test.tsx`、`web/e2e/workbench-withdraw-flow.spec.ts` 覆盖用户流程 |

“人工准入、关系级撤回、旧异常入口删除及内部转账统一写边界”的最终本地验证证据：全后端 4272 tests OK（65 项按外部 PostgreSQL 环境条件跳过）；撤回 command/pair/repository/UoW 专项 109 passed，no-OA/auth/routes/v2 相邻回归 185 passed；前端全量 Vitest 987 passed 且 production build 通过。默认 Chromium 全量 182 项中 181 项通过；唯一未通过项是与本需求无关的 OA 嵌入侧栏动画帧 P95 单次环境波动，该项独立重复运行 3/3 通过，本次关系确认、撤回、权限、stale 和异常入口相关 Browser 流程均通过。

上述本地证据覆盖 exact-set、同一事务重验、全局稳定锁序、topology version、fingerprint、幂等与用户流程。生产发布仍需 release gate、只读页面/API/队列和性能门禁；当前固定 production write smoke 不具备“同栏任意成员 + predecessor 拓扑恢复 + 同 key 重放”的合法 test-owned shape，因此不得用其他 shape 冒充本需求的生产写证据。真实 PostgreSQL 并发锁等待仍由发布后监控与后续专用 test-owned scenario 覆盖。

## 人工 confirm-link 内部转账路由门禁

- 状态：covered。`tests/test_no_oa_bank_batch_workbench_integration.py` 证明 mixed 与全 `internal_transfer` 银行选择统一进入 `manual_confirmed` command/UoW，`tests/test_workbench_auth_context_idempotency.py` 保护真实 UoW 幂等重放；独立 no-OA batch 回归与 `tests/test_read_model_architecture_guards.py` 共同证明“删除旧分流、保留独立功能”。
- 结果：全后端 4272 tests OK（65 项按外部 PostgreSQL 环境条件跳过）；相关 no-OA/auth/routes/v2 相邻矩阵 185 passed。
- Browser E2E 不新增 Spec ID：页面动作、权限、request/response shape、read model 与 worker 均未变化，内部 dispatch 不应通过浏览器私有实现细节断言。

旧 Browser candidate mock 不是当前业务状态，不再作为正式关系 E2E 事实源。生产发布以 canonical counts、fresh read models、520 fixed case 和页面 Audit 为最终数据证据。
