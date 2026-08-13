# 部署

## 本地与服务器一致性

本地开发可以使用轻量依赖，但生产部署必须保持运行时语义一致：

- 前端 base path、后端 API prefix、OA iframe/session、Nginx 代理路径必须和服务器一致。
- PostgreSQL durable queue、read model freshness、worker registry 和 App Health 状态不能在服务器上被旁路。
- SSH tunnel 或本地代理只用于调试，不作为生产路径。
- 部署 smoke 必须验证 API 返回 JSON、页面能加载、App Health 可读、关键 read model 不被伪装为 fresh。

## 推荐路径

当前推荐 OA 同域部署：

- 前端：`/fin-ops/`
- 后端：`/fin-ops-api/`

详细步骤见 `../../deploy/oa/README.md`。

## 发布前检查

- 后端基础检查通过。
- 前端构建通过。
- PostgreSQL migration 已应用，API 使用 `FIN_OPS_APP_STORAGE_BACKEND=postgres` 与 `FIN_OPS_APP_READ_BACKEND=postgres`。
- Redis 和 MinIO/S3 按目标环境配置；Redis 不可用时 worker 仍必须能通过 PostgreSQL polling 运行。
- OA Mongo 只作为 `oa.sync` worker 的只读外部源；App Mongo 只允许迁移、shadow-read、audit 和 rollback 工具使用。
- OA 菜单和角色 SQL 已按账户类型准备。
- 有可回滚的后端、前端和配置版本。

## Release-Based 发布

生产主发布路径是服务器 release，而不是覆盖 `/opt/fin-ops/current/backend`：

```bash
./scripts/deploy-oa.sh
```

默认发布到：

```text
/opt/fin-ops/releases/<release-name>/src
```

发布脚本会生成 `src/RELEASE.json`，并通过 `finops-prod` 免密 SSH 调用服务器上的 root-owned helper：

```bash
sudo -n /usr/local/sbin/finops-deploy-control check-release <release-name>
sudo -n /usr/local/sbin/finops-deploy-control schema-compatibility-plan <release-name> --json
sudo -n /usr/local/sbin/finops-deploy-control release-gate-activate <release-name>
```

`release-gate-activate` 负责让 API、RabbitMQ worker 和 dispatcher 指向该 release。它先验证候选 migration fingerprint 与生产 applied schema；存在 pending migration 时必须先有 exact previous-code/candidate-schema 写入证据，否则在停止服务前失败。只有通过后才执行 schema migration，并调用服务器上
root-owned 的 `/usr/local/sbin/finops-ensure-runtime-workers`，幂等安装 runtime worker systemd 模板、补齐缺失的
worker env、并 `enable/restart` 最小生产正确性必须长期运行的 worker 矩阵。最后脚本会检查 live 前端 `index.html` 与 release 内
`web/dist/index.html` 的哈希一致，避免后端和前端版本漂移。

Workbench page runtime 首次由 generation read model 切换为 direct canonical API 时，激活在服务停止、
migration 和 Python env 同步完成后，先运行一次显式 typed-identity 兼容修复并立即验证第二次执行零变更，
随后在数据库默认只读事务下完整构造并关闭 candidate Application。三份 root-only evidence 均通过后才安装/
启动 candidate workers、dispatcher 和 API；普通 Application 构造保持只读，不隐式修历史数据。

`git push main` 不是部署动作。标准顺序是：本地验证、提交、推送、执行 release 发布、发布后 smoke check。默认脚本会拒绝 dirty worktree；生产发布必须能追溯到具体 commit。

生产 browser route-shell smoke 的 Playwright bundle 是独立 runner 输入，不属于 release archive。生成命令：

```bash
python3 scripts/package_production_browser_smoke.py \
  --release-name <active-release-name> \
  --output /tmp/fin-ops-production-browser-smoke.tar.gz
```

该命令只在本地生成包含批准文件和 manifest 的 tarball，不会上传、部署、安装浏览器、下载依赖、登录 OA 或执行生产浏览器测试。正常 release archive 仍只包含 backend、`web/dist`、scripts、deploy helpers 和选定根文档；不要把 `web/e2e`、`node_modules` 或浏览器二进制加入 `scripts/deploy_oa.py` 的 release 打包路径。真正执行生产 browser evidence 前，还必须有独立 runner runtime、内存 token broker、脱敏 artifact contract，以及执行前后的 `/health/ready`、dirty scope、App Status readiness、read-model outbox 和 dead-letter 聚合检查。

release 目录会占用磁盘。默认保留最近 8 个 release，同时永远保护 deploy-control status 中仍被引用的 active release。旧 root-owned 历史 release 如果当前部署用户没有权限删除，会被跳过并输出原因，需要单独做一次 root 清理。可按磁盘容量调整：

```bash
./scripts/deploy-oa.sh --keep-releases 12
```

