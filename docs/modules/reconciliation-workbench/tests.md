# 关联台测试与验证

日期：2026-07-28

## 2026-07-28 逐栏折叠、普通行直显与搜索真实预览

- Business core：`no_oa_bank_batch` 与普通关系保留全部真实行；`bank_flow_rule_batch` 只有银行成员数 `>3` 才生成银行栏 summary/collapsed rows，1 到 3 行直接显示；ETC 仍只折叠发票栏。
- Repository/read model：summary page 不再把普通银行/发票行截成 3 行；无搜索的折叠栏只传 summary + count，搜索时最多传 3 条真实命中 collapsed rows。schema v10 淘汰旧 generation/page cache，不新增表、worker、cache 或 API。
- API/Frontend：group detail 按 `collapsed_row_counts.<pane>` 逐栏验证；ETC 的 OA/银行栏验证正常 rows，发票栏验证 collapsed rows。闭合态搜索直接渲染真实命中行并高亮，不显示“隐藏内容命中”、不自动展开或预取详情。
- Regression：普通多行与 legacy no-OA 不出现通用“还有 N 条，展开”；bank-flow 与 ETC 保留 click-only detail、失败可重试和同 generation fail-closed。

## 2026-07-28 日常报销付款明细复合行

- Backend/API：`tests/test_workbench_query_service.py` 保护父 OA 行只发布精简稳定付款明细字段，附件发票继续携带显式 `source_expense_item_id`；不新增 relation member 或独立配对对象。
- Frontend：`web/src/test/WorkbenchApi.test.ts` 保护 item/source ID DTO；`WorkbenchColumns.test.tsx` 保护申请类型移入申请人栏并清理项目栏 process/evidence chip；`RelationGroupGrid.test.tsx` 保护“多个项目 · N + 父 OA 金额”、逐项项目/金额、附件发票同带对齐，以及点击子项仍只选择父 OA。
- Read model：Workbench schema 升级为 v8，使旧 generation/page cache 失效并经现有 exact/all freshness gateway 重建；没有新增表、worker、cache 或第二 read model。

## 2026-07-26 relation preview 真实 DTO、并发反馈与安全错误回归

- `web/src/test/WorkbenchApi.test.ts` 使用真实 confirm-before / withdraw-after `selection + zone/status=unpaired` fixture，证明 preview-only adapter 保留 `rawGroupType=selection`、正式页面仍映射为 unpaired，非法 selection fail closed，普通 groups mapper 继续拒绝 selection。
- `web/src/test/WorkbenchSelection.test.tsx` 与 `web/src/test/WorkbenchZone.test.tsx` 用受控未 resolve Promise 证明 confirm/withdraw 在下一 render 已显示可访问 busy 状态，pending 期间重复点击只产生一次 POST，selection/version 漂移响应不会打开 drawer，失败后入口恢复且后端英文/parser sentinel 不进入 UI；既有 formal submit drawer 回归保持通过。
- Workbench API 安全错误矩阵覆盖 stale/version conflict、row unavailable、401/403、409、invalid preview、5xx 与 non-JSON response；只允许批准的中文文案，同时保留 `status/code/requestId` 支持字段。
- `web/e2e/workbench-relation-fanout.spec.ts` 与 `web/e2e/workbench-withdraw-flow.spec.ts` 的 Chromium fixture 使用真实 selection DTO，覆盖 confirm/withdraw pending、成功 drawer/关闭和失败恢复；本次不运行无关 Browser suite。

## 2026-07-25 关联台写后恢复读放大回归

