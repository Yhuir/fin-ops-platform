# 流水规则批量处理实施记录

## 2026-08-14 - OA-first 成本隔离更正

- 流水规则批次提交不会自行形成 OA 成本；对应银行流水只进入成本统计“按时间/按标签”。
- Browser 回归已删除“流水规则手续费成本项目”旧链路。下文早期实施记录里的该项目名仅是历史记录，不再代表当前合同。

## 2026-08-12 - OA/发票要求按变化标签增量传播到 active relation

- 业务口径：批次 submitted/withdrawn 历史 payload 继续冻结；active Workbench relation 的 `requires_oa/requires_invoice` 不再永久冻结。规则保存只比较这两个布尔值的语义差异，并只处理持久化 tag proof 命中变化标签的 active relation。
- 原子边界：PostgreSQL 设置 CAS、visible background job 和 `settings.bank_relation_requirements.recalculate.requested` outbox 在同一事务提交。API 只返回 job receipt；`settings-maintenance` required worker 承担后台执行，禁止页面请求内扫描关系。
- 重算语义：每条关系使用其完整 `paired_requirement_tag_codes` 和当前规则做 OR；先预验证本 job 全部关系的 case、精确月份、tag proof 和 current rule，任一缺失则零关系写入。结果未变短路；结果变化通过正式 relation command 保留 identity/members/amount，更新 metadata 并追加 `bank_relation_requirement_recalculated` history。
- 收敛与性能：只刷新实际写入关系所在的精确 `workbench` / `workbench_relation` 月份并标记同月 matching dirty，不允许 `all`。迁移 `0145` 创建 tag-proof GIN 索引，并投递一次幂等全标签 convergence job，用于把发布前存量 active relations 收敛到当前规则。
- 旧链删除：删除人工 `--reapply-case-id` / `--expected-rule-version` helper 参数、专用 plan/execute 分支、运维说明与对应测试；历史缺失/损坏 proof repair 仍保留，但不再承担正常规则传播。
- 验证：覆盖 semantic diff、完整 tag OR、fail-closed 零写、no-op、幂等重放、原子 settings/job/outbox、精确月份 refresh、worker registry、前端 job feedback、旧 helper 负向门禁和既有页面回归。

## 2026-08-10 HeroUI 批次筛选收敛

- 未提交/已提交/历史改用共享 HeroUI `ToggleButtonGroup`，月份改用共享“全部 + 年/月”控件；删除旧嵌套 segment、原生 month input 和对应 CSS，canonical 列表/提交/撤回 I/O 不变。

## 2026-08-08 submit-selection canonical 事实源闭环

- 生产 `submit-selection` 曾先从 `ImportNormalizationService._transactions_by_id` 和启动时 category/settings snapshot 生成 expected proof，再由 PostgreSQL `SERIALIZABLE` guard 用当前事实生成 actual proof；两套事实源导致页面刷新后仍反复返回 `bank_flow_rule_batch_candidate_conflict`。
- 请求现在必须携带列表项 `scope_month`；application service 复用页面 canonical query，一次取得候选流水、当前有效分类、标签 policy/requirement 和 active relation。选中提交不再调用 import/category/settings 启动时快照。
- relation metadata 使用同一 canonical rule proof 冻结 `flow_rule_version`、`requires_oa` 和 `requires_invoice`；最终写事务同时比较 selected-row proof 与 rule proof。假冲突被移除，真实流水、分类、规则或占用漂移继续 fail closed 并整体 rollback。
- 页面仍为写后一次 normal GET；没有新增 polling、read model、worker、缓存或页面 fan-out。no-OA 等其他模块继续保留其现有读取合同。

## 2026-08-05 selected-row 时间语义与冲突恢复

- 根因是 submit-selection 初读 proof 保留银行导入的空格时间，而事务内 canonical 重读把同一 `timestamptz` 输出为 ISO 8601 offset；旧 guard 直接比较字符串，误把同一时刻判为候选变化。
- proof 现统一比较 UTC 秒级时刻；无时区文本按 `Asia/Shanghai` 解释，非法时间保留原文 fail closed。金额、分类、方向、账户、月份、成员、占用和真实时间漂移的并发保护不放宽。
- 页面复用共享时间展示 helper；真实 candidate conflict 清空旧选择/详情并只刷新一次列表，禁止自动重提。
- 回归覆盖等价序列化通过、真实时间漂移拒绝、ISO 时间无 `T/+08:00` 裸显，以及冲突后一次 GET/一次 POST/选择清空。

## 2026-07-31 标签管理抽屉迁移到共享壳

- 只把标签管理的自定义 backdrop/aside/header/close/footer 壳替换为共享 `AppDrawer`，保留 `min(960px, 92vw)`、表格、权限、dirty/busy、nested dialog、规则 CAS 与保存后回读时机。
- 退出生命周期改由 HeroUI right drawer 统一管理；loading/mutation 期间禁止 dismiss，旧 shell CSS 和并行生命周期已删除。
- canonical query、规则 I/O、API shape、写事务和模块边界均未变化，因此不修改 `boundary-io.md`；没有新增第三方动画库、fallback 或第二套 drawer abstraction。
- 回归由 `BankFlowRuleBatchPage.test.tsx` 的交互/旧 shell 负向门禁和 `drawer-motion.spec.ts` 的共享真实浏览器 motion 合同承担。

## 2026-07-30 live detail 与 submitted bucket 完整性修复

- 根因一：列表生成的 live candidate 没有持久化，但页面自动选择后调用了只读取正式批次的详情 API，因此返回“流水规则批次不存在”。详情现以列表项 `scope_month` 调用同一 canonical builder 重算，提交 guard 复用该 helper，不增加 draft 存储、read model、Redis 或 fallback。
- 根因二：submitted/withdrawn bucket 曾跳过月份 candidate rows 和 active relation 输入，导致共享 builder 无法重建正式状态，出现 summary 有数而列表为空。repository 现在对所有 bucket 读取同一月份窗口的 bounded canonical 输入。
- 回归覆盖列表到 live 详情 identity、月份路由透传、submitted summary/list 一致和页面自动详情请求；页面仍为 API 直读，旧 persisted draft/read model 链路未恢复。

## 2026-07-29 未提交 live candidate 与 draft runtime 退休

- 未提交候选不再读取或写入 persisted draft；repository 在同一 `REPEATABLE READ / READ ONLY` snapshot 中批量读取请求月份（内部转账含 ±2 天窗口）的银行流水、有效分类、paired policy、active relation 和正式历史，application service 使用共享 live builder 计算 summary、过滤、排序与分页。
- 生产验证发现旧 SQL 在 live builder 前只按 manual/confirmation category 预筛，导致银行明细可自动识别的 188500 元内部往来款仍被遗漏。修复后 repository 返回月份窗口内全部 non-deleted 银行流水和分类事实，GET、详情、提交 guard 与 Audit 统一复用 `BankTransactionEffectiveCategoryProvider` 批量计算 effective category；写事务同时锁定当前 app settings 规则行，禁止查询与提交间规则漂移。
- GET、提交事务复核与 Page/System Audit 使用同一 `BankBatchService` 匹配内核；候选 identity、成员、金额、188500 元内部往来匹配与占用判断保持确定性，歧义 fail closed。
- 提交携带 `scope_month`，在写事务内重读并锁定候选依赖；规则、成员、金额、分类或 active relation 漂移返回 candidate conflict，relation/batch 写入整体回滚。
- canonical draft event、owner、producer、worker、registry/env、repair/replay 和 deploy 接线已删除；`app.bank_flow_rule_batches/events` 只保存 submitted、withdrawn、stale 等正式业务状态和历史。
- 下方 2026-07-27 及更早记录是迁移过程审计，不再作为当前运行时合同；当前合同以本节、`README.md`、`boundary-io.md` 和 `state-machine.md` 为准。

## 2026-07-27 页面 canonical direct-read 迁移

