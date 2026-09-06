# 现金测试入口

现金业务算例由[技术设计 TC01–TC28](../../dev/cash-module-technical-design.md)定义。测试必须验证金额/来源/版本/状态，不只断言 HTTP 200。

| 七类 | 本轮范围 |
| --- | --- |
| 1 业务核心 | Money、输入边界、两种预算、费用/票据/债务、月份日期、版本与删除重放 |
| 2 Service | 真 PG 事务、配置/现金/事项/分配/任务同事务、部分失败回滚 |
| 3 API | cash routes、认证授权、严格 JSON/query、201/200 重放、400/403/409/503、安全错误 |
| 4 查询/后台 | cash 报表一致快照、余额窗口、筛选分页、零 GET 写、无缓存/新 worker |
| 5 前端 | 不新增现金组件或现金 E2E；运行旧前端消费测试和构建，不宣称现金 UI 已测 |
| 6 全链 | 创建/任务/多账查询/分次/删除及源纠错，真 PG；OA 模拟失败及真实只读来源分开 |
| 7 旧页回归 | session/ACL/操作历史/HTTP、普通 Mongo 项目、迁移、reset、普通 canonical 链和旧前端 |

入口为 `tests/test_cash_*.py`。设置显式 disposable `FIN_OPS_TEST_DATABASE_URL`，按权限测试说明另给测试管理员 URL；绝不借用生产 DSN。具体运行命令、样本量、结果和未测风险只记录在[实施计划](../../dev/cash-module-implementation-plan.md)的本轮执行记录。