- `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests::test_refresh_status_uses_fast_freshness_status_instead_of_heavy_diagnostic` 证明公开 refresh-status 优先使用既有轻量 groups freshness port，完整 generation/outbox/worker diagnostic 不进入页面轮询热路径；旧 repository fallback 与 timeout 合同保持。
- `web/src/test/WorkbenchSelection.test.tsx` 的 withdraw 完整恢复用例把 combined initial 保持为一次 recovery trigger 和一次最终 fresh payload，共 2 次；中间 refreshing 只调用轻量 refresh-status，最终仍验证 OA、银行、发票分别恢复为完整 unpaired singleton。
- `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_filters_workbench_groups_page_from_structured_group_rows` 锁定 active-member CTE 为 `NOT MATERIALIZED`，防止 all-scope 条件查询恢复“先复制全部 active members、再应用搜索/筛选”的优化屏障；同文件搜索、pane/列/时间、total/row counts/matching ids 回归继续保护原业务语义。
- 现有 Workbench Selection 全文件继续覆盖 confirm operation projection、withdraw blocking UI、generation version conflict、failed/stale 状态、权限、筛选和详情交互；没有增加 retry fallback、第二轮询器或放宽 fresh 判断。

## 2026-07-25 访问时 exact Workbench proof 与 consumer 隔离

- `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_all_freshness_returns_only_exact_canonical_mismatch_scopes` 证明 `month=all` 使用 canonical/active-generation bulk proof，只返回真实变化月份。
- `tests/test_workbench_sql_runtime.py` 的 relation-preview selection 合同证明 selected row 查询使用 generation/scope/`row_id=ANY`，OA attachment context 仍绑定同一 generation，并对 missing、duplicate、non-fresh 和 version drift fail closed。
- `tests/test_workbench_write_characterization.py` 与 `tests/test_workbench_auth_context_idempotency.py` 证明 confirm/withdraw preview 每请求只调用一次 bounded selection，旧 full-payload/alias/withdraw row resolver 一旦调用即失败；formal confirm/withdraw 把 preview callable 设为一旦调用即失败后仍通过 canonical command/UoW。
- disposable PostgreSQL fixture（month/all、2/6/20 rows、active/obsolete generations、OA/银行/发票及 attachment context）旧/新各 10 次证据：旧 full-payload preview p50 为 `12.699–222.378ms`、p95 为 `12.902–248.509ms`；新 bounded preview p50 为 `0.728–2.930ms`、p95 为 `0.755–3.516ms`，每次固定 6 条测试计数 SQL、完整 payload copy/scan 为零。EXPLAIN 证明 month bulk 命中 `workbench_rows_generation_scope_row_uidx`（3 rows、10 shared hits、0 reads），all generation-set join 同样命中该索引（3 rows、19 hits、0 reads），无需 migration/index。
- `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests::test_searched_initial_all_page_enqueues_only_exact_workbench_mismatch_scopes` 证明带搜索的 combined initial 也必须先通过 freshness gate，只入队 exact Workbench scopes，不得因查询不可缓存而退化成 `api_initial_page_stale -> workbench:all`。
- `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests::test_month_initial_does_not_enqueue_unrelated_all_statistics_scopes` 证明单月页面只读取 all-period 统计 generation 状态用于 cache/fail-closed，不得因此入队其它月份。
- 关联台不消费 `workbench_relation` distribution，已删除 combined initial 的 relation dependency callback、阻塞、状态字段和双投递；其它实际消费者的 relation gate 不变。
- `tests/test_app_postgres_mode.py`证明access enqueue只在既有active projection存在时附canonical `freshness_token`，并复用调用方已计算的expected versions、不重复canonical proof；missing projection仍按普通enqueue自愈。`tests/test_runtime_queue.py`与真实PostgreSQL integration证明同target并发/完成窗口去重、A→B→A latest-target语义、不同target follow-up及failed dirty恢复。
- `tests/test_platform_runtime_boundary_guards.py`、Workbench write/idempotency/stale与Batch Accounting回归机械禁止`_schedule_workbench_read_model_persist`、后台rebuild线程、旧async env和测试monkeypatch重新进入生产/测试链路。

## 2026-07-24 Workbench generation 批量发布回归

