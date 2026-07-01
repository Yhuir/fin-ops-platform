# 日常报销批量账务管理提交 504/HTML GSD 分析

日期：2026-07-01

## 范围

- 用户症状：`日常报销批量账务管理` 页面点击 `关联OA项与流水` 后弹窗提示接口返回 HTML，路径显示 `/api/batch-accounting/submit`。
- 直接模块：`batch-accounting`。
- 上下游模块：`workbench_relation`、Workbench active read model、runtime worker/read model refresh、关联台、银行明细、成本统计、搜索、发票 lifecycle 相关页面。
- 本次产物：线上根因确认、最小 Bug 修复、实现前模块化全量分析、Read Model/API 性能评估与后续优化路线。

## 线上证据

- 生产 Nginx access log 在用户截图时间附近记录：
  - `2026-07-01 11:07:43 +0800`
  - `POST /fin-ops-api/api/batch-accounting/submit HTTP/2.0`
  - status `504`
  - referer `https://www.yn-sourcing.com/fin-ops/batch-accounting`
- 因为 Nginx `504` 默认响应是 HTML，前端 `apiClient` 正确识别为 “接口返回 HTML 页面”。这不是 React 页面按钮拼错路径。
- 同机验证当前路由和代理：
  - 直连 backend `POST /api/batch-accounting/submit` 返回 JSON `401 invalid_oa_session`。
  - HTTPS `/api/batch-accounting/submit`、`/fin-ops/api/batch-accounting/submit`、`/fin-ops-api/api/batch-accounting/submit` 均返回 JSON `401`，不返回 HTML。
  - Nginx active 配置中 `/api/`、`/fin-ops/api/`、`/fin-ops-api/` 均在 SPA fallback 之前代理到 Python API。
- 结论：线上错误不是“路由未注册/代理路径错”，而是请求进入后端后耗时超过 Nginx upstream 超时，Nginx 返回 HTML 504。

## 根因

### 1. 提交 route 没有走 SQL read model loader

列表接口已经使用：

- `BatchAccountingApiRoutes.list_payload(...)`
- `self._service_factory(use_sql_read_model=True).build_payload(...)`

但提交接口此前使用：

- `self._service_factory().submit(...)`

这让提交热路径默认回退到 `_build_api_workbench_payload("all")` 的旧全量工作台构建，而不是使用 `load_batch_accounting_workbench_payload(bank_year=...)`。提交按钮因此比页面列表更容易触发全量扫描和超时。

### 2. 提交 service 复用整页 `_build_context`

`BatchAccountingService.submit -> _submit_unlocked -> _build_context` 之前会在提交前构建整页上下文，并通过 `_relation_distribution_row_id_sets([*bank_rows, *open_oa_rows])` 请求整页银行/OA relation distribution。

对一次提交来说，真正需要校验的是本次选中的：

- 1 条银行流水；
- N 条 OA 主单；
- 当前 OA 关联的发票 rows；
- 这些 rows 的 relation readiness / active relation。

整页 relation distribution 是列表职责，不应成为写操作的默认前置扫描。

## 本次修复

- `POST /api/batch-accounting/submit` route 改为 `self._service_factory(use_sql_read_model=True).submit(...)`。
- `BatchAccountingService._submit_unlocked(...)` 使用 `_build_context(..., include_relation_distribution=False)`，避免提交时扫描整页 relation distribution。
- 提交前改为按本次 `row_ids` 调用 `_relation_read_model_status_for_row_ids(..., reason="batch_accounting_submit_relation_readiness")`。
- active relation 冲突检查改为一次 `active_relations_for_row_ids(row_ids)`，再在内存中判断：
  - 选中银行 row 已有关联则拒绝；
  - 选中 OA 已有关联银行流水则拒绝；
  - OA 只有发票关系仍允许补关联银行流水。
- 更新模块文档和 API 合同：submit 也优先走 SQL read model；写操作 freshness 按本次操作 rows，不按整页普通 relation distribution。

## 页面功能模块化分析

