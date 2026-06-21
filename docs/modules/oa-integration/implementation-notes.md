# OA 集成 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- OA 集成首轮测试闭环状态为 `documented-risk`：本地测试已覆盖主要 contract、失败分支和跨模块 dirty scope，但真实 OA 登录、OA 草稿页面、OA Mongo 字段变体、同域 iframe/cookie 和生产 worker drain 必须由 staging/生产前 smoke 补证。
- OA Mongo 仍按外部只读源处理；本系统只能建立映射、缓存和投影，不写 OA 原始库。
- 目标 OA 申请人凭据只允许 admin 维护，response/log/audit 不得回显 password；创建 OA 草稿前必须先通过目标申请人登录拿 token。
- 进项 OA 反提和 ETC OA 草稿的本地撤销/删除只处理本系统状态，不删除或撤销真实 OA 草稿/流程。
- OA source alias / migration identity 修复必须先只读审计再显式建模；不得通过删除 `app.oa_applications`、`app.oa_attachments`、`app.oa_attachment_invoice_cache` 或伪造 read model readiness 来消除重复。
- OA 附件 OCR/parser 输出不是正式发票事实源；进入统一发票池前必须经过 `InvoiceAttachmentRecognitionService`，结果只允许为关联已存在发票、受控创建并关联、忽略；同一强 identity 命中多张 canonical 发票时必须按多义匹配忽略，不得任选一张建立关系。

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

## 2026-06-21 - OA 附件发票 Promotion 设置化

- 目标：避免用户清空统一发票池并手工重新导入 Excel 时，OA 附件 OCR 结果通过 OA 同步或关联台读路径重新写入 `app.invoices`。
- 影响范围：`AppSettingsService`、OA attachment invoice cache promotion、Workbench OA payload 构建触发路径、设置页 OA 导入设置。
- 关键决策：新增 `OA附件发票晋级` 三态设置。`disabled` 完全跳过 promotion；默认 `link_existing_only` 只关联已有统一发票池记录，不创建缺失发票；`create_missing` 才保留受控创建能力。该开关不删除 OA 附件，也不改变 OCR cache，只控制 OCR 结果是否进入统一发票池/关系补充。
- 文档影响：更新 `oa-integration`、`settings`、`reconciliation-workbench` 模块文档。
- 测试覆盖：新增/更新 `tests/test_app_settings_service.py`、`tests/test_workbench_v2_api.py`、`web/src/test/SettingsPage.test.tsx`，覆盖设置 round-trip、默认不创建、禁用不调用 promotion、显式创建和设置页保存。
- 验证命令：见本轮交付说明。
- 未测风险：真实生产 OA 附件历史 OCR cache 未在本地重放；发票池清空和手工重导入仍应在开关设为 `disabled` 或默认 `link_existing_only` 后用生产备份保护。

## 2026-06-21 - OA 附件未知证据禁止提升为正式发票