- `tests/test_workbench_sql_runtime.py` 证明 rows、groups、group_rows 三张热点 generation 表使用同一事务内 PostgreSQL `COPY`，旧多值 `INSERT` 不再承担这三段写入，activation 仍在全部数据成功后执行。
- `tests/test_postgres_connection.py` 覆盖 `copy_rows(...)` 的 cursor 生命周期、typed row 传递与计时边界；`tests/test_postgres_state_store_integration.py` 在 disposable PostgreSQL 证明 JSONB、数组、日期、numeric 行真实落库后才激活 generation，并证明任一 COPY 中途失败会回滚全部 payload、保留一条既有 `failed` 诊断且绝不留下 active 状态。
- 没有新增第二 writer、staging 表、缓存或 worker；不支持 `COPY` 的测试连接保留既有批量写 fallback，生产 psycopg 只走原生 COPY。

## 2026-07-22 Turnover 人工闭环冻结要求分区回归

- Business core：`turnover_manual_closure` active relation 只拥有同组关系，不无条件代表完成；OA/发票四种冻结 requirement 组合按 OR 聚合，未知、空或缺失 snapshot fail closed。要求 OA 的 bank-only case 保持完整 unpaired，补齐要求后才以同 case paired；`batch_accounting` 与 ETC 显式完成合同保持隔离。
- Service/API：Turnover 人工确认复用同一次 selected-row 快照，并且只读取一次 canonical rule payload，冻结 tag code、OA/发票布尔值、来源和版本；合并后的任一 bank member 不在 selected ids、bank row 缺失/重复或规则无效时 UoW 不打开。deterministic 写入的既有冻结合同不变。
- Read model/Audit：SQL projection、写后 operation projection 和 preview 复用 relation 自身冻结要求；Page Audit 独立发现缺快照与错误 zone；本次不改变共享 projection schema、scope、worker 或 cache。
- Frontend：API mapper 保留显式 false、缺字段保持缺失语义；不完整 relation 的空 pane显示“待补 OA/发票”。生产组件与页面请求 I/O 未改变。
- 旧链回归：no-OA 规则保存不再扫描并追溯回写既有 Turnover relation；普通 manual、deterministic、batch accounting、ETC、合并与撤回测试共同防止其它页面分区被放宽。

## 2026-07-20 折叠流水详情惰性加载回归

- Repository：production-shape materialized group 只有银行成员时，group detail 仍必须返回 `oa_rows=[]`、完整 `bank_rows`、`invoice_rows=[]`，且折叠计数与明细成员一致。
- API client：HTTP 200 若缺少任一 pane 数组、group identity 不一致，或逐栏声明成员数与实际详情不一致，必须 fail-closed，不能把不完整 payload 安装为可展开数据；有 `collapsed_row_counts.<pane>` 的栏校验 collapsed rows，其它栏校验正常 rows。
- 前端交互：页面加载和 group 更新不得自动预取折叠明细；用户点击后只发一次详情请求，成功后展开，失败后保持折叠并显示可重试状态。
- E2E：首屏只显示 3 条流水摘要时不请求详情；用户点击“展开 4 条明细”后恰好请求一次 group detail，并渲染 4 条完整流水。

## 2026-07-20 Turnover 撤回 preparation 隔离回归

- `tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_prepared_withdraw_reuses_lock_relation_snapshot_and_freshness` 保护同一 service/transaction 的 preparation 复用一次 lock/scoped snapshot/freshness。
- `test_prepared_withdraw_rejects_a_different_case` 保护 preparation 不得跨 case 使用；普通 Workbench withdraw 不传 preparation，既有测试继续覆盖原调用合同。

## 七类测试

| 类别 | 适用 | 主要覆盖 |
| --- | --- | --- |
| 1. Business core | 是 | 确定性证据、365 日边界、N:M:K exact-sum、歧义/金额-only/红冲 fail-closed、撤回阻断指纹、paired/unpaired 精确分区 |
| 2. Service layer | 是 | repository 输入、orchestrator 单 UoW、幂等、rollback、history、普通 relation 写零 dirty/outbox、旧状态清理 |
| 3. API contract | 是 | paired/unpaired shape、分页/search/detail、confirm/withdraw、版本冲突、权限、unknown state fail-fast |
| 4. Read model/cache/worker | 是 | active generation 原子发布、freshness、all-scope 组合、exact generation stats、stats 缺失/发布竞态 fail-closed、bulk refresh、旧 generation 不冒充 fresh |
| 5. Frontend interaction | 是 | 两区渲染、singleton 未配对、选择/preview/撤回、loading/empty/error/stale、权限与分页 |
| 6. End-to-end | 是 | canonical import/OA -> matching -> formal relation；当前页访问触发 Workbench fresh 后 paired；withdraw -> 当前页访问后 singleton unpaired；跨页访问时独立收敛与非消费者隔离 |
| 7. Regression | 是 | 520 样例、13 张发票、ETC/OA 附件、no-OA、batch accounting、turnover、cost/search/invoice lifecycle |

