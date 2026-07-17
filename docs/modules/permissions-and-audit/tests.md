# 权限与审计测试矩阵

> 修改本模块前先读取本文件，确认会话、权限、审计、敏感数据和旧功能回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| OA token/session | `backend/src/fin_ops_platform/app/auth.py`、`web/src/features/session/api.ts` | cookie/header 解析、401/403、超时、local dev/test auth、过期 token |
| Access control | `AccessControlService`、settings access control | denied/read_export_only/full_access/admin 判断，动态 provider 失败时不可误拒绝已授权用户 |
| Session frontend | `SessionContext`、`SessionGate`、`web/e2e/app-shell.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts`、`tests/test_permissions_write_entry_inventory.py`、`docs/modules/permissions-and-audit/e2e-spec.md`、`docs/modules/permissions-and-audit/e2e-coverage.md`、`docs/modules/permissions-and-audit/write-entry-inventory.md` | loading/forbidden/expired/error/retry，权限 hooks 的默认 fail-closed，真实浏览器下未授权不渲染业务页，只读/全权限/admin 角色矩阵不越权，页面写入口矩阵不伪装 covered，pageRegistry 与 inventory 必须双向一致，pageRegistry 与 role matrix readable route 必须双向一致，新增页面必须进入 role matrix，dynamic opener 必须在 inventory 与 role matrix 双向一致，`covered-browser` row 必须有 dynamic opener 或登记在页面级静态覆盖 registry，dynamic opener/static registry 只能引用当前 `covered-browser` 模块且不能重复归类，Browser E2E 证据路径必须解析到当前文件或匹配真实 glob，新增 mutating feature API client 必须映射到 write-entry inventory，写控件关键词必须在 inventory 与 role matrix DOM 扫描 pattern 双向一致，源码高风险写控件文案 sentinel 必须仍存在且已登记，read-export visible enabled 写控件和已打开的关联台列顺序拖拽 settings 保存入口、关联台未配对候选动作、关联台已配对撤回动作、关联台现金处理行级菜单、关联台已处理/已忽略恢复、银行分类确认、银行人工待分类、银行自动标签、no-OA 标签、pending 规则、收入批量、进项支付规则、进项 OA reverse、销项收款规则/收据历史、OA pending 进行中/规则、ETC 对账流程、batch accounting 选择与已提交撤回、turnover 等动态区被 DOM 候选扫描拦截，并捕获隐藏浏览器错误 |
| API guards | `server.py` read/mutation/admin route helpers | read API、write API、export API、admin-only API 的二次校验和错误 shape |
| App health permissions | App Health dashboard / App Status popover / `web/e2e/app-shell.spec.ts` | dashboard admin-only，非 admin 不请求 dashboard；App Status admin link 受控 |
| Settings permissions | `SettingsPage`、`AppSettingsService` | admin 账户管理、只读用户不可保存、数据重置和 OA 凭据 admin-only |
| Export permissions | bank/tax/cost/input/output/turnover exports | read_export_only 可导出但不能写；导出错误/HTML 不能误当文件；`test_readonly_export_user_can_export_but_cannot_mutate_or_admin` 覆盖 cost/turnover 下载、pending export auth pass-through 和代表性写入/admin 403 |
| Audit trail | `AuditTrailService`、业务 service/UoW | actor、tenant、action、entity、金额、metadata；事务失败不能留下半条 audit |
| Sensitive data | auth/session/settings/credential/reset/logging | token、密码、DSN、凭据密文、附件正文不出现在 response/log/audit |

## 场景覆盖清单

