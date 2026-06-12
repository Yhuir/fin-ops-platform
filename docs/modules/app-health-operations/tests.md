# 系统状态测试矩阵

> 修改本模块前先读取本文件，确认 App Health / App Status 的事实源、状态优先级、测试入口和旧功能回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| App Health page | `web/src/pages/AppHealthOperationsPage.tsx` | admin-only、只读 dashboard、刷新失败保留旧 payload、unknown 显示 `--` 而不是 0 |
| Global icon/popover | `web/src/components/shell/AppStatusIndicator.tsx` | icon 必须来自全局 `app_status`，路由切换不改变状态；admin 才显示运维入口 |
| Frontend providers/API | `AppHealthStatusContext`、`features/appHealth/api.ts`、`features/appStatus/api.ts` | SSE/轮询、malformed payload 不得默认 green、App Status mapper 字段兼容 |
| HTTP routes | `server.py` `/api/app-health*`、`/api/operations/app-health-dashboard` | auth guard、SSE contract、dashboard admin-only、cache stale after refresh error |
| Overview service | `AppStatusOverviewService` | green/yellow/red 优先级、readiness missing、critical failed/unavailable、dependencies、tasks、scope diagnostics |
| Runtime repository | `RuntimeMonitoringRepository` | dirty scopes/outbox/workers/readiness/RabbitMQ/API metrics 聚合，不可用 snapshot 不能变 green |
| Registries | domain/read model/job/dependency/worker registries | 新页面/read model/worker/job/dependency 必须同步 registry，否则状态 plane 漏报 |
| Readiness backfill | `app_status_readiness_backfill` | 只能从真实 projection 计算 readiness，不能批量伪造 fresh |
| Runtime ops tools | `runtime_queue_ops`、deploy worker examples | dead letter/replay/worker manifest 操作必须依赖 readiness 和 registry |

## 场景覆盖清单

