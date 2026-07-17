# OA 待付款核对模块边界与 I/O

日期：2026-07-17

## 模块化状态

- 状态：`READY_FOR_UNIFIED_DEPLOYMENT`；本地代码、测试和文档闭环，生产回填与性能证据待统一部署后完成。
- 边界可信度：high。
- 隔离目标：只改变 `oa_pending_payment` 页面、read model、专属 worker 和 integration snapshot；不改变其它页面 API/read model。
- 旧路径状态：旧 filter endpoint/client、Python 全量 `all_rows`/filter scan、共享 invoice worker OA 分支、Mongo/MySQL projector I/O、snapshot relation fallback、本地 state-store relation snapshot、server private OA adapter fallback、sync service 多 list 扫描和无调用方 fingerprint polling 均已从运行时链路删除。

## 职责

### 本模块负责

- OA 待付款页面查询、筛选、排序、详情和 OA 专属 Audit 展示。
- `oa_pending_payment` read model、freshness gate、ETag 条件读取和 operation barrier targets。
- OA payment-status/admission integration snapshot、source watermark 和精确月份 refresh。
- in-progress pending relation、bank claim、promotion 和付款状态写回编排。

### 本模块不负责

- OA 登录、菜单权限和外部系统自身一致性。
- Workbench、银行明细、发票、input/output invoice read model 的所有权。
- 通用 worker framework、queue、operation barrier 或共享 Page Audit 默认文案。

## 输入 I/O

| 输入 | Owner | 合同 |
| --- | --- | --- |
| 页面 rows query / `If-None-Match` | OA 页面/API | 只进入 `OaPendingPaymentReadModelService.conditional_rows`；认证 tenant、query contract、fresh gate 先于 `304` |
| OA completed / in-progress / payment status | OA integration sync | 外部 adapter 每个启用 form/scope 只读一次；`all` 接收 sync owner 的 retention cutoff，并在字段校验/附件解析前排除保留期外文档，再输出双视图：通用 `projection_records` 遵守配置，OA 私有 `admission_records` 固定包含 completed + in-progress。读取失败或保留期内 status/identity 不可判定时整轮不提交并记录 failed run；合法 in-progress 草稿尚未填写 amount/applicant/reason 时仍进入 admission，空金额为 `NULL`，保留期内 completed 缺既有必填字段仍 fail-closed。成功后一次 PostgreSQL 事务提交 completed projection、admission、payment-status snapshot、watermark；相同 snapshot 不更新时间戳、不 replace admission、不 enqueue refresh。in-progress 只保留附件文件元数据，不解析附件、发票或 OCR |
| Workbench/pending relation | 对应 relation owner | read model projector 只读 PostgreSQL；owner version 和关系成员决定消费方 OA 月份 |
| 银行/进项发票 canonical facts | core/invoice owner | 通过现有 relation/source-version 合同进入月份投影；本模块不直接写其事实或 read model |
| `writeback-paid` / `link-bank-transactions` | command service | 复核权限、active relation、outflow、金额和 flow id；外部 MySQL 成功后必须幂等 reconcile PostgreSQL payment snapshot |
| refresh event | durable queue | `scope_type=oa_pending_payment`；普通业务变化只用 `YYYY-MM`，`all` 仅用于初始化、显式修复和统一部署回填 |
| Page Audit | admin-only operations API | 同一只读 repeatable-read snapshot 内分别判断 integrity、freshness 和 queue；不得写或自动修复 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| rows 聚合响应 | OA 页面 | `200` fresh payload + `ETag`；`304` 空 body；`202` 不含旧 rows且带精确 barrier targets。列表 DTO 只返回前端声明字段，不返回 read-model 内部 `searchText`、逐行 `sourceVersions` 或 cache metadata；版本证明只在顶层返回，详情继续走现有惰性 detail API。每次请求先在 OA 私有 repeatable-read snapshot 内完成 PostgreSQL freshness/version gate，`304` 在 payload I/O 前返回；非条件 fresh `200` 才以包含 tenant、normalized query、contract revision 和 version token 的 ETag 读取共享 gateway 下的 OA 私有 Redis key。cache miss 用一个有界 data statement 返回 summary/facets + 当前页并缓存 300 秒；版本变化自然换 key，Redis 不可用时退回同一 PostgreSQL statement。禁止 cache 先于 gate、显式跨页面 invalidation、第二个 page roundtrip或返回旧版本 payload |
| `filterConfig` / `filterOptions` | OA 页面 | 随 rows 同响应 set-based 计算；summary/facet CTE 只 materialize 聚合需要的 typed columns，不读取 `payload/raw_payload`；page CTE 只读取 bounded payload 并在 SQL 内移除内部字段；不存在第二个 filter API |
| read model publish | `read_model.oa_pending_payment_*` | 月份原子 replace、source vector、event source version 和 CAS；月份 rows 只能含同月 OA 主行，relation group row identity 必须含 month scope。`all` freshness gate 与 Page Audit 都把跨 scope 重复 `row_id` 作为阻断错误，列表不得用 `DISTINCT ON` 或 Python 去重隐藏错误；旧 event 不得清新 dirty |
| latest dirty index | `job.read_model_dirty_scopes` | 只索引 `scope_type='oa_pending_payment'`，键顺序与 gate 的 `(tenant, scope type, scope, source version DESC, updated_at DESC, id DESC)` 完全一致；不得扩大 predicate 让其它页面承担该索引写入或存储成本 |
| dirty/outbox | runtime queue | snapshot repository 同事务只 enqueue 精确月份 `oa_pending_payment`。admission/payment-status-only 变化不得产生 Workbench/shared dirty；completed canonical 真实新增、修改或删除由 `OAProjectionSyncService` 按 `completed_projection_changed_scopes` 交给既有 shared owner fan-out。禁止 repository 隐式拥有 Workbench fan-out 或重新合并两个变化集合 |
| write result | 前端/operation barrier | 返回受影响 scope 和 freshness targets；重复命令幂等，部分外部成功时明确可重试 |
| Audit status | OA 标题附件 | 中文状态与去重样本；内部 code 仅作次级诊断，外部 sync lag 不冒充 integrity pass |