| 场景 | 保护测试 | 说明 |
| --- | --- | --- |
| OA session bootstrap | `tests/test_session_api.py`、`web/src/test/SessionApi.test.ts`、`web/src/test/SessionGate.test.tsx`、`web/e2e/app-shell.spec.ts` | Authorization header、Admin-Token cookie、超时、expired、forbidden、retry；真实 Chromium 下 forbidden/expired 不触发 protected page API |
| protected API guard | `tests/test_auth_guard.py`、各 API 权限测试 | 无 token 401、无权限 403、导入端点也受保护；readonly export 聚合 smoke 校验代表性导出可读、写入/admin 仍拒绝 |
| access tier 判定 | `tests/test_session_api.py`、`tests/test_app_settings_service.py` | settings allowed/readonly/admin/full access、admin 自动 allowed、provider 失败；`test_get_session_me_projects_access_tier_matrix_from_settings` 聚合校验 `/api/session/me` 的角色能力矩阵 |
| write/admin 权限 | `tests/test_settings_data_reset_service.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_tax_offset_api.py`、`tests/test_pending_invoice_api.py`、`tests/test_turnover_ledger_api.py`、`tests/test_bank_auto_tag_rules_api.py` | 写入、规则保存、数据重置、OA 凭据、标签规则、turnover relation 的 403 |
| 前端隐藏/禁用 | `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/TaxOffsetPage.test.tsx`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts`、`tests/test_permissions_write_entry_inventory.py` | readonly/full-access/admin 不同 UI 能力；AppHealth dashboard admin-only 的真实浏览器 API 调用边界；只读用户全页面可读但 settings/tax/import/no-OA 写入口不可用；full-access settings 普通保存会真实发出 POST、返回 200、显示成功反馈且无隐藏浏览器错误；admin 能新增访问账户、保存权限数组并在保存后继续显示持久化账户，能保存 OA 申请人凭据 PUT/200、清空密码 DELETE/200、清空密码输入、确认页面和普通 settings 保存 body 不泄露密码，能打开 data reset 影响确认和 OA 密码复核弹窗并在取消后不创建 reset job，并能打开销项收款收据编号设置并保存一次 PUT/200；read-export 首屏和已打开的关联台列顺序拖拽 settings 保存入口、关联台未配对候选动作、关联台已配对撤回动作、关联台现金处理行级菜单、关联台已处理/已忽略恢复、银行分类确认、银行人工待分类、银行自动标签、no-OA 标签、pending 支出/收入规则、收入批量、进项支付规则、进项 OA reverse、销项收款规则/收据历史、OA pending 进行中/规则、ETC 对账流程、batch accounting 选择与已提交撤回、turnover 等动态区域 visible enabled 写控件关键词扫描防止同页新增按钮漏禁用；关键词覆盖拖动列、确认买票/确认为买票/确认为过账/取消现金处理/保存补充信息/保存凭据/清空密码/新增账户/数据重置等深层写动作，并由 inventory 单测锁住关键关键词不被误删 |
| audit 记录 | `tests/test_audit_service.py`、`tests/test_workbench_auth_context_idempotency.py`、`tests/test_bankdetail_write_uow_contract.py`、`tests/test_turnover_ledger_uow_contract.py`、业务 service tests | actor/tenant、事务内 audit、rollback、防半写入 |
| 敏感数据保护 | `tests/test_postgres_migrations.py`、`tests/test_app_postgres_mode_integration.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_settings_data_reset_service.py` | SQL 不含 secret、session/app health secret safe、密码不回显 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_session_api.py`、`tests/test_audit_service.py`、`tests/test_app_settings_service.py` | 覆盖 access tier 聚合矩阵、admin 自动 allowed、readonly 非写入、audit amount/metadata。 |
| 2. Service-layer tests | 适用 | `tests/test_workbench_auth_context_idempotency.py`、`tests/test_bankdetail_write_uow_contract.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_bank_auto_tag_rules_api.py` | 覆盖 actor/tenant 传递、事务内 audit + dirty/outbox、失败 rollback、规则权限。 |
| 3. API contract tests | 适用 | `tests/test_auth_guard.py`、`tests/test_session_api.py`、`tests/test_settings_data_reset_service.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_tax_offset_api.py`、`tests/test_pending_invoice_api.py`、`tests/test_app_health_api.py` | 覆盖 401/403、session payload、readonly export 路由聚合 smoke、write/admin 403、dashboard admin-only、错误字段。 |
| 4. Read model/cache/background job tests | 局部适用 | `tests/test_app_health_api.py`、`tests/test_runtime_queue_ops.py`、`tests/test_platform_runtime_boundary_guards.py` | 权限本身不走 read model；但 App Status 会消费 session/permission，worker/service 不得 import auth 或解析 cookie/header。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/SessionGate.test.tsx`、`web/src/test/SessionApi.test.ts`、`web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/TaxOffsetPage.test.tsx`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts`、`tests/test_permissions_write_entry_inventory.py`、`docs/modules/permissions-and-audit/e2e-spec.md`、`docs/modules/permissions-and-audit/e2e-coverage.md`、`docs/modules/permissions-and-audit/write-entry-inventory.md` | 覆盖 session gate、权限 hooks、readonly/admin UI、写入按钮隐藏/禁用、运维入口，以及真实浏览器中 AppHealth admin-only gate、全页面角色矩阵、admin 数据重置影响确认/OA 密码复核取消路径、admin 销项收据编号设置保存、首屏和已打开动态区域 visible enabled 写控件 DOM 候选扫描、写入口 inventory、pageRegistry/inventory 双向一致性 gate、role matrix、dynamic opener registry 双向一致性 gate、`covered-browser` dynamic/static proof gate、opener/static registry stale guard、Browser 证据路径解析 gate、mutating feature API client 到 inventory 的映射 gate、写控件关键词 registry 到 role matrix pattern 的双向一致性 gate、源码高风险写控件文案 sentinel gate 和严格浏览器错误捕获；已打开动态区包括关联台列顺序拖拽 settings 保存入口、关联台未配对候选动作、关联台已配对撤回动作、关联台现金处理行级菜单、关联台已处理/已忽略恢复、银行分类确认、银行人工待分类、银行自动标签、成本统计标签规则、no-OA 标签、pending 规则、收入批量、进项支付规则、进项 OA reverse、销项收款规则/收据历史、OA pending 进行中/规则、ETC 对账流程、batch accounting 选择与已提交撤回和 turnover。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_workbench_auth_context_idempotency.py`、`tests/test_turnover_workbench_integration.py`、`tests/test_write_operation_e2e_smoke.py`、`web/src/test/WorkbenchSelection.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 覆盖 session actor -> 写入 command -> audit/dirty/outbox、生产 test-owned Workbench checkpoint 显式读取并绑定当前 read-model version、readonly 用户无法写入的关键路径，以及 session -> route -> protected dashboard/API/页面写入口不越权的浏览器 smoke。 |
| 7. Existing feature regression tests | 适用 | 以上全部 + 下游模块权限测试 | 每次权限改动都可能影响所有页面/API；必须保护旧 401/403、旧导出、旧按钮、旧 audit、旧 admin-only 和浏览器层受保护 API 不被调用。 |