- 列表、summary、分页和详情改由 `BankFlowRuleBatchCanonicalQueryRepository` 直接读取 `app.bank_flow_rule_batches/events`、银行/分类/settings facts 和 `app.workbench_pair_relations.status='active'`。
- 列表的 settings、total、page rows、summary 位于同一显式 `REPEATABLE READ / READ ONLY` snapshot；服务端过滤/分页，settings + 组合结果固定 2 次 SELECT。详情固定 4 次 SELECT，无逐行 relation/category 查询。
- API 删除 `read_model_status/version/stale_reasons`、source/read-model scope、refresh enqueue 和 operation-barrier envelope；前端删除 stale polling、202/background reconcile 和本地伪造提交/撤回状态，每次写成功只执行一次列表 GET。
- submit/submit-selection/withdraw/reset 继续使用 relation command、active occupancy、幂等/CAS、审计和 changed-batch delta writer；冻结标签与 requirement metadata 不变。
- no-OA legacy 和共享全局 worker/manifest/App Status/deploy 注册未在本分支删除；共享删除清单交主控在所有页面迁移分支合并后 whole-repo scan。
- 本节取代下方历史 read-model/freshness 实施记录作为当前运行时事实；下方内容只保留演进审计。

## 2026-07-21 未提交资格、精确月份原子刷新与完整汇总

- 新未提交资格收口为 active tag 且 `requires_oa=false`、`requires_invoice=false`；需要 OA 或发票的流水退出本页面未提交区。标签抽屉仍显示全部 active tags，submitted/withdrawn rail 只按实际历史聚合显示。
- 页面删除 `activeTags + summary categories + current page batches` 的旧三路标签合并；主/子 rail 的 batch count 与 row count 只读取服务端完整 summary，不再受分页影响。
- 规则保存先纯规范化并比较合格 tag code 集合；资格中性变化零 refresh，完全 no-op 零写入。资格变化用单条集合 SQL 查找 bank-detail/现存 draft 的受影响月份。
- PostgreSQL 生产路径在同一事务内用数据库版本锁写 settings，并批量写所有月份 dirty scope/outbox；队列异常、部分入队或版本冲突整体回滚。响应携带 changed codes、affected months、targets 和 refresh 状态。
- source versions 删除原始 `bank_flow_rule_batch_tag_rules_version`，改用合格 tag code 集合的稳定 `bank_flow_rule_batch_eligibility_version`，避免 OA-only/Invoice-only 互换造成无效重建。
- 规则保存前端不等待 worker：先清空选择、隐藏受影响当前月份旧未提交 rows 并反馈成功；月份 barrier 和 reload 在后台执行。
- 上游刷新补齐：银行导入/导入状态/自动标签规则走 derived lifecycle，手工银行分类在 Turnover UoW 同事务追加精确 `bank_flow_rule_batch` dirty/outbox。
- 旧 `all` 规则刷新、全部 active 标签未提交显示、当前页行数反推 rail count 和已删除 relation requirement 回写文档均已移除。

## 2026-07-20 规则保存 O(1) 与 formal relation 合同收口

- 2026-07-14 formal-relations 合同已取代 2026-06-30 的 requirement-based paired/open 模型：active relation 完整成员进入 paired，无 active relation 的事实进入 unpaired singleton。
- 规则保存删除两次 active relation 全量扫描、逐 relation metadata/history 写、turnover mode 升级、broad lifecycle 和重复 refresh；当时暂以一次 `bank_flow_rule_batch/all` 代替，已在 2026-07-21 收口为精确受影响月份事务入队。
- semantic no-op 不递增 version、不写 settings/audit、不入队。
- `BankBatchApplicationService` 中 bank-flow 可达的旧 tag writer/sync/helper 已删除；独立 no-OA legacy service 保留自身合同。
- migration `0111_bank_flow_rule_batch_tag_rules_canonical_shape.sql` 把旧 selected seed 合并到 requirements 后删除 selected shape；runtime 不留 fallback。
- 2026-06-30 requirement 同步方案已从本实施记录删除，不再描述当前运行时合同。

## 2026-07-06 Scope source-version freshness 修复

目标：修复生产 `bank_flow_rule_batches` API 在 `bank_flow_rule_batch:2026-07` worker 刷新已完成且耗时约 100ms 后，仍因 `bank_detail_source_versions_mismatch` 持续返回 stale 并反复 enqueue refresh 的问题。

关键决策：

- API 列表 fresh gate 对月份 scope 不再依赖 bank-detail provider 的 mutable `last_source_versions`；它和 worker 一样通过 `read_model_scope_source_versions(month)` 读取 bank-detail scope summary 与 Workbench relation source-version port。
- Worker 月份 scope rebuild 在 precheck 后若无法 skip，发布 snapshot 时复用同一份 precheck source_versions；后续 `bulk_get_for_rows(...)` 或 relation 明细读取只影响 row payload，不允许改写 scope source-version 形态。
- 不放宽 stale 判定、不把 stale 伪装成 fresh；修复的是同一 scope 内 API 期望版本与 worker 发布版本不一致的问题。
- 旧 no-OA legacy worker/模块仍是独立 legacy 域，本修复只覆盖当前 `/bank-flow-rule-batches` 生产链路和中性 bank-batch refresh core。

测试覆盖：

- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_bank_flow_list_freshness_uses_scope_source_versions`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_bank_flow_refresh_publishes_prechecked_scope_source_versions`
- `tests/test_bank_flow_rule_batch_backend_boundary.py`

验证命令：

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_routes.py -q`

## 2026-07-04 Bank Transaction Paired Policy 全局化

目标：把“流水规则标签 / 流水规则标签管理”收敛为全局 Bank Transaction Paired Policy，并删除 bank-flow 页面链路中的旧 no-OA 历史重算和 selected-tag 兼容输出。

关键决策：

- 关联台 `WorkbenchCandidateGroupingService` 的 paired/open 分区改为：任何含银行流水的 group 都先按银行流水 row 上物化的 `requires_oa` / `requires_invoice` 或 legacy `paired_requires_*` 判定；缺失 policy metadata 默认需要 OA 和发票。
- `bank_flow_rule_batch`、工资/内部转账、外部往来、legacy no-OA 等关系类型不再能绕过全局 policy 直接进入 paired；需要无 OA/无发票闭环时，必须由 relation metadata 显式声明 false/false 或对应单项 false。
- `GET /api/bank-flow-rule-batches/tag-rules` 的 public payload 不再返回 `selected_tag_codes` / `inactive_selected_tag_codes`；前端 feature type/API/page 同步删除 `selectedTagCodes` 兼容字段。
- 删除旧 no-OA 历史重算 route、页面入口、前端 API/type/test 和 application service 中无入口的方法；旧 no-OA 历史事实仍由 `no-oa-bank-batches` 模块管理，不再挂回 bank-flow 页面。

测试覆盖：

- `tests/test_no_oa_bank_batch_tag_selection_api.py`
- `web/src/test/RelationGroupGrid.test.tsx`
- `tests/test_bank_flow_rule_batch_routes.py`
- `web/src/test/BankFlowRuleBatchApi.test.ts`

## 2026-07-03 Read model unchanged source-version probe

目标：修复生产 full critical 1s smoke 中 `bank_flow_rule_batch:2026-02` 即使 `source_versions_unchanged` 也可能在 skip 前耗时约 1.4s 的问题。

关键决策：

- `bank_flow_rule_batch.read_model.refresh` 的月份 scope 先通过 bank-detail scope summary 和 Workbench relation source-version port 构造当前 source_versions，再对比 `read_model.bank_flow_rule_batch_rows` 的 source-version summary。
- source_versions 一致时直接 complete dirty scope，不再读取完整银行交易行、分类行、关系行，也不保存 snapshot。
- 无法证明 source_versions 一致时才进入完整 rebuild；`all` scope 不走月级 probe，避免无效 precheck。
- 该改动只调整 worker 内部 I/O 顺序，不改变 bank-flow API、页面 DTO、规则设置、关系状态机、readiness/outbox 事实源或审批/审计边界。

测试覆盖：

- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_bank_flow_scope_source_versions_use_probe_ports_before_row_loading`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_unchanged_read_model_scope_uses_bank_flow_source_version_summary`
- `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_source_versions_for_scope_keys_uses_scope_summary_without_loading_rows`

验证命令：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests tests/test_bank_flow_rule_batch_application_service.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_read_model_manifest.py -q`

