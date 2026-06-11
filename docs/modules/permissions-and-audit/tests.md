# 权限与审计测试矩阵

> 修改本模块前先读取本文件，确认会话、权限、审计、敏感数据和旧功能回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| OA token/session | `backend/src/fin_ops_platform/app/auth.py`、`web/src/features/session/api.ts` | cookie/header 解析、401/403、超时、local dev/test auth、过期 token |
| Access control | `AccessControlService`、settings access control | denied/read_export_only/full_access/admin 判断，动态 provider 失败时不可误拒绝已授权用户 |
| Session frontend | `SessionContext`、`SessionGate` | loading/forbidden/expired/error/retry，权限 hooks 的默认 fail-closed |
| API guards | `server.py` read/mutation/admin route helpers | read API、write API、export API、admin-only API 的二次校验和错误 shape |
| App health permissions | App Health dashboard / App Status popover | dashboard admin-only，非 admin 不请求 dashboard；App Status admin link 受控 |
| Settings permissions | `SettingsPage`、`AppSettingsService` | admin 账户管理、只读用户不可保存、数据重置和 OA 凭据 admin-only |
| Export permissions | bank/tax/cost/input/output/turnover exports | read_export_only 可导出但不能写；导出错误/HTML 不能误当文件 |
| Audit trail | `AuditTrailService`、业务 service/UoW | actor、tenant、action、entity、金额、metadata；事务失败不能留下半条 audit |
| Sensitive data | auth/session/settings/credential/reset/logging | token、密码、DSN、凭据密文、附件正文不出现在 response/log/audit |

## 场景覆盖清单

