# Domain Events Lifecycle Spec-first E2E Coverage

## 覆盖矩阵

| Spec ID | 状态 | 当前证据 | 缺口 |
| --- | --- | --- | --- |
| `DOMAIN-E2E-001` | `partial` | 多个页面 fan-out Playwright specs 覆盖 relation/import/settings/no-OA/turnover 到下游页面；`web/src/test/useActiveFinanceDomainEvent.test.tsx` 覆盖 active subscription。 | 不是每个 event x 页面组合都有 Browser 覆盖。 |
| `DOMAIN-E2E-002` | `covered` | `tests/test_derived_data_lifecycle_service.py` 覆盖所有 declared events 生成 safe JSON plan。 | 新事件必须先补 characterization。 |
| `DOMAIN-E2E-003` | `covered` | `web/src/test/domainEvents.test.ts`、`web/src/test/useActiveFinanceDomainEvent.test.tsx`。 | 真实跨浏览器/iframe event 行为归 app-shell/OA smoke。 |
| `DOMAIN-E2E-004` | `partial` | `tests/test_runtime_worker_read_model_refresh_scopes.py` 和页面 fan-out Browser specs 覆盖主要链路。 | 全部真实业务写入口的 durable outbox 样本仍依赖 write-operation audit。 |
| `DOMAIN-E2E-005` | `covered` | startup stale scan 相关 backend tests 覆盖默认 disabled、opt-in scope 和 fresh skip。 | 生产启用前仍需 release smoke。 |

## 当前验证入口

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_runtime_worker_read_model_refresh_scopes -v
cd web && npm test -- --run src/test/domainEvents.test.ts src/test/useActiveFinanceDomainEvent.test.tsx
```

## 下一步

1. 新增 lifecycle event 时，先补 `DOMAIN-E2E-002` characterization，再补具体页面 fan-out Browser。
2. 把真实 write-operation audit 结果回填到 `DOMAIN-E2E-004`，避免只凭前端 event 宣称跨页同步完成。
