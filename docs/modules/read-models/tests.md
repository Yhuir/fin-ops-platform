# Read Model 测试矩阵

> 本矩阵只维护 page read-model 下线的负向 guard 和 direct API 回归入口。历史 freshness/dirty/readiness 测试记录不再作为当前验收入口。

## 影响面

- 页面入口：无独立页面；各页面用自己的 direct API/前端测试覆盖 loading、empty、error、refetch。
- API payload：不得返回 `read_model_status`、`read_model_stale_reasons`、`refresh_enqueued` 或 operation barrier target fields。
- Runtime：`ReadModelRefreshGateway`、runtime queue page-refresh methods、page dirty/readiness runtime state 已删除并由 guard 覆盖。
- 真实后台任务：保留 import、OA、file migration、settings reset、Workbench matching 等 job/outbox/worker 测试；它们不是 page read-model freshness proof。

## 当前测试入口

| 类别 | 测试 | 目的 |
| --- | --- | --- |
| Manifest / registry | `tests/test_read_model_manifest.py` | 证明 active page read-model manifest 和 App Status registry 为空 |
| 架构 guard | `tests/test_read_model_architecture_guards.py` | 防止 refresh gateway、runtime queue refresh methods、旧 producer 回流 |
| 平台边界 guard | `tests/test_platform_runtime_boundary_guards.py` | 防止 app/services/tools 重新 import 或定义 page read-model gateway/worker |
| Direct API contract | `tests/test_direct_api_contract_harness.py` | 防止页面 API 暴露 legacy read-model fields |
| Runtime real workers | `tests/test_runtime_worker_registry.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` | 保留真实 worker，同时证明 page refresh scope 不回流 |
| Migration/drop proof | `tests/test_postgres_migrations.py` | 证明 legacy dirty/readiness 表 drop migration 存在 |

## 七类测试决策

| 类别 | 适用性 | 当前决策 |
| --- | --- | --- |
| 1. Business core unit tests | 不直接适用 | 业务规则由各业务模块覆盖 |
| 2. Service-layer tests | 适用 | 用 manifest、architecture guard、runtime registry/worker tests 覆盖删除边界 |
| 3. API contract tests | 适用 | 用 direct API contract harness 和各业务 API tests 防 legacy fields |
| 4. Read model/cache/background job tests | 适用 | 只保留负向 guard 和真实后台任务测试，不新增 page refresh worker 测试 |
| 5. Frontend component/interaction tests | 按页面适用 | 前端只测 direct refetch/committed projection，不测 operation barrier |
| 6. E2E business-flow integration tests | 按业务适用 | 由导入、OA、Workbench、发票、银行等业务模块覆盖 direct flow |
| 7. Existing regression tests | 适用 | guard tests 必须随本模块变更运行 |

## 最小验证

```bash
PYTHONPATH=backend/src python3 -m pytest \
  tests/test_read_model_manifest.py \
  tests/test_read_model_architecture_guards.py \
  tests/test_direct_api_contract_harness.py \
  -q
```

更大边界改动再加：

```bash
PYTHONPATH=backend/src python3 -m pytest \
  tests/test_platform_runtime_boundary_guards.py \
  tests/test_runtime_worker_registry.py \
  tests/test_runtime_worker_read_model_refresh_scopes.py \
  tests/test_postgres_migrations.py \
  -q
```

## 未测风险

- 本地测试不连接真实 PostgreSQL/RabbitMQ/Redis/systemd。
- 生产烟测应由 operations runbook 验证真实 background jobs、outbox、worker heartbeat 和 direct API HTTP SLO。