## 核心固定测试

- `tests/test_workbench_free_matching_engine.py`
- `tests/test_workbench_formal_relation_repository.py`
- `tests/test_workbench_matching_orchestrator.py`
- `tests/test_workbench_relation_grouping.py`
- `tests/test_workbench_relation_alignment_service.py`
- `tests/test_workbench_sql_runtime.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_workbench_query_service.py`
- `tests/test_postgres_migrations.py`
- `web/src/test/RelationGroupGrid.test.tsx`
- `web/src/test/WorkbenchApi.test.ts`
- `web/src/test/WorkbenchSelection.test.tsx`
- `web/src/test/WorkbenchWriteGate.test.ts`
- `web/src/test/WorkbenchZone.test.tsx`

## 必须保护的不变量

- 520 元历史 case 前缀不影响 active relation 进入 paired。
- 13 张合计 1709.49 元发票保持 13 个 unpaired singleton。
- `paired ∩ unpaired = ∅`，`paired ∪ unpaired = canonical identities`。
- 装饰字段、输入顺序和旧 candidate/decision metadata 不改变 membership/group id。
- OA 附件来源 alias 与 canonical OA row id 不同的情况下，正式关系 alignment 仍指向 canonical OA；复合行只按显式 source item + 唯一 row index 映射 canonical expense item id，且不修改 canonical 发票来源字段。
- 同金额竞争、exact single 与 exact sum 竞争、duplicate reference、currency/direction mismatch、fuzzy/date-only evidence 均不写关系。
- 显式引用跨全部历史；组合证据 365 天接受、366 天拒绝。
- 超过六个成员和 2:2:2 均能在有界唯一闭合时形成一条正式关系。
- UoW 失败时 relation、history、idempotency 和 outbox 不得半写入。
- source payload 即使把无 active relation 的 row 放在旧 paired section，最终也必须降级为 unpaired singleton。
- E2E mock 不得用共享历史 `case_id` 构造未配对组；每区单一搜索词必须扫描该区三类结构化行，任一行命中后保留完整组上下文，隐藏 pane 与折叠明细也必须可命中。
- 未配对 canonical row 若携带旧 `candidate:` / `decision:` / `temp:` ownership，输出必须清理与该候选 ownership 绑定的 mode 装饰且仍保持 singleton；control owner 优先级必须是 active formal relation > active override > active exception。正式关系成员不能携带旧 override/exception decoration；未配对 row 的 active override 必须优先于同 row exception，`pending_input_invoice` 等合法 control fields 必须与 canonical override 精确一致。回归测试必须同时覆盖最终 `workbench_rows.payload` 写入形状和 Page Audit SQL 的相同优先级。
- ETC collapsed-summary 必须同时物化 summary row 和全部 invoice detail rows；paired/unpaired 只改变 zone/status，不得丢失、重复或隐藏明细。
- Workbench groups page cache schema 必须与 projection schema 同步，projection 行为升级后旧 Redis payload 必须自动失效。
- combined initial 两区首屏必须各为 50 groups、`has_more` 保留真实 total，默认 batch SQL 每区读取最多 51 条用于判定后续页；前端不得显示“已加载 N / total”或手动“加载更多”，仅在 fresh、查询稳定且用户滚动接近区域底部时自动请求下一页；同区请求必须去重，搜索/筛选/version 变化时旧响应不得并入新结果，失败后停止自动重试并提供显式重试。后续 `/groups` 必须绑定同一 `expected_read_model_version`，不得为性能退回 200-group 首屏或全量 payload。
- 默认无筛选 all-scope `/groups` 的 total/row_counts 必须来自当前 active-month generation-set digest 对应的两条 `workbench_generation_stats`；统计缺失或查询前后 digest 改变时返回 refreshing，不得执行旧的全量 distinct row count。月 generation 发布与该统计必须处于同一事务，多个 scope 同批发布只生成一次最终 digest 统计。
- all-scope 区域搜索、来源、pane/列/时间筛选必须只 materialize active generation key，条件之间按既有 AND/OR 语义相交；total、row counts、matching group ids 在一条计数 SQL 中得到，分页只按 matching ids 读取 payload。搜索必须覆盖展示字段、排除内部 identity/detail-only 值、转义 ILIKE 通配符并限制 200 字符。测试必须断言 SQL 不读取 `g.*`/payload/raw payload，不 join 历史 physical all group，且不为 count/page 重复执行 member 条件。
- 前端必须断言每区只有一个 HeroUI `SearchField` 且位于区域 header 同行；输入时使用既有 deferred combined initial 单请求，等待期间保留当前稳定结果并显示 pending，失败可重试。所有可见命中片段都高亮；只命中折叠明细时仍返回对应关联组，但闭合态只显示摘要，不显示折叠成员且不发详情请求。搜索和非搜索状态下，ETC 发票与流水规则批次都只能由用户显式点击展开；收起后必须恢复摘要，搜索切换期间完成的旧详情请求不得重新展开新结果。
- 搜索框在首个 combined initial 完成前已可输入时，不得提前消费新的 zone query key；初始稳定数据安装后必须补发包含该 query 的 combined initial 请求，不能只对首屏 50 组做本地高亮并漏掉其它组或折叠明细。
- 关联台 Audit 绿色结果必须绑定 active Workbench read-model version + 页面 freshness status；generation/status 改变立即清除旧绿色结果。`workbench_matching_scope_not_converged` 属于 freshness+queue 阻断，`workbench_generation_source_versions_mismatch` 属于 freshness 阻断。
- matching source-version 回归必须证明纯 Workbench projection schema 不进入 matching provider；bank-flow/no-OA read-model provider 仍保留自身所需的 Workbench projection dependency。失败 scope 运维重试必须覆盖 dry-run 零写、fingerprint drift 零写、非 failed 拒绝和 exact month 单次 durable requeue。
- 普通标量列的同列多选必须按 OR，`全选`不能把结果清空；不同列/不同 pane 继续按 AND，银行金额表头的方向+付款账号复合筛选继续要求同一行同时满足。前端本地过滤、HTTP mock、repository SQL 和 summary preview 必须使用同一合同。
- group detail 必须稳定输出三个 pane 数组；展开 Promise 只有在同一 active read-model version 的完整详情已安装后才能成功。详情保持 click-only lazy load，禁止恢复 mount/update 自动预取或静默吞错。

