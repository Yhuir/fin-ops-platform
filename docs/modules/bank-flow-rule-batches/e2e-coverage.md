# 流水规则批量处理 E2E 覆盖映射

状态：covered-independent-io。当前实现使用 `web/e2e/bank-flow-rule-batches-flow.spec.ts` 覆盖流水规则入口；后端用 `tests/test_bank_flow_rule_batch_backend_boundary.py`、`tests/test_bank_flow_rule_batch_application_service.py`、`tests/test_operation_freshness_barrier.py`、`tests/test_read_model_manifest.py` 和 `tests/test_runtime_worker_registry.py` 保护独立 route/application service/persistence IO/read model/worker/freshness 边界。真实 pending-invoice/invoice attach 跨页补票入口和物理表拆分仍列为后续风险。

| Spec ID | 业务场景 | 当前覆盖 | 缺口 |
| --- | --- | --- | --- |
| BRB-E2E-001 | 标签规则抽屉跟随银行明细标签 | `web/e2e/bank-flow-rule-batches-flow.spec.ts`、`web/src/test/BankFlowRuleBatchPage.test.tsx` | 已覆盖新 route、标题、xlsx-like grid、OA/发票 checkbox、保存 `rules` 且不发送 `selected_tag_codes`；浏览器 E2E 已覆盖银行明细自动标签保存后本抽屉同步更新。 |
| BRB-E2E-002 | 无需 OA/发票直接进入已配对并折叠 | `web/e2e/bank-flow-rule-batches-flow.spec.ts`、`tests/test_workbench_candidate_grouping.py` | 已覆盖 `relation_mode=bank_flow_rule_batch`、4 条流水折叠、展开明细和流水规则文案。 |
| BRB-E2E-003 | 需要发票时先 open，补票后 paired | `web/e2e/bank-flow-rule-batches-flow.spec.ts`、`tests/test_workbench_candidate_grouping.py` | 已覆盖 requires_invoice=true 时先留在 open，并通过关联台确认补票候选发票后同一 `bank_flow_rule_batch` 进入 paired。真实 pending-invoice/invoice attach 跨页入口仍需后续补齐。 |
| BRB-E2E-004 | OA 和发票都需要时缺任一项不 paired | `tests/test_workbench_candidate_grouping.py` | 已覆盖 `requires_oa=true` 且 `requires_invoice=true` 时，缺 OA、缺发票均留在 open，OA/发票齐全才 paired；浏览器级操作流仍可在真实 OA/发票补齐入口完善后补充。 |
| BRB-E2E-005 | 历史 no-OA submitted rebaseline | `tests/test_no_oa_bank_batch_tag_selection_api.py`、`web/e2e/bank-flow-rule-batches-flow.spec.ts` | 已覆盖 dry-run、apply、撤回旧 relation、旧 batch withdrawn、apply 幂等；浏览器 E2E 覆盖 dry-run 清单、apply 携带 manifest/reason、operation barrier 后刷新。 |
| BRB-E2E-006 | 权限、陈旧和失败状态 fail closed | `web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/bank-flow-rule-batches-flow.spec.ts` | 已覆盖 read-export 无保存/提交/撤回、首屏失败恢复、stale read model 保持可见行。 |
| BRB-E2E-007 | 银行标签变更后规则 grid 同步 | `web/e2e/bank-flow-rule-batches-flow.spec.ts` | 已覆盖银行明细自动标签规则保存后，流水规则抽屉左侧标签同步更新，旧标签不再出现。 |
| BRB-E2E-008 | 已提交批次批量重置回未提交候选 | `tests/test_no_oa_bank_batch_tag_selection_api.py`、`web/src/test/BankFlowRuleBatchPage.test.tsx`、`web/e2e/bank-flow-rule-batches-flow.spec.ts` | 已覆盖提交后调用 `POST /api/bank-flow-rule-batches/reset-submitted`、等待 `bank_flow_rule_batch` operation barrier、页面回到未提交并重新展示候选；后端覆盖 relation 取消和 row 释放。 |

## 旧测试迁移说明

现有 no-OA E2E/集成测试只能作为迁移参考。后续实现时不能把旧 `no_oa_bank_batch` 成功路径当作本模块完成证据，除非测试已经断言：

- 页面名称和 route 为流水规则批量处理。
- 规则 API 为 `bank-flow-rule-batches`。
- relation mode 为 `bank_flow_rule_batch`。
- `selected_tag_codes` 不参与写入。
- paired/open 由 OA/发票 checkbox requirement 判定。
- 大于 3 条银行流水折叠展示。
