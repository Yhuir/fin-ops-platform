# OA 集成测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 必须保护的行为 | 代表测试入口 |
| --- | --- | --- |
| OA session / 权限 | `Admin-Token` -> Authorization、`/api/session/me`、无权限 403、只读/全操作/admin 分层 | `tests/test_auth_guard.py`、`tests/test_session_api.py`、`tests/test_oa_identity_service.py`、`web/src/test/SessionApi.test.ts`、`web/src/test/SessionGate.test.tsx` |
| OA Mongo 只读 adapter | 付款申请/报销/项目映射、字段变体、断连空结果、read status、backoff、附件发票 cache | `tests/test_mongo_oa_adapter.py`、`tests/test_mongo_oa_attachment_invoice_cache.py`、`tests/test_oa_attachment_invoice_service.py` |
| OA 投影与 sync worker | 投影 upsert、结构化附件、legacy row id 迁移、下游 dirty scope、retention cutoff、API enqueue 不 inline sync | `tests/test_oa_projection_sql_runtime.py`、`tests/test_worker_oa_sync.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` |
| OA 待付款 | rows/filter/detail API、read model stale/missing、权限、生命周期状态 | `tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_api.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` |
| OA 手动搜索/导入 | fast search、完成状态限制、附件刷新、幂等导入、删除 marker、Workbench/Search invalidation | `tests/test_oa_manual_import_service.py`、`tests/test_oa_manual_import_api.py`、`web/src/test/SettingsOaManualSearchImportTable.test.tsx` |
| OA applicant credentials | admin-only、保存/list/delete、password 不回显、repository 加密/解密、settings response 不泄漏 | `tests/test_oa_applicant_credentials_service.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_postgres_oa_applicant_credentials_repository.py`、`web/src/test/SettingsPage.test.tsx` |
| 目标 OA 申请人登录 | RSA 加密、HTTP/网络/无效 JSON/无 token 失败、错误不泄露 password、缺凭据不尝试登录 | `tests/test_target_oa_applicant_token_provider.py` |
| 进项发票 OA 反提 | preview hash、idempotency、目标申请人、草稿创建失败恢复、version conflict、人工 submitted/not_submitted、提交历史脱敏 | `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` |
| ETC OA 草稿 / 人工状态 | 草稿 payload、撤销本地绑定、manual status、删除本地批次不删除真实 OA、前端 OA review URL 清洗 | `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`web/src/test/EtcApi.test.ts`、`web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/EtcOaNavigation.test.ts` |
| 部署 / OA role sync | 同域路径、环境变量、nginx、deploy smoke、role assignment | `tests/test_deploy_oa_script.py`、`tests/test_deploy_oa_nginx_config.py`、`tests/test_oa_role_sync_service.py` |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_mongo_oa_adapter.py`、`tests/test_oa_manual_import_service.py`、`tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_etc_backend.py` | 保护 OA 字段映射、完成状态、反提状态机、ETC 人工确认和删除本地批次边界。 |
| 2. Service-layer tests | 适用 | `tests/test_target_oa_applicant_token_provider.py`、`tests/test_oa_applicant_credentials_service.py`、`tests/test_oa_projection_sql_runtime.py`、`tests/test_oa_pending_payment_service.py` | 保护 service/repository/worker 编排、凭据脱敏、外部 OA 登录失败、投影和下游 dirty scope。 |
| 3. API contract tests | 适用 | `tests/test_oa_applicant_credentials_api.py`、`tests/test_oa_manual_import_api.py`、`tests/test_input_invoice_usage_api.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_auth_guard.py`、`tests/test_session_api.py` | 保护 response shape、错误码、权限、read model status、idempotency/version conflict。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_oa_projection_sql_runtime.py`、`tests/test_worker_oa_sync.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`、`tests/test_mongo_oa_adapter.py` | 保护 OA sync worker、projection repository、Mongo read status/backoff、App Status worker/readiness 注册。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/SessionApi.test.ts`、`web/src/test/SessionGate.test.tsx`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/InputInvoiceUsage*.test.tsx`、`web/src/test/EtcApi.test.ts`、`web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/SettingsPage.test.tsx` | 保护 session bootstrap、权限态、OA 待付款 stale/detail、反提 drawer、ETC OA 操作、设置页凭据和手动导入。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_oa_projection_sql_runtime.py`、`tests/test_input_invoice_usage_api.py`、`tests/test_etc_backend.py`、`tests/test_oa_manual_import_api.py` | 保护 OA sync -> projection -> downstream dirty、进项反提 -> 草稿 -> 人工确认、ETC 业务批次 -> OA 草稿 -> 人工确认、手动导入 -> Workbench sync。 |
| 7. Existing feature regression tests | 适用 | 上述全部，加 `tests/test_platform_runtime_boundary_guards.py`、`tests/test_deploy_oa_script.py`、`tests/test_deploy_oa_nginx_config.py` | OA 集成横跨所有页面，任何改动都要先判断 session、权限、read model、Workbench、发票生命周期、税金/成本/search 是否受影响。 |

## 本轮新增回归

- `tests/test_target_oa_applicant_token_provider.py`
  - `test_http_error_uses_oa_message_without_exposing_password`
  - `test_network_failure_invalid_json_and_missing_token_are_failures`

这两个测试补齐目标 OA 申请人登录的外部失败分支：HTTP error、网络不可达、无效 JSON、缺 token 都必须失败，且错误信息不能泄漏目标申请人密码。

