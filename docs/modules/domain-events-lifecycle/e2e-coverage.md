# Domain Events Lifecycle Spec-first E2E Coverage

## 覆盖矩阵

| Spec ID | 状态 | 当前证据 | 缺口 |
| --- | --- | --- | --- |
| `DOMAIN-E2E-001` | `covered-local` | 页面组件测试证明普通写零 barrier、当前页 normal GET；`PageRouteHost.test.tsx` 证明浏览器生命周期不触发 reload。 | Candidate A 生产矩阵补 route 重进/手动刷新与另一已打开页面零 I/O。 |
| `DOMAIN-E2E-002` | `covered` | `tests/test_derived_data_lifecycle_service.py` 覆盖所有 declared events 生成 safe JSON plan。 | 新事件必须先补 characterization。 |
| `DOMAIN-E2E-003` | `covered` | `web/src/test/PageRouteHost.test.tsx` 的 lifecycle zero-reload 与旧 module/source guard。 | 无前端事件性能项。 |
| `DOMAIN-E2E-004` | `covered-local` | write-operation impact/SLO suites 与 `tests/test_read_model_architecture_guards.py` 证明 ordinary/import/OA write 零 downstream jobs；各 read-model/API/Playwright suite 证明访问时 exact-scope convergence。 | 全部真实业务写入口与逐页 p95/p99 仍依赖 Phase 27 production validation。 |
| `DOMAIN-E2E-005` | `covered` | startup stale scan 相关 backend tests 覆盖默认 disabled、opt-in scope 和 fresh skip。 | 生产启用前仍需 release smoke。 |

## 当前验证入口

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_derived_data_lifecycle_service.py tests/test_runtime_worker_read_model_refresh_scopes.py tests/test_read_model_architecture_guards.py -q
cd web && npm test -- --run PageRouteHost App
```

## 下一步

1. 新增 lifecycle event 前先证明不能由 access-time freshness 解决，再补 `DOMAIN-E2E-002` characterization 和权限/审计。
2. 把真实 write-operation 零 fan-out与逐页 access-to-fresh 结果回填到 `DOMAIN-E2E-004`。
