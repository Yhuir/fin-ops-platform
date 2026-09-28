# 流水规则批量处理

入口：`/bank-flow-rule-batches`。

根据银行用途和标签要求实时构造待提交候选，管理正式批次提交与撤回。

## 边界与 I/O

输入：month/type/status/bucket/account_key/page/page_size；候选详情携带 view=candidate 与 scope_month。提交携带选中成员、规则版本和幂等身份。输出：summary、batches、pagination、详情和命令结果；page_size 最大 200。

## 当前业务约定

- 候选由当前银行分类、设置和 active relation 在同一快照构造，不把待提交候选作为持久事实。
- 正式 batch、events、关系和历史通过同一事务保存；提交重检成员占用、规则与选择证明。
- 内部转账使用跨月边界窗口，批次归最早成员月份；候选账户身份复用 canonical account_key。
- 标签要求改变时，配置、后台任务和 settings-maintenance 事件同事务提交。任务成功后才提示重算完成。
- 撤回处理所选正式批次及后续合并历史；没有 active owner 时关系撤回幂等完成。
- 冲突清理旧选择和详情后回读一次，不自动重复提交。

## 依赖方向

[银行明细](../bank-details/README.md)、[设置](../settings/README.md)、[正式关联关系](../workbench-relations/README.md)、[后台任务](../runtime-workers/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/BankFlowRuleBatchPage.tsx](../../../web/src/pages/BankFlowRuleBatchPage.tsx)
- [web/src/features/bankFlowRuleBatches/api.ts](../../../web/src/features/bankFlowRuleBatches/api.ts)
- [backend/src/fin_ops_platform/app/routes_bank_flow_rule_batches.py](../../../backend/src/fin_ops_platform/app/routes_bank_flow_rule_batches.py)
- [backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py](../../../backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/bank_flow_rule_batch_canonical_query.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/bank_flow_rule_batch_canonical_query.py)
- [web/src/features/dateTime.ts](../../../web/src/features/dateTime.ts)
- [backend/src/fin_ops_platform/services/bank_relation_requirement_recalculation.py](../../../backend/src/fin_ops_platform/services/bank_relation_requirement_recalculation.py)
- [backend/src/fin_ops_platform/services/bank_details_canonical_query.py](../../../backend/src/fin_ops_platform/services/bank_details_canonical_query.py)
- [backend/src/fin_ops_platform/services/bank_flow_rule_batch_canonical_query.py](../../../backend/src/fin_ops_platform/services/bank_flow_rule_batch_canonical_query.py)
- [backend/src/fin_ops_platform/services/postgres_state_store.py](../../../backend/src/fin_ops_platform/services/postgres_state_store.py)
- [web/e2e/bank-flow-rule-batches-flow.spec.ts](../../../web/e2e/bank-flow-rule-batches-flow.spec.ts)
- [web/src/test/BankFlowRuleBatchPage.test.tsx](../../../web/src/test/BankFlowRuleBatchPage.test.tsx)
- [web/src/test/BankFlowRuleBatchPolicy.test.ts](../../../web/src/test/BankFlowRuleBatchPolicy.test.ts)
- [tests/test_bank_details_canonical_query.py](../../../tests/test_bank_details_canonical_query.py)
- [tests/test_bank_flow_rule_batch_canonical_query_repository.py](../../../tests/test_bank_flow_rule_batch_canonical_query_repository.py)
- [tests/test_bank_flow_rule_batch_application_service.py](../../../tests/test_bank_flow_rule_batch_application_service.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
