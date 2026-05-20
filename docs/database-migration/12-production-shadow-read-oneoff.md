# 12 Production shadow-read one-off 执行记录

执行时间：2026-05-20

Gate：`BLOCKED`

## 阶段边界

- 阶段 12 只执行授权后的 production one-off shadow-read rehearsal。
- 没有做 production cutover。
- 没有启用 production dual-write 或 mirror-write。
- 没有把生产 backend 切到 PostgreSQL、shadow 或 dual。
- 没有修改或重启生产 `fin-ops.service`。
- 没有修改 `/etc/systemd/*`、systemd drop-in、生产配置或 `/opt/fin-ops/current`。
- 没有写生产 PostgreSQL `fin_ops`；PostgreSQL 访问限定为固定 SELECT，并在 `READ ONLY` transaction 中执行。
- 没有写 app Mongo `fin_ops_platform_app`；primary store 使用 `ApplicationStateStore(read_only=True)`。
- OA Mongo `form_data_db.form_data` 未触碰；没有读、写、建索引、清洗、备份或迁移该库/集合。
- 远端只写入阶段 12 临时目录 `/tmp/finops-stage12-shadow-read-<run_id>/`，report 取回本地后已清理远端临时代码和 report 副本。

## 阶段 11 承接事实

- 阶段 11 Gate 为 `PARTIAL`。
- 阶段 11 已完成本地 `ShadowReadRehearsalRunner`、CLI 和测试。
- 阶段 11 没有执行真实 production shadow-read rehearsal，原因是生产服务器没有阶段 10/11 新增代码，且当时未授权生产临时代码同步。
- 阶段 11 blocked artifact：`docs/database-migration/reports/stage11-production-shadow-read-rehearsal.blocked.json`。
- 用户已授权阶段 12 one-off 只读演练路径。

## 本阶段代码加固

阶段 12 发现生产 venv 缺少 `psycopg`，不能直接使用 `PostgresStateStore` 的 native PostgreSQL backend。为避免安装依赖或修改生产 venv，本阶段新增只读 `psql` shadow store：

- `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py` 新增 `--shadow-backend postgres_psql_json`
- `tests/test_shadow_read_rehearsal.py` 新增 CLI/backend 覆盖

安全设计：

- 只暴露阶段 12 conservative domain 需要的 `load_*` 方法。
- 只使用代码内固定 SQL，不接受外部 SQL。
- 每次 query 都以 `begin transaction read only` 开启事务，并设置 `statement_timeout`。
- 通过 `sudo -u postgres psql -d fin_ops` 读取生产 PostgreSQL，未打印 DSN 或 secret。
- mismatch sample 只保留 path/kind/severity、类型、数量和 sha256 指纹，不保留 primary/shadow 原始业务 payload。

注意：这是 one-off rehearsal 适配器，不是长期 production runtime backend。后续 controlled dual-write/cutover 仍应使用正式 PostgreSQL driver/connection 和最小权限数据库账号。

## 本地验证

阶段 12 修改后已运行：

```text
python -m py_compile backend/src/fin_ops_platform/services/shadow_read_psql_store.py backend/src/fin_ops_platform/services/shadow_read_rehearsal.py backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py tests/test_shadow_read_rehearsal.py
python -m pytest tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_shadow_state_store.py tests/test_cutover_preflight.py tests/test_state_store_factory_preflight.py -q
44 passed, 13 subtests passed
```

后续全量验证见本文末尾。

## 生产只读预检

生产服务状态：

```text
service_active=active
main_pid=251543
working_dir=/opt/fin-ops/current
python_version=Python 3.11.6
tmp_writable=yes
```

生产 `/health`：

```text
health_status=ready
health_storage_backend=mongo
health_storage_mode=mongo_only
health_storage_database=fin_ops_platform_app
```

生产 PostgreSQL 只读 smoke：

```text
schema_migrations=0001,0002,0003,0004,0005,0006,0007
counts=6,897,31,391,431,822
```

计数顺序：

```text
app.import_batches,
app.import_batch_rows,
app.import_files,
app.invoices,
app.bank_transactions,
read_model.search_index_rows
```

生产进程环境只输出 `FIN_OPS_*` key names，没有输出任何 env value、URI、密码或 token。

## Production one-off rehearsal

最终有效 run：

```text
run_id=stage12-shadow-read-20260520142049
primary_backend=mongo_readonly
shadow_backend=postgres_psql_json
limit=10
remote_temp_dir=/tmp/finops-stage12-shadow-read-stage12-shadow-read-20260520142049
local_report=docs/database-migration/reports/stage12-shadow-read-20260520142049.stage12.shadow-read.json
cli_exit=1
report_gate=BLOCKED
redaction_scan=passed
```

执行 domain 白名单：

- `app_settings`
- `background_jobs`
- `app_health_alerts`
- `workbench_pair_relations`
- `no_oa_bank_batches`
- `bank_transaction_categories`
- `turnover_relations`

服务状态 before/after：

