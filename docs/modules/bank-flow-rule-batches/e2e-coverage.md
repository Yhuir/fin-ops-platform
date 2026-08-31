# 流水规则批量处理 E2E 覆盖映射

状态：covered-partial。当前实现使用 `web/e2e/bank-flow-rule-batches-flow.spec.ts` 覆盖流水规则入口；后端用 canonical query repository/application/route/architecture tests 保护独立 route、同 snapshot、固定查询数、active relation、canonical persistence 和 tag-rule settings 边界。成本统计跨页回归证明规则批次流水只进入银行事实视图；没有完成 OA 付款关系时，不得伪造项目成本。标签抽屉保存、提交和单批次撤回均覆盖旧状态字段缺失与当前页单次 normal GET。

| Spec ID | 业务场景 | 当前覆盖 | 缺口 |
| --- | --- | --- | --- |
| BRB-E2E-001 | 标签规则抽屉跟随银行明细标签 | `web/e2e/bank-flow-rule-batches-flow.spec.ts`、`web/src/test/BankFlowRuleBatchPage.test.tsx` | 已覆盖新 route、标题、xlsx-like grid、全部 active tag 的 OA/发票 checkbox、保存 `rules` 且不发送 `selected_tag_codes`；未提交 rail 明确排除需要任一单据的标签，submitted/history 使用实际历史 summary；保存返回空 targets 后当前页 normal GET 收敛，银行明细自动标签保存后抽屉同步更新。 |
| BRB-E2E-002 | 无需 OA/发票直接进入已配对并折叠 | `web/e2e/bank-flow-rule-batches-flow.spec.ts`、`web/src/test/BankFlowRuleBatchPage.test.tsx`、`tests/test_no_oa_bank_batch_tag_selection_api.py`、`web/src/test/RelationGroupGrid.test.tsx` | 已覆盖三栏表格信息层级、checkbox 可见尺寸、单选/半选/全选/清空、旧重复标签负向断言、`relation_mode=bank_flow_rule_batch`、4 条流水折叠、展开明细和流水规则文案。 |
| BRB-E2E-003 | 无 active relation 时 unpaired，确认后 paired | `web/e2e/bank-flow-rule-batches-flow.spec.ts`、`tests/test_workbench_relation_grouping.py` | 后端 active relation 分组回归已覆盖；Chromium shared Workbench confirm-preview fixture 的旧 DTO 当前被前端拒绝，主控修复共享 fixture 后必须重跑。 |
| BRB-E2E-004 | 规则保存增量重算 existing active relation | `tests/test_bank_relation_requirement_recalculation.py`、`tests/test_postgres_repositories_boundaries.py`、`tests/test_bank_flow_rule_batch_application_service.py` | 覆盖 semantic diff、完整 tag OR、设置/job/outbox 原子性、零写失败、精确月份刷新、幂等重放；生产 Browser 分区归位由发布门禁验证。 |
| BRB-E2E-006 | 权限、空集和失败状态 fail closed | `web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/bank-flow-rule-batches-flow.spec.ts`、`web/src/test/BankFlowRuleBatchPage.test.tsx` | 已覆盖 read-export 无保存/提交/撤回、首屏失败恢复、真实空态和首次 canonical GET 后不后台轮询。 |
| BRB-E2E-007 | 银行标签变更后规则 grid 同步 | `web/e2e/bank-flow-rule-batches-flow.spec.ts` | 已覆盖银行明细自动标签规则保存后，流水规则抽屉左侧标签同步更新，旧标签不再出现。 |

## 旧测试迁移说明

现有 no-OA E2E/集成测试只能作为迁移参考。后续实现时不能把旧 `no_oa_bank_batch` 成功路径当作本模块完成证据，除非测试已经断言：

- 页面名称和 route 为流水规则批量处理。
- 规则 API 为 `bank-flow-rule-batches`。
- relation mode 为 `bank_flow_rule_batch`。
- `selected_tag_codes` 不参与写入。
- paired/unpaired 由 active formal relation 及其当前持久化 requirement 判定，checkbox 语义变化经后台任务写入该 requirement。
- 大于 3 条银行流水折叠展示。