## 2026-07-01 最终校验闭环

目标：关闭收口检查发现的 validation drift，确保 bank-flow tag-rule 边界即使被服务层直接调用，也不会接受旧 no-OA selected-tag 语义或重复规则覆盖。

关键决策：

- `AppSettingsService.update_bank_flow_rule_batch_tag_rules(...)` 在服务边界拒绝 `selected_tag_codes` / `selectedTagCodes`，错误码为 `bank_flow_rule_batch_selected_tag_codes_forbidden`。
- `rules[]` 中重复 `tag_code` 在归一化前 fail fast，错误码为 `duplicate_bank_flow_rule_batch_tag_rule`，不再允许后写覆盖前写。
- 不改变 no-OA legacy `selected_tag_codes` 合同；该旧写路径只属于 `no-oa-bank-batches`。
- 长期文档状态更新为 modular closure：页面级 state/effect 编排保留在 page，纯 I/O、DTO、策略、view model、operation barrier helper 和通用组件位于 feature 边界。

测试覆盖：

- `tests/test_app_settings_service.py::AppSettingsServiceTests::test_bank_flow_rule_batch_tag_rules_reject_legacy_selection_and_duplicate_rules`
- `tests/test_bank_flow_rule_batch_routes.py::BankFlowRuleBatchRoutesTests::test_tag_rules_reject_legacy_selection_and_duplicate_rules`

验证命令：

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_app_settings_service.py tests/test_bank_flow_rule_batch_routes.py -q`
- 其余回归命令见本次最终答复。

## 2026-07-01 Read model / 操作 API 性能收敛

目标：降低流水规则批量处理页面常用操作耗时，移除 detail/withdraw 中可避免的 `all` scope 同步刷新，并让 bank-flow worker 使用专属 source-version summary 跳过 unchanged scope。

关键决策：

- `detail_payload(batch_id)` 和 `withdraw_batch(batch_id)` 先读取当前 bank-flow batch storage；只有 batch 缺失时才 fallback `scope_key=all` runtime snapshot refresh。
- `unchanged_read_model_scope_result(...)` 按 relation mode 选择 `bank_flow_rule_batch_source_versions_summary(...)` 或 no-OA summary；worker 对 bank-flow 也启用 unchanged skip。
- `tag-rules` 保存仍保留 `all` refresh enqueue，因为规则变更可能影响所有 active bank-flow relation requirement metadata；要进一步优化需要先引入 tag/relation 到 affected scope 的可靠索引。

测试覆盖：

- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_detail_uses_current_bank_flow_batch_without_all_scope_refresh`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_detail_falls_back_to_all_scope_refresh_when_batch_is_missing`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_withdraw_uses_current_bank_flow_batch_without_all_scope_refresh`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_withdraw_falls_back_to_all_scope_refresh_when_batch_is_missing`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_unchanged_read_model_scope_uses_bank_flow_source_version_summary`

验证命令：

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_postgres_repositories_boundaries.py -q`

## 2026-07-01 Tag-rule settings family 独立切换

目标：关闭 `bank_flow_rule_batch` 运行时规则仍读取/写入 `no_oa_bank_batch_tag_selection` 的问题，避免银行流水规则批处理页面继续被 no-OA settings family 污染。

关键决策：

- 新增迁移 `0083_bank_flow_rule_batch_tag_rules.sql`，在 `app.app_settings.settings_payload` 缺失 `bank_flow_rule_batch_tag_rules` 时，从历史 `no_oa_bank_batch_tag_selection` 一次性复制规则值；运行时不做隐式 fallback。
- `AppSettingsService` 新增 `get_bank_flow_rule_batch_tag_rules_payload()` / `update_bank_flow_rule_batch_tag_rules(...)`，保留原 public payload shape、乐观锁、active tag 校验、审计和自动标签归档时的失效规则清理。
- `BankFlowRuleBatchApplicationService` 的规则读写切到 bank-flow settings key；`BankBatchApplicationService` 按 relation mode 选择 tag rules payload。2026-07-21 起 bank-flow source version 使用合格 tag code 集合的稳定 `bank_flow_rule_batch_eligibility_version`，不再使用原始规则版本。
- 2026-07-04 后旧 no-OA 历史重算不再属于 bank-flow 页面或公开 API；历史 no-OA 事实只由 no-OA legacy 域管理。

测试覆盖：

- `tests/test_app_settings_service.py::AppSettingsServiceTests::test_bank_flow_rule_batch_tag_rules_are_independent_from_no_oa_selection`
- `tests/test_app_settings_service.py::AppSettingsServiceTests::test_update_settings_preserves_bank_flow_rule_batch_tag_rules`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_update_tag_selection_uses_bank_flow_rule_settings_boundary`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_bank_flow_source_versions_use_bank_flow_rule_version_boundary`
- `tests/test_bank_flow_rule_batch_routes.py::BankFlowRuleBatchRoutesTests::test_tag_rules_return_policy_rules_and_map_conflict`
- `tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_bank_flow_rule_batch_tag_rules_settings_are_split_from_no_oa_settings`

验证命令：

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_app_settings_service.py tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_postgres_migrations.py tests/test_postgres_repositories_boundaries.py tests/test_state_store.py -q`

## 2026-07-01 PostgreSQL 独立物理存储切换

目标：关闭 `bank_flow_rule_batch` 逻辑边界已独立但生产批次存储/read model 仍复用 no-OA 物理表的问题。

关键决策：

- 新增迁移 `0082_bank_flow_rule_batch_storage.sql`，创建 `app.bank_flow_rule_batches`、`app.bank_flow_rule_batch_events`、`read_model.bank_flow_rule_batch_rows`，并从历史 no-OA 表中按 `relation_mode=bank_flow_rule_batch` 回填旧数据。
- `PostgresStateStore.load/save_bank_flow_rule_batches*` 改为调用 `PostgresWorkbenchRepository` 的 bank-flow 专属 I/O；`PostgresReadModelRepository.list_bank_flow_rule_batch_rows` 和 `bank_flow_rule_batch_source_versions_summary` 改为查询 `read_model.bank_flow_rule_batch_rows`。
- legacy no-OA 继续使用 `app.no_oa_bank_batches`、`app.no_oa_bank_batch_events`、`read_model.no_oa_bank_batch_rows`；`relation_mode` 仍保留在 bank-flow payload/metadata 中供 API 和 Workbench relation 兼容，但不再作为 bank-flow 运行时读写 no-OA 表的条件。
- 本次不迁移标签规则 family，也不拆分前端页面状态；标签规则 family 风险已在上方 2026-07-01 `bank_flow_rule_batch_tag_rules` 切换中关闭，前端状态拆分仍保留为后续任务。

测试覆盖：

- `tests/test_postgres_migrations.py::PostgresMigrationDiscoveryTests::test_bank_flow_rule_batch_independent_storage_schema_and_backfill_are_declared`
- `tests/test_postgres_repositories_boundaries.py::test_bank_flow_rule_batch_save_uses_dedicated_physical_tables`
- `tests/test_postgres_repositories_boundaries.py::test_no_oa_bank_batch_save_does_not_touch_bank_flow_physical_tables`
- `tests/test_postgres_repositories_boundaries.py::test_bank_flow_rule_batch_read_model_queries_dedicated_table_without_relation_mode_predicate`
- `tests/test_bank_flow_rule_batch_backend_boundary.py::BankFlowRuleBatchBackendBoundaryTests::test_postgres_state_store_bank_flow_storage_uses_dedicated_repository_io`
- `tests/test_state_store.py::StateStoreTests::test_bank_flow_rule_batches_use_independent_local_snapshot_file`

