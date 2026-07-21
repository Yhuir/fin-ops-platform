# OA 待付款核对模块边界与 I/O

日期：2026-07-17

## 模块化状态

- 状态：`READY_FOR_UNIFIED_DEPLOYMENT`；本地代码、测试和文档闭环，生产回填与性能证据待统一部署后完成。
- 边界可信度：high。
- 隔离目标：只改变 `oa_pending_payment` 页面、read model、专属 worker 和 integration snapshot；不改变其它页面 API/read model。
- 旧路径状态：旧 filter endpoint/client、Python 全量 `all_rows`/filter scan、1,340 行 live `OaPendingPaymentQueryService`、共享 invoice worker OA 分支、Mongo/MySQL projector I/O、WorkBench read-model freshness 串行等待、snapshot relation fallback、本地 state-store relation snapshot、server private OA adapter fallback、sync service 多 list 扫描和无调用方 fingerprint polling 均已从运行时链路删除。

## 职责

### 本模块负责

- OA 待付款页面查询、筛选、排序、详情和 OA 专属 Audit 展示。
- `/api/oa-pending-payments` 下所有 read/write endpoint 的单次鉴权执行；route 只经显式 read-session/write-auth ports 调用共享 identity/policy owner，不重复经过全局前置 guard。
- `oa_pending_payment` read model、freshness gate、ETag 条件读取和 operation barrier targets。
- OA payment-status/admission integration snapshot、source watermark 和精确月份 refresh。
- in-progress pending relation、bank claim、promotion 和付款状态写回编排。

### 本模块不负责

- OA identity 解析、access-tier/菜单权限策略和外部系统自身一致性；这些仍由共享 auth owner 提供，本模块只执行端点门禁。
- Workbench、银行明细、发票、input/output invoice read model 的所有权。
- 通用 worker framework、queue、operation barrier 或共享 Page Audit 默认文案。

## 输入 I/O

| 输入 | Owner | 合同 |
| --- | --- | --- |
| OA token/session | shared auth owner | `OaPendingPaymentApiRoutes` 对每个 owned read endpoint 调用一次 read-session port、对每个 owned write endpoint 调用一次 write-auth port；缺 token、过期、无页面权限或只读用户写入必须在业务/read-model I/O 前拒绝。全局 dispatcher 不得对同一路径再解析一次相同 session |
| 页面 rows query / `If-None-Match` | OA 页面/API | 只进入 `OaPendingPaymentReadModelService.conditional_rows`；认证 tenant、query contract、fresh gate 先于 `304` |
| OA completed / in-progress / payment status | OA integration sync | 外部 adapter 每个启用 form/scope 只读一次；`all` 接收 sync owner 的 retention cutoff，并在字段校验/附件解析前排除保留期外文档，再输出双视图：通用 `projection_records` 遵守配置，OA 私有 `admission_records` 固定包含 completed + in-progress。读取失败或保留期内 status/identity 不可判定时整轮不提交并记录 failed run；合法 in-progress 草稿尚未填写 amount/applicant/reason 时仍进入 admission，空金额为 `NULL`，保留期内 completed 缺既有必填字段仍 fail-closed。成功后一次 PostgreSQL 事务提交 completed projection、admission、payment-status snapshot、watermark；相同 snapshot 不更新时间戳、不 replace admission、不 enqueue refresh。in-progress 只保留附件文件元数据，不解析附件、发票或 OCR |
| Workbench/pending relation | 对应 relation owner | projector 只读 PostgreSQL canonical relation；不读取或等待 `workbench_relation` read model。owner 写事务把受影响 OA 月份作为 `oa_pending_payment` target，pending relation owner维护自己的月份版本 |
| 银行/进项发票 canonical facts | core/invoice owner | 通过现有 relation/source-version 合同进入月份投影；本模块不直接写其事实或 read model |
| `writeback-paid` / `link-bank-transactions` | command service | 复核权限、active relation、outflow、金额和 flow id；外部 MySQL 成功后必须幂等 reconcile PostgreSQL payment snapshot |
| refresh event | durable queue | `scope_type=oa_pending_payment`；普通业务变化只用 `YYYY-MM`，`all` 仅用于初始化、显式修复和统一部署回填 |
| Page Audit | admin-only operations API | 同一只读 repeatable-read snapshot 内分别判断 integrity、freshness 和 queue；不得写或自动修复。Audit 继续要求已登记的 `invoice_lifecycle` downstream consumer 收敛，但 OA rows/query 不读取该 read model；其 pending-invoice 输入优化不得反向污染 OA 页面运行时 I/O |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| rows 聚合响应 | OA 页面 | `200` fresh payload + `ETag`；`304` 空 body；`202` 不含旧 rows且带精确 barrier targets。列表 DTO 只返回前端声明字段，不返回 read-model 内部 `searchText`、逐行 `sourceVersions` 或 cache metadata；版本证明只在顶层返回，详情继续走现有惰性 detail API。每次请求先用 OA 私有单条 PostgreSQL statement 完成 freshness/version gate，`202` 与 `304` 在 Redis/payload I/O 前返回；非条件 fresh `200` 才以包含 tenant、normalized query、contract revision 和 version token 的 ETag 读取共享 gateway 下的 OA 私有 Redis key。cache hit 不启动 read snapshot transaction；cache miss 或 Redis fallback 必须进入 repeatable-read snapshot，重新执行同一 gate并要求 `status=fresh`、`version_token` 与外层完全相同后，才用一个有界 data statement 返回 summary/facets + 当前页并缓存 300 秒。版本变化自然换 key，读中竞态 fail-closed 为 `202`。禁止 cache 先于 gate、显式跨页面 invalidation、第二个 page roundtrip或返回旧版本 payload |
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
- canonical relation schema、pending relation scope version，以及本次 `oa_pending_payment` event source version；
- OA projector/API/read-model contract revision。

