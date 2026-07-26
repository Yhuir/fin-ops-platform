# 税金抵扣模块维护入口

- Module key: `tax-offset`
- Route: `/tax-offset`
- Page key: `tax-offset`
- 状态：canonical PostgreSQL 直读

## 修改前必读

- `docs/product-specs/cost-tax.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/app-architecture/pages.md`
- `docs/architecture/module-boundaries/canonical-facts.md`
- `docs/modules/imports-invoices/boundary-io.md`
- `docs/modules/permissions-and-audit/boundary-io.md`

## 当前读取链

`TaxOffsetPage` 只调用 `/api/tax-offset*`。route 负责鉴权、参数和 HTTP 映射；`TaxOffsetQueryService` 组合业务响应；`PostgresTaxOffsetCanonicalRepository` 在一个显式 `REPEATABLE READ / READ ONLY` snapshot 中读取：

- `app.invoices`
- `app.tax_certified_import_records`
- `app.tax_offset_plans`

repository 固定执行发票、认证记录和最新计划三次查询，复用 `TaxOffsetService` 生成计划内/外认证匹配、锁定行、默认选择、summary 与 statistics。页面响应不含 `read_model_status`、`source_versions`、refresh enqueue 或 cache metadata，不返回 202，也不自动轮询。

税金页是 Workbench relation 非消费者：不读取 `app.workbench_pair_relations`、Workbench read model、成本统计 read model 或其它页面投影。OA/Mongo/MySQL/对象存储和文件解析不进入页面 GET 热路径；OA 附件必须先 promotion 为 canonical invoice。

## 写入链

- 认证导入：preview/confirm 与后台 import job owner 保持不变；完成后页面直接重新 GET canonical facts。
- 抵扣计划：`TaxOffsetPlanService` 校验 `canonical_snapshot_version`，保持权限、审计、幂等和 409 冲突；成功写入 `app.tax_offset_plans` 后页面直接重新 GET。
- 计划和认证写响应只返回 `affected_scope_keys`，不返回页面 read-model targets 或 operation barrier。

## 代码入口

- `web/src/pages/TaxOffsetPage.tsx`
- `web/src/components/tax/*`
- `web/src/features/tax/{api,types}.ts`
- `backend/src/fin_ops_platform/app/routes_tax.py`
- `backend/src/fin_ops_platform/services/tax_offset_query_service.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/tax_offset.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/tax_offset_page_audit.py`
- `backend/src/fin_ops_platform/services/tax_offset_service.py`
- `backend/src/fin_ops_platform/services/tax_offset_plan_service.py`
- `backend/src/fin_ops_platform/services/tax_certified_import_*`

## 共享清理边界

旧 tax read model、refresh/cache warmup/worker、App Status registry、deploy env、RabbitMQ route 和全局 cleanup migration 仍由主控在所有页面分支合并后统一处理。本模块直读链不得重新依赖这些共享兼容资源。

## 本目录文件

- `boundary-io.md`：直接/上下游 I/O、事实源、文件边界和删除条件。
- `state-machine.md`：页面、计划和认证导入状态。
- `tests.md`：七类测试映射、性能 guard 和回归命令。
- `e2e-spec.md` / `e2e-coverage.md`：Browser 合同及覆盖。
- `implementation-notes.md`：提炼后的实施记录。
