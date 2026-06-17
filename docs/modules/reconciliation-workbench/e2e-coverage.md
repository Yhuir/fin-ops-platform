# 关联台 Spec-first E2E Coverage

本文件把关联台 Spec 场景映射到现有自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `RECON-WB-E2E-001` | `partial` | `web/e2e/fixtures/workbenchFlow.ts`、`web/e2e/workbench-relation-fanout.spec.ts`、`web/e2e/pending-invoices-fanout.spec.ts`、`web/src/test/WorkbenchSelection.test.tsx` | Browser 已覆盖 open group 三栏选择、preview、confirm submit 和 paired group 出现；缺“弹窗内阻塞直到 fresh refetch”的浏览器级断言和 refetch 失败负面场景。 |
| `RECON-WB-E2E-002` | `covered` | `web/e2e/workbench-relation-fanout.spec.ts` | 真实 Chromium 从银行明细候选标签进入关联台，confirm 后回银行明细验证 `有oa` / `有发票`，并断言重新请求列表。 |
| `RECON-WB-E2E-003` | `covered` | `web/e2e/pending-invoices-fanout.spec.ts` | confirm 后回待找发票验证状态、发票号码和 OA 申请人。 |
| `RECON-WB-E2E-004` | `partial` | `tests/test_workbench_auth_context_idempotency.py`、`tests/test_workbench_relation_command_service.py`、`web/src/test/WorkbenchSelection.test.tsx` | 后端/Vitest 覆盖强；缺真实 Browser 从 paired group 发起 withdraw preview/submit 的场景。 |
| `RECON-WB-E2E-005` | `partial` | `tests/test_workbench_auth_context_idempotency.py`、`tests/test_workbench_v2_api.py`、`web/src/test/WorkbenchSelection.test.tsx` | 已覆盖 API 和前端 mapper；缺 Browser 自动候选 split/suppress 流。 |
| `RECON-WB-E2E-006` | `partial` | `web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/AppHealthStatusContext.test.tsx`、后端 read model tests | 缺 Browser stale/refreshing/failed UI 场景。 |
| `RECON-WB-E2E-007` | `partial` | `web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/OperationBarrierApi.test.ts` | 缺 Browser 写 API 失败、barrier 超时、fresh refetch 失败的用户可见断言。 |
| `RECON-WB-E2E-008` | `partial` | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/SessionGate.test.tsx` | role matrix 覆盖全页面读写 gate，但未逐一覆盖关联台每个写入口。 |
| `RECON-WB-E2E-009` | `partial` | `tests/test_workbench_exception_*`、`tests/test_workbench_v2_api.py`、`tests/test_platform_runtime_boundary_guards.py` | 缺 Browser 异常处理 apply/cancel/ignore。 |
| `RECON-WB-E2E-010` | `missing` | `web/src/test/WorkbenchColumns.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` | 缺真实浏览器大数据/三栏滚动/详情遮挡场景。 |
| `RECON-WB-E2E-011` | `partial` | API idempotency/rollback tests | 缺 Browser 网络失败和重试。 |
| `RECON-WB-E2E-012` | `partial` | `web/src/test/AppHealthStatusContext.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` | 缺 Browser App Health write safety / OA dirty gate 场景。 |

## 现有 E2E 审计结论

- 保留：`workbench-relation-fanout.spec.ts`、`pending-invoices-fanout.spec.ts`。它们已按业务结果断言跨页面 fan-out，不只是断言当前代码行为。
- 保留并后续加强：`batch-accounting-flow.spec.ts`、`turnover-ledger-flow.spec.ts`。它们证明 relation barrier 和 bucket/group 恢复，但属于下游 owner 页面发起的 relation 流程。
- 需要新增：关联台自身 withdraw、split candidate、stale/refreshing、失败恢复、异常处理、大数据滚动。
- 不需要推翻重写：当前 workbench 相关 e2e 没有发现保护错误行为的测试；主要问题是覆盖粒度还停留在 smoke。

## 下一轮补测建议

1. 新增 `web/e2e/workbench-withdraw-flow.spec.ts`：从关联台 paired group 发起 withdraw preview/submit，验证弹窗内阻塞、operation barrier、fresh refetch 和 open recovery。
2. 新增 `web/e2e/workbench-stale-error-flow.spec.ts`：mock stale/refreshing/failure，验证页面提示和写入口 gate。
3. 新增 `web/e2e/workbench-candidate-split-flow.spec.ts`：automatic decision split/suppress。
4. 扩展 permissions role matrix：逐项覆盖关联台 confirm、withdraw、exception 写入口。

