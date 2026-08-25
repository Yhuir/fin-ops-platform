# OA 集成 实施记录

## 2026-08-24 - 历史附件身份的显式 OA alias 修复边界

- 根因：旧 OA row 已退出 canonical projection，但其附件发票来源仍按不可变 provenance 保留旧 parent/item ID；当前 canonical OA 保有相同物理附件。页面运行时缺少显式 alias 时必须 fail closed，不能把金额、项目或 row index 当成 OA 身份证明。
- 决策：删除未安装到现有 root helper、因而不可达的通用 alias repair 工具，改由 `0153_oa_source_alias_attachment_identity_repair.sql` 对唯一已审阅案例做一次性修复。迁移精确限定旧/新 OA、旧/新两组 item 与两张 canonical 发票：旧侧要求 canonical invoice 的不可变 OA provenance；新侧要求当前 item `attachment_invoices` 的数电号码或“代码+号码”强身份、当前附件键，并要求该附件键确实由当前 OA 持有且 attachment payload 回指同一当前 item。生产迁移已证明 `source_expense_row_index` 跨 OA 生命周期会变化，且该案例没有 current attachment 的 cache-source bridge，因此两者都不再承担身份门禁。两张发票必须按强号码唯一覆盖两条当前 item 与两份当前 owned attachment；禁止退化为金额、名称、row index、顺序或历史 cache bridge 猜测。
- 写入：只在 canonical OA 唯一存在、旧 OA 已退出 canonical projection、alias 无冲突时写一条 `app.oa_source_aliases.status='active'` 审计事实；无目标数据的新库 no-op，证据不一致 fail closed。迁移不改 OA、发票、source links、relation 或表结构，不创建数据库备份。
- 性能：一次性迁移不进入 Workbench 页面热查询；运行时继续走 indexed active alias。迁移发现、强证据条件和禁止更新/删除核心事实由 `tests/test_postgres_migrations.py` 覆盖；`tests/test_oa_source_alias_repair_postgres_integration.py` 在真实 PostgreSQL 中让旧/新 item 顺序交叉、附件键完全不同且 row index 全部不一致，只允许强发票身份与当前附件所有权闭环完成映射。

## 2026-08-18 - OA 流程单号投影

- 目标：让下游详情读取真实 OA 流程单号，禁止以内部 `form_id`/表单类型代替。
- 根因：Mongo adapter 已将 completed OA 的权威流程号归一到 `detail_fields.OA单号`，但 PostgreSQL projection 仍写入始终为空的 `record.case_id`。
- 关键决策：projection 精确读取 `detail_fields.OA单号` 写 `workflow_no`，占位符和缺失值保持空；不猜测、不从 row id 或 form type 兜底。
- 数据闭环：projection 版本提升为 `2026-08-18-workflow-number-v9`，复用现有 durable OA sync 幂等重投；不新增 schema、worker、read model 或直接数据库修补。
- 测试：覆盖真实号码写入、缺失号码不使用内部 identity，以及待找发票下游详情合同。

## 2026-08-18 - 支付申请费用类型表单字段隔离

- 目标：修复支付申请的权威 `category` 在 OA 归一化中被遗漏，造成成本统计中 115 个 OA 归集单元缺少费用类型的问题。
- 根因：旧共享候选键在修复日常报销 `purposeType` 时被收敛为单一字段，使支付申请和日常报销错误共用一套读取合同；支付申请生成端仍写入 `EtcOAFormFieldMapping.category`。
- 关键决策：支付申请精确读取可配置 category 字段，日常报销子项精确读取 `purposeType`；删除共享候选键和递归同名字段扫描，不在成本层、detail fields 或申请事由上增加兜底。
- 数据闭环：projection 版本提升为 `2026-08-18-form-specific-expense-type-v8`，由既有 durable OA sync 幂等重投历史数据；不直接更新主数据库投影行，不新增 schema、worker 或 read model。
- 验收：发布前只读审计 115 条源字段的标准值/空值/非法值；发布后恢复量必须等于修前标准值数量，空/非法残余继续保持缺失，不以无证据强制归零。
- 测试：`tests/test_mongo_oa_adapter.py` 覆盖支付申请 category、环境自定义字段、日常报销 purposeType 和表单字段互不污染；projection/sync 回归保护版本化幂等重投。