```text
service_before=active:251543
service_after=active:251543
service_after_cleanup=active:251543
working_dir_after_cleanup=/opt/fin-ops/current
```

远端临时目录清理：

```text
removed=/tmp/finops-stage12-shadow-read-stage12-shadow-read-20260520141251
removed=/tmp/finops-stage12-shadow-read-stage12-shadow-read-20260520141749
removed=/tmp/finops-stage12-shadow-read-stage12-shadow-read-20260520142049
```

## Report 摘要

Artifact：

- `docs/database-migration/reports/stage12-shadow-read-20260520142049.stage12.shadow-read.json`

总览：

```text
total_domains=7
compared_domains=7
matched_domains=0
mismatched_domains=7
primary_errors=0
shadow_errors=0
severity_counts=P0:14,P1:8,P2:12,ignored:0
gate=BLOCKED
```

Domain 结果：

| Domain | Status | Mismatches | P0 | P1 | P2 |
| --- | --- | ---: | ---: | ---: | ---: |
| `app_settings` | `mismatched` | 5 | 0 | 5 | 0 |
| `background_jobs` | `mismatched` | 10 | 0 | 0 | 10 |
| `app_health_alerts` | `mismatched` | 2 | 0 | 0 | 2 |
| `workbench_pair_relations` | `mismatched` | 10 | 10 | 0 | 0 |
| `no_oa_bank_batches` | `mismatched` | 1 | 1 | 0 | 0 |
| `bank_transaction_categories` | `mismatched` | 3 | 0 | 3 | 0 |
| `turnover_relations` | `mismatched` | 3 | 3 | 0 | 0 |

主要 mismatch 类型，已脱敏且不包含业务原文：

- `app_settings`：`allowed_usernames` 长度和顺序/成员指纹不一致。
- `background_jobs`：PostgreSQL shadow 中存在 primary Mongo 当前未出现的 job ids，样本上限 10。
- `app_health_alerts`：primary 与 shadow 的 health alert snapshot 形态不一致。
- `workbench_pair_relations`：pair relation history 数量和 event payload 形态不一致，包含 P0。
- `no_oa_bank_batches`：primary 有 `schema_version`，shadow 缺失，包含 P0。
- `bank_transaction_categories`：primary 有 `schema_version`、`audit_log`、`categories` snapshot 形态，shadow 缺失或形态不一致，包含 P1。
- `turnover_relations`：primary 有 `schema_version`、`audit_log`、`relations` snapshot 形态，shadow 缺失，包含 P0。

## Gate 判定

`BLOCKED`

已完成：

- 真实 production one-off shadow-read rehearsal 已执行。
- report artifact 已取回本地。
- report JSON parse 通过。
- report 脱敏扫描通过。
- 生产服务未修改、未重启，PID 前后不变。
- 生产 PostgreSQL 未写入。
- app Mongo 仅以 `read_only=True` 读取。
- OA Mongo `form_data_db.form_data` 未触碰。
- 远端临时代码和 report 副本已清理。

阻塞原因：

- 7/7 conservative domains 均出现 mismatch。
- 存在未解释 P0/P1 mismatch：`P0=14`、`P1=8`。
- 因存在未解释 P0/P1，不能进入 controlled dual-write、mirror-write 或 production cutover。

## 用户下一步需要做什么

进入下一阶段前必须先修复或解释阶段 12 report 中的 P0/P1 mismatch：

1. 针对 `app_settings` 修复 allowed user 配置的 backfill/同步差异，确认 PostgreSQL 与当前 app Mongo primary 的业务等价规则。
2. 针对 `workbench_pair_relations` 修复 pair relation history 的转换形态，确认 event history 不被包装成 snapshot payload。
3. 针对 `no_oa_bank_batches`、`bank_transaction_categories`、`turnover_relations` 修复 `schema_version`、`audit_log`、空集合 snapshot 的 PostgreSQL 表达方式，或在 diff 规则中明确可解释忽略项。
4. 针对 `background_jobs` 和 `app_health_alerts` 明确这些 runtime 状态是否应该迁移、重建、清空或作为 P2 可解释差异处理。
5. 修复后重新执行 production one-off shadow-read rehearsal，直到 conservative domains 无未解释 P0/P1。

只有阶段 12 重跑达到 `PASS`，或所有 P0/P1 都有可审计解释并降级，才适合生成下一阶段 controlled dual-write / mirror-write rehearsal prompt。

## 最终验证记录

阶段 12 runner/CLI + shadow/preflight 相关测试：

```text
python -m pytest tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_shadow_state_store.py tests/test_cutover_preflight.py tests/test_state_store_factory_preflight.py -q
44 passed, 13 subtests passed
```

PostgreSQL 回归矩阵：

```text
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q
32 passed, 11 skipped, 5 warnings, 10 subtests passed
```

默认全量测试：

```text
python -m pytest -q
1199 passed, 16 skipped, 5 warnings, 30 subtests passed
```

默认 app check：

```text
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
status=ready
storage.backend=local_pickle
```
