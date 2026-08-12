# Read Model 边界合同

扫描日期：2026-08-13。

本文件只记录当前运行时合同。历史 projection 设计和迁移过程不再作为架构依据；可执行事实源是：

- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 当前唯一集合

App 当前只登记一个 runtime read model：共享 relation distribution `workbench_relation`。关联台页面已与其它 direct 页面一致，请求内读取 canonical facts 与 active formal relations，不属于 read-model manifest。

| Key / scope type | Refresh event | Worker | `all` 语义 | Query owner | Repository owner |
| --- | --- | --- | --- | --- | --- |
| `workbench_relation` | `workbench_relation.read_model.refresh` | `workbench-relation` | fan-out command | `WorkbenchRelationReadFacade` | `WorkbenchRelationReadModelRepositoryPort` |

Manifest、scope policy、App Status registry 与所有带 `read_model_key` 的 worker registration 必须精确等于这个集合。manifest entry 的 worker instance 必须与 runtime registry 双向相等。scope 只接受 `YYYY-MM` 或 `all`；`all` 只负责枚举月份 shard，worker 不发布 materialized parent。

## 保留原因与边界

### 关联台 direct canonical 页面

- `WorkbenchQueryFacade -> PostgresWorkbenchPageQueryRepository` 在一个短 `REPEATABLE READ READ ONLY` transaction 中直接读取 canonical OA/银行流水/发票/ETC facts 与 `app.workbench_pair_relations.status='active'`。
- GET 不读取 `read_model.workbench_*`、Redis、RabbitMQ、dirty scope、outbox、generation/source-version 或 App Status；也不 enqueue 任何 refresh。
- completed OA 与 tenant-scoped in-progress admission 在同一 set-based read boundary 合并；同一 OA 双源冲突、active relation 缺 typed canonical member、typed owner 重复或 relation member arrays 不一致时 fail closed。
- relation completion 严格复用持久化 `requires_oa/requires_invoice`、relation mode 豁免和 OA workflow；不在 GET 中重新读取当前 settings rules。incomplete formal relation 完整保留在 `unpaired`。
- 首屏、groups、filter options、exception bucket 和 detail 使用 scope-first、typed membership、exact totals、opaque keyset cursor 与 visible-page-only batch hydration。搜索不读取 raw JSON 全文或内部 id。
- API 不返回 `read_model_status/read_model_version/active_generation_id/source_versions/refresh_enqueued/job`，不提供 `/api/workbench/refresh-status`。
- 页面写门禁只保留 permission、global mutation block 和 OA sync safety。cursor 不是写 CAS；preview fingerprint、canonical/relation versions、exact-set 与 idempotency 继续在 relation UoW 内验证。
- 写成功后页面只执行一次 normal direct GET；不等待 worker，不应用 operation projection。
- Workbench matching 仍是独立 canonical domain job；`workbench_relation` 仍是独立共享 distribution。两者都不是页面 GET 的前置依赖。

### `workbench_relation`

- 只分发仍被独立消费者使用的 eligible active canonical relations。
- `app.workbench_pair_relations` 是事实源；read model 不是 relation 写模型。
- 查询必须通过 `WorkbenchRelationReadFacade` 与 freshness proof；调用方不得直接 SQL 读取 `read_model.workbench_relation_*`。
- `turnover_manual_closure` 等页面专属 relation mode 按各模块合同直接读取 canonical relation，不得无条件进入共享 distribution。
- 关联台页面不消费该共享 distribution；其每次 normal GET 都直接从 canonical relation 表读取 active relations。

### 已移除的 Search 与 no-OA projection

- `/api/search`、Search service/repository/projector、refresh producer/handler、worker registrations 与 deploy env 已删除；当前页面没有 Search runtime consumer。
- `/api/no-oa-bank-batches/*` 保留业务 API，但列表由 `NoOaBankBatchApplicationService` 请求内刷新并查询 canonical `app.no_oa_bank_batches/events`；响应不含 `read_model_status`、`refresh_enqueued` 或 operation barrier target。
- `search`、`no_oa_bank_batch` 的历史 projection 表、outbox、dirty scope 和 readiness 只作上一版本回滚证据；当前 runtime 不读、不写、不 claim。

## 已退役页面 read model

下列页面/API 直接通过页面专属 query service，在 PostgreSQL `REPEATABLE READ READ ONLY` snapshot 中读取 canonical facts 和 active canonical relations；关联台的 direct 合同见上文：

| 页面 | 已退役 runtime key/链路 |
| --- | --- |
| 银行明细与账户余额 | `bank_detail`、`bank_account_balance` |
| OA 待付款核对 | `oa_pending_payment` |
| 流水规则批量处理 | `bank_flow_rule_batch` 页面 projection |
| 批量账务 | Workbench page generation 页面读链；shared relation distribution 仍按自己的消费者合同保留 |
| ETC 票据管理 | 无独立页面 read model；不得借用 Workbench 页面 projection |
| 税金抵扣 | `tax_offset` |
| 待找发票 | `pending_invoice`、`search-pending` 页面辅助 projection |
| 进项发票使用情况 | `input_invoice_usage`、invoice lifecycle 页面链 |
| 销项发票收款情况 | `output_invoice_collection`、invoice lifecycle 页面链 |
| 外部往来款 | `turnover_ledger` |
| 成本统计 | `cost_statistics` |

