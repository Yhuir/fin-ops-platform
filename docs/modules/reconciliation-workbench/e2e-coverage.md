# 关联台 Spec-first E2E Coverage

本文件把关联台 Spec 场景映射到现有自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `RECON-WB-E2E-001` | `covered` | `web/e2e/fixtures/workbenchFlow.ts`、`web/e2e/workbench-relation-fanout.spec.ts`、`web/e2e/workbench-network-recovery-flow.spec.ts`、`web/e2e/pending-invoices-fanout.spec.ts`、`web/e2e/workbench-stale-error-flow.spec.ts`、`web/src/test/WorkbenchSelection.test.tsx` | Browser 已覆盖 open group 三栏选择、preview、confirm submit、弹窗内 busy/重复提交锁定、operation barrier/fresh refetch 后 paired group 出现，以及 refetch 失败 committed error；`workbench-relation-fanout.spec.ts` 已为打开关联台、三栏选择、打开预览、确认提交记录 Playwright `operation-latency-*.json` 附件。 |
| `RECON-WB-E2E-002` | `covered` | `web/e2e/workbench-relation-fanout.spec.ts` | 真实 Chromium 从银行明细候选标签进入关联台，confirm 后回银行明细验证 `有oa` / `有发票`，并断言重新请求列表；返回银行明细操作记录 `operation-latency-*.json` 附件。 |
| `RECON-WB-E2E-003` | `covered` | `web/e2e/pending-invoices-fanout.spec.ts` | confirm 后回待找发票验证状态、发票号码和 OA 申请人。 |
| `RECON-WB-E2E-004` | `covered` | `web/e2e/workbench-withdraw-flow.spec.ts`、`tests/test_workbench_auth_context_idempotency.py`、`tests/test_workbench_relation_command_service.py`、`web/src/test/WorkbenchSelection.test.tsx` | Browser 已覆盖从 paired group 发起 withdraw preview/submit，断言 `operation_type`、`preview_id`、`submit_expected_versions` 回传、弹窗内 busy 锁定、operation barrier 和 fresh refetch 后 open recovery。 |
| `RECON-WB-E2E-005` | `covered` | `tests/test_workbench_sql_runtime.py`、`tests/test_workbench_auth_context_idempotency.py`、`tests/test_workbench_v2_api.py`、`tests/test_audit_workbench_relation_display_tool.py`、`web/e2e/workbench-relations-candidate-semantics.spec.ts` | 覆盖 automatic decision/candidate 不再投影为可见同组 linked 行；all-scope 和 groups page 过滤旧 visible automatic decision group；无 active relation 的撤回 preview/旧 operation submit 被拒绝且不 suppress candidate/decision；display audit 能发现 active generation 中残留的 visible automatic decision rows。 |
| `RECON-WB-E2E-006` | `covered` | `web/e2e/workbench-stale-error-flow.spec.ts`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/AppHealthStatusContext.test.tsx`、后端 read model tests | Browser 已覆盖 Workbench stale/refreshing 状态提示、不全局禁用无关 group、stale empty/false-empty 不显示真实空态、OA dirty/refreshing 禁用写入口、refresh failed 横幅且当前 active generation 仍可查看。 |
| `RECON-WB-E2E-007` | `covered` | `web/e2e/workbench-stale-error-flow.spec.ts`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/OperationBarrierApi.test.ts` | Browser 已覆盖确认关联写 API 失败时停留在预览弹窗、显示错误、行不移动且不启动 barrier；也覆盖写成功后 operation barrier timeout 与 fresh refetch failure 的 committed error，弹窗提示“关系已写入，关联台刷新未完成”、禁用备注和重试，且在 fresh refetch 成功前不触发本页 relation event 提前移动底层行。 |
| `RECON-WB-E2E-008` | `covered` | `web/e2e/workbench-permissions-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/SessionGate.test.tsx` | Browser 已覆盖 `read_export_only` 可查看 open/paired/processed/ignored 状态，但确认、撤回、异常 apply/cancel、ignore/unignore 写入口必须隐藏或 disabled，且不发出任何 Workbench mutation API 或 operation barrier。 |
| `RECON-WB-E2E-009` | `covered` | `web/e2e/workbench-exception-flow.spec.ts`、`tests/test_workbench_exception_*`、`tests/test_workbench_v2_api.py`、`web/src/test/WorkbenchExceptionModal.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`tests/test_platform_runtime_boundary_guards.py` | Browser 已覆盖 open group 异常处理 preview/apply、弹窗内 busy 锁定、operation barrier 与 Workbench fresh refetch 后 processed exception 展示、cancel exception 回到 open，以及发票 ignore -> ignored modal -> unignore 恢复；后端 apply API 返回受影响 scope 与 freshness targets，且不泄露 `all` scope。 |
| `RECON-WB-E2E-010` | `covered` | `web/e2e/workbench-large-scroll-flow.spec.ts`、`web/src/test/WorkbenchColumns.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` | Browser 已覆盖 205 个 open group 的长列表首屏分页、加载更多、搜索过滤到指定 group、详情抽屉打开/关闭、选择状态保持、三栏横向滚动同步和关键按钮无遮挡。真实生产 P95/P99 性能仍属 staging/生产风险。 |
| `RECON-WB-E2E-011` | `covered` | `web/e2e/workbench-network-recovery-flow.spec.ts`、API idempotency/rollback tests | Browser 已覆盖 confirm-link 一次网络失败后在同一预览重试成功、409 stale preview 不显示重试且要求重新预览、confirm/withdraw 预览提交期间双击不创建第二次 mutation。 |
| `RECON-WB-E2E-012` | `covered` | `web/e2e/workbench-stale-error-flow.spec.ts`、`web/e2e/workbench-permissions-flow.spec.ts`、`web/src/test/AppHealthStatusContext.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` | Browser 已覆盖 OA dirty/refreshing gate 禁用关联台写入口，并补回 `app_status` 存在时保留 `oaSync=dirty` 的前端契约；同时覆盖 `overall.write_safety.blocks_mutations=true` 下 `read_export_only`、`full_access`、`admin` 三类会话在 open/paired/processed/ignored 状态仍可查看读侧诊断，但确认、撤回、异常 apply/cancel、ignore/unignore 写入口隐藏或 disabled，且不发出任何 Workbench mutation API 或 operation barrier。 |
| `RECON-WB-E2E-013` | `covered` | `web/e2e/workbench-cash-special-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | Browser 已覆盖 full-access 用户从已配对银行流水更多菜单执行现金过账、买票成本确认和取消现金处理，断言三个 mutation 请求体携带完整 group row ids、买票弹窗必填校验、operation barrier 调用和成功后无隐藏 UI/browser 错误；权限矩阵已覆盖 read-export 下同一行级菜单不可触发且三个 durable endpoint 零调用。 |

## 现有 E2E 审计结论

- 保留：`workbench-relation-fanout.spec.ts`、`pending-invoices-fanout.spec.ts`。它们已按业务结果断言跨页面 fan-out，不只是断言当前代码行为。
- 保留并后续加强：`batch-accounting-flow.spec.ts`、`turnover-ledger-flow.spec.ts`。它们证明 relation barrier 和 bucket/group 恢复，但属于下游 owner 页面发起的 relation 流程。
- 已补齐：网络恢复、重复提交、409 stale preview、App Health write-safety 和已配对现金流水特殊处理浏览器场景。
- 不需要推翻重写：当前 workbench 相关 e2e 没有发现保护错误行为的测试；主要问题是覆盖粒度还停留在 smoke。

## 下一轮补测建议

1. 继续推进 `workbench-relations` candidate/linked 负面语义、non-fresh 诊断和更多下游页面 fan-out。
2. 推进 `bank-details` 关系标签、导出、筛选分页和大表格滚动的 Spec-first Browser E2E。
