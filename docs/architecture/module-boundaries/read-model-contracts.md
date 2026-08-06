# Read Model 边界合同

扫描日期：2026-08-06。

本文件只记录当前运行时合同。历史 projection 设计和迁移过程不再作为架构依据；可执行事实源是：

- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 当前唯一集合

App 当前只登记两个 runtime read model：关联台页面 active-generation `workbench`，以及共享 relation distribution `workbench_relation`。

| Key / scope type | Refresh event | Worker | `all` 语义 | Query owner | Repository owner |
| --- | --- | --- | --- | --- | --- |
| `workbench` | `workbench.read_model.refresh` | `workbench` | 冷启动/显式恢复 fan-out；页面查询 `all` 由 active month shards 组合 | `WorkbenchQueryFacade` | `PostgresReadModelRepository`（active generation） |
| `workbench_relation` | `workbench_relation.read_model.refresh` | `workbench-relation` | fan-out command | `WorkbenchRelationReadFacade` | `WorkbenchRelationReadModelRepositoryPort` |

Manifest、scope policy、App Status registry 与所有带 `read_model_key` 的 worker registration 必须精确等于这个集合。每个 manifest entry 的 worker instance 必须与 runtime registry 双向相等。两种 scope 都只接受 `YYYY-MM` 或 `all`；`all` 只负责枚举月份 shard，关联台查询层可将 active month generations 组合为 `all` 视图，但 worker 不发布 materialized parent。

## 保留原因与边界

### `workbench`

- 关联台页面继续读取 PostgreSQL `read_model.workbench_*` active generations；canonical facts 与 `app.workbench_pair_relations` 只由 projection builder 在 refresh 时读取。
- 每次查询必须先通过 `WorkbenchQueryFreshnessService` 比较 canonical source proof、durable queue 状态与 active generation source versions；旧 generation 不得伪装 fresh。
- 普通 canonical writer 只推进被 Workbench source proof 消费的 `updated_at`/version 与业务审计，不投递 Workbench dirty/outbox、freshness target 或 operation barrier。公开 `/api/workbench/refresh-status` 发现 stale 时复用既有 `ReadModelRefreshGateway`，只 enqueue proof 返回的 exact month scopes；既有 PostgreSQL queue、Workbench worker 与 active-generation 原子发布链负责收敛。
- 关联台页面可见时，首次进入或重新获得 focus 立即执行一次公开 refresh-status；每次 status 完成后等待 1000ms 再调度下一次，document hidden 时暂停且全程 single-flight。只有 fresh 且 generation version 改变时进入既有 300ms combined-payload reload debounce，同一 generation 只安装一次。
- Workbench 银行分类展示复用银行明细 canonical classifier；月份 source proof 必须包含该月及 active 跨月关系银行成员的分类事实和分类确认/撤销时间，使银行明细确认后的下一次关联台访问走既有 exact-scope freshness/refresh，不恢复写后 fan-out。
- Workbench OA 输入由 completed projection 与 tenant-scoped in-progress admission 组成；月份 source proof 必须包含 `oa_pending_payment_admissions_updated_at`。历史 pending bank claim version 不再进入 proof，OA workflow 从 `in_progress` 变为 `completed` 必须使同一 case 的实际月份 generation stale，并由页面下一次 1 秒 status 检查精确收敛。
- Redis 只缓存已通过 freshness gate 的 groups payload；stale、refreshing 或 failed 时只允许按当前 active generation 的精确 payload version 只读命中，禁止写入或让 Redis 参与 freshness 判定。Workbench 若已有 active generation，可返回该稳定 generation 并显式标记 non-fresh、阻断写入；缺失 active generation 时仍 fail closed，不得用 false-empty 覆盖页面。恢复请求继续经 gateway enqueue 精确月份 scope。
- Workbench matching 是独立 canonical domain job；`workbench_relation` 是独立共享 distribution，二者都不能替代页面 active generation。
- Workbench relation grouping 在 generation payload 中发布 additive `oa_invoice_anomaly`，其 `items[]` 按日常报销子付款项或支付申请关系组表达 `oa_invoice_amount_mismatch|oa_invoice_attachment_missing`；ignore/restore 决定来自既有 exception case 表的独立 scenario，并按 exact month 加载。异常抽屉的 `active|processed` 查询只过滤当前 active generation payload，combined initial summary 以 additive `ignored_exception_count` 汇总 ignored OA/发票异常、legacy processed group 和 payload `ignored=true` 独立行；不新增 read model、scope、worker、queue 或 cache owner，异常状态和 display-only 缺失占位不能改变 generation 的 paired/unpaired、relation membership 或 canonical invoice facts。

