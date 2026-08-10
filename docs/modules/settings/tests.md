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
| 1. 业务核心 | 适用 | `tests/test_app_settings_service.py`、`tests/test_session_api.py`、`tests/test_oa_role_sync_service.py`：canonical accounts、casefold/overlap、005/full/read/denied、permission-present 006、no-op/version、严格三角色与补偿 |
| 2. Service/repository | 适用 | `tests/test_app_settings_service.py`、`tests/test_workbench_settings_sync_api.py`、`tests/test_settings_data_reset_service.py`、`tests/test_settings_data_reset_job.py`、`tests/test_postgres_oa_applicant_credentials_repository.py`：ACL critical section、generic-preserve-ACL、durable audit、commit recovery、OA target/compensation |
| 3. API contract | 适用 | `tests/test_auth_guard.py`、`tests/test_session_api.py`、`tests/test_workbench_settings_sync_api.py`、`tests/test_app_health_api.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_settings_data_reset_job.py`：direct URL/API 403、generic 400、dedicated admin-only、409/502/503 shape |
| 4. Read model/cache/worker | 适用（负向/共享） | 唯一 inventory owner `tests/test_permissions_write_entry_inventory.py` + `tests/test_settings_data_reset_job.py`：每次 evaluator 一次 provider、generic save 零 OA、ACL no-op 早于 OA/commit、零 cache/outbox/dirty/read-model path，并锁定现有两个 read models/六个 workers |
| 5. 前端交互 | 适用 | `web/src/test/SessionApi.test.ts`、`web/src/test/SessionGate.test.tsx`、`web/src/test/App.test.tsx`、`web/src/test/PageRouteHost.test.tsx`、`web/src/test/SettingsPage.test.tsx`：hostile OA evidence 不授予 tier、direct route gate、权威路由注册、独立 ACL 状态、移动端 HeroUI 分类选择器与重置原因校验 |
| 6. 端到端 | 适用 | `web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts`：admin/full/read/denied、direct protected API、admin-only controls、ACL save/restore/即时撤权及 reset 主链 |
| 7. 既有功能回归 | 适用 | 13-09 backend/inventory 与 13-11 frontend/Browser 证据；唯一 scanner 继续保护 AppHealth、OA credentials、data reset、权威路由注册、现有两个 read models/六个 workers和普通页面 I/O 不变 |

## 必须保留的负向断言

- `/api/workbench/settings` 不能写 `bank_transaction_tags`；银行自动标签只归银行明细 API。
- pending invoice rule 保存不能恢复 `pending_invoice_rules_changed` 页面 fan-out。
- settings service/route 不直接 SQL 写 dirty scope/outbox，不调用 Workbench page builder。
- reset job payload、audit、日志和 error 不包含密码。
- Settings 不维护第二份 read-model dependency/fan-out matrix。

## Phase 13 ACL 证据 ownership

- 13-09 的 backend matrix 由 `tests/test_session_api.py`、`tests/test_auth_guard.py` 与 admin-only API tests 提供；`YNSYLP006` fixture 刻意保留 OA business/dedicated roles 和 `finops:app:view`，但 canonical ACL 缺席仍 denied。
- `tests/test_permissions_write_entry_inventory.py` 是退役 authority、fixed OA selector 与 no-new-runtime 的唯一 whole-repo scanner；本模块不复制 scanner 或 allowlist。
- 13-11 的 frontend/Browser matrix 由四个 session/router component tests 和 `web/e2e/permissions-role-matrix.spec.ts` 提供，锁定 direct `/fin-ops/`、protected API 403、权威路由注册、AppHealth/OA credentials/data reset admin-only，以及管理员 ACL restore 后目标账号即时回到 denied。
- 真实 OA router/menu、fresh production token/session 和 post-deploy role matrix 只由 13-05 production checkpoint 证明；本地 deterministic mock 不替代该证据，本计划不声称已部署。

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