## 2026-08-11 - OA 删除与自动匹配并发闭环

- 目标：补齐权威快照正确删除 OA 后，已经在事务外读取的自动匹配 plan 仍可能重新创建失效 relation 的并发窗口。
- 根因：OA 删除事务与 formal relation 创建事务都各自正确，但旧 matching batch 的成员有效性没有在 relation UoW 内重新证明。
- 关键决策：OA 删除链不增加补偿；由 Workbench 共享 relation command 在写事务内先锁定并验证当前 canonical 成员，再取得 relation advisory lock。无论删除或匹配先取得 canonical 行锁，最终都只允许“成员存在的关系”提交。
- 测试覆盖：真实 PostgreSQL integration 复现 stale plan，OA 权威快照删除后 formal confirm 返回 `workbench_relation_canonical_member_missing` 且 relation 表无写入。
- 文档影响：更新 OA 与关联台的 boundary I/O；API、read model、worker、权限和前端合同不变。

## 2026-08-11 - OA 权威快照统一删除与关联关系清理

- 目标：修复 OA 周期同步删除已失效 completed 投影后，关联台 active relation 偶发保留不存在 OA 成员的问题。
- 根因：`upsert_application_records(...)` 的旧隐式 scope cleanup 先删除投影但丢弃 row id；随后权威快照的正式删除拿不到已删除 row id，无法调用 `remove_rows_from_active_relations(...)`。
- 关键决策：删除 upsert 内的隐式 cleanup；由既有 `commit_authoritative_snapshot(...) -> delete_stale_completed_application_records(...)` 唯一负责删除、返回 row id，并在同一事务通过正式 relation command 清理或替换 active relation。不新增 fallback、第二条修复链或页面补偿。
- 测试覆盖：unit fake 验证保留 OA 与删除 OA 同批时 row id 不丢；SQL runtime 验证 upsert 不再隐式清理；真实 PostgreSQL integration 验证投影删除与 relation 取消同一事务闭环。
- 文档影响：既有 `boundary-io.md` 已规定权威快照和正式 relation command 的边界，本次只纠正实现并登记回归，不改变 API、read model 或 worker 合同。

## 2026-08-07 - OA附件身份桥双顺序闭环与历史修复门禁

- 目标：修复 parser cache 先于 `app.oa_attachments` 落库时身份桥缺失，导致已有 canonical 发票只显示“人工导入”且无法恢复 OA 绑定的问题。
- 影响范围：OA cache repository、completed OA projection、附件 promotion、Workbench matching、生产 bridge/promotion repair 工具。
- 关键决策：抽出唯一 `oa_attachment_identity_bridge` repository 边界；cache 保存按 cache key、OA附件落库后按本轮真实变化 OA row ids 复用同一集合式 SQL。冲突更新仅在上下文真实变化时写入；不增加页面通知、read model、worker 或周期全表扫描。OA来源只追加，保留人工导入 provenance；弱身份和跨 OA/expense-item 冲突继续 fail closed。
- 旧链删除：删除 `ops_tax_etc.py` 内依赖写入时序的私有跨身份 SQL，避免 cache writer 与 projection writer 各维护一套规则。
- 性能：新增 cache source `(source_expense_item_id, source_attachment_name, cache_source_attachment_key, source_kind)` partial index；每批一次 bridge，no-op OA snapshot 零调用。
- 安全：bridge 与 promotion apply 都要求紧邻 dry-run 的 SHA-256 candidate fingerprint；候选变化立即停止。
- 测试覆盖：两种到达顺序真实 PostgreSQL integration、changed/no-op repository、source provenance/promotion、repair fingerprint、migration/index 与 deploy-control exact release command。
- 未测风险：本地未配置 disposable PostgreSQL 时 integration tests 会跳过；发布后必须通过生产 dry-run/apply、identity audit、Workbench/进项使用/待找发票页面和性能指标补证。

