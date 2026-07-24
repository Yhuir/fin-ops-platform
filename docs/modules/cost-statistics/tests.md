# 成本统计测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 2026-07-24 - 首次访问同时收敛 Workbench 与 Cost

- Service/read model：`tests/test_cost_statistics_sql_runtime.py` 证明一次 month/all 页面访问会为每个 stale Workbench 月份同时 ensure 对应 Workbench scope 与同 project scope 的 Cost child；Cost projection 在任何 payload I/O 前比较 canonical Workbench expected versions 与 active generation，不匹配时 fail closed。`tests/test_cost_statistics_postgres_integration.py` 保护默认 provider 的真实 PostgreSQL 查询和同一 fail-closed 合同。
- Worker/manifest：`tests/test_runtime_worker.py` 与 `tests/test_read_model_manifest.py` 证明标准化 `workbench_read_model_not_fresh` 只补投同月 Workbench，并把 Cost event 短延迟 defer；不发布半成品、不需要第二次页面访问。
- 回归：`tests/test_read_model_architecture_guards.py` 继续要求 access enqueue 走共享 gateway；普通 relation 写零 fan-out、Bank Detail profile 与 parent rollup 合同不变。生产 `<3s` 仍以候选部署后的 test-owned fixture 为最终门禁。

## 2026-07-24 - 全流水视图复用 Bank Detail 与旧复制表删除

- Business/read boundary：`time|bank_tag` 的 explorer、transaction detail、export-preview/export统一使用 `dependency_profile=bank_flow`，只等待 Bank Detail exact month scopes并直接查询 `read_model.bank_detail_rows`；`project|bank|expense_type` 保持 Workbench→Bank Detail→Cost OA allocation profile。global statistics可独立 non-fresh，不能阻塞已 fresh rows。
- API/frontend：transaction detail现在必须携带 `view + scope + project_scope`；后端用同一 scope约束 freshness gate与 point SQL，防止跨月绕过 freshness。缺失/非法参数返回400，profile non-fresh返回409。前端从当前 explorer state透传三项参数；export final recheck复用首次查询的同一 profile。
- Old-path deletion：projection/repository/query/Audit不再写或读 `cost_statistics_bank_flow_rows`，也不生成 `bank_flow_time_rows/bank_flow_summary` legacy payload。migration `0123_drop_legacy_cost_statistics_bank_flow_rows.sql` 删除物理复制表；历史 0107/0108 migration保留不可变，但 production runtime禁止 dual-read、fallback和第二 writer。
- Service/read-model/Audit：`tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_page_audit.py`、`tests/test_cost_statistics_postgres_integration.py` 覆盖 profile gate、Bank Detail直接查询、Cost conditional publish只替换 allocation rows、parent统计和Audit exact-set；`tests/test_postgres_migrations.py` 覆盖0123存在及执行后旧表缺失。
- App Health fixture：测试不再依赖已删除的写后 fan-out或手写空 Cost parent，而是通过正式 gateway→worker访问链建立 Workbench、Bank Detail、Cost与OA fresh状态；真实 PostgreSQL System Audit `16/16`。
- 本轮定向结果：真实 PostgreSQL相关 backend组合 `231/231`；write-operation runner单元 `55/55`；Cost页面组件 `32/32`；前端 production build成功。未运行183项浏览器套件，也未运行无意义全量CI。候选部署后的 test-owned可恢复 fixture、所有相关页面访问收敛与生产p95/p99仍是最终门禁。
- 七类决策：1 source-version/profile与标签/金额业务合同、2 query/repository/Audit、3 transaction/explorer/export API、4 read model/migration/worker、5 Cost页面参数与non-fresh交互、6 write→零fan-out→按访问收敛、7 Workbench/Bank Detail/Cost/OA/System Audit回归全部适用并有对应定向证据。

## 2026-07-24 - access-time `all` 快速 refreshing 与 sibling month 并行

- Service/API contract：`tests/test_cost_statistics_sql_runtime.py` 证明 `scope=all` 发现 durable outbox active dependency 后立即返回现有 `refreshing` envelope，不执行 Workbench canonical bulk proof、Cost dependency gate、payload read 或重复 enqueue；没有 active event 时仍走完整 fail-closed proof。month scope 不使用该短路，保留“当前 rows fresh、全期间 statistics refreshing”的既有合同。
- Repository/PostgreSQL：同文件锁定 repository port 与 event-type-first active outbox SQL；`tests/test_cost_statistics_postgres_integration.py` 在真实临时 PostgreSQL 证明只返回 `pending/processing` 且与当前 Cost project 或全局 Workbench/Bank Detail 相关的 dependency，排除 done 与其它 Cost project。
- Worker/deploy/regression：`tests/test_runtime_worker_registry.py` 证明 Workbench primary 唯一 claim `all`、secondary 只 claim month，Cost 两个 required PostgreSQL consumer 使用独立 worker kind；`tests/test_deploy_runtime_examples.py` 证明 registry 派生 manifest/env，不新增手写部署清单；`tests/test_postgres_migrations.py` 与 disposable PostgreSQL integration 保护 0122 索引。
- 已运行定向结果：不含浏览器 183 suite 的 backend contract `182 passed`；真实临时 PostgreSQL `6 passed`，数据库自动删除。按用户指示不手动触发、不等待与本改动无关的耗时 CI；发布前只补 lint/docs/diff/边界定向门，发布后以 test-owned confirm→withdraw、恢复、worker heartbeat、页面 access-to-fresh p95/p99 与 System Audit 为最终证明。
- 七类决策：1 业务规则未变，不新增 business-core 测试；2 service、3 既有 API refreshing shape、4 read model/worker、6 生产可逆写→访问→恢复、7 Cost/registry/migration/deploy 回归适用。5 frontend 不适用，因为页面组件、交互与 HTTP shape 未变。

## 2026-07-24 - normal parent 精确收敛与 force 全量隔离

- Service/worker：`tests/test_cost_statistics_sql_runtime.py` 证明普通 API parent 与 `cost_statistics_shard_converged` parent 直接重建廉价 rollup，绝不调用已删除的 readiness shard discovery；显式 force parent 仍枚举全部当前月份、向每个 child 传播 `force_refresh`，并等待后续收敛。
- Explicit operations：`tests/test_cost_statistics_runtime_service.py` 与 `tests/test_cost_statistics_derived_lifecycle_executor.py` 证明 global invalidation、settings reset 和无 scope 的显式 maintenance 都把 parent 标记为 force；月度精确 invalidation 不会升级为全量。
- Old-path deletion：`CostStatisticsSqlProjectionBuilder.missing_or_stale_cost_statistics_shards(...)`、Cost relation-delta handler/projection/repository publisher 和 write-trace causal smoke均已删除。生产代码不再从 `read_model.app_status_readiness` 推导 Cost child jobs，也没有隐藏的行级 delta兼容路径；query repository 的 durable dirty + child lineage gate仍是唯一精确 freshness owner。architecture guard要求这些符号在 production runtime保持为零，SLO audit只把旧 reason当作禁止回归 signature。
- 七类决策：1 无新业务规则；2 service/显式 lifecycle、4 read model/worker、6 生产 test-owned confirm→withdraw、7 Cost/Workbench/queue/Audit 回归适用。3 API shape 与 5 frontend 未变，不新增对应测试；生产 E2E/SLO 和 System Audit 是最终门禁。

## 2026-07-22 - OA 配对流水漏统修复与 v11 重投影

- Business core：`tests/test_cost_statistics_sql_projection_rules.py` 覆盖旧 OA 排除标记/借还款不再否决、缺失维度 fallback、一银行多 OA 6万/4万精确拆分、金额不闭合不推断、多银行不拆分、active completed project 与银行原生月份去重。
- Service/read model：`tests/test_cost_statistics_sql_runtime.py` 覆盖 `paired`/`unpaired` 正式 relation、candidate 排除、full/delta 共用投影、stable row key、allocation row count 与唯一 transaction count、单 statement tag-selected 标题数、detail allocations、v11 source versions、CAS publish/parent rollup 回归。
- API/frontend：`tests/test_cost_statistics_api.py` 保持 explorer/detail/export/tag-rules 状态与权限合同；`web/src/test/CostStatisticsApi.test.ts`、`CostStatisticsPage.test.tsx` 覆盖 additive mapping 与详情拆分展示，loading/error/freshness/关闭交互保持。
- Audit/integration：`tests/test_cost_statistics_page_audit.py` 锁定正式 relation 两区、银行原生月份、exact split/full fallback/stable row key 和四组只读 query budget；`web/e2e/cost-statistics-relation-fanout.spec.ts` 覆盖 candidate 不入成本、OA+bank 无发票正式关系确认后进入成本的全链路。
- Regression：成本之外的 Workbench、Bank Detail、Tax Offset、Pending Invoice、OA Pending、read-model gateway/worker/manifest 与平台边界测试必须随全量 backend/frontend/e2e 验证复跑；本变更不新增表、migration、endpoint、queue、worker、依赖或共享 UI 状态。

## 2026-07-18 - relation identity 与 downstream lifecycle 最终门

- Cost projection：`tests/test_cost_statistics_sql_runtime.py` 锁定 active/cancelled/mixed delta 的 affected group 与 replacement row 都使用 `case:<case_id>`，同时保留 transaction-target 原子替换、完整 metadata 和 parent fan-out 回归。
- Invoice lifecycle：`tests/test_invoice_lifecycle_sql_projection.py` 证明只读取 expense/income exact fresh pending shards并传播对应 source versions；`tests/test_search_pending_sql_runtime.py` 证明查询使用 `scope_month + direction`、dirty 时不读取 rows；`tests/test_invoice_lifecycle_postgres_integration.py` 在真实 PostgreSQL 验证 scope/source/payload合同。
- 旧链与隔离：`tests/test_platform_runtime_boundary_guards.py` 禁止 invoice lifecycle 重新 import/call `SearchPendingSqlProjectionBuilder._pending_invoice_rows(...)`，并要求窄 repository port 与 fail-closed marker。无 API、前端、schema、registry 或其它页面 read model 变化。
- 七类决策：1 identity/invariant、2 projection/repository、4 read model/worker、6 relation→Cost/OA Audit生产流、7 architecture regression适用；3 API shape 与5 frontend未变，不新增对应测试。发布后仍须对三个页面执行操作前后 Audit 和生产 SLO。

## 2026-07-17 - unchanged 版本确认与 month/parent 收敛

- 生产故障：可逆 relation 写入后，成本月份内容来源版本已经与当前 Workbench/Bank Detail 一致，但旧 unchanged 路径返回通用 `skipped` 且没有推进 `published_source_version`；readiness 忽略该事件，parent 又因 month 非 fresh 反向补投，形成持续自激队列。
- Service/业务状态：`test_cost_statistics_sql_projection_skips_unchanged_month_scope_without_workbench_scan` 与 processing 变体证明 exact source versions 只跳过重建，仍必须成功确认当前 event 版本并返回 `published=true/skipped_rebuild=true`；race 测试证明确认失败返回 unpublished，不能完成或 fan-out。
- Repository/read model：新增成功与 dirty/source race 测试，锁定一事务内 dirty row `FOR UPDATE`、event 版本相等、parent JSONB source versions 精确相等，只更新发布版本且不执行 payload/row SQL。port/manifest/physical-owner 测试登记唯一成本专属 I/O。
- 隔离/回归：read-model 与 platform architecture guards 全量证明未改共享 queue/readiness、其它页面 repository 或 API；无 migration、表、缓存、worker、HTTP/UI 变更。
- 七类决策：1 状态竞态、2 service/repository、4 read model/worker、6 projection→repository→handler 现有集成、7 architecture regression 适用；3 API 与 5 frontend 不适用，因为 HTTP shape和 UI 未变。生产 queue drain、三页连续 Audit、混合负载与 p95/p99 属于发布后门禁。

