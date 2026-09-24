# OA 待付款核对模块边界与 I/O

日期：2026-07-28

## 模块化状态

- 状态：`DIRECT_CANONICAL_READ_ACTIVE`。
- 边界可信度：high。
- 页面读模型：页面专属 PostgreSQL query repository；无页面 read-model freshness/version/cache/worker 运行时依赖。
- 旧链状态：`oa_pending_payment` projection/worker/registry、invoice-lifecycle 间接依赖和部署单元已删除。

## 职责

### 本模块负责

- OA 待付款 rows、summary、statistics、facets、筛选、排序、分页和惰性详情。
- `/api/oa-pending-payments` owned endpoints 的单次鉴权、tenant 隔离和结构化 HTTP 错误。
- 页面 query service 的业务组合，以及 page-specific repository 的 canonical SQL。
- in-progress admission、正式 Workbench relation 命令和 OA 支付状态自动同步结果展示。
- 已完成/进行中 OA 事实源 XLSX 导出；导出边界不消费流水、发票或关系事实。
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
| rows query | frontend/API | `month`、keyword、trade-date range、filters、sort、page/page_size、view mode；非法参数 fail closed；纯金额 keyword 在 service 边界归一为无千分位文本，selector 搜索 OA、流水、已付和发票 canonical 金额。 |
| export query | frontend/API | `sources=completed,in_progress`，允许部分选择且至少一种；不接收或继承 rows 的 month/keyword/filter/sort/page 参数。 |
| bank candidate query | frontend/API | relation status、keyword、page/page_size、repeated oa_row_ids；全部支出流水池由 PostgreSQL 服务端分页 |
| completed OA | OA integration | `app.oa_applications` 已提交 snapshot；页面不访问 Mongo |
| in-progress admission | OA integration | `app.oa_pending_payment_admissions`，按 tenant 读取 |
| payment status | OA integration/oa-sync worker | `app.oa_pending_payment_status_snapshots`，按 tenant + flow ids 批量读取 |
| completed relation | Workbench relation owner | 只读 `app.workbench_pair_relations` 中全部 `status='active'`；混合收支关系只把可解析 outflow 作为支付证据，不读 Workbench page payload 或 `workbench_relation` projection |
| in-progress relation | Workbench relation owner | 与 completed OA 共用 `app.workbench_pair_relations.status='active'`；workflow status 只决定关联台 zone，不产生第二套 relation owner |
| bank facts | core/bank owner | `app.bank_transaction_units`，只批量读取当前页 relation members；拆分子项以自己的 ID/金额参与支付关联 |
| input invoice facts | invoice owner | `app.invoices`，只批量读取当前页 relation members |
| relation write command | frontend | 只创建/扩展 active relation；保留 outflow、幂等、CAS/冲突和 audit 校验，不直接写 OA 支付状态 |

## 直接输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| rows response | frontend | 固定 `200` canonical JSON：rows/pagination/summary/statistics/filterConfig/filterOptions/appliedFilters/sort/viewMode |

