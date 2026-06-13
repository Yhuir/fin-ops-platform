# Runtime 同步 Stage 9 - 写操作闭环 Profile 扩展

Stage 8 只能为 `turnover_manual_closure_or_withdraw` 生成可执行 scenario；Workbench 关联撤回和免 OA 批次撤回只输出候选上下文。本阶段补齐高影响写操作的 action metadata、审计 profile 和只读 scenario 生成，让最终 closure gate 可以覆盖这些页面的真实写后同步链路。

## 本阶段目标

- 写操作入队时保留 `action_name` metadata，后续审计能区分同一事件类型下的具体动作。
- `workbench_relation_withdraw` 覆盖关联台、银行明细、关联关系、发票生命周期、待找发票、进项使用、销项回款、OA 待付款、成本统计、搜索和税金抵扣的 refresh expectation。
- `no_oa_bank_batch_withdraw` 覆盖免 OA 批次、关联台、关联关系、成本统计和搜索的 refresh expectation。
- scenario discovery 为 Workbench/no-OA 生成可执行 HTTP scenario，但全部带 `requires_manual_approval_before_apply=true`。

## 数据流

```text
业务写入
  -> WorkbenchWriteUnitOfWork / NoOaBankBatchApplicationService
  -> DerivedDataLifecycleService(action_name metadata)
  -> ReadModelRefreshGateway normalize/validate/dedupe
  -> PostgreSQL durable dirty/outbox
  -> RabbitMQ wakeup/worker
  -> readiness fresh
  -> write_operation_slo_audit 按 operation profile 验证
```

`metadata.action_name` 只用于可观测性和审计归因，不是权限、幂等或业务状态事实源。权限和审计仍由各业务 API/service 的既有边界负责。

## 第三方组件取舍

- RabbitMQ：继续保留。它只做 wakeup/transport，降低 outbox poll 等待；PostgreSQL durable queue 仍是事实源。
- Redis fresh-cache：继续只允许缓存 fresh gate 后 payload。它改善页面秒开，不替代真实 read model freshness。
- PgBouncer：保留在完整栈规划中，用于 worker 并发或连接数增长时保护 PostgreSQL；当前 2-3 人使用不是 5 秒 SLO 的首要瓶颈。
- Prometheus/Grafana：保留。需要长期看每个 read model 的 enqueue-to-fresh p95、失败率、pending age、API p95 和 RabbitMQ 状态。
- PostgreSQL 索引/分区：按基线和 `EXPLAIN` 推进。优先索引热点查询和降低 workbench 写放大；分区只在表体量、VACUUM 或历史扫描证明需要时实施。
- Kafka：当前不建议引入。现有瓶颈是 read model refresh、SQL/JSON 写入、真实登录态验收和写操作场景覆盖，不是吞吐型事件流。Kafka 会增加 broker、consumer group、offset、重放和运维复杂度，但不能替代 PostgreSQL outbox 的一致性事实源。

## 仍未闭环的条件

以下条件同时满足前，不能宣称“全 app 每个页面 5 秒内真实同步闭环完成”：

- `runtime_sync_closure_gate` 使用真实 OA/Admin token/cookie 通过 authenticated HTTP SLO。
- 业务批准生成的 Workbench/no-OA/turnover scenario 可以真实执行，且执行对象有可接受的审计和回滚策略。
- `--apply-write-scenarios` 后写操作 E2E 通过，并且 24h write operation audit 覆盖高影响 operation profile。
- `/health/ready` 中 outbox/dirty scope/RabbitMQ DLQ/required worker/current-effective blocker 均为健康状态。

## 验收命令

只读生成候选：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_scenario_discovery \
  --output /tmp/finops-write-operation-scenario-discovery-stage9-$(date +%Y%m%d%H%M%S).json \
  --scenario-output /tmp/finops-write-e2e-scenarios-stage9-$(date +%Y%m%d%H%M%S).json
```

最终闭环 gate：

```bash
export FIN_OPS_HTTP_SLO_ADMIN_TOKEN='真实管理员 Admin-Token'
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_sync_closure_gate \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --apply-read-model-smoke \
  --write-scenario /tmp/finops-write-e2e-scenarios-stage9.json \
  --apply-write-scenarios \
  --http-target-ms 1000 \
  --read-model-target-ms 5000 \
  --write-target-ms 5000 \
  --output /tmp/finops-runtime-sync-closure-gate-stage9-$(date +%Y%m%d%H%M%S).json
```

## 本地验证

```bash
python3 -m py_compile \
  backend/src/fin_ops_platform/services/read_model_refresh_gateway.py \
  backend/src/fin_ops_platform/services/workbench_uow.py \
  backend/src/fin_ops_platform/app/server.py \
  backend/src/fin_ops_platform/services/workbench_write_facade.py \
  backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py \
  backend/src/fin_ops_platform/tools/write_operation_slo_audit.py \
  backend/src/fin_ops_platform/tools/write_operation_scenario_discovery.py

PYTHONPATH=backend/src python3 -m pytest \
  tests/test_read_model_refresh_gateway.py \
  tests/test_workbench_uow_contract.py \
  tests/test_no_oa_bank_batch_application_service.py \
  tests/test_workbench_dirty_queue_wiring.py \
  tests/test_write_operation_slo_audit.py \
  tests/test_write_operation_scenario_discovery.py \
  tests/test_write_operation_e2e_smoke.py \
  tests/test_runtime_sync_closure_gate.py -q
```

结果：72 passed；语法检查通过。

## 当前结论

本阶段把“能否证明写后 5 秒真实同步”的缺口从代码/profile/scenario 生成层面补齐。它仍不是最终完成状态，因为真实生产 apply 必须依赖登录态和业务审批。若 closure gate 仍失败，应优先看失败项归属：auth、write scenario 审批、单个 read model p95、worker/DLQ、还是具体 SQL 热点；不要用假 fresh 或清理失败记录掩盖 blocker。