## 2026-07-16 - 统一发布准备最终验证

- 旧链门禁：`tests/test_platform_runtime_boundary_guards.py` 同时禁止旧 root/project route、full-view query/repository/manifest、warmup runtime/server/registry/type、projection Redis兼容参数和 worker注入回归；whole-repo生产路径扫描为零。
- API/read model：当前 explorer、export-preview/export、transaction和tag-rules合同继续覆盖 fresh/non-fresh、ETag、分页、限流、点查、权限、durable refresh和source-version CAS；删除旧 contract 后没有兼容 endpoint、fallback或第二 worker。
- Frontend/E2E：`CostStatisticsPage` 31项组件测试覆盖 initial/loading/error/refreshing/stale/fresh、轻量 inert锁、scope隔离、五视图、详情、导出和规则；完整 Playwright覆盖成本 relation/import/settings fan-out、非fresh防伪成功、权限与其他页面回归。
- 全量结果：`bash scripts/verify.sh lint`；无外部数据库的 `bash scripts/verify.sh backend` 为 `4078 passed, 35 skipped`；`bash scripts/verify.sh frontend` 为 `72 files / 855 tests` 且 production build通过；`bash scripts/verify.sh e2e` 为 `179/179 passed`；`bash scripts/verify.sh docs` 与 `git diff --check` 通过。
- 真实数据库：创建 visibly disposable临时 PostgreSQL，设置显式host的 `FIN_OPS_TEST_DATABASE_URL` 后再次运行完整 backend；实际应用 `0001–0107`，结果 `4104 passed, 6 skipped`，临时库自动删除。首次无host URL被migration安全阀拒绝，只修正命令后重跑，未放宽安全断言。
- 七类决策：1 业务口径未变，不新增规则测试，但既有金额/方向/归因回归全跑；2 service；3 API；4 read model/cache/job；5 frontend interaction；6 relation/import/settings跨模块E2E；7 full regression均适用并已覆盖。
- 发布后风险：本地闭环不等于生产性能已验证；备份、旧lane drain、migration、rehydrate、Page Audit、canary、真实p95/p99和三页面混合负载隔离仍必须在统一部署窗口执行。

## 2026-07-16 - GSD 05-20 cost/tax projection owner 拆分

- 影响范围：成本与税金 projection 文件所有权、生产 worker import、直接 runtime/architecture tests 和模块文档；不改 API、UI、read model数据、schema、queue、registry或业务规则。
- Business/service：成本 projection rules、SQL runtime和API回归继续覆盖原归集、source-version、CAS发布、分页/导出与当前 explorer/export/transaction 合同。
- 隔离：`test_cost_and_tax_sql_projection_owners_are_split_without_legacy_module` 锁定旧文件不存在、两个新 owner互不包含对方 builder/模块前缀、worker只使用明确新 import且无兼容路径；税金 SQL runtime 同轮通过，证明 Tax Offset行为零变化。
- 七类决策：1、2、3、4、7适用；5前端未改不适用；6无新业务流，以两个 projection→repository及worker assembly现有集成覆盖。真实生产 worker仍待统一部署后验证。

## 2026-07-16 - GSD 05-19 worker unchanged metadata-only I/O

- 影响范围：成本 projection、repository port/summary SQL owner/manifest、直接 boundary/runtime tests 与文档；不改 API shape、route、前端、queue/worker wiring、schema/index、Tax Offset 或其他页面。
- Business/service：`test_cost_statistics_sql_projection_skips_unchanged_month_scope_without_workbench_scan` 与 dirty-processing 回归锁定 source_versions exact equality、entry/row count 和原 skip envelope；fixture 已删除 full-view method，只暴露 `get_cost_statistics_scope_metadata(...)`。
- Repository/read model：`test_repository_reads_cost_statistics_scope_metadata_without_payload_or_row_scans` 锁定一次 parent point query、精确三字段、零 payload/join/dirty/dependency SQL 与零 `fetch_all`；port/manifest/physical owner 测试登记窄 I/O。
- Legacy/隔离：`test_cost_statistics_projection_unchanged_check_reads_scope_metadata_only` 和 cost boundary guard 禁止 projection 恢复 full-view/payload 读取；owner 证明与生产只读零 warmup job 证据已关闭删除门，旧 root/project HTTP、full-view 和 warmup 链必须保持零生产实现。
- 七类决策：1 exact equality/skip、2 service/repository、3成本 API回归、4 read-model/worker、7 existing regression适用；5 frontend不适用；6 无新跨模块业务流，以 projection→port→repository contract集成覆盖，真实 worker/生产量级留到统一部署后。
- 未测风险：尚无真实数据 EXPLAIN、worker drain 或 production write-to-fresh p99；本轮不部署，统一发布后补证据。

## 2026-07-16 - GSD 05-18 成本 Audit exact-set 单语句收敛

- 影响范围：仅 `cost_statistics_page_audit.py`、成本 Audit 直接测试与模块文档；不改 API、read-model 发布、worker、前端、共享 Audit、Workbench/Bank Detail proof owner 或其他页面。
- Business/service：`test_exact_set_proofs_use_one_query_and_preserve_each_issue_contract` 锁定 scope row count、missing scope、duplicate identity、canonical expected-set 四类 issue code/details、四个独立 `limit`、精确参数顺序与唯一 `cost_exact_set_proofs` I/O；同时禁止恢复 `bank_transactions.id::text OR legacy_mongo_id` 旧扫描，并锁定 UUID 主键/legacy 唯一键 equality probes 与同一行去重条件。
- 性能/旧代码：`test_clean_audit_preserves_contract_and_active_relation_query_budget` 把 active-relation 固定总预算锁定为 23；静态断言禁止四个旧 per-query helper 和无调用 `_proof_query_issues` 回归，不保留 wrapper/fallback。
- Contract/integration：caller-owned snapshot、只读行为、registry/CLI/operations/System envelope 和共享上游 proof 保持；一次性本地 PostgreSQL 0001–0107 migration 后完整成本 Audit clean-pass，证明合并 statement 的 syntax/列解析。
- 七类决策：1 exact-set business proof、2 service I/O、3 Audit/API envelope 回归、4 read-model 只读、6 page/CLI/System + PostgreSQL 集成、7 existing regression 适用；5 frontend 不适用，因为页面与遮罩未改。
- 未测风险：本地空数据 PostgreSQL 不替代真实数据 `EXPLAIN (ANALYZE, BUFFERS)`、生产 Audit `<=5s`、mismatch 修复与连续 pass；这些仍待用户授权后的统一部署窗口。

## 2026-07-16 - GSD 05-17 成本 Audit 结构化 bank-flow 单读链路

- 影响范围：仅 `cost_statistics_page_audit.py`、成本 Audit 直接测试与模块文档；不改 API、read-model 发布、worker、前端、共享 Audit 或其他页面。
- Business/service：`test_bank_flow_proofs_read_only_v9_structured_rows` 锁定 canonical expected-set、字段 proof 和 summary rollup 全部读取 `cost_statistics_bank_flow_rows`，成本 Audit SQL 对旧 `bank_flow_time_rows` 为零引用；金额直接使用 numeric 列，parent 由 month rows 形成 `project_scope || ':all'`。
- Contract/integration：既有三类 blocking issue、统一 business-values statement、caller snapshot、read-only 和 26-query 预算保持；通用 Audit 测试同步锁定 typed bank amount，而不要求恢复 JSON member 解析；System Audit PostgreSQL parent fixture 也不再写入已禁止的 row array。
- 七类决策：1 business exact-set/field/summary、2 service I/O、3 Audit envelope 回归、4 structured read-model 只读、6 page/CLI/System 本地集成、7 existing regression 适用；5 frontend 不适用，因为页面和遮罩未改。
- PostgreSQL integration：新增 `CostStatisticsPageAuditPostgresTests::test_v9_parent_without_row_arrays_passes_real_postgres_audit`，在 0001–0107 migration 后用无 row arrays 的 v9 parent执行完整成本 Audit，锁定 SQL syntax/列解析与 clean pass；默认仍由 `FIN_OPS_TEST_DATABASE_URL` 安全门禁。
- 未测风险：本地 PostgreSQL 空数据证明不能替代真实 plan、生产数据量、Audit `<=5s` 与连续 pass；这些仍待统一部署窗口，本轮不部署。

## 2026-07-16 - GSD 05-16 成本 Audit business-values 单次集合查询

- 影响范围：`cost_statistics_page_audit.py`、成本 Audit专属测试与文档；不改页面/API、read model、worker、Workbench/Bank Detail proof owner或其他页面。
- Business/service：`tests/test_cost_statistics_page_audit.py::CostStatisticsPageAuditTests::test_business_value_proofs_use_one_query_and_preserve_each_issue_contract`锁定五类issue code/details、五个独立`limit`、绑定参数顺序与单次`cost_business_value_proofs` I/O。
- 性能/只读：`test_clean_audit_preserves_contract_and_active_relation_query_budget`将真实触发group-row proof的固定预算锁定为26；caller-owned snapshot与`connection.executed == []`继续证明无写入、无temp table、无refresh。
- Contract/integration：同文件的registry、CLI、operations/System snapshot测试以及通用Audit回归保护唯一owner和既有report envelope；Workbench relation equality仍只执行一次。
- 七类决策：1 business proof、2 service I/O、3 Audit API envelope回归、4 read-model snapshot只读、6 CLI/operations/System集成、7 existing regression适用；5 frontend不适用，因为UI/Audit icon/遮罩未改。
- 未测风险：未运行真实PostgreSQL syntax/plan/生产数据量；26不是生产`<=5s`结论，剩余exact-set查询与生产连续pass留待后续prompt/统一部署窗口。

## 2026-07-16 - GSD 05-15 bulk export 有界 SQL / write-only XLSX

