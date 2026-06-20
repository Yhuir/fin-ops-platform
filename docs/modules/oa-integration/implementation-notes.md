# OA 集成 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- OA 集成首轮测试闭环状态为 `documented-risk`：本地测试已覆盖主要 contract、失败分支和跨模块 dirty scope，但真实 OA 登录、OA 草稿页面、OA Mongo 字段变体、同域 iframe/cookie 和生产 worker drain 必须由 staging/生产前 smoke 补证。
- OA Mongo 仍按外部只读源处理；本系统只能建立映射、缓存和投影，不写 OA 原始库。
- 目标 OA 申请人凭据只允许 admin 维护，response/log/audit 不得回显 password；创建 OA 草稿前必须先通过目标申请人登录拿 token。
- 进项 OA 反提和 ETC OA 草稿的本地撤销/删除只处理本系统状态，不删除或撤销真实 OA 草稿/流程。
- OA source alias / migration identity 修复必须先只读审计再显式建模；不得通过删除 `app.oa_applications`、`app.oa_attachments`、`app.oa_attachment_invoice_cache` 或伪造 read model readiness 来消除重复。

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
