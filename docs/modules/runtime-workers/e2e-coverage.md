# Runtime Workers Spec-first E2E Coverage

## 覆盖矩阵

| Spec ID | 状态 | 当前证据 | 缺口 |
| --- | --- | --- | --- |
| `WORKER-E2E-001` | `covered` | `tests/test_runtime_worker_registry.py`、`tests/test_deploy_runtime_examples.py`、deploy worker manifest tests；生产只读巡检显示 20 个 worker running。 | GitHub/生产未来 release 仍需每次 smoke。 |
| `WORKER-E2E-002` | `covered` | `tests/test_runtime_queue.py`、`tests/test_runtime_worker.py`、`tests/test_runtime_queue_ops.py`。 | 真实 dead-letter repair 需要 operator 审批。 |
| `WORKER-E2E-003` | `covered` | `tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_runtime_worker_registry.py`、`tests/test_read_model_manifest.py`、`tests/test_read_model_architecture_guards.py`。 | 页面 read model/event/parser 不得回流；如新增真实 worker/event 必须同步 registry 和 guard tests。 |
| `WORKER-E2E-004` | `covered` | dependency-not-fresh defer、active scope dedupe、superseded event 回归测试已覆盖。 | 真实长尾 latency 仍需 runtime SLO。 |
| `WORKER-E2E-005` | `partial` | `tests/test_rabbitmq_runtime.py`、`tests/test_rabbitmq_staging_preflight.py` 覆盖 transport 合同。 | 无 `RABBITMQ_TEST_URL` 时不能证明真实 broker。 |
| `WORKER-E2E-006` | `partial` | 最近生产只读 `runtime_sync_closure_gate` 的 `runtime_health` pass，queue/DLQ/unacked 为 0；随后 current release critical direct apply full rerun 15/15 pass。 | authenticated/full closure 和 mutating scenario 未闭合。 |
| `WORKER-E2E-007` | `external-risk` | `bash scripts/verify.sh infra-smoke` 是统一入口。 | 需要 staging/production env、apply gate 和长期运行窗口。 |

## 当前验证入口

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_worker_registry tests.test_runtime_queue tests.test_runtime_monitoring -v
PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_runtime tests.test_runtime_queue_ops tests.test_runtime_state_policy tests.test_deploy_runtime_examples -v
bash scripts/verify.sh infra-smoke
```

## 下一步

1. 用真实 `RABBITMQ_TEST_URL` 执行 staging preflight。
2. 提供真实 bearer/admin token 和审批 ticket 后执行 authenticated/full closure 与受控 mutating scenario。
3. 每次新增 worker/event type 时，同步 manifest、systemd/env、tests 和本覆盖矩阵。