- 影响范围：成本 query service、cost repository port/manifest、PostgreSQL export page query、API/SQL runtime tests 与文档；不改 route/HTTP shape、前端、worker、Audit、schema、权限或其他页面 read model。
- Business/service：`tests/test_cost_statistics_sql_runtime.py` 证明 preview 只请求 8 行且不读取 full view，download 每批请求 1,000 行、只在首批取 summary，并在 workbook 完成后第二次比较 published proof；超限在 workbook 创建前失败，中途版本变化 fail-closed。
- Repository/read model：同文件的 SQL contract test 覆盖 month/date/project/expense/tag filters、structured cost table、summary 与 page limit；port/manifest 登记唯一 `get_cost_statistics_export_page(...)`，未向共享 gateway 或其他页面扩散。
- API/integration：`tests/test_cost_statistics_api.py` 继续解析 time/bank-tag/month/project/expense/transaction workbooks，保护文件名、sheet 顺序、高级选项、精确日期、expense filters、preview summary 与 400 limit DTO。
- Legacy/隔离：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_cost_statistics_bulk_export_does_not_reload_full_explorer_payload` 禁止 `_filtered_entries_from_read_model`、full-view bulk caller、非 write-only workbook 和大于 1,000 的 repository 批次回归。
- 七类决策：1 business core、2 service、3 API、4 read model/cache、6 local publish-fixture→export workbook、7 regression 适用并覆盖；5 frontend 无行为变化，复用既有 Browser 合同，不新增 UI 测试。
- 未测风险：无真实 PostgreSQL EXPLAIN/大数据内存峰值/代理下载/生产并发发布；统一部署后再执行 authenticated export smoke 与生产性能证据。本轮未部署。

## 2026-07-16 - GSD 05-14 全量 load / 无条件 save 旧合同删除

- 影响范围：成本 repository port、共享 PostgreSQL read-model repository 的成本专属方法、Postgres/local state store、state-store protocol、manifest 与直接测试；不改 API/DTO、worker event、schema、Audit、前端或其他页面 read model。
- Service/read model：`tests/test_cost_statistics_sql_runtime.py` 与 `tests/test_postgres_repositories_boundaries.py` 把原 direct-save 行存储断言迁到真实 source-version conditional publish，继续覆盖 metadata、两类 structured rows、parent no-row、obsolete delete、batch write 与 stale publish 零写入。
- State-store/隔离：`tests/test_postgres_state_store.py::PostgresStateStoreTests::test_postgres_full_state_snapshot_omits_cost_statistics_read_model` 证明 broad load/save 不再查询或写入成本表；`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_cost_statistics_does_not_retain_full_snapshot_load_or_unconditional_save_io` 锁定 port/repository/state-store/protocol 的旧方法和 snapshot key 不得回归。
- Contract/回归：`tests/test_read_model_manifest.py` 锁定成本 port 只登记 scoped reads 与 conditional publish；成本 API/SQL runtime、scope/gateway、derived lifecycle 和 state-store 回归保护既有 `200/202/304/409`、freshness、parent fan-out 与其他 state key。
- 七类决策：2 service、3 API 回归、4 read model/cache/worker、6 projection→publish→query integration、7 existing regression 适用并覆盖；1 business core、5 frontend 不适用，因为金额/归因/状态规则和 UI 均未改变。
- 未测风险：本轮无生产部署、worker drain 或真实生产 SLO；warmup删除门已关闭，统一部署后仍需跑 migration/rehydrate、EXPLAIN、Audit、页面/导出 p95/p99 与混合负载隔离验证。

## 2026-07-16 - GSD 05-12 单次依赖鲜度门禁与旧 provider 删除

- 影响范围：成本 query/runtime、成本 PostgreSQL gate、projection/query 共用 source-version helper、App Settings 无 I/O mapper、Application 成本装配与旧 provider 删除；不改前端、Audit、worker、migration、共享 gateway 或其他页面 read model。
- Business core：`tests/test_cost_statistics_sql_runtime.py` 证明 shared helper 对 concrete month 包含 Workbench/Bank Detail snapshots，对 parent `all` 明确省略两类伪依赖；当前 settings version 变化会让旧成本 snapshot 在 payload I/O 前 fail-closed。
- Service/read model/cache：四个 query 入口分别只调用一次成本 gate，non-fresh 不读 Redis/page/full/detail rows；repository 单条 SQL 同时包含 App Settings singleton、Workbench active generation/dirty、Bank Detail scope/dirty，并覆盖 pending、failed、非法 settings shape、空 dependency versions 与 published/dirty version drift。
- API/回归：既有 `200/202/304`、detail `409/404`、export/标签/权限 DTO 回归保持；runtime 不再按当前 expected key 删除 Redis，versioned namespace + gate 使旧 cache 不可读且由 TTL 退出。
- 旧代码 guard：禁止 Application 四个 cost source wrappers、runtime `source_versions_provider/expected_source_versions/delete_redis_cache`、query `tag_selection_provider` 与 legacy live service 回归；测试 fixture 使用 gate snapshot/production pure helper，不加 app shim。
- 验证证据：成本/App Settings/边界主回归 `316 tests` 通过；共享 query gateway/freshness/scope 回归 `46 tests` 通过；`bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check` 通过。
- 七类决策：1 business core、2 service、3 API contract、4 read model/cache、6 query→route integration、7 existing regression 适用并已覆盖；5 frontend 不适用，因为 UI/遮罩/交互合同未变。
- 未测风险：未部署、未访问生产、未运行真实 PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)`，因此不能声明 p95/p99 已达标；真实 plan、连接池排队与生产 SLO 留到用户允许统一部署后的验证窗口。

## 2026-07-16 - GSD 05-10 成本 Audit source-version 证明单次往返

- 影响范围：`cost_statistics_page_audit.py`、成本 Audit 专属测试和既有成本 source-version 合同测试；不改通用 Audit、页面/API、read model、worker、Workbench 或 Bank Detail。
- 新增/更新测试：`tests/test_cost_statistics_page_audit.py` 锁定 source-version proof 只有一个数据库调用、row/scope + 月度上游 + parent shard 三类 issue code/details、三分支各自 `limit` 和 active-relation 总预算 30；`tests/test_audit_page_business_read_model_tool.py` 继续验证上游版本与 parent shard SQL/阻断合同。
- 查询门禁：05-09 active-relation 上限为 32；05-10 删除同一函数内两个额外串行往返后，上限固定为 30。没有删除、缓存或降级任何 proof，三个分支总样本仍可达到 `3 * limit`。
- 验证证据：成本/通用 page/operations/System 65 tests（2 skipped）通过；成本 API/SQL runtime 66 tests 通过。`FIN_OPS_TEST_DATABASE_URL` 未配置，因此没有真实 PostgreSQL syntax/plan/data-volume 证据。
- 未测风险：30 仍不是最多四组 SQL 或生产 `<=5s` 结论；统一部署后必须量测每组 SQL、整体 p95、真实 upstream mismatch 和连续 pass。

## 2026-07-16 - GSD 05-09 成本 Audit 重复证明与固定往返收敛

- 影响范围：`cost_statistics_page_audit.py`、Workbench integrity collector 的可选 summary I/O、成本 Audit 专属测试；不改页面/API/read model/worker/其他页面 Audit。
- 新增/更新测试：`tests/test_cost_statistics_page_audit.py` 增加 active relation 场景的真实 query budget、summary/dirty/outbox 单查询 fail-closed、relation equality 单次执行和既有双 issue-code 保留；共享 Workbench Audit 回归验证默认 `include_summary=True` 行为不变。
- 查询门禁：旧 05-08 空数据预算为 35，真实 active relation 会额外查询 group rows、实际上限为 36；05-09 删除 2 次 runtime state 往返、1 次重复 relation equality 和 1 次成本不消费的 Workbench generation summary 后，active-relation 上限固定为 32。
- 未测风险：本地没有真实 PostgreSQL 数据量和 `EXPLAIN (ANALYZE, BUFFERS)`；32 仍不是四组 SQL 或 `<=5s` 结论，统一部署后必须量测每组 SQL、整体 p95 和连续 pass。

## 2026-07-16 - GSD 05-08 成本 Audit 所有权迁移

- 变更类型：Audit repository ownership / registry dispatch / legacy shared-branch deletion；业务口径与 HTTP response shape 不变。
- 架构结论：`cost_statistics_page_audit.py` 是唯一成本证明 owner；page Audit、通用只读 CLI 和 System Audit 都直接调用它并透传 caller-owned snapshot。共享 `page_business_audit.py` 只输出明确的 Bank Detail projection proof provider，不再包含成本合同、SQL、issue mapping 或 dependency dispatch。
- 旧代码删除：shared repository 中 `cost_statistics` runtime/text 分支、`PAGE_AUDIT_CONTRACTS` 成本登记和 generic domain dispatch 全部删除；无第二 route、snapshot、registry、repair 或 fallback。
- 新增/更新测试：`tests/test_cost_statistics_page_audit.py`、`tests/test_audit_page_business_read_model_tool.py`、`tests/test_page_audit_registry.py` 的既有全覆盖回归。
- 覆盖点：原 exact-set/critical fields/summary/group/bank-account/version/parent/dependency/queue issue codes 等价；显式 snapshot identity；唯一 executor；CLI；共享旧分支静态零命中；迁移时空数据查询预算 `1 fetch_one + 34 fetch_all = 35` 不回退。
- 七类测试决策：1 business core 适用并迁移既有金额/方向/归因 SQL 断言；2 service-layer 适用；3 API contract 适用但 shape 未变；4 read model/cache/job 适用；5 frontend 不适用；6 operations/System Audit dispatch 适用；7 其他 page-business/OA 回归适用。
- 未测风险：35 是 05-08 行为等价空数据预算而非性能终态；05-09 已用 active relation 场景校正并降至 32。真实 PostgreSQL query plan、生产 `<=5s`、既有 upstream mismatch 修复和连续 pass 仍必须由后续 prompt 与统一部署窗口证明。

## 2026-07-16 - GSD 05-07 成本页轻量 freshness 交互锁

- 变更类型：cost-local frontend lifecycle / accessibility / interaction isolation；后端 API、read model、worker、Audit 和共享 App Shell 不变。
- 架构结论：页面只派生一个 `effectiveCostPageState`，合并当前 explorer lifecycle/freshness、App Status 精确成本 scope 和标签规则 barrier。只有明确 fresh 解锁；其他状态使用 native `inert`、`aria-busy`、内联 status rail 和 20% alpha pointer layer。标题/Audit/导航保持可用，不新增通用 overlay、store、实时通道或依赖。
- 旧代码删除：首屏 loading 和 read-model refreshing/stale/unavailable 的旧 `.state-panel` 分支与旧文案已删除；non-fresh 不保留可操作 view/range/refresh/tag/export/table/load-more；detail/export portal 会关闭，详情请求可取消；无 modal-looking backdrop、blur 或遮罩动画。
- 新增/更新测试：`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`；既有 `CostStatisticsApi.test.ts` 继续保护唯一 explorer client contract。
- 覆盖点：initial/error/refreshing/stale/unavailable/fresh；真实 `inert`、20% alpha/no blur/no dialog；retry；锁定焦点迁移与 fresh 后恢复；domain refresh 关闭 export portal；标签规则 drawer 保留且 body/footer inert；BFCache revalidate；App Status 精确 scope 锁定与旁支 scope 隔离；五视图、详情、导出、大表和窄屏 Chromium 回归。
- 七类测试决策：1 business core 不适用，金额/分类/状态转换未改；2 service-layer 不适用，无 service/repository/worker 改动；3 API contract 不适用，HTTP shape/status 未改，复跑既有 client contract；4 read model/cache/job 间接适用，前端 fail-closed 消费既有 freshness/App Status，后端 CAS/gate 未改；5 frontend interaction 适用并新增 Vitest；6 E2E 适用并全量复跑 cost Chromium flow；7 existing regression 适用，保护五视图、范围、详情、导出、规则、权限和其他 scope 隔离。
- 本地验证：Vitest `37 passed`；Chromium `12 passed`；production build 通过，仅保留既有第三方 CSS minify/chunk warnings。最终 lint/docs/diff 与旧代码扫描证据见 `05-07-SUMMARY.md`。
- 未测风险：真实 App Health SSE/fallback 时序、生产浏览器 data-ready SLO、生产 migration/rebuild/EXPLAIN、Audit 和跨设备收敛需统一部署窗口验证；本轮保持 `DEPLOYMENT_HOLD`。

## 2026-07-16 - View-specific cursor explorer 原子切换

