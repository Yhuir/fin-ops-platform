# 现金测试入口

## 当前状态与回归修复（2026-09-08）

现金闭环已实施和发布，实际结果以[实施§16](../../dev/cash-module-implementation-plan.md#16-闭环修复实际执行2026-09-08)为准：当时现金167项专项通过，全仓PG为6 failure、44 error、5 skip；该数值是当时记录。下文“待执行§15”等段落保留为历史计划，不覆盖§16。

失败根因、修复顺序与最新进度统一见[PostgreSQL回归修复记录§7](../../dev/postgres-regression-repair-plan.md#7-执行记录2026-09-08)。测试生命周期、完整 schema、二态 ACL、canonical 事实准备与失效断言已修正；包含银行排序修复后的真实PG全量为4121项、4119通过、2个ETC失败、0 error/skip。不改现金业务、生产表结构、权限规则或前端，不以专项成功覆盖全量失败。恢复 ETC 五个跳过测试后发现无扩展名 TXT 被上传校验拒绝，窄范围应用修复等待用户确认。

新增待执行测试计划见[实施§15.4–15.6](../../dev/cash-module-implementation-plan.md#154-必测算例和七类测试责任)：旧未动欠款、个人起算/归属、非现金分类、跨项目来源及并发纠错、任务一次记账、票据跨年催款/截止、矩阵全范围合计和删除回溯。本轮仅改文档，未新增或运行这些业务测试；上轮95前端/25无DB测试及下面历史记录不作为新规则通过。仍复用当前测试文件/真实PG/浏览器，不新建测试框架或门禁。

方案接受后的补测责任见实施§15.9：分类仅被事项/调整引用时的删除保护、每个复合入口的新字段一致性、来源/借款项目分开筛选、历史余额不能用于当前占额、个人配置故障不阻断普通现金；已结束项目历史票据/费用来源的拒绝必须显式，不能靠测试自动绕过。上述均待代码实施时执行，本轮不把文档审阅计为业务测试通过。

## 当前实现：全现金UI统筹

本轮七类测试适用性与原计划见[实施§13.5–13.6](../../dev/cash-module-implementation-plan.md#135-测试责任与命令)，实际数量、命令与失败/发布记录统一见[实施§14](../../dev/cash-module-implementation-plan.md#14-统一现金ui实际执行与验证2026-09-08)。现有Cash测试与test_cash_*.py已扩多选、余额、候选、原API和写后重读；新增CashFilters.test.tsx与真实cash-real-api-flow.spec.ts，几何测试直接扩cash-module-flow.spec.ts，原生Tabs由Books/Tasks/Settings覆盖，不另造重复测试框架。以下1176项是历史结果。

验收不能只默认空态：所有子页/视图及抽屉开关、搜索候选、翻页多选、取消/应用、null/不限、错误、键盘和撤权Portal清除须覆盖。原生HeroUI真实浏览器测背景坐标/滚动不变；多选在真实PG分页前处理，余额按完整账序。第4类仅直接读查询适用，无新cache/read model/worker。公开单值API/普通页仍回归，生产不创建现金受限角色。

## 历史验证记录（非本轮验收）

2026-09-07本次UI修复已增加/更新CashBooks、CashFlows、AppSidebar、PageRouteHost及cash-module-flow测试：四子页、0/3/2/4视图、个人选择器、空态/错误稳定表头、32px对齐、筛选恢复/重置、末页删除归一、父对象跨年、停用账户筛选、长金额/满页滚动与非法地址。全量前端1176项和真实HTTP/PG现金54项已通过；最终定向/浏览器、发布和性能结果统一记录[实施计划§12](../../dev/cash-module-implementation-plan.md)。下文F阶段三子页/4-2-4属于首次上线历史，不覆盖本次行为。后台/SQL未变，不新建service/worker测试，既有业务集成仍回归。

生产只读入口：`web/e2e/production-cash-readonly.spec.ts`沿用显式生产smoke环境和本机token wrapper；关闭截图/录像/trace，拦截非GET/HEAD/OPTIONS，逐页读取真实接口并记录数值化耗时，不创建角色/账户/现金/OA记录。只有显式生产验证运行此文件；普通本地E2E使用合成HTTP，与真实PostgreSQL证据分开。

执行细节补充测试：跨年事项/任务关联流水默认不发本年期间且不漏记录；独立流水仍发有界期间；切视图恢复条件但重新取数，撤权卸载条件状态；删末页最后一行调整至最近有效页，重读失败不重发delete；录入Select仅启用项并保留已保存原值，停用项仍可历史筛选；任务/设置多区块能滚动到最后一表，无每表满屏叠加。候选49+null分页、真实搜索差异防抖、完整query应用前校验都有专项测试。

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

七类均适用，其中第4类只涉及直接查询，没有新增缓存/read model/worker，因此不为不存在的后台链路造测试。权限场景使用本地自动化输入，生产不创建现金受限角色，受限角色生产验证由用户负责。最新已运行命令、数量、性能和未测风险统一记录于实施计划§14，不另建门禁。

## 2026-09-10 新增流水交互

CashFlows.test.tsx 新增直接打开/关闭清空、收入切支出保留输入与角色账户、有关联事项取消/确认切换且无旧事项提交；现有转账测试改用转出/转入账户标签。cash-module-flow.spec.ts 新增三种类型键盘切换及 1440/780/390 宽度验证；cash-real-api-flow.spec.ts 使用直接新增入口，继续验证真实 HTTP/PostgreSQL 保存刷新。业务核心、前端 API 请求、组件、端到端、旧入口回归适用；service 与直接查询复用已有回归，无新增后台/cache/read model。

本次本地结果：`cd web && npx vitest run` 98 文件、1296 测试通过；现金专项 149 测试通过；`npx playwright test e2e/cash-module-flow.spec.ts --project=chromium` 11 项通过，桌面/窄屏截图已人工审阅；独立 Docker PostgreSQL `fin_ops_cash_test_entry` 下 `PYTHONPATH=backend/src:tests python3 -m tests.test_cash_http_integration --browser-e2e` 2 项通过，覆盖真实录入/筛选/删除重读和个人事项/任务链路。初始独立环境缺少既有迁移要求的角色，补齐测试容器角色后全流程通过，未改迁移或生产角色。`npm run build`、`bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check` 通过。构建保留既有大 chunk 提示，无新增依赖。
