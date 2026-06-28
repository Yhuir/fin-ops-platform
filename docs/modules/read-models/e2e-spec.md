# Read Model E2E 规格

本模块没有用户页面。E2E 目标是证明页面级 read model 架构不再参与页面读取；业务页面 E2E 由各页面模块维护。

## 场景

| ID | 场景 | 验收 |
| --- | --- | --- |
| `READMODEL-E2E-001` | 已迁移页面首屏、筛选、分页、summary、导出入口 | 页面通过 direct API 返回业务 DTO；payload 不包含 `read_model_status`、`refresh_enqueued` 或 operation barrier target fields |
| `READMODEL-E2E-002` | 写操作后页面更新 | mutation 返回 affected ids/months、version、job 或 committed projection；前端 direct refetch 或应用 committed projection |
| `READMODEL-E2E-003` | 真实后台任务 | import/OA/file migration/settings reset/Workbench matching 通过 job/outbox/worker heartbeat/current worker facts 验证，不作为页面 freshness proof |
| `READMODEL-E2E-004` | 旧 page read-model 回归 | manifest/App Status registry 为空；`.read_model.refresh` lane、dirty/readiness runtime state 和 refresh gateway 不回流 |

## 权限

本模块不定义页面权限。权限由业务 API/session owner 覆盖；runtime/ops 工具必须走对应运维权限和审计。

## 禁止验收

- 不用 worker drain、readiness fresh、dirty scope done 证明页面可读。
- 不恢复 force refresh、scope repair、operation barrier 或 page refresh button。
- 不把 Redis/RabbitMQ/frontend domain event 当状态事实源。

## 最小验证

```bash
PYTHONPATH=backend/src python3 -m pytest \
  tests/test_read_model_manifest.py \
  tests/test_read_model_architecture_guards.py \
  tests/test_direct_api_contract_harness.py \
  -q
```
