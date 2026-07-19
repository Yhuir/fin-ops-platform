# 第一次审阅：事实源、状态机与 I/O 合同

## 审阅问题

1. 谁是批次列表、正式关系和刷新状态的事实源？
2. command 返回后，哪些状态可立即展示，哪些必须等待 worker？
3. 删除旧 ID 是否会破坏历史关系？
4. 本页面是否可以等待或写入其它页面 read model？

## 结论

### Canonical facts 不变

- 银行流水、标签、正式关系和 durable queue仍是 PostgreSQL事实源。
- `read_model.bank_flow_rule_batch_rows` 只做本页面读模型。
- SQL分页只改变读取方式，不改变批次业务规则或 canonical ownership。

### 写后状态分两层

- submit/withdraw/reset transaction提交后，批次与 relation 的 committed canonical state已经成立，可以立即反馈操作成功。
- reset 后重新生成的 draft 是派生状态，必须等 bank-flow worker；UI应明确显示“同步中”，不能伪造 draft 已完成。
- 其它页面的 read model freshness 是下游责任，不是当前页面 command 成功条件。

### 历史身份不可迁移

历史 `no_oa_batch_*` ID已进入关系 case、审计和外键/JSON引用。为了命名整洁而批量改 ID 会引入高风险跨表迁移和外部引用断裂，属于过度设计。

闭环做法是：历史 ID继续可读写；新 bank-flow draft 使用新 namespace；测试同时锁定两种身份的兼容边界。这里“删除旧代码”指删除 bank-flow 新链路继续生成/输出旧合同，不是破坏历史事实。

### 隔离性成立

- 本页面只写 canonical relation + 自己的批次事实，由既有 fan-out通知下游。
- 不直接写 Workbench、银行明细、流水规则配置或其它页面私有 read model。
- response 仍可带完整 downstream targets供事件广播和观测，但 UI 本地 reconcile只消费 bank-flow targets。

## 第一轮判定

计划符合事实源、状态机和 I/O 合同。必须在实施中增加以下门禁：

- reset transaction失败时 relation 与 batches均不产生半写；
- refreshing/stale状态不能标 fresh；
- 历史 ID读取、详情、撤回回归测试；
- API response shape和权限不变。
