# 现金账

入口：`/cash`。

独立管理现金流水、专账事项、结算、任务与配置。共用数据库和身份，财务事实只存在 cash.*，不进入普通财务池。

## 边界与 I/O

输入：section=flows/accounts/tasks/settings；UUID 身份、ISO 日期/月、两位十进制金额、命令版本。输出：仅现金页面可见的 rows/count/summary、详情及事务结果，全部响应 no-store。

## 当前业务约定

- CashApiRoutes → cash service → cash repository；授权后惰性组装有界小池，最大 2 连接、等待 8、获取超时 2 秒、SQL 超时 5 秒，应用隔离不是数据库账号隔离。
- 普通列表显式选择 time_scope=all 或成对日期，互斥；all 截至上海今天。账户余额按真实 opening_date 全账序计算，关键词筛选只影响筛选合计。
- flows/items/settlements 与配置只通过现金复合命令事务写入；来源变更校验后续引用并整体回滚。GET 不创建任务实例。
- 同人跨项目的非现金归属与现金项目约束分别校验；实际收付复用来源，不能重复创建本金。任务实例保留当月快照，不被未来模板覆盖。
- 只通过 OA owner 窄口读取项目元数据，不查询普通财务；普通 reset、worker、成本、银行余额和全局操作历史不读写 cash。
- 页面使用独立严格 JSON client、15 秒超时和取消；401/403 或退页卸载敏感子树，无全局 storage/事件/业务缓存。
- 现金流水合计与查询错误共享固定高度区域；加载时金额显示未知并禁用账户余额入口，空结果与错误保留表头及滚动容器，反馈不推动表格。每月任务的空状态提示占用固定区域，刷新时保留各分组表头与空状态行高度。
- 公共表格/抽屉只复用展示；现金状态归可卸载 CashProvider。HTTP 技术日志脱敏路径，代理层亦需配置；ACL 管理仍保留平台安全审计。

## 依赖方向

[权限与审计](../permissions-and-audit/README.md)、[OA 集成](../oa-integration/README.md)、[公共财务表格](../finance-table-system/README.md)、[设置](../settings/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [backend/src/fin_ops_platform/app/routes_cash.py](../../../backend/src/fin_ops_platform/app/routes_cash.py)
- [backend/src/fin_ops_platform/app/cash_runtime.py](../../../backend/src/fin_ops_platform/app/cash_runtime.py)
- [backend/src/fin_ops_platform/services/cash_service.py](../../../backend/src/fin_ops_platform/services/cash_service.py)
- [web/src/features/cash/hooks.tsx](../../../web/src/features/cash/hooks.tsx)
- [tests/test_cash_runtime.py](../../../tests/test_cash_runtime.py)
- [tests/test_cash_http_integration.py](../../../tests/test_cash_http_integration.py)
- [web/src/pages/CashPage.tsx](../../../web/src/pages/CashPage.tsx)
- [web/e2e/production-cash-readonly.spec.ts](../../../web/e2e/production-cash-readonly.spec.ts)
- [web/e2e/cash-module-flow.spec.ts](../../../web/e2e/cash-module-flow.spec.ts)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