## 2026-07-17 - 相同 OA snapshot 零写与 change-driven fan-out

- 目标：消除周期性 `oa.sync` 在源数据未变化时更新 projection 时间戳、重写子表并让 OA/Workbench/成本统计等页面反复 refreshing 的写放大。
- 边界：`PostgresOAProjectionRepository` 是 completed OA diff/write owner；`PostgresOaPendingPaymentSourceSnapshotRepository` 是 status/admission diff owner；`OAProjectionSyncService` 只依据 snapshot `affected_scope_keys`、真实删除 scope 和 promotion scope 编排既有 producer/gateway。
- 关键决策：相同业务列和规范 JSON 使用 PostgreSQL `IS DISTINCT FROM` 判定 no-op；no-op 仍记录 sync run/运维 watermark，但不改变业务 projection/status/admission 时间戳、不重写 item/attachment、不生成 downstream dirty/outbox。没有增加 fallback、双路 projection 或通用 diff abstraction。
- 测试：unit/SQL tests 覆盖 changed/no-op 两支；真实 PostgreSQL integration 覆盖重复 commit 的 application/status 时间戳和 outbox count 不变；legacy 无 snapshot 的测试 fake 继续保留原 fan-out 语义，不影响生产 authoritative snapshot 路径。
- 待生产门：发布后观察至少一个完整周期 sync 窗口，确认无业务变化时三页面始终 fresh；真实变化仍必须按 exact month 收敛并通过各页面 Audit。


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- OA 集成首轮测试闭环状态为 `documented-risk`：本地测试已覆盖主要 contract、失败分支和跨模块 dirty scope，但真实 OA 登录、OA 草稿页面、OA Mongo 字段变体、同域 iframe/cookie 和生产 worker drain 必须由 staging/生产前 smoke 补证。
- OA Mongo 仍按外部只读源处理；本系统只能建立映射、缓存和投影，不写 OA 原始库。
- 目标 OA 申请人凭据只允许 admin 维护，response/log/audit 不得回显 password；创建 OA 草稿前必须先通过目标申请人登录拿 token。
- 进项 OA 反提和 ETC OA 草稿的本地撤销/删除只处理本系统状态，不删除或撤销真实 OA 草稿/流程。
- OA source alias / migration identity 修复必须先只读审计再显式建模；`app.oa_source_aliases` 中只有 `active` alias 可参与 canonicalization，不得通过删除 `app.oa_applications`、`app.oa_attachments`、`app.oa_attachment_invoice_cache` 或伪造 read model readiness 来消除重复。
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

## 2026-07-03 - OA 完成态别名统一

- 目标：修复历史 OA projection 行的 `workflow_status` 使用 `已完成`、`approved` 或 `2` 等完成态别名时，`workbench_relation` projection 无法读出 OA 源对象，导致待找发票 relation distribution 的 `linked_oa` 为空。
- 影响范围：`postgres_repositories/oa_projection.py` 的完成态 SQL/helper、`OAProjectionSyncService` 完成态过滤、`OA_PROJECTION_SYNC_VERSION`、`workbench_relation` distribution 和待找发票 read model freshness。
- 关键决策：完成态判断属于 OA projection/source-object 边界；下游 relation/pending invoice 只消费统一后的 projection 和 source version，不新增页面级 fallback。
- 文档影响：更新 OA 集成、Workbench relation、待找发票边界和测试记录。
- 测试覆盖：`tests/test_oa_projection_sync_service.py::OaProjectionSyncServiceTests::test_oa_sync_treats_legacy_completed_workflow_aliases_as_completed`、`tests/test_workbench_relation_sql_projection.py::WorkbenchRelationSqlProjectionTests::test_rebuild_keeps_oa_summary_for_legacy_completed_workflow_status`。
- 验证命令：见本轮交付说明。
- 未测风险：未连接真实生产 Postgres/RabbitMQ worker drain；发布后需要重建受影响月份的 `workbench_relation` 与 `pending_invoice` read model，确认历史别名行重新生成 OA summary。

