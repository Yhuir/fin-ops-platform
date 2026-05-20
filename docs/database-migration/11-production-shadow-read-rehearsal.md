# 11 Production shadow-read rehearsal 执行记录

执行时间：2026-05-20

Gate：`PARTIAL`

## 阶段边界

- 阶段 11 没有做 production cutover。
- 没有启用 production dual-write 或 mirror-write。
- 没有把生产 backend 切到 PostgreSQL、shadow 或 dual。
- 没有修改或重启生产 `fin-ops.service`。
- 没有写生产 PostgreSQL `fin_ops`；生产侧只做 service/schema/count/health 只读检查。
- 没有写 app Mongo `fin_ops_platform_app`。
- OA Mongo `form_data_db.form_data` 未触碰；没有读、写、建索引、清洗、备份或迁移该库/集合。
- destructive PostgreSQL integration 只在本机一次性 UTF8 test cluster 的 `fin_ops_stage11_test` 上执行，测试结束后停止并删除 cluster。

## 完成内容

### ShadowReadRehearsalRunner

新增：

- `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
- `tests/test_shadow_read_rehearsal.py`

能力：

- 定义 `ShadowReadDomainSpec`、`ShadowReadDomainResult`、`ShadowReadRehearsalReport`。
- `ShadowReadRehearsalRunner` 只调用白名单 read methods，拒绝 `save*`、`store*`、`delete*`、`truncate*`、`confirm*`、`submit*`、`withdraw*`、`revert*`、`clear*` 等非只读方法。
- 明确排除高风险 read methods：`load`、文件 bytes 读取、historical ETC bundle content 读取、OA sync/manual/cache entry 等。
- 每个 domain 先读 primary，再读 shadow，然后复用阶段 10 的 `diff_state_snapshots()`。
- primary/shadow error 不会写入任何数据，会进入 domain result 并影响 Gate。
- mismatch 支持 P0/P1/P2/ignored 分级。
- report JSON serializable，并通过 `redact_diff_payload()` 脱敏。

### 只读 rehearsal CLI

新增：

- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`

能力：

- 支持 `--json`、`--markdown`、`--output`、`--domains`、`--limit`、`--primary-backend`、`--shadow-backend`、`--data-dir`、`--run-id`、`--production`、`--require-read-only-guard`。
- CLI 拒绝 `--cutover`、`--enable-dual-write`、`--dual-write`、`--write`、`--restart-service`、`--switch-backend`。
- `--production` 或 `--require-read-only-guard` 必须设置 `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1`。
- 支持 backend：
  - `local_pickle`
  - `postgres`
  - `mongo_readonly` 仅作为 primary backend，且必须显式 read-only guard；不通过 `state_store_factory.py` 放宽生产 preflight guard。
- 默认 artifact 写入 `docs/database-migration/reports/`，文件名包含 run id 和 `stage11.shadow-read`。

### 初始 domain 白名单

阶段 11 初始白名单以“无参数、app state-store 合约内、无需 OA adapter、无需读取文件 bytes”为硬门槛。推荐第一批：

- `app_settings` / `load_app_settings`
- `background_jobs` / `load_background_jobs`
- `app_health_alerts` / `load_app_health_alerts`
- `workbench_pair_relations` / `load_workbench_pair_relations`
- `no_oa_bank_batches` / `load_no_oa_bank_batches`
- `bank_transaction_categories` / `load_bank_transaction_categories`
- `turnover_relations` / `load_turnover_relations`
- `turnover_relation_audit_log` / `load_turnover_relation_audit_log`
- `turnover_ledger_extras` / `load_turnover_ledger_extras`
- `workbench_read_models` / `load_workbench_read_models`
- `workbench_candidate_matches` / `load_workbench_candidate_matches`
- `cost_statistics_read_models` / `load_cost_statistics_read_models`
- `tax_offset_read_models` / `load_tax_offset_read_models`
- `tax_certified_imports` / `load_tax_certified_imports`
- `etc_state` / `load_etc_state`
- `etc_reconciliation_state` / `load_etc_reconciliation_state`
- `historical_etc_repair_bundle_metadata` / `load_historical_etc_repair_bundle_metadata`
- `historical_etc_repair_parsed_seeds` / `load_historical_etc_repair_parsed_seeds`
- `historical_etc_repair_states` / `load_historical_etc_repair_states`

不纳入初始白名单：

- `load()`：可能触发 legacy/split fallback 噪声，且风险大。
- `read_import_file()`、`read_etc_reconciliation_file()`、`read_etc_invoice_file()`、`read_historical_etc_repair_bundle()`：读取文件或 bytes，不适合作为第一批 shadow-read rehearsal。
- `*_exists(id)`：需要业务 ID 参数，后续可从已比对 snapshot 采样。
- OA adapter 读路径和 OA Mongo `form_data_db.form_data`：阶段 11 不纳入。
- 所有写入或状态变更方法。

