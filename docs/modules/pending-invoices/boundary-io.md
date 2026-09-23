# 待找发票模块边界与 I/O

日期：2026-08-18

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 页面读边界：页面专属 API → `PendingInvoiceCanonicalQueryService` → `PostgresPendingInvoiceCanonicalRepository` → PostgreSQL canonical facts。
- 运行时语义：页面没有 read-model freshness gate、refresh enqueue、polling、202、stale/fallback 或 `read_model_status/source_versions`。
- 共享资源：`search` 与 `workbench_relation` 只服务各自登记消费者；旧
  `pending_invoice`、search-pending、invoice-lifecycle 页面 worker 已删除。

## 职责边界

### 负责

- 待找发票 rows、summary、全期间 statistics、filter options、筛选、排序、服务端分页和导出。
- 页面候选发票、relation detail、流水/发票/OA object detail。
- 规则读取/保存、选择已有发票、收入状态覆盖的页面 API 与写后重新 GET。
- 保持支出/收入/现金收入、`paid_invoiced`、无需开票、OA/进销项覆盖、规则优先级和权限审计口径。

### 不负责

- 不拥有 bank/invoice/OA canonical facts，也不直接写这些表。
- 不拥有 `app.workbench_pair_relations`；关系写入仍委托 `WorkbenchRelationCommandService`。
- 不拥有 Search API、invoice lifecycle 页面或共享 read-model/worker 的删除。
- 不负责创建新发票；待找发票 manual preview/confirm 旧 service 写链已删除，单张发票统一由发票导入模块负责。
- 不从外部 OA/Mongo/MySQL/对象存储读取页面请求。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| direction/filter/date/keyword/field filters/sort/page/include_statistics | `PendingInvoicesPage.tsx`、`features/pendingInvoices/api.ts` | route 只传递解析后的 query；service 验证方向、筛选、日期、排序、过滤器、分页和统计开关；repository 负责 SQL。纯金额 keyword 使用无千分位文本并查询 canonical 流水、发票、已付和待付金额字段。 |
| 页面 canonical facts | PostgreSQL `app.*` | 银行流水、分类/确认、settings、pending income overrides、invoice/OA snapshots；银行 effective category 与银行明细保持同一优先级，持久人工覆盖优先于内部转账和当前自动规则；禁止读取 `read_model.pending_invoice_*`、`read_model.bank_detail_*`、`read_model.workbench_relation_*`、`read_model.search_*` |
| 正式配对关系 | `app.workbench_pair_relations` | 只读取 `status='active'`；排除 `turnover_manual_closure`；跨月 relation 不按当前月份截断 |
| OA workflow facts | `app.oa_applications` + `app.oa_pending_payment_admissions` | 同一 canonical OA projection 合并 completed/in-progress；OA DTO 输出 `workflow_status`，重复 OA identity fail closed |
| 候选与详情 | 页面专属 API | 候选采用 canonical input invoices + selected canonical expense banks + active relation facts；object detail 按 canonical id 有界读取 |
| 规则/关联/收入状态写入 | existing application/rules services | 保留权限、audit、idempotency、CAS/占用冲突、command 状态；写成功后页面重新 GET canonical facts |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| rows + summary + optional statistics | 前端页面 | 每次请求使用同一显式 `REPEATABLE READ / READ ONLY` snapshot；默认返回全期间 statistics，`include_statistics=false` 返回 `statistics=null` |

全期间 `statistics` 只包含流水总数、支出、收入、OA、进项发票和销项发票数量；旧已找到/待找、现金状态和关系状态数量字段已删除。
| rows.filter_options | 前端筛选 | rows 首响应只返回稳定字段定义，不执行高基数 options 聚合；页面完成首响应后调用专用 `/filter-options`，每字段最多 50 项，数据库聚合且不阻塞表格首屏。 |
| export-preview/export | 前端导出 | 复用同一 canonical row DTO；最大 20,000 行，超限先报错；不读取页面 read model |
| relation/object detail | 前端抽屉 | active canonical relations；统一只返回 `title/subtitle?/detail_available/sections` 公开合同，`kind=bank|invoice|oa` 只控制响应分区；禁止返回 relation case、raw payload、内部 form id 或重复 summary 容器 |
| OA 栏状态 | 前端 | 使用 HeroUI 原生 chip 显示申请类型与“已完成/进行中”；移除 OA “已配对” chip，relation status 不替代 workflow status |
| 发票栏 | 前端 | 有发票号码/日期即表达已有发票关系，不再重复显示“已配对” chip |
| invoice candidates | 前端选择已有发票抽屉 | 服务端过滤、排序、分页；固定两次 SELECT；返回 candidate/bank relation status 与关联流水数 |
| loading/empty/error | 前端可观察状态 | loading、合法空集、错误可区分；没有 refreshing/stale UI 或轮询 |
| table frame | 前端布局 | 与进项发票使用情况、销项发票收款情况、OA 待付款核对共用 `finance-page-table-frame` 有界高度和 contained 内部滚动，不创建页面私有高度分支 |