## 历史 bug 回归库

当前未在本模块发现需要新增到 `docs/dev/regression-bug-bank.md` 的已复现 bug。本轮把“前端隐藏不能替代后端权限”“malformed/expired session fail closed”“worker/service 不得 import auth 或解析 cookie/header”“敏感信息不泄露”作为既有回归保护记录。

## 关键 smoke flows

- 无 token 调 protected API -> `401 invalid_oa_session`；过期 token -> `401`；无权限用户 -> `403 forbidden`。
- OA session bootstrap -> `SessionGate` loading -> authenticated/forbidden/expired/error；超时后可 retry。
- 真实 Chromium 打开 `/operations/app-health`：admin 可见 dashboard；read_export_only、forbidden、expired 不能触发 `/api/operations/app-health-dashboard`。
- 真实 Chromium 以 `read_export_only` 逐页打开所有非 admin 页面：页面可读且不触发 POST/PUT/PATCH/DELETE；settings/tax/import/no-OA/OA pending/batch accounting/turnover/ETC 等已知写入口禁用或隐藏。
- 真实 Chromium 以 `full_access` 打开普通业务写入口并实际完成一次 settings 保存 POST/200/成功反馈，但不能访问 AppHealth dashboard；以 `admin` 打开 settings 高危区、AppHealth dashboard，新增访问账户并保存权限数组、验证保存后账户仍显示，完成一次 OA 申请人凭据 PUT/200 和清空密码 DELETE/200，且不把密码带入普通 settings 保存 body，打开 data reset 影响确认和 OA 密码复核弹窗并在取消后确认不创建 reset job，再打开销项收据编号设置并完成一次 receipt-settings PUT/200。
- admin 在 settings 保存访问控制 -> `/api/session/me` 对 allowed/readonly/full/admin 产出正确 tier。
- readonly export 用户可查询/导出，但看不到写入、导入确认、数据重置、高风险运维入口。
- full access 用户可业务写入，但不能维护 OA 凭据、访问账户管理、数据重置或 AppHealth dashboard。
- 写入 command 使用后端 session actor/tenant，不信任 request body actor；audit 与 dirty/outbox 同事务。
- 数据重置/OA 凭据/运维 dashboard 只允许 admin，失败响应不泄露密码/token。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_session_api.SessionApiTests.test_get_session_me_projects_access_tier_matrix_from_settings \
  tests.test_auth_guard.AuthGuardTests.test_readonly_export_user_can_export_but_cannot_mutate_or_admin \
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
  tests.test_permissions_write_entry_inventory \
  -v