## 事实与持久化所有权

- completed OA：`app.oa_applications`，由 OA sync owner 写。
- in-progress admission：`app.oa_pending_payment_admissions`，由 OA sync owner 权威 replace/delete。
- payment status：`app.oa_pending_payment_status_snapshots`，由 OA sync 权威 replace/delete；成功的页面写回可通过 `record_paid_statuses` 做幂等增量 reconcile。
- source watermark：`app.oa_sync_watermarks` 的 `oa_pending_payment_source:<tenant>:<month>`。
- pending relation / bank claim：`app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims` 及事件表。
- read model：OA 专属月份 rows/scopes；只由 `OaPendingPaymentSqlProjectionBuilder` 发布。
- durable refresh truth：`job.outbox_events` 与 `job.read_model_dirty_scopes`；Redis/RabbitMQ 不能替代状态事实源。Redis 只保存通过当前请求 fresh gate 后的 OA 私有版本化 rows payload，不拥有 freshness、版本或失效事实。
- `all` scope freshness inventory 只组合 canonical source watermark、现存 OA scope，以及当前 `pending/processing/failed/dead_lettered` queue scope；已 `done` 的 outbox 历史不属于当前 freshness I/O，不得进入页面热路径或改变 version token。
- `all` scope 在同一个 freshness statement 中检查跨月份 `row_id` 唯一性；发现重复必须返回 `202/refreshing` 并由 Page Audit 给出跨 scope 样本。fresh 数据直接读取月份 projection，不保留会每次排序并静默吞错的旧 `DISTINCT ON(row_id)` 兼容链。

## 动态 freshness vector

每个月份实际与期望版本至少包含：

- completed OA、in-progress admission、payment-status snapshot 的 source signature/version；
- pending relation scope version；
- Workbench relation source versions，其中已包含 relation、bank transaction、invoice 和相关 parser/schema 版本；
- OA projector/API/read-model contract revision。

输入发票 payment rules 不参与 `InvoiceLifecyclePolicy.evaluate_oa_payment`，因此不虚构 OA dependency/version。若未来业务规则真正进入 OA 付款判定，必须同时增加 owner version、writer fan-out 和测试。

## Writer inventory

| 事实变化 | 支持写入口 | OA 版本/刷新责任 |
| --- | --- | --- |
| external completed OA、admission、payment status | `OAProjectionSyncService` + `PostgresOaPendingPaymentSourceSnapshotRepository.commit_authoritative_snapshot` | 同事务 completed projection + snapshot + watermark + OA 精确月份 dirty/outbox。repository 分别返回 completed shared change 与 OA private change；service 只对 completed shared change执行既有 shared owner fan-out。外部读取失败整轮不提交并记录 failed run；`all` 同步把旧 watermark scopes 纳入 completed 删除比较 |
| 页面 MySQL paid 写回 | `OaPendingPaymentCommandService` + `record_paid_statuses` | MySQL 幂等写后，同事务更新 PG status、月份 watermark、精确月份 dirty/outbox；PG 失败返回安全重试错误 |
| in-progress pending relation create/cancel/promote | `PostgresOaPendingPaymentRelationRepository` / promotion service | 同事务增加 `oa_pending_payment_relation:<tenant>:<month>` 版本并 enqueue 消费方月份 |
| completed Workbench relation | Workbench relation owner | owner source version/dirty fan-out；OA projector读取同月 fresh Workbench relation proof |
| 银行导入/更正 | bank lifecycle/UoW owner | Workbench relation source vector包含 bank `updated_at`；有 OA consumer 的月份由既有 lifecycle fan-out |
| 进项发票导入/更正 | invoice lifecycle owner | Workbench relation source vector包含 invoice `updated_at`；有 OA consumer 的月份由既有 lifecycle fan-out |
| 显式初始化/修复 | `runtime_queue_ops enqueue-read-model-refresh --scope oa_pending_payment:all` | 低优先级 all fan-out；月份 inventory 只读取当前 tenant 的 `oa_pending_payment_source:<tenant>:<month>` watermarks，因此有事实快照但零 OA rows 的月份也必须发布 empty fresh shard；不从 completed/admission rows 猜月份，不用于普通单月写入 |