输入发票 payment rules 不参与 `InvoiceLifecyclePolicy.evaluate_oa_payment`，因此不虚构 OA dependency/version。若未来业务规则真正进入 OA 付款判定，必须同时增加 owner version、writer fan-out 和测试。

## Writer inventory

| 事实变化 | 支持写入口 | OA 版本/刷新责任 |
| --- | --- | --- |
| external completed OA、admission、payment status | `OAProjectionSyncService` + `PostgresOaPendingPaymentSourceSnapshotRepository.commit_authoritative_snapshot` | 同事务 completed projection + snapshot + watermark + OA 精确月份 dirty/outbox。repository 分别返回 completed shared change 与 OA private change；service 只对 completed shared change执行既有 shared owner fan-out。外部读取失败整轮不提交并记录 failed run；`all` 同步把旧 watermark scopes 纳入 completed 删除比较 |
| 页面 MySQL paid 写回 | `OaPendingPaymentCommandService` + `record_paid_statuses` | MySQL 幂等写后，同事务更新 PG status、月份 watermark、精确月份 dirty/outbox；PG 失败返回安全重试错误 |
| in-progress pending relation create/cancel/promote | `PostgresOaPendingPaymentRelationRepository` / promotion service | 同事务增加 `oa_pending_payment_relation:<tenant>:<month>` 版本并 enqueue 消费方月份 |
| completed Workbench relation confirm/withdraw | `WorkbenchWriteUnitOfWork` | 与 canonical relation 同一事务批量 enqueue 受影响 `oa_pending_payment:<month>`；OA projector直接读取 canonical relation，不等待 `workbench_relation` read model |
| 银行导入/更正 | bank lifecycle/UoW owner | 只有影响 OA relation evidence 的事实变化才由既有 target planner enqueue 对应 OA 月份；projector按 relation member id 批量读取 canonical bank facts |
| 进项发票导入/更正 | invoice lifecycle owner | 只有影响 OA relation evidence 的事实变化才由既有 target planner enqueue 对应 OA 月份；projector按 relation member id 批量读取 canonical invoice facts |
| 显式初始化/修复 | `runtime_queue_ops enqueue-read-model-refresh --scope oa_pending_payment:all` | 低优先级 all fan-out；月份 inventory 只读取当前 tenant 的 `oa_pending_payment_source:<tenant>:<month>` watermarks，因此有事实快照但零 OA rows 的月份也必须发布 empty fresh shard；不从 completed/admission rows 猜月份，不用于普通单月写入 |

禁止直接 SQL 改 canonical facts后不更新 owner version/outbox。生产权限、boundary guard 和 Audit 共同防止越界写入。

## Worker 与依赖方向

- 专属 worker：`oa-pending-payment`，只 claim `oa_pending_payment.read_model.refresh`。
- projector 只依赖 PostgreSQL canonical repositories和 OA read-model port；禁止 Mongo adapter、MySQL payment repository、HTTP/Application或其它页面 read model。
- `invoice-usage-collection` 只负责 input/output invoice，不注册或 claim OA refresh。
- query service 只依赖窄 read-model repository、queue、expected source-version provider 与可选 Redis helper；Redis 只经共享 `ReadModelQueryGateway` 进入 gate 后的版本化 OA 私有 payload 路径，禁止完整 live `OaPendingPaymentQueryService`、共享页面 key 或主动跨页面失效。
- route 只做一次认证、query/header 传递和 HTTP 映射；业务和 SQL 不进入 route。共享 auth policy 不复制到模块，global guard 也不重复包裹本模块路径。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend | `web/src/pages/OaPendingPaymentsPage.tsx`、`web/src/components/oaPendingPayments/*`、`web/src/features/oaPendingPayments/*` |
| API/query | `routes_oa_pending_payments.py`、`oa_pending_payment_query_contract.py`、`oa_pending_payment_read_model_service.py`、`oa_pending_payment_read_model_repository.py` |
| Command | `oa_pending_payment_command_service.py`、`oa_pending_payment_relation_promotion_service.py` |
| Projection/worker | `oa_pending_payment_projection_rows.py`、`oa_pending_payment_sql_projection.py`、`oa_pending_payment_read_model_refresh.py`、`app/worker.py`、`deploy/oa/bin/finops-ensure-runtime-workers.sh` |
| Persistence | `postgres_repositories/oa_pending_payment_source_snapshot.py`、`oa_pending_payment_relation.py`、`oa_pending_payment_admission.py`、`read_models.py` |
| Audit | `postgres_repositories/page_business_audit.py`、`OaPendingPaymentAuditIcon.tsx` |