| 场景 | 保护测试 | 说明 |
| --- | --- | --- |
| OA session bootstrap | `tests/test_session_api.py`、`web/src/test/SessionApi.test.ts`、`web/src/test/SessionGate.test.tsx` | Authorization header、Admin-Token cookie、超时、expired、forbidden、retry |
| protected API guard | `tests/test_auth_guard.py`、各 API 权限测试 | 无 token 401、无权限 403、导入端点也受保护 |
| access tier 判定 | `tests/test_session_api.py`、`tests/test_app_settings_service.py` | settings allowed/readonly/admin/full access、admin 自动 allowed、provider 失败 |
| write/admin 权限 | `tests/test_settings_data_reset_service.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_tax_offset_api.py`、`tests/test_pending_invoice_api.py`、`tests/test_turnover_ledger_api.py`、`tests/test_bank_auto_tag_rules_api.py` | 写入、规则保存、数据重置、OA 凭据、标签规则、turnover relation 的 403 |
| 前端隐藏/禁用 | `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/TaxOffsetPage.test.tsx` | readonly/full-access/admin 不同 UI 能力 |
| audit 记录 | `tests/test_audit_service.py`、`tests/test_workbench_auth_context_idempotency.py`、`tests/test_bankdetail_write_uow_contract.py`、`tests/test_turnover_ledger_uow_contract.py`、业务 service tests | actor/tenant、事务内 audit、rollback、防半写入 |
| 敏感数据保护 | `tests/test_postgres_migrations.py`、`tests/test_app_postgres_mode_integration.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_settings_data_reset_service.py` | SQL 不含 secret、session/app health secret safe、密码不回显 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_session_api.py`、`tests/test_audit_service.py`、`tests/test_app_settings_service.py` | 覆盖 access tier、admin 自动 allowed、readonly 非写入、audit amount/metadata。 |
| 2. Service-layer tests | 适用 | `tests/test_workbench_auth_context_idempotency.py`、`tests/test_bankdetail_write_uow_contract.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_bank_auto_tag_rules_api.py` | 覆盖 actor/tenant 传递、事务内 audit + dirty/outbox、失败 rollback、规则权限。 |
| 3. API contract tests | 适用 | `tests/test_auth_guard.py`、`tests/test_session_api.py`、`tests/test_settings_data_reset_service.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_tax_offset_api.py`、`tests/test_pending_invoice_api.py`、`tests/test_app_health_api.py` | 覆盖 401/403、session payload、write/admin 403、dashboard admin-only、错误字段。 |
| 4. Read model/cache/background job tests | 局部适用 | `tests/test_app_health_api.py`、`tests/test_runtime_queue_ops.py`、`tests/test_platform_runtime_boundary_guards.py` | 权限本身不走 read model；但 App Status 会消费 session/permission，worker/service 不得 import auth 或解析 cookie/header。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/SessionGate.test.tsx`、`web/src/test/SessionApi.test.ts`、`web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/TaxOffsetPage.test.tsx` | 覆盖 session gate、权限 hooks、readonly/admin UI、写入按钮隐藏/禁用、运维入口。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_workbench_auth_context_idempotency.py`、`tests/test_turnover_workbench_integration.py`、`web/src/test/WorkbenchSelection.test.tsx` | 覆盖 session actor -> 写入 command -> audit/dirty/outbox，以及 readonly 用户无法写入的关键路径。 |
| 7. Existing feature regression tests | 适用 | 以上全部 + 下游模块权限测试 | 每次权限改动都可能影响所有页面/API；必须保护旧 401/403、旧导出、旧按钮、旧 audit、旧 admin-only。 |

## 历史 bug 回归库

当前未在本模块发现需要新增到 `docs/dev/regression-bug-bank.md` 的已复现 bug。本轮把“前端隐藏不能替代后端权限”“malformed/expired session fail closed”“worker/service 不得 import auth 或解析 cookie/header”“敏感信息不泄露”作为既有回归保护记录。

## 关键 smoke flows

- 无 token 调 protected API -> `401 invalid_oa_session`；过期 token -> `401`；无权限用户 -> `403 forbidden`。
- OA session bootstrap -> `SessionGate` loading -> authenticated/forbidden/expired/error；超时后可 retry。
- admin 在 settings 保存访问控制 -> `/api/session/me` 对 allowed/readonly/full/admin 产出正确 tier。
- readonly export 用户可查询/导出，但看不到写入、导入确认、数据重置、高风险运维入口。
- full access 用户可业务写入，但不能维护 OA 凭据、访问账户管理、数据重置或 AppHealth dashboard。
- 写入 command 使用后端 session actor/tenant，不信任 request body actor；audit 与 dirty/outbox 同事务。
- 数据重置/OA 凭据/运维 dashboard 只允许 admin，失败响应不泄露密码/token。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_auth_guard \
  tests.test_session_api \
  tests.test_audit_service \
  tests.test_app_settings_service \
  tests.test_settings_data_reset_service \
  tests.test_oa_applicant_credentials_api \
  tests.test_bank_auto_tag_rules_api \
  tests.test_tax_offset_api \
  tests.test_pending_invoice_api \
  tests.test_turnover_ledger_api \
  tests.test_turnover_workbench_integration \
  tests.test_workbench_auth_context_idempotency \
  tests.test_bankdetail_write_uow_contract \
  tests.test_platform_runtime_boundary_guards \
  tests.test_app_health_api \
  -v

cd web && npm test -- --run \
  src/test/SessionGate.test.tsx \
  src/test/SessionApi.test.ts \
  src/test/SettingsPage.test.tsx \
  src/test/WorkbenchSelection.test.tsx \
  src/test/AppHealthOperationsPage.test.tsx \
  src/test/AppStatusIndicator.test.tsx \
  src/test/TaxOffsetPage.test.tsx

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

Nightly full suite 应覆盖本模块的 session/auth/permission/audit 后端测试、前端 SessionGate/权限交互测试、docs verify。模块级快速验证使用上方命令。

## 未测风险

- 真实 OA 菜单、OA 角色同步、OA 会话接口超时/失败和生产 token 过期语义需要 staging/生产 smoke。
- 全页面全角色矩阵没有在单个测试里穷尽；依赖各页面模块的权限交互测试和 nightly full suite。
- 审计目前分散在多个业务 service/UoW；缺少统一生产审计查询/导出 smoke。
- 真实导出下载在浏览器和代理层的权限行为需要发布前 smoke。