- 变更类型：cost-local repository/query/API contract + frontend request lifecycle + legacy page-chain deletion。
- 架构结论：保留原 `/api/cost-statistics/explorer`，强制 `scope + view`；每次只返回完整 summary、小型 facets 和最多 100 条当前层级 rows。PostgreSQL durable gate 位于 ETag、Redis 与单条 set-based page SQL 之前；year/all 复用 parent gate，不新增 scope/table/worker/index/dependency。前端只呈现服务端聚合并以 cursor 追加同版本 rows。
- 旧代码删除：删除旧 full explorer client/type/mapper、`timeRows/bankFlowTimeRows` 全量 state、浏览器 scope/filter/group/summary helpers、full-all 导出选项读取，以及 detail 失败时从列表行拼装本地详情的 fallback。旧 full-view loader、month summary 与 project route 已连同最后调用方删除。
- 新增/更新测试：`tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_read_model_manifest.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/apiMock.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`。
- 覆盖点：scope/view/filter/page-size 校验；gate-before-ETag/cache/SQL；ETag 304 skip；cursor query/version binding；one-statement page I/O；available years 不被当前 month/year 锁死；五视图下钻；lazy bounded export facets；翻页；non-fresh empty；详情 stale 不 fallback；390px 大数据 cursor 追加。
- 七类测试决策：1 business core 适用，覆盖 scope/filter/facet/方向与 cursor 边界；2 service-layer 适用，覆盖 gate/cache/page repository；3 API contract 适用，覆盖新唯一 shape、200/202/304/400；4 read model/cache 适用，worker 未改且由既有 CAS 回归保护；5 frontend interaction 适用；6 E2E 适用，完整 Chromium 五视图/详情/导出/分页链路；7 regression 适用，保留旧 month/summary/export/manifest 与 relation fan-out 责任。
- 验证：定向 backend 68 tests 业务用例通过（另行正确调用的 manifest 3 tests 通过）；Vitest 页面 27 tests、API 6 tests 通过；Chromium flow 10 tests 通过（发现并删除 detail local fallback 后定向复跑通过）；production build 通过并仅保留既有第三方 CSS warning。最终 lint/docs/diff 门禁见 `05-06-SUMMARY.md`。
- 未测风险：真实生产 `EXPLAIN (ANALYZE, BUFFERS)`、浏览器/API SLO、migration/rebuild、Audit、轻量锁定遮罩、请求期 expected-source provider、流式导出和剩余内部 full loader；统一部署前不宣称整体闭环。

## 2026-07-16 - 首屏 I/O 隔离与前端旧缓存删除

- 变更类型：frontend request lifecycle + cache/freshness boundary + legacy client cleanup。
- 架构结论：删除前端 5 分钟 explorer Map 与 mount-time `active:all` 预取；页面只加载当前 scope，范围切换时上一 scope 立即退出可操作内容。项目/费用类型导出筛选仅在用户实际需要时读取 fresh `active:all`，time/bank-tag 导出不承担该 I/O。后端 PostgreSQL gate 仍是唯一 freshness 证明，HTTP DTO、read model、worker 和其他页面不变。
- 旧代码删除：`costExplorerCache`、get/clear API、`fetchCostStatisticsMonth`、`fetchProjectCostStatistics` 及仅由它们使用的 API/type definitions；whole-repo current-code scan 为零。
- 新增/更新测试：`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/apiMock.ts`；既有 `web/e2e/cost-statistics-flow.spec.ts` 全量回归。
- 覆盖点：首屏无 `month=all`；API client 每次真实 fetch；scope 延迟期间不保留旧表格；time 导出无 all I/O；expense/project 模式直接打开或弹窗内切换时才加载 all；all non-fresh 时导出中心保持关闭；五视图、详情、标签规则、preview/download、empty/error/non-fresh 回归。
- 七类测试决策：1 business core 不适用，金额/归因/方向未改；2 service-layer 不适用，无后端 service/repository 变更；3 API contract 适用，锁定 explorer mapper 与真实 fetch；4 read model/cache/background job 仅 cache 边界适用，证明前端 cache 删除且后端 gate 唯一，worker 未改；5 frontend interaction 适用；6 既有 explorer→视图→导出 Chromium 主流程适用并通过，无新增跨模块写流；7 existing regression 适用，覆盖五视图和导出/详情/规则。
- 未测风险：完整 explorer payload、view-specific cursor、真实生产 SLO/EXPLAIN、轻量锁定遮罩、Audit 和剩余后端旧模块删除仍属后续切片；本轮不部署。

## 2026-07-16 - 结构化成本行、详情点查与旧 Redis writer 删除

- 变更类型：migration + repository/query/projection + read-model storage/performance contract。
- 架构结论：沿用现有 cost repository port 和 fresh gate，只新增一张当前需求必需的 `read_model.cost_statistics_bank_flow_rows`。OA 配对成本与全银行收支分别写两张结构化表；parent snapshot 不再保存 `time_rows` / `bank_flow_time_rows`。API 逻辑 DTO 从结构化表重建且不保留 JSON fallback；transaction detail 通过同一 freshness gate 后按 identity index 点查，不再加载 `active:all`。projection 的旧无版本 Redis set/delete writer 已删除，query gateway 仍可在 gate 后缓存 versioned payload。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`tests/test_postgres_migrations.py`、`tests/postgres_test_utils.py`。
- 覆盖点：0107 表/约束/权限/父聚合与 identity indexes；父 metadata 无两类 arrays；两张行表 bulk replace；parent 从结构化 bank-flow rows 聚合，且 source manifest 从 month metadata 取得并保留合法空 shard；读取拒绝 stale JSON fallback；transaction point SQL 与详情 API 不访问 full explorer；tag selection 继续限制详情可见性；projection 成功/拒绝均不写旧 Redis；旧 API response shape 回归。
- 七类测试决策：1 金额/方向业务规则未改，不新增 business-core；2 repository/query/projection 适用；3 detail 与既有 explorer/export API shape 适用；4 read model/cache/migration/worker storage 适用；5 UI 本切片未改，不适用；6 projection→repository→query/API 组合路径适用并覆盖，本切片不新增浏览器流；7 existing cost API、共享 migration 与 Redis gateway regression 适用。
- 未测风险：view-specific cursor API、导出流式化、Audit 拆分/修复、轻量遮罩和请求期 expected-source provider 删除仍是后续切片；真实 PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)`、生产数据迁移/rebuild 和 SLO 必须等统一部署窗口验证。本轮不部署。

## 2026-07-16 - PostgreSQL freshness gate before Redis

- 变更类型：migration + cost query/repository + API/read-model cache contract。
- 架构结论：不修改共享 `ReadModelQueryGateway`，只在成本 query owner 增加 repository-port gate。`published_source_version` 与 snapshot/rows 在 05-02 已有 CAS transaction 内发布；每次 explorer/month 请求先用单条 PostgreSQL metadata query 比较最新 durable dirty version/status，fresh 后才允许 Redis/full payload。runtime version 独立于业务 `source_versions`。
- 删除旧代码：full-view loader 已删除；Redis hot-cache 测试要求先执行一条 metadata gate 且不读取 full payload，non-fresh 时 Redis 与 page SQL 都不得触碰。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`tests/test_postgres_migrations.py`。
- 覆盖点：fresh gate→Redis 顺序、published version cache-key rotation、pending/processing/failed/mismatch/metadata-null 阻断 Redis/full rows、missing enqueue、done match、done-history retention、同事务 published-version 写入、migration 无历史回填与 cost-only index、memory API repository 合同。
- 七类测试决策：1 金额业务规则未变，不适用；2 service/repository 适用；3 API 202/fresh shape 适用；4 read model/cache/background version 适用；5 UI 未变，不适用；6 route→gate→Redis/full repository 关键组合路径已覆盖，不新增浏览器 E2E；7 existing cost API/runtime 与共享 query gateway/Tax Offset/Turnover 回归适用。
- 未测风险：生产 `EXPLAIN (ANALYZE, BUFFERS)`、真实延迟门槛、view-specific rows/pagination、前端遮罩、Audit、最终旧模块删除仍属于后续切片；本轮不部署。

## 2026-07-16 - 成本 worker source-version 条件发布与完成

- 变更类型：service/repository + read model/background worker concurrency contract。
- 架构结论：不新增表、服务或通用框架；沿用 durable dirty scope 的 `source_version` 和 active-scope partial unique index。成本 worker 只调用显式 month/parent builder，event 版本缺失或非法时 fail fast；repository 在一个事务内锁定唯一 `pending` / `processing` dirty row，版本精确相等才发布。父 scope 的旧月份删除与 parent snapshot 同事务。发布被拒绝不写 SQL/Redis、不完成 dirty、不 fan-out；发布后出现新 dirty 使条件完成失败时保持 `refreshing`，月 scope 也不 fan-out parent。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py`。
- 覆盖点：合法版本 `0` 保留；缺失、负数、布尔和非整数 event 版本拒绝；匹配版本条件发布；active dirty 缺失或版本更高时零写入；parent cleanup 原子性；拒绝发布不缓存；拒绝发布和完成竞态均不投递 parent；完成调用携带 event 版本。
- 七类测试决策：1 业务金额规则未变，不适用；2 service-layer 适用；3 HTTP/API shape 未变，不适用；4 read model/cache/background job 适用；5 UI 未变，不适用；6 本切片不跨新模块且由 service→repository 组合测试覆盖，不新增 E2E；7 existing regression 适用，既有 cost statistics SQL/runtime 全文件回归。
- 验证命令：`PYTHONPATH=backend/src:. python3 -m unittest tests.test_cost_statistics_sql_runtime -v`；其余 lint/docs/相关回归见 `05-02-SUMMARY.md`。
- 未测风险：读侧 PostgreSQL freshness-before-Redis gate、API/UI overlay、Audit 修复、完整旧代码删除和生产竞态/SLO 证据属于后续切片；本轮不部署。

## 2026-07-14 - 成本统计紧凑导航、金额对齐与下钻时间 chip

- 变更类型：frontend layout + interaction + existing feature regression。
- 架构结论：只调整 `CostStatisticsPage`、共享成本表格 cell text contract 与页面样式；API、read model、worker、权限和业务金额口径不变。五类分类进入标题行，范围控件进入下一行最左；OA 三类金额统一显示“支出”；四种 explorer 下钻表移除独立时间列并在户名/项目名下显示时间 chip；按时间主表保留时间列。
- 新增/更新测试：`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts`。
- 覆盖点：标题行包含分类 tablist；范围控件 CSS/阅读层级左置；标签/金额两列对齐；OA 项目、银行、费用类型列表出现“支出”；项目、银行、费用类型、标签流水表无“时间”表头且复合首列包含格式化时间 chip；真实 Chromium 量测标签三栏高度一致。
- 七类测试决策：1 业务核心不适用，金额和分类规则未变；2 service-layer 不适用，未改 service/repository；3 API contract 不适用，DTO/状态码未变；4 read model/cache/background job 不适用，未改 freshness/worker；5 frontend component and interaction 适用并更新 Vitest 与 Chromium；6 end-to-end business-flow 不新增跨模块写流，既有成本统计 browser 主流程继续回归；7 existing regression 适用，保护五视图切换、范围选择、下钻详情、收入/支出方向和宽表滚动。
- 验证命令：`cd web && npm test -- --run src/test/CostStatisticsPage.test.tsx --reporter=verbose`；`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts -g "keeps redesigned view buttons and range controls usable" --project=chromium`；`cd web && npm run build`；`bash scripts/verify.sh docs`。
- 未测风险：真实生产超长户名/项目名、极端浏览器缩放和生产数据量下的视觉密度仍需 staging/manual smoke。

## 2026-07-13 - 全流水收入纳入标签、分方向展示与导出