## 验证命令

```bash
python3 -m pytest -q \
  tests/test_workbench_free_matching_engine.py \
  tests/test_workbench_formal_relation_repository.py \
  tests/test_workbench_matching_orchestrator.py \
  tests/test_workbench_relation_grouping.py

python3 -m pytest -q \
  tests/test_workbench_sql_runtime.py \
  tests/test_workbench_query_facade.py \
  tests/test_workbench_v2_api.py \
  tests/test_workbench_query_service.py \
  tests/test_postgres_migrations.py

# 需设置一次性本地 FIN_OPS_TEST_DATABASE_URL
python3 -m pytest -q \
  tests/test_postgres_state_store_integration.py::PostgresStateStoreIntegrationTests::test_workbench_all_groups_use_exact_generation_stats_and_fail_closed_when_missing

cd web && npm test -- --run \
  src/test/RelationGroupGrid.test.tsx \
  src/test/WorkbenchApi.test.ts \
  src/test/WorkbenchSelection.test.tsx \
  src/test/WorkbenchWriteGate.test.ts \
  src/test/WorkbenchZone.test.tsx

bash scripts/verify.sh lint
bash scripts/verify.sh docs
```

发布后：

```bash
scripts/with-production-admin-token.sh python3 scripts/rehydrate-workbench-read-models.py
scripts/with-production-admin-token.sh python3 -m fin_ops_platform.tools.audit_workbench_relation_display --month all
```