### `workbench_relation`

- 只分发仍被独立消费者使用的 eligible active canonical relations。
- `app.workbench_pair_relations` 是事实源；read model 不是 relation 写模型。
- 查询必须通过 `WorkbenchRelationReadFacade` 与 freshness proof；调用方不得直接 SQL 读取 `read_model.workbench_relation_*`。
- `turnover_manual_closure` 等页面专属 relation mode 按各模块合同直接读取 canonical relation，不得无条件进入共享 distribution。
- 关联台页面不消费该共享 distribution；其 active relations 在 `workbench` projection refresh 时直接取自 canonical relation 表。

### 已移除的 Search 与 no-OA projection

- `/api/search`、Search service/repository/projector、refresh producer/handler、worker registrations 与 deploy env 已删除；当前页面没有 Search runtime consumer。
- `/api/no-oa-bank-batches/*` 保留业务 API，但列表由 `NoOaBankBatchApplicationService` 请求内刷新并查询 canonical `app.no_oa_bank_batches/events`；响应不含 `read_model_status`、`refresh_enqueued` 或 operation barrier target。
- `search`、`no_oa_bank_batch` 的历史 projection 表、outbox、dirty scope 和 readiness 只作上一版本回滚证据；当前 runtime 不读、不写、不 claim。

## 已退役页面 read model

除关联台外，下列页面/API 直接通过页面专属 query service，在 PostgreSQL `REPEATABLE READ READ ONLY` snapshot 中读取 canonical facts 和 active canonical relations：

| 页面 | 已退役 runtime key/链路 |
| --- | --- |
| 银行明细与账户余额 | `bank_detail`、`bank_account_balance` |
| OA 待付款核对 | `oa_pending_payment` |
| 流水规则批量处理 | `bank_flow_rule_batch` 页面 projection |
| 批量账务 | Workbench generation / relation distribution 页面读链 |
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

流水规则未提交候选不是 read model 或后台任务。页面 API 在同一只读 snapshot 中读取月份窗口内全部 canonical 银行流水、人工/确认分类事实、当前自动分类规则、paired policy 和 active relation；有效分类由与银行明细相同的 `BankTransactionEffectiveCategoryProvider` 批量计算，再交给共享 `BankBatchService` 内核实时推导。禁止仅按已持久化分类做 SQL 预筛。`app.bank_flow_rule_batches/events` 只保存正式状态和历史；旧 canonical draft event/owner/producer/worker/replay 不得恢复。

OA sync、import processing 与 Workbench matching 仍属于 canonical integration/domain jobs；它们不是页面 read model。

## Queue、freshness 与 transport

- `job.outbox_events` 与 `job.read_model_dirty_scopes` 是两个保留 read model 的唯一 refresh 状态事实源。
- 非事务 refresh 必须经 `ReadModelRefreshGateway` 和 scope policy normalize、validate、dedupe。
- 业务 service 不直接 SQL 写 dirty scope/outbox。
- Redis 只能缓存 freshness gate 已证明的 payload。
- RabbitMQ 只能作为 optional transport/wakeup；consumer 必须回 PostgreSQL claim/ack。
- 普通 canonical write 不 fan-out 页面 refresh。只有明确登记的 maintenance/reapply/repair 可以按自身事务合同入队。

## 旧链删除与回滚

- 已退役页面的 service/repository/projector/producer/worker handler、manifest/scope/App Status/RabbitMQ/deploy 注册、前端 polling/status DTO 和专属运维工具必须保持删除；关联台 active-generation runtime 是明确例外，必须完整保留。
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

- 四个可执行 registry/manifest 集合精确为 `workbench`、`workbench_relation`。
- 生产代码中不存在其它 `*.read_model.refresh` 页面事件或 retired projection SQL。
- retired worker instance/env 不在当前部署 manifest；RabbitMQ dispatcher 只发布登记事件。
- 除关联台外的目标页面及成本统计、外部往来页的 direct-read API/frontend/权限/写后 GET 回归通过；关联台 active-generation API/frontend 回归通过。
- 两个保留 read model 的 freshness、queue、worker、App Status 与 scope tests 通过。
- 全量 backend、frontend、build、Browser E2E、lint、docs 和 `git diff --check` 通过后，才允许合并和部署。
