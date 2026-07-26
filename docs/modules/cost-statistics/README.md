# 成本统计模块

## 当前设计

成本统计是直接事实源读取页面，不再是 read model 消费者。

每次页面访问、手动刷新、详情查询或导出请求都执行一次独立读取：

1. PostgreSQL 开启 `REPEATABLE READ READ ONLY` 事务；
2. 在同一快照内读取银行流水、OA、正式关联关系、银行标签/确认与设置；
3. `CostStatisticsPolicy` 在内存中按现有业务口径生成五种视图、统计、详情与导出；
4. API 返回本次快照结果，不等待 worker、不入队、不读取旧 Cost 投影。

因此页面读取不受 Cost 版本、dirty scope、outbox 或 worker 状态控制。写操作仍由各自业务模块写入统一事实源；下一次成本统计请求自然读取提交后的事实。

## 入口

- 页面：`/fin-ops/cost-statistics`
- API：`/api/cost-statistics/explorer`、`export-preview`、`export`、`transactions/{id}`
- 标签规则：`GET|PUT /api/cost-statistics/tag-rules`
- Audit：`cost-statistics` 页面审计，直接验证 canonical relation 完整性

## 维护文档

- [边界与 I/O](boundary-io.md)
- [状态机](state-machine.md)
- [测试矩阵](tests.md)
- [实施决策](implementation-notes.md)
