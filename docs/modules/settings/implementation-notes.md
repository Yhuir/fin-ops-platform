# 设置 实施记录

## 2026-08-31 - 删除成本统计 time/tag 设置 family

- 成本统计已收敛为项目、费用类型、银行账户三个成本视图，不再提供原始银行按时间/标签视图。
- 删除 `cost_statistics_time_tag_selection` 的 service 方法、normalization、公开 payload、state-store/PostgreSQL persistence、audit 语义和 HTTP route；历史持久化字段不作为 runtime fallback。
- `cost_statistics_no_oa_projects` 保持不变，仍是成本统计唯一设置 family。下文 2026-08-18 的“两套规则”只作历史记录，不是当前合同。
- 本次无 schema/data migration、无数据库备份，不影响银行明细模块自己的标签与自动标签规则。

## 2026-08-18 - 成本统计两套规则拆分

- 新增独立 `cost_statistics_time_tag_selection`：默认 `mode=all`，按标签/按时间直接筛选 canonical 银行流水，未来新增标签自动纳入。
- `cost_statistics_no_oa_projects` 改为多个稳定 ID 虚拟项目，服务端强制名称唯一和标签互斥；候选与最终归集仍由成本统计逐笔判断 active OA 关系。
- 旧 `cost_statistics_tag_selection` 仅作为一次性无损读取迁移源；新保存只写两套新 schema，旧 endpoint、DTO、drawer 和运行时过滤链已删除。
- 项目完成状态不再过滤历史成本；两套规则使用独立 CAS/version/audit，不建表、不增加 read model、worker 或 cache。

## 2026-08-18 - 成本统计无 OA 设置收敛

- `cost_statistics_tag_selection` 升级为 schema v3，只保存虚拟项目名和标签 code，默认空；旧默认全选/收入标签自动加入语义一次性重置为空。
- 实际候选和逐笔无 OA 判断仍归成本统计 owner，Settings 只接收 route 提供的 allowed codes，执行名称校验、version CAS、持久化和 audit。
- 删除自动标签归档时静默 detach 成本选择的旧链；不可用选择保持可见，由用户显式取消。没有新增设置页 section、数据库字段、worker、read model 或跨页面 fan-out。

## 2026-08-01 - 数据重置执行边界迁入 durable worker

- Settings API 只负责 admin/OA 密码复核、创建 BackgroundJob 和投递 `settings.data_reset.requested`；密码不进入 job、outbox、日志或 result。
- 删除进程内 executor/inline reset 路径；独立 `settings-maintenance` worker 构造 reset 依赖并更新 job，重启遇到未知 destructive running job 时 fail closed。
- reset 完成后先登记正式 lifecycle/read-model refresh，再安全 reload Gunicorn runtime，防止 API 继续持有 reset 前进程内状态。

## 2026-07-21 - 流水规则 formal/raw 审计镜像修复

- 生产跨页验收发现设置页 Audit 仅在 `bank_flow_rule_batch_tag_rules` 报 `settings_formal_raw_payload_mismatch`；规则正式值与页面行为正确。
- 根因是历史 migration `0111` 规范 `settings_payload` 时只给 raw 根节点写了 migration marker，没有同步 `raw_payload.normalized_payload` 的同一 setting family。
- 新 migration `0118_bank_flow_rule_batch_settings_raw_alignment.sql` 只复制该 canonical setting family 到 raw 审计镜像，保留其它 raw metadata，不改 formal value、规则 version 或 OA/发票开关；正常运行时仍由 settings repository writer 原子双写 formal/raw。
- 本地迁移、settings Audit、repository 与 migration pin 回归共 120 passed + 19 subtests；生产 migration 用时 33ms，schema version 118，执行后 settings 与四个直接/上下游页面 Audit 全部 `pass`、0 blocking issue。
- 生产没有执行业务规则变更；随后 10 次同值 PUT 均为零写入、零 refresh，settings Audit 继续 `pass`。


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- settings 是高扇出配置域，不按单页 UI 维护。每次改动必须先判断是否影响项目范围、权限、业务规则、data reset、OA 凭据、read model、worker 或 App Status。
- 普通 app settings 仍以 `ApplicationStateStore` 为事实源；OA 申请人凭据使用独立 secret repository，不能进入普通 settings payload。
- 数据重置属于高风险运维操作：必须 admin-only、密码确认、protected targets、job progress、失败不泄密，并在重置后避免旧 read model/cache 被展示为 fresh。
- 规则和标签保存不应同步重建所有下游页面，但必须产生明确 dirty/lifecycle fan-out，并由 App Status/下游页面呈现 stale 或 refreshing。
- 本模块页面级 Spec-first 状态为 `spec-first-covered`：本地测试覆盖 service/API/UI contract、data reset Browser 用户路径和项目范围到成本统计 fresh fan-out；真实 OA、真实生产 reset、真实 worker drain 和多页面最终 smoke 仍需 staging/生产前验证。

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

