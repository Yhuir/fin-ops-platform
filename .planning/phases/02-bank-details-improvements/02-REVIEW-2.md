# 银行明细第二次审阅：模块边界、隔离与旧链清理

**审阅问题：** 设计是否污染 I/O、影响其他页面，旧代码删除是否完整且安全？

## 审阅结论

通过，但删除范围必须严格限制为 disconnected skeleton 及当前错误引用，不能顺手整理 no-OA、turnover、Workbench 或 shared app shell。

## 边界复核

- 页面只经 typed client 调 API；没有页面直连 repository/queue。
- route 负责 HTTP/session/permission；application service 负责编排；repository/projection 负责 SQL；worker 只消费 durable queue。
- `bank_detail` 与 `bank_account_balance` 是两个独立 read model；本轮不合并。
- frontend domain event 是 refetch hint；PostgreSQL dirty/outbox 是 freshness 事实源。
- `BankdetailWriteUnitOfWork` 同时模拟 category/settings/no-OA，并且不接入真实 service，反而跨越三个模块边界；删除会减少边界歧义。

## 删除闭环

删除前条件已满足：

1. 定义点已识别；
2. production import/caller 为零；
3. 唯一 test consumer 已识别；
4. 当前真实 replacement owner 已识别；
5. 当前 durable docs 引用已列出；
6. 历史记录与当前事实已区分；
7. 删除后用 architecture guard 防回归。

删除后不得发生：

- 新建另一个同义 UoW；
- 把 no-OA 逻辑迁入银行明细 application service；
- 用兼容分支保留旧 import；
- 放宽 architecture guard 或测试断言；
- 修改其他页面 read model、worker、API DTO。

## 跨页安全最小集合

因为删除对象无生产调用方，功能风险低；但文档曾声称它保护 category/no-OA/outbox，因此必须运行真实 owner 的最小回归：

- bank category mutation + auto tag API；
- bank-detail refresh producer/SQL runtime；
- no-OA、turnover、Workbench 关键 side-effect/architecture tests；
- permissions/audit inventory guard；
- BankDetails frontend component tests。

其他页面不做实现，只做受影响合同的回归验证。

**Gate：PASS。** 可以进入第三次简化、性能和生产闭环审阅。
