---
status: ready_for_operator
phase: 16-imports-invoices-improvements
updated: 2026-06-21T00:35:28+08:00
---

# 导入 Read Model 闭环运维执行包

本文是给运维/发布执行人的短命令包。完整背景见 `16-RELEASE-RUNBOOK.md`。

## 0. 禁止事项

- 未获批准时不要运行任何 `--apply`。
- 未获批准时不要执行真实导入写入 smoke。
- 不要手写 `read_model.app_status_readiness.status='fresh'`。
- 不要删除 current uncovered failed/dead-letter outbox event 来让 App Status 变绿。

## 1. 发布前只读证据

在仓库根目录执行：

```bash
git status --short

pytest tests/test_import_processing_service.py tests/test_import_job_queue.py tests/test_import_api.py tests/test_import_file_api.py tests/test_import_service.py tests/test_postgres_repositories_core.py tests/test_runtime_queue.py tests/test_runtime_worker.py tests/test_runtime_monitoring.py tests/test_runtime_worker_registry.py tests/test_read_model_refresh_gateway.py tests/test_read_model_scope_contract.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_bank_detail_for_transaction_month_scopes tests/test_write_operation_slo_audit.py tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_read_model_refresh_producers_use_scope_gateway_boundary -q

cd web && npx playwright test e2e/imports-invoices-flow.spec.ts e2e/imports-bank-transactions-flow.spec.ts
cd ..

python -m compileall backend/src/fin_ops_platform/services/import_processing_service.py backend/src/fin_ops_platform/services/runtime_worker_handlers.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/postgres_repositories/core.py backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/services/runtime_queue.py backend/src/fin_ops_platform/tools/write_operation_slo_audit.py backend/src/fin_ops_platform/services/read_model_scope_contract.py backend/src/fin_ops_platform/services/postgres_repositories/read_model_scope_contracts.py
PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help
bash scripts/verify.sh docs
git diff --check
```

通过标准：

- pytest 输出 `182 passed`。
- Playwright 输出 `13 passed`。
- 其余命令退出码为 0。

## 2. 运行态只读检查

```bash
./scripts/check-local-runtime.sh --dependencies-only
```

若输出 SSH tunnel warning，只可作为功能连通性证据，不可作为性能验收。

```bash
set -a
source .runtime/fin_ops_platform/local-postgres.env
set +a
scripts/check-read-model-scope-contracts.py --repair orphaned-import-facts --json | tee /tmp/finops-orphaned-import-facts-dry-run.json
```

当前已知输出摘要：

```json
{
  "ok": false,
  "orphaned_dirty_scope_count": 42,
  "cleanup": {"applied": false}
}
```

如果 dry-run 不是 `ok=false` 或数量明显变化，先复核 `items[]`，不要直接沿用历史结论。

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit \
  --json \
  --operation invoice_import_confirmed \
  --operation bank_import_confirmed \
  --lookback-hours 72 \
  --target-ms 5000 \
  | tee /tmp/finops-import-write-slo-before-release.json
```

发布前该命令可能失败；它用于保留旧运行态基线。

## 3. 发布

按生产发布入口执行。发布后必须确认 API/worker 是同一 release。

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_worker_manifest --json
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --registration import --worker-instance import --check
```

必须看到 import worker claim/handler 覆盖：

- `import.process.requested`
- `import.fact.changed`

## 4. Orphaned Dirty Scope Apply

只在审批窗口内执行。

```bash
scripts/check-read-model-scope-contracts.py \
  --repair orphaned-import-facts \
  --apply \
  --reason production_orphaned_import_fact_cleanup \
  --json \
  | tee /tmp/finops-orphaned-import-facts-apply.json
```

通过标准：

```json
{
  "cleanup": {
    "applied": true,
    "deleted": {"job.read_model_dirty_scopes": 42}
  },
  "repair_audit": {"recorded": true}
}
```

随后复查：

```bash
scripts/check-read-model-scope-contracts.py --repair orphaned-import-facts --json | tee /tmp/finops-orphaned-import-facts-post-check.json
```

通过标准：`ok=true` 且 `orphaned_dirty_scope_count=0`。

## 5. Apply 回滚模板

只在误删时使用 apply JSON 的 `items[].row` 恢复。优先在事务中恢复并立即复查。

```sql
begin;

insert into job.read_model_dirty_scopes (
  id,
  tenant_id,
  scope_type,
  scope_key,
  status,
  reason,
  last_error,
  updated_at
) values (
  '<row.id>'::uuid,
  '<row.tenant_id>',
  '<row.scope_type>',
  '<row.scope_key>',
  '<row.status>',
  '<row.reason>',
  nullif('<row.last_error>', ''),
  '<row.updated_at>'::timestamptz
)
on conflict (id) do nothing;

commit;
```

如果 apply JSON 中 `row.last_error` 为 `null`，上面的 `nullif` 应改为 SQL `null`。

回滚后：

```bash
scripts/check-read-model-scope-contracts.py --repair orphaned-import-facts --json
```

预期：被恢复的 row 再次出现在 `items[]`。

## 6. 真实导入 Smoke

需要已批准的小样本和认证上下文。

记录三类导入：

- 进项发票。
- 销项发票。
- 银行流水。

每类都记录：

- preview start/end。
- confirm start/end。
- background job id/status。
- outbox event types and done time。
- dirty scope done time。
- App Status ready/fresh time。

发布后 SLO：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit \
  --json \
  --operation invoice_import_confirmed \
  --operation bank_import_confirmed \
  --lookback-hours 2 \
  --target-ms 5000 \
  --p99-target-ms 5000 \
  | tee /tmp/finops-import-write-slo-after-release.json
```

通过标准：

- `status=pass`。
- Required expectations 不 missing。
- `bank_detail.read_model.refresh` present。
- `bank_account_balance.read_model.refresh` present。
- 非命中方向页可以 `skipped`。

## 7. 最终完成判定

只有同时满足以下条件，才可把主控目标标记 complete：

- 当前 release 已部署。
- orphaned dirty scope post-check 为 `ok=true`。
- 三类真实导入 smoke 成功。
- write-operation SLO audit 通过。
- App Status 最终 ok/fresh。
- 关键页面读取 fresh 且能看到新增导入事实。