## 2026-07-16 - OA reset 改为 pending durable rebuild

- 目标：让 Settings data reset 的完成语义与关联台 read model 的最终 fresh 状态严格分离，消除同步全页读取的性能和可靠性问题。
- 影响范围：Settings data reset runtime executor、API/background-job result、data-safety-reset 边界与测试。
- 关键决策：Settings 只负责权限、清理、job 与 `settings_reset_completed` lifecycle；OA reset 成功登记 durable refresh 后返回 `rebuild_status=pending`，不拥有 Workbench query/projection/OCR，也不重复入队 matching dirty scope。
- 文档影响：同步更新 Settings/data-safety-reset boundary、状态机、测试矩阵和实施记录。
- 测试覆盖：`tests/test_settings_data_reset_service.py` 覆盖 pending、enqueue failure、single enqueue、no synchronous full payload/OA row build、cache retention。
- 未测风险：最终 fresh 与真实性能只能在所有并行 thread 完成、统一部署后通过 worker drain 与生产性能 gate 验证；本轮明确不部署。

## 2026-07-05 - Settings route owner 与旧链路删除 close

- 目标：完成设置模块 HTTP I/O 边界收口，移除 `server.py` 中 `/api/workbench/settings*` 旧 handler 和 settings 持久化内存 fallback。
- 影响范围：`backend/src/fin_ops_platform/app/routes_settings.py`、`backend/src/fin_ops_platform/app/server.py`、`backend/src/fin_ops_platform/services/app_settings_service.py`、settings API/service tests、runtime boundary guard 和本模块边界文档。
- 关键决策：
  - `SettingsApiRoutes` 统一拥有 settings path matching、body/query parsing、权限 gate、错误码、response shape、OA 凭据、OA 手工导入和 data reset job HTTP I/O。
  - `server.py` 只保留 route owner 组装、runtime reset executor、read model/lifecycle side-effect ports，不再定义 `_handle_api_workbench_settings*` 旧 handler。
  - `AppSettingsService._refresh_snapshot_from_state_store()` 不再用当前内存 `_snapshot` 给持久化结果补字段；缺失字段只能通过 normalizer/default contract 得到。
  - `/api/workbench/settings` 保存 pending invoice rules 时，通过 settings event finalizer 触发 `pending_invoice_rules_changed` lifecycle fan-out；银行自动标签写入仍归属银行明细模块。
- 文档影响：更新 `boundary-io.md` 为 `closed`，同步 `README.md`、`tests.md` 和本文件。
- 测试覆盖：新增/更新 `tests/test_app_settings_service.py`，覆盖持久化 settings contract 不读内存 fallback、settings API pending rules lifecycle fan-out；更新 `tests/test_platform_runtime_boundary_guards.py` 锁定 `routes_settings.py` route owner 和 data reset job route 边界；更新 `tests/test_workbench_dirty_queue_wiring.py` 改走公开 HTTP route。
- 验证命令：见本轮最终说明。
- 未测风险：真实生产数据重置、真实 OA 登录、真实 worker drain 和多页面最终 smoke 仍需要 staging/production 验证；本轮覆盖本地 service/API/static boundary contract。
- 后续事项：新增 settings 子路由时必须进 `SettingsApiRoutes`，不得恢复 `server.py` route-inline handler；新增 settings 持久化字段必须通过 normalizer/default contract，不得恢复内存 snapshot fallback。

## 2026-06-19 - 成功写流可见错误残留 guard

