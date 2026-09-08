# 现金账模块

2026-09-08闭环修复已实施并从remote main正式发布，运行事实和未测边界以[实施§16](../../dev/cash-module-implementation-plan.md#16-闭环修复实际执行2026-09-08)为准：新增字段/归属、个人跨项目非现金、来源分类、未结及待回款、任务入口；保持四子页面/三账目Tab、同库同账号、私密cash事实池。§15是已接受计划，§14是上一发布证据，不替代当前验收。

已完成工作：此前获授权的[实施计划§13](../../dev/cash-module-implementation-plan.md#13-全现金模块ui统筹实施计划设计完成代码待授权执行)统一布局、HeroUI原生浮层/排序及多选GET已实现、提交推送和部署；实际验证与最新发布状态统一看[实施§14](../../dev/cash-module-implementation-plan.md#14-统一现金ui实际执行与验证2026-09-08)。下文68eee75c0是上一版记录，不代表本次新计划验收。

本模块管理保密的公司现金/受管储蓄账户、往来事项、票据与个人账、每月任务。现金业务只进入同库 `cash.*`，不进入 App 普通统一事实池。

上一版线上记录为`68eee75c0`，release为`cash-68eee75c0-20260907-ui-layout`，已提交推送`codex/cash-ledger`。复用现有HeroUI/FinanceTable/AppDrawer；四子页面/0-3-2-4视图接真实API。首次上线`8bdfc07ae`的三子页属于历史；上一轮测试、上线和生产只读性能见[实施计划§12](../../dev/cash-module-implementation-plan.md)。现金只读通过，旧银行/工作台四并发耗时仍超标，不把空库和只读验证扩大为完整生产写入验收。

修改前依次读[边界 I/O](boundary-io.md)、[业务总设计](../../product-specs/cash-module-design.md)、[技术字段与 API](../../dev/cash-module-technical-design.md)、[测试](tests.md)。UI 只在[UI 设计](../../product-specs/cash-module-ui-spec.md)定义。

同日UI修复已实现：现金流水成为第四个左侧子页面；现金账目保留三Tab，个人四视图用选择器。CashContent在可撤权卸载子树保存已应用条件，切回重读；表头/空态/滚动/金额列及32px控件已修复。源码原因和原计划保留于[实施计划§11](../../dev/cash-module-implementation-plan.md#11-源码对照后的现金-ui-修复计划2026-09-07待实施)，执行、测试与本次发布状态统一见§12。没有新增API/数据库/权限，生产写入验收仍不以只读验证代替。

代码：`app/routes_cash.py`、`app/cash_runtime.py`；`services/cash_domain.py/cash_service.py/cash_tasks.py/cash_queries.py/cash_oa_projects.py`；`services/postgres_repositories/cash*.py`；migration `0166_cash_ledger.sql`、`0167_cash_shared_runtime_grants.sql`与`0168_cash_business_closure.sql`。同App数据库账号，不另设cash角色、DSN或env。

不新增 worker、缓存、read model、Excel 导入器、审计正文池或通用规则引擎。

前端：`web/src/pages/CashPage.tsx`、`web/src/features/cash/{api.ts,hooks.tsx}`、`web/src/components/cash/`。共享修改只涉及 `pageRegistry.tsx` 单一 cash 权限/导航和 `AppSidebar.tsx` 分组独立展开；普通页面不导入现金模块。