生产命令的实际参数和 release 环境以 `docs/operations/runtime-worker-governance.md` 与 deploy control 为准；不得输出 token。

## 数据安全验收

- migration 前后 canonical OA/银行流水/发票 counts 与金额 checksum 不得减少。
- migration 不修改 `app.workbench_pair_relations` 或 history。
- rehydrate 只发布新 generation，不原地改旧 generation。
- Audit 必须证明满足冻结 requirement 的 active relation typed members 与 paired display 双向相等；未满足 requirement 的 active relation 必须保持同 case、显式 incomplete 并进入 unpaired；无 active owner 的其余 canonical facts 全部 singleton unpaired。
- 520 case、发票号和 OA row id 必须在 fresh generation 中同组；13 张样例必须完整可见。

## 2026-07-28 OA 子项对齐与完整性回归

- `tests/test_mongo_oa_adapter.py`、`tests/test_workbench_query_service.py` 保护来源费用内容/费用说明分别保真并进入 Workbench DTO，既有 `expense_content` 口径不变。
- `tests/test_workbench_relation_grouping.py` 保护普通 OA+发票 active relation 缺银行时保持同 case、进入 `unpaired` 并报告 `missing_row_types=["bank"]`；batch-accounting/ETC 豁免不回归。
- `web/src/test/WorkbenchApi.test.ts`、`web/src/test/RelationGroupGrid.test.tsx` 保护发票只按 exact `source_expense_item_id` 对齐，输入乱序不影响付款项顺序，费用内容/说明在申请事由列显示，点击子项仍选择父 OA。
- Workbench month/all schema 升至 v9，旧 v8 generation 与 page cache 必须返回 builder mismatch 并经既有 freshness gateway 重建。

## 2026-07-22 Workbench v6 与历史修复回归

- `tests/test_workbench_sql_runtime.py` 证明当前 month/all v7 同步，groups/initial cache key 随 schema 派生失效，旧 v6 source version 返回 `builder_mismatch`，不能作为 fresh generation 消费。
- requirement repair 测试证明 legacy Turnover active relation 的完整 preimage/intended after fingerprint、partial execute、exact metadata rollback、partial rollback retry 和 drift zero-write；普通 relation、ETC、batch 与 inactive relation 不受影响。
- 既有 grouping/projection/query 回归继续证明：要求 OA 的 bank-only case 保持同 case unpaired，补齐 OA 后进入 paired，active generation 只经现有原子 publish 边界切换。
- `tests/test_audit_workbench_relation_display_tool.py` 同步保护审计口径：`turnover_manual_closure` 不再享有旧的 requirement 豁免；缺 OA 的 bank-only closure 在 unpaired 不报警，若出现在 paired 必须报告 `relation_requirement_partition_mismatch`。
- `tests/test_workbench_dirty_queue_wiring.py` 证明 v6 展示 schema 不再污染 matching stale scan，同时 bank-flow read-model source versions 仍包含展示 schema；`tests/test_workbench_matching_scope_retry_ops.py` 保护生产失败 scope 的精确、fingerprint-guarded durable retry。

## 2026-07-22 Workbench 写入门禁与 OA 同步恢复回归

- `web/src/test/WorkbenchWriteGate.test.ts` 保护权限、系统写安全、OA dirty/refreshing、read model non-fresh 和缺 active generation version 的单一优先级门禁。
- `web/src/test/WorkbenchSelection.test.tsx` 保护已选 OA + 银行流水在 OA 同步期间禁用确认/异常操作并展示真实原因；关联台专属 `/api/oa-sync/status` 返回 synced 后，即使全局 App Health 仍是旧 dirty 快照，也必须在既有 3 秒轮询周期内自动恢复按钮且保留同 generation 选择。
- `web/src/test/WorkbenchZone.test.tsx` 保护选择区禁用原因的可见与可访问输出；`web/e2e/workbench-stale-error-flow.spec.ts` 保护 Chromium 下 OA dirty/refreshing 的按钮、提示和零 mutation 请求。
- 性能不新增 I/O：门禁复用既有 OA status 轮询和已加载的 Workbench page status/version，不新增 API、轮询器、worker、read model 或跨页面状态。

