# 阶段 07：PostgreSQL domain repository 闭合执行记录

本文记录 2026-05-20 执行阶段 07 的结果。阶段目标是在阶段 06 `PARTIAL` 基础上继续闭合 PostgreSQL mode 的正式表 repository、domain mapper、局部增量语义和 API smoke。

## 阶段边界

- 本阶段不是生产 shadow、dual-write 或 cutover。
- 未修改、未重启生产 `fin-ops.service`。
- 未写 OA Mongo，未读取或触碰 `form_data_db.form_data`。
- 未写 app Mongo `fin_ops_platform_app`。
- 生产 PostgreSQL `fin_ops` 仅执行只读 smoke。
- destructive integration 仅在本机 disposable PostgreSQL test DB `fin_ops_stage07_test` 上执行。

## 本轮代码变更

| 文件 | 变更 |
| --- | --- |
| `backend/src/fin_ops_platform/services/postgres_repositories/__init__.py` | 新增 PostgreSQL repository package 入口。 |
| `backend/src/fin_ops_platform/services/postgres_repositories/core.py` | 新增 core repository，负责 imports、import rows、invoices、bank transactions、file imports 的正式表读写和 domain hydration。 |
| `backend/src/fin_ops_platform/services/postgres_state_store.py` | 接入 `PostgresCoreRepository`；`save()` 将关键 domain snapshot 分发写正式表；正式表优先读取、JSON snapshot 兜底；补充 workbench/read model changed-scope 删除语义；修正 bank category code/label 映射。 |
| `backend/src/fin_ops_platform/services/postgres_connection.py` | 修正 schema version bytes 解码，避免非 UTF8 test cluster 返回 bytes 时 readiness 误判。 |
| `tests/test_postgres_repositories_core.py` | 新增 core repository mapper 单测，验证 `ImportNormalizationService.from_snapshot()` 和 `FileImportService.from_snapshot()` 可消费正式表恢复结果。 |
| `tests/test_postgres_state_store_integration.py` | 新增真实 PostgreSQL imports/file_imports round-trip 和 changed-scope 删除集成测试。 |
| `tests/test_app_postgres_mode_integration.py` | 新增 no-OA PostgreSQL mode import preview/confirm API smoke，并验证 app rebuild 后仍可从正式表读取 batch。 |

## 已闭合项

- `load()["imports"]` 现在可从 `app.import_batches`、`app.import_batch_rows`、`app.invoices`、`app.bank_transactions` 恢复 domain snapshot，并可被 `ImportNormalizationService.from_snapshot()` 消费。
- `load()["file_imports"]` 现在可从 `app.import_files` 恢复 `FileImportSession` / `FileImportPreviewItem`，并可被 `FileImportService.from_snapshot()` 消费。
- `PostgresStateStore.save()` 不再只是保存 `full_state` JSON，而是对 imports、file_imports、categories、workbench/no-OA/read models、turnover、cost/tax read models、jobs/health 等已有正式表路径进行分发写入。
- `full_state` 保留为兼容兜底，但 `load()` 不再用它覆盖已经从正式表恢复出的非空 domain state。
- `workbench_read_models.changed_scope_keys` 会删除 changed 集合中已不存在的 stale scope。
- `workbench_candidate_matches.changed_scope_months` 会按月删除旧 candidates，再写入本轮 changed month 的新 candidates，保留其他月份。
- `bank_transaction_categories` 保存时兼容 service snapshot 的 `category_code` / `category_label` 字段，避免真实 category 被写成 `unknown`。
- bytes 文本归一化已补齐，避免 `uuid::text` 在异常编码环境下变成 `b'...'` 后写入 UUID 列失败。

## 仍未闭合项

阶段 07 本轮 Gate 仍为 `PARTIAL`，原因如下：

- tax certified import、ETC、historical ETC 仍主要依赖 JSONB snapshot，尚未拆出完整正式表 mapper 和 dataclass/Enum/Decimal/datetime hydration。
- pair relation/no OA/category/turnover 的 event/history 表写入仍未完整闭合。
- `read_model.search_index_rows` 仍是迁移/预留表；本轮验证了 no-OA API smoke，但尚未把 app search runtime 切到正式 search index repository。
- repository package 当前只拆出 core；workbench/read_models/ops_tax_etc 仍在 `PostgresStateStore` 内集中实现，后续应继续拆分。

这些剩余项不阻断本轮已实现功能，但阻断“全部数据库迁移完成”和生产 cutover。

## 验证记录

本地无 `FIN_OPS_TEST_DATABASE_URL` 时，PostgreSQL integration 安全 skip：

```text
python -m pytest tests/test_postgres_repositories_core.py tests/test_postgres_state_store.py tests/test_postgres_state_store_integration.py -q
9 passed, 5 skipped
```

本机 UTF8 disposable PostgreSQL cluster，数据库 `fin_ops_stage07_test`：

```text
python -m pytest tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py -q
8 passed, 12 subtests passed
```

阶段相关测试：

```text
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py -q
29 passed, 8 skipped, 10 subtests passed
```

默认全量测试：

```text
python -m pytest -q
1144 passed, 13 skipped, 17 subtests passed
```

默认 app check：

```text
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
status=ready, storage.backend=local_pickle
```

生产 PostgreSQL 只读 smoke：

```text
fin-ops.service: active
schema_migrations: 0001,0002,0003,0004,0005,0006,0007
app.import_batches=6
app.import_batch_rows=897
app.import_files=31
app.invoices=391
app.bank_transactions=431
read_model.search_index_rows=822
```

## Gate 判定

| Gate | 状态 | 依据 |
| --- | --- | --- |
| 默认模式全量测试 | PASS | `1144 passed, 13 skipped` |
| PostgreSQL integration skip guard | PASS | 无测试库时 integration skip，不误写生产 |
| disposable PostgreSQL integration | PASS | `fin_ops_stage07_test` 上 state store + app smoke 通过 |
| imports/file_imports domain hydration | PASS | 单测和真实 PostgreSQL round-trip 均通过 |
| changed-scope 局部删除语义 | PASS | real PostgreSQL integration 覆盖 workbench snapshot/candidate stale 删除 |
| 生产只读 smoke | PASS | 仅只读，服务和关键表计数正常 |
| tax/ETC/historical ETC 正式表 mapper | PARTIAL | 尚未实现完整 mapper/hydration |
| event/history 表写入 | PARTIAL | pair/no-OA/category/turnover events 尚未全部闭合 |
| production cutover 前置 | PARTIAL | 仍不可进入生产切换 |

阶段 07 结论：`PARTIAL`。本轮已显著推进 PostgreSQL mode 的核心 imports/file_imports 正式表运行能力，并增加真实 PostgreSQL/API 验证；但完整迁移仍需下一阶段继续闭合 tax/ETC/historical ETC、event/history 和 search index runtime。