- 变更类型：business rule + read model/API contract + settings migration + frontend interaction/export。
- 架构结论：OA 统计继续只消费配对支出 `time_rows`；按时间/按标签消费收入与支出 `bank_flow_time_rows`，不显示合并总额或净额，只显示正数绝对值的分方向金额/笔数。收入与支出标签都进入规则，legacy 显式选择升级为 schema v2 时保留原支出选择并加入当前有效收入标签。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`tests/test_app_settings_service.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts`。
- 覆盖点：投影拉取 inflow/outflow 且输出方向摘要；query/tag/export/filter 合同；legacy 规则迁移；页面顶部、主标签、子标签分方向金额/笔数；绿/橘方向样式；收入明细；time/bank_tag preview 和下载字段；OA 统计旧口径回归。
- 七类测试决策：1 业务核心适用（方向分类、金额、规则迁移）；2 service 适用（projection/query/settings）；3 API contract 适用（explorer、preview、export）；4 read model/cache/worker 适用（schema v8、Audit expected-set）；5 frontend interaction 适用；6 E2E 适用（bank detail -> projection -> API -> UI/export）；7 existing regression 适用（OA 统计、旧选择和旧导出）。权限合同未改变，沿用既有 tag-rules 写权限和 export 权限回归。

## 2026-07-11 - 正式 relation lineage 与全银行流水口径测试收敛

- 变更类型：test fixture contract correction + read model lineage regression。
- 架构结论：成本统计 OA 归因只能消费 active `workbench_relation`；没有 active relation 的相似事实不得进入成本，新 Workbench runtime 也不再生成 open/proposed candidate。API fixture 必须通过正式 confirm-link 写边界建立 active relation。`按标签` / `按时间` 的 `bank_flow_time_rows` 是独立的全银行流水 projection；2026-07-13 起包含收入与支出，测试数据必须从 canonical bank transactions 构造。
- 更新测试：`tests/test_cost_statistics_api.py`。
- 覆盖点：fixture 通过真实 `/api/workbench/actions/confirm-link` 建立关系；没有 active relation 的相似事实仍被排除；全银行流水可包含没有 OA relation 的收入或支出，并保持 `未配对OA` / `未分类` 展示口径；project/expense-type export 继续消费 OA 配对支出行。
- 七类测试决策：business core、service-layer、API contract、read model/cache/background job、end-to-end business-flow integration、existing regression 适用并由成本统计 API/服务组合测试覆盖；frontend interaction 行为未变，继续由既有 `CostStatisticsPage.test.tsx` 与 Browser flow 覆盖。

## 2026-07-10 - 成本统计标签规则和双统计口径

- 变更类型：settings-backed rule contract + read model payload contract + frontend drawer interaction。
- 架构结论：成本统计标签规则由 `AppSettingsService` 持久化，暴露主/子标签 leaf code 与虚拟 `__uncategorized__` 未分类标签；当前 schema v2 默认全选有效收入与支出标签 + 未分类，显式空数组表示全部不进入成本统计。`按项目`、`按银行`、`按OA费用类型` 只统计 OA 配对支出 `time_rows`；`按标签`、`按时间` 统计全部银行收支 `bank_flow_time_rows`。规则保存不触发 read model rebuild。
- 新增/更新测试：`tests/test_app_settings_service.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`。
- 覆盖点：默认标签选择包含有效收支标签和未分类；保存空选择可持久化；API 读写标签规则并返回空 targets，缺少写权限时不调用 settings service；query service 对 OA 配对行和全银行收支行按同一标签规则过滤；前端 mapper 支持 `bank_flow_time_rows`；规则抽屉保存后递增当前页 query nonce并关闭，不等待 operation barrier；Browser 记录 Drawer 打开/保存 latency、PUT 一次、当前 explorer normal GET 与零 barrier。
- 七类测试决策：business core 适用，覆盖标签选择和金额口径过滤；service-layer 适用，覆盖 settings 持久化、query service 过滤和 read model payload 使用；API contract 适用，覆盖 `GET/PUT /api/cost-statistics/tag-rules` 与空 targets；read model/cache/background job 适用，覆盖 query-time filtering 和不触发 rebuild；frontend interaction 适用，覆盖紧凑抽屉、normal GET 和零 barrier；existing regression 覆盖 explorer、五视图、导出/详情不回退 live fallback。
- 验证命令：见本轮最终说明。

## 2026-07-06 - 按流水标签类型读取银行明细有效主/子标签

- 变更类型：read model payload contract + cross-module read boundary。
- 架构结论：成本统计 `time_rows.bank_tag_*` 不再信任 Workbench 行内旧标签字段；月份 shard 使用 `BankTransactionTagReadFacade` 从 fresh `bank_detail` scoped read model 批量读取银行明细有效分类，并把 `bank_detail_source_versions` 写入成本统计 source_versions。当时 payload schema 升级为 `2026-07-cost-statistics-bank-tags-v4`，当前 schema 已在 2026-07-10 升级到 v5；旧 v3/v4 父 scope 即使仍被标记 fresh，也必须返回空刷新态并入队重建，不能继续把旧 `未标记` 行交给页面。`bank_detail` 非 fresh 时成本统计 worker 抛 `bank_detail_read_model_not_fresh`，由 runtime dependency retry 处理，不发布旧标签 payload。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py`、`tests/test_runtime_bootstrap.py`。
- 覆盖点：Workbench bank row 不携带标签字段时，成本统计仍从银行明细 facade 写入主标签、子标签和 label path；成本统计 expected source_versions 包含 bank detail scope 版本；worker wiring 向 `CostStatisticsSqlProjectionBuilder` 传入 `bank_transaction_tag_read_facade`；旧 v3 `active:all` payload 不向页面返回旧行并入队重建；依赖非 fresh 时不保存成本统计 read model。
- 七类测试决策：service-layer、API contract、read model/cache/background job、existing regression 适用并覆盖；frontend interaction 由既有 `CostStatisticsPage.test.tsx::bank tag view drills down from primary tag to sub tag to transaction` 覆盖，本轮 UI 未变；business core 金额归因不变；E2E 写流继续沿用银行明细/成本统计既有 Browser flows，本轮不新增跨模块浏览器用例。
- 验证命令：见本轮最终说明。

## 2026-07-05 - 银行账户全集、标签规则联动、时间格式与表头总金额

- 变更类型：read model payload contract + frontend interaction/layout + cross-module lifecycle。
- 架构结论：按银行统计的银行全集由 settings owner 的 `bank_account_mappings` 经成本统计 SQL projection 写入 explorer `bank_accounts`，页面只合并 `bank_accounts + time_rows`。按时间展示格式化后的 `YYYY-MM-DD HH:mm:ss`，过滤仍使用原始 `trade_time`。2026-07-13 起全流水视图已用收支分列金额替代当时的表头总金额。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_bank_details_sql_runtime.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/AppSidebar.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts`。
- 覆盖点：explorer payload 必须包含 `bank_accounts`；settings 银行账户映射进入 `source_versions.bank_account_mappings_fingerprint`；标签规则版本继续进入 `source_versions.bank_auto_tag_rules_version`；按银行统计展示设置中的零金额账户；时间列不直出 ISO/T 字符串；sidebar 深蓝背景有组件回归断言。全流水收支分列由 2026-07-13 测试覆盖。
- 七类测试决策：service-layer、API contract、read model/cache/background job、frontend interaction、existing regression 适用并覆盖；business core 金额归因口径不变，不新增独立业务规则测试；end-to-end business-flow 使用既有成本统计/银行明细/settings browser flows，本轮新增的是读模型合同与页面交互，不新增跨模块写流 e2e。
- 验证命令：见本轮最终说明。

## 2026-07-05 - 成本统计页面 I/O、旧 UI 与旧后端 fallback 关闭

- 变更类型：frontend layout / page I/O cleanup + route-owner/query-runtime legacy dependency cleanup。
- 架构结论：成本统计页面主范围选择器只暴露 `all` / `year` / `month` 三种读侧范围，使用单一按钮打开浮层；页面不再暴露自定义日期范围、项目范围切换按钮、顶部三张 summary card 和标题下解释文案。精确日期范围仍属于导出中心 I/O。页面固定以 `project_scope=active` 请求 explorer/detail/export；`project_scope=all` 仍由后端 API/read model 合同测试覆盖。
- 新增/更新测试：`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts`、`tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_sql_projection_rules.py`、`tests/test_cost_statistics_derived_lifecycle_executor.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_platform_runtime_boundary_guards.py`。
- 覆盖点：旧 summary card 组件/样式删除；主页面范围控件没有 custom date/radio/tab 残留；所有视图的范围按钮可选 all/year/month；项目视图不再出现 `项目范围：进行中/所有项目`；导出中心继续携带 active project scope 和精确日期范围；legacy `CostStatisticsService` module/class/test/import 与 API fixture 已删除；query service 不再持有 local read model service 或 `_cached_month_entries` fallback；runtime service 不再持有 `explorer_loader` / read model upsert writer；live export helper 与 `ProjectDetailExportService` 已删除；derived lifecycle 计划只报告 `cost_statistics.read_model.refresh`。
- 七类测试决策：service-layer、API contract、read model/cache/background job、frontend interaction、existing regression 适用并覆盖；business core 适用但只保留成本归因测试，删除 live export 专项；end-to-end business-flow 继续沿用 browser/import/settings/Workbench fan-out 覆盖，本轮不新增跨模块业务流。
- 验证命令：见本轮最终说明。

## 2026-07-04 - 按流水标签类型视图与 bank tag payload 合同

- 变更类型：read model payload contract + frontend 派生视图。
- 架构结论：流水标签统计属于成本统计 explorer read model 的读侧派生功能；页面只能读取 `cost_statistics.time_rows.bank_tag_*`，不得直接调用银行明细页 read model 或本地重算银行标签事实。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_rebuilds_active_all_from_materialized_shard_rows`、`tests/test_cost_statistics_sql_projection_rules.py::CostStatisticsSqlProjectionRuleTests::test_projection_counts_only_outflow_with_one_complete_oa_context`、`tests/test_cost_statistics_sql_projection_rules.py::CostStatisticsSqlProjectionRuleTests::test_active_scope_excludes_only_known_completed_projects`、`web/src/test/CostStatisticsApi.test.ts::maps bank tag fields from explorer time rows`、`web/src/test/CostStatisticsPage.test.tsx::bank tag view drills down from primary tag to sub tag to transaction`。
- 覆盖点：Workbench bank row 的 `effective_category_*` / `category_*` 字段进入成本统计 month shard payload；parent scope 从 materialized rows 聚合时保留标签字段；SQL projection 与 read-model query/export 输出同一 shape；前端 mapper 归一 snake_case 标签字段；页面三栏为 `主标签 / 子标签 / 流水`，第一、第二栏合计 50% 宽度。
- 七类测试决策：business core 不新增独立规则测试，因为成本归因金额口径不变；service-layer、API contract、read model/cache、frontend interaction、existing regression 适用并覆盖；E2E 本轮先不新增，因为该功能不新增跨模块写流，后续可并入成本统计浏览器 smoke。
- 验证命令：见本轮最终说明。

## 2026-07-02 - secondary read/export route read-model closure

- 变更类型：route-owner/query-service 边界收口。
- 新增/更新测试：`tests/test_cost_statistics_api.py::CostStatisticsApiTests::test_cost_statistics_secondary_read_routes_delegate_to_query_service_and_fail_closed`、导出/preview 用例显式预热 read model、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_cost_statistics_routes_use_route_owner`。
- 覆盖点：explorer/detail/export/export-preview 路由只调用 `CostStatisticsQueryService`；read model 未 fresh 返回 `409 cost_statistics_read_model_not_fresh`；导出 row limit 仍返回 `cost_statistics_export_row_limit_exceeded`；静态 guard 禁止旧 root/project route、warmup、full-view module/method、Application/test field 或兼容 shim 回归。
- 验证命令：见本轮最终说明。