cd web && npm test -- --run \
  src/test/SessionGate.test.tsx \
  src/test/SessionApi.test.ts \
  src/test/SettingsPage.test.tsx \
  src/test/WorkbenchSelection.test.tsx \
  src/test/AppHealthOperationsPage.test.tsx \
  src/test/AppStatusIndicator.test.tsx \
  src/test/TaxOffsetPage.test.tsx \
  src/test/NoOaBankBatchPage.test.tsx

cd web && npx playwright test e2e/permissions-role-matrix.spec.ts

bash scripts/verify.sh docs

cd web && npm run e2e:smoke
```

## Nightly CI 覆盖

Nightly full suite 应覆盖本模块的 session/auth/permission/audit 后端测试、前端 SessionGate/权限交互测试、Playwright app shell permission smoke、Playwright 全页面角色矩阵、docs verify。模块级快速验证使用上方命令。

## 未测风险

- 真实 OA 菜单、OA 角色同步、OA 会话接口超时/失败和生产 token 过期语义需要 staging/生产 smoke。
- 权限与审计已补 Spec-first 合同、覆盖映射、写入口 inventory、registry/role-matrix/inventory/dynamic opener 双向一致性 gate、`covered-browser` dynamic/static proof gate、opener/static registry stale guard、Browser 证据路径解析 gate、mutating feature API client 到 inventory 的映射 gate、写控件关键词 registry 到 role matrix pattern 的双向一致性 gate、源码高风险写控件文案 sentinel gate，以及 read-export 首屏和已打开动态区 visible enabled 写控件 DOM 候选扫描；已打开动态区包括关联台列顺序拖拽 settings 保存入口、关联台未配对候选动作、关联台已配对撤回动作、关联台现金处理行级菜单、关联台已处理/已忽略恢复、银行分类确认、银行人工待分类、银行自动标签、成本统计标签规则、no-OA 标签、pending 规则、收入批量、进项支付规则、进项 OA reverse、销项收款规则/收据历史、OA pending 进行中/规则、ETC 对账流程、batch accounting 选择与已提交撤回和 turnover。`PERM-E2E-003` 仍是 partial，缺的是尚未由 role matrix 自动打开的页面特定抽屉/弹窗深层发现和真实环境权限 smoke，不应伪装为 covered。
- 后端 session contract、代表性 readonly export 路由、AppHealth browser permission smoke 和本地 deterministic 全页面角色矩阵已有聚合测试；逐页面所有按钮、真实导出下载和生产代理层权限行为仍依赖各页面模块测试、Playwright 扩展和 staging/生产 smoke。
- 审计目前分散在多个业务 service/UoW；缺少统一生产审计查询/导出 smoke。
- 真实导出下载在浏览器和代理层的文件名、header 暴露和权限行为需要发布前 smoke。
