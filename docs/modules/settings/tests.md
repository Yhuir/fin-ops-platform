# 设置测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口、影响面和应保护的旧功能。实现后按实际影响更新矩阵。

## 2026-07-11 - OA 数据重置 canonical 发票全集保护

- OA reset 只重建 OA 及其附件派生事实，不得删除同一 canonical invoice store 中的普通进/销项发票。
- `tests/test_settings_data_reset_service.py` 以稳定 invoice id 断言 OA attachment 被缓存重建，同时普通 output invoice `iv-o-202604-001` 仍存在；测试不依赖列表顺序，也不通过 OCR 重跑掩盖事实源边界。
- 此合同覆盖 service-layer、read model/background job、跨模块 reset integration 与 existing regression；页面交互和 HTTP shape 未变化，沿用既有 settings component/Browser 覆盖。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/SettingsPage.tsx` | section 切换、loading/error、admin-only、保存按钮、数据重置确认、active reset job reentry |
| Workbench settings modal | `web/src/components/workbench/WorkbenchSettingsModal.tsx` | 关联台内设置入口、项目同步、账户映射、数据重置入口与设置页共享 API |
| Frontend API mapper | `web/src/features/workbench/api.ts` | snake_case/camelCase、`pending_invoice_tag_groups`、不得回传 `bank_transaction_tags`、data reset job、OA credential payload 不泄密 |
| HTTP routes | `routes_settings.py` `/api/workbench/settings*` | settings GET/POST、项目 sync/create/delete、OA 手动导入 mutation、data reset、credential routes 的权限和 response shape；`server.py` 只组装 route owner 和 runtime side-effect ports |
| Settings service | `AppSettingsService` | 项目、权限、银行映射、OA 配置、拒绝银行标签写入、待找发票规则版本、audit、OA role sync |
| Data reset service | `SettingsDataResetService` | protected targets、导入/文件/关联台/read model/dirty scope 清理、OA rebuild、progress、错误不泄密 |
| Credential service | `OaApplicantCredentialService`、repository、target token provider | admin-only、pgcrypto 加密、列表不解密、密码不进 settings payload、不泄露真实 OA password |
| Read model / worker | `DerivedDataLifecycleService`、runtime worker/readiness registries | settings 变更必须产生正确 dirty/read model fan-out；reset 后旧缓存/read model 不能伪装 fresh |
| App Status / App Health | app status registries、overview service | reset/job/dirty scope/worker busy 必须可见；设置页不能只看局部组件状态 |

## 场景覆盖清单

| 场景 | 保护测试 | 说明 |
| --- | --- | --- |
| 保存项目、权限、银行映射和 OA 配置 | `tests/test_app_settings_service.py`、`tests/test_workbench_settings_sync_api.py`、`web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` | 覆盖 normalize、state store round-trip、OA role sync、项目 sync/create/delete API 权限、只读/管理员 UI、OA 附件发票 promotion 模式保存。 |
| OA 手动导入 mutation 权限 | `tests/test_oa_manual_import_api.py` | 覆盖 refresh attachments、manual import create、manual import delete 在只读 session 下返回 403，且不会调用下游写服务或接受 body actor 伪造。 |
| 保存待找发票规则且拒绝银行标签回写 | `tests/test_app_settings_service.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/SettingsPage.test.tsx`、`tests/test_derived_data_lifecycle_service.py` | 覆盖 `/api/workbench/settings` 不接受 `bank_transaction_tags`、`AppSettingsService.update_settings(...)` 不暴露银行标签写参数、前端不回传银行标签展示字典、非法映射、audit、规则 version、下游 `pending_invoice_rules_changed` lifecycle fan-out；银行自动标签保存归属 `bank-details` 模块。 |
| 数据重置 / 项目范围 | `tests/test_settings_data_reset_service.py`、`web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/e2e/settings-data-reset-flow.spec.ts`、`docs/modules/settings/e2e-spec.md`、`docs/modules/settings/e2e-coverage.md` | 覆盖 admin/password gate、job progress、protected targets、reset OA rebuild、失败不清数据不泄密；Browser e2e 覆盖真实 Chromium 下影响确认、OA 密码复核、job polling、settings reload、严格浏览器错误捕获，也覆盖项目标记完成 -> 保存 settings -> 成本统计 active fresh project scope 排除已完成项目且项目范围切换 UI 不出现，并在成功后检查没有操作失败/同步失败/read model 失败等可见错误残留。`project_scope=all` 保留为成本统计 API/read model 合同。 |
| OA 申请人凭据 | `tests/test_oa_applicant_credentials_*`、`tests/test_target_oa_applicant_token_provider.py`、`web/src/test/SettingsPage.test.tsx` | 覆盖 admin-only、无密码回显、加密、目标 OA 登录 provider |
| 旧功能回归 | `tests/test_postgres_migrations.py`、`tests/test_app_status_overview_service.py`、相关下游模块测试 | 保护 settings payload 兼容、迁移、App Status 和下游页面不被配置变更误伤 |
| 流水规则 formal/raw 审计镜像 | `tests/test_postgres_migrations.py`、`tests/test_audit_settings_page.py`、生产 `GET /api/operations/app-health/page-audit?page=settings` | `0118` 只把 canonical `bank_flow_rule_batch_tag_rules` 同步到 `raw_payload.normalized_payload`，不修改 formal value；迁移后 settings Audit 必须 `pass`、0 blocking issue。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_app_settings_service.py`、`tests/test_oa_applicant_credentials_service.py` | 覆盖 settings normalize、访问控制、项目状态、银行标签写入边界、待找发票规则版本、OA 附件发票 promotion 模式默认值/非法值、非法映射、版本冲突、凭据必填/admin-only。 |
| 2. Service-layer tests | 适用 | `tests/test_app_settings_service.py`、`tests/test_settings_data_reset_service.py`、`tests/test_oa_applicant_credentials_service.py`、`tests/test_postgres_oa_applicant_credentials_repository.py`、`tests/test_target_oa_applicant_token_provider.py` | 覆盖 state store、audit、OA role sync、settings 拒绝银行标签回写、data reset、protected targets、PG 加密、目标 OA login provider。 |
| 3. API contract tests | 适用 | `tests/test_app_settings_service.py`、`tests/test_workbench_settings_sync_api.py`、`tests/test_oa_manual_import_api.py`、`tests/test_settings_data_reset_service.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 `SettingsApiRoutes`、`/api/workbench/settings`、`bank_transaction_tags_write_forbidden`、settings project mutation、OA manual import mutation、data reset job、credential routes、权限、错误、job、protected_targets、无密码回显。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_app_settings_service.py`、`tests/test_settings_data_reset_service.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py`、`web/e2e/settings-data-reset-flow.spec.ts` | 设置事实本身不是 read model，但规则保存、项目范围和 data reset 会影响 dirty scope、read model、cache、worker readiness；`/api/workbench/settings` 保存 pending invoice rules 必须触发 `pending_invoice_rules_changed` queue fan-out；Browser e2e 以 mock fresh boundary 覆盖项目状态保存后成本统计 active read model 重新读取，并检查成功后无 read model 失败提示残留。`project_scope=all` 由成本统计 API/read model 合同覆盖。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/e2e/settings-data-reset-flow.spec.ts` | 覆盖设置页、关联台内设置 modal、只读/admin、数据重置 job progress/reentry、凭据 section、App Status 全局提示，并用真实浏览器保护确认/密码/job polling/reload、项目状态保存后成本统计 active/all project scope 可见性，以及成功后无可见错误残留。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_settings_data_reset_service.py`、`tests/test_derived_data_lifecycle_service.py`、`web/e2e/settings-data-reset-flow.spec.ts`、下游模块 integration tests | 覆盖 data reset -> 清理/重建、pending invoice rules -> 下游 refreshing、OA credential -> token provider；Browser e2e 覆盖设置页发起 reset 到 settings reload 的用户路径，也覆盖项目标记完成 -> 保存 settings -> 成本统计 active 排除/all 保留，且成功后没有操作失败/同步失败/read model 失败等可见错误残留。真实多页面 worker drain smoke 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | `tests/test_postgres_migrations.py`、`tests/test_audit_settings_page.py`、`tests/test_app_settings_service.py`、`tests/test_oa_applicant_credentials_api.py`、`web/src/test/WorkbenchSelection.test.tsx`、`web/e2e/settings-data-reset-flow.spec.ts` | 保护旧 settings payload、迁移顺序、formal/raw 审计一致性、旧关联台设置入口、只读/权限、历史非法映射可见并可修复，以及 data reset 双弹窗/job polling 和“成功但报错提示仍显示”不退化。 |