这些页面的 GET 合同：

- 一个页面 query owner、一个只读 snapshot、一个页面 DTO。
- rows、summary、statistics、facets、筛选、排序和分页必须来自同一 snapshot。
- 正式配对关系只读取 `app.workbench_pair_relations.status='active'`，并按页面规则筛选 relation mode。
- 不返回页面 `read_model_status`、`source_versions`、`refresh_enqueued`、scope、job 或 operation-barrier target。
- 不因 GET enqueue，不轮询 freshness，不读取 Redis/RabbitMQ，不回退历史 projection 或进程内 snapshot。
- PostgreSQL runtime 缺少页面 canonical repository 时 fail fast，不能双读或 fallback。

页面普通写合同：

- 只提交 canonical fact/relation/state、audit、idempotency 和业务 CAS。
- 返回业务 identity、canonical version 与信息性 affected scopes；不返回已退休页面 freshness/barrier target。
- 当前页面成功后只执行一次 normal GET；不主动读取、刷新或等待其它页面。
- 两个浏览器页面之间以共同 canonical facts 达成一致，不建立跨页面同步协调器。

## Bank-flow live candidate

流水规则未提交候选不是 read model 或后台任务。页面 API 在同一只读 snapshot 中读取月份窗口内全部 canonical 银行流水、人工/确认分类事实、当前自动分类规则、paired policy 和 active relation；有效分类由与银行明细相同的 `BankTransactionEffectiveCategoryProvider` 批量计算，再交给共享 `BankBatchService` 内核实时推导。禁止仅按已持久化分类做 SQL 预筛。`app.bank_flow_rule_batches/events` 只保存正式状态和历史；旧 canonical draft event/owner/producer/worker/replay 不得恢复。标签 requirement 保存产生的 settings-maintenance job 是正式关系 metadata 的增量业务任务，不是 bank-flow 页面 projection；它只刷新实际变化关系所在的精确 `workbench_relation` scope，并按正式 matching 合同标记受影响月份。

OA sync、import processing 与 Workbench matching 仍属于 canonical integration/domain jobs；它们不是页面 read model。

## Queue、freshness 与 transport

- `job.outbox_events` 与 `job.read_model_dirty_scopes` 是唯一保留 read model 的 refresh 状态事实源。
- 非事务 refresh 必须经 `ReadModelRefreshGateway` 和 scope policy normalize、validate、dedupe。
- 业务 service 不直接 SQL 写 dirty scope/outbox。
- Redis 只能缓存仍登记 read model 的 freshness gate 已证明的 payload；Workbench 页面不使用该缓存。
- RabbitMQ 只能作为 optional transport/wakeup；consumer 必须回 PostgreSQL claim/ack。
- 普通 canonical write 不 fan-out 页面 refresh。只有明确登记的 maintenance/reapply/repair 可以按自身事务合同入队。

## 旧链删除与回滚

- 已退役页面的 service/repository/projector/producer/worker handler、manifest/scope/App Status/RabbitMQ/deploy 注册、前端 polling/status DTO 和专属运维工具必须保持删除；关联台 page active-generation runtime 不再是例外。
- `workbench.read_model.refresh`、page worker/env、generation prune timer、refresh-status、page Redis owner 和 active production rehydrate/convergence tooling 必须不存在。`read_model.workbench_*` 物理派生表与历史 migrations 暂时保留为上一 immutable release 的离线回滚材料，新 runtime 对它们必须为零 I/O。
- migration `0127_direct_canonical_page_runtime_retirement.sql` 是无数据变更的退休标记。历史 outbox、dirty scope、readiness 与 projection 表暂不 drop，保留上一版本回滚能力。
- deploy preflight 必须先停止并 disable 当前 registry 未登记的旧 worker，再确认退休 event/dirty scope 没有 `processing`。
- 历史表存在不代表可读；生产代码、测试夹具和文档不得把它们重新当作当前事实源。
- 物理 drop 必须另立可回滚 migration，并在生产确认无 reader/writer/backlog 后审批执行。

## 变更规则

- 新增 read model 必须先证明 direct canonical query 无法满足当前需求，并同时更新 manifest、scope policy、App Status、worker registry、env/deploy、API contract、tests 与本文档。
- 修改保留 read model 的 scope/projection/freshness 必须同步更新 gateway、queue、worker、repository、permission owner 和回归测试。
- 删除或改名公共符号前必须 whole-repo 扫描 API、service、repository、worker、deploy、tests 和 docs。
- 禁止通过 compatibility branch、隐藏 fallback、双读、shadow projection 或旧 DTO 延长已退役链路。

## 验收

- 四个可执行 registry/manifest 集合精确为 `workbench_relation`。
- 生产代码中不存在其它 `*.read_model.refresh` 页面事件或 retired projection SQL。
- retired worker instance/env 不在当前部署 manifest；RabbitMQ dispatcher 只发布登记事件。
- 所有 direct 页面及成本统计、外部往来页、关联台的 API/frontend/权限/写后 GET 回归通过。
- 唯一保留 read model 的 freshness、queue、worker、App Status 与 scope tests 通过；Workbench page GET 的 queue/cache/generation I/O 为零。
- 全量 backend、frontend、build、Browser E2E、lint、docs 和 `git diff --check` 通过后，才允许合并和部署。
