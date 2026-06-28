# Read Model 模块维护入口

- Module key: `read-models`
- 类型: legacy guard module
- Route: `N/A`
- Page key: `N/A`

本模块只维护 page read-model 下线清单、负向 guard 和删除条件。页面读取目标是 `docs/architecture/direct-api-read-architecture.md` 定义的 direct API。

## 修改前必读

- `docs/architecture/direct-api-read-architecture.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/architecture/module-boundaries/canonical-facts.md`
- `docs/operations/runtime-worker-governance.md`

## 当前边界

- Active page read-model manifest 当前为空。
- App Status page read-model registry 当前为空。
- `ReadModelRefreshGateway` 已删除。
- Runtime queue page-refresh 方法已删除。
- Legacy dirty/readiness runtime tables 已由 migration `0082` 删除。
- 新页面/API 不得新增 read model、freshness gate、dirty scope、readiness proof、refresh worker、force refresh 或 operation barrier。

页面读取必须走：

```text
route -> service -> repository -> PostgreSQL canonical facts / OA SQL projection / import facts -> DTO
```

写后闭环必须走：

```text
mutation -> canonical facts + audit -> affected ids/months/version/job/committed projection -> frontend direct refetch
```

## 允许保留

- `READ_MODEL_MANIFEST`：空 guard。
- `APP_STATUS_READ_MODEL_REGISTRY`：空 guard。
- `read_model_scope_policy.py`：历史 scope 负向清单。
- `read_model_freshness.py`：legacy helper/guard 测试对象，不能成为新页面读取证明。
- `PostgresReadModelRepository` 中仍未删除的兼容/诊断 surface：必须逐步分类删除或证明为非页面事实。
- 真实后台任务：`job.outbox_events`、worker heartbeat、background jobs、`job.workbench_matching_dirty_scopes`。
- Current matching facts：`read_model.workbench_candidate_matches`、`read_model.workbench_reconciliation_decisions`。

| read_model_key | scope_type | 分区 key | 增量目标 | full rebuild fallback | freshness proof | force refresh |
| --- | --- | --- | --- | --- | --- | --- |
| 无 | 无 | 无 | 无 | 无 | 无 | 无 |

## 禁止路径

- 页面 API 返回 `read_model_status`、`read_model_stale_reasons`、`refresh_enqueued` 或 operation barrier target fields。
- 恢复 `.read_model.refresh` event lane、page refresh worker、scope repair、force refresh 或 freshness SLO。
- Redis/RabbitMQ/frontend domain event 作为页面可读证明。
- 业务 service 裸 SQL 写 page read-model dirty/readiness/outbox 状态。
- 生产缺 direct repository/view 时回退 live scan、memory snapshot 或旧 QueryService 并伪装 fresh。

## 模块 IO 合同

| IO | 当前合同 |
| --- | --- |
| Query input | 页面 query 不经过本模块；legacy 查询只能作为删除清单或内部诊断 |
| Refresh input | 已删除；不得新增 page `.read_model.refresh` |
| Output payload | 页面 payload 不带 legacy freshness 字段 |
| Outbox | 仅真实后台任务可用；不是 page freshness proof |
| Cache | Redis 只可作为可删除短 TTL response cache，不能证明 fresh |

## 测试入口

- `tests/test_read_model_manifest.py`
- `tests/test_read_model_architecture_guards.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_direct_api_contract_harness.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_runtime_worker_read_model_refresh_scopes.py`
- `tests/test_postgres_migrations.py`

## 本目录文件

- `state-machine.md`：guard-only 状态机。
- `boundary-io.md`：模块边界与 I/O。
- `tests.md`：负向 guard 和 direct API 回归矩阵。
- `e2e-spec.md` / `e2e-coverage.md`：E2E 下线验收。
- `implementation-notes.md`：历史实施记录，不作为当前架构入口。
