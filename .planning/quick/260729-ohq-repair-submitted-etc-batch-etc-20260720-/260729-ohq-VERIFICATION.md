---
quick_id: 260729-ohq
status: passed
verified_at: 2026-07-29
production_release: main-0bbeb2d4-20260729194337
---

# Quick Task 260729-ohq Verification

## Must Haves

- [x] `etc_20260720_001` 只增加四张经确认 canonical 发票。
- [x] business/submission batch 从 64 / 3686.36 收敛到 68 / 3740.82。
- [x] 四张发票无 PDF/XML 的原始事实被诚实保留。
- [x] OA 草稿和已关闭对账任务执行前后 fingerprint/hash 一致。
- [x] dry-run fingerprint、expected version、owner、目标金额和目标成员 fail closed。
- [x] execute 幂等重放不产生第二次写入。
- [x] ETC 页面与 Workbench 使用同一 canonical batch membership。
- [x] Workbench 折叠摘要和 68 条折叠明细均包含四张发票。
- [x] Search exact scope 已 fresh，durable queue 已 drained。
- [x] ETC 与 Workbench Page Audit 均通过。
- [x] 三个目标读取端点生产 p95 均低于 1 秒。

## 七类测试覆盖

1. Business core unit：适用。覆盖精确四成员计划、金额/数量不变量、缺失来源、部分修复、并发版本漂移和幂等重放。
2. Service layer：适用。覆盖 repair repository/tool、事务回滚、审计、ETC link/overlap、historical lifecycle 和精确 Workbench refresh。
3. API contract：不改变 HTTP path 或 response shape；生产只读验证 business batch、Workbench groups/detail 的既有合同。
4. Read model/cache/background job：适用。覆盖 Workbench v11 完整 ETC 成员、旧 generation 淘汰、Search worker 90 秒后台预算、exact scope fresh 和 durable queue drain；未新增缓存或 worker。
5. Frontend component/interaction：不适用。没有修改前端组件或交互；按用户要求不运行无关浏览器测试。
6. End-to-end business flow：适用。生产验证 canonical repair -> ETC detail -> Workbench summary/detail -> Search fresh -> Page Audit。
7. Existing feature regression：适用。覆盖 PostgreSQL core repository typed values、Workbench active-relation suppression、dirty queue wiring、旧 strict-link partial overlap 和 Search 前台 2 秒默认预算不变。

## 本地验证

```bash
PYTHONPATH=backend/src python3 -m pytest -q \
  tests/test_repair_submitted_etc_batch_members_tool.py \
  tests/test_postgres_core_repository.py \
  tests/test_workbench_dirty_queue_wiring.py \
  tests/test_search_sql_runtime.py \
  tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_keeps_all_business_members_when_strict_links_are_partial \
  tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_excludes_unpaired_etc_summary_when_batch_has_active_relation

bash scripts/verify.sh lint
bash scripts/verify.sh docs
git diff --check
```

结果：31 passed、1 个依赖本地真实 PostgreSQL 的既有环境测试 skipped；lint、docs、diff check 均通过。

## 生产验证

- 发布：`./scripts/deploy-oa.sh` 激活 `main-0bbeb2d4-20260729194337`，API、dispatcher 和必需 worker active。
- canonical/API：business batch version 13，68 张 / 3740.82 元，目标四张存在，OA/task 未改变。
- Workbench：group `unpaired:invoice:e831970d7f373cb92a2da976`，summary 68 / 3740.82，`collapsed_rows.invoice` 68 行，四张目标发票存在。
- Search：`search=2026-06` 最新任务 `done/fresh`，`stale_count=0`；旧 covered dead letters 先 dry-run 证明后归档。
- Audit：`etc-tickets` 与 `reconciliation-workbench` 为 `pass/fresh/drained`。
- 性能：ETC detail / Workbench search / Workbench detail 的生产 p95 分别为 176.876ms / 129.225ms / 161.452ms。

## Remaining Risk

- 四张补录发票在原统一发票池中没有 PDF/XML，因此 ETC 合并 PDF 不会为它们生成页面；这是来源附件缺失，不是批次成员缺失。后续只有拿到真实原件并走正式附件恢复合同后才能补齐。
- System Audit 的 `bank-flow-rule-batches` integrity failure 为本任务开始前已存在的独立数据问题；本任务没有修改该模块。
- 两个 pending-invoice 端点在此前广域只读性能探针中仍偏慢；不属于本次 ETC/Workbench 链路。
- 未运行真实浏览器和全量 CI；本次没有前端改动，且用户明确要求避免无意义浏览器测试和 CI。
