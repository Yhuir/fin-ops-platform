# 10 Shadow-read / dual-write / cutover preflight 执行记录

执行时间：2026-05-20

Gate：`PASS`

## 阶段边界

- 阶段 10 是 preflight 基础设施阶段，没有做生产 cutover。
- 没有启用生产 shadow-read、dual-write 或 PostgreSQL primary backend。
- 没有修改或重启生产 `fin-ops.service`。
- 没有写生产 PostgreSQL `fin_ops`；生产侧只做 service/schema/count 只读 smoke。
- 没有写 app Mongo `fin_ops_platform_app`。
- OA Mongo `form_data_db.form_data` 未触碰；没有读、写、建索引、清洗、备份或迁移该库/集合。
- destructive PostgreSQL integration 只在本机一次性 UTF8 test cluster 上执行，测试结束后停止并删除 cluster。

## 完成内容

### State-store diff

新增：

- `backend/src/fin_ops_platform/services/state_store_diff.py`
- `tests/test_state_store_diff.py`

能力：

- `diff_state_snapshots(primary, shadow, domain=None, ignored_paths=None, max_mismatches=20)` 支持 dict/list/scalar diff。
- mismatch path 使用稳定业务路径，例如 `imports.batches.batch_1.status`。
- 默认忽略 runtime metadata，例如 `created_at`、`updated_at`、`generated_at`、内部 PostgreSQL id 和 `raw_payload.migration_metadata`。
- `redact_diff_payload()` 会移除 secret-like key，并把 URI 脱敏为 `<redacted-uri>`。
- diff result 可 JSON 序列化。

### ShadowStateStore

新增：

- `backend/src/fin_ops_platform/services/shadow_state_store.py`
- `tests/test_shadow_state_store.py`

能力：

- read path 先返回 primary 结果，shadow compare 为 best-effort，不阻断主请求。
- write path 默认仍只写 primary；阶段 10 没有做 shadow write。
- `shadow_summary()` 记录 compared、matched、mismatched、shadow_errors、last_mismatch、last_error。
- shadow 异常和 mismatch summary 做脱敏。
- 支持 `compare_enabled` 和 `compare_sample_rate`；默认 compare disabled，sample rate 默认 `1.0`。

### DualStateStore

新增：

- `backend/src/fin_ops_platform/services/dual_state_store.py`
- `tests/test_dual_state_store.py`

能力：

- write path 执行 primary first，然后 mirror。
- primary failure 时不执行 mirror，原异常向上传递。
- non-strict mirror failure 不阻断 primary success，但记录 `mirror_failed`、`last_failure` 和 callback event。
- strict mirror failure 抛出 `DualWriteMirrorError`。
- file-object write 目前 primary-only，并在 `primary_only_methods` 中记录，避免在没有文件 mirror 策略时误写。
- `dual_write_summary()` 记录 primary/mirror success/failure、strict failure 和最后失败摘要。
- 所有失败摘要脱敏，避免输出完整 URI、password、token。

### Factory guard

修改：

- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `tests/test_state_store_factory_preflight.py`

新增 preflight-only backend：

- `FIN_OPS_APP_STORAGE_BACKEND=shadow`
- `FIN_OPS_APP_STORAGE_BACKEND=dual`

新增 guard/config：

- `FIN_OPS_PRIMARY_STORAGE_BACKEND`
- `FIN_OPS_SHADOW_STORAGE_BACKEND`
- `FIN_OPS_MIRROR_STORAGE_BACKEND`
- `FIN_OPS_SHADOW_COMPARE_ENABLED`
- `FIN_OPS_SHADOW_COMPARE_SAMPLE_RATE`
- `FIN_OPS_DUAL_WRITE_STRICT`
- `FIN_OPS_CUTOVER_PREFLIGHT_ONLY`

规则：

- 默认未配置时仍返回 `ApplicationStateStore`，不初始化 PostgreSQL。
- `postgres` backend 行为保持原有方式。
- `shadow` 和 `dual` 必须显式声明 primary/shadow/mirror backend。
- preflight wrapper 当前只允许 `local_pickle` 与 `postgres`，明确拒绝 `mongo`，避免阶段 10 accidentally 构造 app Mongo writer。
- `dual` 必须设置 `FIN_OPS_CUTOVER_PREFLIGHT_ONLY=1`，否则 fail-fast。
- boolean、sample rate 和 URI-like 错误输出均有校验和脱敏。

