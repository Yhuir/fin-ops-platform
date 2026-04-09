# 文档索引

推荐阅读顺序：

1. `pre.md`
2. `prd.md`
3. `domain-model.md`
4. `solution-design.md`
5. `roadmap.md`
6. `task-breakdown.md`

文件说明：

- `pre.md`：项目切入点、北极星和阶段边界
- `prd.md`：业务需求和功能范围整理
- `domain-model.md`：领域模型、状态机和规则映射
- `solution-design.md`：面向开发的模块方案和扩展边界
- `roadmap.md`：从 Reconciliation 到 OA / Project Costing 的路线图
- `task-breakdown.md`：Epic 级任务拆解和依赖关系

配套开发 prompt 在 `prompts/` 目录下，按编号顺序执行。

补充：

- `docs/dev/`：关联工作台 V2 的开发文档、接口契约和测试说明
- `docs/dev/ledger-and-reminder-rules.md`：Prompt 05 的台账与提醒规则说明
- `docs/dev/advanced-exception-rules.md`：Prompt 06 的高阶异常处理规则说明
- `docs/dev/oa-integration-foundation.md`：Prompt 07 的 OA 集成底座说明
- `docs/dev/project-costing-foundation.md`：Prompt 08 的项目归集与项目成本测算底座说明
- `docs/dev/cost-statistics-workbench.md`：成本统计页面的数据口径、页面层级、接口建议和导出要求
- `docs/dev/oa-menu-iframe-integration.md`：OA 菜单 iframe 集成说明，包含菜单配置、嵌入地址和 `/fin-ops/` 子路径部署约定
- `deploy/oa/README.md`：OA 同域部署、发布顺序、联调验收和回滚说明
- `deploy/oa/nginx.fin-ops.conf.example`：`/fin-ops/` 与 `/fin-ops-api/` 反向代理示例
- `deploy/oa/fin_ops.env.example`：OA 集成相关环境变量模板
- `deploy/oa/fin_ops_menu.mysql.sql`：OA 菜单 SQL 模板
- `deploy/oa/fin_ops_role_binding.mysql.sql`：OA 只读/全操作/管理员角色与菜单绑定 SQL 模板
- `deploy/oa/fin_ops_user_role_sync.mysql.sql`：按单个 OA 账户同步“隐藏 / 只读导出 / 全操作 / 管理员”角色的 SQL 模板
- `docs/dev/`：税金抵扣 25-27 现已按“计划 / 已认证结果 / 试算”口径重构，重点是只读销项、可编辑进项计划和右侧已认证抽屉
- `docs/dev/reconciliation-workbench-v2-backend.md`：已更新 Prompt 14 的 Workbench V2 后端契约与税金 API
- `docs/superpowers/specs/2026-04-01-cost-statistics-workbench-design.md`：成本统计页面设计文档
- `docs/superpowers/specs/2026-04-01-cost-statistics-project-export-design.md`：项目明细强导出设计文档
- `docs/superpowers/specs/2026-04-02-workbench-global-search-design.md`：关联台强搜索设计文档
- `docs/superpowers/specs/2026-04-03-tax-offset-certified-plan-design.md`：税金抵扣“计划 vs 已认证结果”设计文档
- `docs/superpowers/specs/2026-04-07-tax-offset-certified-import-design.md`：税金抵扣“已认证发票真实模板导入”设计文档
- `docs/superpowers/specs/2026-04-03-oa-shell-auth-visibility-design.md`：OA 页面壳体接入、登录复用和仅少数账户可见的设计文档
- `docs/superpowers/specs/2026-04-07-oa-access-role-management-design.md`：OA 接入后的访问账户管理、只读导出权限和 `YNSYLP005` 独占管理设计文档
- `docs/superpowers/specs/2026-04-08-workbench-pair-relations-design.md`：关联台配对关系独立建模与 `确认关联 / 取消配对` 轻量写模型设计文档
- `docs/superpowers/specs/2026-04-08-workbench-materialized-read-model-design.md`：关联台 `pair relations + 物化读模型` 的性能重构设计文档
- `docs/superpowers/specs/2026-04-08-workbench-pane-search-filter-sort-design.md`：关联台三栏局部搜索、多选筛选与按组时间排序设计文档
- `docs/superpowers/specs/2026-04-08-workbench-column-layout-drag-design.md`：关联台三栏列拖拽排序、宽度联动与登录后持久化设计文档
- `docs/superpowers/plans/2026-04-01-cost-statistics-workbench.md`：成本统计页面实施计划
- `docs/superpowers/plans/2026-04-02-workbench-global-search.md`：关联台强搜索实施计划
- `docs/superpowers/plans/2026-04-03-tax-offset-certified-plan.md`：税金抵扣“计划 vs 已认证结果”实施计划
- `docs/superpowers/plans/2026-04-07-tax-offset-certified-import.md`：税金抵扣“已认证发票真实模板导入”实施计划
- `docs/superpowers/plans/2026-04-03-oa-shell-auth-visibility.md`：OA 页面壳体接入、登录复用和可见性控制实施计划
- `docs/superpowers/plans/2026-04-07-oa-access-role-management.md`：OA 接入后的访问账户管理与权限分层实施计划
- `docs/superpowers/plans/2026-04-08-workbench-pair-relations.md`：关联台 pair relations 轻量写模型与动作性能重构实施计划
- `docs/superpowers/plans/2026-04-08-workbench-materialized-read-model.md`：关联台 `pair relations + read model` 的读写分离实施计划
- `docs/superpowers/plans/2026-04-08-workbench-pane-search-filter-sort.md`：关联台三栏局部搜索、多选筛选与按组时间排序实施计划
- `docs/superpowers/plans/2026-04-08-workbench-column-layout-drag.md`：关联台三栏列拖拽排序、持久化与渲染接线实施计划
- `OA 集成当前 app 技术方案.md`：基于真实 OA 源码分析的总接入方案
- `docs/superpowers/specs/2026-03-26-import-formalization-design.md`：导入正式化 A 的设计文档
- `docs/superpowers/plans/2026-03-26-import-formalization.md`：导入正式化 A 的实施计划
- `docs/superpowers/plans/`：面向执行的实现计划
