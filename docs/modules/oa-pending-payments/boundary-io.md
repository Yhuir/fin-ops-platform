# OA 待付款核对模块边界与 I/O

日期：2026-07-27

## 模块化状态

- 状态：`DIRECT_CANONICAL_READ_IMPLEMENTED_LOCALLY`。
- 边界可信度：high。
- 页面读模型：页面专属 PostgreSQL query repository；无页面 read-model freshness/version/cache/worker 运行时依赖。
- 共享遗留：旧 `oa_pending_payment` projection/worker/registry 尚未全局删除，因为 `invoice_lifecycle` 等调用方仍存在；见“共享 HANDOFF”。

## 职责

### 本模块负责

- OA 待付款 rows、summary、statistics、facets、筛选、排序、分页和惰性详情。
- `/api/oa-pending-payments` owned endpoints 的单次鉴权、tenant 隔离和结构化 HTTP 错误。
- 页面 query service 的业务组合，以及 page-specific repository 的 canonical SQL。
- in-progress admission、pending relation、bank claim/promotion、OA paid writeback 编排。
- 写后重新 GET 和前端 loading/empty/error 状态。

### 本模块不负责

- OA identity/access-tier 的业务策略；只消费共享 auth port。
- OA Mongo/MySQL 同步、银行/发票 canonical facts、Workbench relation 的写所有权。
- Workbench、invoice lifecycle、input/output invoice read model。
- 全局 read-model manifest、worker registry/handlers、App Status registry、RabbitMQ dispatcher、deploy worker env 或 cleanup migration。

## 直接输入 I/O

| 输入 | Owner | 页面合同 |
| --- | --- | --- |
| OA session/token | permissions/auth owner | route 在任何查询/命令 I/O 前解析一次；拒绝未认证、无权限和只读写入 |
| rows query | frontend/API | `month`、keyword、trade-date range、filters、sort、page/page_size、view mode；非法参数 fail closed |
| bank candidate query | frontend/API | relation status、keyword、page/page_size、repeated oa_row_ids；全部支出流水池由 PostgreSQL 服务端分页 |
| completed OA | OA integration | `app.oa_applications` 已提交 snapshot；页面不访问 Mongo |
| in-progress admission | OA integration | `app.oa_pending_payment_admissions`，按 tenant 读取 |
| payment status | OA integration/command | `app.oa_pending_payment_status_snapshots`，按 tenant + flow ids 批量读取 |
| completed relation | Workbench relation owner | 只读 `app.workbench_pair_relations` 中 `status='active'`；不读 Workbench page payload 或 `workbench_relation` projection |
| in-progress relation/claim | OA pending relation owner | active pending relation、claim、promotion facts |
| bank facts | core/bank owner | `app.bank_transactions`，只批量读取当前页 relation members |
| input invoice facts | invoice owner | `app.invoices`，只批量读取当前页 relation members |
| write command | frontend | 保留 active relation、outflow、金额、flow id、幂等、CAS/冲突和 audit 校验 |

## 直接输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| rows response | frontend | 固定 `200` canonical JSON：rows/pagination/summary/statistics/filterConfig/filterOptions/appliedFilters/sort/viewMode |
| detail response | frontend drawer | canonical row hydrate 后复用既有 detail builder；missing=`404`、invalid=`400` |
| bank candidates | frontend drawer | canonical bank facts + active formal/pending relations；返回 relation status 与服务端 pagination |
| write result | frontend | 业务结果、affected objects/scopes、冲突/重试信息；不含 read-model refresh/barrier/version metadata |
| canonical status reconcile | PostgreSQL | 外部写回成功或 already-paid 后幂等记录 payment-status snapshot |
| pending relation/claim/promotion | PostgreSQL | 继续走现有 command/repository/UoW 与审计边界 |
| Audit UI | admin frontend | 单次读取 operations Audit；不等待 operation barrier，不参与页面正确性 |

## Snapshot 与查询责任

- `OaPendingPaymentQueryService.rows(...)` 只解析合同和组合结果。
- `PostgresOaPendingPaymentQueryRepository.snapshot()` 显式执行 `REPEATABLE READ READ ONLY`。
- 同一 rows 响应的 descriptors、pagination、summary、statistics、status counts 和 filter options 在一个 snapshot 内读取。
- selector 使用一个 set-based statement 完成过滤、排序、服务端分页与聚合；随后只为当前页批量 hydrate canonical records/relations/bank/invoices/status。
- 查询次数与 page size 无关；最大 `page_size=200`，禁止逐行/逐组查询和 Python/浏览器全量分页。
- 详情各自使用一个只读 repeatable-read snapshot，先定位 descriptor，再批量 hydrate 单一 canonical group。
- 候选抽屉用一个 set-based statement 读取全量月份的 outflow bank facts、active relation status、keyword filter、total 和当前页；不得经 command service 全量加载后 Python 分页。

