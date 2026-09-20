# Runtime Worker 测试矩阵

## 当前不变量

- `RUNTIME_WORKER_REGISTRY` 是 registration/event/handler 的唯一清单，required instances 精确为 `oa-sync`、`workbench-matching`、`import`、`settings-maintenance`。
- PostgreSQL 是 durable item、传输和 heartbeat 的唯一运行时事实源；Worker 不依赖 RabbitMQ/Redis。
- Worker 不依赖 `Application`、Flask/session/header/HTTP response。
- App read model manifest/worker/event/dirty-scope/readiness/projection 数量为 0。
- `oa.sync(operation=refresh_attachments)` 对 completed 与 `in_progress + expense_claim` 共用既有 worker；只有 completed 子集允许 promotion/matching，进行中日常报销必须 parse-only，进行中支付申请 fail closed。
- deploy 停止并移除 registry 外旧实例，但不删除主数据库或有效业务队列。

## 七类测试

| 类别 | 适用性 | 当前入口 |
| --- | --- | --- |
| 1. 业务核心 | 间接适用 | 各 handler owner 测试保护 import/OA/matching/settings 规则。 |
| 2. Service/repository | 适用 | runtime worker/queue/settings reset tests。 |
| 3. API contract | 间接适用 | job/App Health API tests；worker 无 HTTP API。 |
| 4. Cache/background job | 核心适用 | registry、runtime queue、PostgreSQL integration、RabbitMQ/Redis removal guard tests。 |
| 5. 前端交互 | 间接适用 | App Health、job progress、导入页面 tests。 |
| 6. 端到端 | 适用 | import/OA/settings/matching E2E 与生产 closure gate。 |
| 7. 既有回归 | 核心适用 | 全量 backend/frontend/E2E、deploy/migration tests。 |

## 必须保留的负向断言

- 任意新 `*.read_model.refresh`、旧 registration/env/systemd/timer、operation barrier 或页面 refresh polling 均失败。
- 任意 RabbitMQ dispatcher/consumer/topology/env/systemd 或 Worker Redis dependency 回归均失败。
- import/OA sync 不写 full-state snapshot 或旧 page fan-out。
- OA 精确附件刷新不得为 `in_progress + expense_claim` 调用 promotion/matching 或写统一发票池；不得接纳进行中支付申请、重复/缺失 source row ID 或 scope drift，也不得执行 stale snapshot deletion。
- workbench-matching 不得恢复启动时 category snapshot + Python effective-category provider；计划银行分类必须走 fact repository 的有界 canonical projection。
- deploy 不恢复旧 schema/worker，也不删除主数据库。

## 2026-09-20 ETC 来源闭环回归

- `tests/test_etc_formal_matching.py`：来源先建组、流水顺序/歧义/差额/账户/日期、撤回保护、正式上传字段。
- `tests/test_etc_formal_matching_postgres.py`：47 张 ETC、进行中 OA、后到银行同 case、幂等、事务回滚、旧事实拒绝、提交与 dirty scopes 原子性、多批来源不覆盖。
- 既有 ETC API/删除、OA adapter、matching/UoW、Workbench query/grouping/command、成本和待付款回归；`WorkbenchColumns.test.tsx` 覆盖 paired/unpaired 两区真实进行中标签。
- 不新增 read model/cache，freshness 专属测试不适用。部署和生产证据记录在 [实施计划](../../dev/etc-oa-invoice-bank-matching-plan.md)。