## 2026-06-30 - OA source alias 表与附件票审计归一化

- 目标：治理生产发现的 6 组历史 OA 附件发票跨 OA duplicate blocker，避免把同一 OA 生命周期中的进行中文档与已完成流程文档误判为不同 OA 报销。
- 影响范围：PostgreSQL migration `0081_oa_source_aliases.sql`、`audit_object_identity` 的 OA attachment invoice duplicate 分类、OA 集成边界文档和对象身份运维文档；不改 OA 原始投影、附件、附件发票 cache 或正式发票池。
- 关键决策：新增 `app.oa_source_aliases` 作为显式、可审计 alias 事实表，字段包含 `alias_row_id`、`canonical_row_id`、`reason`、`evidence_hash`、`status`、review 信息和 `raw_payload`。审计工具只读取 `status='active'` 的 alias；未激活 alias 或缺表时保持旧逻辑，继续按原 OA row/source 判定 cross-OA blocker。
- 文档影响：更新本记录、`boundary-io.md`、`tests.md` 和 `docs/operations/object-identity-dedup.md`；read model 文档继续保留“不得通过下游投影或 readiness 规避事实冲突”的决策。
- 测试覆盖：新增 `tests/test_audit_object_identity_tool.py::AuditObjectIdentityToolTests::test_active_oa_source_alias_downgrades_lifecycle_duplicate`；更新 `tests/test_postgres_migrations.py` 覆盖 0081 migration discovery、required table 和 core table raw payload/identity guard。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_audit_object_identity_tool.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_migrations.py::PostgresMigrationDiscoveryTests::test_expected_migration_files_are_present_and_ordered tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_sql_contains_required_schemas_and_tables tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_core_tables_keep_legacy_or_external_identity_and_raw_payload -q`。
- 生产执行：2026-06-30 在生产 `app.oa_source_aliases` 写入 3 条 `active` alias：`oa-exp-69898450db8c0a3633bd748c -> oa-exp-2005`、`oa-exp-69a7aeaedb8c0a3633bd74a7 -> oa-exp-2035`、`oa-exp-69c0b43adb8c0a3633bd74c4 -> oa-exp-2062`。未删除 `app.oa_applications`、`app.oa_attachments`、`app.oa_attachment_invoice_cache*` 或 read model 行。
- 生产验证：生产固定入口 `finops-deploy-control workbench-audit-identity etc-ticket-fix-477cbf08-20260630204229 --json --limit 1` 返回 `blocking_issue_count=0`、`oa_attachment_invoice_blocking_duplicate_group_count=0`、`oa_attachment_invoice_duplicate_group_count=0`；`/health/ready` 返回 `status=ready` 且 release runtime consistent。
- 未测风险：本地不连接真实 OA Mongo；完整 `tests/test_postgres_migrations.py` 当前受无关 `bank_flow_rule_batch` WIP storage contract 影响，不能作为本变更唯一结论。生产 active release 中的 audit helper 已同步本补丁以支持本次固定入口复核，后续正式发布仍应包含 migration 0081 和同一代码变更，避免下次 release 覆盖。
- 后续事项：后续遇到同类 OA lifecycle alias 时仍必须先只读审计并显式登记 active alias；不得通过弱业务指纹、删除 cache 或伪造 readiness 自动收敛。

## 2026-06-22 - OA projection 保留真实申请日期

- 目标：修复下游 Workbench SQL active generation 只能拿到 OA 月初日期，导致关联台申请人时间 chip 在部分 OA 行缺失或退化的问题。
- 影响范围：`PostgresOAProjectionRepository.upsert_application_records(...)` 的 `app.oa_applications.application_date` 写入、`OA_PROJECTION_SYNC_VERSION`、Workbench SQL projection source freshness；不修改 OA 原始 Mongo，只调整本系统投影。
- 关键决策：`application_date` 应优先来自 `OAApplicationRecord.detail_fields["申请日期"]` / `申请时间` 的真实日期部分，只有缺失时才用 `record.month` 兜底。同步版本 bump 后，后续 OA sync 会让相关 read model stale 并重投。
- 文档影响：同步本实施记录；关联台模块记录 applicant chip 的消费 contract。
- 测试覆盖：`tests/test_oa_projection_sync_service.py::OaProjectionSyncServiceTests::test_projection_application_date_uses_record_detail_date_not_month_start`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_projection_sync_service -v`。
- 未测风险：未连接真实 OA/生产 PostgreSQL 回放历史数据；发布后需观察 OA sync 和 Workbench worker drain，确认目标月份 active generation 已重建。

