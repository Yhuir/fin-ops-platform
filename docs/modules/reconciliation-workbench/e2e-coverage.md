# 关联台 E2E 覆盖

日期：2026-08-12

| Spec | 状态 | 证据 | 合同 |
| --- | --- | --- | --- |
| `RECON-WB-E2E-001` | covered | `tests/test_workbench_auth_context_idempotency.py` 覆盖每种支持类型的同栏确认、重复/未解析/不支持成员拒绝及 `requires_note` 门禁；`tests/test_workbench_write_characterization.py` 覆盖 preview；`tests/test_workbench_v2_api.py` 覆盖不等额同类型提交；`web/src/test/WorkbenchSelection.test.tsx` 覆盖同栏选择 | 未配对选择 -> preview -> 正式 relation -> fresh paired/unpaired group；自动 matching 不放宽 |
| `RECON-WB-E2E-002` | covered | `web/e2e/workbench-relation-fanout.spec.ts` | confirm 后银行明细重新读取正式 linked 标签 |
| `RECON-WB-E2E-003` | covered | `web/e2e/pending-invoices-fanout.spec.ts` | confirm 后待找发票重新读取正式 linked 状态 |
| `RECON-WB-E2E-004` | covered | `tests/test_workbench_relation_command_service.py` 的 `test_preview_withdraw_relation_requires_exact_active_member_set`、`test_withdraw_relation_case_and_explicit_rows_must_identify_same_exact_relation`、`test_withdraw_preview_fingerprint_changes_with_topology_and_history_identity`、canonical/case reuse/unique owner 冲突测试与幂等重放测试；`tests/test_workbench_pair_relation_service.py::test_withdraw_restored_relation_version_advances_past_existing_topology_version`；`tests/test_workbench_relation_repository.py::test_relation_member_lock_includes_case_identity_and_persisted_members_in_stable_order`；`tests/test_workbench_write_characterization.py` 的 HTTP 400/409 映射及稳定拓扑恢复；`web/src/test/WorkbenchSelection.test.tsx`、`web/e2e/workbench-withdraw-flow.spec.ts` | paired/unpaired active relation -> exact-set preview/submit -> topology/history fingerprint -> current/predecessor transaction locks -> canonical/case/owner revalidation -> previous stable topology/singleton recovery |
| `RECON-WB-E2E-005` | API/integration covered | `tests/test_workbench_relation_grouping.py`、`tests/test_workbench_v2_api.py` | 无 active relation 的历史非正式 metadata 不合并、不隐藏；对象保持 singleton unpaired |
| `RECON-WB-E2E-006` | covered | `web/e2e/workbench-stale-error-flow.spec.ts` | refreshing/stale/failed 不伪装 fresh，false-empty 与写入被阻止 |
| `RECON-WB-E2E-007` | covered | `web/e2e/workbench-network-recovery-flow.spec.ts` | 写失败不移动；写成功而 refetch 失败时明确提示并避免重复写入 |
| `RECON-WB-E2E-008` | covered | `web/src/test/WorkbenchSelection.test.tsx`、`web/e2e/workbench-permissions-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` 覆盖未配对工具栏精确文案“异常处理”不存在、read-export relation 动作禁用且统一抽屉写动作隐藏 | read-export/full/admin 的读取和 mutation gate；旧人工入口不存在 |
| `RECON-WB-E2E-009` | covered | `web/e2e/workbench-exception-flow.spec.ts`、`web/src/test/groupDisplayModel.test.ts`、`web/src/test/WorkbenchExceptionDrawer.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` 覆盖自动异常、统一抽屉、ignore/restore 与旧入口缺席 | 主表自动异常 chip、右上统计、统一异常抽屉、ignore/unignore 保留；未配对工具栏人工“异常处理”缺席 |
| `RECON-WB-E2E-010` | covered | `web/e2e/workbench-large-scroll-flow.spec.ts` | 首屏 50 组、滚动自动分页、失败停止/显式重试、跨未加载页全量搜索、详情、选择保持和三栏滚动 |
| `RECON-WB-E2E-011` | covered | `web/e2e/workbench-network-recovery-flow.spec.ts` | 网络恢复、重试和幂等提交 |
| `RECON-WB-E2E-012` | covered | `web/e2e/workbench-stale-error-flow.spec.ts`、`workbench-permissions-flow.spec.ts`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/WorkbenchWriteGate.test.ts` | App Health/OA dirty 写安全 gate、选择区禁用原因、专属 OA 状态恢复与只读诊断 |
| `RECON-WB-E2E-013` | covered | `web/e2e/workbench-cash-special-flow.spec.ts` | paired 现金特殊处理写链路及 barrier |
| `RECON-WB-E2E-014` | covered | `tests/test_search_query.py`、`tests/test_workbench_routes.py`、`tests/test_workbench_sql_runtime.py` | OA、流水、发票统一搜索支持金额小数精度等价和 OA 完成时间别名 |

“人工准入、关系级撤回、旧异常入口删除及内部转账统一写边界”的最终本地验证证据：全后端 4272 tests OK（65 项按外部 PostgreSQL 环境条件跳过）；撤回 command/pair/repository/UoW 专项 109 passed，no-OA/auth/routes/v2 相邻回归 185 passed；前端全量 Vitest 987 passed 且 production build 通过。默认 Chromium 全量 182 项中 181 项通过；唯一未通过项是与本需求无关的 OA 嵌入侧栏动画帧 P95 单次环境波动，该项独立重复运行 3/3 通过，本次关联台确认、撤回、权限、stale、异常入口相关 Browser 流程均通过。

上述本地证据覆盖 exact-set、同一事务重验、全局稳定锁序、topology version、fingerprint、幂等与前端用户流程。生产发布仍需 release gate、只读页面/API/队列和性能门禁；当前固定 production write smoke 不具备“同栏任意成员 + predecessor 拓扑恢复 + 同 key 重放”的合法 test-owned shape，因此不得用其他 shape 冒充本需求的生产写证据。真实 PostgreSQL 并发锁等待仍由发布后监控与后续专用 test-owned scenario 覆盖。

## 人工 confirm-link 内部转账路由门禁

- 状态：covered。`tests/test_no_oa_bank_batch_workbench_integration.py` 证明 mixed 与全 `internal_transfer` 银行选择都走标准 relation command/UoW，`tests/test_workbench_auth_context_idempotency.py` 保护真实 UoW 幂等重放，`tests/test_read_model_architecture_guards.py` 证明旧 callback/helper 不再进入调用图；独立 no-OA batch 回归保持通过。
- 结果：全后端 4272 tests OK（65 项按外部 PostgreSQL 环境条件跳过）；相关 no-OA/auth/routes/v2 相邻矩阵 185 passed。
- Browser E2E 不新增 Spec ID：本次没有 UI、权限、请求/响应 shape、read-model scope 或 worker 变化，浏览器无法可靠区分两个服务端内部 owner。

剩余生产风险是实际数据量下的 P95/P99、真实外部 OA 延迟和发布后的全量 rehydrate 时长；由生产 SLO/Audit 处理，不通过增加第三种页面状态规避。
