# 已退役 Read Model 的生产证据

日期：2026-08-15

本 runbook 是旧 projection/read-model runtime 的零残留验证入口。它不再描述 refresh、freshness、operation barrier、backfill 或 projection 恢复；这些能力已经从 App 退役。

## 当前合同

- 页面、详情、汇总、筛选和导出只通过认证 HTTP API 读取 PostgreSQL canonical facts。
- App runtime 的 read model manifest、registry、gateway、repository、worker、dirty scope、Redis page cache 和 projection schema 数量均为 `0`。
- 当前 required workers 精确为 `oa-sync`、`workbench-matching`、`import`、`settings-maintenance`。其中 `workbench-matching` 是候选匹配领域任务，不是页面读取依赖。
- PostgreSQL 通用 outbox、attempt、heartbeat 与 OA integration mirror/cache 保留；它们不是 App 页面 read model。
- Migration `0149_remove_read_model_runtime.sql` forward-only 删除 `read_model` schema 和 `job.read_model_dirty_scopes`，并终止遗留 `%.read_model.refresh` 非终态事件。不得回滚到依赖这些对象的旧 release。

## 发布前验证

```bash
PYTHONPATH=backend/src python3 -m unittest -q \
  tests.test_read_model_runtime_removal \
  tests.test_retired_projection_event_audit \
  tests.test_runtime_worker_registry \
  tests.test_platform_runtime_boundary_guards \
  tests.test_runtime_sync_closure_gate \
  tests.test_http_slo_probe

bash scripts/verify.sh lint
bash scripts/verify.sh docs
```

删除面扫描必须满足：生产源码不存在旧 manifest/gateway/freshness/readiness/projection repository；前端不存在 operation-barrier client、refresh-status polling 或旧响应字段；deploy 只配置 4 个 required workers。

## 部署后只读证据

部署入口：

```bash
./scripts/deploy-oa.sh
```

发布控制器必须在 T0 与 T+30 证明：

- exact release 生效，`/health` 和 authenticated System Audit 通过；
- required workers 精确等于 4 个，未知旧 worker/env/timer 已停止并移除；
- `read_model` schema 与 `job.read_model_dirty_scopes` 不存在；
- `job.outbox_events` 中没有新 `%.read_model.refresh` event，通用 outbox/领域队列无 active blocker；
- RabbitMQ publish/consume/DLQ 与 PostgreSQL heartbeat 正常；
- 核心页面 API error count 为 `0`，每个 probe p95 `<=1000ms`、p99 `<=2000ms`。

认证性能采样：

```bash
scripts/with-production-admin-token.sh \
  env PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.http_slo_probe \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --iterations 20 \
  --warmup 2 \
  --concurrency 4 \
  --target-ms 1000 \
  --p99-target-ms 2000 \
  --json
```

只记录 endpoint、状态码、时延和压缩响应大小等 metadata；不得记录 token、cookie、DSN 或业务 payload。

## 业务链路证据

- 普通写成功后，不出现 page refresh target、freshness target 或 operation-barrier 请求。
- 写后同页和受影响其他页面通过各自 canonical GET 观察已提交事实；GET 不 enqueue、不等待 worker、不触发 RabbitMQ。
- Workbench auto-matching 可以异步完成候选生成，但页面读取和正式 relation command 不依赖该 worker 才能返回 canonical facts。
- 生产写样本只有在有批准、可逆业务样本时执行；本 runbook 不授权创建、修改或删除业务数据。

## 失败处理

- schema allowlist 检查发现未知 relation 时立即停止，不删除未知对象。
- forward-only migration 生效后不回滚旧 release；在当前 canonical 架构上向前修复。
- 任一核心 API 超过 SLO 时，先定位 SQL、索引、payload 和连接池；不得恢复 projection/cache/fallback 隐藏问题。
- 任一新 `%.read_model.refresh` event 或旧 worker 复活均视为 release blocker。

本退役任务不需要数据库备份，也不得删除主数据库。若另一个获批的数据修复任务创建 task-specific 备份，应按该任务恢复窗口和用户指令清理；灾难恢复/PITR 资产不属于临时任务备份。