## 2026-06-22 - OA 会话校验短暂超时自动重试

- 目标：修复 OA iframe / 前端首次进入时 `/api/session/me` 因代理、后端或 OA 用户信息服务短暂慢响应而在 10 秒后直接显示“会话校验失败”的问题。
- 影响范围：前端 `SessionProvider` 会话 bootstrap 状态机、`SessionGate` 回归测试；后端 `/api/session/me` API contract 和 OA 权限模型不变。
- 关键决策：只对前端 `request_timeout` 做自动重试，保持“正在验证 OA 会话...”状态；401、403、后端返回的 OA 身份服务错误仍按原错误态展示，避免掩盖真实未登录、无权限或配置错误。
- 文档影响：更新 `oa-integration/tests.md`，登记 session 首次校验短暂超时回归。
- 测试覆盖：更新 `web/src/test/SessionGate.test.tsx`，覆盖首次 session 请求超时后保持验证态并自动重试，重试成功后进入业务页面。
- 验证命令：见本轮交付说明。
- 未测风险：真实 OA 登录接口、同域 cookie、生产代理和冷启动耗时仍需 staging/生产前 smoke 证明；持续不可达场景仍会在重试耗尽后显示原错误页和手动重试入口。
- 后续事项：发布前按关键 smoke flow 用真实 OA iframe 打开 `/fin-ops/?embedded=oa`，确认慢启动或刷新期间不会误落到会话失败页。

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

## 2026-08-25 - OA 附件当前子付款项归属闭环