## 历史 bug 回归库

| 场景 | 回归入口 | 保护点 |
| --- | --- | --- |
| OA Mongo 短暂断连导致页面误认为 fresh | `tests/test_mongo_oa_adapter.py` | 断连返回空结果但 read status 为 error，并进入 backoff。 |
| OA lifecycle alias 导致附件发票 cross-OA blocker | 待补：`tests/test_mongo_oa_adapter.py`、`tests/test_audit_object_identity_tool.py`、alias policy/repository tests | `flowRequestId/processId` 缺失的进行中文档与带 `flowRequestId` 的已完成文档内容一致时，只能生成可审计 alias 候选；未批准 alias 仍 blocking，active alias 才可 canonicalize，且不得删除 OA 投影/cache。 |
| OA sync API 在 HTTP 进程内直接同步 | `tests/test_oa_projection_sql_runtime.py` | 手动 sync API 只 enqueue worker job，不 inline sync。 |
| 目标申请人凭据泄漏到 settings response | `tests/test_oa_applicant_credentials_api.py` | save/list/settings/delete response 不包含 password。 |
| 进项 OA 反提缺凭据仍创建本地 batch | `tests/test_input_invoice_usage_oa_reverse_service.py` | 缺凭据时不创建 batch，不伪造 OA 草稿成功。 |
| ETC OA 草稿 review URL 带 draft/filter 参数 | `web/src/test/EtcOaNavigation.test.ts` | 前端打开稳定 OA 表单列表，不携带 draft id 和 auto edit 参数。 |

## 关键 smoke flows

发布前或 staging 应至少人工/自动 smoke：

1. OA iframe 打开 `/fin-ops/?embedded=oa` -> `/api/session/me` 成功 -> 只读用户看不到写入口，全操作用户可写，管理员可进设置高风险入口。
2. OA sync `2026-05` -> 投影写入 -> Workbench / OA 待付款 / 进项使用 / App Status 显示 fresh 或 refreshing 一致。
3. 设置页保存目标 OA 申请人凭据 -> 进项发票选择 -> 创建 OA 草稿 -> OA 页面可见 draft -> 用户人工确认 submitted/not_submitted。
4. ETC 业务批次创建 OA 草稿 -> 撤销本地绑定或人工确认 submitted -> 删除本地批次不删除真实 OA 草稿/流程。
5. OA Mongo 临时不可用 -> 页面/API 不把旧投影伪装为 fresh，App Status 暴露 blocked/degraded。

P2/P3 一秒级闭环中，这些真实 OA 场景对应 `.planning/P2P3-CLOSURE-PLAN.md` 的 P2P3-013 staging gate。通过条件不是本地 mock 绿灯，而是真实 OA 登录、角色同步、目标申请人、草稿 URL、附件、人工 submitted/not_submitted、投影 freshness 和 App Status 语义均有 staging/production 证据。缺凭据、缺测试对象、只跑本地 stub 或只返回 `auth_missing` 时，状态保持 `staging-gated`。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_mongo_oa_adapter \
  tests.test_worker_oa_sync \
  tests.test_oa_identity_service \
  tests.test_oa_applicant_credentials_service \
  tests.test_oa_applicant_credentials_api \
  tests.test_postgres_oa_applicant_credentials_repository \
  tests.test_target_oa_applicant_token_provider \
  tests.test_input_invoice_usage_oa_reverse_service \
  tests.test_input_invoice_usage_api \
  tests.test_oa_pending_payment_service \
  tests.test_oa_pending_payment_api \
  tests.test_oa_projection_sql_runtime \
  tests.test_oa_manual_import_service \
  tests.test_oa_manual_import_api \
  tests.test_oa_role_sync_service \
  tests.test_deploy_oa_script \
  tests.test_deploy_oa_nginx_config \
  -v

cd web && npm test -- --run \
  src/test/SessionApi.test.ts \
  src/test/SessionGate.test.tsx \
  src/test/OaPendingPaymentsPage.test.tsx \
  src/test/InputInvoiceUsagePage.test.tsx \
  src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx \
  src/test/SettingsPage.test.tsx \
  src/test/SettingsOaManualSearchImportTable.test.tsx \
  src/test/EtcApi.test.ts \
  src/test/EtcTicketManagementPage.test.tsx \
  src/test/EtcOaNavigation.test.ts

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

Nightly CI 应至少覆盖：

- 后端 OA adapter / projection / sync / credentials / API contract tests。
- 前端 session、设置、进项 OA 反提、OA 待付款、ETC OA action mapper tests。
- `bash scripts/verify.sh docs`。

真实 OA/Mongo/staging smoke 不应塞进普通 nightly，除非有隔离测试环境和安全凭据。

## 未测风险

- 真实 OA 登录接口、RSA 公钥、`openssl`、目标申请人账号状态、OA 草稿页面 URL 和 OA 返回 token shape 只能由 staging/生产前 smoke 证明。
- 真实 OA Mongo 字段变体、历史附件、超大月份和索引性能不能由 stub 完全覆盖。
- 真实 OA 菜单角色同步、同域 cookie、iframe 下载/跳转、Nginx 代理行为需要部署环境验证。
- 真实 Postgres/RabbitMQ/Redis/systemd worker drain 和 App Status heartbeat 需要运行环境验证。
- 全页面全角色矩阵成本高，当前由代表性 API/UI 权限测试和 `permissions-and-audit` 模块统一覆盖。
