# 设置测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口、影响面和应保护的旧功能。实现后按实际影响更新矩阵。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/SettingsPage.tsx` | section 切换、loading/error、admin-only、保存按钮、数据重置确认、active reset job reentry |
| Workbench settings modal | `web/src/components/workbench/WorkbenchSettingsModal.tsx` | 关联台内设置入口、项目同步、账户映射、数据重置入口与设置页共享 API |
| Frontend API mapper | `web/src/features/workbench/api.ts` | snake_case/camelCase、`pending_invoice_tag_groups`、不得回传 `bank_transaction_tags`、data reset job、OA credential payload 不泄密 |
| HTTP routes | `server.py` `/api/workbench/settings*` | settings GET/POST、项目 sync/create/delete、OA 手动导入 mutation、data reset、credential routes 的权限和 response shape |
| Settings service | `AppSettingsService` | 项目、权限、银行映射、OA 配置、拒绝银行标签写入、待找发票规则版本、audit、OA role sync |
| Data reset service | `SettingsDataResetService` | protected targets、导入/文件/关联台/read model/dirty scope 清理、OA rebuild、progress、错误不泄密 |
| Credential service | `OaApplicantCredentialService`、repository、target token provider | admin-only、pgcrypto 加密、列表不解密、密码不进 settings payload、不泄露真实 OA password |
| Read model / worker | `DerivedDataLifecycleService`、runtime worker/readiness registries | settings 变更必须产生正确 dirty/read model fan-out；reset 后旧缓存/read model 不能伪装 fresh |
| App Status / App Health | app status registries、overview service | reset/job/dirty scope/worker busy 必须可见；设置页不能只看局部组件状态 |

## 场景覆盖清单

| 场景 | 保护测试 | 说明 |
| --- | --- | --- |
| 保存项目、权限、银行映射和 OA 配置 | `tests/test_app_settings_service.py`、`tests/test_workbench_settings_sync_api.py`、`web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` | 覆盖 normalize、state store round-trip、OA role sync、项目 sync/create/delete API 权限、只读/管理员 UI |
| OA 手动导入 mutation 权限 | `tests/test_oa_manual_import_api.py` | 覆盖 refresh attachments、manual import create、manual import delete 在只读 session 下返回 403，且不会调用下游写服务或接受 body actor 伪造。 |
| 保存待找发票规则且拒绝银行标签回写 | `tests/test_app_settings_service.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/SettingsPage.test.tsx`、`tests/test_derived_data_lifecycle_service.py` | 覆盖 `/api/workbench/settings` 不接受 `bank_transaction_tags`、`AppSettingsService.update_settings(...)` 不暴露银行标签写参数、前端不回传银行标签展示字典、非法映射、audit、规则 version、下游 lifecycle fan-out；银行自动标签保存归属 `bank-details` 模块。 |
| 数据重置 | `tests/test_settings_data_reset_service.py`、`web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` | 覆盖 admin/password gate、job progress、protected targets、reset OA rebuild、失败不清数据不泄密 |
| OA 申请人凭据 | `tests/test_oa_applicant_credentials_*`、`tests/test_target_oa_applicant_token_provider.py`、`web/src/test/SettingsPage.test.tsx` | 覆盖 admin-only、无密码回显、加密、目标 OA 登录 provider |
| 旧功能回归 | `tests/test_postgres_migrations.py`、`tests/test_app_status_overview_service.py`、相关下游模块测试 | 保护 settings payload 兼容、迁移、App Status 和下游页面不被配置变更误伤 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_app_settings_service.py`、`tests/test_oa_applicant_credentials_service.py` | 覆盖 settings normalize、访问控制、项目状态、银行标签写入边界、待找发票规则版本、非法映射、版本冲突、凭据必填/admin-only。 |
| 2. Service-layer tests | 适用 | `tests/test_app_settings_service.py`、`tests/test_settings_data_reset_service.py`、`tests/test_oa_applicant_credentials_service.py`、`tests/test_postgres_oa_applicant_credentials_repository.py`、`tests/test_target_oa_applicant_token_provider.py` | 覆盖 state store、audit、OA role sync、settings 拒绝银行标签回写、data reset、protected targets、PG 加密、目标 OA login provider。 |
| 3. API contract tests | 适用 | `tests/test_app_settings_service.py`、`tests/test_workbench_settings_sync_api.py`、`tests/test_oa_manual_import_api.py`、`tests/test_settings_data_reset_service.py`、`tests/test_oa_applicant_credentials_api.py` | 覆盖 `/api/workbench/settings`、`bank_transaction_tags_write_forbidden`、settings project mutation、OA manual import mutation、data reset job、credential routes、权限、错误、job、protected_targets、无密码回显。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_settings_data_reset_service.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py` | 设置事实本身不是 read model，但规则保存、项目范围和 data reset 会影响 dirty scope、read model、cache、worker readiness。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx` | 覆盖设置页、关联台内设置 modal、只读/admin、数据重置 job progress/reentry、凭据 section、App Status 全局提示。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_settings_data_reset_service.py`、`tests/test_derived_data_lifecycle_service.py`、下游模块 integration tests | 覆盖 data reset -> 清理/重建、pending invoice rules -> 下游 refreshing、OA credential -> token provider。真实多页面 smoke 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | `tests/test_postgres_migrations.py`、`tests/test_app_settings_service.py`、`tests/test_oa_applicant_credentials_api.py`、`web/src/test/WorkbenchSelection.test.tsx` | 保护旧 settings payload、迁移顺序、旧关联台设置入口、只读/权限、历史非法映射可见并可修复。 |