`statistics` 只包含已完成 OA、进行中 OA 和 canonical 进项发票数量；同 ID 同时出现时已完成优先，旧付款、流水和关系数量字段已删除。
| OA facts export | frontend download | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`；sheet 为 `已完成OA` / `进行中OA`；只含登记的 OA 字段，20,000 行上限，`Cache-Control: no-store`。 |
| export audit | `audit.events` | action=`oa_pending_payment_source_export_downloaded`，以 `operation.completed/success` 终态记录；只记录 actor、来源、各来源数量、总行数和文件名，不记录 OA 业务内容。 |
| detail response | frontend drawer | canonical row hydrate 后复用既有 detail builder；missing=`404`、invalid=`400` |
| bank candidates | frontend drawer | canonical bank facts + active formal relations；返回 relation status 与服务端 pagination |
| write result | frontend | 业务结果、affected objects/scopes、冲突/重试信息；不含 read-model refresh/barrier/version metadata |
| payment reconcile event | `job.outbox_events` / `oa-sync` worker | relation writer 同事务登记 `oa.payment_status.reconcile`；worker 按最新 active OA+outflow topology 幂等写外部状态与 PostgreSQL snapshot。完整 OA 权威快照以 retention 前的 current canonical OA 支付身份集合（Mongo document ID + `flowRequestId/processId`）比较完整 MySQL status 集合；确认 source flow 消失时，同事务删除 PG snapshot 并登记 `remove_missing_oa_statuses`。worker 在外部删除前以候选确定性身份定位 OA raw document，再按业务编号重读并执行 lifecycle arbitration，只把仍属于 current canonical OA 的候选视为重现，同时合并 completed + admitted canonical flow 后批量删除 MySQL 状态；source read 失败不删除。 |
| formal relation mutation | PostgreSQL | 只调用 `WorkbenchRelationCommandService`；扩展唯一 active case 时保留原 case 和发票成员，冲突或多个 owner fail closed |
| matching dirty scopes | `job.workbench_matching_dirty_scopes` | admission 或 completed OA canonical snapshot 发生匹配相关变化时，在同一业务事务中标记实际月份及前后各两个月；仅 payment-status 变化不触发匹配。 |
| Audit UI | admin frontend | 单次读取 operations Audit；不等待 operation barrier，不参与页面正确性 |
| table frame | frontend | 与进项发票使用情况、销项发票收款情况、待找发票共用 `finance-page-table-frame` 有界高度和 contained 内部滚动；本页工具栏仍占用 frame 的独立首行 |

## Snapshot 与查询责任

- `OaPendingPaymentQueryService.rows(...)` 只解析合同和组合结果。
- `PostgresOaPendingPaymentQueryRepository.snapshot()` 显式执行 `REPEATABLE READ READ ONLY`。
- 同一 rows 响应的 descriptors、pagination、summary、statistics、status counts 和 filter options 在一个 snapshot 内读取。
- selector 使用一个 set-based statement 完成过滤、排序、服务端分页与聚合；随后只为当前页批量 hydrate canonical records/relations/bank/invoices/status。
- selector 与 hydrate 都不得按 relation mode 丢弃 active relation；支付状态和展示只消费成功解析的 outflow bank facts。
- 查询次数与 page size 无关；最大 `page_size=200`，禁止逐行/逐组查询和 Python/浏览器全量分页。
- 详情各自使用一个只读 repeatable-read snapshot，先定位 descriptor，再批量 hydrate 单一 canonical group。
- 候选抽屉用一个 set-based statement 读取全量月份的 outflow bank facts、active relation status、keyword filter、total 和当前页；不得经 command service 全量加载后 Python 分页。
- 导出在一个只读 repeatable-read snapshot 内执行一条 `UNION ALL` 查询并按来源稳定排序；XLSX 使用 write-only workbook，禁止逐行 SQL、页面 rows 复用、read model 或全量关系 hydrate。

## 事实与持久化所有权

- completed OA：`app.oa_applications`，OA sync owner。
- in-progress admission：`app.oa_pending_payment_admissions`，OA sync owner。
- payment status：`app.oa_pending_payment_status_snapshots`，OA sync/payment reconcile owner；支付状态只由最新 active OA+outflow topology 收敛，不持久化写回归属门禁。支付状态从属于 OA 源生命周期：只有完整 `all` 同步能以 retention 前的 source flow ID 集合声明 flow 已删除；month sync、精确附件刷新和 retention 裁剪都无权删除外部状态。
- formal relation：`app.workbench_pair_relations`，Workbench relation owner；completed 与 in-progress 共用同一事实源。
- 历史 pending relation / claim：`app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims` 及事件表只读审计；migration `0136` 已迁移 active 关系并撤销运行时写权限。
- bank/input invoice：`app.bank_transactions`、`app.invoices`，对应 canonical owner。
- 旧 `read_model.oa_pending_payment_*` runtime 已删除；历史 migration/表只供上一版本回滚。

## Writer inventory

| 事实变化 | 支持入口 | 页面可见性 |
| --- | --- | --- |
| external OA/admission/payment status | OA integration authoritative snapshot | PostgreSQL commit 后下一次页面 GET 可见；admission/completed OA 变化在同一事务标记 matching dirty scopes，payment-status-only 更新不标记；请求热路径不访问外部源 |
| Workbench confirm/withdraw | Workbench UoW | active canonical relation commit 后下一次页面 GET 可见 |
| in-progress OA relation create/extend | OA pending command -> Workbench relation UoW | formal owner transaction commit 后下一次页面 GET 可见；无 promotion 阶段 |
| admission terminal cleanup | OA source snapshot -> Workbench relation command | OA 不再属于 completed 或 admitted 时，从 active case 移除该 OA；剩余成员仍构成有效组则保留原 case，否则取消 relation |
| authoritative OA deletion | OA source snapshot -> `oa.payment_status.reconcile` -> MySQL adapter | 完整 `all` 扫描把生命周期去重后的 current canonical OA 支付身份集合与完整 MySQL status flow 集合比较；真实消失 flow 的 PG 状态和关系在 snapshot 事务内清理，外部 MySQL 状态由 durable event 幂等批量删除。执行前按候选 Mongo document ID 或 `flowRequestId/processId` 定位两个配置表单内的文档，并按业务编号重读同组流程、复用 lifecycle arbitration，再合并 canonical OA；只有候选仍属于 current canonical OA 才不删除，历史 raw document 被取代时不能阻止删除，源读取失败不执行删除，仅超出 App retention 且仍是 current canonical 的 flow 保留外部状态。 |
| bank/invoice import or correction | canonical import owners | commit 后下一次页面 GET 可见 |
| active relation topology change | Workbench relation repository -> `oa.payment_status.reconcile` -> oa-sync worker | writer 对本次变更 case 批量读取变更前 relation；事件中的 typed OA ID 取变更前后成员并集，确保撤回后已脱离 case 的 OA 仍进入 reconcile。有 active outflow 自动写 `已支付`；无 active outflow 自动写 `待支付`；金额不等不阻断，失败状态不覆盖 |

任何 writer 都不能要求本页面 freshness enqueue/polling 才能达到正确结果。外部系统未同步到 PostgreSQL 属于 integration lag，不允许通过页面 fallback 绕过。

## 依赖方向

```text
route -> query service -> page PostgreSQL repository -> canonical tables
route -> command service -> Workbench relation command
relation repository -> durable reconcile event -> oa-sync handler -> OA payment adapter + PostgreSQL snapshot
OA authoritative all snapshot -> durable missing-OA removal event -> oa-sync handler -> canonical recheck -> MySQL delete
frontend -> page API only
```

- route 只做 auth、参数转交、HTTP 映射。
- service 不依赖 `Application`、HTTP header/cookie 或 Flask response。
- repository 可以知道表结构和 SQL；service 不散落 SQL。
- 页面不得依赖 Redis、RabbitMQ、runtime worker、readiness、source version 或外部 OA storage。
- 页面 Audit 必须把 active OA+outflow 关系事实集与 canonical page consumer 结果对照，不能只证明 relation member 存在。

## 统一详情展示合同

- OA、银行流水和发票详情统一使用共享 `EntityDetailContent` 与 HeroUI `Table`/`Chip`；标签在左、真实值在右，禁止页面私有表格嵌套或内部字段表。
- 单条和多条使用同一公开字段合同；多条只按 `OA N`、`银行流水 N`、`发票 N` 重复分区，不输出关系概况、数量或是否多条。
- 仅展示 canonical API 实际返回且已登记为用户可见的字段；内部 ID、raw/source 字段和推导字段在共享边界过滤。
- 抽屉打开后按需执行一个有界详情 GET，不按成员 N+1；所有详情时间统一为 `Asia/Shanghai` 的无时区后缀格式。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend | `web/src/pages/OaPendingPaymentsPage.tsx`、`web/src/components/oaPendingPayments/*`、`web/src/features/oaPendingPayments/*` |
| Route/service | `routes_oa_pending_payments.py`、`oa_pending_payment_query_service.py`、`oa_pending_payment_query_contract.py`、`oa_pending_payment_export.py` |
| Query repository | `postgres_repositories/oa_pending_payment_query.py` |
| Pure row/detail composition | `oa_pending_payment_canonical_rows.py`、`oa_pending_payment_details.py` |
| Command | `oa_pending_payment_command_service.py`、`workbench_relation_command_service.py` |
| Payment reconcile | `oa_payment_status_reconcile.py`、`oa_payment_status_reconcile_contract.py`、`postgres_repositories/oa_payment_status_reconcile.py` |
| Canonical snapshots | `postgres_repositories/oa_pending_payment_source_snapshot.py`、`oa_pending_payment_admission.py`、`oa_projection.py` |
| Tests/docs | `tests/test_oa_pending_payment_*`、`web/src/test/OaPendingPayment*`、本目录 |

## 已从页面运行时删除

- `OaPendingPaymentReadModelService` rows/detail route dependency。
- page `read_model_status` / source versions / refresh enqueue / barrier targets。
- Redis versioned rows payload。
- `If-None-Match`、ETag、`202 refreshing`、`304`。
- frontend conditional polling、visibility retry 和 Audit barrier wait。
- command response 的 `readModelRefresh` envelope。
- 人工 `writeback-paid` / `confirm-paid` API、按钮与 page-command direct MySQL write。

旧 service/projector/worker、manifest/scope/registry、App Status、deploy/RabbitMQ registration、Redis cache schema 和 invoice-lifecycle 间接依赖已在跨页面清理中删除。`read_model.oa_pending_payment_*` 历史 migration/表暂留作回滚证据，没有运行时 reader/writer。

旧 `oa_pending_payment_relation_promotion_service.py`、`postgres_repositories/oa_pending_payment_relation.py`、pending bank claim 排除和 promotion runtime 已删除。旧关系表不再参与页面查询、候选占用、关联台 source proof、OA sync 或数据重置。

## 禁止回流

- 禁止 dual read、shadow/fallback、cache 或页面访问 enqueue。
- 禁止读取 `workbench_relation` projection 代替 active canonical relation。
- 禁止从页面请求访问 OA Mongo/MySQL/对象存储。
- 禁止恢复旧 filter endpoint、全量 `all_rows()`、Python/浏览器分页。
- 禁止因历史表仍存在而恢复本页 read model 依赖。
- 禁止把银行流水、发票、relation/raw payload 或页面筛选条件并入 OA 事实源导出。

## 2026-09-15 日常报销子项展示修复

OA 详情复用同次 canonical 批量 hydration，按请求 OA ID 选择原单据，追加全部费用明细节；多 OA 关系不得误取主 OA。列表保持父 OA 行和原有响应形状；详情不传附件原始载荷或内部子项 ID。无每子项查询、缓存或新 worker。

## 右侧抽屉交互（2026-09-15）

本模块复用的右侧抽屉遵循[统一关闭行为](../../dev/right-drawer-dismissal.md)：外部点击/Esc 不关闭，X 继续执行已有关闭保护。业务 owner 持有保存/确认完成状态，公共 AppDrawer 仅展示 `completion`；不改变本模块后端 API、权限、事实写入及查询 I/O。旧的重复退出按钮和成功自动关闭路径已移除，内部编辑取消仍按局部职责处理。

## 2026-09-21 ETC 跨页面正式成员读取

- OA 待付款、进项使用及待找发票共用 `postgres_repositories/relation_invoice_members.py` 的只读成员展开：通过提交批次准确身份、active bridge 或既有 canonical `etc_invoice_id` 取得真实发票；同一 canonical 发票去重，软删除和撤回关系按当前事实处理。保留原关系 ETC summary，不另写一套关系，不把 ETC 原始票据伪造成正式发票。
- 读取在页面既有只读 snapshot 内集合执行；没有新增缓存、read model、worker 或逐票查询。进项合并组搜索覆盖全部成员，+N 与详情抽屉使用同一成员集合，流水/OA 金额按实体去重；汇总付款不按每张发票复制累计。
- 文件范围新增共享 repository SQL；各页面现有 query/assembler/API DTO 和权限保持各自 owner。旧的仅以显式 invoice row ID 读取 ETC 关系的路径已替换。回归入口：`tests/test_etc_relation_page_reads_postgres.py`，覆盖进行中 OA、47 张票、显式重复成员、成员搜索、删除、撤回与三页详情。

## 2026-09 流水拆分合同

银行原金融事实与导入身份不变；银行拆分 owner 的持久化子项通过用途视图进入业务关联。详情使用父交易，列表标签显示当前子项；金额统计不得父子重复相加。 具体输入/输出、跨模块消费、旧链路清理及测试见 [流水拆分 I/O](../../dev/bank-transaction-splits.md)。

### 流水拆分写入边界（2026-09-23）

- `OaPendingPaymentCommandService` 接收显式 `bank_transaction_reader(row_ids)`，一次批量读取选中用途单元；PostgreSQL 由 `bank_transactions_for_command` 从 units 读取，禁止通过 import service 原流水 get 方法解析子项。
- missing child 在关系写入前返回 `bank_transaction_not_found`；原 parent 已拆分后不再作为付款用途单元。分类读取使用 canonical category projection 的 units 口径。
- 本地 JSON backend 明确只提供未拆分银行身份；其 relation repository adapter 的 current-unit resolver 为恒等映射，不猜测拆分。
- 测试：`test_oa_pending_payment_command_service.py` 批量读取、子项金额、缺失身份；`test_bank_split_relations_postgres.py` 真实子项读取及原 parent 排除。

## 2026-09-24 拆分流水的单据核对范围

同一现有 active 关联的用途比较复用 `bank_split_relation_scope` 的 SQL/Python 规则；银行金融事实、子项事实与关联成员不改写。只有全为拆分子项、同一收支方向，且单据目标金额恰好唯一等于完整本金用途组或完整其他用途组时，取该组核对。本金单据可以匹配本金，不再一律删除外部往来子项；金额相同的两组、金额不匹配、混合收支或包含未拆分流水时保留完整证据。

SQL 分页/筛选/汇总和 Python 行数据/详情组装使用相同范围，按集合执行，无逐行查询。OA 已付金额使用 OA 合计目标；发票页面使用当前发票组目标。进项含拆分的当前金额闭合不再依赖旧 relation.amount_check 的历史失败值，仍保留 OA 金额一致、正式关联与原支付规则约束；未拆分、无 OA 抵扣及销项超额收款/红蓝票规则不变。验证入口：`tests/test_bank_split_document_scope_postgres.py`，覆盖利息/本金单据、旧核对失败、金额歧义、未匹配、混合方向、未拆分兄弟流水，检查 SQL 汇总与行数据一致。

## 2026-09-24 原始流水金额展示

银行列表聚合输出 `original_amount`、`original_transaction_count` 与按父身份去重的完整 `bank_split_parts`；单笔 summary 输出 `parent_row_id`、`original_amount`。用途金额与已付/已收业务字段保持原意，不能被原始金额覆盖。银行金额筛选/排序、导出和详情按对应原始流水口径，关键词仍可搜索用途金额；分页与批量查询不变。具体 DTO、导出列与旧路径删除合同见 [流水拆分 I/O](../../dev/bank-transaction-splits.md#2026-09-24-银行原始金额与用途金额展示合同)。没有新增 read model、worker 或持久化事实。
