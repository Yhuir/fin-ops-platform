# Domain Events 与 Derived Lifecycle 测试矩阵

日期：2026-07-22

## 当前合同

- `DERIVED_DATA_EVENTS` 必须严格等于 `etc_business_batch_changed`、`settings_reset_completed`。
- 历史 ETC repair 只接受精确月份且不带 `all`。
- settings data reset 是唯一允许 `include_all=true` 的 production lifecycle 调用，必须保留 admin 权限、审计和进度语义。
- import confirm、OA sync、关系/分类/规则/Drawer 普通写零 lifecycle、零页面 dirty/outbox。
- 前端 finance domain event 只是 active/visible 页面重校验提示，不是 freshness 事实源。

## 七类测试

| 类别 | 适用性 | 当前入口 |
| --- | --- | --- |
| Business core unit | 适用 | `tests/test_derived_data_lifecycle_service.py`：仅两事件、scope 归一、protected targets、未知事件 fail fast |
| Service layer | 适用 | `tests/test_derived_data_lifecycle_service.py`、`tests/test_settings_data_reset_service.py`、ETC historical repair tests |
| API contract | 间接适用 | settings data reset 与 ETC repair owner API tests；本模块无普通业务 API |
| Read model/cache/job | 适用 | `tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_architecture_guards.py` |
| Frontend interaction | 适用 | `web/src/test/domainEvents.test.ts`、`web/src/test/useActiveFinanceDomainEvent.test.tsx` |
| E2E integration | 适用 | `web/e2e/settings-data-reset-flow.spec.ts`、受影响页面访问时收敛 specs |
| Existing regression | 适用 | import/OA/relation/category/rule zero-fan-out suites、runtime registry/env guards |

## 必须失败的回归

- 重新加入 `import_state_changed` 或 `import.fact.changed` registry/handler/env。
- 普通 writer 调 `plan_event(...)`、`include_all=true` 或 service/repository 私写 queue SQL。
- 恢复 `after_mutation` callback、Workbench scope invalidation helper 或跨页面 executor hidden side effect。
- 页面因普通写等待 operation barrier，或 hidden 页面执行 I/O。

## 验证命令

```bash
PYTHONPATH=backend/src python3 -m pytest \
  tests/test_derived_data_lifecycle_service.py \
  tests/test_runtime_worker_read_model_refresh_scopes.py \
  tests/test_read_model_architecture_guards.py \
  tests/test_runtime_worker_registry.py -q
```
