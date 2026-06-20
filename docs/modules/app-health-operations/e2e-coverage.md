# 系统状态 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的系统状态 Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `APP-HEALTH-E2E-001` | `covered` | `web/e2e/app-shell.spec.ts`、`web/src/test/AppHealthOperationsPage.test.tsx`、`tests/test_app_health_api.py` | Browser 覆盖 admin shell、主导航、系统状态 active link、dashboard 标题、数据/请求区、刷新按钮和 dashboard API 调用；组件/API 覆盖 dashboard payload shape。 |
| `APP-HEALTH-E2E-002` | `covered` | `web/e2e/app-shell.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/AppHealthOperationsPage.test.tsx`、`tests/test_app_health_api.py` | Browser 覆盖 read-export 用户看到 admin-only 提示、dashboard 不渲染、protected dashboard API 零调用；后端/API 覆盖 admin-only contract。 |
| `APP-HEALTH-E2E-003` | `covered` | `web/e2e/app-shell.spec.ts`、`web/src/test/SessionGate.test.tsx`、session/auth API tests | Browser 覆盖 forbidden 和 expired session gate、dashboard 不渲染和 protected dashboard API 零调用。 |
| `APP-HEALTH-E2E-004` | `covered` | `web/e2e/app-shell.spec.ts` | 四条 Browser 路径均捕获 `pageerror`、`console.error`、非 abort `requestfailed` 和未预期 dialog。 |
| `APP-HEALTH-E2E-005` | `covered` | `tests/test_app_status_overview_service.py`、`tests/test_app_health_service.py`、`tests/test_app_health_alert_service.py`、`web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/AppStatusApi.test.ts` | 覆盖 green/yellow/red 优先级、runtime unavailable、readiness missing/failed、current-effective blocker、background task、dependency、alert、malformed payload 不默认 green 和全局 icon/popover。 |
| `APP-HEALTH-E2E-006` | `covered` | `tests/test_runtime_monitoring.py`、`tests/test_runtime_queue.py`、`tests/test_runtime_worker_registry.py`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/e2e/finance-table-system-flow.spec.ts` | 覆盖 dirty scopes、outbox、worker heartbeat/RabbitMQ、API metrics、unknown `--`、dashboard 宽表和代表性窄屏滚动。真实 systemd/RabbitMQ/Redis 归 `APP-HEALTH-E2E-010`。 |
| `APP-HEALTH-E2E-007` | `covered` | `tests/test_app.py`、`tests/test_app_postgres_mode.py`、`tests/test_health_ready_payload_probe.py`、`tests/test_http_slo_probe.py`、`tests/test_sse_smoke_probe.py`、`tests/test_runtime_sync_closure_gate.py`、`tests/test_slo_tool_defaults.py` | 覆盖 ready payload bounded、HTML fallback 失败、HTTP/SSE 零样本拒绝、SSE 首事件、health-ready 必经 gate、write/read-model runtime closure gate 输入错误分类。 |
| `APP-HEALTH-E2E-008` | `covered` | `tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`、`tests/test_deploy_runtime_examples.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 registry-derived worker/domain/read model/job/dependency、deploy examples 和 runtime boundary guards；新增 registry 项必须补测试。 |
| `APP-HEALTH-E2E-009` | `covered` | `web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/AppHealthStatusContext.test.tsx`、`web/src/test/AppHealthBroadcast.test.tsx` | 覆盖 dashboard refresh failure stale payload、App Status route independence、SSE/轮询和 BroadcastChannel sync。 |
| `APP-HEALTH-E2E-010` | `external-risk` | `bash scripts/verify.sh infra-smoke` staging gate、runtime/read-model/write-operation/RabbitMQ tool tests；当前生产 release 已补 health ready、runtime health、critical read model direct apply、user-level session 和 SSE 证据。 | 本地 contract 覆盖 API/UI/gate 语义；真实 RabbitMQ/Redis broker 采样、admin dashboard auth、user-level HTTP 4 个慢项和 controlled write-operation E2E 仍必须在 staging/runtime smoke 验证。 |

## 下一轮补测建议

1. staging 运行 `bash scripts/verify.sh infra-smoke`，带 `FIN_OPS_TEST_DATABASE_URL`、`RABBITMQ_TEST_URL` 和必要认证，逐步从 dry-run 升到 apply。
2. staging/production 继续运行 authenticated HTTP、admin dashboard 和 write-operation SLO gates，确保样本非空且不会把性能慢项当 pass。
3. 用真实大库 App Health dashboard 验证 dashboard metrics、`pg_stat_statements`、TTL cache 和宽表滚动性能。