## 2026-07-25 Workbench active-refresh polling 回归

- `tests/test_workbench_sql_runtime.py` 证明 exact scope 有 `pending/processing` outbox event 时直接返回 `refreshing`，不重复执行全月份 canonical proof或 schema scan；dirty 没有 active event 时标记 stale并返回 exact re-enqueue scope。

## 2026-07-25 - v7 complete canonical proof 与 active-flight 合并

- `tests/test_workbench_sql_runtime.py` 覆盖 Application 复用同一个 projection builder、重叠同 scope proof 只执行一次数据库读取、完成后独立访问重新查询、失败 flight 清理可重试、month/all v7 拒绝 v6，以及 composed all proof 保留全部业务字段。
- `tests/test_workbench_etc_relation_enrichment_postgres.py` 在 disposable PostgreSQL 证明 ETC 四表、bank/invoice soft delete、跨月 member 更新、relation withdraw 和 consumed bank settings 都会改变正确 scope proof；无关 settings 不污染 proof，migration `0125` 两个 identity 索引已应用。
- 当前候选没有改 HTTP shape、权限或前端交互；本条不新增重复前端测试。页面双开、写后零 fan-out、access-to-fresh `<3s`、Audit/queue/worker 与 fixture 恢复由最终生产矩阵负责。
- `tests/test_workbench_relation_sql_projection.py` 证明 `turnover_manual_closure` 保留在 Workbench 主 generation 的 canonical 输入，但不进入共享 `workbench_relation` distribution。

## 2026-07-25 - 并发恢复窄 OA I/O 与真实首屏验证

- `tests/test_workbench_query_service.py` 证明 exact/all scope 只返回 OA rows、all scope 继续使用既有 bulk adapter，且不构造 grouped Workbench payload。
- `tests/test_workbench_sql_runtime.py` 证明 generation builder 每个 scope 只调用一次 `list_oa_rows(...)`，附件父 OA 按既有 row-id/SQL fallback 补载，最终 projection shape 不变。
- `tests/test_write_operation_e2e_smoke.py` 与 `tests/test_write_operation_impact_matrix.py` 证明 relation consumer 使用 combined initial 的真实业务 zone：普通完整关系 confirm 在 `paired`，冻结要求未满足的 active Turnover closure 与 withdraw/recovery 均在 `unpaired`；并拒绝把 `/groups` 注册为关联台页面首屏。
- 本地 10,000 OA-row characterization 的旧路径中位数为 `145.809ms`，窄 I/O 为 `84.885ms`，重复组装/序列化 CPU 减少约 `41.8%`；该合成数据只证明共享 worker CPU 路径改善，不替代部署后真实 worker、首屏和总恢复耗时。
- 本次未改前端组件、交互或 HTTP response shape，不重复运行无关 183-browser suite；生产用同一类 test-owned 可逆 relation fixture 验证真实 combined initial、zero fan-out、queue/worker drain 与 System Audit。

## 2026-07-25 - exact/all 并发恢复禁止暂态 all fan-out

- `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests::test_initial_all_page_does_not_fan_out_while_exact_refresh_is_active` 复现生产并发形状：exact scope 已 processing，all freshness 暂时返回 `stale + active_refresh_in_progress` 且没有新的 exact target。
- 回归断言 all 请求返回 non-fresh 轻量状态但不 enqueue `workbench:all`；已有 exact 任务完成后，下一次页面轮询重新执行 canonical proof 并只 enqueue 剩余 mismatch 月份。
- 既有 `test_initial_all_page_enqueues_only_exact_workbench_mismatch_scopes` 继续保护稳定态 exact targets；冷启动/missing 且没有 active refresh 时仍保留正式 `all` 恢复入口。
- `test_default_initial_page_version_drift_fails_closed_without_caching_old_payload` 继续断言 generation-set 切换时不返回、不缓存旧 payload；同时锁定该正常发布竞态不再 enqueue `workbench:all`，下一次请求直接读取新的 active generation-set。

