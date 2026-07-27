# 持久化与读取边界

## 当前持久化

生产主读写状态存放在 PostgreSQL：

- `app.*` 保存业务 canonical facts、active relations、设置和领域任务状态。
- `job.*` 保存后台任务、outbox 和四个保留 read model 的 dirty scope。
- `read_model.*` 只承载已登记的关联台 active-generation 与共享 read model；其它历史页面 projection 表不属于当前运行时合同。
- 原始上传文件和附件进入 MinIO/S3，PostgreSQL `app.file_objects` 只保存 verified object pointer。
- OA Mongo 是外部只读来源，只能由独立 sync worker 或明确登记的 migration/audit 工具读取；页面 API 读取 PostgreSQL OA projection。

Canonical owner、允许写入口和跨模块规则以
[`module-boundaries/canonical-facts.md`](module-boundaries/canonical-facts.md) 为准；read model 的精确清单和
退役合同以 [`module-boundaries/read-model-contracts.md`](module-boundaries/read-model-contracts.md) 为准。

生产 API 不得读取 local/full snapshot、`state:*` JSON、App Mongo snapshot、pickle、GridFS fallback 或 OA
Mongo direct adapter。迁移和回滚工具不能进入 production bootstrap。

## 页面直接读取

除关联台外，以下页面/API 每次请求都在一个 PostgreSQL `REPEATABLE READ READ ONLY` snapshot 中直接读取 canonical
facts 和 active canonical relations：

- 银行明细与账户余额
- OA 待付款核对
- 流水规则批量处理
- 批量账务
- ETC 票据管理
- 税金抵扣
- 待找发票
- 进项发票使用情况
- 销项发票收款情况
- 外部往来款
- 成本统计

每个页面只有一个 query owner 和一个页面 DTO。rows、summary、statistics、facets、筛选、排序和分页必须
来自同一 snapshot；正式配对关系只读取 `app.workbench_pair_relations.status='active'`，并按页面合同
过滤 relation mode。

直接读取页面：

- 不读取 `read_model.*`、Redis、RabbitMQ、dirty scope、outbox 或 active generation。
- 不返回 `read_model_status`、`source_versions`、`refresh_enqueued`、freshness target 或 operation barrier。
- GET 不 enqueue、不轮询 freshness，也不回退旧 projection 或进程内 snapshot。
- PostgreSQL canonical repository 缔结失败时明确报错，禁止 dual-read 或隐藏 fallback。
- 普通写只提交 owner facts、relation/state、audit、idempotency 和业务 CAS；成功后当前页面只做一次 normal GET。

导入事实同样通过 repository 按需读取。发票、银行流水、导入批次和文件列表不得在 production bootstrap
加载为全量内存 snapshot；导入文件列表只返回摘要，预览明细继续由 import session/preview 边界负责。

## 唯一保留的 read model

当前运行时只保留：

| Key | 目的 | 事实源 |
| --- | --- | --- |
| `workbench` | 关联台页面 active-generation rows/groups/group rows | PostgreSQL canonical facts 与 `app.workbench_pair_relations` |
| `workbench_relation` | 给仍登记的独立消费者分发 eligible relation context | `app.workbench_pair_relations` |
| `search` | 全局搜索索引 | PostgreSQL canonical facts |
| `no_oa_bank_batch` | legacy `/api/no-oa-bank-batches/*` 合同 | no-OA canonical batch/relation facts |

Manifest、scope policy、App Status registry 和带 `read_model_key` 的 worker registration 必须精确等于该集合。
四个 read model 都使用月份 shard；关联台查询层可组合 fresh active month generations 为 `all` 视图，
三个共享模型的 `all` 只做 fan-out command。

它们的 refresh 状态事实源是 `job.outbox_events` 和 `job.read_model_dirty_scopes`。非事务 refresh 必须经
`ReadModelRefreshGateway` normalize、validate 和 dedupe；业务 service 不得直接写 queue SQL。Redis 只能
缓存 freshness gate 已证明的 payload；RabbitMQ 只能作为 optional transport/wakeup，消费方仍需回
PostgreSQL claim/ack。

`bank_flow_rule_batch.canonical_draft.refresh`、OA sync、import processing 和 Workbench matching 是领域或
集成任务，不是页面 read model，不能登记到 read-model manifest。

## 旧链删除与回滚

- 除关联台外，已退役页面的 service、repository、projector、refresh producer、worker handler、
  registry/env、前端 polling/status DTO 和页面专属运维工具必须保持删除。
- migration `0127_direct_canonical_page_runtime_retirement.sql` 只标记运行时退休，不物理 drop 历史表；
  这是本次发布的数据库回滚保护，不代表历史表仍可读。
- deploy preflight 必须停止并 disable registry 未登记的旧 worker，并确认退休 event/dirty scope 没有
  `processing`。
- 物理 drop 必须另立可回滚 migration，并在生产确认无 reader、writer 和 backlog 后审批执行。

## 性能与验证

- 页面 query 必须有 bounded pagination、明确 statement timeout、批量 hydration 和避免 N+1 的固定查询数
  合同。
- 高流量 SQL 通过索引和生产 `EXPLAIN (ANALYZE, BUFFERS)` 验证；不要用 read model 掩盖无界查询。
- 发布前必须通过 registry 精确集合、退休事件/表访问负向扫描、四个保留 read model 的 freshness/worker
  回归、页面 API/frontend/E2E 回归、lint、docs 和 `git diff --check`。
- 当前部署入口仍是 `./scripts/deploy-oa.sh`；worker 和生产验证以
  [`../operations/runtime-worker-governance.md`](../operations/runtime-worker-governance.md) 为准。