## 删除条件与禁止回流

- 旧 `/api/oa-pending-payments/filter-options` 必须保持 404/无 route；负向 contract test 和 boundary guard 可以保留该字符串。
- 禁止恢复 `all_rows()`、Python 分页全扫、live fallback、state-store/pickle snapshot 或 `_workbench_query_service._oa_adapter` 页面依赖。
- 禁止恢复已删除的 `oa_pending_payment_service.py`，或让 OA projector重新依赖 `WorkbenchRelationReadFacade` / `workbench_relation_source_versions`。
- 禁止恢复 `deduped_oa_pending_payment_rows`、`DISTINCT ON(row_id)` 或其它只在 rows 响应中隐藏跨 scope 重复的兼容读取；重复身份必须在 freshness/Audit 边界 fail closed。
- 禁止普通月份同时 enqueue `oa_pending_payment:all`；all 只能由显式运维/初始化触发。
- 禁止共享 invoice worker重新注册 OA handler；release helper 必须从既有 shared worker env 精确迁移已退役的 OA flag/event，不能只更新示例文件。
- 禁止恢复 sync service 的 `list_available_months` / `list_application_records` / `list_all_application_records` 多扫描、adapter fingerprint polling、partial-result fallback 或 snapshot repository 的 Workbench fan-out。
- 禁止恢复 `/api/oa-pending-payments*` 的 global guard + module route 双重 session 解析；新增本模块端点必须进入 `OaPendingPaymentApiRoutes.route(...)` 的 read/write auth owner，并由全端点权限回归门保护。
- OA freshness hot-path 索引必须保持 event/scope 私有：dirty latest-version 只覆盖 `scope_type='oa_pending_payment'`，outbox blocking 只覆盖 OA refresh event 的 active/failed 状态；禁止用共享连接池或全 event history 索引改动掩盖页面瓶颈。
- 数据库 migration、历史实施记录和负向测试不是可执行旧链路，不删除。

## 统一部署顺序（本任务不执行）

1. 一次 release 部署 migrations、API、OA sync、专属 worker 和前端；不保留新旧读路径并行窗口。
2. 确认 `oa-pending-payment` worker 已启动且 shared invoice worker 不 claim OA event。
3. enqueue/run `oa.sync:all`，确认 run 成功并核对 `scanned_projection_count`、`scanned_completed_count`、`scanned_in_progress_count`，生成 completed/admission/payment-status canonical snapshot 和 watermarks。
4. enqueue 低优先级 `oa_pending_payment:all`，等待所有月份 dirty/outbox drain。
5. 验证 Page Audit pass、writer inventory、queue/worker health，再执行 1000 次 API 与 200 次 mutation 性能验收。
6. 未达到门槛则回滚 release/worker 配置；新 additive 表可保留，但运行时不得启用旧 live fallback。

## 页面完整性统计合同

- `GET /api/oa-pending-payments` 的既有主响应增加 `statistics`，统计严格来自 OA 待付款页面自身投影时实际拉取的 OA、银行流水和进项发票全集，不读取统一事实源的汇总结果，也不受搜索、筛选、排序或分页影响。
- Worker 在同一次月份投影中拉取完整流水/进项库存，按稳定业务身份生成数量和 membership digest；流水 digest 同时绑定 direction，发票 digest 同时绑定 invoice type。统计与 digest 随月份分片原子发布到既有 `raw_payload.statistics` / `source_versions`，不新增表。
- API freshness 热路径只读取已发布 scope metadata、dirty/outbox 和 source version，不得重新扫描 `app.bank_transactions` / `app.invoices`。全量查询只有在所有相关分片和覆盖 digest 均存在且 scope fresh 时返回统计，否则 `statistics=null` 并沿用既有 refreshing/refresh I/O，禁止用旧统计或 live fallback 冒充 fresh。
- 跨 scope 重复 row identity 检查属于独立 Page Audit/发布质量约束，不在正常页面 freshness 请求中执行全表 `GROUP BY`；月度页面的全量标题统计只重复校验紧凑 scope 元数据和版本令牌。
- Page Audit 在独立只读查询中从 canonical facts、关系事实和投影行重算数量及 membership digest，并与已发布值比较；它只证明页面拉取和投影完整性，不把统一事实源汇总值作为页面统计输入。
