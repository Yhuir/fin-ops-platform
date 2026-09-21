# 进项发票使用情况模块边界与 I/O

日期：2026-08-11

## 模块化状态

- 状态：`canonical-direct-read`
- 当前边界可信度：high
- Query owner：`InputInvoiceUsageCanonicalQueryService`
- PostgreSQL owner：`PostgresInputInvoiceUsageQueryRepository`
- 旧页面 read model：API/frontend、projection/repository、worker/registry/deploy 和 lifecycle 间接链均已删除。

## 职责边界

### 负责

- 进项发票使用 rows、summary、statistics、facets、筛选、排序和服务端分页。
- 发票/OA/银行流水/关联发票详情、当前筛选导出和 OA reverse preview。
- active relation component 聚合、金额合计和支付状态计算。
- OA reverse canonical batch、relation、审计、CAS/idempotency 写入及写后 GET。

### 不负责

- 不拥有 OA 登录和外部 OA 数据同步。
- 不拥有 `app.workbench_pair_relations` 的写模型。
- 不读取或刷新 Workbench、invoice lifecycle 或页面 read model。
- 不修改共享 worker、manifest、scope policy、dispatcher、deploy env 或 App Status registry。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| rows 查询 | `InputInvoiceUsagePage.tsx` | `page`、`page_size`、keyword、日期/月、filters、sort；非法值返回 400。纯金额 keyword 使用无千分位文本并查询价税合计、未税金额、税额和关联流水金额。 |
| canonical invoices | `app.invoices` | 只取非删除 input invoices；金额和日期保持 canonical 口径 |
| formal relations | `app.workbench_pair_relations` | 只取 `status='active'`；按 relation component 聚合 |
| bank/OA facts | `app.bank_transactions`、`app.oa_applications`、`app.oa_pending_payment_admissions` | 只读取已同步 PostgreSQL snapshot；OA summary 输出 canonical `workflowStatus=completed|in_progress`，重复 identity fail closed |
| OA detail id | rows DTO 的 `oa.id` | 只接受 canonical OA identity；repository 通过既有 OA workflow repository 定向查询，不经过进项发票使用行 hash |
| payment rules | `app.app_settings` | 使用现有 input invoice payment rule contract |
| OA reverse facts | `app.input_invoice_usage_oa_reverse_batches` | statistics、preview 和命令状态 |
| lifecycle command | 页面专属写 API | 保持原权限、审计、CAS/idempotency；成功后 GET |
| OA 草稿预填配置 | `GET/PUT /api/workbench/settings/oa-draft-prefill/input-invoice-usage` | 所有已授权 App 账户可见并可只读打开页面右上角抽屉，仅 admin 可编辑/保存独立 versioned family；创建 reverse batch 时固化当次配置快照，后续 OA draft 创建不受并发设置变更影响。多销方或缺失销方 fail closed |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| `/rows` | 页面 | 同一 snapshot 返回 `rows`、`summary`、`statistics`、`pagination`、`filterConfig`、`filterOptions`；`payment_status` 候选排除自身状态条件后聚合，并按规则字典补齐零数量状态，选择状态不得缩减候选词表 |

`statistics` 只包含 canonical 进项发票总数、已完成/进行中 OA、支出/收入流水数量；同 ID OA 以已完成优先，旧付款、关系组和反提批次数量字段已删除。
| relation/details | drawer | row/invoice/bank 按 canonical id 定向读取，不存在返回 404；OA 详情按 canonical OA id 返回 `detailAvailable=true|false`，不可用时保持 200 的既有 drawer 合同 |
| OA 申请人列与详情 | frontend | 总览只显示申请人、申请类型、多 OA 数量和合计金额，不显示流程状态；单条 OA 详情和多 OA 关联详情使用 canonical `workflowStatus` 显示“已完成/进行中”，不得读取或回退 linked/unlinked/unpaired 关系状态 |
| export preview/download | export drawer | 复用 canonical filters/sort；20,000 行上限和原错误合同不变 |
| OA reverse preview/command | OA reverse drawer | preview 只读 canonical snapshot，并分别返回 `permissions.canCreateDraft` 写能力与当前整组 `canCreateDraft` 业务可创建状态；前端对当前勾选集合只做同一非空销方的轻量可用性判断，提交前必须按精确发票集合重新 preview，并以新 preview 的权限、业务状态和 hash 为准。命令只写 canonical facts；候选金额展示与本地搜索都使用无千分位文本。OA payload 动态写目标申请人、当天日期、所选总额和唯一销方，申请事由只显示发票数/发票号码，内部 reverse batch ID 仅保留结构化字段。 |
| write result | 页面 | 不含 refresh target/barrier；页面成功后重跑当前 GET |

`/rows` 不输出 `read_model_status`、`source_versions`、`refresh_enqueued`、scope 或 polling 字段。

## 一致性与性能合同

- 每个页面读请求开启一个 `REPEATABLE READ READ ONLY` transaction。
- rows、summary、statistics、facets 和用于组装当前页的 facts 都在该 transaction 中读取。
- rows/summary/facets 复用一次 materialized canonical CTE；付款规则从同一 request snapshot 交给有界行装配，禁止逐行重读 `app_settings`。整个请求最多 8 条批量 SQL statement，数量不随当前页行数或 relation 数增长。
- 支付状态的 self-excluding facet 在同一 SQL statement、同一 canonical CTE snapshot 内计算；禁止为保持完整候选额外请求 `/filter-options` 或增加数据库往返。
- 服务端完成筛选、排序、分页；Python 只组装当前页有界 facts。
- OA 详情使用一个独立只读 repeatable-read transaction 和一次有界 OA identity 查询；禁止加载页面 row group、发票或流水作为间接查找。
- 只有 EXPLAIN 或真实慢查询证据支持时才增加索引；本模块不自行创建 migration。

