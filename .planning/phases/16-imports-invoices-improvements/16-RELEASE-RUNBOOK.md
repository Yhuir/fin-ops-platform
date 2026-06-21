---
status: ready_for_approval
phase: 16-imports-invoices-improvements
updated: 2026-06-21T00:35:28+08:00
---

# 发票/银行导入 Read Model 闭环发布操作单

运维短命令包见 `16-OPS-EXECUTION-PACK.md`。本文保留背景、验收和失败分流说明。

## 目标

发布当前导入 fan-out、队列 superseded guard、direction-aware read model refresh、bank account balance refresh 和 orphaned import fact dirty scope repair 能力，并在真实运行态证明：

- 导入确认后真实 durable refresh events 齐全。
- Worker 能自然 drain 到 dirty scope done / readiness fresh。
- App Status 不再被 legacy `import_facts_changed` dirty scope 卡住。
- 关联台、发票池、进项使用、销项收款、银行明细和账户余额关键读路径可读。

## 发布前本地证据

已通过：

```bash
pytest tests/test_import_processing_service.py tests/test_import_job_queue.py tests/test_import_api.py tests/test_import_file_api.py tests/test_import_service.py tests/test_postgres_repositories_core.py tests/test_runtime_queue.py tests/test_runtime_worker.py tests/test_runtime_monitoring.py tests/test_runtime_worker_registry.py tests/test_read_model_refresh_gateway.py tests/test_read_model_scope_contract.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_bank_detail_for_transaction_month_scopes tests/test_write_operation_slo_audit.py tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_read_model_refresh_producers_use_scope_gateway_boundary -q
```

结果：`182 passed, 5 warnings`

```bash
cd web && npx playwright test e2e/imports-invoices-flow.spec.ts e2e/imports-bank-transactions-flow.spec.ts
```

结果：`13 passed`

```bash
python -m compileall backend/src/fin_ops_platform/services/import_processing_service.py backend/src/fin_ops_platform/services/runtime_worker_handlers.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/postgres_repositories/core.py backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/services/runtime_queue.py backend/src/fin_ops_platform/tools/write_operation_slo_audit.py backend/src/fin_ops_platform/services/read_model_scope_contract.py backend/src/fin_ops_platform/services/postgres_repositories/read_model_scope_contracts.py
PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help
bash scripts/verify.sh docs
git diff --check
```

均通过。

## 发布前只读检查

这些命令不写数据库。

```bash
./scripts/check-local-runtime.sh --dependencies-only
```

预期：

- PostgreSQL ready。
- Redis ready。
- Object storage ready。
- 如果经 SSH tunnel，不能作为生产性能基准。

```bash
bash scripts/verify.sh infra-smoke
```

预期：

- contract tests 通过。
- 若缺少认证、写入场景或审批票据，报告 `external_input_required`；这不是代码失败。

```bash
set -a
source .runtime/fin_ops_platform/local-postgres.env
set +a
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit \
  --json \
  --operation invoice_import_confirmed \
  --operation bank_import_confirmed \
  --lookback-hours 72 \
  --target-ms 5000
```

当前已知：连接 runtime 上该审计失败，暴露旧运行态缺事件和 19-26s 尾延迟；发布当前代码前不应期待它通过。

```bash
set -a
source .runtime/fin_ops_platform/local-postgres.env
set +a
scripts/check-read-model-scope-contracts.py --repair orphaned-import-facts --json
```

当前已知：dry-run 发现 42 条 orphaned legacy dirty scope，`cleanup.applied=false`。

## 部署

生产发布入口仍以运维文档为准：

```bash
./scripts/deploy-oa.sh
```

或在服务器使用既有 release activation 流程。发布必须确认：

- API release 与 worker release 一致。
- `runtime_worker_manifest --json` 通过。
- required workers 无 missing/stale/mismatch。
- `import` worker claim `import.process.requested` 和 `import.fact.changed`。
- read model workers 覆盖 workbench、workbench_relation、invoice_lifecycle、search、pending_invoice、input_invoice_usage、output_invoice_collection、oa_pending_payment、cost_statistics、tax_offset、bank_detail、bank_account_balance。