## 2026-07-26 - Candidate 可逆 runner 的 bounded preview 采样

- `tests/test_write_operation_e2e_smoke.py` 保护既有可逆 runner 的 `--relation-preview-samples`：默认 1、上限 20；生产候选使用 10。confirm/withdraw 的每个 sample 都经过 canonical preview DTO 校验，但每个 checkpoint 仍只允许一次正式 mutation。
- withdraw 的正式提交只消费最后一次成功 preview 返回的 `preview_id` 与 `submit_expected_versions`；任一 sample 的 HTTP/DTO 错误都会在 mutation 前 fail closed。preview p50/p95/max 与 request IDs 独立报告，p95 超过 3 秒只登记 `performance_status=miss`，不伪装成 correctness failure。
- `bank_oa_invoice` 的 affected consumers 固定为关联台、银行明细、待找发票、进项使用、OA 待付款、成本统计；销项收款与税务抵扣只作 isolation。测试按当前 scenario entry 断言 role，不使用其它 relation shape 的 affected 联集。
- 同条件旧/新 10 次 characterization 继续采用 Task 30-02 的同一 PostgreSQL fixture、scope/version/row IDs、连接与 warm-up：新路径固定每次 6 条 counted SQL、完整 generation scan 为 0、formal snapshot dependency 为 0，最大新样本 5.089ms。
- 相同 URL、无独立 `AbortSignal`、仍在进行的 combined initial 必须只产生一个 HTTP 请求；所有调用方都获得同一映射结果。请求完成或失败后必须移除 in-flight entry，后续读取重新访问服务器；搜索/筛选可取消请求不得被该合并吞掉。
- 正式 confirm/withdraw 的 canonical row resolver 必须读取生产已配置的 `_workbench_sql_read_repository.get_workbench_row_detail(...)`；不得重新引用已退役、未注入的 `_workbench_canonical_query_repository` 而静默回退到全量 live builder。preview selection 仍只用于 preview，正式 command/UoW 不得消费 preview DTO。
- relation preview 必须保留首尾 fresh/version drift 门禁，但同一次 selection 只允许一次 generation proof；末次 freshness 的 active version 是结束 version 证据，不得再次执行等价 proof。`active_relations_for_row_ids` 必须走 active-only repository loader，不能为 active lookup 读取 relation history；withdraw restore preview 仍保留 history loader。
- `tests/test_workbench_relation_command_repository_adapter.py::WorkbenchRelationCommandRepositoryAdapterTests::test_scoped_load_filters_in_memory_snapshot_when_repository_has_no_scope_boundary` 使用禁止 `snapshot()` 的 service，证明撤回 scoped read 直接调用既有 `snapshot_for_row_ids(...)`，只复制目标 relation/history，不重建全量进程内状态。
- 本地 release gate：700 项定向 backend/deploy unittest、123 项 scoped Vitest、3 项 Chromium E2E、repository lint、docs gate 与 production build 全部通过。没有运行 pytest、完整 CI 或 183 项 Browser suite。

## 2026-07-29 - Phase 34 最终验证

- 最新后端根因修复的定向矩阵为 550 passed，覆盖 command adapter/service、pair relation service、write characterization、SQL runtime、鉴权/幂等、runtime boundary 与 relation repository。
- 前端 combined-initial in-flight 合并由 `web/src/test/WorkbenchApi.test.ts` 保护；本轮后端-only scoped snapshot 修复未新增重复 UI 测试。
- production release `main-632dd2aa-20260729153028` 的 Page Audit 为 `pass / fresh / drained`，issues 为空；20 次 gzip 样本的 combined initial、groups 首屏、confirm preview、withdraw preview、refresh status p95 分别为 `312.664/712.718/718.591/557.145/138.925ms`。
- 未运行无关完整 CI 或浏览器套件。未执行真实生产 confirm/withdraw mutation：现有 scenario 不是 test-owned 且缺完整恢复检查点，不能为了测速修改真实财务关系。
