# 税金抵扣模块边界与 I/O

日期：2026-06-28

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：税金抵扣页面通过 tax offset direct API 读取当前月份数据；后端不保留 page read-model worker 或 cost/tax SQL projection，前端不消费页面级 freshness 状态或等待 legacy operation barrier。
- 当前缺口：税金导入、认证、计划、cache warmup 与页面查询耦合较多，变更时必须明确影响面；历史 read_model 表/迁移仍待受控清理。
- 旧代码删除条件：legacy service/cache 路径不再被 worker、runtime、App Status 或 rollback 工具引用，并有 direct API/e2e 回归。

## 职责边界

### 负责

- 税金抵扣页面查询、认证导入、抵扣计划、direct API payload。
- 税金抵扣 direct payload 组装、cache warmup 和导入 job 结果。
- 抵扣计划保存和认证导入成功后，前端直接重新读取当前月份税金抵扣 API；服务端返回的 legacy target envelope 不再作为页面刷新前置条件。

### 不负责

- 不拥有成本统计 parent rollup。
- 不直接处理关联台关系事实写入。
- 不在页面里重新引入 legacy freshness gate 或读取旧缓存。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/筛选 | `TaxOffsetPage.tsx`、`features/tax/api.ts` | 进入 tax offset API/query service |
| 税金导入/认证 | tax certified import services | 写后返回受影响 tax offset scope/job diagnostics；前端成功后直接刷新当前月份 API |
| 抵扣计划保存 | `TaxOffsetPlanService.save_plan(...)` | 验证 direct source versions（存在时）后保存计划；不再校验 read-model scope；前端成功后直接刷新当前月份 API |
| Cache warmup scope | tax offset runtime/cache warmup | affected months；不投递 `tax_offset.read_model.refresh` |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 税金抵扣 rows/summary | 前端页面 | direct payload；不包含页面级 read model freshness 字段 |
| 导入/认证结果 | API/worker | 返回 job/result 并触发后端刷新/诊断；页面不等待 operation barrier |
| 计划保存结果 | 前端页面 | 保存成功后直接刷新页面数据 |
| Cache warmup | runtime/cache | affected months；不投递 `tax_offset.read_model.refresh` |

## 持久化与投影

- Page read model：无；历史表待清理
- Projection：无当前 cost/tax SQL projection
- Worker：无税金 page read-model worker；`tax-offset` / `cost-tax` lane 已下线
- Query owner：`TaxOffsetQueryService`
- Repository owner：tax offset direct query/repository ports

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/TaxOffsetPage.tsx` |
| Frontend feature/components | `web/src/features/tax/*`、`web/src/components/tax/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_tax.py` |
| Backend service | `tax_offset_service.py`、`tax_offset_query_service.py`、`tax_offset_runtime_service.py`、`tax_offset_plan_service.py` |
| Import services | `tax_certified_import_service.py`、`tax_certified_import_application_service.py`、`tax_certified_import_job_service.py` |
| Repository / SQL | 无当前 cost/tax projection；历史 read_model 表仅在迁移/cleanup 中处理 |
| Runtime/cache | `tax_offset_derived_lifecycle_executor.py`、`tax_offset_cache_warmup_executor.py`、`tax_offset_worker_rebuild_executor.py` |
| Tests | `tests/test_tax_offset*.py`、`web/src/test/Tax*.test.*`、`web/e2e/tax-offset-flow.spec.ts` |

## 依赖方向

- 允许依赖：certified import job service、tax offset runtime/cache warmup。
- 必须通过：TaxOffsetQueryService for reads, application/import service for writes。
- 禁止绕过：直接 SQL 写 legacy read model；把成本统计 parent aggregate 当成税金事实源。

## 测试与验证

- `tests/test_tax_offset_api.py`
- `tests/test_tax_offset_service.py`
- `tests/test_tax_offset_worker_rebuild_executor.py`
- `tests/test_tax_offset_cache_warmup_executor.py`
- `web/src/test/TaxOffsetPage.test.tsx` 覆盖保存/认证导入后直接刷新且不请求 operation barrier。
- `web/e2e/tax-offset-flow.spec.ts`

## 当前缺口和删除条件

- cache warmup 变更必须同步 runtime registry 和 deploy env。
- 删除历史 read_model 表/迁移前必须证明 runtime/rollback surfaces 不再依赖 legacy read model 数据；页面 API 已不依赖。
- 队列化认证导入的 job result 若未来暴露给页面刷新，页面仍应按 direct API refresh 合同消费，不重新引入 operation barrier 等待。