- 根因：部分历史附件解析 payload 保留旧 expense item identity；promotion/projection 曾让嵌套旧字段覆盖当前结构化 item，identity bridge 也未在每次重算时证明 current item 存在、current OA owner 唯一并清理失效派生边。结果是 canonical 发票虽然有 `oa_attachment_invoice` provenance，关联台仍可能无法把它稳定放回当前 OA 子付款项。
- 运行时收口：OA projection 与 promotion 始终以外层结构化 item id/row index 为当前权威 owner，保留其它 parser 字段；identity bridge 先把 OA row scope 收敛为受影响 cache keys，只对这些 keys 全局证明唯一 current OA owner 并清理失效派生边。跨 OA 多 owner fail closed；同一 canonical OA 多 item 继续合法。
- 复发源收口：raw cache `source_kind=invoice/evidence/artifact` 只保留 parser occurrence，不再直接授权 reverse promotion。promotion 只消费 `attachment_identity_invoice`，并集合式复核 current application、attachment 和 item 后输出当前 item/row index/name。bridge 的唯一性改为“每个 parsed attachment occurrence 唯一 current attachment owner”，同一 OA 内多个 owner 也 fail closed；同一物理附件以不同 occurrence key 归属多个 item 时继续完整保留。
- 存量修复：复用 `import_audit_repair_ops` 增加全量 OA attachment ownership 模式。它扫描全部非删除 OA provenance 发票，只允许 visible canonical 发票在强发票 identity + 当前 attachment owner 同时成立时追加 `oa_expense_item_invoice`；保留原附件来源，不写 alias、不写 relation case。hidden duplicate、unresolved、跨 OA ambiguous/conflict 只报告零写。
- 数据安全：dry-run 产生 source fingerprint，并通过显式 `--rollback-manifest-path` 在 helper 固定的 root-owned `0700` 目录内以 `O_EXCL + O_NOFOLLOW + 0600` 写 scoped rollback artifact；普通 stdout 只含 rollback fingerprint/count 与哈希化 lineage，不输出原始 source links、附件 key 或 OA/item parent。execute 在 serializable transaction + advisory lock 中重读 source fingerprint，并在锁内再次验证同一私有 rollback artifact fingerprint，以 source-links CAS 更新并与 `audit.events` 同事务提交。幂等和页面闭环验证后，固定 helper 只按安全文件名和 manifest fingerprint 精确删除该 artifact。重复执行零写；不新增 migration、表、read model、worker、cache 或数据库备份，不删除主数据库。
- 性能：运行时 bridge I/O 绑定受影响 cache keys；存量审计/修复是显式运维命令，不进入 HTTP、同步周期或页面热路径。

## 2026-08-26 - OA PDF 按页文本/OCR 识别链路收口

- 生产根因：目标 `oa-exp-2246` 的 28.80 正式 PDF 已稳定归属第二条子付款项，但 PDF 文本层把“下载次数 1”和 20 位发票号码拼成连续 21 位数字。严格身份规则正确拒绝该号码；旧 OA 主链只解析 PDF 文本，而人工录入入口另有页面 OCR，因此 OA cache 长期为 `no_evidence`，现有人工导入 canonical 发票也无法获得 OA attachment/item provenance。
- 运行时收口：`OAAttachmentInvoiceService` 只保留一个 PDF evidence representation 边界。每页先解析文本；只有该页未形成正式发票强 identity 时，才以既有 2 倍渲染和统一图片安全策略 OCR 同页。OA `parse_file_result` 收集全部页面并按正式 identity 去重；人工上传识别复用同一边界并在首个正式发票证据后停止。
- 旧链路删除：删除人工上传专用 `_recognize_first_invoice_from_pdf_images` 分叉；不新增第二 parser、号码截断、页面/Workbench fallback、read model、worker、表或 API。
- 身份与安全：带或不带“发票号码”标签的连续 21 位数字都不合法，禁止截断、去掉首位或末位猜测发票号；价税合计按发票货币固定两位小数分界，并验证 `未税金额 + 税额 = 价税合计`，不能把下一行税率、税号或其它数字字段拼成伪金额。付款截图和无正式证据图片继续不进入统一发票池。parser version 升级使旧 cache 失效，历史重算只通过既有 durable `oa.sync` / 精确附件刷新与 promotion 边界执行。
- 失败语义：RapidOCR 是部署必需依赖，不保留 optional import；初始化或推理异常显式抛出 `OAAttachmentOCRRuntimeError`，使 `oa.sync` 失败重试且不写 current cache。只有 OCR 正常执行但确实无文本时才返回空证据，禁止把运行时故障永久缓存成 `no_evidence`。
- 性能：文本已形成正式发票 identity 的页面不初始化 OCR；人工上传在首张识别成功后停止；OA 只对未识别页 OCR，不对整个 PDF 无条件重复 OCR。
- 数据迁移：无 schema migration、无直接 SQL 业务修补、无数据库备份。生产修复复用现有 canonical UUID，并由既有 promotion 幂等追加带 `source_expense_item_id` 的 `oa_attachment_invoice` 来源；既有人工/审计形成的 `oa_expense_item_invoice` 显式归属边只保留，不由普通 promotion 伪造。