- 目标：防止 data reset 或项目范围保存到成本统计 active/all fresh fan-out 已成功，但页面仍残留“操作失败/同步失败/read model 失败”等可见错误提示。
- 影响范围：`web/e2e/settings-data-reset-flow.spec.ts`、`tests/test_playwright_e2e_strict_diagnostics.py`、本模块测试矩阵和全局测试文档。
- 关键决策：不改变产品逻辑或 deterministic mock；在数据重置完成、settings 保存成功、成本统计 active scope 和 all scope 成功节点复用 `expectNoUnexpectedSuccessUiErrors(...)`。
- 文档影响：更新本模块 `tests.md`、`e2e-coverage.md` 和全局 testing closure state。
- 测试覆盖：`web/e2e/settings-data-reset-flow.spec.ts` 加强 data reset 和 project scope fan-out 成功路径；静态诊断防止后续移除该 guard。
- 验证命令：`cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts --project=chromium`；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`。
- 未测风险：真实生产 data reset、真实 OA 和全页面 worker drain 仍需 staging/production smoke；本轮只覆盖 deterministic Browser flow 的可见错误残留。

## 2026-06-19 - Settings 页面级 Spec-first E2E covered

- 目标：把 settings 从首轮 `documented-risk` 校准为页面级 `spec-first-covered`，明确页面 Browser 合同、覆盖映射和真实基础设施风险边界。
- 影响范围：`web/e2e/settings-data-reset-flow.spec.ts`、`docs/modules/settings/e2e-spec.md`、`docs/modules/settings/e2e-coverage.md`、settings 测试矩阵和全局 Spec-first E2E inventory。
- 关键决策：
  - 不改产品逻辑；现有 service/API/component/Browser 测试已经覆盖 settings 主要业务合同。
  - 给 data reset Browser 流补严格浏览器错误捕获，确保影响确认、OA 密码复核、job polling、settings reload 期间隐藏 `pageerror`、`console.error`、非 abort request failure 或未预期 dialog 会失败。
  - 真实 PostgreSQL/RabbitMQ/Redis/systemd/OA/对象存储、生产备份恢复和全页面 worker drain 不用本地 deterministic E2E 伪装覆盖，继续登记为 staging/runtime smoke external-risk。
- 文档影响：新增 `e2e-spec.md`、`e2e-coverage.md`，更新 `README.md`、`tests.md`、本文件和全局 testing closure 文档。
- 测试覆盖：更新 `web/e2e/settings-data-reset-flow.spec.ts`。
- 验证命令：`cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts --project=chromium`；`bash scripts/verify.sh docs`。
- 未测风险：真实生产 data reset 备份/worker drain/Redis cache、真实 OA 登录/草稿、真实 PostgreSQL pgcrypto key/历史 settings payload 和所有下游页面最终 smoke仍需 staging/production smoke。

## 2026-06-19 - Browser e2e 补项目范围到成本统计 fan-out

- 目标：把 settings 项目状态管理的 Browser E2E 从 data reset 扩展到下游成本统计，避免“设置保存成功但成本统计 active/all project scope 仍读旧状态”。
- 影响范围：`web/e2e/settings-data-reset-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、settings 和成本统计测试矩阵、全局 Spec-first E2E inventory。
- 关键决策：
  - 测试不改变产品逻辑，只新增 opt-in deterministic mock `settingsProjectScopeFanout` 表示 settings 保存后的 `completed_project_ids` 会影响成本统计 explorer 的 active/all project scope。
  - Browser 流在设置页把项目标记完成并保存，断言 POST `completed_project_ids=["settings-cost-project-e2e"]`，再进入成本统计验证 active scope 排除该项目，all scope 保留该项目和金额。
  - 新增严格浏览器错误捕获：`pageerror`、`console.error`、非 abort `requestfailed` 和未预期 dialog 均会失败。
- 文档影响：更新本文件、`tests.md`、成本统计模块测试/覆盖/实施记录和全局 testing closure 文档。
- 测试覆盖：更新 `web/e2e/settings-data-reset-flow.spec.ts` 和 `web/e2e/fixtures/apiMocks.ts`。
- 验证命令：`cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts --project=chromium`。
- 未测风险：本地仍是 mocked Browser E2E，不证明真实 PostgreSQL/RabbitMQ/Redis/systemd settings lifecycle 与 cost-statistics worker drain；真实环境需要 staging/production smoke。

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
- 影响范围：`SettingsPage`、当时仍存在的关联台旧设置弹窗、`web/src/features/workbench/api.ts`、`AppSettingsService`、`SettingsDataResetService`、OA applicant credential service/repository/token provider、derived lifecycle、App Status。
- 关键决策：不为本轮新增低价值代码测试；现有测试已经覆盖主要 service/API/UI contract。本轮补齐影响面、状态机、验证命令和 documented-risk，真实环境风险交给 staging/production smoke。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`implementation-notes.md` 和全局 `testing-closure-dependency-map.md`。
- 测试覆盖：后端覆盖 app settings、data reset、OA credentials、target OA token provider、migration、App Status、derived lifecycle；前端覆盖 SettingsPage、WorkbenchSelection、AppStatusIndicator。
- 验证命令：见 `tests.md` 和 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实生产 reset worker drain、Redis/cache 清理、真实 OA 登录/草稿、真实 PostgreSQL pgcrypto key 和所有下游页面最终 smoke。
- 后续事项：改 settings 时必须先补旧功能 regression/characterization test；若发现真实 reset/OA bug，登记到 `docs/dev/regression-bug-bank.md`。
