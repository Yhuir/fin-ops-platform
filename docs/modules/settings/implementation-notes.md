# 设置 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- settings 是高扇出配置域，不按单页 UI 维护。每次改动必须先判断是否影响项目范围、权限、业务规则、data reset、OA 凭据、read model、worker 或 App Status。
- 普通 app settings 仍以 `ApplicationStateStore` 为事实源；OA 申请人凭据使用独立 secret repository，不能进入普通 settings payload。
- 数据重置属于高风险运维操作：必须 admin-only、密码确认、protected targets、job progress、失败不泄密，并在重置后避免旧 read model/cache 被展示为 fresh。
- 规则和标签保存不应同步重建所有下游页面，但必须产生明确 dirty/lifecycle fan-out，并由 App Status/下游页面呈现 stale 或 refreshing。
- 本模块首轮闭环状态为 `documented-risk`：本地测试覆盖 service/API/UI contract，真实 OA、真实生产 reset 和多页面最终 smoke 仍需 staging/生产前验证。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-16 - settings mutation API 权限闭环

- 目标：修复 settings 页面只读用户可绕过 UI、直接调用部分 mutation API 的风险，确保后端 API 与页面权限一致。
- 影响范围：`/api/workbench/settings/projects/sync`、`/api/workbench/settings/projects`、`/api/workbench/settings/projects/{id}`、`/api/workbench/settings/oa/manual-search/refresh-attachments`、`/api/workbench/settings/oa/manual-imports`、`/api/workbench/settings/oa/manual-imports/{row_id}`。
- 关键决策：新增统一 settings mutation session gate；有 OA session 时 actor 以 session 身份为准，不接受 body `actor_id` 伪造。无 session 的本地/测试模式仍保留原有 body actor fallback。
- 文档影响：更新 `tests.md` 的 HTTP route、API contract 和 regression 覆盖；`state-machine.md` 增加权限闭环变更记录。
- 测试覆盖：新增 project mutation 和 OA manual import mutation API contract regression，覆盖只读 session、body actor 伪造、下游写服务不被调用、既有状态不被删除。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_settings_sync_api.WorkbenchSettingsSyncApiTests.test_project_mutation_endpoints_reject_readonly_session_even_with_spoofed_actor tests.test_oa_manual_import_api.OAManualImportApiTests.test_manual_import_mutation_endpoints_reject_readonly_session_even_with_spoofed_actor -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service tests.test_workbench_settings_sync_api tests.test_oa_manual_import_api tests.test_settings_data_reset_service tests.test_oa_applicant_credentials_service tests.test_oa_applicant_credentials_api tests.test_postgres_oa_applicant_credentials_repository tests.test_target_oa_applicant_token_provider tests.test_postgres_migrations tests.test_app_status_overview_service tests.test_derived_data_lifecycle_service -v`；`cd web && npm test -- --run src/test/SettingsPage.test.tsx src/test/WorkbenchSelection.test.tsx src/test/AppStatusIndicator.test.tsx`。
- 未测风险：真实 OA session/角色同步和生产 project/manual import 操作仍需 staging smoke；本地测试已覆盖后端权限 contract。
- 后续事项：新增 settings mutation route 时必须复用统一 session gate，并补只读 session API regression。

## 2026-06-11 - settings 测试闭环首轮

- 目标：把 settings 从“凭据管理局部文档”扩展为完整配置域闭环，覆盖设置保存、规则 fan-out、数据重置、OA 凭据、权限和下游 read model/worker 风险。
- 影响范围：`SettingsPage`、`WorkbenchSettingsModal`、`web/src/features/workbench/api.ts`、`AppSettingsService`、`SettingsDataResetService`、OA applicant credential service/repository/token provider、derived lifecycle、App Status。
- 关键决策：不为本轮新增低价值代码测试；现有测试已经覆盖主要 service/API/UI contract。本轮补齐影响面、状态机、验证命令和 documented-risk，真实环境风险交给 staging/production smoke。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`implementation-notes.md` 和全局 `testing-closure-dependency-map.md`。
- 测试覆盖：后端覆盖 app settings、data reset、OA credentials、target OA token provider、migration、App Status、derived lifecycle；前端覆盖 SettingsPage、WorkbenchSelection、AppStatusIndicator。
- 验证命令：见 `tests.md` 和 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实生产 reset worker drain、Redis/cache 清理、真实 OA 登录/草稿、真实 PostgreSQL pgcrypto key 和所有下游页面最终 smoke。
- 后续事项：改 settings 时必须先补旧功能 regression/characterization test；若发现真实 reset/OA bug，登记到 `docs/dev/regression-bug-bank.md`。
