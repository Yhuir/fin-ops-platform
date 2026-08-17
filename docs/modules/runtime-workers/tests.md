# Runtime Worker 测试矩阵

## 当前不变量

- `RUNTIME_WORKER_REGISTRY` 是 registration/event/handler 的唯一清单，required instances 精确为 `oa-sync`、`workbench-matching`、`import`、`settings-maintenance`。
- PostgreSQL 是 durable item、传输和 heartbeat 的唯一运行时事实源；Worker 不依赖 RabbitMQ/Redis。
- Worker 不依赖 `Application`、Flask/session/header/HTTP response。
- App read model manifest/worker/event/dirty-scope/readiness/projection 数量为 0。
- deploy 停止并移除 registry 外旧实例，但不删除主数据库或有效业务队列。

## 七类测试

| 类别 | 适用性 | 当前入口 |
| --- | --- | --- |
| 1. 业务核心 | 间接适用 | 各 handler owner 测试保护 import/OA/matching/settings 规则。 |
| 2. Service/repository | 适用 | runtime worker/queue/settings reset tests。 |
| 3. API contract | 间接适用 | job/App Health API tests；worker 无 HTTP API。 |
| 4. Cache/background job | 核心适用 | registry、runtime queue、PostgreSQL integration、RabbitMQ/Redis removal guard tests。 |
| 5. 前端交互 | 间接适用 | App Health、job progress、导入页面 tests。 |
| 6. 端到端 | 适用 | import/OA/settings/matching E2E 与生产 closure gate。 |
| 7. 既有回归 | 核心适用 | 全量 backend/frontend/E2E、deploy/migration tests。 |

## 必须保留的负向断言

- 任意新 `*.read_model.refresh`、旧 registration/env/systemd/timer、operation barrier 或页面 refresh polling 均失败。
- 任意 RabbitMQ dispatcher/consumer/topology/env/systemd 或 Worker Redis dependency 回归均失败。
- import/OA sync 不写 full-state snapshot 或旧 page fan-out。
- deploy 不恢复旧 schema/worker，也不删除主数据库。