## 一致性、查询与性能

- `PostgresPendingInvoiceCanonicalRepository.query()` 显式开启 `REPEATABLE READ / READ ONLY`。
- rows、当前筛选 summary 和 counts 由一次 set-based SQL 计算，分页在 SQL 中执行；全期间 statistics 只在 `include_statistics=true` 时聚合。
- 页面首次加载和筛选变更先调用 `/api/pending-invoices/rows?include_statistics=false`；成功渲染 rows 后再非阻塞调用同一 rows endpoint 加载全期间 statistics，并调用 `/api/pending-invoices/filter-options` 加载选项。辅助请求失败不得清空或锁住已返回 rows。
- 页面 row DTO 只保留 `bank_transactions.primary|summaries`、`input_invoices.primary|summaries` 和
  `oa.primary|summaries` canonical 容器；旧 `bank_transaction`、`invoices`、`oa_applicant` 重复字段不再输出。
- 列表标签字典只含展示元数据；规则 matcher、account scope 和其它执行期字段只留在后端 settings/query owner。
- 分类/确认/income override、relation members、invoice/OA/bank summaries 都批量聚合；禁止 per-row/per-group N+1。
- 自动规则字符串使用 PostgreSQL `normalize(..., NFKC)`、空白折叠及现有“帐户→账户”口径；`include_statistics=false` 时只为请求方向构建规则匹配文本，内部转账与 relation 事实仍读取双方向 canonical rows，禁止用方向裁剪改变业务判断。
- SQL 分类后由 `pending_invoice_status_payload` 再校验；若 SQL 和领域策略分歧则请求失败。
- 50,003 条本地 PostgreSQL canonical bank rows 和生产 SLO 实测记录在 `implementation-notes.md`；本次未新增 cache、queue、worker、materialized view、索引或依赖。

## 统一详情展示合同

