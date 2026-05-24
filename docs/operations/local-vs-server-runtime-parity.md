# 本地与服务器运行一致性

本地开发和服务器生产可以使用同一份代码、同一个 PostgreSQL 数据库，但性能和 AppHealth 数值仍然可能不同。原因是运行拓扑不同：

- 本地：浏览器 -> Vite dev server -> 本地 Python 后端 -> SSH tunnel -> 服务器 PostgreSQL/Redis/MinIO。
- 服务器：浏览器 -> Nginx 静态前端 -> 服务器 Python 后端 -> 服务器本机 PostgreSQL/Redis/MinIO/RabbitMQ。

因此，本地适合做功能正确性、页面交互、接口契约和小规模回归检查；生产 p95/p99、RabbitMQ consumer、worker heartbeat、DLQ 和端到端导入性能必须在服务器或 staging 上验收。

## 为什么 AppHealth 数值不同

`AppHealth 运维状态`里的请求 p95/p99 来自当前 Python 进程的 rolling window，不是 PostgreSQL 里的全局历史指标。

- 本地后端重启后只统计本地进程收到的请求。
- 服务器后端只统计服务器进程收到的请求。
- 两边 sample 数量、访问顺序、缓存状态、连接池状态和网络路径都不同。

截图里本地 `GET /api/workbench/groups` 的 `连接 p95` 和 DB/SQL 时间高于服务器，符合 SSH tunnel 访问远程 PostgreSQL 的表现。即使 SQL 和数据相同，本地每个数据库 round trip 都要经过本机到服务器的网络路径，页面如果有多次 SQL 查询，就会明显放大。

## 什么才算一致

一致性不要靠肉眼判断页面相似，而要分层验证：

1. 代码一致：后端 release 指向同一批文件哈希；前端必须重新 build 并发布到 `/www/wwwroot/fin-ops/dist`。
2. migration 一致：服务器 `public.schema_migrations` 已应用到当前版本。
3. 运行配置一致：生产 API/worker/dispatcher 的 systemd drop-in 指向同一 release，关键 env 包括 `FIN_OPS_APP_STORAGE_BACKEND`、`FIN_OPS_APP_READ_BACKEND`、`FIN_OPS_QUEUE_BACKEND`、`FIN_OPS_IMPORT_PROCESSING_BACKEND`。
4. 基础设施拓扑一致：RabbitMQ topology、dispatcher allowlist、worker consumer、DLQ 和 AppHealth RabbitMQ 管理接口都可观测。
5. 性能验收在同拓扑环境做：本地 SSH tunnel 数值不能和服务器 p95/p99 直接比较。

## 推荐工作流

日常开发：

```bash
./scripts/start-backend.sh
./scripts/start-web.sh
./scripts/check-local-runtime.sh --require-backend
```

本地确认：

- 页面流程正确。
- API contract 正确。
- 导入、关联台、AppHealth 没有前端错误。
- `check-local-runtime.sh` 可以有 SSH tunnel 延迟 warning，但不能有 dependency error。

发布前：

```bash
PYTHONPATH=backend/src:tests python3 -m unittest <受影响测试> -v
cd web && npm test -- --run <受影响测试>
cd web && npm run build
git diff --check
```

服务器发布必须同时覆盖：

- 后端 release。
- 前端 build 产物 `/www/wwwroot/fin-ops/dist`。
- PostgreSQL migration。
- RabbitMQ topology。
- dispatcher allowlist。
- worker systemd 实例。
- AppHealth/RabbitMQ/worker 验证。

性能验收：

- 使用服务器或 staging 的 AppHealth p95/p99。
- 本地 AppHealth 只看是否有异常请求和功能链路，不作为生产性能结论。
- 如果要比较代码变更前后性能，必须在同一环境、同一数据、同一访问脚本、同一 warmup 策略下比较。

## 当前已知边界

- 本地 `FIN_OPS_SSH_TUNNEL_HOST` 存在时，数据库、Redis、MinIO 访问都经过 SSH tunnel。
- 本地 `FIN_OPS_DEV_ALLOW_LOCAL_SESSION=1` 会启用本地开发用户；服务器走生产鉴权。
- 本地没有配置 RabbitMQ management 时，AppHealth 中 RabbitMQ queue 指标会显示 unknown；服务器应显示真实 ready/unacked/consumer/DLQ。
