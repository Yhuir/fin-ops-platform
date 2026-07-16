# OA 待付款核对模块边界与 I/O

日期：2026-07-16

## 模块化状态

- 状态：`READY_FOR_UNIFIED_DEPLOYMENT`；本地代码、测试和文档闭环，生产回填与性能证据待统一部署后完成。
- 边界可信度：high。
- 隔离目标：只改变 `oa_pending_payment` 页面、read model、专属 worker 和 integration snapshot；不改变其它页面 API/read model。
- 旧路径状态：旧 filter endpoint/client、Python 全量 `all_rows`/filter scan、共享 invoice worker OA 分支、Mongo/MySQL projector I/O、snapshot relation fallback、本地 state-store relation snapshot、server private OA adapter fallback 均已从运行时链路删除。

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
| OA completed / in-progress / payment status | OA integration sync | 外部读取完整成功后，一次 PostgreSQL 事务提交 completed projection、admission、payment-status snapshot、watermark 和精确月份 outbox |
| Workbench/pending relation | 对应 relation owner | read model projector 只读 PostgreSQL；owner version 和关系成员决定消费方 OA 月份 |
| 银行/进项发票 canonical facts | core/invoice owner | 通过现有 relation/source-version 合同进入月份投影；本模块不直接写其事实或 read model |
| `writeback-paid` / `link-bank-transactions` | command service | 复核权限、active relation、outflow、金额和 flow id；外部 MySQL 成功后必须幂等 reconcile PostgreSQL payment snapshot |
| refresh event | durable queue | `scope_type=oa_pending_payment`；普通业务变化只用 `YYYY-MM`，`all` 仅用于初始化、显式修复和统一部署回填 |
| Page Audit | admin-only operations API | 同一只读 repeatable-read snapshot 内分别判断 integrity、freshness 和 queue；不得写或自动修复 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| rows 聚合响应 | OA 页面 | `200` fresh payload + `ETag`；`304` 空 body；`202` 不含旧 rows且带精确 barrier targets |
| `filterConfig` / `filterOptions` | OA 页面 | 随 rows 同响应 set-based 计算；不存在第二个 filter API |
| read model publish | `read_model.oa_pending_payment_*` | 月份原子 replace、source vector、event source version 和 CAS；旧 event 不得清新 dirty |
| dirty/outbox | runtime queue | canonical snapshot 同事务精确月份 enqueue；gateway normalize/validate/dedupe |
| write result | 前端/operation barrier | 返回受影响 scope 和 freshness targets；重复命令幂等，部分外部成功时明确可重试 |
| Audit status | OA 标题附件 | 中文状态与去重样本；内部 code 仅作次级诊断，外部 sync lag 不冒充 integrity pass |

## 事实与持久化所有权

- completed OA：`app.oa_applications`，由 OA sync owner 写。
- in-progress admission：`app.oa_pending_payment_admissions`，由 OA sync owner 权威 replace/delete。
- payment status：`app.oa_pending_payment_status_snapshots`，由 OA sync 权威 replace/delete；成功的页面写回可通过 `record_paid_statuses` 做幂等增量 reconcile。
- source watermark：`app.oa_sync_watermarks` 的 `oa_pending_payment_source:<tenant>:<month>`。
- pending relation / bank claim：`app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims` 及事件表。
- read model：OA 专属月份 rows/scopes；只由 `OaPendingPaymentSqlProjectionBuilder` 发布。
- durable refresh truth：`job.outbox_events` 与 `job.read_model_dirty_scopes`；Redis/RabbitMQ 不能替代状态事实源。

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
| external completed OA、admission、payment status | `OAProjectionSyncService` + `PostgresOaPendingPaymentSourceSnapshotRepository.commit_authoritative_snapshot` | 同事务 completed projection + snapshot + watermark + 精确月份 dirty/outbox；外部读取失败整轮不提交 |
| 页面 MySQL paid 写回 | `OaPendingPaymentCommandService` + `record_paid_statuses` | MySQL 幂等写后，同事务更新 PG status、月份 watermark、精确月份 dirty/outbox；PG 失败返回安全重试错误 |
| in-progress pending relation create/cancel/promote | `PostgresOaPendingPaymentRelationRepository` / promotion service | 同事务增加 `oa_pending_payment_relation:<tenant>:<month>` 版本并 enqueue 消费方月份 |
| completed Workbench relation | Workbench relation owner | owner source version/dirty fan-out；OA projector读取同月 fresh Workbench relation proof |
| 银行导入/更正 | bank lifecycle/UoW owner | Workbench relation source vector包含 bank `updated_at`；有 OA consumer 的月份由既有 lifecycle fan-out |
| 进项发票导入/更正 | invoice lifecycle owner | Workbench relation source vector包含 invoice `updated_at`；有 OA consumer 的月份由既有 lifecycle fan-out |
| 显式初始化/修复 | `runtime_queue_ops enqueue-read-model-refresh --scope oa_pending_payment:all` | 低优先级 all fan-out；不用于普通单月写入 |

