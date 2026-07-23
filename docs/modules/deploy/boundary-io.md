# 部署模块边界与 I/O

日期：2026-07-05

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：部署模块负责发布、runtime worker/systemd/env/nginx/verify，不承载业务逻辑。
- 当前缺口：无 P0/P1 模块化缺口；新增 read model/worker 仍必须同步 deploy examples 和 runtime worker manifest。
- 旧代码删除状态：`legacy-current` 覆盖式发布入口、旧单文件 `deploy/oa/fin_ops.env.example` 和 systemd 示例中的 current/backend runtime 路径已移除；import worker/dispatcher env 已移除退役的 `import.fact.changed` event，只保留 `import.process.requested`。release helper 只保留历史 `/opt/fin-ops/current` 归档/guard，不作为旧发布 I/O。

## 职责边界

### 负责

- `deploy-oa` 发布入口、nginx/systemd/env examples、runtime worker 确保脚本、verify 脚本。
- 生产 rollout、worker manifest、部署前后校验。

### 不负责

- 不直接修复业务数据。
- 不定义业务 API。
- 不绕过应用层执行生产写操作。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Deploy command | `scripts/deploy-oa.sh` | 使用明确 release/remote/env |
| Runtime worker manifest | `runtime_worker_manifest.py` | 必须匹配 registry |
| Verify command | `scripts/verify.sh` | 按 backend/web/docs/ops 分类执行 |
| Runtime env examples | `deploy/oa/env/*.env.example` | 按 common/secrets/migrator/worker/dispatcher 拆分，禁止恢复单文件 env |
| Controlled write smoke stdin | operator | `--apply-stdin` 第一行为 Admin Token、第二行为 approval ticket；两者均必填且不落盘。consumer assertion 只接受 typed `equals` / `contains` / `excludes`；`excludes` 只能证明已登记业务根不再含显式 test-owned row/case identity，不能解除 fixture identity gate |
| Optional write smoke restore point | operator | 只在风险与成本相称时使用 `write-operation-restore-point <release> <run-id>`；明确 test-owned、幂等且自动执行 inverse/recovery 的 relation smoke 不以全库备份作为固定前置。创建命令使用既有 migrator DSN 跨 schema 只读导出，只通过 `PG*` 子进程环境传递连接字段，并以 `pg_restore --list` + SHA-256 manifest 验证；删除只能用 `write-operation-restore-point-delete <run-id> <expected-sha256>` 精确匹配固定目录、文件集合、manifest identity 和 dump checksum |
| Request error lookup | API `requestId` | 只接受 12 位小写十六进制 ID，并从最近两小时 API journal 返回精确匹配的单行异常；不开放任意日志查询 |
| Request traceback lookup | API `requestId` | 同一严格 ID 和两小时时间窗；从异常摘要开始最多返回 64 行，并在 traceback 终止异常行停止；不包含 locals，不开放任意 journal 参数 |
| Import audit repair | `finops-deploy-control import-audit-repair` | 只调用固定 Python module；execute 必须携带同一数据快照 dry-run 返回的 SHA-256 fingerprint；生命周期修复必须同时显式提供唯一 `--batch-id` / `--file-id` |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Release artifact | 生产服务器 | 可追踪版本 |
| systemd/env files | deploy/oa | 与 registry 一致 |
| Verification result | operator/CI | 失败不得伪装成功 |
| Bounded request traceback | operator | 仅用于把已知生产 500 定位到 release 文件和行号；不得输出业务 payload、token 或任意日志窗口 |
| Write smoke restore-point manifest | operator | 固定记录 release、run-id、UTC 时间、dump 路径、字节数、格式和 SHA-256；不得包含 DSN、token 或业务 payload |

## 持久化与投影

- Own read model：无。
- Worker contract：`runtime_worker_registry.py`、systemd/env examples。
- Production docs：`docs/operations/`、`deploy/oa/README.md`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Scripts | `scripts/deploy-oa.sh`、`scripts/deploy_oa.py`、`scripts/verify.sh` |
| CI | `.github/workflows/nightly-ci.yml` |
| Deploy control | `deploy/oa/bin/finops-deploy-control.sh`、`finops-ensure-runtime-workers.sh` |
| Examples | `deploy/oa/nginx.fin-ops.conf.example`、`deploy/oa/systemd/*.service.example`、`deploy/oa/env/*.env.example` |
| Worker manifest | `backend/src/fin_ops_platform/tools/runtime_worker_manifest.py`、`runtime_worker_registry.py` |
| Tests | `tests/test_deploy_*.py`、`tests/test_runtime_worker_registry.py` |

## 依赖方向

- 允许依赖：runtime worker registry, operations docs, CI verify scripts。
- 必须通过：documented deploy scripts.
- 禁止绕过：ad hoc production edits without operations docs; scripts embedding business fixes.

## 测试与验证

- `tests/test_deploy_oa_script.py`
- `tests/test_deploy_runtime_examples.py`
- `bash scripts/verify.sh docs`

## 当前缺口和删除条件

- 新增 worker/read model 是 deploy-impacting change，必须同步 examples、docs、tests。
- 禁止恢复 `--mode legacy-current`、`build_legacy_remote_deploy_script`、`create_legacy_release_archive` 或 `deploy/oa/fin_ops.env.example`。
- 禁止在 systemd examples 或发布脚本中恢复 `/opt/fin-ops/current/backend` 作为运行目录。
- `finops-deploy-control` 对 legacy current 的归档只用于 release 激活前清理历史 runtime，不得重新变成覆盖式发布入口。

## Phase 19 受控生产命令（2026-07-12）

- `read-model-refresh` 只调用 `runtime_queue_ops enqueue-read-model-refresh`，由 scope policy 和 `ReadModelRefreshGateway` 写 durable queue；必须显式 dry-run 或 execute。
- `settings-normalize` 只调用 canonical settings normalizer/repository tool。
- `import-audit-repair` 只允许写 `app.import_batch_rows`、`app.invoices`，以及显式目标的 `app.import_batches` / `app.import_files` 生命周期字段：dry-run 使用 repeatable-read read-only snapshot；execute 使用 serializable transaction、advisory lock、expected fingerprint 和 owner/precondition guard，并输出 rollback manifest。生命周期修复还必须由唯一 succeeded job、注册行计数、canonical invoice owner 与 `manual_invoice_import` source-link 闭环共同证明；被旧 preview 清空的 row link 只允许按 batch + source identity 一对一恢复，并以单条 bulk SQL 更新。helper 不接受 SQL、通配目标或任意 module 名。
- `runtime-queue-resolve-covered` 只处理已有 exact-scope fresh/done 覆盖证明的 dead letter，不开放通用 SQL 或任意 queue mutation。
- `write-operation-e2e-smoke --apply-stdin` 只把两行 stdin 注入固定 relation runner：Admin Token 与 approval ticket；
  缺任一输入都在 mutation 前失败，不依赖 root-owned env 已同步才能保留审批闸门。
- write-operation runner 的 consumer 与隔离/causal 写前 baseline 共用有界 freshness 语义：只对
  `202 refreshing`、`read_model_not_fresh`、dependency `503` 轮询；业务断言、认证、合同和页面 SLO 失败仍立即
  fail closed，避免瞬态 read model 状态阻断已提交关系的 canonical recovery。