- OA、银行流水和发票详情统一使用共享 `EntityDetailContent` 与 HeroUI `Table`/`Chip`；标签在左、真实值在右，禁止页面私有打印版、统计概况或嵌套卡片。
- 单条和多条使用同一公开字段合同；多条只按 `OA N`、`银行流水 N`、`发票 N` 重复分区，不输出关系数量、是否多条或内部关系元数据。relation detail 在一次只读 snapshot 中集合读取成员，不能复用 rows 全页统计查询或逐成员补查。
- 仅展示 canonical 详情 API 实际返回且已登记为用户可见的字段；内部 ID、raw/source 字段和推导字段在共享边界过滤。发票币种等非事实字段不得用默认值补造。
- OA 单号只来自 completed OA projection 的 `workflow_no`（权威 `detail_fields.OA单号`）或进行中 admission 的真实 workflow/form number；`expense_claim`、`payment_request` 仅是内部表单类型，绝不能作为 OA 单号展示。
- 抽屉打开后按需执行一个有界详情 GET，不按成员 N+1；所有详情时间统一为 `Asia/Shanghai` 的无时区后缀格式。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/PendingInvoicesPage.tsx` |
| Frontend API/types/components | `web/src/features/pendingInvoices/*`、`web/src/components/pendingInvoices/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_pending_invoices.py` |
| Page query service/repository | `backend/src/fin_ops_platform/services/pending_invoice_canonical_query.py` |
| Existing write/export formatting | `pending_invoice_service.py`、`pending_invoice_rules_application_service.py` |
| Minimal assembly | `backend/src/fin_ops_platform/app/server.py` |
| Tests | `tests/test_pending_invoice_canonical_query.py`、`tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoices*.test.*` |

## 依赖方向

- 允许：page route → canonical query service → page-specific PostgreSQL repository。
- 允许：page route → existing application/rules services for writes and pure export formatting。
- 禁止：route/server 堆业务 SQL；service 接收 `Application`；repository 依赖 HTTP/auth。
- 禁止：页面直接访问共享 read model、worker、queue、cache 或外部同步源。

## 跨页面清理结果

- `PendingInvoiceReadModelService`、source-version provider、repository/projection、manifest/query-owner 和 `search-pending`/invoice-lifecycle 页面链已删除。
- 独立 Search runtime 已删除；`workbench_relation` 共享 distribution 只保留给明确登记消费者，本页面不消费它。
- `read_model.pending_invoice_*` 历史 migration/表暂留作回滚证据，没有运行时 reader/writer。
- `app.pending_invoice_manual_invoice_commands` 名称为历史遗留，但仍承载当前 attach-existing/income-status command 并保存既有审计数据；不得据此恢复已删除的 manual invoice writer。

## 2026-09-15 日常报销子项展示修复

OA detail SQL 读取原单据 canonical expense_items，服务使用共享公共详情投影追加费用明细节；移除旧服务重复拼装逻辑。详情展示原始子项，不创建关系、不改变发票/银行详情、列表、导出或 worker。

## 右侧抽屉交互（2026-09-15）

本模块复用的右侧抽屉遵循[统一关闭行为](../../dev/right-drawer-dismissal.md)：外部点击/Esc 不关闭，X 继续执行已有关闭保护。业务 owner 持有保存/确认完成状态，公共 AppDrawer 仅展示 `completion`；不改变本模块后端 API、权限、事实写入及查询 I/O。旧的重复退出按钮和成功自动关闭路径已移除，内部编辑取消仍按局部职责处理。

## 2026-09-21 ETC 跨页面正式成员读取

- OA 待付款、进项使用及待找发票共用 `postgres_repositories/relation_invoice_members.py` 的只读成员展开：通过提交批次准确身份、active bridge 或既有 canonical `etc_invoice_id` 取得真实发票；同一 canonical 发票去重，软删除和撤回关系按当前事实处理。保留原关系 ETC summary，不另写一套关系，不把 ETC 原始票据伪造成正式发票。
- 读取在页面既有只读 snapshot 内集合执行；没有新增缓存、read model、worker 或逐票查询。进项合并组搜索覆盖全部成员，+N 与详情抽屉使用同一成员集合，流水/OA 金额按实体去重；汇总付款不按每张发票复制累计。
- 文件范围新增共享 repository SQL；各页面现有 query/assembler/API DTO 和权限保持各自 owner。旧的仅以显式 invoice row ID 读取 ETC 关系的路径已替换。回归入口：`tests/test_etc_relation_page_reads_postgres.py`，覆盖进行中 OA、47 张票、显式重复成员、成员搜索、删除、撤回与三页详情。


## 2026-09-23 流水子项用途边界

用途分类/配对使用 `app.bank_transaction_units`，配置为无需发票的本金不参与待票 paid_total。删除按整 case 的 `turnover_manual_closure` 排除条件，混合本金/费用组仍可进入待票。相同父流水子项按父身份合并展示，未筛选时优先显示需要发票的用途；详情查询子身份后解析真实父流水，关联详情按父去重。每个银行详情 section 明确返回 `bank_transaction_id`。

验证：`tests/test_bank_split_consumers_postgres.py` 使用隔离 PostgreSQL 数据库覆盖原始金额不变、子项标签筛选、成本待分配、待票金额和详情父身份、往来补充信息迁移。往来手工成员重建和含利息 case 的本金闭环由对应 service/query 单元测试覆盖。

列表主流水和 summaries 批量返回 `bank_transaction_id`（原流水公开身份）、`parent_bank_transaction_id`、`parent_amount`、`bank_split_parts`（含 `category_path`）、`bank_split_version`；从当前分页及其关联银行集合一次 SQL 取得，不逐行拉取。待票查询及写入服务必传 `bank_units_by_ids` 读取端口；生产由 canonical unit repository 提供，单笔补票、批量补票、收入状态操作均可接受子项身份，金额运算使用用途金额。原 import service 只保留发票等原有职责，不用父流水读取器处理 child UUID。
