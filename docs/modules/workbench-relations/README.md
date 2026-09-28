# 正式关联关系

入口：`公共命令与读取边界`。

独占正式关系 app.workbench_pair_relations 及追加历史的业务写入；active 关系拥有 typed 成员。其他页面读取同一正式事实。

## 边界与 I/O

输入：精确成员 row_ids/row_types、tenant、服务端 actor、版本、幂等键、命令与备注。输出：关系状态、版本、历史、受影响成员和月份，以及必要的领域任务。

## 当前业务约定

- 人工请求至少包含两个不同且存在的 canonical 成员；active overlap、未知类型和版本漂移明确拒绝。
- command/UoW 在同事务重检成员、持久幂等、关系、历史和审计；同键同意图重放返回原结果，不同意图冲突。
- confirm/extend/replace/cancel/withdraw 统一经过 owner；跨模块不得自行改关系表。
- 金额不等不阻止普通人工关联，但要求的备注必须保存。OA 与完整外部往来闭环复用 Turnover validator 后使用对应关系模式。
- 匹配 worker 使用同一命令边界；来源明确的后到 OA、流水或发票可补齐关系与明细归属，不按弱金额猜测来源。
- 关系历史可提供当前展示证据，展示分组不能改变正式拓扑。银行拆分版本和成员重新检查在同一事务完成。
- 撤回按正式历史恢复/取消所属关系；审计历史追加保留。

## 依赖方向

[关联台](../reconciliation-workbench/README.md)、[外部往来款](../turnover-ledger/README.md)、[流水规则批量处理](../bank-flow-rule-batches/README.md)、[OA 集成](../oa-integration/README.md)、[后台任务](../runtime-workers/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [tests/test_etc_relation_page_reads_postgres.py](../../../tests/test_etc_relation_page_reads_postgres.py)
- [tests/test_bank_transaction_split_relation_service.py](../../../tests/test_bank_transaction_split_relation_service.py)
- [tests/test_bank_split_relations_postgres.py](../../../tests/test_bank_split_relations_postgres.py)
- [tests/test_bank_transaction_split_locking.py](../../../tests/test_bank_transaction_split_locking.py)
- [tests/test_workbench_relation_command_service.py](../../../tests/test_workbench_relation_command_service.py)
- [tests/test_workbench_auth_context_idempotency.py](../../../tests/test_workbench_auth_context_idempotency.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