## 2026-08-26 - 设置页 OA 精确附件刷新迁入 worker

- 根因：HTTP 侧 `OAManualImportService` 运行时注入的是 PostgreSQL projection adapter，却用动态能力探测调用 Mongo-only refresh；能力不存在时静默重读旧 projection，仍返回 200 和旧计数，形成“刷新成功但没有下载/OCR/重解析”的假成功。手动导入入口还有同一旧 fallback。
- 边界：删除两处动态 refresh/fallback 和 HTTP 侧 promoter。Settings route 只通过 `OAAttachmentRefreshRequestService` 校验 row IDs、登记现有 `oa.sync(operation=refresh_attachments)` 并读取受控 durable status/result；Mongo 下载、强制 parser reparse、定向 projection upsert、promotion 和 matching reconciliation 全部由既有 OA worker 执行。
- 合同：POST 返回 202/event id，GET 返回 `pending/processing/done/failed/dead_lettered`。只有 `done` 才携带逐 row 计数和 promotion summary；缺记录、非完成态、OCR/解析/promotion 失败均显式失败，禁止回退普通全量 sync、旧 projection 或第二套解析。
- 数据与性能：精确 operation 只处理选中 rows，不执行 stale deletion，不新增 event type、worker、表、migration、数据库备份或页面 read model；重复执行保持 canonical invoice/source link 幂等，并显式补发 matching reconciliation。
## 2026-07-28 - 日常报销付款明细存量重投合同

- 目标：确保历史日常报销与新数据都保留稳定付款明细 identity，并让 OA 附件证据可显式回指对应付款项。
- 关键决策：继续使用既有 `oa-exp-{external_id}:item:{row_index}:{fingerprint}`，不生成随机 UUID、不改变父 OA ID；item 不是独立可配对事实。`OA_PROJECTION_SYNC_VERSION` 升级为 `2026-07-28-expense-item-source-identity-v2`，由 durable `oa.sync` worker 幂等重投存量，不在 HTTP 或页面链路 inline 拉取。

## 2026-07-28 日常报销费用字段保真

- 目标：关联台子付款项的“申请事由”同时展示 OA 来源“费用内容”和“费用说明”，且不改变成本统计既有 `expense_content` 口径。
- 决策：schedule item 分别保存 `fee_content` 与 `fee_description`；`expense_content` 继续使用首个非空字段作为兼容输出，不新增表、worker、read model 或第二同步链路。
- 存量：`OA_PROJECTION_SYNC_VERSION` 升级为 `2026-07-28-expense-item-display-fields-v3`，只通过既有 durable `oa.sync` worker 幂等重投。
- 不变项：原 OA Mongo 只读、父 OA relation identity、统一发票池和附件 promotion 规则不变；禁止 fuzzy item/invoice mapping。

## 2026-07-29 ETC OA 历史附件引用全量修复

- 目标：修复 ETC OA 表单历史数据中保存的 `http://127.0.0.1:9300/fileManager/...`，避免 OA 前端生成 `/oa-apihttp://...` 空白链接。
- 受控写入：全量扫描 form 2，按 ETC 强 marker 限定对象；逐记录备份、哈希并发门禁后，只把内部绝对前缀替换为根相对 `/fileManager/`。
- 生产结果：1,554 条记录全量复扫，7 条 ETC OA 与全部非 ETC OA 的目标错误引用均为 0；206 个唯一 ETC PDF 全部验证为真实 PDF。
- 不变项：不重提 OA，不修改 `processStatus`、金额、附件成员、App canonical facts、配对关系或任何 read model/worker。
## 2026-08-15 - OA附件发票多子付款项来源保真