## 修改前影响面清单

成本统计是跨银行流水、发票、OA、Workbench relation、项目归因和费用分类的派生 read model。任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 业务归因 | `CostStatisticsSqlProjectionBuilder`、project costing service、workbench relation/detail payload | 项目、费用类型、费用内容、金额方向、OA 字段、银行字段和 relation distribution 不能由页面重算。 |
| 项目范围 | app settings project status、`project_scope` | `active` 默认，只排除已完成项目；`all` 包含全部；未知项目保持 active；非法 scope 拒绝。 |
| read model scope contract | `ReadModelRefreshGateway`、scope policy registry | 合法 scope 只允许 `active:YYYY-MM`、`all:YYYY-MM`、`active:all`、`all:all`；裸月份/裸 all 只能在 gateway 归一化。 |
| 月份 shard | `read_model.cost_statistics_rows`、`cost_statistics.read_model.refresh` | 月份 shard 从对应 Workbench 月份 read model 构建；成功后重新入队同 project scope 父 scope。 |
| Workbench 输入边界 | `read_model.workbench_generations` active generation、`read_model.workbench_groups`、`read_model.workbench_group_rows`、`read_model.workbench_rows` | 成本统计必须先定位 active generation，再按 `generation_id + scope_key` 消费 groups 和成员 row；`workbench_groups.payload` 只作为组级 metadata 输入，OA/银行成员必须从 `workbench_group_rows + workbench_rows` materialize，不能按裸 `scope_key` 扫描历史 generation 或继续读旧 group JSON 成员数组。 |
| 全期间父 scope | `read_model.cost_statistics_read_models` | 父 scope 是一等 read model；从已物化月份 rows 聚合，不读 Workbench `all` 全量 payload。 |
| App Status readiness | `read_model.app_status_readiness`、`job.read_model_dirty_scopes`、`job.outbox_events` | 父 scope failed/unavailable 才阻断成本统计主体验；月份 shard failed/unavailable 是局部 busy。 |
| API/read cache | `/api/cost-statistics*`、Redis hot cache、SQL read model | fresh gate 后才能缓存；miss/stale 返回 refreshing 并入队，不同步重建伪 fresh。 |
| 导出 | cost statistics export/export-preview | time/project/expense type/bank view、date range、project scope、advanced export filters 和 filename contract。 |
| 前端交互 | `CostStatisticsPage`、`web/src/features/cost-statistics/api.ts` | 单按钮 all/year/month range、view switch、drilldown、modal、loading/error/empty/refreshing、export center；首屏只请求当前 scope，scope 切换不显示上一 scope，项目/费用类型导出参考数据按需且只接受 fresh；自定义日期范围只属于导出中心。 |
| 跨模块 fan-out | imports、ETC、pending invoice rules、workbench relation、turnover、project scope settings | 写入后必须通过 lifecycle/dirty scope/outbox 影响成本统计，不能只靠前端事件。 |

## 场景覆盖清单

## 2026-06-26 - Month-scope unchanged source_versions skip

- 变更类型：narrow implementation slice。
- 背景：生产 direct read model SLO 显示 `cost_statistics` 月度 scope 在输入未变化时仍重扫 Workbench active generation 输入并重写 payload，影响 p95。月度 projection 现在把 workbench active generation `source_versions` 纳入自身 source_versions，只有 SQL view 已 fresh 且版本完全一致时才返回 `skipped/source_versions_unchanged`。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_skips_unchanged_month_scope_without_workbench_scan`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；API contract/frontend/E2E/business core 不新增，因为 response shape、页面行为、成本归因和导出语义不变。
- 验证结果：`python -m pytest tests/test_cost_statistics_sql_runtime.py tests/test_cost_statistics_runtime_service.py tests/test_read_model_manifest.py -q` 已作为扩展集合的一部分通过；完整 backend verify 仍需本轮最终执行。

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 成本统计核心归因 | P0 | `tests/test_cost_statistics_sql_projection_rules.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_project_costing_service.py` | covered | 唯一 production SQL projection 覆盖银行原生月份非零支出、正式 OA relation、旧排除标记不再否决、借还款、多 OA 明确金额拆分/不闭合 fallback、完成/未知项目范围；Workbench open/proposed candidate 不计入成本。 |
| API shape、route facade、project scope | P0 | `tests/test_cost_statistics_api.py` | covered | explorer/detail/export、`project_scope`、invalid scope、cache hit/miss、导入 invalidation；旧 root/project route 保持删除。 |
| 导出和 export preview | P1 | `tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_sql_runtime.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` | covered | XLSX、filename、date range、project/expense filters、project scope 透传；导出只在 fresh gate 后读取 cost-owned SQL summary/bounded rows，preview <=8、download batch <=1000、write-only 且结束复核发布版本；Browser 覆盖 `read_export_only` 成功 download event、请求不带页面分页参数、下载内容字段；超过 20,000 行同步导出上限时结构化返回 `cost_statistics_export_row_limit_exceeded` 并在真实浏览器导出中心展示。 |
| durable invalidation / no local owner | P0 | `tests/test_cost_statistics_runtime_service.py`、`tests/test_cost_statistics_derived_lifecycle_executor.py`、`tests/test_settings_data_reset_service.py` | covered | month/all scope normalization、queue-only invalidation、queue unavailable不假成功、data reset durable rebuild；旧进程内 service/module/test 由 guard 禁止回归。 |
| scope gateway/legacy cleanup | P0 | `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` | covered | legacy scope normalize、非法 scope reject、production checker dry-run/apply/replacement dedupe。 |
| SQL runtime fresh/miss/stale | P0 | `tests/test_cost_statistics_sql_runtime.py` | covered | SQL read model read、PostgreSQL-first gate、Redis cache、API miss enqueue、malformed explorer payload requeue、详情 identity point lookup、production requires SQL model。 |
| parent scope aggregation | P0 | `tests/test_cost_statistics_sql_runtime.py` | covered | `active:all` / `all:all` 从两张 materialized shard row tables 聚合，不读 Workbench all payload或 child JSON arrays；parent metadata 不保存两类大数组。 |
| parent rollup / explicit force isolation | P0 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_runtime_service.py`、`tests/test_cost_statistics_derived_lifecycle_executor.py` | covered | 普通 parent 直接发布结构化 rollup，不读取 readiness、不补投历史 child；shards converged 后再次发布最终 lineage。只有显式 force parent 枚举全部当前 shards并透传 force metadata，forced month绕过 unchanged shortcut执行完整重建。 |
| App Status scope-level semantics | P0 | `tests/test_app_status_overview_service.py`、`tests/test_runtime_monitoring.py` | covered | 父 scope failed blocks；月份 shard failed/unavailable busy；scope details preserved。 |
| 首屏 SLO 探针与有界聚合 | P2 | `tests/test_http_slo_probe.py`、`tests/test_cost_statistics_sql_runtime.py` | covered | 认证态 SLO 只探测页面实际使用的 explorer；父 scope 从已物化月份 shard 聚合，不读 Workbench 全量 payload。 |
| legacy warmup / HTTP / full-view deletion | P0 | `tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_architecture_guards.py`、`tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_sql_runtime.py` | covered | warmup scheduler/retry/registry、旧 root/project route、full-view query/repository/manifest、projection Redis compat dependency 与前端 mock/type 均已删除；静态 guard 禁止回归。 |
| 前端页面交互 | P1 | `web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/bank-flow-rule-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts` | covered | time/project/bank/expense/bank-tag view、drilldown、单按钮 range picker、empty/error/refreshing/stale/failed、export center、后端导出失败消息展示、OA 登录态缺失错误展示、同一流水拆成多条成本行时项目费用类型下钻不丢行/不触发表格重复 key；真实 Chromium 覆盖 explorer 暂时 503 错误态、普通空态/表格/导出防伪成功、点击刷新后恢复 fresh 成本行，按时间首屏、按项目下钻、按银行选择银行账户/项目/流水详情、按费用类型选择费用类型/流水详情、导出中心成功下载/错误反馈、read model 非 fresh 不显示最终空态/旧项目行/旧 summary card 且禁用导出、fresh explorer 下 detail/export non-fresh 不伪成功和不下载、120+ 成本行在 390px 窄屏下按时间表/项目下钻表纵横滚动、右侧列 viewport 可见、导出入口和选择器无遮挡且无浏览器错误、Workbench 成本关系 candidate 不计入/confirmed 后计入成本、ETC 导入 confirm 后成本统计 fresh read model 与 ETC 成本行展示、bank-flow selected-row submit 后成本统计 fresh read model 与流水规则手续费成本行展示、外部往来 manual closure confirm 后成本统计 fresh read model 与闭环成本行展示，以及 settings 项目标记完成后 active scope 排除已完成项目且项目范围切换 UI 不出现。 |
| Workbench 成本关系 fan-out | P0 | `web/e2e/cost-statistics-relation-fanout.spec.ts`、`tests/test_cost_statistics_sql_projection_rules.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_workbench_relation_repository.py` | covered | Browser 已证明 open candidate 不进入成本项目/金额/明细，关联台确认 OA+bank+invoice 成本关系后成本页重新读取并展示 `智能工厂项目`、`58,000.00` 和对应流水详情。 |
| 前端 API mapper/cache | P1 | `web/src/test/CostStatisticsApi.test.ts` | covered | project scope 透传、read model status mapping、explorer 每次调用真实 fetch且无 module-level TTL payload cache、export 下载错误 JSON message 透出。 |
| 真实生产 scope cleanup `--apply` | P2 | 运维 runbook / staging smoke | documented-risk | 需要真实 Postgres 环境，只能按 runbook 只读检查后受控执行。 |

## 七类测试适用性

2026-07-16 unified readiness closure：`cost_statistics` 当前模块状态为 `READY_FOR_UNIFIED_DEPLOYMENT / DEPLOYMENT_HOLD`。`CostStatisticsQueryService` 只读 SQL read model/Redis fresh cache并拥有导出 limit/error；`CostStatisticsSqlProjectionBuilder` 是唯一成本归集 owner；miss/stale/repository unavailable 只返回 `refreshing` 并入队 `cost_statistics.read_model.refresh`。legacy live service、本地 read model、warmup job、旧 root/project HTTP/full-view 与 `ProjectDetailExportService` 均已删除。`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_cost_statistics_query_runtime_do_not_keep_legacy_live_fallbacks` 锁定这些旧链路不得回归。

2026-07-16 GSD 05-13：`CostStatisticsReadModelService`、独立测试、Application startup field/snapshot/persist callback 与 runtime local clear/invalidate/persist dependencies 已删除。projection 的单 scope repository publish shape由 SQL runtime测试保护；invalidation 只有 durable gateway 接受后才计入 `invalidated_scopes`。当时保留的 warmup bridge 已在取得生产 active/attention=0 证据后删除。

2026-07-01 modular IO 更新：`cost_statistics` 刷新链路移除旧 `cost-tax` 成本统计兼容消费者，只保留 `cost-statistics` 专用 worker；`cost-tax` 仅属于 `tax_offset` 兼容链路。`tests/test_runtime_worker_registry.py::RuntimeWorkerRegistryTests::test_cost_tax_worker_no_longer_consumes_cost_statistics_refreshes`、`tests/test_read_model_manifest.py::ReadModelManifestTests::test_cost_tax_and_turnover_manifest_preserve_summary_contracts` 和 `tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_cost_statistics_shard_convergence_reasons_do_not_bump_active_scope` 锁定 worker I/O、manifest 辅助 worker 边界和 active scope 内部分片收敛不重复 bump 的性能合同。生产性能 smoke 发现月度 projection 按裸 `scope_key` 扫描 `workbench_groups` 历史 generation，`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts` 现在锁定 active generation join、结构化 `workbench_group_rows + workbench_rows` 成本输入，并禁止继续通过 `jsonb_path_exists(workbench_groups.payload, ...)` 读取旧成员数组；`test_cost_statistics_scope_shards_are_listed_from_active_workbench_generations` 锁定父 scope shard 枚举只能来自 active `workbench_generations`。

