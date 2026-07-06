# Read Models Spec-first E2E Spec

本文件定义 read model / freshness / operation barrier 的端到端验收合同。它不是页面业务口径，页面业务仍以各页面模块 `e2e-spec.md` 为准；本模块只定义所有页面共同依赖的数据最新性和 worker 收敛边界。

## 模块目标

用户在任意页面执行写操作、导入、规则保存或刷新后，页面不能把旧 projection、旧 Redis payload、缺 source/schema proof 的 SQL view 或未完成 worker 状态伪装成 fresh。只有后端 freshness/readiness/dirty/outbox 事实证明完成后，页面才能显示最终业务结果或允许关闭操作级同步状态。

## Spec IDs

| Spec ID | 用户可观察合同 | 必须证明 |
| --- | --- | --- |
| `READMODEL-E2E-001` | 页面读取 fresh read model 时显示业务数据、summary、分页、导出入口和状态提示一致。 | API payload 必须带 `read_model_status=fresh` 或等价 fresh 证明；Redis 只能缓存 fresh gate 后 payload。 |
| `READMODEL-E2E-002` | 页面遇到 missing/stale/refreshing read model 时显示同步中/诊断状态，不能显示普通空态或旧 rows。 | API 需要返回 refreshing/stale/missing reason，并通过规范 scope 入队。 |
| `READMODEL-E2E-003` | 写操作成功后，页面必须等待 operation barrier 或目标 read model fresh reload，不能只凭 POST 200 就显示已同步。 | `/api/operation-barrier/status` 或页面 fresh reload 证明 affected scopes 已 fresh。 |
| `READMODEL-E2E-004` | 导入、关联、撤回、规则保存、data reset、project scope change 等跨页写操作必须产生正确 dirty/outbox/readiness fan-out。 | durable queue 事件、dirty scopes、readiness 和页面下游 fresh 证据一致。 |
| `READMODEL-E2E-005` | 生产/staging direct read model apply gate 能把 critical scopes enqueue 到 worker 并收敛到 done/fresh。 | `read_model_slo_smoke --critical-only --apply` 通过；dry-run 只能证明 scope discovery。 |
| `READMODEL-E2E-006` | 真实业务写入口必须能被 write-operation audit 关联到 required scopes 和 SLO。 | `write_operation_slo_audit` 有非空 matching samples 且通过 operation profile；无样本是 missing，不是 covered。 |
| `READMODEL-E2E-007` | 非规范 scope、历史 failed/outbox、legacy readiness 不得污染当前 App Health。 | scope contract check 区分 covered historical failure 与 current blocker，repair 需要 audit/rollback。 |
| `READMODEL-E2E-008` | 每个当前注册页面必须声明其 read model fresh 入口、生产只读 probe、页面事实源、配对关系事实源（若页面显示配对状态）和 deterministic Browser/API 证据。 | `docs/dev/page-read-model-fact-display-matrix.json` 必须与 `web/src/app/pageRegistry.tsx`、App Status read model registry、HTTP SLO probe registry 和证据文件同步；当前页面矩阵不得再引用 legacy `no_oa_bank_batch` 页面 read model。 |
| `READMODEL-E2E-009` | 每个 write-operation SLO profile 必须声明写入事实源、配对关系事实源、durable outbox scope、目标页面/read model、生产 gate policy、1s/3s SLO 和 deterministic 证据。 | `docs/dev/write-operation-impact-matrix.json` 必须与 `write_operation_slo_audit.DEFAULT_OPERATION_EXPECTATIONS`、App Status read model registry、页面 fresh/fact-display 矩阵、standing ticket policy 和证据文件同步。 |

## 权限和角色

本模块不直接决定页面权限。权限测试必须证明被禁止角色不会触发 mutating endpoint，也不会通过 read model refresh 绕过业务权限。admin-only runtime/readiness dashboard 的 authenticated gate 归 `app-health-operations` 与 `permissions-and-audit` 共同覆盖。

## 失败与恢复场景

- Redis cache payload 缺 schema/source proof：必须 miss cache，走 SQL view 或 enqueue refresh。
- SQL view 缺 schema/source proof：必须返回 non-fresh，不写 fresh cache。
- dirty scope pending/processing/failed：页面必须显示 refreshing/blocked，不伪装 fresh。
- worker 完成后 readiness fresh：页面可重读并显示最终结果。
- write-operation audit 无样本：保持 missing，不得用 direct refresh 证据替代真实写链路证据。
- 页面新增、改名或新增 read model：必须同步更新页面 read model/fact-display 矩阵，否则不能声明页面 fresh 与事实源显示覆盖。
- 新增或修改 durable write operation：必须同步更新 write-operation impact 矩阵，否则不能声明写后跨页 read model 强可见覆盖。

## 外部风险

真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实生产数据和 mutating write scenario 不能由本地 mock Browser E2E 完全证明。它们必须进入 staging/runtime gate，并在 `e2e-coverage.md` 中标为 `external-risk` 或 `partial`。
