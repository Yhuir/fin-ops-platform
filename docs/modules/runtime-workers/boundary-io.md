# Runtime Worker 模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：所有后台 worker 由 registry、durable queue、handler 和部署 manifest 显式声明。
- 当前缺口：部分 worker 同时承担多个 read model event，变更时必须同步检查 systemd/env、RabbitMQ dispatch 和 tests。
- 旧代码删除条件：旧 worker 启动方式不再被 deploy/systemd/scripts 引用。

## 职责边界

### 负责

- Runtime queue、worker registry、worker handler、worker health/readiness。
- 把 durable queue 中的 outbox/read model event 分发给对应 worker。
- 为部署和 app health 暴露 worker 实例合同。

### 不负责

- 不拥有业务源事实。
- 不直接知道 HTTP cookie/header 或 Flask response。
- 不绕过 service/repository 边界写业务表。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Outbox/job event | PostgreSQL durable queue | event type 必须在 registry 中登记 |
| Worker instance env | deploy/systemd | instance name 必须匹配 registry |
| Handler call | runtime worker | handler 只处理登记 event type |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Job result/status | runtime queue/app health | 成功、失败、重试和 readiness 可观察；影响 read model 的 job completion result summary 必须携带 target envelope 或明确不适用 |
| Read model projection | 对应 repository | 只写 worker 对应投影 |
| Wakeup/transport | RabbitMQ 可选 | 不能作为状态事实源 |

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Runtime queue | `backend/src/fin_ops_platform/services/runtime_queue.py` |
| Worker registry | `backend/src/fin_ops_platform/services/runtime_worker_registry.py` |
| Worker runtime | `backend/src/fin_ops_platform/services/runtime_worker.py`、`runtime_worker_handlers.py` |
| App worker entry | `backend/src/fin_ops_platform/app/worker.py` |
| RabbitMQ | `backend/src/fin_ops_platform/app/rabbitmq_dispatcher.py`、`rabbitmq_topology.py`、`services/rabbitmq_runtime.py` |
| Deploy | `deploy/oa/systemd/*.service.example`、`deploy/oa/env/*.env.example`、`deploy/oa/bin/finops-ensure-runtime-workers.sh` |
| Tests | `tests/test_runtime_worker*.py`、`tests/test_runtime_queue*.py`、`tests/test_rabbitmq_*.py` |

## 依赖方向

- 允许依赖：runtime queue repository、registered handlers、read model projection services。
- 必须通过：runtime worker registry。
- 禁止绕过：worker import `Application`、`app.server`、`app.auth`、HTTP response/status objects。

## 测试与验证

- `tests/test_runtime_worker_registry.py`
- `tests/test_runtime_worker.py`
- `tests/test_runtime_worker_read_model_refresh_scopes.py`
- `tests/test_runtime_queue.py`
- `tests/test_deploy_runtime_examples.py`

## 当前缺口和删除条件

- 新增 worker 必须同步 registry、manifest/systemd env、tests、docs。
- 移除 worker 前必须证明 deploy、queue event、RabbitMQ dispatch 和 app health 不再引用。