2026-06-24 modular IO 历史上下文：`read-models:next-pilot-selection-after-tax-offset` 选择 `cost_statistics` 作为第九个非 Go read model 试点。`read-models:cost-statistics-repository-port-extraction` 当时新增 `CostStatisticsReadModelRepositoryPort` 并让 projection save 与 SQL read wiring 使用窄 port；其中当时保留的全量 load / 无条件 save 已由 2026-07-16 的 GSD 05-14 删除，当前 port 只登记 scoped reads 与 source-version conditional publish。`read-models:cost-statistics-refresh-freshness-operation-barrier-audit` 已确认 SQL fresh gate、parent aggregate、force refresh、App Status registry 和 primary `cost-statistics` worker 有本地证据。`read-models:cost-statistics-derived-lifecycle-executor-port-extraction` 已新增 `CostStatisticsDerivedLifecycleExecutor`，移除 `Application._derived_lifecycle_cost_statistics_executor(...)`，并用 `tests/test_cost_statistics_derived_lifecycle_executor.py` 与 platform guard 锁定 lifecycle invalidation、metadata 和 `enqueued_jobs` accounting。`read-models:cost-statistics-post-derived-local-implementation-closure-audit` 当时确认 warmup/retry/rebuild app 方法均为 runtime delegate，但真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred，所以当时未声明 closed；该状态已由 2026-07-05 Close 记录取代。`read-models:cost-statistics-full-state-read-model-snapshot-quarantine` 已移除 broad `_persist_state(...)` 对 `cost_statistics_read_models` 的写入，并扩展 `tests/test_read_model_architecture_guards.py` 防止 cost/tax read model broad full-state snapshot 写入回归。

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_cost_statistics_sql_projection_rules.py`、`tests/test_project_costing_service.py` | 直接覆盖 production SQL projection 的成本归因、项目范围、特殊业务链路、票据/往来排除或保留规则。 |
| 2. Service-layer tests | 适用 | `tests/test_cost_statistics_page_audit.py`、`tests/test_cost_statistics_runtime_service.py`、`tests/test_cost_statistics_derived_lifecycle_executor.py`、`tests/test_project_costing_api.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖成本专属 Audit owner、durable invalidation、runtime/lifecycle、project costing 与旧 owner删除，并静态禁止 local service/live fallback/writer 回归。 |
| 3. API contract tests | 适用 | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts`、`tests/test_http_slo_probe.py`、相关定向 E2E specs | 覆盖 explorer、transaction、export/export-preview、project scope、错误和 response shape；transaction锁定必需 `view/scope/project_scope`、非法请求400和profile-specific 409，export锁定首次/final gate同 profile。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_postgres_integration.py`、`tests/test_cost_statistics_page_audit.py`、`tests/test_postgres_migrations.py`、gateway/worker/App Health tests | 覆盖两个 dependency profile、Bank Detail直接 rows、Cost allocation CAS/parent、0123 drop、freshness fail-closed、正式 gateway→worker收敛和System Audit。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/CostStatisticsApi.test.ts`、相关 Playwright specs | 覆盖页面状态、范围、drilldown、export、错误、API mapper、标签 drawer保存零 barrier，以及详情请求透传当前 view/scope。浏览器历史覆盖保留，本轮按用户要求不重复运行183项。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_write_operation_e2e_smoke.py`、`tests/test_cost_statistics_postgres_integration.py`、`tests/test_audit_app_health_system.py`、候选生产 fixture | 本地锁定普通写零页面 fan-out、访问哪个 profile只ensure其所需scope、同scope去重、worker/App Health收敛；真实生产write→access→fresh仍在唯一候选部署后验证。 |
| 7. Existing feature regression tests | 适用 | 成本API/SQL/Audit/PG组合，加 Workbench、Bank Detail、OA App Health与前端Cost定向集 | 防止删除复制表后污染Workbench/Bank Detail/OA、旧API shape、detail/export和System Audit。当前真实PG组合231项、runner 55项、页面32项与build均通过。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 2026-06-18 | 成本统计 explorer 返回 `401 invalid_oa_session` 时，页面吞掉后端业务消息并显示泛化“成本统计数据加载失败”，导致用户误判为成本统计/read model 故障。 | `web/src/test/CostStatisticsPage.test.tsx::surfaces OA session errors from explorer loading` | covered |
| 2026-06-18 | App Health 显示成本统计已同步，但 explorer SQL/Redis payload 仍是旧 shape，缺少当前页面需要的 `summary`、`time_rows`、`project_rows`、`expense_type_rows`，导致前端 mapper 抛错并显示泛化加载失败。 | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_api_rejects_malformed_fresh_sql_payload_and_requeues`、`tests/test_read_model_query_gateway.py::ReadModelQueryGatewayTests::test_invalid_fresh_cache_payload_contract_misses_and_uses_sql_view`、`test_invalid_sql_payload_contract_enqueues_refresh_without_populating_cache` | covered |
| 2026-06-17 | 成本统计项目视图选中项目后再选择费用类型，若同一 `transaction_id` 对应多条成本行，前端用裸流水 id 作为 HeroUI Table 行 id/key，导致行身份冲突、丢行，真实浏览器可表现为卡死后白屏。 | `web/src/test/CostStatisticsPage.test.tsx::project view keeps split cost rows with the same transaction id renderable` | covered |
| 2026-06-18 | 关联台 open/proposed candidate 被误显示为成本项目或金额，或 OA+bank+invoice 成本关系确认后成本页没有重新读取并展示对应项目/流水。 | `web/e2e/cost-statistics-relation-fanout.spec.ts`、`tests/test_cost_statistics_sql_projection_rules.py`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts` | covered |
| 2026-06-19 | 成本统计 explorer 返回 `refreshing` / `stale` / `failed` 的空 payload 时，页面可能误显示最终空态、旧项目行、旧 summary card 指标或允许导出非 fresh 数据。 | `web/e2e/cost-statistics-flow.spec.ts::does not treat * read model payloads as final empty cost data`、`web/src/test/CostStatisticsPage.test.tsx::hides read model refresh details without treating empty accepted payload as final empty data` | covered |
| 2026-06-20 / 2026-07-16 | 成本统计 explorer 首屏暂时 503 时，页面可能直接显示正常空态或允许导出中心打开；旧 mount-time all-scope 参考请求还会放大首屏 I/O 并干扰失败恢复。 | `web/e2e/cost-statistics-flow.spec.ts::recovers explorer after a transient load failure when refreshed`、`web/src/test/CostStatisticsPage.test.tsx::refreshes explorer data after a transient loading failure`、`defaults to time view and loads month-aware transaction rows`、`keeps export center closed while all-scope export options are refreshing` | covered locally; all-prefetch/cache removed, real network/worker drain pending |
| 2026-06-19 | 成本统计 explorer fresh 但流水详情或导出接口返回 non-fresh 时，页面可能打开旧详情、保留旧预览或生成下载文件。 | `web/e2e/cost-statistics-flow.spec.ts::does not treat non-fresh transaction detail or export responses as successful results` | covered locally; real worker drain pending |
| 2026-06-19 | 成本统计导出中心只覆盖 row-limit 错误，缺少真实浏览器 download event、文件名、请求不带分页和导出字段保护。 | `web/e2e/cost-statistics-flow.spec.ts::downloads the current time-view cost rows with request filters and cost fields` | covered locally; real workbook open pending |
| 2026-06-19 | 成本统计在大数据/长字段/390px 窄屏下可能出现表格无法横向滚动、右侧列不可见、项目/费用类型选择器或导出入口被遮挡，或 fresh read model 行数足够但浏览器层面不可用。 | `web/e2e/cost-statistics-flow.spec.ts::keeps large cost tables fresh, scrollable, and usable on narrow screens` | covered locally; real production volume/performance pending |
| 2026-06-10 | 裸月份/裸 `all` scope 进入 durable queue，导致成本统计 worker 报 scope contract 错误并污染 App Status。 | `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` | covered |
| 2026-06-16 | 外部往来 Postgres 事务写路径绕过 scope policy，再次向成本统计投递裸 `2026-02`、`2026-03`、`all` 并造成生产 dead-letter。 | `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction`、`tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear` | covered locally; production cleanup apply pending |
| 2026-06-16 | 把成本统计误当普通分页列表处理，遗漏 explorer/summary 认证态 SLO 或让父 scope 回退读取 Workbench 全量 payload。 | `tests/test_http_slo_probe.py::HttpSloProbeTests::test_default_probes_cover_page_domains_and_known_slow_endpoints`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_rebuilds_active_all_from_materialized_shard_rows` | covered |
| 2026-07-03 | Workbench group payload 去重后，成本统计若继续从 `workbench_groups.payload` 的 `oa_rows` / `bank_rows` JSON 数组读成员，会重新依赖旧大 payload 并漏掉 metadata-only group。 | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts` | covered |
| 2026-07-01 | 成本统计月份 projection 绕过 Workbench active generation 边界，按裸 `scope_key` 扫描 `read_model.workbench_groups` 历史 generation，导致生产 `2026-06` 扫描 126k groups / 629MB JSON，并存在旧 generation 污染风险。 | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts`、`test_cost_statistics_scope_shards_are_listed_from_active_workbench_generations` | covered |
| 2026-06-10 | `active:all` / `all:all` 父 scope 错误读取 Workbench `all` 大 payload。 | `tests/test_cost_statistics_sql_runtime.py` | covered |
| 2026-06-10 | 父 scope 等待缺失/stale 月份 shard 时被伪造为 fresh。 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_app_status_overview_service.py` | covered |
| 2026-06-12 | Workbench open/proposed candidate 被当成 confirmed relation 计入成本金额。 | `tests/test_cost_statistics_sql_projection_rules.py`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts` | covered |
| 2026-06-13 | 成本税务 projection 直接从 OA 附件 parser cache 拼进项发票输入，绕过统一 Invoice repository。 | `tests/test_tax_offset_service.py::test_month_payload_includes_oa_attachment_invoices_by_issue_month`、`tests/test_tax_offset_api.py::test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_invoice_row_preserves_canonical_oa_attachment_source_metadata` | covered by shared tax/workbench boundary |
| 长期 | 月份 shard failed 误把整个成本统计主体验标红。 | `tests/test_app_status_overview_service.py` | covered |
| 长期 | SQL read model miss/stale 时 API 同步 rebuild 或返回假 fresh。 | `tests/test_cost_statistics_sql_runtime.py` | covered |
| 长期 | 导出和页面查询没有透传 project scope，或导出中心没有透传精确日期范围。 | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx` | covered |
| 2026-06-16 | 成本统计 time/project/expense_type export-preview/export 对大匹配集同步生成预览 rows 或 XLSX，拖慢 API 线程和内存。 | `tests/test_cost_statistics_api.py::CostStatisticsApiTests::test_cost_statistics_export_limit_returns_structured_error`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_cost_statistics_query_runtime_do_not_keep_legacy_live_fallbacks` | covered |
| 2026-06-16 | 成本统计下载接口收到 `cost_statistics_export_row_limit_exceeded` 等结构化错误时，前端下载路径不解析 JSON 或页面丢弃错误消息，用户只能看到泛化失败。 | `web/src/test/CostStatisticsApi.test.ts::surfaces backend row-limit messages from failed export downloads`、`web/src/test/CostStatisticsPage.test.tsx::shows backend export failure messages inside the export center` | covered |
| 2026-06-17 | 成本统计导出中心在真实浏览器中 preview/export 请求未携带当前项目范围或行数上限错误未展示。 | `web/e2e/cost-statistics-flow.spec.ts` | covered |
| 长期 | 成本统计错误纳入现金代收代付/票据购买/发票抵扣等特殊关系。 | `tests/test_cost_statistics_sql_projection_rules.py` | covered |

## 关键 smoke flows

1. `银行/发票/ETC 导入确认、bank-flow selected-row submit 或 turnover manual closure -> lifecycle/domain plan -> cost_statistics dirty scope -> cost-statistics worker -> month shard fresh -> parent scope re-enqueue -> all scope fresh -> 页面展示`；ETC、bank-flow 和 turnover 路径已有 Browser 证据断言成本页 fresh explorer 与对应成本行。
2. `Workbench relation confirm/cancel -> cost statistics invalidation -> affected month shard refresh -> App Status busy -> fresh 后恢复 -> 成本页重新读取并只展示 confirmed 成本关系`
3. `project scope setting change -> active/all scope refresh -> active view 排除已完成项目`；`web/e2e/settings-data-reset-flow.spec.ts` 已覆盖 settings 项目标记完成后进入成本统计验证 active fresh scope，`project_scope=all` 保留为后端 API/read model 合同。
4. `active:all 父 scope refresh -> 检查 month shard readiness -> 缺失 shard 入队 -> 父 scope refreshing -> shards fresh 后聚合发布`
5. `页面切换 view/date scope -> explorer API -> stale/refreshing/failed 或暂时 503 显示刷新或不可用语义 -> 不显示最终空态或旧项目行 -> 暂时 503 时手动刷新 -> fresh 后 drilldown/export`
6. `真实 Chromium 按时间首屏 -> read_export_only 打开导出中心 -> 导出 preview -> download event -> 文件名/字段/筛选断言 -> 按项目 -> active scope 项目/费用类型/流水详情下钻 -> 导出 row-limit 错误反馈`
7. `真实 Chromium 390px 窄屏 -> 120+ 成本行 fresh explorer -> 按时间宽表横向/纵向滚动 -> 右侧列 viewport 可见 -> 按项目选择长项目/费用类型 -> 项目对应流水表横向/纵向滚动 -> 无 console/page/request/dialog 错误`

## 本模块验证命令

最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_service tests.test_project_costing_service tests.test_project_costing_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_page_audit tests.test_audit_page_business_read_model_tool tests.test_operations_audit_service tests.test_operations_audit_report tests.test_page_audit_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api tests.test_cost_statistics_runtime_service tests.test_cost_statistics_derived_lifecycle_executor -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v
PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service tests.test_runtime_monitoring -v
PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe.HttpSloProbeTests.test_default_probes_cover_page_domains_and_known_slow_endpoints -v
cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx
cd web && npx playwright test e2e/cost-statistics-flow.spec.ts
cd web && npx playwright test e2e/cost-statistics-relation-fanout.spec.ts
cd web && npx playwright test e2e/imports-etc-invoices-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/turnover-ledger-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts --project=chromium
cd web && npm run e2e:smoke
bash scripts/verify.sh docs
```

