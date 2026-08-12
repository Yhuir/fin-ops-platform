# Read Model 模块维护入口

- Module key: `read-models`
- 类型: 资源模块
- Route / Page key: `N/A`

## 修改前必读

- `docs/architecture/persistence-and-read-models.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/modules/read-models/boundary-io.md`
- `docs/modules/runtime-workers/boundary-io.md`
- `docs/operations/runtime-worker-governance.md`

## 当前闭环

当前 runtime manifest 只登记一个 read model：`workbench_relation`。它向银行明细、待找发票、进项/销项等独立消费者分发正式关系的 linked/unlinked 视图；其 worker instance 是 `workbench-relation`。

| Manifest key | scope type | refresh event | worker instance |
| --- | --- | --- | --- |
| `workbench_relation` | `workbench_relation` | `workbench_relation.read_model.refresh` | `workbench-relation` |

`workbench_relation` 的 manifest 细节与代码常量保持逐字一致：

- partition key：`relation month_scope; all is fan-out only`
- scoped incremental target：`workbench relation distribution rows and groups for affected month scopes`
- full rebuild fallback：`gateway force refresh fan-out rebuilds relation month shards and marks empty scopes`
- freshness proof：`workbench_relation scope source_versions plus app_status readiness and current-effective dirty/outbox state`
- force refresh / operation barrier：`gateway_force_refresh` / `app_status_registry_target`

关联台页面不是 read model 消费者。它通过 `WorkbenchQueryFacade -> PostgresWorkbenchPageQueryRepository` 在请求内直接读取 canonical PostgreSQL facts、active formal relations 和异常决策：

- 一个请求使用一个 `REPEATABLE READ READ ONLY` snapshot。
- GET 不读或写 page generation，不访问 Redis page payload cache，不 enqueue refresh。
- API 不返回 `read_model_status`、generation/version、freshness proof 或 refresh job。
- 写命令继续使用 canonical entity/relation version、preview fingerprint、exact member set 和幂等；成功后页面执行一次 normal direct GET。
- `workbench-matching` 仍是 canonical relation 生产任务，不属于 read model registry。

历史 `read_model.workbench_*` 表和已应用 migrations 本 release 不删除，只作为 previous immutable release 的短期离线回滚证据。当前代码、worker、RabbitMQ、App Status、timer、cache 和 API 均不得访问它们。

## 代码入口

- `backend/src/fin_ops_platform/services/read_model_query_gateway.py`
- `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_scope_contract.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_model_scope_contracts.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `scripts/check-read-model-scope-contracts.py`

关联台 direct query 的入口列在 `docs/modules/reconciliation-workbench/boundary-io.md`，不归本模块所有。

## I/O 合同

### 输入

| 输入 | Owner | 合同 |
| --- | --- | --- |
| Relation query | consumer facade | 通过 `ReadModelQueryGateway` 读取登记的 `workbench_relation` scope；非 fresh 明确失败，不回退页面 direct query |
| Relation refresh request | `ReadModelRefreshGateway` + scope policy | normalize、validate、dedupe 后写 PostgreSQL durable queue |
| Transactional relation refresh | 明确登记的业务 UoW | 与 canonical write 同事务，承担等价 scope contract；不得恢复 page Workbench fan-out |
| Force refresh | 受控 runbook/tool | 权限、scope、dedupe、审计和结果证明齐全；页面 GET 不触发 |

### 输出

| 输出 | 合同 |
| --- | --- |
| `workbench_relation` payload | non-fresh 不得伪装为空集合；返回自己的 readiness/source proof |
| Dirty scope/outbox | PostgreSQL `job.read_model_dirty_scopes` 与 `job.outbox_events` 是唯一状态事实源 |
| Redis | 只能缓存通过 fresh gate 的登记 read model payload，不能保存关联台 direct page payload |
| RabbitMQ | 仅作 optional wakeup；只发布 registry 允许的 event，不是 freshness 事实源 |

## Public surface

- `ReadModelQueryGateway`
- `ReadModelRefreshGateway`
- `ReadModelScopePolicyRegistry`
- `READ_MODEL_MANIFEST`
- `WorkbenchRelationReadFacade` 及其 narrow repository port

## 禁止边界

- 业务 service 不得裸 SQL 写 dirty scope/outbox。
- 页面、route 或 direct repository 不得读取历史 `read_model.workbench_*`。
- 不得恢复 `workbench.read_model.refresh`、page worker、refresh-status、generation prune、page Redis cache、shadow read 或 fallback。
- 不得把 `workbench_relation` 接入关联台页面热路径。
- 不得把 `workbench-matching` 登记为 read model。
- Redis/RabbitMQ/前端事件不得成为业务或 freshness 事实源。

## Legacy 隔离

| 对象 | 当前状态 | 删除条件 |
| --- | --- | --- |
| 历史 Workbench page generation tables/views/indexes | rollback-only，当前 runtime 零 I/O | 稳定窗口结束、previous-release rollback 不再需要，并由独立 forward migration 精确删除 |
| 历史 Workbench page migrations | 永久保留 | 已应用 schema 历史不得删除或重写 |
| Workbench page worker/event/cache/timer/tools | retired | 当前 release 必须物理移除 active code/config，不保留兼容分支 |
| `workbench_relation` | active | 只有实际 consumer 全部迁出后才能另案评估 |

## 验证

- Manifest/registry/scope：`tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py`、`tests/test_read_model_scope_contract.py`。
- Gateway/runtime：`tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_query_gateway.py`、`tests/test_runtime_worker.py`、`tests/test_rabbitmq_runtime.py`。
- Workbench direct isolation：WorkBench repository/API contract tests、`tests/test_platform_runtime_boundary_guards.py`、whole-repo retired-symbol scan。
- Cross-page regression：银行明细、待找发票、进项/销项、OA、税金、成本、批量账务和 no-OA 的既有测试。

## 本目录文件

- `boundary-io.md`：当前边界与 I/O。
- `state-machine.md`：仅登记 read model 的状态机。
- `tests.md`：七类测试与验证入口。
- `implementation-notes.md`：提炼后的历史决策和生产证据；历史段落不是当前 runtime 合同。