| 功能模块 | 当前边界 | 评价 | 后续重构方向 |
| --- | --- | --- | --- |
| 页面容器 `BatchAccountingPage` | 负责 bucket、年份、分页、搜索、选择、差额说明、overlay | 基本清晰，但页面状态仍偏厚 | 可拆为 `BankRail`、`OaSelectionTable`、`SubmittedRelationsView`、`BatchAccountingToolbar` |
| Frontend API `features/batchAccounting/api.ts` | DTO mapping、URL、JSON/HTML fallback | 清晰 | 保持只做传输和 DTO，不承载业务规则 |
| HTTP route `routes_batch_accounting.py` | query/body/session 到 service 的适配、mutation 后调度 persist/lifecycle | 已从 `server.py` 抽出，边界可接受 | 长期可继续减少 `server.py` wrapper，但不是本次 Bug 必要条件 |
| Service `BatchAccountingService` | 候选过滤、金额校验、relation command orchestration、撤回/修复 | 职责偏多，但仍在单一业务域内 | 拆出 read-side selector/query port、submit command validator、submitted relation presenter |
| Candidate read side | 通过 Workbench SQL active read model 构建候选 payload，无独立 batch read model manifest | 可运行但不是独立模块 | 若继续优化耗时，应引入窄 `batch_accounting` read repository 或独立 read model |
| Relation read side | `workbench_relation` facade 提供 distribution/freshness | 边界清晰 | 写操作必须保持 scoped row ids；列表可继续用 distribution |
| Relation write side | `WorkbenchRelationCommandService.confirm_relation/withdraw_relation` | 边界清晰，是关系事实 owner | 不允许回退 direct pair service |
| Lifecycle/worker | 成功写入后 dirty scopes、persist、barrier、worker refresh | 边界清晰 | 可增加 submit proxy/SLO probe |
| 下游页面 | 关联台、银行明细、成本统计、搜索等消费 relation/read model | 依赖方向正确 | 通过 operation barrier 和 derived lifecycle 保护，不由批量账务页面手工刷新事实 |

## Read Model 和 API 性能评估

线上 `/health/ready` 暴露的 API 性能摘要显示：

- `GET /api/batch-accounting`
  - sample_count `5`
  - p50 `1157.965 ms`
  - p95/p99 `11774.579 ms`
  - DB p95 `8692.965 ms`
  - SQL p95 `8690.921 ms`
  - query_count p95 `115`
- `POST /api/batch-accounting/submit`
  - health 摘要未保留成功样本，但 Nginx access log 已记录一次真实 `504`。
  - 修复前热路径会走旧全量 workbench loader，并扫描整页 relation distribution。
- `POST /api/batch-accounting/{relation_id}/withdraw`
  - 代码路径已经按 relation id / active relation rows 校验，结构比 submit 更窄。
  - 仍建议纳入 mutation SLO probe。

### 优化空间

| 优先级 | 目标 | 预期收益 | 风险 |
| --- | --- | --- | --- |
| P0 已完成 | submit route 使用 SQL read model，submit relation 检查只按选中 rows | 直接降低点击提交超时概率，避免 Nginx 504 HTML | 低，已有 API/service 回归 |
| P1 | 给 mutation endpoints 增加安全 POST SLO/proxy probe：无 auth/空 body 必须返回 JSON，不得 HTML | 提前发现 504/HTML/fallback | 低 |
| P1 | 对 `load_batch_accounting_workbench_payload` 的三段 SQL 做 `EXPLAIN ANALYZE`，检查 `read_model.workbench_rows` 的 `source_kind/scope_month/generation_id/scope_key/counterparty_name` 索引 | 降低 GET p95 和 submit 候选行加载耗时 | 中，需要生产数据计划证据 |
| P2 | 将 batch accounting 列表分页下推到 SQL：bank 和 OA 分别 count/page，不先取全量再 Python 裁剪 | 首屏和刷新耗时更稳定 | 中，需要 API pagination contract 保护 |
| P2 | 增加 selected-row loader：submit 只按 bank_row_id/oa_row_ids/invoice links 读取必要 payload | 提交耗时从候选规模相关变为选择规模相关 | 中，需要透明处理发票行和跨年 OA |
| P3 | 独立 `batch_accounting` read model manifest/worker/scope policy | 页面职责最清晰，性能最好 | 高，跨 worker/read model/docs/tests |

## 修复验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_route_handlers_do_not_bypass_service_boundaries -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_oa_nginx_config tests.test_http_slo_probe -v`
- `cd web && npm test -- --run src/test/apiClient.test.ts src/test/BatchAccountingApi.test.ts`

## 后续建议

1. 先部署本次 P0 修复，观察 `POST /api/batch-accounting/submit` 是否还出现 504。
2. 用生产库对 `load_batch_accounting_workbench_payload` 三条 SQL 做 explain，确认 GET p95 11.8s 的主因。
3. 如果 GET 仍超过目标耗时，优先做 SQL 分页下推和 selected-row loader，不要直接扩展 Nginx timeout 掩盖问题。
4. 中长期再评估独立 batch accounting read model；只有当 SQL active read model 调优仍不能满足页面 SLO 时再上独立 worker/read model。
