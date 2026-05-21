# 监控与告警

## 当前可观察对象

- `/health` 和 app health API。
- OA 同步状态。
- 工作台 dirty scopes。
- 后台任务状态。
- Runtime durable queue backlog、failed outbox event、stale read model dirty scopes。
- 成本统计缓存预热。
- Mongo 连接错误。
- 导入和重置任务失败。

## 告警建议

生产环境至少关注：

- 后端不可用。
- OA 会话接口不可用。
- App Mongo 写入失败。
- 后台任务连续失败。
- `job.outbox_events` pending 积压时间持续增长。
- `job.outbox_events` failed 数量非零且持续增加。
- `job.read_model_dirty_scopes` 长时间处于 pending、processing 或 failed。
- 数据重置任务异常结束。
- 工作台 read model 长时间无法刷新。
- API 返回 `read_model_unavailable`，表示 production PostgreSQL runtime 缺少对应 SQL read repository 或 repository 初始化失败；这不是允许回落旧 snapshot 的场景，应该检查 PostgreSQL 连接、migration 版本和 worker 配置。
- `state:full_state` 在 PostgreSQL `app.app_settings` 中持续更新。生产 API/worker 不应设置 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT=1`；若出现该 key 写入，应排查是否误用了 migration/shadow/test 配置。

## 日志要求

- 日志应包含请求路径、用户、动作、耗时和错误摘要。
- 不输出 token、密码、完整附件正文或敏感原始文件内容。
- 高风险动作需要审计日志，不只依赖应用日志。

## 收口验证报告

运行时 SQL/read-model 收敛的最终验收报告由以下命令生成：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.run_runtime_convergence_closure \
  --json \
  --require-real-infra \
  --run-unit-tests \
  --output docs/database-migration/reports/runtime-convergence-closure-require-real-infra.json
```

报告语义：

- `pass`：该项已在当前环境验证通过。
- `skip`：缺少真实环境或配置；只能用于本地开发报告，不能作为生产验收。
- `fail`：验证失败或强制真实环境下缺少依赖；必须修复后重跑。

生产 cutover 或最终下线旧 snapshot/Mongo/GridFS fallback 前，`--require-real-infra` 报告必须整体为 `pass`。该报告需要覆盖真实 PostgreSQL migration/queue integration、Redis TTL cache、MinIO/S3 checksum smoke、GridFS backfill/verify/orphan cleanup worker、OA Mongo source 只读探测与 `oa.sync` worker、worker `--check` 和 read model 查询性能探测。
