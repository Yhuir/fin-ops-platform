---
quick_id: 260729-nh8
status: passed
verified_at: 2026-07-29
---

# Quick Task 260729-nh8 Verification

## 本地门禁

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_reads_relation_preview_selection_with_one_bounded_row_lookup tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_relation_preview_selection_fails_closed_for_divergent_cross_month_rows tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_relation_preview_selection_fails_closed_for_missing_rows`：3 passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime tests.test_workbench_write_characterization tests.test_workbench_auth_context_idempotency tests.test_workbench_query_facade`：295 passed。
- `cd web && npm test -- --run src/test/WorkbenchApi.test.ts`：44 passed。
- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- `cd web && npm run build`：通过；只有既有 HeroUI CSS minify 与 chunk-size warning。
- `git diff --check`：通过。

## 七类测试评估

1. Business core unit：适用；覆盖 identical duplicate collapse，以及金额、状态、来源任一漂移 fail-closed。
2. Service layer：适用；覆盖 `month=all` 双 active generation 的 selected/context 去重、请求顺序、两次 freshness、一次 generation proof 和两条 bounded SQL。
3. API contract：适用；既有 confirm preview characterization 保持稳定 HTTP/error contract，生产真实请求验证 200 DTO；本次不改变 response shape。
4. Read model/cache/background job：适用；覆盖 active generation-set、fresh/version 和跨 shard 行合同。未改变 cache、queue 或 worker，因此没有新增后台任务测试。
5. Frontend interaction：适用；`WorkbenchApi.test.ts` 覆盖 `relation_preview_rows_ambiguous` 只映射为批准的中文文案。页面交互结构未改变，不增加重复组件/E2E。
6. End-to-end business flow：适用；本地保护 preview 与 formal UoW 分离，生产完成 initial/groups -> exact selection preview -> unpaired rere读的只读闭环。未对真实财务关系执行 mutation。
7. Existing feature regression：适用；295 项关联台 SQL/query/write/idempotency 回归覆盖 confirm/withdraw、missing、freshness、version drift、formal reread 和既有页面查询。

## 生产验证

- `./scripts/deploy-oa.sh` 成功激活 `main-bf429ea3-20260729170433`；API、RabbitMQ dispatcher 与 11 个 required workers 均为 active，readiness 通过。
- 当前 `month=all` 为 `fresh`，version 为 `workbench:all:active-generation-set:7d7e742142f46d25b7e5d305210ed38e4f5951e031de65f659156679ad8eef84`。
- 真实选区：
  - OA：`oa-pay-2215`
  - 流水：`txn_imported_1480`、`txn_imported_1481`、`txn_imported_0113`、`txn_imported_0115`
- confirm preview 返回 HTTP 200、`can_submit=true`、amount status `matched`、OA/流水均为 `200000.00`、delta `0.00`；操作前 2 组、操作后 1 组。
- preview 2 次 warmup 后 20 次样本：p50 `252.383ms`、p95 `730.272ms`、mean `361.758ms`、max `814.141ms`。
- browser-equivalent gzip GET 各 2 次 warmup + 20 次：
  - combined initial：p50 `208.458ms`、p95 `303.235ms`、max `365.211ms`。
  - 搜索“房克丽”的 unpaired groups：p50 `156.195ms`、p95 `175.834ms`、max `183.814ms`。
- 搜索结果仍为 2 个 unpaired groups，并完整包含上述 5 个 canonical IDs；preview 没有产生关系写入。
- Page Audit 返回 HTTP 200，`integrity=pass`、`freshness=fresh`、`queue=drained`、issues 为空。

## 残余风险

- 部署后第一次未预热 preview 样本为 `1267.370ms`；稳态 p95 和 max 均低于 1 秒，因此满足当前 p95 SLO，但不能声称冷启动每一次都小于 1 秒。
- 没有 test-owned、可逆且带完整恢复检查点的生产 fixture，因此未对真实财务关系执行 confirm/withdraw mutation。正式 UoW、CAS、幂等、审计和 inverse 由本地回归保护；生产验证只证明真实 preview 与读取链路。
- 未运行无关完整 CI 或浏览器套件；本次后端 repository + API mapper 变更由定向单元、服务、构建和真实生产 HTTP 链路覆盖。
