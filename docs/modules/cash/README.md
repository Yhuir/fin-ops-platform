# 现金账模块

本模块管理保密的公司现金/受管储蓄账户、往来事项、票据与个人账、每月任务。现金业务只进入同库 `cash.*`，不进入 App 普通统一事实池。

本轮实现后端；没有现金前端页面、导航或权限 checkbox。实际验证/部署状态见[实施计划](../../dev/cash-module-implementation-plan.md)。

修改前依次读[边界 I/O](boundary-io.md)、[业务总设计](../../product-specs/cash-module-design.md)、[技术字段与 API](../../dev/cash-module-technical-design.md)、[测试](tests.md)。UI 只在[UI 设计](../../product-specs/cash-module-ui-spec.md)定义。

代码：`app/routes_cash.py`、`app/cash_runtime.py`；`services/cash_domain.py/cash_service.py/cash_tasks.py/cash_queries.py/cash_oa_projects.py`；`services/postgres_repositories/cash*.py`；migration `0166_cash_ledger.sql`。

不新增 worker、缓存、read model、Excel 导入器、审计正文池或通用规则引擎。
