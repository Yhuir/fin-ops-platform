# Runtime Worker 测试矩阵

## 当前不变量

- `RUNTIME_WORKER_REGISTRY` 是 registration/event/handler/scope lane 的唯一清单。
- 带 `read_model_key` 的 registration 精确覆盖 `workbench_relation`、`search`、
  `no_oa_bank_batch`；retired page worker/event/env 不存在。
- PostgreSQL durable queue 是 job/read-model 状态事实源；RabbitMQ 只负责 wakeup。
- Worker 不依赖 `Application`、Flask/session/header/HTTP response。
- import、OA sync、Workbench matching、BankFlow canonical draft 是领域/integration job，
  不能登记为页面 read model。
- deploy 必须 stop/disable 未登记 instance，并在 retired processing work 存在时拒绝激活。

## 七类测试

| 类别 | 适用性 | 当前入口 |
| --- | --- | --- |
| 1. 业务核心 | 间接适用 | 各 handler owner 测试保护 import/OA/matching/canonical draft 业务规则 |
| 2. Service/repository | 适用 | `tests/test_runtime_worker.py`、`tests/test_runtime_queue.py`：claim、retry、defer、ack、heartbeat、timeout |
| 3. API contract | 间接适用 | job/App Status API tests 保护状态和错误 shape；worker 自身无 HTTP API |
| 4. Read model/cache/background job | 核心适用 | `tests/test_runtime_worker_registry.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_manifest.py` |
| 5. 前端交互 | 间接适用 | App Status、job progress 和导入页面 tests；worker 不拥有 UI |
| 6. 端到端 | 适用 | import/OA/settings/BankFlow E2E 与 backend integration flows |
| 7. 既有功能回归 | 核心适用 | 全量 backend/frontend/E2E，加 deploy/RabbitMQ/queue/migration tests |

## 必须保留的负向断言

- retired page `*.read_model.refresh`、scope、handler、registration、env/systemd unit 不存在。
- registry/manifest/scope/App Status 集合精确三项。
- `bank_flow_rule_batch.canonical_draft.refresh` 不进入 read-model manifest/readiness。
- RabbitMQ consumer 必须回 PostgreSQL claim；publish success 不代表 done/fresh。
- import/OA sync 不写 full-state snapshot 或 retired page fan-out。
- deploy preflight 不删除历史表/backlog，不在门禁失败时停止所有保留 worker。

## 验证

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_runtime_worker_registry \
  tests.test_runtime_worker \
  tests.test_runtime_queue \
  tests.test_runtime_worker_read_model_refresh_scopes \
  tests.test_deploy_runtime_examples -v
```

生产 systemd instance、真实 RabbitMQ wakeup、旧 processing backlog 和 worker drain 必须在
发布窗口验证；本地 fake 不能证明生产进程已收敛。
