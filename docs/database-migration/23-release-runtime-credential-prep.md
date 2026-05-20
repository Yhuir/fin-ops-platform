# 阶段 23：Release / Runtime Credential Preparation

## 目标

阶段 23 的目标是在不切换生产服务、不修改 live systemd 配置、不重启 `fin-ops.service` 的前提下，准备可用于后续 read switch 的生产 release candidate、PostgreSQL runtime dependency、runtime role 和 root-only credential file，并用该 release candidate 执行一次 no-traffic PostgreSQL mode readiness check。

本阶段不是 cutover，不让生产 service 使用 PostgreSQL DSN。

## 执行边界

- 未修改 `/opt/fin-ops/current`。
- 未修改 `/opt/fin-ops/venv`。
- 未修改 systemd unit 或 live env。
- 未重启 `fin-ops.service`。
- 未执行 read switch 或 cutover。
- 未写 app Mongo。
- 未读取、写入或触碰 OA Mongo `form_data_db.form_data`。
- 生产 PostgreSQL 写入仅限 runtime role/privilege 和 root-only credential 文件准备。

## Prompt

阶段 23 Codex 执行 prompt：

- `prompts/23-release-runtime-credential-prep.prompt.md`

该 prompt 的最终 gate 是：

- `PASS_RELEASE_RUNTIME_CREDENTIAL_READY_REQUIRES_READ_SWITCH_AUTHORIZATION`
- 或阻断型 gate：`BLOCKED_RELEASE_CANDIDATE`、`BLOCKED_RUNTIME_DEPENDENCY`、`BLOCKED_POSTGRES_RUNTIME_ROLE`、`BLOCKED_NO_TRAFFIC_POSTGRES_SMOKE`

## 本地准备与验证

本地 release readiness 验证：

```bash
PYTHONPATH=backend/src pytest -q tests/test_postgres_state_store.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py tests/test_app_postgres_mode.py tests/test_state_store_factory_preflight.py
```

结果：

- `26 passed, 5 warnings, 6 subtests passed in 0.57s`

完整测试在阶段 23 修复后通过：

- `1268 passed, 21 skipped, 5 warnings, 50 subtests passed in 5.66s`

阶段执行期间发现 production PostgreSQL mode no-traffic check 会读取到历史 transform 遗留的 `app.etc_submission_batches.legacy_mongo_id = 'current_state:submission_batches:1'` 聚合快照行，导致 `EtcBatch` hydration 缺少单条 batch 必需字段。根因是 repository 读取 formal ETC 表时未过滤历史聚合快照行。

已在本阶段补充回归测试并修复：

- `tests/test_postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`

修复后验证：

```bash
PYTHONPATH=backend/src pytest -q tests/test_postgres_state_store.py::PostgresStateStoreTests::test_etc_repository_ignores_legacy_current_state_aggregate_rows tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_state_store_factory_preflight.py
```

结果：

- `22 passed, 5 warnings, 6 subtests passed in 0.61s`

## Production 执行结果

最终成功 run：

- Run ID：`stage23-release-runtime-20260520233335`
- Release candidate：`/opt/fin-ops/releases/stage23-release-runtime-20260520233335`
- Release source：`/opt/fin-ops/releases/stage23-release-runtime-20260520233335/src`
- Release venv：`/opt/fin-ops/releases/stage23-release-runtime-20260520233335/venv`
- Release data dir：`/opt/fin-ops/releases/stage23-release-runtime-20260520233335/data`
- Tarball sha256：`b8bf9b64ac97de7fb03d099ecef7e6dbc3344247fdb86102a571f9f5196d7196`

生产 PostgreSQL runtime role/credential 准备：

- Role：`fin_ops_app_runtime`
- Credential file：`/root/fin_ops_stage23_postgres_runtime.env`
- Credential file mode：`600`
- Redacted DSN：`postgresql://fin_ops_app_runtime:***@127.0.0.1:5432/fin_ops`
- Granted schemas：`app`、`read_model`、`job`、`audit`
- `public.schema_migrations`：`select`

No-traffic PostgreSQL mode check：

- Exit code：`0`
- App status：`ready`
- Storage backend：`postgres`
- Storage mode：`postgres`
- PostgreSQL status：`ready`
- stderr：`0 bytes`

Service state check：

- `service-before.txt` 与 `service-after.txt` diff 为空。
- `MainPID=452671`
- `ExecMainStartTimestamp=Wed 2026-05-20 16:07:52 CST`
- `ExecStart=/opt/fin-ops/venv/bin/python -m fin_ops_platform.app.main --host 127.0.0.1 --port 18001`
- `WorkingDirectory=/opt/fin-ops/current`
- `User=root`
- `ActiveState=active`
- `SubState=running`

## 报告产物

关键报告：

- `reports/stage23-release-runtime-20260520233335.stage23-summary.json`
- `reports/stage23-release-runtime-20260520233335.postgres-mode-check.json`
- `reports/stage23-release-runtime-20260520233335.postgres-mode-check.stdout.json`
- `reports/stage23-release-runtime-20260520233335.postgres-mode-check.stderr.txt`
- `reports/stage23-release-runtime-20260520233335.postgres-runtime-role.json`
- `reports/stage23-release-runtime-20260520233335.release-candidate.json`
- `reports/stage23-release-runtime-20260520233335.release-imports.txt`
- `reports/stage23-release-runtime-20260520233335.release-tarball.sha256`
- `reports/stage23-release-runtime-20260520233335.service-before.txt`
- `reports/stage23-release-runtime-20260520233335.service-after.txt`

历史阻断 run 也保留在 `reports/`，用于追溯：

- `stage23-release-runtime-20260520231736`：blocked by ETC hydration against stale aggregate row。
- `stage23-release-runtime-20260520233115`：blocked by psycopg `%` placeholder parsing in `LIKE 'current_state:%'` SQL。

## Gate

阶段 23 Gate：

- `PASS_RELEASE_RUNTIME_CREDENTIAL_READY_REQUIRES_READ_SWITCH_AUTHORIZATION`

含义：

- release candidate 可创建。
- release candidate venv 可安装 `backend/requirements.txt`，并可 import `psycopg` 和 PostgreSQL migration/runtime modules。
- production PostgreSQL runtime role 和 root-only credential file 已准备。
- no-traffic PostgreSQL app readiness check 通过。
- live production service 未切换、未重启、未修改。

## 下一步

下一阶段应进入阶段 24：controlled production read switch planning / rehearsal。

阶段 24 执行任何 production service 配置变更前必须重新运行 same-run：

- production read-only shadow-read。
- runtime policy classification。
- no-traffic PostgreSQL mode check。

只要出现 P0/P1/read error/`blocked_unknown`，必须停止。正式修改 `/opt/fin-ops/current`、systemd env、生产服务启动配置或重启服务前，需要用户单独授权。
