# Runtime Workers Spec-first E2E Coverage

| Spec ID | 状态 | 当前证据 | 外部缺口 |
| --- | --- | --- | --- |
| `WORKER-E2E-001` | covered | `tests/test_runtime_worker_registry.py`、deploy runtime tests、`tests/test_read_model_runtime_removal.py` | 每次生产发布复验 heartbeat。 |
| `WORKER-E2E-002` | covered | `tests/test_runtime_queue.py`、`tests/test_runtime_worker.py`、`tests/test_runtime_queue_ops.py` | 真实 dead-letter repair 需独立审批。 |
| `WORKER-E2E-003` | covered | removal guard、migration、retired event audit tests | 生产 migration 后复验 schema/event。 |
| `WORKER-E2E-004` | covered | runtime worker retry/defer/timeout/shutdown tests | 长尾延迟由生产 metrics 观察。 |
| `WORKER-E2E-005` | partial | `tests/test_rabbitmq_runtime.py`、`tests/test_rabbitmq_staging_preflight.py` | 需真实 broker。 |
| `WORKER-E2E-006` | partial | `tests/test_runtime_sync_closure_gate.py`、deploy gate tests | 需当前 release 的 T0/T+30 证据。 |
| `WORKER-E2E-007` | external-risk | `bash scripts/verify.sh infra-smoke` | 需生产/staging 环境。 |

## 验证

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_runtime_worker \
  tests.test_runtime_worker_registry \
  tests.test_runtime_queue \
  tests.test_runtime_monitoring \
  tests.test_read_model_runtime_removal -v
bash scripts/verify.sh infra-smoke
```