- 目标：避免 OCR 或外部附件缓存只带发票号、金额等字段但缺少正式发票证据类型时，被提升为统一发票池记录。
- 影响范围：`InvoiceAttachmentRecognitionService`、`ImportNormalizationService.upsert_oa_attachment_invoice`、OA attachment invoice cache promotion。
- 关键决策：正式发票候选必须具备 `tax_invoice` / `machine_invoice` evidence type，或在缺少 evidence type 时具备明确正式发票 document kind（如 `digital_invoice`、`yunnan_machine_invoice`、`railway_e_ticket_invoice`、含“发票/电子客票”的正式文档类型）。未知 evidence、缺 evidence 且仅有发票号、付款凭证、非税票据、交通罚没票据均忽略；解析候选层、识别层和底层 `allow_create=True` 都不能绕过该 gate。
- 文档影响：更新 `tests.md` 历史回归库。
- 测试覆盖：新增 `tests/test_oa_attachment_invoice_service.py::OAAttachmentInvoiceServiceTests::test_parse_files_does_not_return_unknown_evidence_with_invoice_number`、`tests/test_object_identity_policy.py::FinancialObjectIdentityPolicyTests::test_oa_attachment_invoice_evidence_classification_is_centralized`、`tests/test_invoice_attachment_recognition_service.py` 中未知/缺 evidence 的完整 identity 忽略测试，以及 `tests/test_import_service.py::ImportNormalizationServiceTests::test_oa_attachment_allow_create_requires_formal_invoice_evidence`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_invoice_attachment_recognition_service.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_import_service.py::ImportNormalizationServiceTests::test_oa_attachment_allow_create_requires_formal_invoice_evidence tests/test_import_service.py::ImportNormalizationServiceTests::test_oa_attachment_allow_create_accepts_formal_document_kind_without_evidence_type tests/test_import_service.py::ImportNormalizationServiceTests::test_oa_attachment_invoice_upsert_creates_canonical_invoice_with_source_context tests/test_import_service.py::ImportNormalizationServiceTests::test_oa_attachment_allow_create_requires_strong_invoice_identity -q`。
- 未测风险：真实 OCR 模型可能漏填 evidence type；这类结果按当前规则宁可忽略，不自动建票，需要通过 OCR/parser 改进补齐正式 evidence 后再进入发票池判断。

## 2026-06-21 - OA 附件强 identity 多义匹配忽略闭环

- 目标：落实“强 identity 命中多张发票直接忽略”的规则，避免 OCR 在历史污染或重复数电号码下任选一张发票建立错误 OA 关系。
- 影响范围：`InvoiceAttachmentRecognitionService`、`ImportNormalizationService` identity repository adapter、`PostgresCoreRepository` 发票 identity 查询。
- 关键决策：保留旧 `find_invoice_by_identity(...) -> Invoice | None` 供普通导入 dedup 使用，新增 `find_invoices_by_identity(...) -> list[Invoice]` 只给附件识别服务判断多义命中；多条命中返回 `ignore/ambiguous_invoice_identity`。
- 文档影响：本实施记录补充 OA 附件识别不变量；README 已记录“非正式票据、残缺号码、多义匹配或未知证据直接忽略”。
- 测试覆盖：新增 `tests/test_invoice_attachment_recognition_service.py::InvoiceAttachmentRecognitionServiceTests::test_formal_attachment_with_ambiguous_existing_identity_is_ignored`，以及 `tests/test_postgres_repositories_core.py::test_find_invoices_by_identity_returns_all_digital_invoice_matches`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_import_service.py tests/test_invoice_attachment_recognition_service.py tests/test_postgres_repositories_core.py tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_etc_paths_do_not_call_legacy_canonical_sync_helpers tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_app_invoice_writes_stay_in_core_repository -q`。
- 未测风险：真实生产 OCR 准确率和历史污染数据仍需通过备份、只读审计、cleanup preflight 和重导入流程闭环。

## 2026-06-21 - OA 附件发票识别 service 边界

