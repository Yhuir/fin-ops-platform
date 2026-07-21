# 流水规则批量处理 E2E 覆盖映射

状态：covered-close。当前实现使用 `web/e2e/bank-flow-rule-batches-flow.spec.ts` 覆盖流水规则入口；后端用 `tests/test_bank_flow_rule_batch_backend_boundary.py`、`tests/test_bank_flow_rule_batch_application_service.py`、`tests/test_app_settings_service.py`、`tests/test_operation_freshness_barrier.py`、`tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py`、`tests/test_postgres_migrations.py` 和 `tests/test_postgres_repositories_boundaries.py` 保护独立 route/application service/persistence IO/read model/worker/freshness/physical storage/tag-rule settings family 边界。Browser deterministic fixture 已切到 `bank-flow-rule-e2e-*` / `bank-flow-rule-batch-e2e-*` / `流水规则手续费成本项目`，不再用旧 no-OA I/O 表示 bank-flow 链路。标签抽屉打开/勾选/保存、提交批次、重置全部已提交、提交内部往来批次、撤回批次和确认撤回已输出 Playwright `operation-latency-*.json` 附件；其它筛选/展开/跨页补票操作仍需后续迁移。真实 pending-invoice/invoice attach 跨页补票入口仍列为后续风险。

| Spec ID | 业务场景 | 当前覆盖 | 缺口 |
| --- | --- | --- | --- |
| BRB-E2E-001 | 标签规则抽屉跟随银行明细标签 | `web/e2e/bank-flow-rule-batches-flow.spec.ts`、`web/src/test/BankFlowRuleBatchPage.test.tsx` | 已覆盖新 route、标题、xlsx-like grid、全部 active tag 的 OA/发票 checkbox、保存 `rules` 且不发送 `selected_tag_codes`；未提交 rail 明确排除需要任一单据的标签，submitted/history 使用实际历史 summary；浏览器覆盖保存先完成、精确月份 barrier/list reload 后台收敛，以及银行明细自动标签保存后抽屉同步更新。 |
| BRB-E2E-002 | 无需 OA/发票直接进入已配对并折叠 | `web/e2e/bank-flow-rule-batches-flow.spec.ts`、`tests/test_no_oa_bank_batch_tag_selection_api.py`、`web/src/test/RelationGroupGrid.test.tsx` | 已覆盖 `relation_mode=bank_flow_rule_batch`、4 条流水折叠、展开明细和流水规则文案。 |
| BRB-E2E-003 | 无 active relation 时 unpaired，确认后 paired | `web/e2e/bank-flow-rule-batches-flow.spec.ts`、`tests/test_workbench_relation_grouping.py` | 覆盖 singleton unpaired 与确认形成 active formal relation 后完整成员 paired；规则 requirement 仅保留为审计提示。 |
| BRB-E2E-004 | 规则保存不追溯改写 existing relation | `tests/test_no_oa_bank_batch_tag_selection_api.py` | 覆盖 bank-flow、turnover、manual relation metadata 和 mode 保持不变。 |
| BRB-E2E-006 | 权限、陈旧和失败状态 fail closed | `web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/bank-flow-rule-batches-flow.spec.ts` | 已覆盖 read-export 无保存/提交/撤回、首屏失败恢复、stale read model 保持可见行。 |
| BRB-E2E-007 | 银行标签变更后规则 grid 同步 | `web/e2e/bank-flow-rule-batches-flow.spec.ts` | 已覆盖银行明细自动标签规则保存后，流水规则抽屉左侧标签同步更新，旧标签不再出现。 |
| BRB-E2E-008 | 已提交批次批量重置并按当前资格重算 | `tests/test_no_oa_bank_batch_tag_selection_api.py`、`web/src/test/BankFlowRuleBatchPage.test.tsx`、`web/e2e/bank-flow-rule-batches-flow.spec.ts` | 已覆盖提交后调用 `POST /api/bank-flow-rule-batches/reset-submitted`、后台等待月份 barrier、页面回到未提交；只有当前 OA/发票双 false 的释放 rows 会重新展示，需要单据的 rows 退出本页面。后端覆盖 relation 取消、row 释放和历史保留。 |

## 旧测试迁移说明

现有 no-OA E2E/集成测试只能作为迁移参考。后续实现时不能把旧 `no_oa_bank_batch` 成功路径当作本模块完成证据，除非测试已经断言：

- 页面名称和 route 为流水规则批量处理。
- 规则 API 为 `bank-flow-rule-batches`。
- relation mode 为 `bank_flow_rule_batch`。
- `selected_tag_codes` 不参与写入。
- paired/unpaired 由 active formal relation 判定，checkbox requirement 不参与分区。
- 大于 3 条银行流水折叠展示。