| 场景 | 保护测试 | 说明 |
| --- | --- | --- |
| idle / busy / blocked health API | `tests/test_app_health_api.py`、`tests/test_app_health_service.py` | 覆盖 dirty OA scopes、workbench consistency failure、dependency error、background jobs、SSE |
| App Status overview | `tests/test_app_status_overview_service.py` | 覆盖 registry 一致性、background task、read model missing/failed、worker missing、runtime unavailable、current-effective blocker、历史 scope 诊断、API contract |
| Runtime monitoring metrics | `tests/test_runtime_monitoring.py` | 覆盖 backlog、failed jobs、stale dirty scopes、RabbitMQ、worker metrics、worker mismatch；App Status runtime repository 在 `tests/test_app_status_overview_service.py` 额外覆盖 legacy scope 与 covered outbox failure |
| Readiness backfill | `tests/test_app_status_readiness_backfill.py` | 覆盖 dry-run/apply、missing projection 不伪造 fresh |
| Worker/queue ops | `tests/test_runtime_worker_registry.py`、`tests/test_runtime_queue.py`、`tests/test_runtime_queue_ops.py`、`tests/test_deploy_runtime_examples.py` | 覆盖 registry-derived worker、outbox/dirty queue、dead letter resolve、deployment examples |
| Frontend dashboard | `web/src/test/AppHealthOperationsPage.test.tsx` | 覆盖只读 dashboard、admin gate、unknown metrics、refresh failure stale payload |
| Frontend global status | `web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/AppStatusApi.test.ts`、`web/src/test/AppHealthStatusContext.test.tsx`、`web/src/test/AppHealthResolver.test.ts`、`web/src/test/AppHealthBroadcast.test.tsx` | 覆盖 mapper、icon/popover、route independence、SSE/轮询和 BroadcastChannel sync |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_app_status_overview_service.py`、`tests/test_app_health_service.py`、`tests/test_app_health_alert_service.py` | 覆盖状态优先级、domain level、alert/job/readiness/dependency 判定。 |
| 2. Service-layer tests | 适用 | `tests/test_app_status_overview_service.py`、`tests/test_runtime_monitoring.py`、`tests/test_runtime_queue_ops.py`、`tests/test_app_status_readiness_backfill.py` | 覆盖 service/repository 边界、runtime snapshot、worker metrics、readiness 写入和 ops 操作约束。 |
| 3. API contract tests | 适用 | `tests/test_app_health_api.py`、`tests/test_app_status_overview_service.py`、`web/src/test/AppStatusApi.test.ts` | 覆盖 `/api/app-health`、SSE、dashboard admin-only、`app_status` shape、malformed payload 拒绝。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_runtime_monitoring.py`、`tests/test_runtime_queue.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_readiness_backfill.py` | 覆盖 dirty scopes、outbox、worker heartbeat、RabbitMQ、readiness missing/stale/failed。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/AppHealthStatusContext.test.tsx`、`web/src/test/AppHealthBroadcast.test.tsx` | 覆盖 dashboard、全局 icon、popover、admin link、SSE/轮询、BroadcastChannel。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_app_health_api.py`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx` | 覆盖 job/dirty/readiness -> API -> 前端展示的关键路径。真实 worker drain 到 UI 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | `tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py`、`tests/test_deploy_runtime_examples.py`、`web/src/test/AppStatusIndicator.test.tsx` | 保护旧页面 route registry、worker manifest、deploy env、App Status 不因路由切换或新 domain 漏报。 |

## 历史 bug 回归库

当前未在本模块发现需要新增到 `docs/dev/regression-bug-bank.md` 的已复现 bug。本轮把“malformed payload 不得默认 green”“runtime unavailable 不得空 green”“dashboard refresh 失败保留旧 payload 但标 warning”作为已有回归保护记录。

## 关键 smoke flows

- dirty scope/outbox pending -> `/api/app-health` busy/yellow -> App Status popover 显示受影响 domain。
- critical read model failed/unavailable -> App Status blocked/red -> 页面不能把旧数据当 fresh。
- legacy cost statistics scope 或已被后续真实完成事实覆盖的 outbox failure -> App Status 保持当前 canonical 状态，同时通过历史诊断暴露 repair/audit 信息。
- required worker missing/stale/mismatch -> runtime infrastructure warning -> App Health dashboard 和 App Status domain 可定位。
- import/data reset/background job running -> active background task -> App Status 显示任务进度和 affected domains。
- dashboard refresh 成功后展示数据/请求/后台三块；下一次刷新失败时保留旧 dashboard 并显示 warning。
- malformed app_status payload -> 前端 mapper 返回 null，不能默认 green。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_app_health_api \
  tests.test_app_health_service \
  tests.test_app_health_alert_service \
  tests.test_app_status_overview_service \
  tests.test_runtime_monitoring \
  tests.test_app_status_readiness_backfill \
  tests.test_runtime_worker_registry \
  tests.test_runtime_queue \
  tests.test_runtime_queue_ops \
  tests.test_deploy_runtime_examples \
  -v

cd web && npm test -- --run \
  src/test/AppHealthOperationsPage.test.tsx \
  src/test/AppStatusIndicator.test.tsx \
  src/test/AppStatusApi.test.ts \
  src/test/AppHealthStatusContext.test.tsx \
  src/test/AppHealthResolver.test.ts \
  src/test/AppHealthBroadcast.test.tsx

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

Nightly full suite 应覆盖本模块的后端 app health/status/runtime tests、前端 AppHealth/AppStatus tests、docs verify。模块级快速验证使用上方命令。

## 未测风险

- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker 的 heartbeat、queue backlog、DLQ、readiness convergence 需要 staging 或生产 smoke；本地测试使用 fake repository/connection 证明 contract。
- SSE 经过 Nginx/OA iframe 代理后是否缓冲、断线、回退轮询，需要真实部署 smoke。
- `/api/operations/app-health-dashboard` 的真实大库指标性能、pg_stat_statements 可用性和短 TTL cache 行为需要生产观测。
- App Status 只能证明全局运行事实 plane，不替代每个业务页面自己的 stale/error/loading 交互测试。