禁止直接 SQL 改 canonical facts后不更新 owner version/outbox。生产权限、boundary guard 和 Audit 共同防止越界写入。

## Worker 与依赖方向

- 专属 worker：`oa-pending-payment`，只 claim `oa_pending_payment.read_model.refresh`。
- projector 只依赖 PostgreSQL repositories；禁止 Mongo adapter、MySQL payment repository、HTTP/Application。
- `invoice-usage-collection` 只负责 input/output invoice，不注册或 claim OA refresh。
- query service 只依赖窄 read-model repository、queue、expected source-version provider 与可选 Redis helper；Redis 只经共享 `ReadModelQueryGateway` 进入 gate 后的版本化 OA 私有 payload 路径，禁止完整 live `OaPendingPaymentQueryService`、共享页面 key 或主动跨页面失效。
- route 只做认证、query/header 传递和 HTTP 映射；业务和 SQL 不进入 route。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend | `web/src/pages/OaPendingPaymentsPage.tsx`、`web/src/components/oaPendingPayments/*`、`web/src/features/oaPendingPayments/*` |
| API/query | `routes_oa_pending_payments.py`、`oa_pending_payment_query_contract.py`、`oa_pending_payment_read_model_service.py`、`oa_pending_payment_read_model_repository.py` |
| Command | `oa_pending_payment_command_service.py`、`oa_pending_payment_relation_promotion_service.py` |
| Projection/worker | `oa_pending_payment_sql_projection.py`、`oa_pending_payment_read_model_refresh.py`、`app/worker.py`、`deploy/oa/bin/finops-ensure-runtime-workers.sh` |
| Persistence | `postgres_repositories/oa_pending_payment_source_snapshot.py`、`oa_pending_payment_relation.py`、`oa_pending_payment_admission.py`、`read_models.py` |
| Audit | `postgres_repositories/page_business_audit.py`、`OaPendingPaymentAuditIcon.tsx` |

## 删除条件与禁止回流

- 旧 `/api/oa-pending-payments/filter-options` 必须保持 404/无 route；负向 contract test 和 boundary guard 可以保留该字符串。
- 禁止恢复 `all_rows()`、Python 分页全扫、live fallback、state-store/pickle snapshot 或 `_workbench_query_service._oa_adapter` 页面依赖。
- 禁止恢复 `deduped_oa_pending_payment_rows`、`DISTINCT ON(row_id)` 或其它只在 rows 响应中隐藏跨 scope 重复的兼容读取；重复身份必须在 freshness/Audit 边界 fail closed。
- 禁止普通月份同时 enqueue `oa_pending_payment:all`；all 只能由显式运维/初始化触发。
- 禁止共享 invoice worker重新注册 OA handler；release helper 必须从既有 shared worker env 精确迁移已退役的 OA flag/event，不能只更新示例文件。
- 禁止恢复 sync service 的 `list_available_months` / `list_application_records` / `list_all_application_records` 多扫描、adapter fingerprint polling、partial-result fallback 或 snapshot repository 的 Workbench fan-out。
- OA freshness hot-path 索引必须保持 event/scope 私有：dirty latest-version 只覆盖 `scope_type='oa_pending_payment'`，outbox blocking 只覆盖 OA refresh event 的 active/failed 状态；禁止用共享连接池或全 event history 索引改动掩盖页面瓶颈。
- 数据库 migration、历史实施记录和负向测试不是可执行旧链路，不删除。

## 统一部署顺序（本任务不执行）

1. 一次 release 部署 migrations、API、OA sync、专属 worker 和前端；不保留新旧读路径并行窗口。
2. 确认 `oa-pending-payment` worker 已启动且 shared invoice worker 不 claim OA event。
3. enqueue/run `oa.sync:all`，确认 run 成功并核对 `scanned_projection_count`、`scanned_completed_count`、`scanned_in_progress_count`，生成 completed/admission/payment-status canonical snapshot 和 watermarks。
4. enqueue 低优先级 `oa_pending_payment:all`，等待所有月份 dirty/outbox drain。
5. 验证 Page Audit pass、writer inventory、queue/worker health，再执行 1000 次 API 与 200 次 mutation 性能验收。
6. 未达到门槛则回滚 release/worker 配置；新 additive 表可保留，但运行时不得启用旧 live fallback。
