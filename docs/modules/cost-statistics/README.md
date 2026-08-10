# 成本统计模块

## 当前设计

成本统计是直接事实源读取页面，不再是 read model 消费者。

每次页面访问、手动刷新、详情查询或导出请求都执行一次独立读取：

1. PostgreSQL 开启 `REPEATABLE READ READ ONLY` 事务；
2. 在同一快照内读取银行流水、OA、正式关联关系、银行标签/确认与设置；
3. `CostStatisticsPolicy` 在内存中按现有业务口径生成五种视图、统计、详情与导出；
4. API 返回本次快照结果，不等待 worker、不入队、不读取旧 Cost 投影。

因此页面读取不受 Cost 版本、dirty scope、outbox 或 worker 状态控制。写操作仍由各自业务模块写入统一事实源；下一次成本统计请求自然读取提交后的事实。

五个视图使用同一个当前视图搜索合同：搜索在聚合和 cursor 分页之前执行。`按时间` 展示真实银行对手方、标签和摘要；分页在表格内部接近底部时自动加载，局部错误只重试下一页，不触发整页 reload。

五个视图共用同一有界内容高度和表内滚动合同。`按项目`、`按银行`、`按 OA 费用类型`、`按标签`把范围选择和搜索放在同一行；`按时间`保留左侧常驻时间栏。空结果只由表格内容区呈现，不在表格上方增加会造成布局位移的第二个提示。

OA 成本口径只消费完成态 OA；进行中 OA 不进入 `按项目`、`按银行`、`按 OA 费用类型`及其汇总、下钻与详情。点击流水立即打开复用全站 `AppDrawer` 的右侧抽屉，详情加载与失败只在抽屉内反馈，不锁定页面请求状态，也不显示文字 loading。

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