## 生产只读盘点

本阶段主线程完成了生产只读复核：

```text
fin-ops.service=active
ExecStart=/opt/fin-ops/venv/bin/python -m fin_ops_platform.app.main --host 127.0.0.1 --port 18001
WorkingDirectory=/opt/fin-ops/current
FragmentPath=/etc/systemd/system/fin-ops.service
DropInPaths=/etc/systemd/system/fin-ops.service.d/10-fin-ops-env.conf
```

生产 `/health` 当前 storage：

```text
health_status=ready
health_storage_backend=mongo
health_storage_mode=mongo_only
health_storage_database=fin_ops_platform_app
```

阶段 10/11 代码部署状态：

```text
stage10_shadow_file=absent
stage11_file=absent
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

systemd/drop-in env key names 只读检查未输出 secret values。观察到与 app/OA 服务相关的 key names，但没有输出任何值。

## Production rehearsal 结果

本阶段没有执行真实 production shadow-read rehearsal。

原因：

- 生产当前 primary state source 是 app Mongo `fin_ops_platform_app`，运行模式 `mongo_only`。
- 服务器 `/opt/fin-ops/current/backend` 下没有阶段 10/11 新增 shadow/preflight/rehearsal 代码文件。
- service-level shadow-read 需要部署代码、修改配置或重启服务，阶段 11 prompt 明确禁止在未获用户授权时执行。
- one-off server-side rehearsal 也需要把阶段 11 CLI/runner 部署或复制到服务器，这属于生产文件变更，本阶段未授权。

因此 production rehearsal artifact 为 blocked report：

- `docs/database-migration/reports/stage11-production-shadow-read-rehearsal.blocked.json`

## 验证记录

阶段 11 runner/CLI + 阶段 10 相关测试：

```text
python -m pytest tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_shadow_state_store.py tests/test_cutover_preflight.py tests/test_state_store_factory_preflight.py -q
42 passed, 13 subtests passed
```

阶段 09 PostgreSQL 回归矩阵：

```text
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q
32 passed, 11 skipped, 5 warnings, 10 subtests passed
```

默认全量测试：

```text
python -m pytest -q
1197 passed, 16 skipped, 5 warnings, 30 subtests passed
```

默认 app check：

```text
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
status=ready
storage.backend=local_pickle
```

本机 UTF8 disposable PostgreSQL `fin_ops_stage11_test`：

```text
python -m pytest tests/test_postgres_migrations.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py -q
21 passed, 5 warnings, 16 subtests passed
```

本机 UTF8 disposable PostgreSQL shadow rehearsal CLI：

```text
PYTHONPATH=backend/src python -m fin_ops_platform.tools.run_shadow_read_rehearsal --json --production --primary-backend postgres --shadow-backend postgres --domains app_settings,background_jobs
gate=PASS
matched=2
domains=2
```

## Gate 判定

`PARTIAL`

已完成：

- 阶段 11 本地 runner/CLI 能力完成并有测试覆盖。
- 可比对 domain 白名单和排除项已固化。
- 默认 local/Mongo 行为保持，app check 仍为 `local_pickle`。
- 全量测试通过。
- 本机真实 PostgreSQL integration 和 rehearsal CLI 通过。
- 生产运行形态已只读确认：当前 app primary 是 Mongo `fin_ops_platform_app`。
- 生产 PostgreSQL schema/counts 只读复核通过。

未完成：

- 真实 production shadow-read rehearsal 没有执行。

阻塞原因：

- `BLOCKED_FOR_PRODUCTION_REHEARSAL_CODE_NOT_DEPLOYED`
- `BLOCKED_REQUIRES_PRODUCTION_CODE_DEPLOY_OR_ONE_OFF_CODE_SYNC_AUTHORIZATION`

## 下一步

阶段 12 前需要用户明确授权一个生产只读演练路径：

1. 部署当前阶段 11 代码到服务器，但不改 backend、不启用 dual-write、不 cutover。
2. 在服务器上以 one-off 命令执行 `run_shadow_read_rehearsal`，设置 `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1`。
3. 初始 production rehearsal 只跑保守 domain：
   - `app_settings`
   - `background_jobs`
   - `app_health_alerts`
   - `workbench_pair_relations`
   - `no_oa_bank_batches`
   - `bank_transaction_categories`
   - `turnover_relations`
4. 观察 report 中是否有未解释 P0/P1 mismatch。

只有 production shadow-read rehearsal report 无未解释 P0/P1 后，才建议进入阶段 12：controlled dual-write / mirror-write rehearsal planning。
