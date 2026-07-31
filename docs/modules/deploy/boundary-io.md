# 部署模块边界与 I/O

日期：2026-07-05

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：部署模块负责发布、runtime worker/systemd/env/nginx/verify，不承载业务逻辑。
- 当前缺口：无 P0/P1 模块化缺口；新增 read model/worker 仍必须同步 deploy examples、runtime worker manifest 和生产等价发布门禁。
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
| Deploy command | `scripts/deploy-oa.sh` | 使用明确 release/remote/env；正常激活只允许调用 `finops-deploy-control release-gate-activate <release>`，公开 `activate` 入口已删除。`--no-activate` 只上传和校验，不生成门禁证据 |
| Release-gate credential | 本机 `scripts/with-production-admin-token.sh` | Admin Token 只通过部署进程 stdin 交给 root helper，不写入 release、证据、命令行或日志；缺失时必须在任何生产切换前 fail closed |
| Release-gate RabbitMQ env | `/etc/fin-ops/fin-ops.rabbitmq-topology.env`、`/etc/fin-ops/fin-ops.rabbitmq-monitoring.env` | topology apply 与 runtime health/closure 分别加载自己的 systemd 运维边界；缺失或不可读必须 fail closed，不得读取 worker consumer 凭据代替 |
| Runtime worker manifest | `runtime_worker_manifest.py` | 必须匹配 registry |
| Verify command | `scripts/verify.sh` | 按 backend/web/docs/ops 分类执行 |
| Runtime env examples | `deploy/oa/env/*.env.example` | 按 common/secrets/migrator/worker/dispatcher 拆分，禁止恢复单文件 env |
| Controlled write smoke stdin | operator | `--apply-stdin` 第一行为 Admin Token、第二行为 approval ticket；两者均必填且不落盘。scenario 只接受固定 root-owned `0600` 标准文件，或 `finops-deploy` 持有且不可 group/world write 的 `/tmp/finops-write-e2e-*.json`；可选 preview sample count 只接受 `1..20`，默认 1，且只重复只读 preview。mutation response 显式 `outbox_event_ids: []` 是普通写零 fan-out receipt，runner 不得把它误当 receipt 缺失而强制查询 disabled-by-default durable idempotency；字段缺失时才允许走 durable receipt 查询。每个 checkpoint 必须清除上一 checkpoint 的 receipt。同一受影响页面可声明最多三个明确 scope probe，用于逐一模拟用户访问该页的 active/all 等正式 scope；`bank_oa_invoice` 的 Cost probes 必须至少包含一个 `project_scope=active` 的 Workbench-dependent semantic probe，可追加 `project_scope=all` 以收敛 System Audit，但二者都不得使用 time/bank_tag 冒充 relation proof。不得以多 scope probe 投递 sibling scope 或放宽业务 fan-out。isolation 页面仍必须恰好一个 probe。consumer assertion 只接受 typed `equals` / `contains` / `excludes`；`excludes` 只能证明已登记业务根不再含显式 test-owned row/case identity，不能解除 fixture identity gate。consumer `target_ms` 同时约束单次 fresh HTTP 和该 consumer 首次访问到 fresh/业务可见的总耗时；`operation_commit_to_visible_ms` 仅保留为观察值，不得把访问前的 zero-fan-out 审计时间算入访问 SLO。任一强制门超限都必须 fail closed |
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
| Production-equivalent release evidence | `/opt/fin-ops/runtime-smoke/release-gates/<release>/evidence.json` | root-owned `0600` 原子写入，并绑定 release 名称、candidate Git commit 和 previous release。最终 PASS 必须同时证明 `unknown_worker_count=0`、`required_worker_not_ready=0`、`dirty_scope_count=0`、`pending_outbox_count=0`、`publishing_outbox_count=0`、`dead_letter_delta=0`、`queue_stable_after_300_seconds=true` |
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
| Tests | `tests/test_deploy_*.py`、`tests/test_runtime_worker_registry.py`、`tests/test_write_operation_e2e_smoke.py` |

## 依赖方向

- 允许依赖：runtime worker registry, operations docs, CI verify scripts。
- 必须通过：documented deploy scripts.
- 禁止绕过：ad hoc production edits without operations docs; scripts embedding business fixes.

## 测试与验证

- `tests/test_deploy_oa_script.py`
- `tests/test_runtime_sync_closure_gate.py`
- `tests/test_deploy_runtime_examples.py`
- `bash scripts/verify.sh docs`

## 当前缺口和删除条件

- 新增 worker/read model 是 deploy-impacting change，必须同步 examples、docs、tests。
- 禁止恢复 `--mode legacy-current`、`build_legacy_remote_deploy_script`、`create_legacy_release_archive` 或 `deploy/oa/fin_ops.env.example`。
- 禁止在 systemd examples 或发布脚本中恢复 `/opt/fin-ops/current/backend` 作为运行目录。
- `finops-deploy-control` 对 legacy current 的归档只用于 release 激活前清理历史 runtime，不得重新变成覆盖式发布入口。
- 禁止恢复公开 `activate` 命令或在上传脚本中直接切换 release。激活前必须以当前 release 完成 pre checkpoint；候选激活后必须完成 T+0、T+60s、T+300s checkpoint。任一检查或最终 evidence 合同失败都必须自动恢复 previous release，并对回滚后的 runtime 再执行完整 checkpoint。

## Production-equivalent Release Gate（2026-07-31）