## 历史 bug 回归库

- 2026-06-16：settings project sync/create/delete 与 OA manual import mutation routes 曾只依赖页面 UI 隐藏或 settings update 局部权限，缺少统一 `can_mutate_data` 后端校验。回归测试：`tests/test_workbench_settings_sync_api.py::WorkbenchSettingsSyncApiTests::test_project_mutation_endpoints_reject_readonly_session_even_with_spoofed_actor`、`tests/test_oa_manual_import_api.py::OAManualImportApiTests::test_manual_import_mutation_endpoints_reject_readonly_session_even_with_spoofed_actor`。

## 关键 smoke flows

- admin 保存 pending invoice 规则 -> `pending_invoice_rules_changed` -> 待找发票、发票 lifecycle、税金、成本、关联台刷新或进入 refreshing。
- admin 在银行明细自动标签规则抽屉保存银行标签/自动标签 -> bank detail / no-OA / workbench 候选相关 read model dirty；settings 保存如果携带 `bank_transaction_tags` 必须失败，service 层也不得暴露该写参数，旧页面不把 stale 数据当 fresh。
- admin 执行银行/发票/OA 数据重置 -> password gate -> job progress -> protected targets 保留 -> read model/dirty scope/cache 清理 -> App Status 可见。
- admin 保存/删除 OA 申请人凭据 -> settings payload 不泄密 -> 目标 OA token provider 使用独立凭据 -> 外部 OA 失败不泄露密码。
- 项目同步/手工新增/完成/本地删除 -> settings reload 后项目状态保留 -> 成本统计/search/project scope 不误伤。
- 访问控制保存 -> admin 自动进入 allowed -> readonly/admin UI 和 API 权限一致。

## 模块验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_app_settings_service \
  tests.test_workbench_settings_sync_api \
  tests.test_oa_manual_import_api \
  tests.test_settings_data_reset_service \
  tests.test_oa_applicant_credentials_service \
  tests.test_oa_applicant_credentials_api \
  tests.test_postgres_oa_applicant_credentials_repository \
  tests.test_target_oa_applicant_token_provider \
  tests.test_postgres_migrations \
  tests.test_app_status_overview_service \
  tests.test_derived_data_lifecycle_service \
  -v

cd web && npm test -- --run \
  src/test/SettingsPage.test.tsx \
  src/test/WorkbenchSelection.test.tsx \
  src/test/AppStatusIndicator.test.tsx

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

Nightly full suite 应覆盖本模块的后端 settings/data-reset/credential tests、前端 SettingsPage/WorkbenchSelection/AppStatus tests、docs verify。模块级快速验证使用上方命令。

## 未测风险

- 真实生产数据重置仍需备份、worker pause/drain、Redis/cache 清理和 reset 后全页面 smoke；本地测试只能证明 service contract。
- 真实 OA 登录、RSA、token、草稿页面和目标申请人权限需要 staging/生产前 smoke；本地以 mock provider 保护密码和错误语义。
- 真实 PostgreSQL pgcrypto key、历史 settings payload、半迁移数据和大规模 state store 仍需生产 dry-run 或 staging 验证。
- 所有下游页面在 settings fan-out 后的最终 UI 刷新不能只靠本模块证明；由各下游模块测试和少量真实链路 smoke 共同保护。
