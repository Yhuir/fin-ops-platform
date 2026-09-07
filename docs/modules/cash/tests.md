# 现金测试入口

2026-09-07本次UI修复已增加/更新CashBooks、CashFlows、AppSidebar、PageRouteHost及cash-module-flow测试：四子页、0/3/2/4视图、个人选择器、空态/错误稳定表头、32px对齐、筛选恢复/重置、末页删除归一、父对象跨年、停用账户筛选、长金额/满页滚动与非法地址。全量前端1176项和真实HTTP/PG现金54项已通过；最终定向/浏览器、发布和性能结果统一记录[实施计划§12](../../dev/cash-module-implementation-plan.md)。下文F阶段三子页/4-2-4属于首次上线历史，不覆盖本次行为。后台/SQL未变，不新建service/worker测试，既有业务集成仍回归。

生产只读入口：`web/e2e/production-cash-readonly.spec.ts`沿用显式生产smoke环境和本机token wrapper；关闭截图/录像/trace，拦截非GET/HEAD/OPTIONS，逐页读取真实接口并记录数值化耗时，不创建角色/账户/现金/OA记录。只有显式生产验证运行此文件；普通本地E2E使用合成HTTP，与真实PostgreSQL证据分开。

执行细节补充测试：跨年事项/任务关联流水默认不发本年期间且不漏记录；独立流水仍发有界期间；切视图恢复条件但重新取数，撤权卸载条件状态；删末页最后一行调整至最近有效页，重读失败不重发delete；entry/filter全部调用显式传mode、停用账户仅历史筛选可选；任务/设置多区块能滚动到最后一表，无每表满屏叠加。

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