- 每个 checkpoint 复用现有权威工具，而不是维护第二套 SQL、worker 清单或页面审计：`runtime_worker_manifest`/systemd exact inventory、`rabbitmq_topology --apply`、`domain_contract_audit`、`RuntimeMonitoringRepository.health_summary()`、`runtime_sync_closure_gate`、隔离 PostgreSQL 可逆写探针和只读页面 canonical audit。
- 门禁连接生产真实 PostgreSQL schema 和 RabbitMQ topology/management；RabbitMQ management 未配置、指标读取失败或 dead-letter 增量非零均 fail closed。Redis 不是本门禁事实源。
- `runtime_sync_closure_gate` 使用三个明确 profile：`preflight` 检查当前 stable runtime readiness、worker/queue/RabbitMQ 收敛、隔离事务写入能力和只读 canonical audit；`full` 在 T+0 追加 critical read-model enqueue-to-fresh、API/health/SSE；`stability` 在 T+60/T+300 重跑读侧、性能和 runtime 收敛检查。三个 profile 都不得 confirm、withdraw 或修改任何真实业务关系。critical read-model 与 HTTP 类目标分别为 5000ms 与 1000ms。页面 shell 使用公开 origin，API/SSE 使用内部服务 origin，禁止把内部 API origin 误用于页面探针。业务合同失败不能由重试或兼容 fallback 掩盖。
- 隔离写探针只在当前数据库连接的 `pg_temp` 临时表内执行 begin/insert/read/delete/rollback，验证真实 PostgreSQL 写事务、约束和回滚能力；它不接触 canonical facts、关系、read model、outbox 或 dirty scope。页面 canonical audit 只调用既有 admin audit API，不执行修复。
- 登记过的 `test_owned` 可逆业务 scenario、standing approval 和 `write-operation-e2e-smoke` 只保留为显式 operator 工具，不属于自动 release gate。release activate 不读取 scenario，不接受 approval ticket，也不自动恢复或撤回任何业务关系。
- 标准 scenario 的唯一写入口是 `finops-deploy-control write-operation-e2e-scenario-install`：输入仅接受 `/tmp/finops-write-e2e-*.json` 的 finops-deploy-owned、非链接、非 group/world-writable 文件和一个已存在 release；helper 使用该 release 的合同校验器验证后，原子安装 root-owned `0600` 文件并保留 `.previous`。输出只包含校验状态、scenario 名称/数量和内容摘要，不返回业务行内容。
- runtime health 必须在 read-model、HTTP/SSE 和隔离写探针之后采样，确保 evidence 记录的是所有门禁动作完成后的 durable queue、dirty scope、worker 与 dead-letter 收敛状态。
- pre checkpoint 在任何切换前完成。`runtime_sync_closure_gate` 允许通过既有 repository 幂等收敛一次已经 `done` 且 publish lock 为空或过期的 `publishing` 终态，但 reconciliation 必须写入 checkpoint evidence，并在同一 checkpoint 内再取得至少一个无残留、无再次 reconciliation 的干净采样才可 PASS；持续复发按 dispatcher/状态机故障 fail closed。部署 shell 不得在 gate 外隐式清理。pre 失败必须恢复 previous release 的 deploy-control/runtime-worker helper。候选激活后 T+0 运行 `full`，T+60s/T+300s 运行 `stability`；最终 evidence 要求每个 checkpoint 的 terminal publish reconciliation 已稳定、`publishing_outbox_count=0`，并证明真实 worker、queue、read model、dead-letter 与性能持续收敛。只有最终 evidence 验证成功，发布才返回成功。

## Phase 19 受控生产命令（2026-07-12）

- `read-model-refresh` 只调用 `runtime_queue_ops enqueue-read-model-refresh`，由 scope policy 和 `ReadModelRefreshGateway` 写 durable queue；必须显式 dry-run 或 execute。
- `settings-normalize` 只调用 canonical settings normalizer/repository tool。
- `import-audit-repair` 只允许写 `app.import_batch_rows`、`app.invoices`，以及显式目标的 `app.import_batches` / `app.import_files` 生命周期字段：dry-run 使用 repeatable-read read-only snapshot；execute 使用 serializable transaction、advisory lock、expected fingerprint 和 owner/precondition guard，并输出 rollback manifest。生命周期修复还必须由唯一 succeeded job、注册行计数、canonical invoice owner 与 `manual_invoice_import` source-link 闭环共同证明；被旧 preview 清空的 row link 只允许按 batch + source identity 一对一恢复，并以单条 bulk SQL 更新。helper 不接受 SQL、通配目标或任意 module 名。
- `runtime-queue-resolve-covered` 只处理已有 exact-scope fresh/done 覆盖证明的 dead letter，不开放通用 SQL 或任意 queue mutation。
- `write-operation-e2e-smoke --apply-stdin` 只把两行 stdin 注入固定 relation runner：Admin Token 与 approval ticket；
  缺任一输入都在 mutation 前失败，不依赖 root-owned env 已同步才能保留审批闸门。固定标准 scenario
  保持 root-owned `0600`；临时 scenario 保持 `/tmp` + `finops-deploy` owner 边界。
- write-operation runner 的 consumer 与隔离/causal 写前 baseline 共用有界 freshness 语义：只对
  `202 refreshing`、`read_model_not_fresh`、dependency `503` 轮询；业务断言、认证、合同和页面 SLO 失败仍立即
  fail closed，避免瞬态 read model 状态阻断已提交关系的 canonical recovery。Direct canonical API
  不返回 `read_model_status` 时按其同步响应合同验收；只有响应显式声明非 fresh、refresh 已入队或 statistics
  非 fresh 时才进入 freshness 重试，禁止把“没有 read model”误判成“read model 不新鲜”。
