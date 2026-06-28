# 系统状态模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：系统状态页面只聚合 app health、app status、runtime worker、真实后台任务和依赖，不承载业务修复逻辑；页面域颜色不再由 legacy read-model readiness 或 projection diagnostics 决定。
- 当前缺口：server.py 仍保留部分 app health/status endpoint。
- 旧代码删除条件：所有 health/status endpoint 有明确 route/service owner 且前端只读观测 API。

## 职责边界

### 负责

- 系统状态页面、健康告警、worker runtime 状态和后台任务展示。
- 聚合 app status domain/job/dependency registry。
- 为运维判断 runtime convergence/worker 状态提供只读入口。

### 不负责

- 不直接执行生产修复或数据写操作。
- 不触发页面 read-model refresh、projection rebuild 或业务写操作。
- 不隐藏真实 runtime stale/processing 状态。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面读取 | `AppHealthOperationsPage.tsx`、`features/appHealth/api.ts` | 只读 API |
| Health probe | app health endpoints | 返回 runtime-ready/status |
| Runtime registry | app status services | 聚合 worker/job/dependency 状态；不消费 legacy read-model readiness |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| App health payload | 页面/indicator | 不伪装 runtime readiness；不返回 `workbench_read_model` / `workbench_relation_read_model` 或 read-model scope diagnostics |
| Alert/status | shell/status page | 明确 stale/failed/degraded/processing |
| Dashboard payload | operations page | 只读聚合 |

## 持久化与投影

- Own page read model：无独立 manifest entry。
- Reads runtime state of：worker/job/dependency registries。
- Service owner：`AppHealthService`、`AppStatusOverviewService`、`RuntimeMonitoring`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/AppHealthOperationsPage.tsx` |
| Frontend feature/context | `web/src/features/appHealth/*`、`features/appStatus/*`、`contexts/AppHealthStatusContext.tsx` |
| Shell | `web/src/components/shell/AppStatusIndicator.tsx` |
| Backend route | `/api/app-health*`、`/api/operations/app-health-dashboard` in `server.py` |
| Backend service | `app_health_service.py`、`app_health_alert_service.py`、`app_status_overview_service.py`、`runtime_monitoring.py` |
| Registries | `app_status_domain_registry.py`、`app_status_job_registry.py`、`app_status_dependency_registry.py` |
| Tools/tests | `tests/test_app_health*.py`、`tests/test_app_status*.py` |

## 依赖方向

- 允许依赖：status registries, runtime monitoring, app health services。
- 必须通过：read-only service APIs。
- 禁止绕过：系统状态页面触发业务写操作；隐藏 failed/stale worker；把 legacy read-model failed/stale 重新升级为页面域 blocked/busy。

## 测试与验证

- `tests/test_app_health_api.py`
- `tests/test_app_health_service.py`
- `tests/test_app_status_overview_service.py`
- `web/src/test/AppHealthOperationsPage.test.tsx`

## 当前缺口和删除条件

- 如果引入修复操作，必须拆成独立运维 command 模块并补权限/审计。