### Cutover preflight

新增：

- `backend/src/fin_ops_platform/services/cutover_preflight.py`
- `backend/src/fin_ops_platform/tools/verify_cutover_preflight.py`
- `tests/test_cutover_preflight.py`

能力：

- `CutoverPreflightChecker` 只读查询 PostgreSQL health、schema version、`public.schema_migrations` location 和核心表 counts。
- CLI 支持 `--json`、`--require-backup-confirmation`、`--database-url-env`。
- CLI 明确拒绝 `--cutover`、`--enable-dual-write`、`--restart-service`、`--write`、`--production-write`。
- preflight report 包含 guards、backup checklist、rollback checklist、readiness summary。
- CLI 异常边界和 report 输出均脱敏。
- 修复并测试了模块命令行入口读取 `sys.argv[1:]` 的行为，`python -m ... --json` 会输出 JSON。

## 生产只读 smoke

阶段 10 只执行生产只读检查：

```text
fin-ops.service=active
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

说明：生产库 migration 记录表位于 `public.schema_migrations`。

## 验证记录

新增/阶段 10 目标测试：

```text
python -m pytest tests/test_state_store_diff.py tests/test_shadow_state_store.py tests/test_dual_state_store.py tests/test_cutover_preflight.py tests/test_state_store_factory_preflight.py -q
39 passed, 9 subtests passed
```

阶段 09 + 阶段 10 回归矩阵：

```text
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py tests/test_state_store_diff.py tests/test_shadow_state_store.py tests/test_dual_state_store.py tests/test_cutover_preflight.py tests/test_state_store_factory_preflight.py -q
72 passed, 11 skipped, 5 warnings, 19 subtests passed
```

默认 app check：

```text
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
status=ready
storage.backend=local_pickle
```

默认全量测试：

```text
python -m pytest -q
1187 passed, 16 skipped, 5 warnings, 26 subtests passed
```

本机 UTF8 disposable PostgreSQL `fin_ops_stage10_test`：

```text
python -m pytest tests/test_postgres_migrations.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py -q
21 passed, 5 warnings, 16 subtests passed
```

本机 UTF8 disposable PostgreSQL preflight CLI：

```text
PYTHONPATH=backend/src python -m fin_ops_platform.tools.verify_cutover_preflight --json
status=pass
postgres.connectivity=ready
postgres.schema_version=0007
postgres.schema_migrations_table=public.schema_migrations
guards.no_production_writes=enforced
```

## Gate 判定

`PASS`

阶段 10 已完成：

- shadow-read diff 基础设施可用，默认不启用，compare 不阻断 primary read。
- dual-write/mirror-write wrapper 可用，具备 strict/non-strict failure semantics、primary-first 语义和脱敏摘要。
- factory guard 可显式构造 shadow/dual preflight wrapper，并拒绝不完整或危险配置。
- cutover preflight CLI 可只读检查 PostgreSQL readiness，并拒绝切换/写入动作。
- 默认 local/Mongo 行为保持，app check 仍为 `local_pickle`。
- 真实 PostgreSQL integration 通过。
- 生产 PostgreSQL 只读 smoke 通过。

阶段 10 没有完成、也不应该完成的内容：

- 没有真正生产 shadow-read 观测窗口。
- 没有真正生产 dual-write 观测窗口。
- 没有生产 cutover。
- 没有验证最终 cutover freeze window、人工备份确认和业务验收签字。

## 下一步

可以进入阶段 11：生产 shadow-read 演练规划与执行。

阶段 11 进入前需要明确：

- 生产 shadow-read 的 primary/shadow backend 配置和采样率。
- mismatch 观察窗口、阈值、告警接收人和人工判定流程。
- 不写 app Mongo、不写 OA Mongo、不切换事实源的运行守卫。
- cutover 前 PostgreSQL/app Mongo 备份确认人和保留策略。