旧 `/opt/fin-ops/current/backend` 覆盖式部署入口已经移除。生产发布只能通过
`./scripts/deploy-oa.sh` 生成 versioned release，并由 root-owned `finops-deploy-control`
完成 check-release、activate、readiness 和 cleanup。

## Worker 启动合同

生产环境按职责拆分 worker 进程，所有进程都连接同一个 PostgreSQL durable queue。不要用 API in-process thread 作为生产刷新机制。

Worker 实例、event types、env 模板和 check 命令只以 registry 为事实源：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_worker_manifest --required-instances
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_worker_manifest --json
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_worker_manifest --worker-check-command workbench-relation
```

生产 systemd 只使用 registration contract：

```bash
python -m fin_ops_platform.app.worker \
  --registration <instance> \
  --worker-instance <instance>
```

不要在本文维护第二份 worker 矩阵；新增 worker 或 read model refresh event 时先改
`backend/src/fin_ops_platform/services/runtime_worker_registry.py`，再让
`deploy/oa/bin/finops-ensure-runtime-workers.sh` 和 App Health 从 registry 收敛。

可复制的 systemd/env 模板位于：

- `deploy/oa/systemd/fin-ops.service.example`
- `deploy/oa/systemd/fin-ops-worker@.service.example`
- `deploy/oa/systemd/fin-ops-rabbitmq-topology.service.example`
- `deploy/oa/systemd/fin-ops-rabbitmq-dispatcher.service.example`
- `deploy/oa/systemd/finops-enqueue-oa-sync.service.example`
- `deploy/oa/systemd/finops-enqueue-oa-sync.timer.example`
- `deploy/oa/env/fin-ops.common.env.example`
- `deploy/oa/env/fin-ops.secrets.env.example`
- `deploy/oa/env/fin-ops.postgres-migrator.env.example`
- `deploy/oa/env/fin-ops.worker.oa-sync.env.example`
- `deploy/oa/env/fin-ops.worker.workbench-matching.env.example`
- `deploy/oa/env/fin-ops.worker.workbench-relation.env.example`
- `deploy/oa/env/fin-ops.worker.import.env.example`
- `deploy/oa/env/fin-ops.worker.settings-maintenance.env.example`
- `deploy/oa/env/fin-ops.rabbitmq-*.env.example`

systemd `.service.example` 中的 `REPLACE_WITH_RELEASE` 只用于 bootstrap 占位；标准发布通过
`./scripts/deploy-oa.sh` 调用固定 root helper 的 `release-gate-activate`，生成
`99-deploy-release.conf`，把 API、worker 和 dispatcher 指向实际
`/opt/fin-ops/releases/<release>/src`。公开 `activate` 命令已经删除。

生产 secret 只能放在 `/etc/fin-ops/*.env` 这类 root-only `EnvironmentFile` 中。`RABBITMQ_URL`、`FIN_OPS_POSTGRES_DATABASE_URL`、`FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL`、Redis、MinIO/S3、OA role sync 密码、OA payment status MySQL 密码都不能写入 systemd inline `Environment=` 或仓库文件。migrator DSN 应单独放在 `/etc/fin-ops/fin-ops.postgres-migrator.env`，仅在执行 schema migration 时手动加载，不要加入 API/worker unit。

最小生产正确性不需要 RabbitMQ，也不应依赖人工长期手动启动。普通 release 使用唯一发布入口：

```bash
./scripts/deploy-oa.sh --release-name <release-name>
```

若候选同时修改 deploy-control，必须按 `deploy/oa/README.md` 的三阶段流程执行：先
`--no-activate` 上传并校验 exact release，再以批准 SHA-256 由 root 原子 bootstrap candidate
deploy-control，最后用 `--activate-existing --release-name <exact-release>` 零重传激活。激活内部必须调用
`/usr/local/sbin/finops-ensure-runtime-workers "$RELEASE_DIR/src"`。该 helper 必须是服务器 root-owned 固定 helper，不能从 release 目录直接
`sudo /bin/bash` 执行上传脚本。仓库内的 `deploy/oa/bin/finops-ensure-runtime-workers.sh` 是 helper 源文件，历史服务器首次接入时应由 root 安装：

```bash
sudo install -m 0755 -o root -g root \
  deploy/oa/bin/finops-ensure-runtime-workers.sh \
  /usr/local/sbin/finops-ensure-runtime-workers
printf '%s\n' \
  'finops-deploy ALL=(root) NOPASSWD: /usr/local/sbin/finops-ensure-runtime-workers /opt/fin-ops/releases/*/src' |
  sudo tee /etc/sudoers.d/finops-runtime-workers >/dev/null
sudo visudo -cf /etc/sudoers.d/finops-runtime-workers
```

该 helper 只在目标 env 文件缺失时从模板创建，不覆盖已有 secret 或 worker 配置；它会安装/更新
`fin-ops-worker@.service`，并按 `runtime_worker_manifest --required-instances` 启用、重启 required worker。

如果需要手动修复一台历史服务器，可以执行等价命令：

```bash
sudo install -m 0755 -o root -g root \
  deploy/oa/bin/finops-ensure-runtime-workers.sh \
  /usr/local/sbin/finops-ensure-runtime-workers