## 事实与持久化所有权

- completed OA：`app.oa_applications`，OA sync owner。
- in-progress admission：`app.oa_pending_payment_admissions`，OA sync owner。
- payment status：`app.oa_pending_payment_status_snapshots`，OA sync/paid reconcile owner。
- pending relation / claim：`app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims` 及事件表。
- formal relation：`app.workbench_pair_relations`，Workbench relation owner。
- bank/input invoice：`app.bank_transactions`、`app.invoices`，对应 canonical owner。
- 旧 `read_model.oa_pending_payment_*` 不再是本页面事实源；其暂时保留不代表页面可读取或回退。

## Writer inventory

| 事实变化 | 支持入口 | 页面可见性 |
| --- | --- | --- |
| external OA/admission/payment status | OA integration authoritative snapshot | PostgreSQL commit 后下一次页面 GET 可见；请求热路径不访问外部源 |
| Workbench confirm/withdraw | Workbench UoW | active canonical relation commit 后下一次页面 GET 可见 |
| pending relation create/cancel/promote | OA pending command/repository | owner transaction commit 后下一次页面 GET 可见 |
| bank/invoice import or correction | canonical import owners | commit 后下一次页面 GET 可见 |
| MySQL paid writeback | OA command adapter + PG snapshot reconcile | command 成功后前端重新 GET；PG 失败返回可重试错误 |

任何 writer 都不能要求本页面 freshness enqueue/polling 才能达到正确结果。外部系统未同步到 PostgreSQL 属于 integration lag，不允许通过页面 fallback 绕过。

## 依赖方向

```text
route -> query service -> page PostgreSQL repository -> canonical tables
route -> command service -> existing command/adapters/repositories
frontend -> page API only
```

- route 只做 auth、参数转交、HTTP 映射。
- service 不依赖 `Application`、HTTP header/cookie 或 Flask response。
- repository 可以知道表结构和 SQL；service 不散落 SQL。
- 页面不得依赖 Redis、RabbitMQ、runtime worker、readiness、source version 或外部 OA storage。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend | `web/src/pages/OaPendingPaymentsPage.tsx`、`web/src/components/oaPendingPayments/*`、`web/src/features/oaPendingPayments/*` |
| Route/service | `routes_oa_pending_payments.py`、`oa_pending_payment_query_service.py`、`oa_pending_payment_query_contract.py` |
| Query repository | `postgres_repositories/oa_pending_payment_query.py` |
| Pure row/detail composition | `oa_pending_payment_projection_rows.py`、`oa_pending_payment_read_model_details.py` |
| Command | `oa_pending_payment_command_service.py`、`oa_pending_payment_relation_promotion_service.py` |
| Canonical snapshots | `postgres_repositories/oa_pending_payment_source_snapshot.py`、`oa_pending_payment_relation.py`、`oa_pending_payment_admission.py` |
| Tests/docs | `tests/test_oa_pending_payment_*`、`web/src/test/OaPendingPayment*`、本目录 |

## 已从页面运行时删除

- `OaPendingPaymentReadModelService` rows/detail route dependency。
- page `read_model_status` / source versions / refresh enqueue / barrier targets。
- Redis versioned rows payload。
- `If-None-Match`、ETag、`202 refreshing`、`304`。
- frontend conditional polling、visibility retry 和 Audit barrier wait。
- command response 的 `readModelRefresh` envelope。

旧共享 service/projector/worker 文件本任务不删除；这里只声明它们已退出页面调用链。

## 共享 HANDOFF

主控在所有分支合并并确认无调用方后统一处理：

- `read_model_manifest.py` 的 `oa_pending_payment` registration。
- `runtime_worker_registry.py`、`runtime_worker_handlers.py`、`read_model_scope_policy.py` 中 OA refresh 注册。
- App Status 全局 registry/Audit 中 OA legacy readiness dependency。
- deploy/systemd worker env、RabbitMQ event registration。
- `OaPendingPaymentReadModelService`、read-model repository port、SQL projection/refresh service 和 `read_model.oa_pending_payment_*` tables/indexes/migrations。
- Redis OA rows cache key/schema。
- `invoice_lifecycle` 当前对 OA read-model repository 的依赖；必须先迁移 lifecycle，禁止抢删。

## 禁止回流

- 禁止 dual read、shadow/fallback、cache 或页面访问 enqueue。
- 禁止读取 `workbench_relation` projection 代替 active canonical relation。
- 禁止从页面请求访问 OA Mongo/MySQL/对象存储。
- 禁止恢复旧 filter endpoint、全量 `all_rows()`、Python/浏览器分页。
- 禁止把共享旧 read model 仍存在解释为本页可依赖。
- 禁止本任务修改全局 cleanup migration 或共享 worker/deploy registry。
