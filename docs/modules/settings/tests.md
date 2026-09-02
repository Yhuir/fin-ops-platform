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
- OA 精确附件刷新只登记现有 `oa.sync` operation；`completed` 与 `in_progress + expense_claim` 是后端可接纳状态，当前 UI 保留所有 completed OA 的刷新，并只对 `in_progress + expense_claim` 扩展刷新，且与 completed-only 正式导入能力隔离。POST 202、GET durable status/result，Settings API 不访问 Mongo/OCR/promoter，不以旧 projection 计数伪造同步成功。

## 七类测试

| 类别 | 适用性 | 当前入口 |
| --- | --- | --- |
| 1. 业务核心 | 适用 | `tests/test_app_settings_service.py`、`tests/test_session_api.py`、`tests/test_oa_role_sync_service.py`：canonical page accounts、casefold/重复、固定 005、页面允许/拒绝、permission-present 006、no-op/version、两个专用 OA 角色与补偿；成本统计无 OA 设置默认空、命名校验、schema v3、CAS 与标签归档保留 |
| 2. Service/repository | 适用 | `tests/test_app_settings_service.py`、`tests/test_workbench_settings_sync_api.py`、`tests/test_settings_data_reset_service.py`、`tests/test_settings_data_reset_job.py`、`tests/test_oa_attachment_refresh_request_service.py`、`tests/test_postgres_oa_applicant_credentials_repository.py`：ACL critical section、durable audit、精确刷新 enqueue/status、commit recovery、OA target/compensation |
| 3. API contract | 适用 | `tests/test_auth_guard.py`、`tests/test_session_api.py`、`tests/test_workbench_settings_sync_api.py`、`tests/test_app_health_api.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_oa_manual_import_api.py`、`tests/test_settings_data_reset_job.py`：精确刷新 202/status/result/error、direct URL/API 403、generic 400、dedicated admin-only、409/502/503 shape |
| 4. Read model/cache/worker | 适用（负向/共享） | `tests/test_runtime_queue.py`、`tests/test_oa_projection_sync_service.py`、唯一 inventory owner `tests/test_permissions_write_entry_inventory.py` + `tests/test_settings_data_reset_job.py`：精确 `oa.sync` terminal result、Settings API 零 Mongo/OCR/promoter、普通 save 零 dirty/read-model path，并锁定既有 worker/event 集合 |
| 5. 前端交互 | 适用 | `web/src/test/SessionApi.test.ts`、`web/src/test/SessionGate.test.tsx`、`web/src/test/App.test.tsx`、`web/src/test/PageRouteHost.test.tsx`、`web/src/test/SettingsPage.test.tsx`、`web/src/test/SettingsOaManualSearchImportTable.test.tsx`、`web/src/test/TableAlignmentStyles.test.ts`：HeroUI 控件、紧凑宽度、旧卡片 CSS 删除、静态说明移除、项目/标签页切换、访问账户、凭据隔离、数据重置两步确认与进度；精确刷新 queued/processing/done/failed、轮询取消及状态能力边界 |
| 6. 端到端 | 适用 | `web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts`：005 管理员、普通页面授权、无页面拒绝、direct protected API、admin-only controls、ACL save/restore/即时撤权及 reset 主链 |
| 7. 既有功能回归 | 适用 | 13-09 backend/inventory 与 13-11 frontend/Browser 证据；唯一 scanner 继续保护 AppHealth、OA credentials、data reset、权威路由注册、现有两个 read models/六个 workers和普通页面 I/O 不变 |

## 必须保留的负向断言

- `/api/workbench/settings` 不能写 `bank_transaction_tags`；银行自动标签只归银行明细 API。
- Settings owner 不得自行推断无 OA 流水；成本统计 route 必须传入 canonical 实际候选。自动标签归档不得静默删除成本统计的历史选择。
- pending invoice rule 保存不能恢复 `pending_invoice_rules_changed` 页面 fan-out。
- settings service/route 不直接 SQL 写 dirty scope/outbox，不调用 Workbench page builder。
- reset job payload、audit、日志和 error 不包含密码。
- Settings 不维护第二份 read-model dependency/fan-out matrix。
- OA refresh API 不得直接调用 `refresh_application_record_attachments` 或 attachment promoter，也不得在能力缺失时回读旧 projection 返回 200。

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
cd web && npm test -- --run
cd web && npm run build
```

真实 OA credential provider、生产 reset、对象存储和跨页面数据可见性必须在发布窗口以
受控 smoke 验证；本地测试不能替代这些外部依赖。
