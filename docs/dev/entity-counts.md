# 页面业务数量

业务数量按 OA 身份计条、发票身份计张、原始银行流水身份计笔；拆分子项和重复关系不能增加原始对象数。聚合发生在各页面既有查询 owner 内，不新增统计服务、缓存或后台任务。

- OA 待付款：流程/支付流水两层切换，业务摘要与合并行分页分开，见 [OA I/O](../modules/oa-pending-payments/boundary-io.md)。
- 批量账务、流水规则批次：状态入口使用原始流水笔数，操作批次及其分页保留，见 [批量账务](../modules/batch-accounting/boundary-io.md)、[流水规则批次](../modules/bank-flow-rule-batches/boundary-io.md)。
- ETC：状态入口统计真实 ETC 发票成员张数，批次仍是操作对象，见 [ETC](../modules/etc-tickets/boundary-io.md)。
- 关联台异常：分别提供 OA、原始流水、发票数量，不把混合对象相加冒充关系数，见 [关联台](../modules/reconciliation-workbench/boundary-io.md)。
- 进项、销项、待找发票已有实体统计继续保持；进项无消费的组数摘要删除。待找发票不能推断尚未取得的发票张数。

互斥性属于每个页面的业务状态定义，不能从 UI 单选推导。历史撤回与当前提交可以涉及相同对象，不要求两类数量相加等于全部。统计应覆盖完整筛选集合，不从当前页长度补算；合法空集合是 0，失败与合同缺失不能伪装成 0。
