# 现金测试入口

现金业务算例由[技术设计 TC01–TC28](../../dev/cash-module-technical-design.md)定义。测试必须验证金额/来源/版本/状态，不只断言 HTTP 200。

| 七类 | 本轮范围 |
| --- | --- |
| 1 业务核心 | Money、输入边界、两种预算、费用/票据/债务、月份日期、版本与删除重放 |
| 2 Service | 真 PG 事务、配置/现金/事项/分配/任务同事务、部分失败回滚 |
| 3 API | cash routes、认证授权、严格 JSON/query、201/200 重放、400/403/409/503、安全错误 |
| 4 查询/后台 | cash 报表一致快照、余额窗口、筛选分页、零 GET 写、无缓存/新 worker |
| 5 前端 | CashApi/Hooks/Books/Items/Tasks/Settings/FlowComposition/FlowCorrections、路由与侧栏、真实HeroUI浏览器交互；生产只读与合成E2E证据分开 |
| 6 全链 | 创建/任务/多账查询/分次/删除及源纠错，真 PG；OA 模拟失败及真实只读来源分开 |
| 7 旧页回归 | session/ACL/操作历史/HTTP、普通 Mongo 项目、迁移、reset、普通 canonical 链和旧前端 |

入口为`tests/test_cash_*.py`。设置显式disposable `FIN_OPS_CASH_TEST_DATABASE_URL`及`FIN_OPS_TEST_DATABASE_URL`，绝不借用生产DSN。`test_cash_runtime.py`覆盖同库同账号、旧cash配置不能改向、连接限额、失败清理、真实录入/查询/删除及普通数据不变；0167验证已有运行角色的十表DML。专用cash账号provision和双向数据库拒绝测试随已取消方案移除，不删除页面权限或全局审计隔离测试。具体命令、样本和未测风险只记录在[实施计划](../../dev/cash-module-implementation-plan.md)。

前端测试入口为`web/src/test/Cash*.test.*`及AppSidebar/Settings/PageRouteHost回归；浏览器入口`web/e2e/cash-module-flow.spec.ts`。验证分组独立、4/2/4菜单、严格现金HTTP边界、响应竞态取消、写后局部重读、撤权清除、真实金额null与各事务命令。Make内存点击不作为App验证证据。

Make移植测试责任矩阵（2026-09-07 已进入实现和验证，结果统一记录于实施计划）：

| 七类 | F阶段具体新增/更新责任 |
| --- | --- |
| 1 核心 | 现金输入Money/日期/字段适用，表单命令组装、null与缺字段、UI展示状态映射；账务算法继续后端唯一owner |
| 2 Service | 追加报表投影不改变写事务；receipt/category/remark来源和删除后消失、OA历史独立链验证 |
| 3 API | TurnoverRow三新字段形状/语义；现金client遇HTML不换地址、错误不空成功、写结果未知/409/403；无普通API请求 |
| 4 读侧 | 12000→9000→6500逐次未结、分页批量投影、票据非现金抵清仍不是已回款；不加cache/worker，无缓存状态/新job测试 |
| 5 前端 | 17列、3子页面/4-2-4菜单、共享权限只一项、导入/现金展开互不影响；抽屉/选择器/任务/设置全部成败状态、取消/旧响应、退出与Portal隐私；无持久化现金条件 |
| 6 全链 | 真API：必要设置→手工/任务→适用账表→编辑/源纠错→删除→全账及任务一致；非现金/票据/个人期初完整路径 |
| 7 回归 | AppSidebar/PageRouteHost/Settings、普通银行与往来、AppDrawer、cash-special、普通API兼容；现金与普通页同时负载 |

七类均适用，其中第4类只涉及直接查询，没有新增缓存/read model/worker，因此不为不存在的后台链路造测试。权限场景使用本地自动化输入，生产不创建现金受限角色，受限角色生产验证由用户负责。具体已运行命令、数量、性能和未测风险统一记录于实施计划§10，不另建门禁。