## 历史 bug 回归库

- 2026-06-16：settings project sync/create/delete 与 OA manual import mutation routes 曾只依赖页面 UI 隐藏或 settings update 局部权限，缺少统一 `can_mutate_data` 后端校验。回归测试：`tests/test_workbench_settings_sync_api.py::WorkbenchSettingsSyncApiTests::test_project_mutation_endpoints_reject_readonly_session_even_with_spoofed_actor`、`tests/test_oa_manual_import_api.py::OAManualImportApiTests::test_manual_import_mutation_endpoints_reject_readonly_session_even_with_spoofed_actor`。
- 2026-06-19：设置页已补 Spec-first E2E 合同和覆盖映射，data reset Browser 流已纳入严格浏览器错误捕获；真实 PostgreSQL/RabbitMQ/Redis/systemd/OA/对象存储仍归 staging/runtime smoke。回归测试：`web/e2e/settings-data-reset-flow.spec.ts`。
- 2026-06-17：设置页 data reset 只有组件层测试，缺少真实浏览器覆盖影响确认、OA 密码复核、job polling、完成后 settings reload 和全局反馈的闭环。回归测试：`web/e2e/settings-data-reset-flow.spec.ts`。
- 2026-06-21：OA 附件发票 promotion 模式纳入设置页。默认 `link_existing_only` 不创建缺失发票，`disabled` 完全跳过 promotion，只有 `create_missing` 才允许正式发票缺失时创建统一发票池记录。回归测试：`tests/test_app_settings_service.py`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_attachment_invoice_cache_update_does_not_create_missing_invoice_by_default`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_attachment_invoice_cache_update_disabled_mode_skips_promotion`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_attachment_invoice_cache_update_create_missing_mode_promotes_formal_invoice`、`web/src/test/SettingsPage.test.tsx`。

## 关键 smoke flows

- admin 保存 pending invoice 规则 -> `pending_invoice_rules_changed` -> 待找发票、发票 lifecycle、税金、成本、关联台刷新或进入 refreshing。
- settings HTTP route owner smoke -> `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_settings_routes_use_route_owner` 必须证明 `server.py` 不再拥有 `_handle_api_workbench_settings*`、OA 手工导入 parser 或 data reset route I/O。
- admin 在银行明细自动标签规则抽屉保存银行标签/自动标签 -> bank detail / no-OA / workbench 候选相关 read model dirty；settings 保存如果携带 `bank_transaction_tags` 必须失败，service 层也不得暴露该写参数，旧页面不把 stale 数据当 fresh。
- admin 执行银行/发票/OA 数据重置 -> password gate -> job progress -> protected targets 保留 -> read model/dirty scope/cache 清理 -> App Status 可见。
- Browser e2e: `/settings` -> 数据重置 -> 影响确认 -> OA 密码复核 -> `settings_data_reset` job polling -> settings reload -> 全局成功反馈且无可见错误残留；`/settings` 项目标记完成 -> 保存 settings -> `/cost-statistics` active scope 排除已完成项目，且项目范围切换 UI 不出现，成功后无可见错误残留。
- admin 保存/删除 OA 申请人凭据 -> settings payload 不泄密 -> 目标 OA token provider 使用独立凭据 -> 外部 OA 失败不泄露密码。
- 项目同步/手工新增/完成/本地删除 -> settings reload 后项目状态保留 -> 成本统计/search/project scope 不误伤；Browser e2e 已覆盖项目完成状态到成本统计 active scope，`project_scope=all` 由成本统计 API/read model 合同覆盖。
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
  tests.test_platform_runtime_boundary_guards \
  -v

cd web && npm test -- --run \
  src/test/SettingsPage.test.tsx \
  src/test/WorkbenchSelection.test.tsx \
  src/test/AppStatusIndicator.test.tsx

cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

Nightly full suite 应覆盖本模块的后端 settings/data-reset/credential tests、前端 SettingsPage/WorkbenchSelection/AppStatus tests、deterministic Playwright `settings-data-reset-flow` smoke、docs verify。`settings-data-reset-flow` 同时保护成功后无可见错误残留。模块级快速验证使用上方命令。

## 未测风险

- 真实生产数据重置仍需备份、worker pause/drain、Redis/cache 清理和 reset 后全页面 smoke；本地测试和 deterministic Playwright 只能证明 service contract 与设置页浏览器闭环。
- 真实 OA 登录、RSA、token、草稿页面和目标申请人权限需要 staging/生产前 smoke；本地以 mock provider 保护密码和错误语义。
- 真实 PostgreSQL pgcrypto key、历史 settings payload、半迁移数据和大规模 state store 仍需生产 dry-run 或 staging 验证。
- 所有下游页面在 settings fan-out 后的最终 UI 刷新不能只靠本模块证明；由各下游模块测试和少量真实链路 smoke 共同保护。

## 2026-07-22 Phase 27 设置写后零 fan-out 回归

- `tests/test_oa_manual_import_api.py`：OA 手工导入与设置保存保留 owner 校验、权限、审计、事实/version 写入，普通结果 targets 为空且不发布跨页面 refresh。
- `web/src/test/SettingsOaManualSearchImportTable.test.tsx`：可写 Drawer 保存后立即结束并刷新当前设置视图，不轮询 operation barrier。
- 下游正确性改为逐页面访问验证；旧“settings 保存后必须 fan-out 所有页面”的测试与说明不再有效。数据 reset 仍是显式运维批处理，不属于普通保存。
