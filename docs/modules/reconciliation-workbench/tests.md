# 关联台测试与验证

日期：2026-07-14

## 七类测试

| 类别 | 适用 | 主要覆盖 |
| --- | --- | --- |
| 1. Business core | 是 | 确定性证据、365 日边界、N:M:K exact-sum、歧义/金额-only/红冲 fail-closed、撤回阻断指纹、paired/unpaired 精确分区 |
| 2. Service layer | 是 | repository 输入、orchestrator 单 UoW、幂等、rollback、history、dirty/outbox、旧状态清理 |
| 3. API contract | 是 | paired/unpaired shape、分页/search/detail、confirm/withdraw、版本冲突、权限、unknown state fail-fast |
| 4. Read model/cache/worker | 是 | active generation 原子发布、freshness、all-scope 组合、bulk refresh、旧 generation 不冒充 fresh |
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

## 验证命令

```bash
python3 -m pytest -q \
  tests/test_workbench_free_matching_engine.py \
  tests/test_workbench_formal_relation_repository.py \
  tests/test_workbench_matching_orchestrator.py \
  tests/test_workbench_relation_grouping.py

python3 -m pytest -q \
  tests/test_workbench_sql_runtime.py \
  tests/test_workbench_v2_api.py \
  tests/test_workbench_query_service.py \
  tests/test_postgres_migrations.py

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
