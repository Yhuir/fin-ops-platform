# Read Model E2E 覆盖

| 场景 | 状态 | 证据 | 剩余风险 |
| --- | --- | --- | --- |
| `READMODEL-E2E-001` | covered-by-modules | 各页面 direct API/API contract/frontend tests | 真实生产数据组合仍需业务模块 smoke |
| `READMODEL-E2E-002` | covered-by-modules | 各业务 mutation/refetch/committed projection tests | 跨页组合由对应业务 flow 覆盖 |
| `READMODEL-E2E-003` | covered | runtime worker/job/outbox/Workbench matching tests | RabbitMQ/systemd 真连接由 operations smoke 覆盖 |
| `READMODEL-E2E-004` | covered | `tests/test_read_model_manifest.py`、`tests/test_read_model_architecture_guards.py`、`tests/test_platform_runtime_boundary_guards.py` | 历史 docs/fixtures 仍需持续清理 |

## 快速回归

```bash
PYTHONPATH=backend/src python3 -m pytest \
  tests/test_read_model_manifest.py \
  tests/test_read_model_architecture_guards.py \
  tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_read_model_refresh_gateway_is_removed \
  tests/test_direct_api_contract_harness.py \
  -q
```
