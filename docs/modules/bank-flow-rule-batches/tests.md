# 流水规则批量处理测试矩阵

状态：covered-close。页面列表、summary、分页、详情和写后回读已切到 PostgreSQL canonical query boundary；页面 API 不再返回 read-model status/version、refresh enqueue 或 operation-barrier targets，前端不再轮询 freshness。

## 七类测试适用性

| 类别 | 是否适用 | 当前覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 适用 | OA/发票只有双 false 合格；未知、停用、重复标签 fail fast；提交冻结 requirement/category metadata；内部转账金额只计单边；重复选择、占用和版本冲突保持原领域错误。 |
| 2. Service-layer tests | 适用 | canonical query repository 在一个 `REPEATABLE READ / READ ONLY` snapshot 中完成列表 count、分页 rows 和 summary 聚合；详情集合读取银行流水、当前分类、active relation 和批次事件；submit/withdraw/reset 继续走 relation command 与 batch delta writer。 |
| 3. API contract tests | 适用 | 权限、非法参数、空集、筛选、排序、分页、summary、详情、提交/撤回/reset、规则 CAS；明确断言响应不含 `read_model_*`、refresh 或 operation-barrier 字段。 |
| 4. Read model, cache, and background job tests | 适用（清理回归） | 页面 SQL 禁止读取 `read_model.bank_flow_rule_batch_rows` 和 no-OA 表；页面 service 不 enqueue、不走 relation projection，前端首次 GET 后不后台轮询。共享 registry/worker 的最终删除由主控合并任务处理。 |
| 5. Frontend component and interaction tests | 适用 | loading/empty/error、筛选、分页、详情、规则抽屉、权限、提交/撤回/reset；每次成功写命令只触发一次当前列表 GET，不启动 freshness polling。 |
| 6. End-to-end business-flow integration tests | 适用 | 规则/选择 -> relation command -> canonical batch/event 保存 -> 当前页 GET -> 关联台 active relation 展示；生产合并后补 PostgreSQL 与 Browser smoke。 |
| 7. Existing feature regression tests | 适用 | no-OA legacy API、Workbench 正式关系、bank-details 标签、成本/外部往来款、权限与审计不受页面读路径迁移影响。 |

## 主要测试入口

- `tests/test_bank_flow_rule_batch_canonical_query_repository.py`
- `tests/test_bank_flow_rule_batch_application_service.py`
- `tests/test_bank_flow_rule_batch_routes.py`
- `tests/test_bank_flow_rule_batch_backend_boundary.py`
- `tests/test_no_oa_bank_batch_workbench_integration.py`
- `tests/test_no_oa_bank_batch_tag_selection_api.py`
- `tests/test_workbench_relation_command_service.py`
- `tests/test_workbench_relation_repository.py`
- `web/src/test/BankFlowRuleBatchApi.test.ts`
- `web/src/test/BankFlowRuleBatchPage.test.tsx`
- `web/src/test/BankFlowRuleBatchPolicy.test.ts`
- `web/src/test/RelationGroupGrid.test.tsx`
- `web/e2e/bank-flow-rule-batches-flow.spec.ts`

## 必测失败路径

- 无读取权限；规则保存无写权限。
- 非法月份、bucket、status、页码或 page size。
- 规则 CAS 冲突、未知/停用/重复 tag code。
- 空选择、重复 row、跨月、跨账户、混合标签、active relation 已占用、规则版本过期。
- Relation command 或 batch delta writer 失败时不得留下半批次。
- 空列表必须来自已完成的 canonical snapshot，不能由 missing/stale 投影伪造。
- submitted/withdrawn 历史使用冻结标签和 requirement metadata；当前标签改名或归档不得改写历史。
- canonical relation 查询只接受 `app.workbench_pair_relations.status='active'`，不得读取 Workbench page projection。
- 页面和 feature 源码不得重新出现 freshness polling、202 reconcile 或 no-OA fallback。

## 验证命令

```bash
PYTHONPATH=backend/src python3 -m pytest -q \
  tests/test_bank_flow_rule_batch_canonical_query_repository.py \
  tests/test_bank_flow_rule_batch_application_service.py \
  tests/test_bank_flow_rule_batch_routes.py
npm --prefix web test -- --run \
  src/test/BankFlowRuleBatchApi.test.ts \
  src/test/BankFlowRuleBatchPage.test.tsx
bash scripts/verify.sh lint
npm --prefix web run build
git diff --check
```