## 搜索控件展示边界

- 页面复用 `QuerySearch` 和 HeroUI `SearchField`，只控制工具栏排列与搜索区域宽度；内部输入、图标和清除按钮由原生组件管理。
- 搜索外框承担统一边框与聚焦反馈，页面不得通过后代 `input` 选择器再次添加边框、背景或聚焦阴影。旧原生输入框的普通、hover、focus-visible 样式已删除。
- 关键词草稿、提交、清除、分页和查询 API 合同保持不变。

## 统一详情展示合同

- OA、银行流水和发票详情统一使用共享 `EntityDetailContent` 与 HeroUI `Table`/`Chip`；标签在左、真实值在右，页面不得维护第二套详情 renderer。
- 单条和多条使用同一公开字段合同；多条只重复 `OA N`、`银行流水 N`、`发票 N` 分区，不输出关系概况、数量、是否多条或内部 case/source 信息。
- 仅展示 canonical API 实际返回且已登记为用户可见的字段；内部 ID、raw payload、批次字段和推导字段在共享边界过滤。
- 详情按需一次有界读取，不得逐成员 N+1；时间统一为 `Asia/Shanghai` 的无 `T`/`Z`/offset 格式。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend | `web/src/pages/InputInvoiceUsagePage.tsx`、`web/src/features/inputInvoiceUsage/*`、`web/src/features/oaDraftPrefill.ts`、`web/src/components/inputInvoiceUsage/*`、`web/src/components/common/OaDraftPrefillDrawer.tsx` |
| Route | `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py` |
| Query service | `input_invoice_usage_canonical_query_service.py` |
| Business assembler | `input_invoice_usage_service.py` |
| Query repository | `postgres_repositories/invoice_usage_collection_query.py` |
| Commands/export | `input_invoice_usage_oa_reverse_service.py`、`input_invoice_usage_export_service.py` |
| Tests | `tests/test_input_invoice_usage*.py`、`tests/test_invoice_usage_collection_canonical_query.py`、`web/src/test/InputInvoiceUsage*.test.tsx`、`web/e2e/input-invoice-usage-flow.spec.ts` |

## 依赖方向

`frontend -> route -> canonical query service -> page query repository -> canonical PostgreSQL tables`

写路径为：

`frontend -> route -> command service -> canonical repository/audit -> current rows GET`

禁止依赖方向：

- route -> SQL
- query service -> HTTP/session
- page query repository -> read-model tables
- frontend -> filter-options/read-model refresh/status endpoint

## 跨页面清理结果

`InvoiceUsageCollectionSqlProjectionBuilder` 的 input projection、invoice-usage-collection worker/handler/registry/manifest/deploy、input read-model scope/App Status/audit/repair 注册项已删除。历史 migration/表暂留作回滚证据，没有运行时 reader/writer。

## 2026-09-15 日常报销子项展示修复

OA 详情 expenseItems 使用公共费用字段白名单（项目、金额、费用类型/内容/说明、报销日期、支付方式、发票种类、票据张数、附件文件数），页面按顺序展示所有子项。canonical 及现有非 PG service 共用纯投影，禁止输出附件原始载荷。列表、关联写入和成本分配不变。

## 右侧抽屉交互（2026-09-15）

本模块复用的右侧抽屉遵循[统一关闭行为](../../dev/right-drawer-dismissal.md)：外部点击/Esc 不关闭，X 继续执行已有关闭保护。业务 owner 持有保存/确认完成状态，公共 AppDrawer 仅展示 `completion`；不改变本模块后端 API、权限、事实写入及查询 I/O。旧的重复退出按钮和成功自动关闭路径已移除，内部编辑取消仍按局部职责处理。

## 页面进入与时间范围（2026-09-21）

页面每次挂载在现有 query session 的 `restoreQuery` 清除 `month`、`invoiceDateFrom/To`、`invoice_date` 与 `bank_trade_time` 日期列条件，首个 rows/导出请求使用清理后的范围；不新增日期控件。保留 keyword、非日期 filters、sort 和 pageSize。旧范围确实含日期时，page 重置为 1，activeWorkflow/detailTarget 清空；原为全部时不无条件重置合法页码与流程。普通刷新、排序、分页、保存回读及抽屉关闭不执行 restore。

通用进入边界见 [时间范围实施约定](../../dev/date-range-default-all-plan.md)。HTTP schema、权限、业务资格与事实写入边界不因此改变。

## 2026-09-21 ETC 跨页面正式成员读取

- OA 待付款、进项使用及待找发票共用 `postgres_repositories/relation_invoice_members.py` 的只读成员展开：通过提交批次准确身份、active bridge 或既有 canonical `etc_invoice_id` 取得真实发票；同一 canonical 发票去重，软删除和撤回关系按当前事实处理。保留原关系 ETC summary，不另写一套关系，不把 ETC 原始票据伪造成正式发票。
- 读取在页面既有只读 snapshot 内集合执行；没有新增缓存、read model、worker 或逐票查询。进项合并组搜索覆盖全部成员，+N 与详情抽屉使用同一成员集合，流水/OA 金额按实体去重；汇总付款不按每张发票复制累计。
- 文件范围新增共享 repository SQL；各页面现有 query/assembler/API DTO 和权限保持各自 owner。旧的仅以显式 invoice row ID 读取 ETC 关系的路径已替换。回归入口：`tests/test_etc_relation_page_reads_postgres.py`，覆盖进行中 OA、47 张票、显式重复成员、成员搜索、删除、撤回与三页详情。