sudo /usr/local/sbin/finops-ensure-runtime-workers "$(pwd)"
```

`--check` 应在发布前对 required worker 跑一次，确认 handler、PostgreSQL 和 Redis 状态；命令由
`runtime_worker_manifest --worker-check-command <instance>` 生成，禁止手写 `--enable-*` 组合作为生产检查入口。

## Worker 运行边界

- read model refresh worker 使用 SQL-native projection builder，不构造完整 `Application`，也不调用 `StateStore.load()`。
- `all` scope 只展开为 month/entity shard 子任务；不在单个 worker 事件中做全量同步构建。
- `job.outbox_events` 和 `job.read_model_dirty_scopes` 是权威恢复点；Redis 只用于短 TTL cache、唤醒和辅助锁。
- worker 可水平扩容；PostgreSQL claim 使用 row lock 语义，重复任务通过 dedupe key 和 scope 状态合并。
- 每个 worker 事件都必须设置 `--task-timeout-seconds` 和 `--statement-timeout-seconds`，并通过 `--lock-timeout-seconds` 释放 crash 或卡死后遗留的 `processing` 事件。
- 失败任务必须保留 `last_error` 并进入 retry 或 failed 状态，不能静默 fallback 到旧 snapshot、App Mongo 或 GridFS。

## RabbitMQ 生产切换边界

RabbitMQ 是 outbox envelope transport，不是业务事实源。生产切换必须按以下顺序：

1. 应用 PostgreSQL migration，确认 `job.outbox_events` 已有 publish 状态字段，`job.runtime_outbox_envelope_v1` 可读。
2. 用 `fin-ops-rabbitmq-topology.service` 或同等 one-shot 命令显式创建 durable topology。
3. 保持 PostgreSQL polling worker 运行，启动 `fin-ops-rabbitmq-dispatcher.service` 的 shadow publish 模式；用 `RABBITMQ_DISPATCH_EVENT_TYPES` 控制灰度事件族。
4. 观察 outbox unpublished backlog、publish failed backlog、dispatcher lag、RabbitMQ per-queue depth、DLQ count。同步 SLO 场景下
   dispatcher idle poll 默认应为 `RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS=0.5`；如果仍是 5 秒，单个新事件可能在
   投递前就消耗完整页面同步预算。
5. 只按 `runtime_worker_registry` 当前 required instance/event type 逐个切到
   `FIN_OPS_QUEUE_BACKEND=rabbitmq`；不得手写恢复已退役的 Search、no-OA 或页面 projection worker。
   RabbitMQ consumer 仍会按 heartbeat 间隔低频 drain PostgreSQL durable queue，RabbitMQ 只作为唤醒层。
6. 每切一组都要触发受控事件验证 PostgreSQL publish/ack 与 RabbitMQ queue/DLQ，再扩 worker 数量和 prefetch。

回滚路径是停止 dispatcher 和 RabbitMQ consumer worker，恢复 worker env 为 `FIN_OPS_QUEUE_BACKEND=postgres`，再启动 PostgreSQL polling worker。详细 runbook 见 `docs/operations/runtime-read-model-hardening.md`。

## 全量 Backfill / Drain

发布 PostgreSQL read model 或 OA projection 变更后，先补结构化 OA 子表，并只为
`workbench_relation` 这一个保留 read model enqueue 它自身登记的 exact scopes，再由登记 worker drain。
Workbench page、Search/no-OA projection runtime 已退役，不得重新 enqueue：

```bash
set -a
source .runtime/fin_ops_platform/local-postgres.env
set +a

/opt/miniconda3/bin/python3 scripts/backfill-runtime-read-models.py \
  --backfill-oa-children \
  --enqueue-missing \
  --json

/opt/miniconda3/bin/python3 scripts/backfill-runtime-read-models.py \
  --run-worker \
  --max-iterations 200 \
  --lock-timeout-seconds 30 \
  --task-timeout-seconds 60 \
  --statement-timeout-seconds 30 \
  --json
```

如果上一次 worker 异常退出留下 `processing` 事件，确认没有同名 worker 仍在运行后，可临时把 `--lock-timeout-seconds` 降到 `1` 重新 drain。这个操作只回收超过 lock timeout 的 PostgreSQL queue 事件，不读取旧 snapshot fallback。

## 发布后检查

- `/health`。
- `/api/session/me`。
- 只读/全操作/管理员/不可见账户分层。
- 工作台、导入、税金、成本统计、银行明细、设置页。
- App health 状态和后台任务。
- `job.outbox_events` pending/failed、`job.read_model_dirty_scopes` pending/failed/stale 数量在预期范围内。