禁止直接 SQL 改 canonical facts后不更新 owner version/outbox。生产权限、boundary guard 和 Audit 共同防止越界写入。

## Worker 与依赖方向

- 专属 worker：`oa-pending-payment`，只 claim `oa_pending_payment.read_model.refresh`。
- projector 只依赖 PostgreSQL repositories；禁止 Mongo adapter、MySQL payment repository、HTTP/Application。
- `invoice-usage-collection` 只负责 input/output invoice，不注册或 claim OA refresh。
- query service 只依赖窄 read-model repository、queue和 expected source-version provider；禁止完整 live `OaPendingPaymentQueryService`。
- route 只做认证、query/header 传递和 HTTP 映射；业务和 SQL 不进入 route。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend | `web/src/pages/OaPendingPaymentsPage.tsx`、`web/src/components/oaPendingPayments/*`、`web/src/features/oaPendingPayments/*` |
| API/query | `routes_oa_pending_payments.py`、`oa_pending_payment_query_contract.py`、`oa_pending_payment_read_model_service.py`、`oa_pending_payment_read_model_repository.py` |
| Command | `oa_pending_payment_command_service.py`、`oa_pending_payment_relation_promotion_service.py` |
| Projection/worker | `oa_pending_payment_sql_projection.py`、`oa_pending_payment_read_model_refresh.py`、`app/worker.py` |
| Persistence | `postgres_repositories/oa_pending_payment_source_snapshot.py`、`oa_pending_payment_relation.py`、`oa_pending_payment_admission.py`、`read_models.py` |
| Audit | `postgres_repositories/page_business_audit.py`、`OaPendingPaymentAuditIcon.tsx` |

## 删除条件与禁止回流

- 旧 `/api/oa-pending-payments/filter-options` 必须保持 404/无 route；负向 contract test 和 boundary guard 可以保留该字符串。
- 禁止恢复 `all_rows()`、Python 分页全扫、live fallback、state-store/pickle snapshot 或 `_workbench_query_service._oa_adapter` 页面依赖。
- 禁止普通月份同时 enqueue `oa_pending_payment:all`；all 只能由显式运维/初始化触发。
- 禁止共享 invoice worker重新注册 OA handler。
- 数据库 migration、历史实施记录和负向测试不是可执行旧链路，不删除。

## 统一部署顺序（本任务不执行）

1. 一次 release 部署 migrations、API、OA sync、专属 worker 和前端；不保留新旧读路径并行窗口。
2. 确认 `oa-pending-payment` worker 已启动且 shared invoice worker 不 claim OA event。
3. enqueue/run `oa.sync:all`，生成 completed/admission/payment-status canonical snapshot 和 watermarks。
4. enqueue 低优先级 `oa_pending_payment:all`，等待所有月份 dirty/outbox drain。
5. 验证 Page Audit pass、writer inventory、queue/worker health，再执行 1000 次 API 与 200 次 mutation 性能验收。
6. 未达到门槛则回滚 release/worker 配置；新 additive 表可保留，但运行时不得启用旧 live fallback。