- 目标：防止 OA 附件 OCR 的残缺号码、非税票据、付款凭证或交通罚没票据被旧逻辑误写入统一发票池。
- 影响范围：OA attachment invoice cache refresh、`ImportNormalizationService.upsert_oa_attachment_invoice`、`object_identity_policy`、tax offset 和 Workbench attachment invoice 链路。
- 关键决策：新增轻量 `InvoiceAttachmentRecognitionService`，只输出 `link_existing_invoice`、`create_invoice_and_link`、`ignore`。只有强发票身份（数电号码或发票代码+号码）且字段足够完整的正式发票才允许创建；非正式票据、残缺号码、多义匹配、未知 evidence type 和付款类凭证直接忽略。
- 文档影响：更新 OA 集成 README、ETC 导入/票据模块和产品口径。
- 测试覆盖：新增 `tests/test_invoice_attachment_recognition_service.py`；更新 import service、tax offset、object identity policy 和 Workbench V2 相关测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_import_service.py tests/test_invoice_attachment_recognition_service.py tests/test_object_identity_policy.py tests/test_tax_offset_service.py tests/test_tax_offset_api.py -q`。
- 未测风险：真实 OCR 准确率、真实附件混合包和生产历史污染数据仍需只读审计、备份、受控清理和重导入验证。

## 2026-06-20 - OA source alias / migration identity 只读审计与修复设计

- 目标：解释生产 `workbench-audit-identity` 暴露的 6 个 `oa_attachment_invoice` cross-OA duplicate，判断是否应按 OA source alias / migration identity 修复，而不是直接清理数据。
- 影响范围：`MongoOAAdapter._expense_external_id(...)`、OA projection `app.oa_applications` / `app.oa_attachments`、`app.oa_attachment_invoice_cache_sources`、`audit_object_identity` 的 OA attachment invoice duplicate 分类，以及后续 Workbench / Search / 待找发票 read model 语义。
- 生产只读证据：
  - PostgreSQL `BEGIN READ ONLY` 查询显示 3 对 OA source 在 `form_id/form_type/applicant/application_date/project_name/amount/currency/scope_month` 上完全成对一致：`oa-exp-2005` vs `oa-exp-69898450db8c0a3633bd748c`、`oa-exp-2035` vs `oa-exp-69a7aeaedb8c0a3633bd74a7`、`oa-exp-2062` vs `oa-exp-69c0b43adb8c0a3633bd74c4`。
  - 每对短号记录的 `workflow_status=completed`；每对长 Mongo ObjectId 记录的 `workflow_status=in_progress`。因此它们不是可以盲目合并的同一行 ID，而是同一业务内容在 OA 源内存在「进行中草稿/过程文档」与「已完成流程文档」两种 source。
  - OA Mongo 只读 projection 查询匹配 6 个源文档：长 ObjectId 文档没有 `flowRequestId/processId`，`processStatus=1`；已完成文档使用不同 Mongo `_id`，但 `flowRequestId` 分别为 `2005/2035/2062`，`processStatus=2`、`status=APPROVED`。三对文档的申请人、申请日期、明细数量、项目、金额、费用内容和附件数量一致。
  - 本地代码确认 `MongoOAAdapter._expense_external_id(...)` 优先使用 `flowRequestId/processId`，缺失时退回 Mongo `_id`；`_build_external_id_query(...)` 同时按 `flowRequestId/processId/_id` 查找。这解释了为什么完成单以短号 `oa-exp-20xx` 投影，进行中文档以长 ObjectId 投影。
- 关键判断：
  - 这 6 个 blocker 更像 OA lifecycle / migration alias：同一报销业务内容先以无 `flowRequestId` 的进行中文档出现，完成后又以带 `flowRequestId` 的批准文档出现。
  - 不能直接删长号记录或 cache source；长号仍是外部 OA 原始源的一部分，且可能被历史 manual import、relation、cache source 或审计引用。
  - 不能仅靠业务指纹自动降级 duplicate；申请人、金额、项目、日期相同仍可能是真实重复报销。自动规则只能产出候选，真正参与 canonicalization 的 alias 必须有显式、可审计的来源。
- 修复设计：
  1. 新增只读 alias audit：扫描 `oa_attachment_invoice` cross-OA duplicate，按 `form_id + applicant + applicationDate + schedule item fingerprint + attachment filename/count + invoice identity` 生成 `probable_oa_lifecycle_alias` 报告；报告必须区分 `completed_with_flow_request_id` 与 `in_progress_without_flow_request_id`，并给出 canonical 候选 `oa-exp-{flowRequestId}`。
  2. 新增 OA source identity policy：封装「外部 source id」「业务内容指纹」「完成态 canonical id」的判断，供 audit、projection repair 和测试复用，避免把 heuristic 分散到 Workbench 或 read model。
  3. 若后续需要生产修复，优先新增显式 alias/identity 表，例如 `app.oa_source_aliases(alias_row_id, canonical_row_id, reason, evidence_hash, status, reviewed_by, reviewed_at, raw_payload, created_at)`；默认只写 `detected/pending_review`，只有人工或受控 `--apply` 批准后才进入 `active`。
  4. `audit_object_identity` 和 downstream duplicate classifier 只在 alias `active` 后使用 canonical OA id 合并上下文；未批准 alias 继续保持 `cross_oa` blocker，防止误把真实重复报销隐藏。
  5. 生产修复不删除 OA 原始投影、附件、cache 或发票解析结果；最多新增 alias 事实、刷新受影响 read model，并保留 rollback/audit payload。
- 文档影响：本记录补充 `oa-integration` 的长期实施决策；`read-models` 已记录 cross-OA duplicate 只读审计入口和禁止手工清理原则。
- 测试覆盖：本阶段只做只读审计和设计，未新增测试。后续实现必须覆盖 `tests/test_mongo_oa_adapter.py`、`tests/test_audit_object_identity_tool.py`、`tests/test_object_identity_policy.py` 或新增 alias policy/repository tests，验证 alias 仅在严格证据和 active 状态下降级，未批准候选仍 blocking。
- 验证命令：生产 PostgreSQL 只读 schema/target rows/cache source 查询；生产 OA Mongo 只读 projection 查询；本地代码读取 `MongoOAAdapter._expense_external_id(...)`、`_build_external_id_query(...)`、`audit_object_identity` duplicate 分类逻辑。
- 未测风险：尚未实现 alias audit 工具、alias 表、受控 apply、read model 刷新或 rollback；尚未证明除这 3 对外没有其它同类 alias。真实误判风险必须由只读 audit 全量报告和人工 review gate 控制。
- 后续事项：下一阶段先实现只读 alias audit 和本地测试；只有报告稳定并人工确认后，再讨论 alias 表 migration 与受控 apply，不直接删数据。

## 2026-06-11 - OA 集成测试闭环首轮

- 目标：完成 `oa-integration` 的影响面、七类测试矩阵、状态机、依赖地图和模块验证，补齐高价值测试缺口。
- 影响范围：OA session、Mongo adapter、OA projection sync worker、OA pending payments、OA manual import、OA applicant credentials、目标 OA 申请人登录、进项 OA 反提、ETC OA 草稿、OA role sync、部署同域路径。
- 关键决策：不把真实 OA/Mongo/staging 风险伪装为本地已闭环；本地只保护 contract、状态机和失败处理，真实外部系统行为进入 `documented-risk`。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`docs/dev/testing-closure-dependency-map.md`、`docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `tests/test_target_oa_applicant_token_provider.py` 中 HTTP error、网络不可达、无效 JSON、缺 token 回归，确保目标 OA 登录失败不会伪装成功且不泄露 password。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_target_oa_applicant_token_provider -v`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_mongo_oa_adapter tests.test_worker_oa_sync tests.test_oa_identity_service tests.test_oa_applicant_credentials_service tests.test_oa_applicant_credentials_api tests.test_postgres_oa_applicant_credentials_repository tests.test_target_oa_applicant_token_provider tests.test_input_invoice_usage_oa_reverse_service tests.test_input_invoice_usage_api tests.test_oa_pending_payment_service tests.test_oa_pending_payment_api tests.test_oa_projection_sql_runtime tests.test_oa_manual_import_service tests.test_oa_manual_import_api tests.test_oa_role_sync_service tests.test_deploy_oa_script tests.test_deploy_oa_nginx_config -v`
  - `cd web && npm test -- --run src/test/SessionApi.test.ts src/test/SessionGate.test.tsx src/test/OaPendingPaymentsPage.test.tsx src/test/InputInvoiceUsagePage.test.tsx src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx src/test/SettingsPage.test.tsx src/test/SettingsOaManualSearchImportTable.test.tsx src/test/EtcApi.test.ts src/test/EtcTicketManagementPage.test.tsx src/test/EtcOaNavigation.test.ts`
  - `bash scripts/verify.sh docs`
- 未测风险：真实 OA 登录/RSA/openssl、目标申请人账号状态、OA 草稿页面、真实 OA Mongo 历史字段/附件/性能、同域 cookie/iframe/Nginx 下载、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain。
- 后续事项：发布前按 `tests.md` 的关键 smoke flows 做 staging/生产前验证；继续主控闭环到 `data-safety-reset`。
