# 现金账模块

本模块管理保密的公司现金/受管储蓄账户、往来事项、票据与个人账、每月任务。现金业务只进入同库 `cash.*`，不进入 App 普通统一事实池。

2026-09-07 用户已授权执行修复、提交推送本分支、部署及生产验证。App 现金前端已接入真实 API，复用现有 HeroUI/FinanceTable/AppDrawer；侧栏三子页面、正文 4/2/4 视图、流水与事项/任务/设置已实现。实际验证和部署结果见[实施计划](../../dev/cash-module-implementation-plan.md)，不能以实现状态替代生产验收。

修改前依次读[边界 I/O](boundary-io.md)、[业务总设计](../../product-specs/cash-module-design.md)、[技术字段与 API](../../dev/cash-module-technical-design.md)、[测试](tests.md)。UI 只在[UI 设计](../../product-specs/cash-module-ui-spec.md)定义。

代码：`app/routes_cash.py`、`app/cash_runtime.py`；`services/cash_domain.py/cash_service.py/cash_tasks.py/cash_queries.py/cash_oa_projects.py`；`services/postgres_repositories/cash*.py`；migration `0166_cash_ledger.sql`与`0167_cash_shared_runtime_grants.sql`。同App数据库账号，不另设cash角色、DSN或env。

不新增 worker、缓存、read model、Excel 导入器、审计正文池或通用规则引擎。

前端：`web/src/pages/CashPage.tsx`、`web/src/features/cash/{api.ts,hooks.tsx}`、`web/src/components/cash/`。共享修改只涉及 `pageRegistry.tsx` 单一 cash 权限/导航和 `AppSidebar.tsx` 分组独立展开；普通页面不导入现金模块。