扩展回归按改动选择：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_import_job_queue tests.test_derived_data_lifecycle_service tests.test_workbench_v2_api tests.test_turnover_workbench_integration -v
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api tests.test_tax_offset_api tests.test_input_invoice_usage_api -v
cd web && npm test -- --run src/test/AppHealth*.test.tsx src/test/WorkbenchSelection.test.tsx src/test/TaxOffsetPage.test.tsx
PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend Vitest、deterministic Playwright smoke 和 build，覆盖完整成本统计、App Status、read model gateway、前端测试集、成本统计 browser 主流程和 Workbench→Cost 访问时两阶段收敛。单轮模块验证只跑最小闭环。

## 未测风险

- 本轮不连接真实生产 PostgreSQL 执行 `scripts/check-read-model-scope-contracts.py --apply`；发布前后需先 dry-run JSON 报告，再按 runbook 受控清理。
- 本地真实 PostgreSQL已跑 gateway→worker→App Health/System Audit，但未模拟生产 RabbitMQ/Redis/systemd并发。候选部署后仍须分别证明 OA allocation view 的 Workbench→Bank Detail→Cost收敛，以及 `time|bank_tag` 仅 Bank Detail收敛且零 Cost event。
- 本地已覆盖成本统计超过 20,000 行同步导出 fail-closed、导出中心错误反馈，以及 120+ 行窄屏宽表滚动/控件可用性；真实浏览器文件打开、真实生产超大数据查询/下载耗时和生产视觉性能仍需 staging/manual smoke。

## 2026-07-24 all scope 子分片 freshness 门禁

- `tests/test_workbench_sql_runtime.py`：单月与批量 canonical Workbench source-version proof 共用同一 set-based SQL；批量月份去重、非法 scope fail-fast，并覆盖全部 canonical 写表与固定规则版本。
- `tests/test_cost_statistics_sql_runtime.py`：Cost all 访问先批量比较 canonical→active Workbench generations，只 enqueue 全部且仅 stale Workbench 月份；Workbench fresh 后，repository gate 逐月比较 Cost child 的 Workbench/Bank Detail lineage 与 parent `source_shards`，只 enqueue 精确 stale Cost child。concrete month 主表保持当前月 freshness，但同页全期间 statistics 也使用 parent-child proof；其它月份 drift 时 statistics fail-closed 并 ensure exact child，不把当前月 rows 伪装 stale。
- `tests/test_batch_accounting_postgres_integration.py`：真实 PostgreSQL 下批量 Workbench proof 必须与逐月 proof 完全一致；`tests/test_cost_statistics_postgres_integration.py`：真实 PostgreSQL 制造 child Workbench lineage drift，证明 parent fail-closed 并返回精确 child scope。
- `tests/test_read_model_manifest.py`：锁定 Cost repository port 的 bulk active Workbench version I/O；不新增 endpoint、worker、queue、registry、cache 或第二套刷新协调器。
- 真实数据库结果：CI 因未配置 `FIN_OPS_TEST_DATABASE_URL` 明确跳过 PostgreSQL 集成；随后使用显式 host 的一次性本机 PostgreSQL 应用全部 migrations，首次发现并修复无 dirty row 时 SQL 三值逻辑漏报，复跑 `tests.test_cost_statistics_postgres_integration` 与 `tests.test_batch_accounting_postgres_integration` 为 `12/12`，临时库自动删除。
- 发布后门禁：使用 test-owned 可逆 relation fixture，在不预读 concrete child 的前提下访问 Cost all；必须由 all GET 自身发现 drift、只生成 exact month/child refresh、`<=3s` 收敛为 fresh，随后 System Audit `16/16`。同时分别量测 all 与 concrete-month warm p95/p99，证明包含 global statistics child proof 后仍满足页面 SLO。

## 2026-07-23 relation 后访问时可见性门禁

- `tests/test_cost_statistics_sql_runtime.py`：先检测 canonical Workbench expected/active version；上游 stale 只 enqueue 精确 Workbench 月份且停止 Cost I/O，上游 fresh 后 Cost stale 才 enqueue 当前 Cost scope。
- `tests/test_workbench_sql_runtime.py`：Workbench generation publish 完成不触碰 Cost queue，不产生 `workbench_shard_published`。
- `web/src/test/CostStatisticsPage.test.tsx`：relation 提示后只调用 normal explorer GET，明确断言零 operation barrier；refreshing 进入 3s 有界自身重试。
- `tests/test_platform_runtime_boundary_guards.py`：机械禁止 relation/turnover/Workbench publish 恢复 Cost fan-out，并要求 query owner 的两阶段依赖 I/O。

下方 2026-07-18 条目是历史 delta 合同验证记录，已被上述当前门禁取代；它不得被用来恢复普通写后 Cost fan-out。

## 2026-07-18 relation 写后 all 可见性历史门禁（已取代）

- `tests/test_workbench_uow_contract.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_ledger_api.py`：有完整 case/row identity 的正式 relation transaction 必须在同一提交内直投 `cost_statistics_relation_delta`，且 metadata 按 case 保存 active/cancelled；无完整 identity 不得猜测或投递无身份 direct Cost。
- `tests/test_runtime_queue.py`：`relation_deltas` whitelist、同 scope 不同 case 合并、同 case 后写覆盖、非法/超限 fail-closed，以及敏感/未知 metadata 不进入 outbox。
- `tests/test_workbench_sql_runtime.py`：只有 Workbench exact-version publish 成功且仍 current 后才投递 `workbench_shard_published` 收敛事件；成本 enqueue 失败不得完成 Workbench dirty；无 trace 时以 Workbench event id 建立 causal trace。
- `tests/test_cost_statistics_sql_runtime.py`：active/cancelled/mixed-case 精准替换、目标 Workbench rows 未发布时拒绝、Cost 自有 bank-flow 标签点查、精确 source-version CAS、scope 内行版本证明同步，以及 parent 只读 shard metadata + SQL aggregate；普通事件仍走全月重建，month→parent 保留 tenant/priority/trace。
- `web/src/test/CostStatisticsPage.test.tsx`：all 视图收到重复 relation event 后只等待 `active:all`，等待前取消页面自有请求，barrier fresh 后只读取一次并解除既有 inert overlay。
- `tests/test_write_operation_slo_audit.py`、`tests/test_write_operation_e2e_smoke.py`：relation receipt 必须包含 exact delta；Cost all 同时证明 fresh、source versions、业务断言和 delta month→`active:all` causal timeline，旧 release 只允许以 `workbench_shard_published` 作为兼容观测，不是新写入 fallback。
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_relation_cost_refresh_has_transactional_delta_and_publish_convergence_owners`：机械禁止 Cost projection 读取 canonical relation repository、旧无身份 direct reason、隐藏 scope expansion、第二 Cost 路径与前端退回通用 App Status。

## 2026-07-18 relation delta 完整性与语义 freshness 回归

- `tests/test_cost_statistics_postgres_integration.py`：真实 PostgreSQL 验证 delta 事务在精准替换行后原子保存完整 summary/project/expense/bank-flow metadata；parent 聚合从当前 shard 结构化 rows 输出同一完整小型 payload，不加载旧 row arrays。
- `tests/test_cost_statistics_sql_runtime.py`：repository 窄 aggregate port、parent 复用、直接月份 event id→parent trace、Bank Detail 执行计数/内部 relation lineage 变化但内容签名不变时仍 fresh，以及 Bank Detail 业务 signature 变化仍 mismatch；Cost 直接依赖的 Workbench 版本不做归一化。
- `tests/test_cost_statistics_page_audit.py`：Audit 的 Bank Detail upstream proof 只排除嵌套执行计数和内部 relation lineage，保留其它 source-version equality、未知字段 fail-closed 与既有全量业务/summary/group proof。
- 生产复验门禁：confirm 与 withdraw 分别证明 exact direct delta→`active:all` `<=3s`，Cost explorer `200/fresh` 且业务断言变化；每次操作的所有 consumer 收敛后，Cost/Workbench/OA 三页面必须各自 `pass/fresh/drained`。系统级其它页面的既有问题必须单独报告，不能拿来替代或掩盖三页面证据。
