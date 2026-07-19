# 银行明细第三次审阅：简化、性能与生产闭环

**审阅问题：** 计划是否过度设计，是否遗漏生产级闭环？

## 审阅结论

通过。最终设计不是新增性能架构，而是删除一条无效架构；这同时符合 Ponytail、模块化和高性能目标。

## 过度设计检查

以下候选全部拒绝：

- 新增页面专属 cache：当前 cache hit 和 API p95 已达标，还会增加 stale 风险；
- 新增 warmup worker：首屏 warm 已达标，无法解释单次 browser bootstrap；
- 合并 bank detail/account balance read model：破坏余额独立事实边界；
- 新建统一 UoW/事件总线：当前缺口正是一个未接入的抽象骨架；
- 修改 shared session/App Shell：证据不支持，且会扩大到所有页面；
- 删除所有名字含 legacy 的函数：会破坏当前银行文本字段语义；
- 全仓大重构或全量 CI：与本次无生产调用方删除不成比例。

## 完整闭环检查

实施闭环必须包含：

1. 删除代码、孤立测试和当前文档错误引用；
2. architecture guard 阻止旧 skeleton/并行 owner 回归；
3. 定向 lint、backend、frontend、read model、docs 和 git diff 检查；
4. 明确七类测试适用性；
5. READY 前确认 worktree、HEAD、release 文件和迁移影响；
6. 单页面 commit/push/deploy；
7. 发布后 authenticated API + UI + Page Audit；
8. standing fan-out write apply 后测 enqueue-to-fresh、页面可见、Audit、queue drain；
9. 检查 Workbench/no-OA/turnover 及至少一个无关页面没有功能回归；
10. 失败时只回退本页提交/部署，不进入下一页面。

## 性能门槛

- warm authenticated UI data-visible p95 ≤ 1000ms；
- accounts/transactions/rules/Page Audit authenticated p95 ≤ 1000ms；
- 受控写操作 enqueue-to-fresh p95 ≤ 1000ms，p99 ≤ 3000ms；
- 写后直接页面读取必须 fresh 且显示新事实；
- queue/dirty/outbox 最终为零，Audit pass；
- 无跨页错误、无 read model scope 污染。

这些门槛沿用当前运维合同，不新增第二套指标系统。

## 最终实施范围

最终只保留一个 bounded implementation slice：

`删除 disconnected BankdetailWriteUnitOfWork -> 修正当前 owner 文档 -> 增加 architecture guard -> 定向验证 -> 部署 -> 生产 fan-out closure`。

**Gate：PASS。** 三次审阅完成，可以制定详细实施计划；尚未授权跳过计划直接写代码。
