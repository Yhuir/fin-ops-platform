# Runtime Bootstrap 边界

本文记录 production bootstrap 和 repository injection 框架。当前阶段 production 主路径不再读取 full snapshot；旧 snapshot 只保留给迁移、shadow、测试和显式 legacy 兼容场景。

## 模式

`Application` 支持三个 bootstrap mode：

- `production`：默认模式。初始化业务服务时传入空 snapshot，只注入 SQL repositories、queue/cache/object-storage 和轻量配置；不得调用 `ApplicationStateStore.load()` / `PostgresStateStore.load()` / `LegacySnapshotBootstrap.load_full_snapshot()`。
- `legacy`：显式兼容模式。只用于 migration、shadow、test 或本地排障；通过 `LegacySnapshotBootstrap` 集中读取 full snapshot。
- `lightweight`：轻量模式。只初始化 state store、runtime repository context、queue/cache/object-storage 配置和 readiness 基础信息，不调用 `ApplicationStateStore.load()` 或 `PostgresStateStore.load()`。

默认 production 启动：

```python
from fin_ops_platform.app.server import build_application

app = build_application()
```

显式启动 lightweight 模式：

```python
from fin_ops_platform.app.server import build_application

app = build_application(bootstrap_mode="lightweight")
```

或通过环境变量：

```bash
FIN_OPS_BOOTSTRAP_MODE=lightweight \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.main --check
```

显式启动 legacy 兼容模式：

```bash
FIN_OPS_BOOTSTRAP_MODE=legacy \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.main --check
```

`legacy` 不属于 production 主路径。新增 API、worker 或服务构造不得依赖 legacy mode 才能启动。

## Repository Injection

注入上下文位于：

- `backend/src/fin_ops_platform/services/runtime_bootstrap.py`

`Application.runtime_repositories` 暴露：

- `state_store`：当前 store，仅作为过渡边界。
- `queue_repository`：PostgreSQL durable queue repository；只有 PostgreSQL store 可用。
- `redis_helper`：短 TTL cache、wakeup、辅助锁 helper；未配置 Redis 时为 no-op。
- `object_storage_settings`：S3-compatible 对象存储配置骨架。

后续新模块应优先从 `runtime_repositories` 或明确的 SQL repository factory 获取依赖，不再从 full snapshot 构造服务。

PostgreSQL store 额外暴露 `import_fact_repository`。导入相关新代码必须通过该 repository 做 SQL identity lookup、分页列表或批次/文件状态查询，不得在 production path 读取 `state:imports`、`state:file_imports` 或 `state:full_state` 来构造发票、银行流水、导入文件全量内存索引。

已迁移 read model 的 production PostgreSQL runtime 现在要求 SQL repository 可用：`/api/workbench`、`/api/cost-statistics/explorer` 和 `/api/tax-offset` 在 repository 缺失、miss 或 stale 时只能返回 `refreshing` / `read_model_unavailable` 状态并投递 durable refresh，不能回落到 `_build_api_workbench_payload()`、`CostStatisticsService.get_explorer()` 或 `TaxApiRoutes.get_tax_offset()` 同步重算。local pickle 与显式 `bootstrap_mode=legacy` 测试路径保留旧行为。

`PostgresStateStore.save()` 默认不再写 `state:full_state`。只有迁移、shadow 或测试工具确实需要旧 whole snapshot round-trip 时，才允许在工具进程内显式设置 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT=1`；该开关不得用于 production API 或 worker 主进程。

## Legacy Snapshot Allowlist

`LEGACY_SNAPSHOT_ALLOWLIST` 在 production 模块层面必须为空。只有 migration、shadow、test 这类非 production 主路径场景可以显式调用 `LegacySnapshotBootstrap.load_full_snapshot()`，并且 `reason` 必须带有 `legacy_`、`migration_`、`shadow_`、`test` 或 `unit_test` 前缀。

如果未来临时恢复 allowlist，必须满足：

- `snapshot_key`：旧 full snapshot 中的 key。
- `owner`：当前依赖该 snapshot 的服务。
- `module`：只能是 `migration`、`shadow` 或 `test` 相关编号/场景，不允许业务模块编号。
- `exit_condition`：删除该依赖前必须完成的验证条件。

新增 production snapshot 构造依赖不允许通过评审；必须改为 repository/read model 注入。

## 后续模块移除流程

1. 为模块建立 SQL repository 或 read-model repository。
2. 在 production bootstrap 下构造模块所需依赖，不调用 full snapshot。
3. 将业务 API 默认读写路径切到新 repository。
4. 补 backfill、worker、monitoring 和 rollback 文档。
5. 确认 `LEGACY_SNAPSHOT_ALLOWLIST` 仍为空。
6. 运行 guard test，确认 `app/server.py` 没有新增 `self._state_store.load()` 直接调用。

## Guard

测试入口：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap -v
```

Guard 会检查：

- 默认 `production` 和 `lightweight` 模式不触发 full snapshot load。
- legacy full snapshot 读取只通过 `LegacySnapshotBootstrap`，且拒绝 `application_startup` 等 production reason。
- `LEGACY_SNAPSHOT_ALLOWLIST` 为空。
- `app/server.py` 不直接调用 `self._state_store.load()`。
- production PostgreSQL workbench API 在 SQL read model repository 缺失时不会同步调用旧 workbench builder。
- `app/` 和 `services/` 下的 production 代码只能在显式 legacy 文件清单中调用 `_state_store.load()`；新迁移模块不得新增 direct snapshot fallback。
- production bootstrap 即使存在 OA Mongo 配置，也不会构造 direct `MongoOAAdapter`；旧 OA Mongo 读取只在 legacy/bootstrap、worker sync 或迁移工具中显式启用。
- PostgreSQL store 默认不会自动配置 legacy GridFS reader；GridFS 读取只允许 migration/backfill、audit/verify 或 rollback 工具显式注入 reader。
- PostgreSQL store 的已迁移 workbench/cost/tax read model loader 不会在 SQL 为空时读取 `state:workbench_*`、`state:cost_statistics_read_models` 或 `state:tax_offset_read_models` fallback。
