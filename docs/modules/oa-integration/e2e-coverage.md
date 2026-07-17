# OA Integration Spec-first E2E Coverage

## 覆盖矩阵

| Spec ID | 状态 | 当前证据 | 缺口 |
| --- | --- | --- | --- |
| `OA-E2E-001` | `partial` | `tests/test_auth_guard.py`、`tests/test_session_api.py`、`web/src/test/SessionGate.test.tsx`、permissions Browser smoke；生产 full_access 目标 OA 凭据只读 session 曾验证。 | 缺真实 admin 登录态和全角色 OA role sync smoke。 |
| `OA-E2E-002` | `partial` | `tests/test_mongo_oa_adapter.py`、`tests/test_worker_oa_sync.py`、`tests/test_oa_projection_sql_runtime.py`。 | 真实 OA Mongo 字段漂移/大月份/staging worker drain 未完整闭合。 |
| `OA-E2E-003` | `covered` | `web/e2e/oa-pending-payments-flow.spec.ts`、`oa-pending-payments-nonfresh-flow.spec.ts`、API/service/page tests。 | 真实 OA projection 输入归 `OA-E2E-002`。 |
| `OA-E2E-004` | `partial` | `web/e2e/input-invoice-usage-flow.spec.ts`、`tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_target_oa_applicant_token_provider.py`。 | 真实 OA 草稿创建和页面可见性需 staging/production。 |
| `OA-E2E-005` | `partial` | `web/e2e/etc-tickets-flow.spec.ts`、`tests/test_etc_backend.py`、`web/src/test/EtcOaNavigation.test.ts`。 | 真实 OA 草稿页面、撤销/人工状态和外部流程仍需 staging。 |
| `OA-E2E-006` | `covered` | `tests/test_oa_applicant_credentials_api.py`、`tests/test_postgres_oa_applicant_credentials_repository.py`、`web/src/test/SettingsPage.test.tsx`、permissions role matrix。 | 真实管理员账号缺口归 `OA-E2E-001/007`。 |
| `OA-E2E-007` | `external-risk` | deploy/nginx/session route contract tests、app-shell embedded smoke。 | 需要真实 OA iframe/cookie/Nginx/role sync。 |

## 当前验证入口

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_mongo_oa_adapter tests.test_worker_oa_sync tests.test_oa_identity_service tests.test_oa_applicant_credentials_service tests.test_oa_applicant_credentials_api tests.test_postgres_oa_applicant_credentials_repository tests.test_target_oa_applicant_token_provider tests.test_input_invoice_usage_oa_reverse_service tests.test_input_invoice_usage_api tests.test_oa_pending_payment_projection_rows tests.test_oa_pending_payment_api tests.test_oa_projection_sql_runtime tests.test_oa_manual_import_service tests.test_oa_manual_import_api tests.test_oa_role_sync_service -v
cd web && npm test -- --run src/test/SessionApi.test.ts src/test/SessionGate.test.tsx src/test/OaPendingPaymentsPage.test.tsx src/test/InputInvoiceUsagePage.test.tsx src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx src/test/SettingsPage.test.tsx src/test/EtcTicketManagementPage.test.tsx src/test/EtcOaNavigation.test.ts
```

## 下一步

1. 提供 admin OA 登录态或 admin token，补 authenticated admin gate。
2. 在 staging/production 执行真实 OA iframe/session、目标申请人草稿和 OA Mongo projection smoke。
3. 把真实 OA smoke 结果回填到本文件和 `docs/dev/testing-closure-state.md`。
