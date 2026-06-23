# Read Model Workbench Active Generation Contract

**日期:** 2026-06-23
**Boundary:** `read-models:workbench-active-generation-contract`
**状态:** `closed-autonomous`
**范围:** Workbench active generation 特例合同守卫；不改 SQL、worker、matching、route、API shape、Go/Fiber、Go Worker 或生产状态。

## 执行结论

本轮审阅了 Workbench SQL read model 架构文档、`PostgresReadModelRepository` Workbench 读路径、`WorkbenchQueryFacade` 和既有 targeted tests。当前代码已经有较完整的 Workbench active generation 保护：

- `get_workbench_groups_page(...)` 已有测试锁定 page rows、count、row counts 和 source_versions 使用同一次 active generation。
- `get_workbench_summary(...)` 已锁定 active generation source_versions。
- `get_workbench_group_detail(...)` 和 `get_workbench_row_detail(...)` 只从 active generation 读取，并由 facade 层 source-version / refreshing gate 防止返回旧 group/detail。
- Workbench 仍是特殊 read model：不能机械套成普通 `ReadModelQueryGateway` rebuild 语义，必须保留 active generation 原子发布。

本轮不改运行时代码，只把这个特殊合同在 manifest 层加硬：`tests/test_read_model_manifest.py::test_workbench_manifest_preserves_active_generation_exception` 明确要求 Workbench 保持：

- `query_status_contract="equivalent_active_generation"`
- `projection_strategy="active_generation_scoped_publish"`
- `all_scope_semantics="active_month_shard_aggregate"`
- `force_refresh_contract="gateway_force_refresh_active_generation_scope"`
- repository port contract 必须覆盖 view、summary、groups page、group detail、row detail、refresh status、groups freshness status、load/save workbench read models。

## 改动前影响分析

### 1. 模块范围

- 目标模块: `read-models`
- 子边界: `workbench`
- 本次改动类型: active generation special-case manifest guard
- 是否改变业务行为: 否
- 是否改变 API response shape: 否
- 是否改变 SQL 查询或写入: 否
- 是否改变 worker refresh: 否
- 是否进入 Go / Fiber / Go Worker candidate: 否

### 2. Workbench active generation 合同

| Contract | 当前要求 | 测试/守卫 |
| --- | --- | --- |
| publish model | active generation 原子发布 | `projection_strategy="active_generation_scoped_publish"` |
| query status | 等价自管 freshness，不走普通 gateway | `query_status_contract="equivalent_active_generation"` |
| `all` scope | active month shard aggregate，不是普通 parent row | `all_scope_semantics="active_month_shard_aggregate"` |
| force refresh | gateway smoke 使用 active generation scope source | `force_refresh_contract="gateway_force_refresh_active_generation_scope"` |
| repository owner | view/summary/groups/detail/status/load/save 均属 Workbench port | `repository_port_contract` guard |

## Legacy 退役与污染防护

| Legacy path | 当前状态 | 本轮处理 | 后续 |
| --- | --- | --- | --- |
| 把 Workbench 当普通 read model rebuild | 不允许 | manifest guard 锁定 active generation 特例 | 后续 Workbench 切片继续保持 |
| API 请求路径旧 builder fallback | 架构文档禁止，既有测试覆盖 | 本轮不改 | page/API 切片继续守住 |
| active generation 混读 | 已有 targeted tests | 本轮不重复实现 | 若改 SQL 必须跑 Workbench SQL runtime tests |
| matching/candidates/worker rebuild | 本轮不触碰 | 禁止面记录 | Go hot-path admission 后再评估 |

## 七类测试映射

| 类别 | 是否适用 | 本轮覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改 Workbench 业务规则或匹配规则 |
| 2. Service-layer tests | 适用 | manifest Workbench active generation special-case guard |
| 3. API contract tests | 不适用 | 无 API shape 变化 |
| 4. Read model/cache/background job tests | 适用 | Workbench active generation repository port / publish contract 固化 |
| 5. Frontend component and interaction tests | 不适用 | 无前端行为变化 |
| 6. End-to-end business-flow integration tests | 不适用 | 本轮不触发 Workbench worker 或写链路 |
| 7. Existing feature regression tests | 适用 | 既有 Workbench SQL runtime/query facade/architecture tests 保持为后续必要验证集 |

## 环境与验证限制

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 是否需要真实 PostgreSQL: 否，本轮是 manifest/test guard。
- 是否需要真实 worker/outbox/readiness: 否。
- 是否会写生产数据: 否。
- 生产验证: 不适用。
- Secret handling: 未读取、未记录 secret。

## 后续边界

下一步推进 `read-models:bank-detail-and-bank-account-balance-contract`：

- 银行明细和账户余额是高频页面 read model，必须明确 month/all scope、auto-tag source versions、account balance 独立 read model 和 force refresh/barrier 合同。
- 优先做 contract/guard/analysis，不做大规模 SQL 拆分。