验证命令：

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_postgres_migrations.py tests/test_postgres_repositories_boundaries.py tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_application_service.py -q`
- `git diff --check -- backend/src/fin_ops_platform/postgres/migrations backend/src/fin_ops_platform/services tests docs .planning/quick/20260701-bank-flow-rule-batches-full-closure-goal`

## 2026-06-30 App Status storage contract 补齐

目标：修复 `bank_flow_rule_batch` 已登记到 App Status read model registry，但 migration storage contract 未登记，导致完整 `tests/test_postgres_migrations.py` 失败的问题。

关键决策：

- 保留 `bank_flow_rule_batch` 作为独立 read model key、scope、worker event、operation barrier target 和 App Status readiness 目标；不回退到 `no_oa_bank_batch` registry。
- 当时不新增 `read_model.bank_flow_rule_batch_rows` 物理表，过渡期继续使用 `read_model.no_oa_bank_batch_rows`，并由 `payload.relation_mode=bank_flow_rule_batch` 及 relation-mode filter/index 隔离。该过渡判断已在 2026-07-01 被 `0082_bank_flow_rule_batch_storage.sql` 取代。
- 当时 `READ_MODEL_STORAGE_CONTRACTS["bank_flow_rule_batch"]` 显式指向 `read_model.no_oa_bank_batch_rows`，把共享物理存储从隐式 WIP 变成可验证合同；当前合同已更新为 `read_model.bank_flow_rule_batch_rows`。

测试覆盖：

- `tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_app_status_read_model_storage_contracts_are_declared`
- `tests/test_read_model_manifest.py`

## 2026-06-30 后端闭环与旧链路隔离

目标：把 `bank_flow_rule_batch` 从 no-OA route/readiness/producer/worker alias 中拆出，形成独立逻辑 API、read model、worker 和 operation barrier target。

关键决策：

- 保留 no-OA legacy 业务域本身，不删除仍被 `/api/no-oa-bank-batches/*` 使用的历史代码；删除的是 bank-flow 新链路对 no-OA route/event/scope/producer 的依赖。
- 新增 `routes_bank_flow_rule_batches.py`、`BankFlowRuleBatchApplicationService`、`BankFlowRuleBatchReadModelRefreshProducer`、`BankFlowRuleBatchReadModelRefreshService`、`BankFlowRuleBatchReadModelRepositoryPort`；`routes_no_oa_bank_batches.py` 不再处理 `/api/bank-flow-rule-batches/*`。
- `READ_MODEL_MANIFEST`、App Status read model registry、scope policy、runtime worker registry、RabbitMQ dispatch event 和 deploy env 示例均登记 `bank_flow_rule_batch` / `bank-flow-rule-batch` / `bank_flow_rule_batch.read_model.refresh`。
- Operation barrier 删除 `bank_flow_rule_batch -> no_oa_bank_batch` alias，bank-flow readiness/outbox/worker 缺失会真实返回 refreshing/blocked，不再被 no-OA fresh 状态掩盖。
- 当时批次物理存储仍使用 `app.no_oa_bank_batches` 与 `read_model.no_oa_bank_batch_rows`，必须继续用 `relation_mode=bank_flow_rule_batch` 隔离；该风险已在 2026-07-01 通过 `0082_bank_flow_rule_batch_storage.sql` 关闭。

测试覆盖：

- `tests/test_bank_flow_rule_batch_backend_boundary.py`
- `tests/test_bank_flow_rule_batch_routes.py`
- `tests/test_bank_flow_rule_batch_read_model_refresh_producer.py`
- `tests/test_operation_freshness_barrier.py`
- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_no_oa_bank_batch_routes.py`

## 2026-06-30 外部往来旧关系 requirement 同步修复

目标：

- 修复外部往来款借入/归还借款保存为不需要发票后，旧 `turnover:* manual_confirmed` active relation 仍停留在关联台未配对区的问题。

关键决策：

- 规则 UI 是 requirement owner，但 Workbench 分区事实源仍必须是 relation metadata。不能让 Workbench 在查询时读取当前 settings，因为已存在 relation 的 paired/open 判定必须可审计、可回放、可跨进程一致。
- 保存规则后，`NoOaBankBatchApplicationService.update_tag_selection(...)` 除同步 `bank_flow_rule_batch` relation 外，还会扫描 active `turnover:*` relation。若银行流水分类 code 直接命中规则，或属于外部往来/借入/借出/业务往来分类族且存在 `external_turnover` requirement，则通过 `WorkbenchRelationCommandService.update_relation_metadata_for_case_id(..., relation_mode=turnover_manual_closure)` 升级旧 relation 并写入 `requires_oa` / `requires_invoice`。
- 旧逻辑删除/隔离：普通 `manual_confirmed` 两栏 relation 不放宽；无匹配外部往来规则的 relation 不改；同步不直接写 relation 表，不依赖进程内 snapshot。

测试覆盖：

- `tests/test_no_oa_bank_batch_tag_selection_api.py::NoOaBankBatchTagSelectionApiTests::test_tag_rule_update_upgrades_legacy_turnover_relation_from_persistent_repository`
- `tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_update_relation_metadata_for_case_id_can_upgrade_relation_mode`
- `tests/test_workbench_relation_grouping.py`

验证命令：

- `PYTHONPATH=backend/src:. pytest tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_workbench_relation_grouping.py tests/test_no_oa_bank_batch_application_service.py tests/test_workbench_relation_command_service.py tests/test_workbench_relation_command_repository_adapter.py tests/test_turnover_workbench_integration.py tests/test_turnover_ledger_uow_contract.py -q`

未测风险：

- 生产需发布后执行一次同步，确认现存 `turnover:*` 旧关系被升级并触发 `workbench_relation` / `workbench` 刷新。

## 2026-06-30 submitted 列表 read model mode 修复

目标：

- 修复流水规则批量处理提交后，关联台已有 `bank_flow_rule_batch` relation，但页面“已提交”列表不显示该批次的问题。

关键决策：

- 根因是过渡期复用 `no_oa_bank_batch` 底座时，写侧已经使用 `relation_mode=bank_flow_rule_batch`，但构建/read model 回灌仍依赖旧 no-OA 判定。具体旧污染点包括：列表查询没有显式 relation mode I/O；active relation 回灌只识别 no-OA；服务内由 submitted batch 反推 relation fact 时把所有已提交批次硬编码为 `no_oa_bank_batch`。
- 修复边界放在服务和 read repository：`NoOaBankBatchService.build_batches`、`submit_selected_rows` 接受目标 `relation_mode`；批次 payload/read model row 携带 `relation_mode`；列表 API 将 `relation_mode` 传给 read repository；SQL read repository 用 payload relation mode 分区，旧缺字段行默认只归 `no_oa_bank_batch`。
- 服务内部旧逻辑删除/隔离：submitted/withdrawn/stale/superseded 批次保留只保留当前 refresh mode；submitted batch relation fact 只为当前 refresh mode 生成并继承 batch mode；no-OA legacy repair/migration 只能在 no-OA refresh 链路内工作，不能改写 `bank_flow_rule_batch` relation。
- 新增 `read_model.no_oa_bank_batch_rows` relation-mode 过滤表达式索引，保障过渡 read model 的 submitted/unsubmitted 查询性能。

测试覆盖：

- `tests/test_no_oa_bank_batch_service.py` 覆盖 `bank_flow_rule_batch` active relation 能投影成 submitted 批次，并且不会污染 legacy no-OA submitted 列表。
- `tests/test_no_oa_bank_batch_application_service.py` 覆盖应用层列表把 `relation_mode` 传入 read repository。
- `tests/test_no_oa_bank_batch_routes.py` 覆盖 `/api/bank-flow-rule-batches` 列表路由传入 `bank_flow_rule_batch`。
- `tests/test_no_oa_bank_batch_api.py` 覆盖 `/api/bank-flow-rule-batches/submit-selection` 提交后能在 bank-flow submitted 列表读到，并且不会进入 legacy no-OA submitted 列表。
- `tests/test_no_oa_bank_batch_read_model_refresh.py` 和 `tests/test_postgres_migrations.py` 回归 worker 与迁移清单。

验证命令：

- `pytest tests/test_no_oa_bank_batch_service.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_no_oa_bank_batch_routes.py tests/test_postgres_migrations.py`

未测风险：

- 未新增浏览器截图回归；发布后已触发 `no_oa_bank_batch/all` refresh，metadata 使用 `bank_flow_rule_batch_read_model_refresh`，生产 read model 已存在 `bank_flow_rule_batch/submitted` 行。

## 2026-06-29 文档/边界 slice

目标：

- 将需求从“免 OA 流水批量处理”重新定位为“流水规则批量处理”。
- 先沉淀模块边界、I/O、状态机、API 合同和 E2E 规格，不做实现代码。

确认决策：

- 页面不再只处理免 OA 流水，应覆盖所有需要按银行流水标签批量处理的流水。
- 标签规则抽屉左侧事实来自银行明细 active 标签，且左侧只读。
- 右侧只保留 `OA`、`发票` checkbox。
- 勾选表示进入关联台已配对区前必须具备对应 row type；空表示不需要该项。
- 新增/未配置标签默认 `OA` 和 `发票` 都勾选。
- 旧 `selected_tag_codes` 不作为新规则迁移来源；所有数据重新按新规则处理。
- 从本页面提交的批量银行流水进入关联台；超过 3 条银行流水默认折叠。
- 是否进入已配对区仍由 OA/发票 requirement 和实际 row type 是否满足决定。

本 slice 更新：

- 新增 `docs/modules/bank-flow-rule-batches/` 模块文档骨架。
- 计划同步模块索引、canonical facts、read model 合同、Workbench relation/reconciliation/bank details 边界和 API 契约。
- GSD 记录位于 `.planning/quick/260629-bank-flow-rule-batches-boundary/`。

风险：

- 当前代码和部分文档已经包含旧 no-OA 中间实现；implementation slice 必须先清理命名和边界，避免新旧规则同时生产写入。
- 若实现阶段允许跨账户、跨月或跨标签批量提交，需要重新扩展状态机和 relation metadata；当前文档保守约束为同月、同账户、同标签。

后续事项：

- 规则持久化当前使用独立 settings key `app_settings.bank_flow_rule_batch_tag_rules`；如未来升级到独立表，必须保留版本、审计、主动迁移和删除条件。
- 实现新 route/service/read model 后，再迁移导航和旧 no-OA route。
- 编写 Playwright E2E 前先把 `e2e-spec.md` 中的 Spec ID 映射到测试名。

## 2026-06-29 实现 slice

目标：

- 将用户入口改为“流水规则批量处理”，生产调用走 `/api/bank-flow-rule-batches`。
- 重做标签规则抽屉为紧凑 grid：左侧银行标签只读，右侧仅 `OA` / `发票` requirement checkbox。
- 新路径不接收 `selected_tag_codes`；保存只提交 `rules`。
- 提交选中流水写入 `relation_mode=bank_flow_rule_batch`，metadata 保留规则版本、tag code、OA/发票 requirement 和折叠提示。
- Workbench 根据 `requires_oa` / `requires_invoice` 判定 paired/open，大于 3 条银行流水折叠，并显示“流水规则批次明细”。

当前实现说明：

- 后端 route、application service、read model key、refresh producer、worker event、operation barrier、repository port、mutation persistence port 和 refresh persistence port 已作为 `bank_flow_rule_batch` 独立边界接入。
- 旧 no-OA route 仍保留兼容；新页面和 E2E 使用 bank-flow-rule-batches route，且 bank-flow route/service/refresh 不再 import 或继承 no-OA route/application/refresh 模块。
- 共享批次计算逻辑已放入中性 `bank_batch_application_service.py` / `bank_batch_service.py`；no-OA legacy 和 bank-flow 分别从自己的模块边界调用。
- bank-flow 页面不提供历史 no-OA 管理入口；普通查询、提交、撤回和刷新不读写 no-OA batch service。
- 新功能 mutation 和前端等待使用 `read_model_key=bank_flow_rule_batch`；operation barrier 直接读取 `bank_flow_rule_batch` readiness/outbox/worker，不再映射到 no-OA。

验证：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_workbench_relation_command_service.py tests/test_workbench_relation_repository.py -q`
- `npm --prefix web test -- --run RelationGroupGrid.test.tsx BankFlowRuleBatchPage.test.tsx BankFlowRuleBatchApi.test.ts App.test.tsx`
- `npm --prefix web run e2e -- e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium`
- `npm --prefix web run e2e -- e2e/permissions-role-matrix.spec.ts --project=chromium`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_operation_freshness_barrier.py tests/test_read_model_manifest.py tests/test_runtime_worker_registry.py -q`
- `bash scripts/verify.sh docs`
- `npm --prefix web run build`
- `git diff --check`

剩余风险：

- 独立 `bank_flow_rule_batch` 物理表已在 2026-07-01 `0082_bank_flow_rule_batch_storage.sql` 中拆出。
- “补齐 OA/发票后从 open 进入 paired”的完整跨页浏览器动作仍需后续接入真实补票/补 OA 流程测试。

## 2026-06-30 标签规则抽屉分组 UI slice

目标：

- 将“流水规则标签管理”右侧抽屉继续保持紧凑 xlsx/grid 形态。
- `收支类型` 按连续方向合并单元格，同一方向只显示一次。
- `流水主标签` 按主标签合并单元格，同一主标签只显示一次。
- 同一 `流水主标签` 下的不同子标签共享同一行组背景色；不同主标签使用不同背景色。
- `收支类型` 第一列压缩为固定窄列，并用方向底色/左侧色带强化 `支出`、`收入`、`全部` 分隔。

边界说明：

- 主要调整前端展示层 view model、table `rowSpan` 和样式。
- 标签 direction 读取兼容 `expense/outflow/debit/支出/支` 与 `income/inflow/credit/收入/收`；后端组装 active tag 时同 code 优先采用最新银行标签定义中的 direction。
- 不改变 `active_tags` 事实来源、`requirements_by_tag_code` 持久化、保存 payload、权限、read model、operation barrier 或 Workbench paired/open 判定。

验证：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_tag_selection_api.py -q`
- `npm --prefix web test -- --run src/test/BankFlowRuleBatchPage.test.tsx`
- `npm --prefix web run build`
- `npm --prefix web run e2e -- e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium`
- `git diff --check`

## 2026-06-30 已提交批次运行时同步修复

目标：

- 修复生产中列表显示 `bank_flow_rule_batch` submitted 批次，但详情/撤回返回“流水规则批次不存在”的问题。

关键决策：

- 列表以 SQL read model 为入口，详情/撤回仍必须操作 canonical batch service。对于由 worker 从 active relation 回灌出来的 submitted 批次，API 进程启动期快照可能晚于 worker 写入；因此 bank-flow 详情、撤回和 reset 入口先刷新 `relation_mode=bank_flow_rule_batch` runtime snapshot，再读取/修改批次。
- reset submitted 候选显式限定 `relation_mode=bank_flow_rule_batch`，禁止 legacy no-OA submitted 批次混入新页面重置链路。

验证：

- `tests/test_bank_flow_rule_batch_application_service.py` 覆盖 detail/withdraw 前刷新 runtime snapshot，以及 submitted 候选 relation mode 边界。

## 2026-07-02 批量持久化 I/O 优化

目标：

- 降低 `bank_flow_rule_batch.read_model.refresh` 在多 batch scope 下的 projection 写入 round-trip，避免逐 batch 两条 upsert 放大 worker handler 时间。
- 保持 bank-flow 与 legacy no-OA 的物理表、event 表、read model rows 完全隔离。

关键决策：

- `PostgresWorkbenchRepository.save_bank_flow_rule_batches*` 继续作为 bank-flow persistence owner，删除范围和 event 替换顺序不变。
- `app.bank_flow_rule_batches` 和 `read_model.bank_flow_rule_batch_rows` 改为批量 values upsert；payload 仍强制写入 `relation_mode=bank_flow_rule_batch`。
- 同步复用该批量 helper 优化 no-OA legacy persistence，但两者仍写各自表，禁止跨表 fallback。

验证：

- `tests/test_postgres_repositories_boundaries.py` 覆盖 bank-flow 专属物理表写入、禁止 no-OA 表污染、no-OA/bank-flow projection insert 不走逐行 `execute`。
- `PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_workbench_integration.py tests/test_bank_flow_rule_batch_application_service.py -q`

剩余风险：

- 本地优化尚未部署到生产；2026-07-02 生产 1s 高性能 baseline 中 `bank_flow_rule_batch` enqueue-to-fresh `5322.643ms`、handler `4543.139ms`，仍需部署后复测，并继续分析非写入阶段长尾。

## 2026-07-05 模块化 close 审计

目标：

- 使用 Grill me / Ponytail 对流水规则批量处理页面和上下游 I/O 做全量收口，移除 bank-flow 新链路里继续泄露的旧 no-OA 命名、source kind、错误码和文案。
- 不扩大到 no-OA legacy 模块自身退休；`/api/no-oa-bank-batches/*`、`no_oa_bank_batch` read model 和 legacy tests 仍归 `no-oa-bank-batches` 边界。

关键决策：

- `routes_bank_flow_rule_batches.py` 在 HTTP 输出边界翻译共享 bank-batch core 仍可能抛出的 legacy `no_oa_bank_batch_*` selection/relation/version/persistence 错误，公开 API 只返回 `bank_flow_rule_batch_*`。
- 当前 `workbench_relation_grouping.py` 不让 bank-flow 折叠摘要复用 no-OA 输出：bank-flow summary 使用 `source_kind=bank_flow_rule_batch_summary`、id prefix `bank_flow_rule_summary:`、`invoice_relation.code=bank_flow_rule_batch` 和 `流水规则` display tag，并过滤旧 `免OA` tag。
- 当前 `workbench_relation_grouping.py` 保留 legacy `no_oa_bank_batch` 的显式 requirement 合同；该保留只服务 no-OA legacy，bank-flow 缺失 requirement metadata 仍 fail closed 为需要 OA+发票。已删除的 `workbench_candidate_grouping.py` 不得恢复。
- `postgres_repositories/read_models.py` 把 `bank_flow_rule_batch_summary` 纳入 Workbench summary display-only source kind，避免摘要行污染真实银行明细计数、筛选和 read model I/O。
- `web/src/features/workbench/api.ts` 与 `ReconciliationWorkbenchPage.tsx` 按 bank-flow source kind / relation metadata 识别撤回链路，用户可见文案和撤回 reason 改为“流水规则批次”。
- `web/e2e/bank-flow-rule-batches-flow.spec.ts` 与 deterministic `apiMocks.ts` 移除 bank-flow 浏览器链路里的旧 no-OA fixture I/O：transaction id 改为 `bank-flow-rule-e2e-*`，batch id 改为 `bank-flow-rule-batch-e2e-*`，relation case id 改为 `bank-flow-rule-relation-e2e-*`，成本统计 fan-out 项目名改为 `流水规则手续费成本项目`，read model stale reason 改为 `bank_flow_rule_batch_*`。
- `docs/dev/testing-closure-dependency-map.md` 从旧 no-OA 页面入口改为 bank-flow 页面入口；no-OA 只登记 legacy API/read-model。

验证：

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_routes.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_treats_bank_flow_rule_batch_summary_source_kind_as_display_only -q`
- `python3 -m ruff check backend/src/fin_ops_platform/app/routes_bank_flow_rule_batches.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py tests/test_bank_flow_rule_batch_routes.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_workbench_sql_runtime.py`
- `cd web && npm test -- --run BankFlowRuleBatchApi.test.ts RelationGroupGrid.test.tsx`
- `cd web && npm exec tsc -- --noEmit`

## 2026-07-20 流水规则配置保存 O(1) 收敛（已由 2026-07-21 精确月份事务方案替代）

目标：

- 当时先将 tag-rules 保存从两次 active relation 全量扫描与逐 relation 写回，收敛为 settings/audit 单写和一次 bank-flow read-model refresh；后续精确月份方案保留了“零 relation 扫描”并替换 broad refresh。
- 保持批次列表、详情、提交、撤回、重置、no-OA、关联台和流水台账合同不变。

关键决策：

- formal relation 本身决定既有关系的 paired/unpaired；relation 中的 requirement metadata 是创建时审计快照，规则保存不再追溯改写。
- bank-flow 规则 canonical payload 只保留 `version` 与 `requirements_by_tag_code`；migration 0111 移除旧 selected shape，且不修改 no-OA payload。
- 同值保存是真正 no-op；2026-07-21 起实际变化只在资格集合变化时产生精确月份 durable refresh，资格中性变化为零 refresh。
- 删除旧 `_sync_bank_flow_rule_relation_requirements`、`_sync_turnover_rule_relation_requirements` 及其专用 relation 扫描/逐条写回 helper，不保留 fallback。

验证：

- 目标后端 160 passed + 15 subtests；关联回归 204 passed + 287 subtests；前端既有 3 files / 53 tests passed。
- 真实 PostgreSQL 空库应用 0001–0111，migration canonical/no-OA 隔离/幂等通过。
- 当时真实 PostgreSQL 20 次采样：no-op p95 `34.002ms`，actual change p95 `83.475ms`；该 release 的单个 all dirty scope 已由 2026-07-21 精确月份 scope 替代，数值只作为历史基线。
- 全量后端修正后为 4200 passed、64 skipped、716 subtests；剩余 historical ETC、Workbench repository/direct cost fan-out、cost fan-out matrix 与 cost-statistics fixture 问题可在未改动基线 SHA `3c80361db` 复现，不属于本项链路。
- SHA `182c29be4d6b1f9fd91001d88600fddd411bf2ef` 已部署为 `main-182c29be-20260720015418`；migration 0111 用时 42ms，API/dispatcher/22 workers active 且 worker workdir mismatch 为 0。
- 生产 20 次读取：页面壳 p95 `139.570ms`、GET p95 `258.567ms`、Page Audit p95 `370.022ms`；60/60 通过。
- 生产同值 PUT 20 次测量 p95 `275.186ms`、max `431.232ms`，version `11 → 11`。
- bank-flow、关联台、银行明细、turnover Page Audit 全部 `pass / fresh / drained`、0 issue；本子链路生产闭环完成。

## 2026-07-20 流水规则批量处理读写性能收敛

目标：

- 把 all/month 列表从双全量 row 读取、Python 分页和摘要收敛为固定查询数的 SQL 分页/聚合。
- 把批次详情的逐成员银行流水读取改为现有 canonical repository bulk I/O。
- 把 reset 的逐 relation cancel 与请求内逐月 rebuild 改为一次 scoped bulk cancel、一次原子 delta 保存和后台 scoped reconcile。
- 删除 bank-flow 运行链中的 no-OA schema/ID/display/error/idempotency/worker/route compatibility 路径，同时保持独立 no-OA legacy 模块功能不变。

实现决策：

- `BankFlowRuleBatchReadModelRepositoryPort.read_page(...)` 是页面列表唯一 read I/O：当前页 rows 使用 `LIMIT/OFFSET`，total 使用完整列表筛选，summary 使用 month/account summary filter 聚合，source-version/readiness proof 独立返回；前端默认 page size 从 200 收窄为 50。
- `ImportNormalizationService.list_transactions_by_ids(...)` 复用 `PostgresCoreRepository.list_bank_transactions_by_ids(...)`，按输入 ID 去重并恢复稳定顺序；bank-flow detail/selection 不再调用逐 row getter。
- reset 领域状态仍逐批校验 version，但 relation command 只调用一次 `cancel_relations_by_case_ids(...)`；persistence 显式接收 `changed_batch_ids`，即使历史 active relation 已缺失也不会漏写 withdrawn batch。HTTP 请求不调用 `refresh_batches(...)`。
- submit/withdraw/reset command 成功后前端先更新本页 committed state并解除前台阻塞；`bank_flow_rule_batch` freshness wait 与 reload 作为后台 reconcile，完整跨页 targets 继续通过既有 domain event 发布。
- bank-flow service 使用独立 schema version、新 batch ID prefix、正式 display tag、错误码和 idempotency namespace；route legacy error translation map 已删除。共享 core 的中性 bank rows/source versions/stale reasons 是正式入口，no-OA 名称只保留为 legacy 模块 wrapper。

验证证据：

- 目标及隔离回归 459 tests 通过；前端 BankFlowRuleBatch page/API 43 tests 通过。
- Chromium `bank-flow-rule-batches-flow.spec.ts` 最终 9/9 通过；reset 写后不自动触发下一批 detail GET，后台重读稳定使用 unsubmitted/page 1。
- 真实本地 PostgreSQL 空库应用全部 migrations 后，paged query + aggregate summary integration test 通过；验证 draft presentation、pagination total 和完整 summary 金额/计数。
- architecture guard 固定 bank-flow route/application/refresh wrapper 不得出现 `no_oa`、`NO_OA`、`免OA` 或 legacy error map。
- 最终唯一 SHA、部署 release、生产读/写性能、Page Audit 和 worker drain 证据在本次统一发布验证完成后补录。

生产首轮验证与补充收敛：

- release `main-a3a331b5-20260720030257` 首轮 20 次读测量中，页面壳 p95 `108.923ms`、Audit p95 `265.977ms` 已通过；all 列表从基线 `965.789ms` 降到 `539.327ms`，但仍未达到 `500ms` 门槛；2026-07 月列表 p95 `720.336ms`，且首次请求真实经历一次 stale/enqueue。因此本阶段没有提前关闭。
- runtime 指标显示列表数据库 p95 约 `80.504ms`，而 server p95 约 `606.884ms`，剩余瓶颈主要在请求内 Python source-version/presentation，而不是 SQL 分页本身。
- 删除列表热路径中重复的 relation source-version 预加载；月份 expected-source read 本身已经通过同一 facade 读取该 scope，旧调用造成一次重复 I/O。
- shared source-version port 现在按显式 relation mode 传递 `bank_flow_rule_batch_source_version_precheck`；bank-flow API/worker 不再把旧 `no_oa_bank_batch_source_version_precheck` reason 污染到 dependency I/O，no-OA legacy 默认值只保留在自身调用链。
- 当前页 50 个 batch 与约 40 个 summary category 过去会分别调用 `tag_dictionary_payload()`，每次 deep-copy 整份分类字典；现在每个请求只建立一次 definition index 并复用，不新增跨请求 payload cache。
- `BankTransactionCategoryService.snapshot_version()` 缓存与完整 snapshot 序列化完全相同的 SHA-256，只在分类或 tag dictionary 实际变更时失效。20,000 条合成记录中，旧 copy+hash 约 `212.869ms`，首次无 copy hash 约 `190.723ms`，后续读取约 `0.005ms`；该优化保持 hash 合同不变，不改变其它页面数据。
- 目标与 no-OA 隔离回归 `103 passed`，lint 通过；必须部署新 SHA 后重新执行相同 20 次生产读测量，未达门槛不得关闭。

生产第二轮与 durable freshness 收敛：

- SHA `1be049026` 部署为 `main-1be04902-20260720032126` 后，all 列表 p95 降至 `244.072ms` 并通过；month 列表 p95 为 `541.278ms`，20/20 fresh、零 enqueue，但仍高于 `500ms`，阶段继续保持 open。
- runtime 证明 month 与 all 的主要差异是每次 month GET 额外跨读 bank-detail/workbench-relation live source versions，查询数 p95 `15`；这绕过了页面 repository 的 durable freshness 边界，并在每次只读请求重复 worker 才需要的 dependency precheck。
- 列表删除 live dependency source-version读取，改为只消费 `read_page(...)` 返回的本模块 durable dirty/readiness/source-consistency proof。canonical writer仍必须事务内写 dirty/outbox，worker仍执行完整 source-version precheck；不存在“事实变了但页面继续伪装 fresh”的 fallback。
- repository 对 fresh 月份 scope 的多个 distinct source versions返回 `schema_mismatch`，API返回明确 stale reason并入队 scoped refresh；all scope允许不同月份具有不同 source versions。
- 同时删除 month readiness 对同一 dirty scope 的重复查询。真实 disposable PostgreSQL应用 0001–0111 后，SQL分页/聚合/混合 source-version fail-closed integration test通过；目标测试中的既有 cost-statistics fan-out fixture failure不属于本改动且未放宽。

最终生产读验证与写门禁：

- SHA `a5e5b795a` / release `main-a5e5b795-20260720032959` 的最终 20 次生产采样全部达标：页面壳 p95 `130.237ms`、all list p95 `272.284ms`、2026-07 month list p95 `260.943ms`、Page Audit p95 `322.560ms`；80/80 成功，list 40/40 fresh 且零 enqueue。
- 1-row 与 33-row 详情各 20 次测量，p95 分别为 `175.940ms` 与 `337.446ms`；`bank-flow-rule-batches`、关联台、银行明细、流水台账、成本统计五个 Page Audit 均 `pass / fresh / drained / ready`、0 issue。
- 生产 submit/withdraw 可逆样本没有被擅自执行：首次 mutation 的强制 `app-health-operations` 预检发现 `tax-offset`、`input-invoice-usage`、`output-invoice-collections`、`settings` 四个范围外页面已有 integrity issue，并在写前 fail closed。为保持模块隔离和九页面串行，当前模块不跨界修复、也不绕过门禁；该写证据在主控流程最终系统门、全局预检恢复 pass 后补做。

## 2026-07-21 双 false 资格规则与生产刷新验证

- 新未提交资格统一为 active tag 且 `requires_oa=false`、`requires_invoice=false`；缺失 requirement fail closed。左侧未提交主/子标签只来自该集合，submitted/withdrawn 标签与计数继续来自 read model 中冻结的实际历史。
- 规则保存先比较资格集合的对称差；只对变化 tag 使用一条集合 SQL 解析 canonical bank-detail 与现存 draft 批次的精确月份。PostgreSQL 下 settings version CAS、无关 settings 字段合并、多月份 dirty/outbox 在同一事务提交；资格中性保存零 refresh，完全同值为零写入，空月份不 fallback `all`。
- 最终生产 release `main-ca22f3be-20260721155950` 已激活，schema version `118`。首次 7 个月 rollout 校正后，2026-01 至 2026-07 的未提交结果均无不合格 tag；2026-07 submitted 历史仍为 2 个 batch，未受当前规则隐藏。
- 生产验证发现共享 worker 没有兑现 manifest 已声明的 `force_refresh` 合同：运维强制事件仍会进入 unchanged skip。现已删除该旧行为；顶层或 metadata 的 `force_refresh=true` 都绕过 skip，仍按精确 month scope 和原 source-version/persistence 边界重建。
- 稳态真实强制重建验证：2026-01 至 2026-06 enqueue-to-fresh 为 `402.6–861.0ms`；2026-07 连续 10 次为 median `484.9ms`、p95/max `883.8ms`，达到当前月 p95 ≤ 1s、历史月份 p95 ≤ 5s 的目标。发布重启后首轮冷样本有长尾，因此生产监控仍保留长窗口告警，不用冷样本替代稳态 SLO 结论。
- 最终 release 再次强制刷新 2026-07：worker 处理 `677.275ms`，stale/unavailable 均为 0，outbox pending/publishing/failed 均为 0；从本地 SSH 运维命令发起到公网 barrier fresh 共 `2572.9ms`，其中远程 enqueue 命令往返 `1785.1ms`。
- 最终 release 的 10 次同值 PUT 全部保持 version `11`、零 affected scope、零 enqueue，median `178.5ms`、p95/max `208.5ms`；10 次 2026-07 GET 全部 fresh，median `186.1ms`、p95/max `272.1ms`。
- 生产跨页只读 Audit：`bank-flow-rule-batches`、`bank-details`、`turnover-ledger`、`reconciliation-workbench`、`settings` 全部 `pass`、0 blocking issue。历史 `0111` 只修改 formal rule payload 导致 settings formal/raw 审计不一致，已由 `0118` 在 33ms 内只同步 raw 镜像，canonical rule value、version 和 OA/发票开关均未改变。
- 本项相关后端回归 `421 passed + 76 subtests`，迁移/settings Audit/repository 回归最终 `120 passed + 19 subtests`；前端全量 `73 files / 862 tests`、构建和 Chromium bank-flow `9/9` 通过。全仓后端基线 `4245 tests` 仍有 8 failures + 3 errors：6 个 cost-statistics fixture、3 个 no-OA legacy 历史折叠、1 个 write-operation impact matrix，以及 1 个 local read-model API harness 缺少 bank-flow SQL repository；除最后一个既有本地 harness contract 外均不在本模块文件范围，生产 PostgreSQL route/Audit 已通过。

## 2026-07-21 canonical relation 占用与页面 Audit freshness 收敛

- 根因不是双 false 候选规则本身持续算错，而是 bank-flow worker 用 Workbench relation read model 生成候选；canonical relation 已提交后，该依赖投影仍可能暂时保留旧关系视图，导致旧 draft 被发布到未提交列表。提交入口随后读取到 canonical 新关系并正确拒绝，因此暴露 `bank_flow_rule_batch_selection_occupied`。
- worker 和 submit-selection 统一复用现有 PostgreSQL `workbench_relation_source_bundle_from_source(...)`：一次查询按目标 bank row ids 返回 canonical active relation rows 与同一 snapshot source versions。worker 先读 scope bank rows，再读 bundle；unchanged 才跳过，重建时才加载分类。worker 启动不再加载全量 relation snapshot，也不再接入 relation read-model facade。
- projection schema version 升级为 `2026-07-bank-flow-rule-batch-v2`，确保旧 v1 页面投影无法冒充 fresh。列表响应增加稳定 `read_model_version`；前端在版本、status 或手工刷新 token 变化时取消在途 Audit 并清除旧结果，写后本地状态立即标记 refreshing。
- Audit contract 升级到 v26，并在既有 batch/relation proof 内补充 draft member 与其它 active relation 的跨 case overlap；旧 Audit 之所以通过，是因为只校验同 case relation 的状态/成员 equality，没有证明未提交成员未被其它 case 占用。
- `bank_flow_rule_batch_selection_occupied` 明确映射 HTTP 409；页面 linked 行只展示“已有未撤回关联”及 OA/发票计数，内部 relation case id 保留为机器冲突证据但不渲染。

生产闭环：

- SHA `fc5babd5b16c427ca7bf027e2af81f9b980188e1` 已部署为 release `main-fc5babd5b-bank-flow-audit-202607211740`；`/health/ready` 证明 runtime commit、source root 和 release metadata 一致，schema version 为 118，API、dispatcher 与 22 个登记 worker 全部 active。
- 通过正式 durable gateway 对 `bank_flow_rule_batch=2026-07` 执行 `force_refresh`，事件 `3b5bc119-ba56-436b-984e-9efbba2cbcbd` 完成后页面为 fresh。未提交由 4 批降为 3 批；手续费未提交由 1 批/13 条降为 0，手续费 5 个已提交批次/28 条历史仍保留；全部已提交历史为 10 批/38 条。
- 该页 Page Audit v26 返回 `pass / fresh / drained / ready`，0 blocking issue、0 backlog；单次列表 204.8ms、Audit 539.5ms。正式 20 次只读采样中列表 p50/p95/p99 为 `129.510/199.007/219.358ms`，Audit 为 `248.811/418.376/584.328ms`，40/40 成功，列表 20/20 fresh、零 enqueue。
- 生产 Chromium DOM 验证未提交 3、已提交 10；两区均不含 `bank_flow_rule_batch_*`，已提交详情显示“已有未撤回关联”，无操作失败、console error 或 page error，完整交互 1.45s。
- 17 页 System Audit 的 freshness/queue 为 `fresh / drained`，但仍有 5 个本模块范围外的既有 integrity 阻断：tax-offset source version、pending-invoices row count、input-invoice-usage relation version、invoice import 历史孤儿/证据、ETC import 历史状态。本次未修改这些模块的 service/repository/worker I/O，未越权修复，也不把系统级结果声明为全绿。

## 2026-07-22 Turnover requirement 旧回写链删除

- legacy no-OA rule-save service 不再扫描 active relations，也不再调用 relation metadata update 去追溯改写 `turnover_manual_closure` 的 OA/发票要求；相关 `_sync_turnover_rule_relation_requirements`、tag mapping、比较 helper、常量和测试语义已删除。
- 当前 bank-flow rule save 继续只维护 canonical 规则和自身受影响月份 refresh；Turnover 新 relation 在创建事务中从一次 canonical rules payload 冻结 requirement，存量缺快照 relation fail closed 并只允许受控 repair。
- 本次不改变 bank-flow API、settings DTO、read model、worker、queue、页面或性能合同；零扫描回归防止重新引入跨模块 relation 写 I/O。

## 2026-07-27 页面 canonical 直读

- 页面列表、汇总与详情改为页面专属 PostgreSQL query repository；列表在一个显式 `REPEATABLE READ READ ONLY` snapshot 内固定执行 2 次 SELECT（规则设置 + 分页/总数/汇总组合查询），详情固定执行 4 次 SELECT。
- 页面请求只读取 `app.bank_flow_rule_batches`、`app.bank_flow_rule_batch_events`、canonical 银行/分类/规则事实和 `status='active'` 的 `app.workbench_pair_relations`；不读取 `read_model.bank_flow_rule_batch_rows`、no-OA legacy 表或 Workbench relation projection。
- 前端删除 freshness/status/version、refresh enqueue、202 与 polling 语义；submit-selection、submit、withdraw、reset 和规则保存成功后均只重新执行一次当前列表 GET。
- disposable PostgreSQL 在 projection 表保持空集时验证 2 个批次的列表、汇总、详情与 active relation 一致性。10,000 批次、page size 200 的本机热查询 20 次样本：列表 p50 `780.802ms`、p95 `1621.686ms`、max `2007.049ms`；详情 p50 `15.408ms`、p95 `17.266ms`。列表组合 SQL 的 `EXPLAIN (ANALYZE, BUFFERS)` execution 为 `397.194–449.873ms`，shared read blocks 为 0。
- 查询已复用现有主键、legacy id、分类和 relation GIN 索引；当前证据没有证明需要新增索引或 migration。本机样本不替代主控合并后的生产 HTTP 测量。

## 2026-08-10 撤回后重提 500 根因修复

- 页面 canonical 列表和详情数据正确；建设银行 20 条候选是三个 withdrawn 批次流水的精确并集，不存在 active relation 占用或半提交。
- 根因是 relation command 按 `row_ids + case_ids` 查询 active relation 时，`PostgresStateStore.load_active_workbench_pair_relations_for_row_ids(...)` 包装层只接受 `row_ids`，运行时在原子写事务前抛出 `TypeError`。
- 修复只补齐包装层已有契约并转发 `case_ids`；不改变候选分组、API、SQL、数据库 schema、relation mode 或最终 `SERIALIZABLE` 原子写边界。
- 删除前端无调用且后端无 route 的旧 `submitBankFlowRuleBatches` 与 `/api/bank-flow-rule-batches/submit` 合同；保留普通流水 `submit-selection` 和内部往来 `/{batch_id}/submit`。
- 完整回归覆盖三个同账户手续费批次分别提交、撤回、自然归并为一个候选并重提；生产发布后以当前 20 条真实候选执行一次受控写验证并记录性能、批次、关系、历史和审计结果。

# 2026-08-10 “全部”批次范围 canonical 修复

- 根因是页面省略月份后，canonical repository 仍把候选范围初始化为 `and false`；正式 submitted 批次因此在空候选集合上被错误判为 stale 并从公开列表过滤，withdrawn 历史则继续存在，形成“全部只剩历史”的假空结果。
- 修复只删除该旧空范围分支：精确月份继续使用 ±2 天边界窗口，省略月份时在同一 `REPEATABLE READ / READ ONLY` snapshot 内一次集合读取全部 non-deleted 银行流水、当前分类、正式历史和 active relation；共享 live builder、状态校验、排序、summary 与分页保持唯一实现。
- 不新增前端月份 fan-out、后端逐月 N+1、缓存、read model、worker、表或兼容 fallback；“全部”继续由前端省略 `month` 表达。
- 回归保护跨月 draft + submitted 同时可见、固定查询数、API 参数合同和页面从当前月份切换“全部”后的请求；发布必须以生产数据一致性和 p95 性能复测为门禁。
