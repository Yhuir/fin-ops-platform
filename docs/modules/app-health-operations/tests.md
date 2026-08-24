# 系统状态测试矩阵

日期：2026-08-23

本文只维护当前 App Health / App Status / System Audit 的有效测试入口。已退役的 read model、readiness、dirty scope、页面 Audit 组件和页面 refresh route 不再作为运行时或测试前提。

## 影响面与回归责任

| 层级 | 当前入口 | 必须保护的合同 |
| --- | --- | --- |
| App Health 页面 | `web/src/pages/AppHealthOperationsPage.tsx` | admin-only、只读 dashboard；唯一 System Audit 按钮；普通 dashboard refresh 清除旧 Audit 结果；unknown 显示 `--` |
| System Audit 前端 API | `web/src/features/appHealth/api.ts` | 只暴露固定 `fetchAppHealthSystemAudit()`，只请求 `page=app-health-operations`；不得恢复任意 page-key client |
| 业务页面 | `web/src/pages/*`、`web/src/components/*` | 不展示 Page Audit 控件，不依赖 Audit 结果，不产生额外 Audit I/O；原有加载、筛选、分页、抽屉和写后 canonical GET 保持不变 |
| Global App Status | `AppHealthStatusContext`、`features/appStatus/*`、`AppStatusIndicator` | 状态只来自 session、jobs、required workers、通用 outbox、dependencies、alerts；DTO/runtime summary 不恢复 read-model/readiness 字段 |
| HTTP routes | `/api/app-health`、`/api/operations/app-health-dashboard`、`/api/operations/app-health/page-audit` | auth guard、dashboard admin-only、System Audit 只读/fail-closed；后端 page proof 只供 System Audit/运维验证；旧 refresh/SSE routes 保持 404 |
| System Audit backend | `page_audit_registry.py`、`app_health_system_audit.py`、各 page proof repository | 一个 caller-owned `REPEATABLE READ READ ONLY` snapshot 编排 17 个子页 proof；覆盖 canonical facts、关系、inventory、worker/outbox 和 external evidence；不 refresh、不 repair、不写业务数据 |
| Runtime monitoring | `AppStatusOverviewService`、`RuntimeMonitoringRepository`、worker registry | 4 个 required worker 与 `job.outbox_events` 的 ready/busy/blocked 口径；runtime unavailable 不能变 green |
| Production evidence | deploy T+0/T+30、HTTP SLO、runtime closure、production admin App Health smoke | deployed release 与 remote main 一致；核心 GET p95/p99 达标；health-ready、worker/queue、System Audit 和只读浏览器链路通过 |

## 核心场景

- 管理员打开 App Health：dashboard 成功加载；点击 System Audit 只发送一次固定 GET，不产生 `POST/PUT/PATCH/DELETE`。
- 非管理员、forbidden 或 expired session：不请求 admin dashboard/System Audit。
- System Audit：内部 18 页合同与外部 evidence 分开呈现；external unknown 不能伪装端到端通过；任一子页、inventory、worker 或 outbox 问题 fail closed。
- 普通 dashboard refresh：清除上一份本地 Audit 结果，避免历史 snapshot 冒充当前状态。
- 业务/财务/导入/设置页：管理员身份下也没有 Audit 按钮；页面仍只执行本模块原有 canonical API 链路。
- App Status：worker `working` 不计问题；stale/missing/mismatch/unavailable 与 queue pending/processing/failed/backlog 按后端状态机展示；不存在 read-model summary。
- Workbench matching：stale/rebuilding/error 把 Workbench domain 标为 busy；failed dirty scope 产生 critical alert；两者都不恢复旧 matching BackgroundJob 或阻断全局写入。
- Dashboard/SLO：inventory、导入历史、请求 p95/p99、DB/SQL/连接指标保持有界；错误响应、HTML fallback、零样本和超时不得通过。

## 七类测试适用性

| 类别 | 适用性 | 当前入口与说明 |
| --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_app_status_overview_service.py`、external evidence tests：状态优先级、worker/queue/domain、external proof fail-closed |
| 2. Service-layer tests | 适用 | `tests/test_audit_app_health_system.py`、`tests/test_runtime_monitoring.py`、`tests/test_operations_dashboard_service.py`：单 snapshot 编排、runtime/inventory I/O、无写副作用 |
| 3. API contract tests | 适用 | `tests/test_app_health_api.py`、`web/src/test/AppHealthPageAuditApi.test.ts`：权限、固定 System Audit endpoint、错误合同、旧路径 404 |
| 4. Read model/cache/background job tests | 部分适用 | read model/cache 不适用，已由 `tests/test_read_model_runtime_removal.py` 防回归；background job、outbox、worker 由 runtime tests 覆盖 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/AppHealthOperationsPage.test.tsx`、各业务页面测试、`tests/test_page_audit_registry.py`：集中式按钮与分散入口删除合同 |
| 6. End-to-end integration tests | 适用 | `web/e2e/app-shell.spec.ts`、`web/e2e/production-admin-app-health.spec.ts`、System Audit PostgreSQL integration：API -> UI -> snapshot proof |
| 7. Existing feature regression tests | 适用 | 全量前端测试、backend App Health/runtime tests、生产 SLO/closure：保护其它页面与运维发布链 |

## 验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_page_audit_registry \
  tests.test_read_model_runtime_removal \
  tests.test_audit_app_health_system \
  tests.test_app_health_api \
  tests.test_app_status_overview_service \
  tests.test_runtime_monitoring \
  tests.test_operations_dashboard_service

bash scripts/verify.sh frontend
bash scripts/verify.sh lint
bash scripts/verify.sh docs
```

配置 `FIN_OPS_TEST_DATABASE_URL` 时，PostgreSQL integration 必须实际执行；未配置时只能报告 conditional skip。生产验证使用 `scripts/with-production-admin-token.sh` 加载本机 secret，禁止打印或提交 token。