- 根因：record 级发票聚合和 promotion 单值冲突规则会折叠同一物理发票在同一 OA 多个子付款项的来源；解析 cache 又把子付款项上下文混入 key，导致相同附件重复 OCR。
- 收口：物理附件 cache identity 排除 item occurrence、保留 OA 边界；每个 expense item 的 occurrence 仍生成独立来源 key。promotion 从 item 级结果生成候选，同一 OA 的多条 item 来源允许追加，canonical invoice source links 按 item 去重保留；跨 OA 自动合并继续 fail closed。
- 模板确认：现有解析器已覆盖 `电子发票（铁路电子客票）` / `railway_e_ticket_invoice` 的票号、日期、金额和正式发票准入，本次无需新增并行模板。
- 数据与运行时：没有新增 migration、表、read model、worker 或任务型数据库备份；正常 OA sync / 精确 attachment refresh 会幂等补齐来源，不执行全历史重放。

## 2026-08-16 进行中附件隔离、铁路客票金额与 lifecycle alias promotion

- 影响范围：Mongo OA adapter 的日常报销记录构建、设置页精确附件刷新、铁路电子客票金额解析、OA 附件正式发票 promotion 与 PostgreSQL active source alias read port。
- 关键决策：进行中 OA 只保留附件引用元数据；所有入口都由 adapter 构建边界强制禁止下载/OCR/evidence/invoice。铁路票价限制为最多两位小数，避免压平文本后吞入下一行长客票号，并升级 parser cache version。promotion 按批量读取 `app.oa_source_aliases.status='active'`，只允许 lifecycle alias 两端共享 canonical invoice；未激活或不同 canonical OA 继续 fail closed。
- 生产样本补充：历史统一发票来源可能把 `derived_from_oa_id` 保存为 `父OA ID:item:...`。promotion 必须复用 `oa_attachment_parent_oa_id` 先归一父 OA ID，再做 active alias 集合查询和冲突判断；否则已批准的生命周期 alias 仍会被旧 item 级来源误判为跨 OA 冲突。
- 旧链路删除：移除调用方可通过 `parse_attachment_evidence=True` 强迫进行中流程解析的隐式能力；不新增第二套解析、promotion 或页面 fallback。
- 数据安全：不改主数据库 schema，不删除 OA 投影、附件 cache 或 canonical invoice；生产历史样本只允许先 dry-run，再对已核验的 active alias 与精确 OA row 执行受控修复。
- 验证：新增进行中人工刷新、高铁票价长号、active alias promotion 与 repository 单批查询回归；发布后验证目标 144.99 OA 的铁路票进入统一发票池并保留 1 分金额差异 chip，同时附件缺失异常消失。

## 2026-08-17 OA 费用类型真实字段收口

- 生产事实：目标日常报销 `oa-exp-2290` 的子付款项费用类型来自 `schedule[].purposeType='s4'`，而 `data.detailReimbursementType='withdraw_expense'` 是报销业务类型，不是费用类型。
- 修复：Mongo OA adapter 只读取真实 `purposeType`；移除无生产事实依据的候选字段以及 `reimbursementType` / `detailReimbursementType` 费用类型污染链，未知枚举仍保持空值，禁止回退为“其他”。
- 同批生产字段覆盖审计确认：`schedule[].purposeType` 覆盖 2,642 条 OA；`schedule[].category` 与 `schedule[].feeType` 覆盖数均为 0。因此直接读取面只保留 `purposeType`，避免猜测字段在未来静默覆盖真实费用类型。
- 存量：`OA_PROJECTION_SYNC_VERSION` 升级为 `2026-08-17-expense-purpose-type-v7`，由既有 durable `oa.sync` worker 幂等重投；不新增表、read model、worker、缓存或同步链路。
- 下游：统一 canonical `expense_type` 继续供关联台项目列第二行 chip、OA 详情和成本统计消费；下游页面不得重新猜测或回退费用类型。