## Orphaned Dirty Scope 清理

只在发布当前代码并确认没有正在运行的导入窗口后执行。

先归档 dry-run JSON：

```bash
scripts/check-read-model-scope-contracts.py --repair orphaned-import-facts --json
```

确认条件：

- `items[]` 全部是 `reason=import_facts_changed`。
- 对应 scope 没有 active `import.fact.changed` outbox 可 claim。
- 本次发布后的真实 `*.read_model.refresh` 事件已经成为后续刷新事实源。
- 有明确审批或生产窗口。

执行清理：

```bash
scripts/check-read-model-scope-contracts.py \
  --repair orphaned-import-facts \
  --apply \
  --reason production_orphaned_import_fact_cleanup \
  --json
```

预期：

- `cleanup.applied=true`。
- `cleanup.deleted.job.read_model_dirty_scopes` 等于 dry-run 中确认可清理的数量。
- `repair_audit.recorded=true`。
- 不应删除 outbox events。
- 不应写 readiness fresh。

回滚：

- 使用 apply 报告里的 `items[].row` 恢复被删 `job.read_model_dirty_scopes` 行。
- 回滚后重新运行 dry-run，确认相同 row 再次出现。
- 不通过手写 readiness fresh 回滚。

## 发布后真实导入 Smoke

需要明确的 staging/生产写入批准、可回滚小样本和认证上下文。

执行最小三类导入：

1. 小批进项发票。
2. 小批销项发票。
3. 小批银行流水。

每次记录：

- `/imports/files/preview` 响应时间。
- `/imports/files/confirm` 返回 job 时间。
- background job 到 `succeeded` 时间。
- outbox enqueue 到 done 时间。
- dirty scope pending/processing 到 done 时间。
- App Status 从 busy 到 ok/fresh 时间。

发布后审计：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit \
  --json \
  --operation invoice_import_confirmed \
  --operation bank_import_confirmed \
  --lookback-hours 2 \
  --target-ms 5000 \
  --p99-target-ms 5000
```

必须关注：

- `bank_import_confirmed` 有 `bank_detail.read_model.refresh`。
- `bank_import_confirmed` 有 `bank_account_balance.read_model.refresh`。
- `invoice_import_confirmed` 有 workbench、workbench_relation、invoice_lifecycle、search、pending_invoice、direction page、oa_pending_payment、cost_statistics、tax_offset。
- 非命中方向页可以 `skipped`，但 required 事件不能 missing。

关键读路径：

- 关联台能看到导入后的发票/流水。
- 发票池能看到新增发票。
- 进项发票使用只受进项文件刷新影响。
- 销项发票收款只受销项文件刷新影响。
- 银行明细能看到新增流水。
- 账户余额 API freshness gate 返回 fresh。

## 失败分流

如果失败，按证据分类：

- Missing required event：producer fan-out 或部署版本不一致。
- Event pending/processing 长时间不变：worker claim/worker registration/lock。
- Event done 但 dirty scope pending：completion path 或 legacy stranded scope。
- Event done 但 readiness 非 fresh：readiness reporter 或 query freshness contract。
- Event done 但耗时超标：单个 read model handler rebuild 慢，优先 profile `oa_pending_payment`、`cost_statistics`。
- App Status busy 但业务页面可见：runtime state cleanup/readiness aggregation 问题。

## 完成标准

只有同时满足以下条件才可把主控目标标记完成：

- 当前代码已发布到目标 runtime。
- orphaned import fact dry-run 为 `ok=true`，或 apply 后复查为 `ok=true`。
- 真实小批进项、销项、银行流水导入 smoke 均成功。
- write-operation SLO audit 对 `invoice_import_confirmed` 和 `bank_import_confirmed` 通过。
- App Status 最终收敛，不存在无 active outbox 的 pending dirty scope。
- 关键页面读路径可见且 fresh。
