# 设置测试矩阵

## 当前不变量

- settings route 只做 HTTP/auth 映射，业务校验、version、audit 和 persistence 由
  `AppSettingsService`/专属 service 负责。
- 普通设置保存只提交 canonical settings/version/audit，不 fan-out 已退役页面 dirty scope，
  不返回 freshness 或 operation-barrier target。
- canonical 页面在下一次 normal GET 读取新设置；`workbench` 与 `workbench_relation`
  只按各自 owner 的显式 maintenance/reset 合同刷新。
- OA applicant credential 使用独立 repository；password/cipher/token 不进入普通 settings
  payload、日志或错误。
- data reset 是独立 durable job + `settings-maintenance` worker，必须保护权限、密码复核、secret 不持久化、protected targets、进度、
  interrupted destructive reset fail-closed、API graceful reload 和页面重进；job 完成不依赖 API 线程或 retired page worker。

## 七类测试

| 类别 | 适用性 | 当前入口 |
| --- | --- | --- |
| 1. 业务核心 | 适用 | `tests/test_app_settings_service.py`、`tests/test_oa_applicant_credentials_service.py`：normalize、版本、非法映射、权限、凭据 |
| 2. Service/repository | 适用 | `tests/test_settings_data_reset_service.py`、`tests/test_settings_data_reset_job.py`、`tests/test_postgres_oa_applicant_credentials_repository.py`、`tests/test_target_oa_applicant_token_provider.py` |
| 3. API contract | 适用 | `tests/test_settings_data_reset_job.py`、`tests/test_workbench_settings_sync_api.py`、`tests/test_oa_manual_import_api.py`、`tests/test_oa_applicant_credentials_api.py`：admin/password、enqueue 失败、错误、secret 隔离、retired target 缺失 |
| 4. Read model/cache/worker | 适用（负向/共享） | `tests/test_settings_data_reset_job.py`、`tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py`、`tests/test_platform_runtime_boundary_guards.py`：durable reset/reload、普通保存零页面 fan-out、registry/manifest 一致 |
| 5. 前端交互 | 适用 | `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx` |
| 6. 端到端 | 适用 | `web/e2e/settings-data-reset-flow.spec.ts`：确认、密码、job polling、reload、错误恢复 |
| 7. 既有功能回归 | 适用 | 全量 backend/frontend/E2E；重点保护权限、OA、关联台、银行、发票、成本和税金 |

## 必须保留的负向断言

- `/api/workbench/settings` 不能写 `bank_transaction_tags`；银行自动标签只归银行明细 API。
- pending invoice rule 保存不能恢复 `pending_invoice_rules_changed` 页面 fan-out。
- settings service/route 不直接 SQL 写 dirty scope/outbox，不调用 Workbench page builder。
- reset job payload、audit、日志和 error 不包含密码。
- Settings 不维护第二份 read-model dependency/fan-out matrix。

## 验证

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_app_settings_service \
  tests.test_settings_data_reset_service \
  tests.test_settings_data_reset_job \
  tests.test_oa_applicant_credentials_service \
  tests.test_oa_applicant_credentials_api \
  tests.test_workbench_settings_sync_api \
  tests.test_oa_manual_import_api -v
cd web && npm test -- --run src/test/SettingsPage.test.tsx src/test/WorkbenchSelection.test.tsx
```

真实 OA credential provider、生产 reset、对象存储和跨页面数据可见性必须在发布窗口以
受控 smoke 验证；本地测试不能替代这些外部依赖。
