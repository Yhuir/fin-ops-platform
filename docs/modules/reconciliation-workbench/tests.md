# 关联台测试与验证

日期：2026-07-17

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
- E2E mock 不得用共享历史 `case_id` 构造未配对组；搜索只过滤对应 pane，不得把其他 pane 的独立 canonical facts 隐藏。
- 未配对 canonical row 若携带旧 `candidate:` / `decision:` / `temp:` ownership，输出必须清理与该候选 ownership 绑定的 mode 装饰且仍保持 singleton；control owner 优先级必须是 active formal relation > active override > active exception。正式关系成员不能携带旧 override/exception decoration；未配对 row 的 active override 必须优先于同 row exception，`pending_input_invoice` 等合法 control fields 必须与 canonical override 精确一致。回归测试必须同时覆盖最终 `workbench_rows.payload` 写入形状和 Page Audit SQL 的相同优先级。
- ETC collapsed-summary 必须同时物化 summary row 和全部 invoice detail rows；paired/unpaired 只改变 zone/status，不得丢失、重复或隐藏明细。
- Workbench groups page cache schema 必须与 projection schema 同步，projection 行为升级后旧 Redis payload 必须自动失效。
- combined initial 两区首屏必须各为 50 groups、`has_more` 保留真实 total，默认 batch SQL 每区读取最多 51 条用于判定后续页；后续 `/groups` 必须绑定同一 `expected_read_model_version`，不得为性能退回 200-group 首屏或全量 payload。
- 默认无筛选 all-scope `/groups` 的 total/row_counts 必须来自当前 active-month generation-set digest 对应的两条 `workbench_generation_stats`；统计缺失或查询前后 digest 改变时返回 refreshing，不得执行旧的全量 distinct row count。月 generation 发布与该统计必须处于同一事务，多个 scope 同批发布只生成一次最终 digest 统计。
- all-scope 搜索、来源、pane/列/时间筛选必须只 materialize active generation key，条件之间按既有 AND/OR 语义相交；total、row counts、matching group ids 在一条计数 SQL 中得到，分页只按 matching ids 读取 payload。测试必须断言 SQL 不读取 `g.*`/payload/raw payload，不 join 历史 physical all group，且不为 count/page 重复执行 member 条件。
- 普通标量列的同列多选必须按 OR，`全选`不能把结果清空；不同列/不同 pane 继续按 AND，银行金额表头的方向+付款账号复合筛选继续要求同一行同时满足。前端本地过滤、HTTP mock、repository SQL 和 summary preview 必须使用同一合同。

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
- Audit 必须证明 active relation typed members 与 paired display 双向相等、其余 canonical facts 全部 singleton unpaired。
- 520 case、发票号和 OA row id 必须在 fresh generation 中同组；13 张样例必须完整可见。
