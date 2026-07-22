# 关联台测试与验证

日期：2026-07-22

## 2026-07-22 Turnover 人工闭环冻结要求分区回归

- Business core：`turnover_manual_closure` active relation 只拥有同组关系，不无条件代表完成；OA/发票四种冻结 requirement 组合按 OR 聚合，未知、空或缺失 snapshot fail closed。要求 OA 的 bank-only case 保持完整 unpaired，补齐要求后才以同 case paired；`batch_accounting` 与 ETC 显式完成合同保持隔离。
- Service/API：Turnover 人工确认复用同一次 selected-row 快照，并且只读取一次 canonical rule payload，冻结 tag code、OA/发票布尔值、来源和版本；合并后的任一 bank member 不在 selected ids、bank row 缺失/重复或规则无效时 UoW 不打开。deterministic 写入的既有冻结合同不变。
- Read model/Audit：SQL projection、写后 operation projection 和 preview 复用 relation 自身冻结要求；Page Audit 独立发现缺快照与错误 zone；本次不改变共享 projection schema、scope、worker 或 cache。
- Frontend：API mapper 保留显式 false、缺字段保持缺失语义；不完整 relation 的空 pane显示“待补 OA/发票”。生产组件与页面请求 I/O 未改变。
- 旧链回归：no-OA 规则保存不再扫描并追溯回写既有 Turnover relation；普通 manual、deterministic、batch accounting、ETC、合并与撤回测试共同防止其它页面分区被放宽。

## 2026-07-20 折叠流水详情惰性加载回归

- Repository：production-shape materialized group 只有银行成员时，group detail 仍必须返回 `oa_rows=[]`、完整 `bank_rows`、`invoice_rows=[]`，且折叠计数与明细成员一致。
- API client：HTTP 200 若缺少任一 pane 数组、group identity 不一致，或声明成员数与实际详情不一致，必须 fail-closed，不能把不完整 payload 安装为可展开数据。
- 前端交互：页面加载和 group 更新不得自动预取折叠明细；用户点击后只发一次详情请求，成功后展开，失败后保持折叠并显示可重试状态。
- E2E：首屏只显示 3 条流水摘要时不请求详情；用户点击“展开 4 条明细”后恰好请求一次 group detail，并渲染 4 条完整流水。

## 2026-07-20 Turnover 撤回 preparation 隔离回归

- `tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_prepared_withdraw_reuses_lock_relation_snapshot_and_freshness` 保护同一 service/transaction 的 preparation 复用一次 lock/scoped snapshot/freshness。
- `test_prepared_withdraw_rejects_a_different_case` 保护 preparation 不得跨 case 使用；普通 Workbench withdraw 不传 preparation，既有测试继续覆盖原调用合同。

## 七类测试

| 类别 | 适用 | 主要覆盖 |
| --- | --- | --- |
| 1. Business core | 是 | 确定性证据、365 日边界、N:M:K exact-sum、歧义/金额-only/红冲 fail-closed、撤回阻断指纹、paired/unpaired 精确分区 |
| 2. Service layer | 是 | repository 输入、orchestrator 单 UoW、幂等、rollback、history、dirty/outbox、旧状态清理 |
| 3. API contract | 是 | paired/unpaired shape、分页/search/detail、confirm/withdraw、版本冲突、权限、unknown state fail-fast |
| 4. Read model/cache/worker | 是 | active generation 原子发布、freshness、all-scope 组合、exact generation stats、stats 缺失/发布竞态 fail-closed、bulk refresh、旧 generation 不冒充 fresh |
| 5. Frontend interaction | 是 | 两区渲染、singleton 未配对、选择/preview/撤回、loading/empty/error/stale、权限与分页 |
| 6. End-to-end | 是 | canonical import/OA -> matching -> formal relation -> worker -> paired；withdraw -> singleton unpaired；跨页 relation fan-out |
| 7. Regression | 是 | 520 样例、13 张发票、ETC/OA 附件、no-OA、batch accounting、turnover、cost/search/invoice lifecycle |

## 核心固定测试

- `tests/test_workbench_free_matching_engine.py`
- `tests/test_workbench_formal_relation_repository.py`
- `tests/test_workbench_matching_orchestrator.py`
- `tests/test_workbench_relation_grouping.py`
- `tests/test_workbench_sql_runtime.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_workbench_query_service.py`
- `tests/test_postgres_migrations.py`
- `web/src/test/RelationGroupGrid.test.tsx`
- `web/src/test/WorkbenchApi.test.ts`
- `web/src/test/WorkbenchSelection.test.tsx`
- `web/src/test/WorkbenchZone.test.tsx`

## 必须保护的不变量

- 520 元历史 case 前缀不影响 active relation 进入 paired。
- 13 张合计 1709.49 元发票保持 13 个 unpaired singleton。
- `paired ∩ unpaired = ∅`，`paired ∪ unpaired = canonical identities`。
- 装饰字段、输入顺序和旧 candidate/decision metadata 不改变 membership/group id。
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
- 前端必须断言每区只有一个 HeroUI `SearchField` 且位于区域 header 同行；输入时使用既有 deferred combined initial 单请求，等待期间保留当前稳定结果并显示 pending，失败可重试。所有可见命中片段都高亮；只命中隐藏 pane/折叠明细时显示“隐藏内容命中”，用户展开完整详情后显示实际高亮。
- 搜索框在首个 combined initial 完成前已可输入时，不得提前消费新的 zone query key；初始稳定数据安装后必须补发包含该 query 的 combined initial 请求，不能只对首屏 50 组做本地高亮并漏掉其它组或折叠明细。
- 关联台 Audit 绿色结果必须绑定 active Workbench read-model version + 页面 freshness status；generation/status 改变立即清除旧绿色结果。`workbench_matching_scope_not_converged` 属于 freshness+queue 阻断，`workbench_generation_source_versions_mismatch` 属于 freshness 阻断。
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

## 2026-07-22 Workbench v6 与历史修复回归

- `tests/test_workbench_sql_runtime.py` 证明 month/all v6 同步，groups/initial cache key 随 schema 派生失效，旧 v5 source version 返回 `builder_mismatch`，不能作为 fresh generation 消费。
- requirement repair 测试证明 legacy Turnover active relation 的完整 preimage/intended after fingerprint、partial execute、exact metadata rollback、partial rollback retry 和 drift zero-write；普通 relation、ETC、batch 与 inactive relation 不受影响。
- 既有 grouping/projection/query 回归继续证明：要求 OA 的 bank-only case 保持同 case unpaired，补齐 OA 后进入 paired，active generation 只经现有原子 publish 边界切换。
- `tests/test_audit_workbench_relation_display_tool.py` 同步保护审计口径：`turnover_manual_closure` 不再享有旧的 requirement 豁免；缺 OA 的 bank-only closure 在 unpaired 不报警，若出现在 paired 必须报告 `relation_requirement_partition_mismatch`。
