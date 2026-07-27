# 关联台测试矩阵

日期：2026-07-27

## 七类覆盖

| 类别 | 是否适用 | 主要入口 | 本迁移保护 |
| --- | --- | --- | --- |
| 1. Business core | 适用 | `tests/test_workbench_relation_grouping.py`、`tests/test_workbench_write_characterization.py` | paired/unpaired、completion requirement、重复/冲突、ETC collapsed group、ignored/exception、筛选/排序业务等价 |
| 2. Service/repository | 适用 | `tests/test_workbench_canonical_query_repository.py`、`tests/test_workbench_query_facade.py`、`tests/test_workbench_uow_contract.py`、`tests/test_workbench_auth_context_idempotency.py` | canonical SQL owner、同 snapshot、固定查询数、事务内 identity/type 重验、CAS/幂等/rollback |
| 3. API contract | 适用 | `tests/test_workbench_routes.py`、`tests/test_workbench_v2_api.py`、`tests/test_workbench_stale_write_contract.py` | 权限拒绝、非法参数、空集、分页、summary/detail/preview、409、旧 runtime 字段和旧 endpoints 删除 |
| 4. Read model/worker cleanup | 适用 | `tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_architecture_guards.py`、`tests/test_workbench_dirty_queue_wiring.py`、`tests/test_sse_smoke_probe.py` | 页面不读 generation/cache/status/queue/SSE；旧 generation/worker/manifest 保持删除，只有登记的共享 relation/search/no-OA read model 保留 |
| 5. Frontend interaction | 适用 | `web/src/test/Workbench*.test.*` | loading/empty/error、权限、搜索/筛选/排序/分页、drawer、写后 GET、无 polling/SSE/version gate |
| 6. E2E flow | 适用 | `web/e2e/workbench-stale-error-flow.spec.ts`、`tests/test_write_operation_e2e_smoke.py` | preview -> confirm/withdraw -> reread；旧刷新等待步骤删除 |
| 7. Existing regression | 适用 | `tests/test_no_oa_bank_batch_workbench_integration.py`、`tests/test_bank_auto_tag_rules_api.py`、`tests/test_app_health_api.py`、`tests/test_workbench_canonical_query_repository.py` | no-OA、银行标签、App Health 与 batch-accounting canonical 查询不被误伤 |

## 必须断言

- 查询只引用 canonical `app.*` facts 和 `app.workbench_pair_relations.status='active'`，不引用 `read_model.workbench*`。
- initial 的 summary、paired/unpaired 首页处于一个 `REPEATABLE READ READ ONLY` transaction。
- `all`、单月、最大 page size 200、group detail、row detail 和 20-row preview 查询次数固定，无逐组/逐行 N+1。
- search 最长 200、普通文本语义；筛选、排序、分页、summary/row counts 与完整 group 返回保持业务等价。
- 跨月 relation members 不被拆成错误 owner；ETC owner precedence 不产生重复、空 summary 或跨 scope group。
- ignored/exception 继续展示，但不能覆盖 active relation ownership。
- preview/confirm/withdraw 不出现 `expected_read_model_version`；transaction 内重验 canonical identities/types 和 active relation business versions。
- canonical row 消失或类型漂移返回 409，mutation 不执行；幂等重复和 relation version/occupancy conflict 保持既有合同。
- frontend/API 不再出现 `read_model_status`、`read_model_version`、`source_versions`、`refresh_enqueued`、active generation、`/refresh-status` 或 `/events`。
- batch-accounting 不再依赖 generation；`workbench_relation` distribution 与 worker 只服务登记的独立消费者。

## 性能 guards

`tests/test_workbench_canonical_query_repository.py` 锁定：

- default initial empty shape：10 条语句（含 2 条 transaction setup），单一 snapshot。
- groups empty/最大分页 selector：4 条语句；`LIMIT/OFFSET`，最大 200 descriptors 一次 hydration。
- missing group/row detail：各 3 条语句。
- 20-row preview：每个 canonical kind 一次批量 loader。
- command transaction canonical validation：1 条有界 SQL。
- 本地 recording-double 的 empty initial 小于 100ms。

该耗时只防止 Python orchestration 失控，不能代替真实 PostgreSQL/生产 p95。repository 2 秒 statement timeout 是安全上限，不是 SLO 证明。

## 最小验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_workbench_canonical_query_repository \
  tests.test_workbench_query_facade \
  tests.test_workbench_routes \
  tests.test_workbench_auth_context_idempotency \
  tests.test_workbench_uow_contract \
  tests.test_workbench_v2_api \
  tests.test_workbench_write_characterization \
  tests.test_platform_runtime_boundary_guards \
  tests.test_read_model_architecture_guards \
  tests.test_no_oa_bank_batch_workbench_integration \
  tests.test_write_operation_e2e_smoke

cd web && npm test -- --run \
  src/test/WorkbenchApi.test.ts \
  src/test/WorkbenchApiRuntimePath.test.ts \
  src/test/WorkbenchExceptionModal.test.tsx \
  src/test/WorkbenchSelection.test.tsx \
  src/test/WorkbenchWriteGate.test.ts \
  src/test/WorkbenchZone.test.tsx

cd web && npm run build
cd web && npx playwright test e2e/workbench-stale-error-flow.spec.ts

bash scripts/verify.sh lint
bash scripts/verify.sh docs
```

## 发布后性能验证

主控合并后在真实 PostgreSQL 数据量下分别测量：

- 默认 initial。
- 最大月份和 `month=all`。
- groups page size 200，带/不带 search/filter/sort。
- group detail、row detail。
- 20-row preview。

记录 `duration_ms`、`connection_acquire_ms`、`sql_execute_fetch_ms`、`database_query_count` 和响应体大小。只有慢 SQL 的 `EXPLAIN (ANALYZE, BUFFERS)` 证明需要时才新增索引 migration。

## 未测风险

- 当前本地测试没有真实生产基数、并发、连接池等待或 PostgreSQL planner 证据。
- 历史 active-generation 表仍存在但无运行时 reader/writer；物理 drop 留给单独可回滚 migration。
- 真实 OA/银行/发票/ETC 同步延迟仍由各 canonical owner 的 ingestion/health 合同负责；页面请求不会调用外部系统补数。
